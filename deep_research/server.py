"""Deep Research Agent — FastAPI service entry point.

Endpoints
─────────
  POST /run/deep_research          Submit a research query → run_id  (poll-based)
  POST /run/deep_research/stream   Submit + stream SSE progress in real time
  GET  /runs/{run_id}              Poll run status
  GET  /runs/{run_id}/output       Fetch the final report once complete
  GET  /chains                     List registered chains
  GET  /health                     Full health (LLM + MCP adapters)
  GET  /ready                      Kubernetes readiness probe
  GET  /live                       Kubernetes liveness probe

Streaming (SSE) event types
────────────────────────────
  run_started       {"run_id", "query"}
  step_completed    {"step", "success", "duration_ms", "error"}
  pipeline_completed {"run_id", "stats"}
  pipeline_failed   {"run_id", "error"}

Run locally
───────────
  uvicorn deep_research.server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agentorchestrator.core.orchestrator import AgentOrchestrator
from agentorchestrator.server.mcp import MCPServer
from agentorchestrator.services.llm_gateway import LLMGatewayClient
from agentorchestrator.services.mcp_service import MCPServiceManager
from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter

from deep_research.chain import CHAIN_NAME, build_pipeline
from deep_research.config import settings
from deep_research.middleware import setup_middleware

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# ── Application state ─────────────────────────────────────────────────────────

_ao: Optional[AgentOrchestrator] = None
_llm: Optional[LLMGatewayClient] = None
_mcp: Optional[MCPServiceManager] = None

# In-process run store: run_id → state dict
_runs: dict[str, dict[str, Any]] = {}

# Per-run asyncio queues: run_id → Queue[dict | None]
# None is the sentinel that tells the SSE generator the run is done.
_run_queues: dict[str, asyncio.Queue] = {}

# Human-readable labels shown in SSE progress events
_STEP_LABELS: dict[str, str] = {
    "plan_research":     "Planning research sub-queries…",
    "search_news":       "Searching news sources…",
    "search_sec":        "Searching SEC/EDGAR filings…",
    "search_financial":  "Searching financial databases…",
    "search_web":        "Supplementary web search…",
    "aggregate_sources": "Aggregating and deduplicating findings…",
    "cross_verify":      "Cross-verifying findings across sources…",
    "generate_report":   "Generating final report…",
}


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise LLM, MCP adapters, orchestrator, middleware."""
    global _ao, _llm, _mcp

    logger.info("Starting Deep Research Agent service…")

    # LLM client
    _llm = LLMGatewayClient(
        server_url=settings.llm_server_url,
        model_name=settings.llm_model_name,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
        api_key=settings.llm_api_key,
        oauth_endpoint=settings.llm_oauth_endpoint,
        client_id=settings.llm_client_id,
        client_secret=settings.llm_client_secret,
    )
    logger.info("LLM client initialised → %s", settings.llm_server_url)

    # MCP adapters — each is created, connected, then registered with the manager.
    # If an endpoint env var is not set the adapter is skipped gracefully; stub
    # tools in tools.py are used instead.
    _mcp = MCPServiceManager()

    _mcp_sources = [
        ("news",      settings.mcp_news_endpoint,      settings.mcp_news_secret,
         settings.mcp_news_routing,      settings.mcp_news_verify_ssl),
        ("sec",       settings.mcp_sec_endpoint,       settings.mcp_sec_secret,
         settings.mcp_sec_routing,       settings.mcp_sec_verify_ssl),
        ("financial", settings.mcp_financial_endpoint, settings.mcp_financial_secret,
         settings.mcp_financial_routing, settings.mcp_financial_verify_ssl),
    ]

    for adapter_name, endpoint, secret, routing, verify_ssl in _mcp_sources:
        if not endpoint:
            logger.warning("MCP adapter '%s' skipped — no endpoint configured", adapter_name)
            continue
        adapter = MCPToolAdapter(name=adapter_name)
        connected = await adapter.connect(
            endpoint=endpoint,
            secret=secret,
            use_path_routing=(routing == "path"),
            verify_ssl=verify_ssl,
        )
        if connected:
            _mcp.register_adapter(adapter)
        else:
            logger.warning(
                "MCP adapter '%s' failed to connect — falling back to stub", adapter_name
            )

    logger.info("MCP adapters initialised")

    # Orchestrator
    _ao = AgentOrchestrator(
        name="deep_research_service",
        max_parallel=settings.chain_max_parallel_steps,
        default_timeout_ms=settings.chain_default_timeout_ms,
    )
    build_pipeline(_ao)
    setup_middleware(_ao, _llm)
    _ao.check()
    logger.info("AgentOrchestrator ready — chain '%s' registered", CHAIN_NAME)

    # ── MCP Server — expose deep_research chain to Cohere North / MCP clients ─
    # Set MCP_SERVER_SECRET in your env to the shared secret you configure in
    # Cohere North's MCP connection settings.  Leave empty to disable auth.
    _mcp_server = MCPServer(
        secret=settings.mcp_server_secret,
        server_name="deep-research-agent",
        version="1.0.0",
    )
    _mcp_server.bind_chain(
        ao=_ao,
        chain_name=CHAIN_NAME,
        tool_name="deep_research",
        description=(
            "Iterative multi-source financial research agent. "
            "Searches news, SEC/EDGAR filings, and financial databases via "
            "internal MCP servers. Cross-verifies findings and returns a "
            "comprehensive cited Markdown report."
        ),
        input_schema={
            "query": {
                "type": "string",
                "description": (
                    "The research question, e.g. "
                    "'Show me all M&A deals > $1B in the past 2 weeks'"
                ),
            },
            "system_instructions": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Additional constraints, e.g. "
                    "'Exclude deals below $1B', 'Include all regions'"
                ),
            },
        },
        context_builder=lambda args: {
            "query": args["query"],
            "system_instructions": args.get("system_instructions", []),
            "llm_client": _llm,
            "mcp_service": _mcp,
        },
        step_labels={
            "plan_research":     "Planning research sub-queries…",
            "search_news":       "Searching news sources…",
            "search_sec":        "Searching SEC/EDGAR filings…",
            "search_financial":  "Searching financial databases…",
            "search_web":        "Supplementary web search…",
            "aggregate_sources": "Aggregating and deduplicating findings…",
            "cross_verify":      "Cross-verifying findings across sources…",
            "generate_report":   "Generating final report…",
        },
    )
    app.include_router(_mcp_server.router, prefix="/mcp")
    logger.info(
        "MCP server mounted at /mcp — tool 'deep_research' ready "
        "(auth=%s)", bool(settings.mcp_server_secret)
    )

    yield  # ── service running ──

    logger.info("Shutting down Deep Research Agent service…")
    if _mcp:
        await _mcp.shutdown()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Deep Research Agent",
    description=(
        "Iterative multi-source research agent built on AgentOrchestrator. "
        "Searches news, SEC filings, and financial databases via internal MCP servers; "
        "cross-verifies findings; and returns a comprehensive cited report."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ── Request / Response models ─────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str = Field(
        ...,
        description="The research question, e.g. 'Show me all M&A deals > $1B in the past 2 weeks'",
        min_length=5,
    )
    system_instructions: list[str] = Field(
        default_factory=list,
        description=(
            "Additional constraints applied throughout the pipeline. "
            "Examples: 'Include deals from all regions', 'Exclude deals below $1B'."
        ),
    )


class RunResponse(BaseModel):
    run_id: str
    status: str
    message: str


class RunStatusResponse(BaseModel):
    run_id: str
    status: str          # "pending" | "running" | "completed" | "failed"
    steps_completed: list[str]
    error: Optional[str] = None


class RunOutputResponse(BaseModel):
    run_id: str
    status: str
    report: Optional[str] = None
    stats: Optional[dict[str, Any]] = None


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(event_type: str, payload: dict[str, Any]) -> str:
    """Format a single SSE message."""
    data = json.dumps({"event": event_type, **payload})
    return f"data: {data}\n\n"


def _make_debug_callback(run_id: str):
    """
    Return a sync debug_callback compatible with ao.launch(debug_callback=...).

    The DAGExecutor calls this synchronously after each step completes inside
    the async event loop, so queue.put_nowait() is safe here.
    """
    def callback(ctx: Any, step_name: str, result: dict[str, Any]) -> None:
        queue = _run_queues.get(run_id)
        if queue is None:
            return

        event = {
            "step": step_name,
            "label": _STEP_LABELS.get(step_name, step_name),
            "success": result.get("success", True),
            "duration_ms": round(result.get("duration_ms", 0), 1),
            "error": result.get("error"),
        }
        # Update run store so polling clients also see step progress
        run = _runs.get(run_id)
        if run is not None and event["success"]:
            run.setdefault("steps_completed", [])
            if step_name not in run["steps_completed"]:
                run["steps_completed"].append(step_name)

        queue.put_nowait(event)

    return callback


async def _sse_generator(
    run_id: str,
    request: Request,
) -> AsyncGenerator[str, None]:
    """
    Async generator that reads step events from the run queue and yields SSE.

    Yields:
      run_started       — immediately on connect
      step_completed    — after each DAG step (including parallel steps)
      pipeline_completed / pipeline_failed — when the run finishes
    """
    run = _runs.get(run_id)
    if run is None:
        yield _sse("error", {"message": f"Run '{run_id}' not found"})
        return

    queue = _run_queues.get(run_id)
    if queue is None:
        yield _sse("error", {"message": f"No event queue for run '{run_id}'"})
        return

    yield _sse("run_started", {"run_id": run_id, "query": run.get("query", "")})

    try:
        while True:
            # Check if the client has disconnected
            if await request.is_disconnected():
                logger.info("SSE client disconnected for run %s", run_id)
                break

            try:
                # Wait up to 1 s so we can re-check client disconnect
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Send a keep-alive comment to prevent proxy timeouts
                yield ": keep-alive\n\n"
                continue

            if item is None:
                # Sentinel — run is done; emit final event and stop
                final_run = _runs.get(run_id, {})
                if final_run.get("status") == "completed":
                    yield _sse("pipeline_completed", {
                        "run_id": run_id,
                        "stats": final_run.get("stats"),
                    })
                else:
                    yield _sse("pipeline_failed", {
                        "run_id": run_id,
                        "error": final_run.get("error", "Unknown error"),
                    })
                break

            yield _sse("step_completed", item)

    finally:
        # Clean up the queue when the generator exits (disconnect or completion)
        _run_queues.pop(run_id, None)


# ── Execution helpers ─────────────────────────────────────────────────────────

async def _execute_run(run_id: str, request: ResearchRequest) -> None:
    """Execute the deep_research chain, emit step events, store results."""
    _runs[run_id]["status"] = "running"
    queue = _run_queues.get(run_id)

    try:
        initial_data = {
            "query": request.query,
            "system_instructions": request.system_instructions,
            "llm_client": _llm,
            "mcp_service": _mcp,
        }
        result = await _ao.launch(
            CHAIN_NAME,
            initial_data,
            request_id=run_id,
            debug_callback=_make_debug_callback(run_id),
        )

        _runs[run_id].update({
            "status": "completed",
            "report": result.get("report"),
            "stats": result.get("stats"),
        })
        logger.info("Run %s completed successfully", run_id)

    except Exception as exc:
        logger.exception("Run %s failed: %s", run_id, exc)
        _runs[run_id].update({"status": "failed", "error": str(exc)})

    finally:
        # Put the sentinel so the SSE generator knows the run is done.
        # For polling-only runs (no queue registered), this is a no-op.
        if queue is not None:
            queue.put_nowait(None)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/run/deep_research", response_model=RunResponse, status_code=202)
async def submit_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Submit a research query. Returns immediately with a run_id to poll.

    Use GET /runs/{run_id} to poll status, GET /runs/{run_id}/output for the report.
    For real-time progress use POST /run/deep_research/stream instead.
    """
    run_id = str(uuid.uuid4())
    _runs[run_id] = {
        "status": "pending",
        "query": request.query,
        "steps_completed": [],
        "report": None,
        "stats": None,
        "error": None,
    }
    # No queue — polling clients don't need one
    background_tasks.add_task(_execute_run, run_id, request)
    logger.info("Run %s submitted (poll) — query: %s", run_id, request.query[:80])
    return RunResponse(
        run_id=run_id,
        status="pending",
        message=f"Research run submitted. Poll GET /runs/{run_id} for status.",
    )


@app.post("/run/deep_research/stream")
async def submit_research_stream(request_body: ResearchRequest, http_request: Request):
    """Submit a research query and stream real-time SSE progress.

    The response is a text/event-stream with the following event types:

      run_started       — emitted immediately after the pipeline starts
      step_completed    — emitted after each DAG step (incl. parallel steps)
      pipeline_completed — final event on success, includes stats
      pipeline_failed   — final event on failure, includes error message

    Example (curl):
      curl -N -X POST http://localhost:8000/run/deep_research/stream \\
           -H "Content-Type: application/json" \\
           -d '{"query": "M&A deals > $1B past 2 weeks"}'
    """
    if _ao is None or _llm is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    run_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()

    _runs[run_id] = {
        "status": "pending",
        "query": request_body.query,
        "steps_completed": [],
        "report": None,
        "stats": None,
        "error": None,
    }
    _run_queues[run_id] = queue

    # Start the pipeline as a background task so the SSE response can begin
    # streaming immediately
    asyncio.create_task(_execute_run(run_id, request_body))

    logger.info("Run %s submitted (stream) — query: %s", run_id, request_body.query[:80])

    return StreamingResponse(
        _sse_generator(run_id, http_request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering
            "X-Run-Id": run_id,
        },
    )


@app.get("/runs/{run_id}", response_model=RunStatusResponse)
async def get_run_status(run_id: str):
    """Poll the status of a submitted research run."""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return RunStatusResponse(
        run_id=run_id,
        status=run["status"],
        steps_completed=run.get("steps_completed") or [],
        error=run.get("error"),
    )


@app.get("/runs/{run_id}/output", response_model=RunOutputResponse)
async def get_run_output(run_id: str):
    """Fetch the final report once the run is complete."""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if run["status"] not in ("completed", "failed"):
        raise HTTPException(
            status_code=202,
            detail=f"Run is still {run['status']}. Try again shortly.",
        )
    return RunOutputResponse(
        run_id=run_id,
        status=run["status"],
        report=run.get("report"),
        stats=run.get("stats"),
    )


@app.get("/chains")
async def list_chains():
    """List all registered chains."""
    if not _ao:
        raise HTTPException(status_code=503, detail="Orchestrator not initialised")
    return {"chains": list(_ao._chains.keys()) if hasattr(_ao, "_chains") else [CHAIN_NAME]}


@app.get("/health")
async def health():
    """Full health check — includes MCP adapter status."""
    mcp_health = await _mcp.health_check() if _mcp else {}
    llm_ok = _llm is not None
    return JSONResponse({
        "status": "ok" if llm_ok else "degraded",
        "llm": {"ok": llm_ok, "url": settings.llm_server_url},
        "mcp": mcp_health,
    })


@app.get("/ready")
async def readiness():
    """Kubernetes readiness probe — fails until orchestrator is initialised."""
    if _ao is None or _llm is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"status": "ready"}


@app.get("/live")
async def liveness():
    """Kubernetes liveness probe — always returns 200 if the process is alive."""
    return {"status": "alive"}


# ── Local dev entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "deep_research.server:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        log_level=settings.log_level.lower(),
        reload=False,
    )
