"""
AgentOrchestrator MCP Connector

Provides integration with MCP (Model Context Protocol) servers.
Allows users to register their own MCP servers as AgentOrchestrator agents.
"""

import logging
from collections.abc import Callable
from typing import Any

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.connectors.base import BaseConnector, ConnectorConfig
from agentorchestrator.core.decorators import agent

logger = logging.getLogger(__name__)


class MCPConnector(BaseConnector):
    """
    Connector for MCP (Model Context Protocol) servers.

    Allows AgentOrchestrator to communicate with external MCP servers,
    enabling users to register their own data sources.

    Usage:
        connector = MCPConnector(MCPConfig(
            name="my_mcp_server",
            base_url="http://localhost:8000",
        ))

        # Or register as an agent
        @forge.agent(name="my_mcp_agent")
        class MyMCPAgent(MCPAgent):
            connector_config = MCPConfig(...)
    """

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._tools: dict[str, dict] = {}

    async def connect(self) -> None:
        """Connect to MCP server and discover tools"""
        # In a real implementation, this would establish a connection
        # to the MCP server and discover available tools
        logger.info(f"Connecting to MCP server: {self.config.name}")
        self._session = True  # Placeholder

        # Discover tools
        await self._discover_tools()

    async def disconnect(self) -> None:
        """Disconnect from MCP server"""
        self._session = None
        self._tools.clear()
        logger.info(f"Disconnected from MCP server: {self.config.name}")

    async def _discover_tools(self) -> None:
        """Discover available tools from MCP server"""
        # This would call the MCP server's tool discovery endpoint
        # For now, this is a placeholder
        self._tools = {}
        logger.info(f"Discovered {len(self._tools)} tools from {self.config.name}")

    async def request(
        self,
        endpoint: str,
        method: str = "POST",
        **kwargs,
    ) -> dict[str, Any]:
        """Make a request to the MCP server"""
        if not self._session:
            raise RuntimeError("Not connected to MCP server")

        # Placeholder for actual MCP protocol implementation
        return {"_mock": True, "endpoint": endpoint}

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a tool on the MCP server"""
        if tool_name not in self._tools:
            raise ValueError(f"Tool not found: {tool_name}")

        return await self.request(
            f"/tools/{tool_name}",
            method="POST",
            data={"arguments": arguments},
        )

    def list_tools(self) -> list[str]:
        """List available tools"""
        return list(self._tools.keys())


class MCPAgent(BaseAgent):
    """
    Base class for MCP-based agents.

    Allows users to easily create agents that wrap MCP servers.

    Usage:
        @forge.agent(name="my_data_source")
        class MyDataAgent(MCPAgent):
            connector_config = ConnectorConfig(
                name="my_mcp",
                base_url="http://localhost:8000",
            )

            async def fetch(self, query: str, **kwargs) -> AgentResult:
                result = await self.connector.call_tool("search", {"query": query})
                return AgentResult(data=result, source="my_mcp", query=query)
    """

    connector_config: ConnectorConfig | None = None

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.connector: MCPConnector | None = None

    async def initialize(self) -> None:
        if self.connector_config:
            self.connector = MCPConnector(self.connector_config)
            await self.connector.connect()
        await super().initialize()

    async def cleanup(self) -> None:
        if self.connector:
            await self.connector.disconnect()
        await super().cleanup()

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Override this to implement your fetch logic"""
        raise NotImplementedError("Subclasses must implement fetch()")

    async def health_check(self) -> bool:
        if self.connector:
            return await self.connector.health_check()
        return False


def create_mcp_agent(
    name: str,
    base_url: str,
    tool_name: str,
    api_key: str | None = None,
    transform_fn: Callable[[dict], Any] | None = None,
) -> type:
    """
    Factory function to create an MCP agent class.

    Usage:
        MyAgent = create_mcp_agent(
            name="my_agent",
            base_url="http://localhost:8000",
            tool_name="search",
        )

        agent = MyAgent()
        result = await agent.fetch("query")
    """
    config = ConnectorConfig(
        name=name,
        base_url=base_url,
        api_key=api_key,
    )

    @agent(name=name)
    class DynamicMCPAgent(MCPAgent):
        connector_config = config

        async def fetch(self, query: str, **kwargs) -> AgentResult:
            import time

            start = time.perf_counter()

            try:
                result = await self.connector.call_tool(tool_name, {"query": query, **kwargs})

                if transform_fn:
                    result = transform_fn(result)

                duration = (time.perf_counter() - start) * 1000
                return AgentResult(
                    data=result,
                    source=name,
                    query=query,
                    duration_ms=duration,
                )

            except Exception as e:
                duration = (time.perf_counter() - start) * 1000
                return AgentResult(
                    data=None,
                    source=name,
                    query=query,
                    duration_ms=duration,
                    error=str(e),
                )

    DynamicMCPAgent.__name__ = f"{name.title().replace('_', '')}Agent"
    return DynamicMCPAgent
