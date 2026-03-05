"""AgentOrchestrator MCP Server
================================

Expose AgentOrchestrator chains (and plain async functions) as MCP tools so
that any MCP-compatible UI (Cohere North, Claude, etc.) can call them.

The server implements the MCP JSON-RPC 2.0 protocol over HTTP and supports
Server-Sent Events (SSE) streaming for long-running tool calls.

Design principles
─────────────────
- **Explicit opt-in only** — nothing is auto-discovered or auto-exposed.
  You register each tool deliberately with `bind_chain()` or `@mcp.tool()`.
- **`bind_chain()` is the primary path** for AgentOrchestrator users. It wires
  the chain's `debug_callback` hook into an SSE stream automatically — no
  manual queue management needed in your service code.
- **`@mcp.tool()` is the escape hatch** for simple one-off functions that don't
  need the full pipeline (e.g. a ticker lookup, a date helper).
- **Protocol-complete** — handles `initialize`, `tools/list`, `tools/call`.
- **JWT bearer auth** — verifies the shared secret from Cohere / any MCP client.
  Set `secret=""` to disable auth (dev only).

Usage
─────
    from agentorchestrator.server.mcp import MCPServer

    mcp = MCPServer(secret=settings.mcp_server_secret)

    # Primary path — chain binding with automatic SSE streaming
    mcp.bind_chain(
        ao=ao,
        chain_name="deep_research",
        tool_name="deep_research",
        description="Iterative multi-source financial research agent.",
        input_schema={
            "query": {"type": "string", "description": "The research question"},
            "system_instructions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional constraints",
            },
        },
        context_builder=lambda args: {
            "query": args["query"],
            "system_instructions": args.get("system_instructions", []),
            "llm_client": llm,
            "mcp_service": mcp_svc,
        },
        step_labels={
            "plan_research":    "Planning research sub-queries…",
            "search_news":      "Searching news sources…",
            "search_sec":       "Searching SEC/EDGAR filings…",
            "search_financial": "Searching financial databases…",
            "aggregate_sources":"Aggregating findings…",
            "cross_verify":     "Cross-verifying findings…",
            "generate_report":  "Generating final report…",
        },
    )

    # Escape hatch — plain async function
    @mcp.tool(name="get_date", description="Get today's date", input_schema={})
    async def get_date() -> str:
        return datetime.now().isoformat()

    # Mount on any FastAPI app
    app.include_router(mcp.router, prefix="/mcp")

SSE event types (tools/call streaming response)
───────────────────────────────────────────────
    {"type": "progress", "step": "plan_research", "label": "Planning…",
     "success": true, "duration_ms": 1234.0}

    {"type": "result", "content": "# Research Report\n…", "stats": {...}}

    {"type": "error",   "message": "something went wrong"}

    {"type": "heartbeat"}   — keep-alive, safe to ignore
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from base64 import b64decode
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_bearer_token(authorization: str, server_secret: str) -> bool:
    """Verify an inbound MCP bearer token produced by create_bearer_token().

    The token is a base64-encoded JSON object (AuthHeaderTokens) that contains
    the server_secret used when the token was created.  We decode it and
    compare the embedded secret against the expected value.

    Args:
        authorization: Full value of the Authorization header
                       (e.g. "Bearer <base64-token>").
        server_secret: The shared secret this server was initialised with.

    Returns:
        True if the token is valid, False otherwise.

    Example:
        ok = verify_bearer_token(request.headers.get("Authorization", ""), secret)
    """
    try:
        token = authorization.removeprefix("Bearer ").strip()
        decoded = b64decode(token.encode()).decode()
        payload = json.loads(decoded)
        return payload.get("server_secret") == server_secret
    except Exception:
        return False


# ── Tool definition ───────────────────────────────────────────────────────────

@dataclass
class MCPToolDef:
    """Internal representation of a registered MCP tool."""
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable
    is_streaming: bool = False


# ── MCPServer ─────────────────────────────────────────────────────────────────

class MCPServer:
    """Expose AgentOrchestrator chains and plain functions as MCP tools.

    See module docstring for full usage examples.
    """

    def __init__(
        self,
        secret: str,
        server_name: str = "agentorchestrator-mcp",
        version: str = "1.0.0",
    ) -> None:
        """Initialise the MCP server.

        Args:
            secret:      Shared secret used to verify inbound bearer tokens from
                         Cohere North or any other MCP client.  Pass "" to
                         disable auth (development only).
            server_name: Name reported in the MCP initialize handshake.
            version:     Version reported in the MCP initialize handshake.
        """
        self._secret = secret
        self._server_name = server_name
        self._version = version
        self._tools: dict[str, MCPToolDef] = {}
        self.router = APIRouter(tags=["MCP"])
        self._register_routes()

    # ── Registration API ──────────────────────────────────────────────────────

    def tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
    ):
        """Decorator — register a plain async function as an MCP tool.

        Use this for simple one-off tools that don't need a full pipeline.
        For chains, use bind_chain() instead.

        The function may be:
        - A regular ``async def`` → returns the full result synchronously.
        - An ``async def`` that returns an ``AsyncGenerator`` → streams partial
          results; MCPServer wraps each yielded value as an SSE event.

        Example::

            @mcp.tool(
                name="get_ticker_price",
                description="Fetch the latest price for a stock ticker.",
                input_schema={"ticker": {"type": "string"}},
            )
            async def get_ticker_price(ticker: str) -> str:
                return await fetch_price(ticker)
        """
        def decorator(fn: Callable) -> Callable:
            is_gen = inspect.isasyncgenfunction(fn)
            self._tools[name] = MCPToolDef(
                name=name,
                description=description,
                input_schema=input_schema,
                handler=fn,
                is_streaming=is_gen,
            )
            logger.info("MCP tool registered: '%s' (streaming=%s)", name, is_gen)
            return fn
        return decorator

    def bind_chain(
        self,
        ao: Any,
        chain_name: str,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        context_builder: Callable[[dict[str, Any]], dict[str, Any]],
        step_labels: Optional[dict[str, str]] = None,
    ) -> None:
        """Bind an AgentOrchestrator chain as a streaming MCP tool.

        This is the **primary registration path** for AgentOrchestrator users.
        The chain's ``debug_callback`` hook is wired automatically into an SSE
        stream — no manual queue management needed in your service code.

        Streaming works as follows:
        1. ``tools/call`` is received from the MCP client (e.g. Cohere North).
        2. ``ao.launch()`` is started as an ``asyncio.Task`` with a
           ``debug_callback`` that puts step-completion events onto a Queue.
        3. The async generator reads from the Queue and yields progress events
           as SSE ``data:`` frames until the pipeline finishes.
        4. The final ``result`` event carries the full output (e.g. the report).

        Args:
            ao:               AgentOrchestrator instance with the chain registered.
            chain_name:       Name of the chain as registered with ``ao``
                              (e.g. ``"deep_research"``).
            tool_name:        MCP tool name exposed to clients.  Does not have to
                              match ``chain_name``.
            description:      Human-readable description shown in ``tools/list``.
            input_schema:     JSON Schema ``properties`` dict for the tool's
                              input arguments.
            context_builder:  ``Callable(args_dict) → initial_data`` — builds
                              the ``data`` dict passed to ``ao.launch()``.
                              Use this to inject ``llm_client``, ``mcp_service``,
                              or any other context the chain steps expect.
            step_labels:      Optional ``{step_name: human_label}`` mapping for
                              richer progress messages in the MCP client UI.

        Example::

            mcp.bind_chain(
                ao=_ao,
                chain_name="deep_research",
                tool_name="deep_research",
                description="Multi-source financial research agent.",
                input_schema={
                    "query": {"type": "string"},
                    "system_instructions": {"type": "array",
                                            "items": {"type": "string"}},
                },
                context_builder=lambda args: {
                    "query": args["query"],
                    "system_instructions": args.get("system_instructions", []),
                    "llm_client": _llm,
                    "mcp_service": _mcp,
                },
                step_labels={
                    "plan_research":    "Planning research sub-queries…",
                    "generate_report":  "Generating final report…",
                },
            )
        """
        labels: dict[str, str] = step_labels or {}

        async def _chain_handler(**kwargs: Any) -> AsyncGenerator[str, None]:
            queue: asyncio.Queue = asyncio.Queue()

            # Sync callback — safe to call put_nowait() from inside the async loop
            def _debug_cb(ctx: Any, step_name: str, result: dict[str, Any]) -> None:
                queue.put_nowait({
                    "type": "progress",
                    "step": step_name,
                    "label": labels.get(step_name, step_name),
                    "success": result.get("success", True),
                    "duration_ms": round(result.get("duration_ms", 0), 1),
                    "error": result.get("error"),
                })

            async def _run() -> None:
                try:
                    result = await ao.launch(
                        chain_name,
                        context_builder(kwargs),
                        debug_callback=_debug_cb,
                    )
                    queue.put_nowait({"_sentinel": True, "result": result})
                except Exception as exc:
                    logger.exception("Chain '%s' failed in MCP tool '%s': %s",
                                     chain_name, tool_name, exc)
                    queue.put_nowait({"_sentinel": True, "error": str(exc)})

            asyncio.create_task(_run())

            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    # Keep-alive — prevents proxy / client timeouts
                    yield json.dumps({"type": "heartbeat"})
                    continue

                if item.get("_sentinel"):
                    if "error" in item:
                        yield json.dumps({"type": "error", "message": item["error"]})
                    else:
                        result = item["result"]
                        yield json.dumps({
                            "type": "result",
                            "content": result.get("report", str(result)),
                            "stats": result.get("stats", {}),
                        })
                    return

                yield json.dumps(item)

        self._tools[tool_name] = MCPToolDef(
            name=tool_name,
            description=description,
            input_schema=input_schema,
            handler=_chain_handler,
            is_streaming=True,
        )
        logger.info(
            "MCP chain bound: tool='%s' → chain='%s' (streaming=True)",
            tool_name, chain_name,
        )

    # ── JSON-RPC 2.0 routes ───────────────────────────────────────────────────

    def _register_routes(self) -> None:
        router = self.router

        @router.post("/initialize", summary="MCP handshake")
        async def initialize(request: Request):
            """MCP initialize — returns server capabilities."""
            self._require_auth(request)
            return JSONResponse({
                "jsonrpc": "2.0",
                "result": {
                    "serverInfo": {
                        "name": self._server_name,
                        "version": self._version,
                    },
                    "capabilities": {
                        "tools": {"streaming": True},
                    },
                },
            })

        @router.post("/tools/list", summary="List available MCP tools")
        async def tools_list(request: Request):
            """Return the catalogue of registered tools."""
            self._require_auth(request)
            tools = [
                {
                    "name": td.name,
                    "description": td.description,
                    "inputSchema": {
                        "type": "object",
                        "properties": td.input_schema,
                        "required": [
                            k for k, v in td.input_schema.items()
                            if not isinstance(v, dict) or not v.get("default")
                        ],
                    },
                }
                for td in self._tools.values()
            ]
            return JSONResponse({"jsonrpc": "2.0", "result": {"tools": tools}})

        @router.post("/tools/call", summary="Invoke an MCP tool")
        async def tools_call(request: Request):
            """Invoke a registered tool.

            - **Streaming tools** (chains bound with ``bind_chain()``) return
              ``text/event-stream`` SSE.
            - **Sync tools** (plain functions registered with ``@mcp.tool()``)
              return a JSON-RPC response immediately.
            """
            self._require_auth(request)

            body = await request.json()
            params = body.get("params", {})
            tool_name = params.get("name")
            arguments: dict[str, Any] = params.get("arguments", {})

            tool = self._tools.get(tool_name)
            if not tool:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": f"Tool '{tool_name}' not found. "
                                   f"Available: {list(self._tools)}",
                    },
                }, status_code=404)

            if tool.is_streaming:
                # Chain-bound or async-generator tool → stream SSE
                return StreamingResponse(
                    self._sse_wrap(tool.handler(**arguments)),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",  # Disable nginx buffering
                    },
                )

            # Plain sync tool → await and return JSON-RPC response
            try:
                result = await tool.handler(**arguments)
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [{"type": "text", "text": str(result)}],
                    },
                })
            except Exception as exc:
                logger.exception("MCP tool '%s' failed: %s", tool_name, exc)
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": str(exc)},
                }, status_code=500)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _require_auth(self, request: Request) -> None:
        """Raise HTTP 401 if the bearer token is invalid.

        Auth is skipped when ``secret`` was set to an empty string (dev mode).
        """
        if not self._secret:
            return
        auth = request.headers.get("Authorization", "")
        if not verify_bearer_token(auth, self._secret):
            raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    @staticmethod
    async def _sse_wrap(
        gen: AsyncGenerator[str, None],
    ) -> AsyncGenerator[str, None]:
        """Wrap an async generator of JSON strings as SSE ``data:`` frames."""
        try:
            async for chunk in gen:
                yield f"data: {chunk}\n\n"
        except Exception as exc:
            error_data = json.dumps({"type": "error", "message": str(exc)})
            yield f"data: {error_data}\n\n"
