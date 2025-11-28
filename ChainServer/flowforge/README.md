# FlowForge

**A DAG-based Chain Orchestration Framework**

FlowForge is a lightweight, decorator-driven framework for building data processing pipelines with automatic dependency resolution, context management, and middleware support.

## Features

- **Decorator-Based Registration**: Simple `@forge.agent()`, `@forge.step()`, `@forge.chain()` decorators
- **DAG Execution**: Automatic dependency resolution with parallel execution
- **Context Management**: Shared state across steps with scoped storage
- **Middleware Support**: Logging, caching, summarization, token management
- **Agent System**: Pre-built and custom data agents
- **MCP Integration**: Connect external MCP servers as agents
- **Extensible**: Register your own agents, steps, and chains

## Installation

```bash
# From source
pip install -e ./flowforge

# Or add to requirements.txt
flowforge @ file:./flowforge
```

## Quickstart

```python
from flowforge import FlowForge, ChainContext

# Initialize
forge = FlowForge(name="my_app")

# Define a step
@forge.step(name="fetch_data", produces=["data"])
async def fetch_data(ctx: ChainContext):
    ctx.set("data", {"key": "value"})
    return {"data": ctx.get("data")}

# Define a dependent step
@forge.step(name="process", dependencies=["fetch_data"])
async def process(ctx: ChainContext):
    data = ctx.get("data")
    return {"processed": data}

# Define a chain
@forge.chain(name="my_pipeline")
class MyPipeline:
    steps = ["fetch_data", "process"]

# Run
import asyncio

async def main():
    result = await forge.run("my_pipeline")
    print(result)

asyncio.run(main())
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         FlowForge                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Agents    │  │    Steps    │  │       Chains        │ │
│  │             │  │             │  │                     │ │
│  │ @agent()    │  │ @step()     │  │ @chain()            │ │
│  │             │  │             │  │                     │ │
│  │ Data        │  │ Processing  │  │ Orchestration       │ │
│  │ Fetching    │  │ Logic       │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Middleware                        │   │
│  │  Logger | Cache | Summarizer | TokenManager          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 DAG Executor                         │   │
│  │  Dependency Resolution | Parallel Execution          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               Context Manager                        │   │
│  │  Shared State | Scoped Storage | Token Tracking      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Core Concepts

### 1. Agents

Agents are responsible for fetching data from external sources.

```python
@forge.agent(name="news_agent", capabilities=["search", "sentiment"])
class NewsAgent(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        # Fetch news data
        return AgentResult(data={...}, source="news", query=query)
```

### 2. Steps

Steps are the processing units in a chain. They can depend on other steps.

```python
@forge.step(
    name="process_data",
    dependencies=["fetch_data"],  # Run after fetch_data
    produces=["processed"],        # Declares what this step produces
)
async def process_data(ctx: ChainContext):
    raw = ctx.get("raw_data")
    processed = transform(raw)
    ctx.set("processed", processed)
    return {"processed": processed}
```

### 3. Chains

Chains define the sequence of steps to execute.

```python
@forge.chain(name="my_pipeline")
class MyPipeline:
    steps = ["step_1", "step_2", "step_3"]
```

### 4. Context

The `ChainContext` provides shared state across steps.

```python
# Store data
ctx.set("key", value, scope=ContextScope.CHAIN)

# Retrieve data
value = ctx.get("key", default=None)

# Check existence
if ctx.has("key"):
    ...
```

### 5. Middleware

Middleware intercepts step execution for cross-cutting concerns.

```python
# Built-in middleware
forge.use_middleware(LoggerMiddleware(level=logging.INFO))
forge.use_middleware(CacheMiddleware(ttl_seconds=300))
forge.use_middleware(SummarizerMiddleware(max_tokens=4000))
forge.use_middleware(TokenManagerMiddleware(max_total_tokens=100000))

# Custom middleware
@forge.middleware(name="my_middleware", priority=50)
class MyMiddleware(Middleware):
    async def before(self, ctx, step_name):
        print(f"Before {step_name}")

    async def after(self, ctx, step_name, result):
        print(f"After {step_name}")
```

## Advanced Usage

### Parallel Step Execution

Steps with no dependencies run in parallel:

```python
@forge.step(name="fetch_news")
async def fetch_news(ctx): ...

@forge.step(name="fetch_filings")
async def fetch_filings(ctx): ...

@forge.step(name="fetch_earnings")
async def fetch_earnings(ctx): ...

@forge.step(name="combine", dependencies=["fetch_news", "fetch_filings", "fetch_earnings"])
async def combine(ctx): ...
```

In this example, `fetch_news`, `fetch_filings`, and `fetch_earnings` run in parallel.

### Custom MCP Server Integration

```python
from flowforge.connectors.mcp import MCPAgent, create_mcp_agent

# Method 1: Subclass MCPAgent
@forge.agent(name="my_mcp")
class MyMCPAgent(MCPAgent):
    connector_config = ConnectorConfig(
        name="my_server",
        base_url="http://localhost:8000",
    )

    async def fetch(self, query, **kwargs):
        result = await self.connector.call_tool("search", {"query": query})
        return AgentResult(data=result, ...)

# Method 2: Factory function
MyAgent = create_mcp_agent(
    name="my_agent",
    base_url="http://localhost:8000",
    tool_name="search",
)
```

### Token Management for LLMs

```python
forge.use_middleware(SummarizerMiddleware(
    max_tokens=4000,
    summarizer=my_llm_summarizer,  # Custom LLM-based summarizer
))

forge.use_middleware(TokenManagerMiddleware(
    max_total_tokens=100000,
    warning_threshold=0.8,
))
```

## API Reference

### FlowForge

| Method | Description |
|--------|-------------|
| `forge.agent()` | Decorator to register an agent |
| `forge.step()` | Decorator to register a step |
| `forge.chain()` | Decorator to register a chain |
| `forge.run(chain_name, initial_data)` | Execute a chain |
| `forge.use_middleware(middleware)` | Add middleware |
| `forge.get_agent(name)` | Get agent instance |
| `forge.list_agents()` | List registered agents |
| `forge.list_steps()` | List registered steps |
| `forge.list_chains()` | List registered chains |
| `forge.visualize_chain(name)` | ASCII visualization of chain DAG |

### ChainContext

| Method | Description |
|--------|-------------|
| `ctx.set(key, value, scope)` | Store a value |
| `ctx.get(key, default)` | Retrieve a value |
| `ctx.has(key)` | Check if key exists |
| `ctx.delete(key)` | Remove a key |
| `ctx.to_dict()` | Export as dictionary |

## Examples

See the `examples/` directory:

- `quickstart.py` - Minimal getting started example
- `meeting_prep_chain.py` - Full Client Meeting Prep implementation
- `custom_agent_example.py` - Custom agent and MCP integration

## License

MIT
