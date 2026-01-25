# AgentOrchestrator API Reference

## Services

### LLMGatewayClient

Client for LLM API calls with OAuth support (for corporate environments).

```python
from agentorchestrator.services import LLMGatewayClient, LLMGatewayConfig

# Option 1: Direct configuration
client = LLMGatewayClient(
    server_url="https://llm-gateway.corp.com/v1/chat/completions",
    oauth_endpoint="https://auth.corp.com/token",
    client_id="my-app",
    client_secret="secret",
    model_name="gpt-4",
    temperature=0.2,
    max_tokens=4096,
)

# Option 2: From environment variables
client = LLMGatewayClient.from_env()

# Option 3: From config object
config = LLMGatewayConfig.from_env()
client = LLMGatewayClient.from_config(config)
```

#### Methods

| Method | Description |
|--------|-------------|
| `generate_async(prompt, system_prompt)` | Generate text response |
| `generate_structured_async(prompt, response_model)` | Generate structured output with Pydantic |
| `from_env()` | Create client from environment variables |
| `from_config(config)` | Create client from config object |

#### Environment Variables

| Variable | Description |
|----------|-------------|
| `LLM_SERVER_URL` | Gateway endpoint URL |
| `LLM_MODEL_NAME` | Model to use (default: gpt-4) |
| `LLM_OAUTH_ENDPOINT` | OAuth token endpoint |
| `LLM_CLIENT_ID` | OAuth client ID |
| `LLM_CLIENT_SECRET` | OAuth client secret |
| `LLM_API_KEY` | API key (alternative to OAuth) |
| `LLM_TEMPERATURE` | Sampling temperature (default: 0.2) |
| `LLM_MAX_TOKENS` | Max output tokens (default: 4096) |

### RedisService

```python
from agentorchestrator.services import RedisService, RedisConfig

# From environment
redis = RedisService.from_env()
await redis.connect()

# Direct configuration
config = RedisConfig(
    host="redis.corp.com",
    port=6379,
    username="service",
    password="secret",
    ssl=True,
)
redis = RedisService.from_config(config)
```

### Mem0Memory

Semantic memory for agents (requires corporate MemoryStoreClient).

```python
from agentorchestrator.services import Mem0Memory

# Create memory with external client
from your_app import MemoryStoreClient

client = MemoryStoreClient(
    base_url="https://mem0.corp.com",
    agent_id="my-agent"
)
memory = Mem0Memory(client=client)

# Store and search
await memory.add("User prefers concise responses")
results = await memory.search("What are user preferences?")
```

### VectorStoreService

```python
from agentorchestrator.services import VectorStoreService, VectorDocument

vs = VectorStoreService()
await vs.upsert([
    VectorDocument(id="d1", text="Use async for I/O", metadata={"topic": "python"})
])
results = await vs.query("How to handle I/O?", limit=5)
```

---

## Core Classes

### AgentOrchestrator

The main entry point for creating pipelines.

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(
    name="my_app",           # Required: Unique name for this instance
    isolated=True,           # Default: Use isolated registries
)
```

#### Decorators

| Decorator | Description |
|-----------|-------------|
| `@ao.step(name, deps, produces)` | Register a processing step |
| `@ao.chain(name, steps)` | Register a chain of steps |
| `@ao.agent(name, capabilities)` | Register a data agent |
| `@ao.middleware(name, priority)` | Register middleware |

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
async with ao:
    result = await ao.launch("my_chain", data)
# Resources cleaned up automatically
```

---

### ChainContext

Shared state across steps in a chain execution.

```python
from agentorchestrator import ChainContext

# Access in steps
@ao.step(name="my_step")
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
from agentorchestrator.core.context import ContextScope

# Step scope - cleared after step completes
ctx.set("temp", value, scope=ContextScope.STEP)

# Chain scope - persists throughout chain (default)
ctx.set("data", value, scope=ContextScope.CHAIN)

# Global scope - persists across chains
ctx.set("config", value, scope=ContextScope.GLOBAL)
```

---

## Decorators

### @ao.step

Register a processing step.

```python
@ao.step(
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

### @ao.chain

Register a chain of steps.

```python
@ao.chain(
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

### @ao.agent

Register a data fetching agent.

```python
from agentorchestrator.agents import BaseAgent, AgentResult

@ao.agent(
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
from agentorchestrator import (
    LoggerMiddleware,
    CacheMiddleware,
    SummarizerMiddleware,
    TokenManagerMiddleware,
)
from agentorchestrator.middleware import (
    RateLimiterMiddleware,
    MetricsMiddleware,
    OffloadMiddleware,
)

# Logging
ao.use(LoggerMiddleware(level="INFO"))

# Caching
ao.use(CacheMiddleware(ttl_seconds=300))

# Summarization (requires LLM)
from agentorchestrator import create_openai_summarizer
summarizer = create_openai_summarizer(api_key="sk-...")
ao.use(SummarizerMiddleware(summarizer=summarizer, max_tokens=4000))

# Token management
ao.use(TokenManagerMiddleware(max_total_tokens=100000))

# Rate limiting
ao.use(RateLimiterMiddleware({
    "fetch_data": {"requests_per_second": 10},
}))

# Large payload offloading
from agentorchestrator.core.context_store import RedisContextStore
store = RedisContextStore(host="localhost", port=6380)
ao.use(OffloadMiddleware(store=store, threshold_bytes=100000))
```

### Custom Middleware

```python
from agentorchestrator import Middleware
from agentorchestrator.core.context import StepResult

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

ao.use(MyMiddleware(priority=50))
```

---

## Agents

### BaseAgent

Base class for all agents.

```python
from agentorchestrator.agents import BaseAgent, AgentResult

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
from agentorchestrator.agents import ResilientAgent, ResilientAgentConfig

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
from agentorchestrator.agents import AgentResult

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
from agentorchestrator.core.context_store import RedisContextStore, ContextRef

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
from agentorchestrator.testing import (
    IsolatedOrchestrator,
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
    async with IsolatedOrchestrator() as ao:
        @ao.step(name="test_step")
        async def test_step(ctx):
            return {"done": True}

        @ao.chain(name="test_chain")
        class TestChain:
            steps = ["test_step"]

        result = await ao.launch("test_chain", {})
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
    result = await ao.launch("my_chain", {})
    assert_step_completed(result, "fetch_data")
```

---

## Utilities

### Circuit Breaker

```python
from agentorchestrator import CircuitBreaker, CircuitBreakerConfig

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
from agentorchestrator import async_retry, RetryPolicy

@async_retry(max_attempts=3, backoff=2.0)
async def flaky_operation():
    ...
```

### Logging

```python
from agentorchestrator import configure_logging, get_logger

configure_logging(level="INFO", json_output=False)
logger = get_logger("my_module")
logger.info("Processing", company="Apple", step="extract")
```

### Tracing

```python
from agentorchestrator import configure_tracing, trace_span

configure_tracing(service_name="my-service", endpoint="http://jaeger:4317")

with trace_span("my_operation", {"key": "value"}):
    result = do_something()
```

---

## CLI

```bash
# Run chain
agentorchestrator run my_chain --data '{"key": "value"}'

# Validate
agentorchestrator check

# List components
agentorchestrator list

# Visualize
agentorchestrator graph my_chain
agentorchestrator graph my_chain --format mermaid

# Health check
agentorchestrator health
agentorchestrator health --detailed

# Diagnose issues
agentorchestrator doctor

# Development
agentorchestrator dev --watch

# Scaffolding
agentorchestrator new agent MyAgent
agentorchestrator new chain MyChain
agentorchestrator new project my-app
```
