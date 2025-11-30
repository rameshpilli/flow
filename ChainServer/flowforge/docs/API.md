# FlowForge API Reference

## Core Classes

### FlowForge

The main entry point for creating pipelines.

```python
from flowforge import FlowForge

forge = FlowForge(
    name="my_app",           # Required: Unique name for this instance
    isolated=True,           # Default: Use isolated registries
)
```

#### Decorators

| Decorator | Description |
|-----------|-------------|
| `@forge.step(name, deps, produces)` | Register a processing step |
| `@forge.chain(name, steps)` | Register a chain of steps |
| `@forge.agent(name, capabilities)` | Register a data agent |
| `@forge.middleware(name, priority)` | Register middleware |

#### Methods

| Method | Description |
|--------|-------------|
| `launch(chain_name, data)` | Execute a chain asynchronously |
| `run(chain_name, data)` | Alias for `launch()` |
| `check()` | Validate all registered definitions |
| `list_defs()` | List all registered components |
| `graph(chain_name)` | Get ASCII visualization of chain DAG |
| `use(middleware)` | Add middleware to the pipeline |
| `get_agent(name)` | Get an agent instance by name |
| `register_resource(name, factory, cleanup)` | Register a resource for dependency injection |
| `get_resource(name)` | Get a registered resource |

#### Context Manager

```python
async with forge:
    result = await forge.launch("my_chain", data)
# Resources cleaned up automatically
```

---

### ChainContext

Shared state across steps in a chain execution.

```python
from flowforge import ChainContext

# Access in steps
@forge.step(name="my_step")
async def my_step(ctx: ChainContext):
    # Read values
    value = ctx.get("key", default=None)

    # Write values
    ctx.set("output", {"result": 123})

    # Check existence
    if ctx.has("key"):
        ...

    return {"success": True}
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `get(key, default=None)` | Retrieve a value |
| `set` | `set(key, value, scope=ContextScope.CHAIN)` | Store a value |
| `has` | `has(key)` | Check if key exists |
| `delete` | `delete(key)` | Remove a key |
| `to_dict` | `to_dict()` | Export as dictionary |

#### Scopes

```python
from flowforge.core.context import ContextScope

# Step scope - cleared after step completes
ctx.set("temp", value, scope=ContextScope.STEP)

# Chain scope - persists throughout chain (default)
ctx.set("data", value, scope=ContextScope.CHAIN)

# Global scope - persists across chains
ctx.set("config", value, scope=ContextScope.GLOBAL)
```

---

## Decorators

### @forge.step

Register a processing step.

```python
@forge.step(
    name="process_data",              # Required: Unique step name
    deps=["fetch_data"],              # Optional: Dependencies (run after these)
    produces=["processed_data"],      # Optional: Keys this step produces
    retry=3,                          # Optional: Retry count on failure
    timeout_ms=30000,                 # Optional: Timeout in milliseconds
    max_concurrency=5,                # Optional: Max parallel instances
)
async def process_data(ctx: ChainContext):
    # Step logic
    return {"result": "done"}
```

### @forge.chain

Register a chain of steps.

```python
@forge.chain(
    name="my_pipeline",               # Required: Unique chain name
    error_handling="fail_fast",       # Optional: "fail_fast" or "continue"
)
class MyPipeline:
    steps = ["step_a", "step_b", "step_c"]

    # Optional: Define parallel execution groups
    parallel_groups = [
        ["step_a"],                   # Group 1: runs first
        ["step_b", "step_c"],         # Group 2: runs in parallel
    ]
```

### @forge.agent

Register a data fetching agent.

```python
from flowforge.agents import BaseAgent, AgentResult

@forge.agent(
    name="news_agent",
    capabilities=["search", "sentiment"],
)
class NewsAgent(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        # Fetch logic
        return AgentResult(
            data={"articles": [...]},
            source="news_api",
            query=query,
        )
```

---

## Middleware

### Built-in Middleware

```python
from flowforge import (
    LoggerMiddleware,
    CacheMiddleware,
    SummarizerMiddleware,
    TokenManagerMiddleware,
)
from flowforge.middleware import (
    RateLimiterMiddleware,
    MetricsMiddleware,
    OffloadMiddleware,
)

# Logging
forge.use(LoggerMiddleware(level="INFO"))

# Caching
forge.use(CacheMiddleware(ttl_seconds=300))

# Summarization (requires LLM)
from flowforge import create_openai_summarizer
summarizer = create_openai_summarizer(api_key="sk-...")
forge.use(SummarizerMiddleware(summarizer=summarizer, max_tokens=4000))

# Token management
forge.use(TokenManagerMiddleware(max_total_tokens=100000))

# Rate limiting
forge.use(RateLimiterMiddleware({
    "fetch_data": {"requests_per_second": 10},
}))

# Large payload offloading
from flowforge.core.context_store import RedisContextStore
store = RedisContextStore(host="localhost", port=6380)
forge.use(OffloadMiddleware(store=store, threshold_bytes=100000))
```

### Custom Middleware

```python
from flowforge import Middleware
from flowforge.core.context import StepResult

class MyMiddleware(Middleware):
    def __init__(self, priority: int = 100):
        super().__init__(priority=priority)

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """Called before step execution."""
        print(f"Starting: {step_name}")

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Called after step execution."""
        print(f"Completed: {step_name} in {result.duration_ms}ms")

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """Called when step fails."""
        print(f"Failed: {step_name} - {error}")

forge.use(MyMiddleware(priority=50))
```

---

## Agents

### BaseAgent

Base class for all agents.

```python
from flowforge.agents import BaseAgent, AgentResult

class MyAgent(BaseAgent):
    async def initialize(self) -> None:
        """Called once before first use."""
        pass

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch data for a query."""
        return AgentResult(data={...}, source="my_agent", query=query)

    async def cleanup(self) -> None:
        """Called on shutdown."""
        pass

    async def health_check(self) -> bool:
        """Return True if healthy."""
        return True
```

### ResilientAgent

Wrapper that adds timeout, retry, and circuit breaker.

```python
from flowforge.agents import ResilientAgent, ResilientAgentConfig

config = ResilientAgentConfig(
    timeout_seconds=10.0,
    max_retries=3,
    retry_delay_ms=1000,
    circuit_failure_threshold=5,
    circuit_recovery_seconds=30.0,
)

resilient = ResilientAgent(agent=MyAgent(), config=config)
```

### AgentResult

Standardized result from agent operations.

```python
from flowforge.agents import AgentResult

result = AgentResult(
    data={"items": [...]},           # Required: The fetched data
    source="api_name",               # Required: Source identifier
    query="search term",             # Required: Original query
    duration_ms=150.5,               # Optional: Fetch duration
    metadata={"page": 1},            # Optional: Additional metadata
    error=None,                      # Optional: Error message if failed
)
```

---

## Context Store

### RedisContextStore

Offload large payloads to Redis.

```python
from flowforge.core.context_store import RedisContextStore, ContextRef

# Initialize
store = RedisContextStore(
    host="localhost",
    port=6380,
    maxmemory="512mb",               # Configure Redis memory limit
    maxmemory_policy="allkeys-lru",  # Eviction policy
)

# Store data
ref = await store.store(
    key="sec_filing",
    data=large_data,                 # Can be any serializable data
    ttl_seconds=3600,
    summary="10-K for AAPL FY2024",
    key_fields={"ticker": "AAPL", "revenue": "394B"},
)

# The ref is lightweight (~500 bytes)
ctx.set("sec_data", ref)

# Retrieve full data later
full_data = await store.retrieve(ref)

# Get storage stats
stats = await store.get_stats()
print(stats["memory"]["used_memory_human"])
```

---

## Testing Utilities

```python
from flowforge.testing import (
    IsolatedForge,
    MockAgent,
    MockMiddleware,
    mock_step,
    mock_chain,
    create_test_context,
    assert_step_completed,
    assert_chain_valid,
)

# Isolated testing
async def test_my_chain():
    async with IsolatedForge() as forge:
        @forge.step(name="test_step")
        async def test_step(ctx):
            return {"done": True}

        @forge.chain(name="test_chain")
        class TestChain:
            steps = ["test_step"]

        result = await forge.launch("test_chain", {})
        assert result["success"]

# Mock agent
mock = MockAgent(
    name="news_agent",
    responses={"Apple": {"articles": [...]}},
    default_response={"articles": []},
)

# Mock step decorator
@mock_step("fetch_data", returns={"data": "mocked"})
async def test_with_mock():
    result = await forge.launch("my_chain", {})
    assert_step_completed(result, "fetch_data")
```

---

## Utilities

### Circuit Breaker

```python
from flowforge import CircuitBreaker, CircuitBreakerConfig

config = CircuitBreakerConfig(
    failure_threshold=5,
    recovery_timeout=30.0,
    half_open_max_calls=3,
)

breaker = CircuitBreaker("external_api", config)

@breaker
async def call_api():
    return await httpx.get("https://api.example.com")
```

### Retry

```python
from flowforge import async_retry, RetryPolicy

@async_retry(max_attempts=3, backoff=2.0)
async def flaky_operation():
    ...
```

### Logging

```python
from flowforge import configure_logging, get_logger

configure_logging(level="INFO", json_output=False)
logger = get_logger("my_module")
logger.info("Processing", company="Apple", step="extract")
```

### Tracing

```python
from flowforge import configure_tracing, trace_span

configure_tracing(service_name="my-service", endpoint="http://jaeger:4317")

with trace_span("my_operation", {"key": "value"}):
    result = do_something()
```

---

## CLI

```bash
# Run chain
flowforge run my_chain --data '{"key": "value"}'

# Validate
flowforge check

# List components
flowforge list

# Visualize
flowforge graph my_chain
flowforge graph my_chain --format mermaid

# Health check
flowforge health
flowforge health --detailed

# Diagnose issues
flowforge doctor

# Development
flowforge dev --watch

# Scaffolding
flowforge new agent MyAgent
flowforge new chain MyChain
flowforge new project my-app
```
