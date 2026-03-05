# MCP Connectors (Model Context Protocol)

AgentOrchestrator provides first-class support for the **Model Context Protocol (MCP)**, allowing you to connect your agents to external tool servers, data sources, and services.

## Overview

MCP is an open protocol that enables AI applications to connect to external tools and data sources through a standardized interface. AgentOrchestrator supports:

- **HTTP Transport** - Connect to remote MCP servers via HTTP/HTTPS
- **stdio Transport** - Run local MCP servers as subprocesses
- **SSE Transport** - Server-sent events for streaming connections
- **Caching** - Built-in response caching with configurable TTL
- **Tool Discovery** - Automatic discovery of available tools and resources

---

## Quick Start

### HTTP Transport (Remote Servers)

```python
from agentorchestrator.plugins import MCPAdapterAgent, MCPAdapterConfig

# Configure the MCP adapter
config = MCPAdapterConfig(
    name="my_mcp_server",
    server_url="http://localhost:3000/mcp",
    transport="http",
    timeout_seconds=30.0,
    headers={"Authorization": "Bearer your-token"},
)

# Create and initialize the agent
agent = MCPAdapterAgent(config)
await agent.initialize()

# Discover available tools
tools = await agent.list_tools()
for tool in tools:
    print(f"Tool: {tool.name}")
    print(f"  Description: {tool.description}")
    print(f"  Schema: {tool.input_schema}")

# Call a tool
result = await agent.call_tool("search", {"query": "AI trends 2024"})
print(result)

# Cleanup when done
await agent.cleanup()
```

### stdio Transport (Local Servers)

```python
from agentorchestrator.plugins import MCPAdapterAgent, MCPAdapterConfig

# Run an MCP server as a subprocess
config = MCPAdapterConfig(
    name="local_server",
    transport="stdio",
    server_command="npx",
    server_args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"],
    timeout_seconds=30.0,
)

agent = MCPAdapterAgent(config)
await agent.initialize()

# Now you can call filesystem tools
result = await agent.call_tool("read_file", {"path": "/path/to/file.txt"})
```

### SSE Transport (Streaming)

```python
from agentorchestrator.plugins import MCPAdapterConfig

config = MCPAdapterConfig(
    name="streaming_server",
    server_url="http://localhost:3000/mcp",
    transport="sse",  # Server-sent events
)
```

---

## Configuration Reference

### MCPAdapterConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Server/agent name |
| `server_url` | `str` | `None` | Server URL (for HTTP/SSE) |
| `server_command` | `str` | `None` | Command to start server (for stdio) |
| `server_args` | `list[str]` | `[]` | Arguments for server command |
| `transport` | `str` | `"http"` | Transport type: `http`, `stdio`, `sse` |
| `timeout_seconds` | `float` | `30.0` | Request timeout |
| `max_retries` | `int` | `3` | Maximum retry attempts |
| `headers` | `dict` | `{}` | Additional HTTP headers |
| `env` | `dict` | `{}` | Environment variables for stdio |
| `verify_ssl` | `bool` | `True` | Verify SSL certificates |
| `cache_enabled` | `bool` | `True` | Enable response caching |
| `cache_ttl_seconds` | `int` | `3600` | Cache TTL (1 hour default) |
| `cache_max_entries` | `int` | `500` | Maximum cache entries |
| `cacheable_tools` | `list[str]` | `None` | Tools to cache (None = all) |

---

## API Reference

### MCPAdapterAgent

The main class for interacting with MCP servers.

```python
class MCPAdapterAgent:
    """MCP adapter agent for connecting to MCP servers."""

    async def initialize(self) -> None:
        """Initialize MCP connection and discover tools."""

    async def cleanup(self) -> None:
        """Cleanup MCP connection."""

    async def list_tools(self) -> list[MCPTool]:
        """List available MCP tools."""

    async def list_resources(self) -> list[MCPResource]:
        """List available MCP resources."""

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        """Call an MCP tool."""

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read an MCP resource."""

    async def fetch(
        self,
        query: str,
        tool_args: dict[str, Any] | None = None,
        **kwargs,
    ) -> AgentResult:
        """Fetch data via MCP (BaseAgent interface)."""

    async def health_check(self) -> bool:
        """Check if MCP connection is healthy."""

    def get_tool(self, name: str) -> MCPTool | None:
        """Get tool by name."""

    def has_tool(self, name: str) -> bool:
        """Check if tool exists."""
```

### MCPTool

```python
@dataclass
class MCPTool:
    """MCP tool definition."""
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
```

### MCPResource

```python
@dataclass
class MCPResource:
    """MCP resource definition."""
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = "text/plain"
```

---

## Caching

The MCP adapter includes built-in caching to reduce redundant calls to external servers.

### Cache Configuration

```python
config = MCPAdapterConfig(
    name="my_server",
    server_url="http://localhost:3000",
    cache_enabled=True,           # Enable caching
    cache_ttl_seconds=3600,       # 1 hour TTL
    cache_max_entries=500,        # Max entries
    cacheable_tools=["search"],   # Only cache specific tools (None = all)
)
```

### Cache Management

```python
agent = MCPAdapterAgent(config)

# Get cache statistics
stats = agent.get_cache_stats()
print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
print(f"Hit Rate: {stats['hit_rate']:.1%}")

# Invalidate cache for a specific tool
agent.invalidate_cache(tool_name="search")

# Invalidate all cache entries
agent.invalidate_cache()

# Skip cache for a specific call
result = await agent.call_tool("search", {"query": "test"}, skip_cache=True)
```

---

## Creating Custom MCP Agents

### Using the Base Class

```python
from agentorchestrator.connectors import MCPAgent, ConnectorConfig
from agentorchestrator.agents.base import AgentResult
from agentorchestrator import ao

@ao.agent(name="financial_data")
class FinancialDataAgent(MCPAgent):
    """Agent for fetching financial data via MCP."""

    connector_config = ConnectorConfig(
        name="financial_mcp",
        base_url="http://financial-data-server:3000",
        api_key="your-api-key",
    )

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch financial data."""
        import time
        start = time.perf_counter()

        try:
            # Parse query to determine tool and arguments
            if "stock price" in query.lower():
                symbol = kwargs.get("symbol", "AAPL")
                result = await self.connector.call_tool(
                    "get_stock_price",
                    {"symbol": symbol}
                )
            elif "earnings" in query.lower():
                symbol = kwargs.get("symbol", "AAPL")
                result = await self.connector.call_tool(
                    "get_earnings",
                    {"symbol": symbol}
                )
            else:
                result = await self.connector.call_tool(
                    "search",
                    {"query": query}
                )

            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=result,
                source="financial_mcp",
                query=query,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source="financial_mcp",
                query=query,
                duration_ms=duration,
                error=str(e),
            )
```

### Using the Factory Function

```python
from agentorchestrator.plugins import create_mcp_agent

# Create agent with factory function
MyAgent = create_mcp_agent(
    name="web_search",
    server_url="http://search-server:3000",
    transport="http",
    headers={"X-API-Key": "key"},
)

# Use the agent
agent = MyAgent()
await agent.initialize()
result = await agent.fetch("search", tool_args={"query": "AI news"})
```

---

## Integration with Multi-Agent Systems

### Using MCP Agents in a Squad

```python
from agentorchestrator.squad import Squad, SquadOptions, LLMGatewayAgent
from agentorchestrator.plugins import MCPAdapterAgent, MCPAdapterConfig

# Create MCP-based data agent
mcp_config = MCPAdapterConfig(
    name="data_source",
    server_url="http://data-server:3000",
)
data_agent = MCPAdapterAgent(mcp_config)
await data_agent.initialize()

# Create LLM agents for analysis
analyst = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Analyst",
    description="Analyzes data from the data source",
    llm_client=llm_client,
))

# Create supervisor
lead = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Lead",
    description="Coordinates data retrieval and analysis",
    llm_client=llm_client,
))

# Form squad with MCP data agent
squad = Squad(
    supervisor=lead,
    agents=[data_agent, analyst],
    options=SquadOptions(trace=True),
)

result = await squad.run("Get latest market data and analyze trends")
```

### Using MCP Tools in Chains

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.plugins import MCPAdapterAgent, MCPAdapterConfig

ao = AgentOrchestrator()

# Initialize MCP agent at startup
mcp_config = MCPAdapterConfig(
    name="tools",
    server_url="http://tools-server:3000",
)
mcp_agent = MCPAdapterAgent(mcp_config)

@ao.step(name="fetch_data")
async def fetch_data(ctx):
    """Fetch data using MCP tool."""
    query = ctx.get("query")
    result = await mcp_agent.call_tool("search", {"query": query})
    ctx.set("raw_data", result)
    return {"fetched": True}

@ao.step(name="process_data", deps=["fetch_data"])
async def process_data(ctx):
    """Process the fetched data."""
    data = ctx.get("raw_data")
    # Process data...
    return {"processed": data}

@ao.chain(name="data_pipeline")
class DataPipeline:
    steps = ["fetch_data", "process_data"]

# Run with lifecycle management
async def main():
    await mcp_agent.initialize()
    try:
        result = await ao.launch("data_pipeline", {"query": "AI trends"})
    finally:
        await mcp_agent.cleanup()
```

---

## Error Handling

### Retry Configuration

```python
config = MCPAdapterConfig(
    name="server",
    server_url="http://localhost:3000",
    max_retries=3,
    timeout_seconds=30.0,
)
```

### Handling Errors

```python
from agentorchestrator.plugins import MCPAdapterAgent

agent = MCPAdapterAgent(config)

try:
    result = await agent.call_tool("search", {"query": "test"})
except RuntimeError as e:
    if "not initialized" in str(e):
        await agent.initialize()
        result = await agent.call_tool("search", {"query": "test"})
except Exception as e:
    print(f"Tool call failed: {e}")
```

---

## SSL Configuration

### Disable SSL Verification (Development Only)

```python
config = MCPAdapterConfig(
    name="dev_server",
    server_url="https://localhost:3000",
    verify_ssl=False,  # Only for development!
)
```

### Custom Headers for Authentication

```python
config = MCPAdapterConfig(
    name="secure_server",
    server_url="https://api.example.com/mcp",
    headers={
        "Authorization": "Bearer your-token",
        "X-API-Key": "your-api-key",
    },
)
```

---

## Best Practices

### 1. Always Cleanup

```python
agent = MCPAdapterAgent(config)
try:
    await agent.initialize()
    # Use agent...
finally:
    await agent.cleanup()
```

### 2. Use Context Managers (Recommended)

```python
# If you're managing multiple agents, consider a lifecycle manager
class MCPLifecycle:
    def __init__(self, configs: list[MCPAdapterConfig]):
        self.agents = [MCPAdapterAgent(c) for c in configs]

    async def __aenter__(self):
        for agent in self.agents:
            await agent.initialize()
        return self

    async def __aexit__(self, *args):
        for agent in self.agents:
            await agent.cleanup()

async with MCPLifecycle([config1, config2]) as lifecycle:
    # Use lifecycle.agents
    pass
```

### 3. Use Caching for Read-Heavy Workloads

```python
config = MCPAdapterConfig(
    name="server",
    server_url="http://localhost:3000",
    cache_enabled=True,
    cache_ttl_seconds=300,  # 5 minutes
    cacheable_tools=["search", "get_data"],  # Only cache read operations
)
```

### 4. Monitor Cache Performance

```python
stats = agent.get_cache_stats()
if stats["hit_rate"] < 0.5:
    print("Consider increasing cache TTL or reviewing query patterns")
```

---

## Troubleshooting

### Connection Issues

```python
# Check health
is_healthy = await agent.health_check()
if not is_healthy:
    print("MCP server not responding")
    # Try reinitializing
    await agent.cleanup()
    await agent.initialize()
```

### Tool Not Found

```python
# Verify tool exists before calling
if agent.has_tool("my_tool"):
    result = await agent.call_tool("my_tool", {})
else:
    print(f"Available tools: {[t.name for t in await agent.list_tools()]}")
```

### Debugging

```python
import logging

# Enable debug logging for MCP
logging.getLogger("agentorchestrator.plugins.mcp_adapter").setLevel(logging.DEBUG)
```

---

## See Also

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [Deep Research Agent Example](../examples/deep_research_agent.py)
- [Financial Research Agent Example](../examples/financial_research_agent.py)
