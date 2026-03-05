"""
Tests for MCP Connector
========================

Tests MCP (Model Context Protocol) connector integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from agentorchestrator.connectors.mcp import MCPConnector, MCPAgent
    from agentorchestrator.connectors.base import ConnectorConfig
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


pytestmark = pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP connector not available")


class TestMCPConnector:
    """Tests for MCP Connector."""

    def test_init_with_config(self):
        """Test connector initialization with config."""
        config = ConnectorConfig(
            name="test_mcp",
            host="localhost",
            port=8080,
        )
        
        connector = MCPConnector(config=config)
        
        assert connector.config.name == "test_mcp"
        assert connector.config.host == "localhost"

    @pytest.mark.asyncio
    async def test_connect_sets_connected_state(self):
        """Test connect method sets connected state."""
        connector = MCPConnector(config=ConnectorConfig(name="test"))
        
        with patch.object(connector, "_establish_connection", new_callable=AsyncMock):
            await connector.connect()
            assert connector.is_connected

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self):
        """Test disconnect clears connected state."""
        connector = MCPConnector(config=ConnectorConfig(name="test"))
        connector._connected = True
        
        with patch.object(connector, "_close_connection", new_callable=AsyncMock):
            await connector.disconnect()
            assert not connector.is_connected

    @pytest.mark.asyncio
    async def test_list_tools_returns_tools(self):
        """Test listing available tools."""
        connector = MCPConnector(config=ConnectorConfig(name="test"))
        
        mock_tools = [
            {"name": "search", "description": "Search tool"},
            {"name": "calculate", "description": "Calculator tool"},
        ]
        
        with patch.object(connector, "_fetch_tools", new_callable=AsyncMock, return_value=mock_tools):
            tools = await connector.list_tools()
            
            assert len(tools) == 2
            assert tools[0]["name"] == "search"

    @pytest.mark.asyncio
    async def test_call_tool_executes_correctly(self):
        """Test calling a tool through the connector."""
        connector = MCPConnector(config=ConnectorConfig(name="test"))
        connector._connected = True
        
        expected_result = {"result": "42"}
        
        with patch.object(connector, "_execute_tool", new_callable=AsyncMock, return_value=expected_result):
            result = await connector.call_tool("calculate", {"expression": "2+2"})
            
            assert result == expected_result


class TestMCPAgent:
    """Tests for MCP Agent wrapper."""

    def test_init_creates_connector(self):
        """Test agent initialization creates connector."""
        agent = MCPAgent(
            name="test_agent",
            connector_config=ConnectorConfig(name="test", host="localhost"),
        )
        
        assert agent.name == "test_agent"
        assert agent.connector is not None

    @pytest.mark.asyncio
    async def test_initialize_connects(self):
        """Test initialize method connects to MCP server."""
        agent = MCPAgent(
            name="test_agent",
            connector_config=ConnectorConfig(name="test"),
        )
        
        with patch.object(agent.connector, "connect", new_callable=AsyncMock):
            await agent.initialize()
            agent.connector.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_disconnects(self):
        """Test cleanup method disconnects from MCP server."""
        agent = MCPAgent(
            name="test_agent",
            connector_config=ConnectorConfig(name="test"),
        )
        agent.connector._connected = True
        
        with patch.object(agent.connector, "disconnect", new_callable=AsyncMock):
            await agent.cleanup()
            agent.connector.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_capabilities_returns_tools(self):
        """Test getting agent capabilities returns MCP tools."""
        agent = MCPAgent(
            name="test_agent",
            connector_config=ConnectorConfig(name="test"),
        )
        
        mock_tools = [{"name": "tool1"}, {"name": "tool2"}]
        
        with patch.object(agent.connector, "list_tools", new_callable=AsyncMock, return_value=mock_tools):
            capabilities = await agent.get_capabilities()
            
            assert len(capabilities) == 2

    @pytest.mark.asyncio
    async def test_execute_tool_through_agent(self):
        """Test executing a tool through the agent."""
        agent = MCPAgent(
            name="test_agent",
            connector_config=ConnectorConfig(name="test"),
        )
        agent.connector._connected = True
        
        expected_result = {"output": "success"}
        
        with patch.object(agent.connector, "call_tool", new_callable=AsyncMock, return_value=expected_result):
            result = await agent.execute("tool1", {"input": "data"})
            
            assert result == expected_result
