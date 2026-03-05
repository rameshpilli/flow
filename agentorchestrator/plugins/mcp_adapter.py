"""
MCP Adapter Agent - Refactored Version

Simplified MCP adapter using MCPToolAdapter infrastructure instead of MCP SDK ClientSession.
Removes anyio task group dependencies that cause async context errors in FastAPI.

Usage:
    from agentorchestrator.plugins import MCPAdapterAgent, MCPAdapterConfig

    config = MCPAdapterConfig(
        name="my_mcp",
        server_url="http://localhost:3000",
        secret="api_secret",  # Or pass via headers
    )
    agent = MCPAdapterAgent(config)
    await agent.initialize()

    tools = await agent.list_tools()
    result = await agent.call_tool("search", {"query": "test"})
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter

logger = logging.getLogger(__name__)


@dataclass
class MCPAdapterConfig:
    """Configuration for MCP adapter agent."""

    name: str
    server_url: str
    secret: Optional[str] = None  # Direct secret (preferred)
    headers: dict[str, str] = field(default_factory=dict)  # Or Authorization in headers
    transport: Literal["http", "sse"] = "http"
    timeout_seconds: float = 30.0
    verify_ssl: bool = True
    cache_enabled: bool = True


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


class MCPAdapterAgent(BaseAgent):
    """MCP adapter agent using MCPToolAdapter infrastructure."""

    _ao_name = "mcp_adapter"
    _ao_version = "2.0.0"  # Bumped version for refactored implementation

    def __init__(self, config: MCPAdapterConfig | dict[str, Any] | None = None):
        super().__init__()

        if isinstance(config, dict):
            self._config = MCPAdapterConfig(**config)
        elif config:
            self._config = config
        else:
            self._config = MCPAdapterConfig(name="mcp", server_url="")

        self._ao_name = self._config.name
        self._mcp_adapter: Optional[MCPToolAdapter] = None
        self._tools: list[MCPTool] = []

    async def initialize(self) -> None:
        """Initialize MCP connection using MCPToolAdapter."""
        if not self._config.server_url:
            raise ValueError("server_url is required")

        # Extract secret from config or headers
        secret = self._config.secret
        if not secret and "Authorization" in self._config.headers:
            auth_header = self._config.headers["Authorization"]
            if auth_header.startswith("Bearer "):
                secret = auth_header[7:]

        # Create and connect adapter
        self._mcp_adapter = MCPToolAdapter(name=self._config.name)

        # Determine routing style (path-based for most, JSON-RPC for SSE/CapIQ)
        use_path_routing = self._config.transport == "http"

        await self._mcp_adapter.connect(
            endpoint=self._config.server_url,
            secret=secret,
            use_path_routing=use_path_routing,
            verify_ssl=self._config.verify_ssl
        )

        # Discover tools
        if self._mcp_adapter.tools_list:
            self._tools = [
                MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in self._mcp_adapter.tools_list
            ]
            logger.info(f"Discovered {len(self._tools)} tools: {[t.name for t in self._tools]}")

        await super().initialize()
        logger.info(f"MCPAdapterAgent initialized: {self._config.name}")

    async def cleanup(self) -> None:
        """Cleanup MCP connection."""
        if self._mcp_adapter:
            try:
                await self._mcp_adapter.disconnect()
                logger.info(f"Disconnected MCP adapter: {self._config.name}")
            except Exception as e:
                logger.debug(f"Error disconnecting MCP adapter: {e}")
            finally:
                self._mcp_adapter = None

        await super().cleanup()

    async def list_tools(self) -> list[MCPTool]:
        """List available MCP tools."""
        return self._tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        """
        Call an MCP tool via the adapter.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            skip_cache: If True, bypass cache

        Returns:
            Tool result
        """
        if not self._mcp_adapter:
            raise RuntimeError("MCP adapter not initialized")

        # Get tool functions from adapter
        tool_functions = await self._mcp_adapter.get_tool_functions()

        # Find matching tool
        tool_func = next((t for t in tool_functions if t.name == tool_name), None)
        if not tool_func:
            raise ValueError(f"Tool not found: {tool_name}")

        # Call tool via adapter's FunctionTool (which handles caching/tracking)
        try:
            # Create a minimal context (FunctionTool expects ToolContext)
            from agents.tool import ToolContext
            ctx = ToolContext()

            result = await tool_func.invoke(ctx, arguments or {})
            return {"content": [{"text": str(result)}]}
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise

    async def fetch(
        self,
        query: str,
        tool_args: dict[str, Any] | None = None,
        **kwargs,
    ) -> AgentResult:
        """
        Fetch data via MCP (implements BaseAgent.fetch).

        Args:
            query: Tool name to call
            tool_args: Arguments for the tool

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

    def get_tool(self, name: str) -> MCPTool | None:
        """Get tool by name."""
        return next((t for t in self._tools if t.name == name), None)

    def has_tool(self, name: str) -> bool:
        """Check if tool exists."""
        return any(t.name == name for t in self._tools)


def create_mcp_agent(
    name: str,
    server_url: str,
    secret: Optional[str] = None,
    **kwargs,
) -> MCPAdapterAgent:
    """
    Factory function to create MCP adapter agent.

    Args:
        name: Agent name
        server_url: Server URL
        secret: API secret/token
        **kwargs: Additional config options

    Returns:
        Configured MCPAdapterAgent
    """
    config = MCPAdapterConfig(
        name=name,
        server_url=server_url,
        secret=secret,
        **kwargs,
    )

    return MCPAdapterAgent(config)