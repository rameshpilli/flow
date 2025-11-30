"""
MCP Adapter Agent

A real MCP (Model Context Protocol) adapter for connecting to MCP servers.

Features:
- Tool discovery and invocation
- Resource listing and reading
- Prompt template support
- Connection management
- Retry and error handling

Usage:
    from agentorchestrator.plugins import MCPAdapterAgent, MCPAdapterConfig

    # Create adapter
    config = MCPAdapterConfig(
        name="my_mcp",
        server_url="http://localhost:3000",
        transport="http",  # or "stdio"
    )
    agent = MCPAdapterAgent(config)
    await agent.initialize()

    # List available tools
    tools = await agent.list_tools()

    # Call a tool
    result = await agent.call_tool("search", {"query": "test"})

    # Or use via fetch interface
    result = await agent.fetch("search", tool_args={"query": "test"})
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from agentorchestrator.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class MCPAdapterConfig:
    """
    Configuration for MCP adapter agent.

    Attributes:
        name: Server/agent name
        server_url: Server URL (for HTTP transport)
        server_command: Command to start server (for stdio transport)
        server_args: Arguments for server command
        transport: Transport type
        timeout_seconds: Request timeout
        max_retries: Maximum retries
        headers: Additional HTTP headers
        env: Environment variables for stdio transport
    """

    name: str
    server_url: str | None = None
    server_command: str | None = None
    server_args: list[str] = field(default_factory=list)
    transport: Literal["http", "stdio", "sse"] = "http"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    headers: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class MCPTool:
    """MCP tool definition."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPResource:
    """MCP resource definition."""

    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = "text/plain"

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


class MCPAdapterAgent(BaseAgent):
    """
    MCP adapter agent for connecting to MCP servers.

    Supports both HTTP and stdio transports.
    """

    _ao_name = "mcp_adapter"
    _ao_version = "1.0.0"

    # Capability schema
    CAPABILITIES = {
        "call_tool": {
            "description": "Call an MCP tool",
            "parameters": {
                "tool_name": {"type": "string", "required": True},
                "arguments": {"type": "object", "default": {}},
            },
        },
        "list_tools": {
            "description": "List available MCP tools",
            "parameters": {},
        },
        "read_resource": {
            "description": "Read an MCP resource",
            "parameters": {
                "uri": {"type": "string", "required": True},
            },
        },
        "list_resources": {
            "description": "List available MCP resources",
            "parameters": {},
        },
    }

    def __init__(self, config: MCPAdapterConfig | dict[str, Any] | None = None):
        super().__init__()

        if isinstance(config, dict):
            self._config = MCPAdapterConfig(**config)
        elif config:
            self._config = config
        else:
            self._config = MCPAdapterConfig(name="mcp")

        self._ao_name = self._config.name
        self._http_client = None
        self._stdio_process = None
        self._tools: list[MCPTool] = []
        self._resources: list[MCPResource] = []
        self._request_id = 0

    async def initialize(self) -> None:
        """Initialize MCP connection."""
        if self._config.transport == "http":
            await self._init_http()
        elif self._config.transport == "stdio":
            await self._init_stdio()
        elif self._config.transport == "sse":
            await self._init_sse()

        # Discover tools and resources
        await self._discover()

        await super().initialize()
        logger.info(f"MCPAdapterAgent initialized: {self._config.name}")

    async def _init_http(self) -> None:
        """Initialize HTTP transport."""
        import httpx

        if not self._config.server_url:
            raise ValueError("server_url required for HTTP transport")

        self._http_client = httpx.AsyncClient(
            base_url=self._config.server_url,
            timeout=httpx.Timeout(self._config.timeout_seconds),
            headers={
                "Content-Type": "application/json",
                **self._config.headers,
            },
        )

    async def _init_stdio(self) -> None:
        """Initialize stdio transport."""
        if not self._config.server_command:
            raise ValueError("server_command required for stdio transport")

        # Start MCP server process
        env = {**self._config.env}

        self._stdio_process = await asyncio.create_subprocess_exec(
            self._config.server_command,
            *self._config.server_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Send initialize request
        await self._stdio_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "AgentOrchestrator",
                "version": "1.0.0",
            },
        })

        # Send initialized notification
        await self._stdio_notify("notifications/initialized", {})

    async def _init_sse(self) -> None:
        """Initialize SSE transport."""
        # SSE transport uses HTTP for requests, SSE for notifications
        await self._init_http()

    async def _discover(self) -> None:
        """Discover available tools and resources."""
        try:
            # List tools
            tools_result = await self._request("tools/list", {})
            if tools_result and "tools" in tools_result:
                self._tools = [
                    MCPTool(
                        name=t["name"],
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                    )
                    for t in tools_result["tools"]
                ]

            # List resources
            resources_result = await self._request("resources/list", {})
            if resources_result and "resources" in resources_result:
                self._resources = [
                    MCPResource(
                        uri=r["uri"],
                        name=r.get("name", ""),
                        description=r.get("description", ""),
                        mime_type=r.get("mimeType", "text/plain"),
                    )
                    for r in resources_result["resources"]
                ]

        except Exception as e:
            logger.warning(f"Failed to discover MCP capabilities: {e}")

    async def cleanup(self) -> None:
        """Cleanup MCP connection."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        if self._stdio_process:
            self._stdio_process.terminate()
            await self._stdio_process.wait()
            self._stdio_process = None

        await super().cleanup()

    def _next_request_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Make MCP JSON-RPC request."""
        if self._config.transport == "http":
            return await self._http_request(method, params)
        elif self._config.transport == "stdio":
            return await self._stdio_request(method, params)
        else:
            raise ValueError(f"Unsupported transport: {self._config.transport}")

    async def _http_request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Make HTTP JSON-RPC request."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        request_id = self._next_request_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            response = await self._http_client.post("/", json=payload)
            response.raise_for_status()

            result = response.json()

            if "error" in result:
                error = result["error"]
                raise Exception(f"MCP error: {error.get('message', error)}")

            return result.get("result")

        except Exception as e:
            logger.error(f"MCP HTTP request failed: {e}")
            raise

    async def _stdio_request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Make stdio JSON-RPC request."""
        if not self._stdio_process or not self._stdio_process.stdin:
            raise RuntimeError("Stdio process not running")

        request_id = self._next_request_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Send request
        message = json.dumps(payload) + "\n"
        self._stdio_process.stdin.write(message.encode())
        await self._stdio_process.stdin.drain()

        # Read response
        if not self._stdio_process.stdout:
            raise RuntimeError("Stdout not available")

        response_line = await asyncio.wait_for(
            self._stdio_process.stdout.readline(),
            timeout=self._config.timeout_seconds,
        )

        if not response_line:
            raise Exception("No response from MCP server")

        result = json.loads(response_line.decode())

        if "error" in result:
            error = result["error"]
            raise Exception(f"MCP error: {error.get('message', error)}")

        return result.get("result")

    async def _stdio_notify(self, method: str, params: dict[str, Any]) -> None:
        """Send stdio notification (no response expected)."""
        if not self._stdio_process or not self._stdio_process.stdin:
            return

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        message = json.dumps(payload) + "\n"
        self._stdio_process.stdin.write(message.encode())
        await self._stdio_process.stdin.drain()

    # ═══════════════════════════════════════════════════════════════════════
    #                         PUBLIC API
    # ═══════════════════════════════════════════════════════════════════════

    async def list_tools(self) -> list[MCPTool]:
        """List available MCP tools."""
        return self._tools

    async def list_resources(self) -> list[MCPResource]:
        """List available MCP resources."""
        return self._resources

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Call an MCP tool.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            Tool result
        """
        result = await self._request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })

        return result or {}

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """
        Read an MCP resource.

        Args:
            uri: Resource URI

        Returns:
            Resource content
        """
        result = await self._request("resources/read", {"uri": uri})
        return result or {}

    async def fetch(
        self,
        query: str,
        tool_args: dict[str, Any] | None = None,
        **kwargs,
    ) -> AgentResult:
        """
        Fetch data via MCP (implements BaseAgent.fetch).

        The query is interpreted as a tool name.

        Args:
            query: Tool name to call
            tool_args: Arguments for the tool
            **kwargs: Additional arguments

        Returns:
            AgentResult with tool output
        """
        start = time.perf_counter()

        try:
            result = await self.call_tool(query, tool_args)
            duration = (time.perf_counter() - start) * 1000

            return AgentResult(
                data=result,
                source=self._ao_name,
                query=query,
                duration_ms=duration,
                metadata={
                    "tool_name": query,
                    "transport": self._config.transport,
                },
            )

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=query,
                duration_ms=duration,
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if MCP connection is healthy."""
        try:
            # Try to list tools as health check
            await self._request("tools/list", {})
            return True
        except Exception:
            return False

    def get_tool(self, name: str) -> MCPTool | None:
        """Get tool by name."""
        return next((t for t in self._tools if t.name == name), None)

    def has_tool(self, name: str) -> bool:
        """Check if tool exists."""
        return any(t.name == name for t in self._tools)


def create_mcp_agent(
    name: str,
    server_url: str | None = None,
    server_command: str | None = None,
    server_args: list[str] | None = None,
    transport: str = "http",
    **kwargs,
) -> MCPAdapterAgent:
    """
    Factory function to create MCP adapter agent.

    Args:
        name: Agent name
        server_url: Server URL (for HTTP)
        server_command: Server command (for stdio)
        server_args: Server arguments
        transport: Transport type
        **kwargs: Additional config options

    Returns:
        Configured MCPAdapterAgent
    """
    config = MCPAdapterConfig(
        name=name,
        server_url=server_url,
        server_command=server_command,
        server_args=server_args or [],
        transport=transport,
        **kwargs,
    )

    return MCPAdapterAgent(config)
