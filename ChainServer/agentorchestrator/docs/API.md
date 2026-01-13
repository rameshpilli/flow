# AgentOrchestrator API Reference

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

## Agent Squad Integration

AgentOrchestrator integrates with [AWS Labs Agent Squad](https://github.com/awslabs/agent-squad) for intelligent multi-agent routing and supervisor patterns.

### SupervisorAgent

Coordinates multiple team agents with dynamic delegation.

```python
from agentorchestrator.agents import SupervisorAgent, SupervisorConfig

supervisor = SupervisorAgent(
    team=[sec_agent, capiq_agent, news_agent],
    config=SupervisorConfig(
        lead_model="anthropic.claude-3-sonnet-20240229-v1:0",
        parallel_execution=True,
        response_strategy=ResponseStrategy.SUMMARIZE,
        max_tokens_per_agent=2000,
    ),
    llm=my_llm,
)

# Lead agent decides which team members to invoke
result = await supervisor.fetch("What are Apple's key financial risks?")
# Only sec_agent and capiq_agent may be called - news_agent skipped if not relevant
```

### AgentSquadBridge

Bridge for intelligent routing between agents.

```python
from agentorchestrator.agents import (
    AgentSquadBridge,
    AgentSquadConfig,
    RoutingStrategy,
    ResponseStrategy,
)

bridge = AgentSquadBridge(
    config=AgentSquadConfig(
        default_strategy=RoutingStrategy.CLASSIFIER,
        response_strategy=ResponseStrategy.SUMMARIZE,
        max_tokens_per_agent=2000,
    ),
    llm=my_llm,
)

# Add agents with descriptions for routing
bridge.add_ao_agent(sec_agent, description="SEC filing expert")
bridge.add_ao_agent(capiq_agent, description="Financial data analyst")

# Classifier routes to single best agent
result = await bridge.route("What was Apple's revenue?")

# Or broadcast to all agents
result = await bridge.broadcast("Analyze Apple's financial health")
```

### Routing Strategies

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `CLASSIFIER` | Routes to single best agent | When query fits one specialist |
| `BROADCAST` | Sends to all agents in parallel | Comprehensive analysis needed |
| `SUPERVISOR` | Lead agent decides dynamically | Complex queries requiring coordination |
| `ROUND_ROBIN` | Distributes across agents | Load balancing |

### Response Strategies

| Strategy | Description | Token Cost |
|----------|-------------|------------|
| `SUMMARIZE` | Summarize each response | ~2K per agent |
| `EXTRACT` | Extract structured data | Depends on model |
| `TRUNCATE` | Cut to max tokens | Fixed limit |
| `MAP_REDUCE` | Two-phase synthesis | 2 LLM calls |
| `RAW` | Pass through unchanged | Full content |

### Pluggable Interfaces

The integration provides pluggable interfaces for custom implementations:

#### ConversationMemoryStore

Implement for custom conversation persistence (Redis, PostgreSQL, MongoDB, etc.).

```python
from agentorchestrator.agents import ConversationMemoryStore, AgentSquadBridge

class RedisMemoryStore(ConversationMemoryStore):
    def __init__(self, redis_client):
        self.redis = redis_client

    async def store(self, session_id, user_id, entry):
        key = f"conv:{session_id}:{user_id}"
        await self.redis.rpush(key, json.dumps(entry))
        await self.redis.ltrim(key, -100, -1)  # Keep last 100

    async def retrieve(self, session_id, user_id, limit=10):
        key = f"conv:{session_id}:{user_id}"
        entries = await self.redis.lrange(key, -limit, -1)
        return [json.loads(e) for e in entries]

    async def clear(self, session_id, user_id):
        await self.redis.delete(f"conv:{session_id}:{user_id}")

# Use with bridge
bridge = AgentSquadBridge(memory_store=RedisMemoryStore(redis_client))
```

#### AgentClassifier

Implement for custom routing logic.

```python
from agentorchestrator.agents import AgentClassifier, AgentSquadBridge

class EmbeddingClassifier(AgentClassifier):
    def __init__(self, embeddings_model):
        self.embeddings = embeddings_model
        self.agent_embeddings = {}

    async def classify(self, query, agents, context=None):
        query_embedding = await self.embeddings.embed(query)

        # Compute agent embeddings if not cached
        for name, desc in agents.items():
            if name not in self.agent_embeddings:
                self.agent_embeddings[name] = await self.embeddings.embed(desc)

        # Find best match by cosine similarity
        best_agent = max(
            agents.keys(),
            key=lambda n: cosine_similarity(query_embedding, self.agent_embeddings[n])
        )
        return {"agent": best_agent, "confidence": 0.85}

# Use with bridge
bridge = AgentSquadBridge(classifier=EmbeddingClassifier(embeddings))
```

#### Built-in Classifiers

| Classifier | Description | Requirements |
|------------|-------------|--------------|
| `KeywordClassifier` | Simple keyword matching | None |
| `LLMClassifier` | LLM-based intelligent routing | LangChain LLM |
| `LLMGatewayClassifier` | Uses LLM Gateway with OAuth | LLMGatewayClient |

```python
from agentorchestrator.agents import LLMClassifier, KeywordClassifier, LLMGatewayClassifier

# LLM Gateway classifier (recommended for proxy environments)
from agentorchestrator.services.llm_gateway import LLMGatewayClient
from cmpt.config import Config

llm_client = LLMGatewayClient(
    server_url=Config.LLM_SERVER_URL,
    oauth_endpoint=Config.LLM_OAUTH_ENDPOINT,
    client_id=Config.LLM_CLIENT_ID,
    client_secret=Config.LLM_CLIENT_SECRET,
    model_name=Config.LLM_MODEL_NAME,
)
bridge = AgentSquadBridge(
    classifier=LLMGatewayClassifier(llm_client),
)

# LLM classifier (for direct LangChain LLM access)
bridge = AgentSquadBridge(
    classifier=LLMClassifier(llm=my_llm, temperature=0.0),
)

# Keyword classifier (no LLM required)
bridge = AgentSquadBridge(
    classifier=KeywordClassifier(),
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