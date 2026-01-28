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

Vector storage for semantic search with in-memory (development) and remote (production) backends.

```python
from agentorchestrator.services import VectorStoreService, VectorDocument, VectorStoreConfig

# In-memory mode (default) - for development
vs = VectorStoreService()
await vs.upsert([
    VectorDocument(id="d1", text="Use async for I/O", metadata={"topic": "python"})
])
results = await vs.query("How to handle I/O?", top_k=5)
```

#### Async Context Manager (Recommended)

Use `async with` for automatic connection cleanup:

```python
async with VectorStoreService() as vs:
    await vs.upsert([VectorDocument(id="1", text="Hello world")])
    results = await vs.query("greeting", top_k=5)
# Connection automatically closed
```

#### Remote Providers (Production)

For remote vector stores (Cohere Compass or custom), `host` and `api_key` are **required**:

```python
from agentorchestrator.services import VectorStoreConfig, VectorStoreService

# Option 1: Direct configuration
config = VectorStoreConfig(
    provider="cohere_compass",
    host="https://compass.corp.com",
    api_key="sk-xxx",
    namespace="my-app",
)
vs = VectorStoreService(config=config)

# Option 2: From environment variables
# Set: VECTOR_PROVIDER, VECTOR_HOST, VECTOR_API_KEY, VECTOR_NAMESPACE
config = VectorStoreConfig.from_env()
vs = VectorStoreService(config=config)
```

**Note**: Creating a `VectorStoreService` with a remote provider but missing `host` or `api_key` raises `ConfigurationError` immediately, preventing runtime crashes.

#### Namespace Isolation

Different namespaces have completely separate document storage (prevents data leakage between tenants/runs):

```python
# Tenant A's documents
config_a = VectorStoreConfig(namespace="tenant-a")
vs_a = VectorStoreService(config=config_a)
await vs_a.upsert([VectorDocument(id="1", text="Tenant A data")])

# Tenant B's documents (separate index)
config_b = VectorStoreConfig(namespace="tenant-b")
vs_b = VectorStoreService(config=config_b)
await vs_b.upsert([VectorDocument(id="1", text="Tenant B data")])

# Each only sees their own data
results_a = await vs_a.query("data")  # Only Tenant A docs
results_b = await vs_b.query("data")  # Only Tenant B docs
```

#### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VECTOR_PROVIDER` | `memory` or `cohere_compass` | `memory` |
| `VECTOR_HOST` | Remote vector store URL | - |
| `VECTOR_API_KEY` | API key for authentication | - |
| `VECTOR_NAMESPACE` | Namespace for isolation | `default` |
| `VECTOR_TIMEOUT` | Request timeout in seconds | `30` |
| `VECTOR_VERIFY_SSL` | Verify TLS certificates | `true` |
| `COHERE_COMPASS_URL` | Fallback for `VECTOR_HOST` | - |
| `COHERE_COMPASS_API_KEY` | Fallback for `VECTOR_API_KEY` | - |

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

#### Launch Return Value

The `launch()` method returns a dictionary with the following structure:

```python
{
    "success": True,              # Whether all steps completed successfully
    "results": [                  # List of per-step results in execution order
        {
            "step": "step_name",
            "output": {...},      # What the step returned
            "duration_ms": 123.4,
            "error": None,        # Error message if step failed
            "error_type": None,   # Exception type if failed
        },
        # ... more steps
    ],
    "context": {                  # Final context state
        "data": {...},            # CHAIN-scoped data
        "steps": {...},           # STEP-scoped data by step name
    },
    "duration_ms": 1234.5,        # Total execution time in milliseconds
    "error": None,                # Error dict if chain failed: {"step": "...", "message": "...", "traceback": "..."}
}
```

**Accessing Step Outputs:**

```python
result = await ao.launch("my_chain", {"name": "World"})

# Check success
if result["success"]:
    # Access first step's output
    greeting = result["results"][0]["output"]["greeting"]

    # Or access via context
    greeting = result["context"]["data"]["greeting"]
else:
    print(f"Failed at step {result['error']['step']}: {result['error']['message']}")
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
    consumes=["raw_data"],            # Optional: Keys this step requires (for dataflow)
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
    error_handling="fail_fast",       # Optional: "fail_fast", "continue", or "retry"
    dataflow=False,                   # Optional: Enable dataflow-based dependency resolution
    input_model=MyInputModel,         # Optional: Pydantic model for input validation
    output_model=MyOutputModel,       # Optional: Pydantic model for output validation
    input_key="request",              # Optional: Key in initial_data to validate
)
class MyPipeline:
    steps = ["step_a", "step_b", "step_c"]

    # Optional: Define parallel execution groups
    parallel_groups = [
        ["step_a"],                   # Group 1: runs first
        ["step_b", "step_c"],         # Group 2: runs in parallel
    ]
```

#### Error Handling Modes

| Mode | Behavior |
|------|----------|
| `fail_fast` | Stop chain immediately on first step failure (default) |
| `continue` | Continue executing independent steps; skip dependents of failed steps |
| `retry` | Retry failed steps according to their retry configuration before failing |

#### Chain Output Validation

When `output_model` is set, the chain output is validated after successful execution:

```python
from pydantic import BaseModel

class ReportOutput(BaseModel):
    summary: str
    score: float

@ao.chain(name="report_chain", output_model=ReportOutput)
class ReportChain:
    steps = ["analyze", "summarize"]

# After execution, result["validated_output"] contains the validated model instance
result = await ao.launch("report_chain", {"data": ...})
if result["success"]:
    report = result["validated_output"]  # ReportOutput instance
```

#### Dataflow-Based Dependencies

When `dataflow=True`, the DAG executor automatically resolves dependencies based on `produces`/`consumes` declarations:

```python
from agentorchestrator import AgentOrchestrator, produces, consumes

ao = AgentOrchestrator(name="dataflow_example")

@produces("company_data")
@ao.step(name="fetch_company")
async def fetch_company(ctx):
    data = await api.get_company("AAPL")
    ctx.set("company_data", data)
    return data

@consumes("company_data")
@produces("analysis")
@ao.step(name="analyze")
async def analyze(ctx):
    data = ctx.get("company_data")
    return {"analysis": analyze_data(data)}

@consumes("company_data", "analysis")
@ao.step(name="report")
async def report(ctx):
    return {"report": generate_report(ctx)}

# Enable dataflow resolution
@ao.chain(name="research_chain", dataflow=True)
class ResearchChain:
    steps = ["fetch_company", "analyze", "report"]

# Dependencies are resolved automatically:
# - analyze depends on fetch_company (consumes company_data)
# - report depends on both (consumes company_data and analysis)
```

Explicit `deps=[]` declarations are merged with dataflow-inferred dependencies. Use `ao.check()` to validate dataflow resolution before running.

#### Chain Lifecycle Events

The executor emits these events during chain execution:

| Event | When Emitted | Payload |
|-------|--------------|---------|
| `ChainStarted` | Before first step executes | `{step_count}` |
| `ChainCompleted` | After all steps complete successfully | `{completed, failed, skipped}` |
| `ChainFailed` | When chain execution fails | `{error}` |

```python
from agentorchestrator.core.event_bus import get_event_bus

bus = get_event_bus()

@ao.event_handler("ChainCompleted")
async def on_chain_complete(ctx, event):
    print(f"Chain finished: {event.payload['completed']} completed, "
          f"{event.payload['failed']} failed")
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

### Middleware Pattern Matching

Middleware supports glob patterns for `applies_to` and `excludes` parameters:

```python
from agentorchestrator import Middleware

# Apply to all "gather_*" steps except "gather_final"
ao.use(SummarizerMiddleware(
    applies_to=["gather_*", "fetch_*"],  # Glob patterns
    excludes=["*_final", "gather_summary"],  # Exclusions take precedence
    max_tokens=4000,
))

# Conditional application based on runtime state
ao.use(TokenManagerMiddleware(
    applies_to=["*"],
    applies_when=lambda ctx, result: getattr(result, 'token_count', 0) > 2000,
))
```

Supported glob patterns:
- `*` matches everything
- `?` matches any single character
- `[seq]` matches any character in seq
- `[!seq]` matches any character not in seq

### TokenBudget (Token Reservation System)

Explicit token budget allocation prevents silent truncation:

```python
from agentorchestrator.middleware import TokenBudget, TokenManagerMiddleware, BudgetStatus

# Define explicit budget allocations
budget = TokenBudget(
    context_window=128000,      # Total LLM context window
    reserved_output=8000,       # Reserved for model response
    reserved_system=3000,       # Reserved for system prompt + tools
    reserved_history=15000,     # Reserved for conversation history
    warning_threshold=0.8,      # Warn at 80% of available
    critical_threshold=0.95,    # Force compression at 95%
)

# Available for step outputs: 128000 - 8000 - 3000 - 15000 = 102,000 tokens

ao.use(TokenManagerMiddleware(
    budget=budget,
    auto_summarize=True,
    summarizer=my_summarizer,
    target_ratio_after_compression=0.7,  # Compress to 70% when critical
))

# Check budget status
status = budget.get_status(current_tokens=90000)
# BudgetStatus.WARNING

report = budget.get_report(current_tokens=90000)
# {
#     "context_window": 128000,
#     "allocated": {"output_reserved": 8000, ...},
#     "usage_percent": 88.2,
#     "status": "warning",
#     "action_needed": False,
# }
```

#### BudgetStatus Levels

| Status | Condition | Action |
|--------|-----------|--------|
| `OK` | Under warning threshold | None |
| `WARNING` | Above warning, below critical | Log warning |
| `CRITICAL` | Above critical, below overflow | Auto-compress |
| `OVERFLOW` | Exceeded available budget | Force compress + offload |

### Tree Summarization Strategy

Hierarchical tree summarization for very large documents (50K+ tokens):

```python
from agentorchestrator.middleware import (
    SummarizerMiddleware,
    SummarizationStrategy,
    create_openai_summarizer,
)

# Create summarizer with TREE strategy
summarizer = create_openai_summarizer(
    model="gpt-4",
    strategy=SummarizationStrategy.TREE,
    tree_group_size=4,  # Group 4 chunks at each level
)

# Use with middleware
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    max_tokens=4000,
    applies_to=["gather_sec", "gather_research"],
))

# Direct usage
summary = await summarizer.summarize(
    text=large_sec_filing,  # 100K tokens
    max_tokens=4000,
    strategy=SummarizationStrategy.TREE,
)
```

#### How Tree Summarization Works

```
Input: 100K tokens (25 chunks of 4K each)

Level 1: 25 chunks → 25 summaries (parallel, ~400 tokens each)
Level 2: 7 groups of ~4 → 7 summaries (parallel)
Level 3: 2 groups of ~4 → 2 summaries (parallel)
Level 4: 1 group of 2 → 1 final summary

Output: ~800 tokens (99.2% reduction)
```

#### Strategy Selection Guide

| Strategy | Best For | Parallelism | Quality |
|----------|----------|-------------|---------|
| `STUFF` | < 4K tokens | N/A | High |
| `MAP_REDUCE` | 10K-50K tokens | High | Good |
| `REFINE` | Quality-critical | None (sequential) | Highest |
| `TREE` | 50K+ tokens | High | Good |

### RollingSummaryMiddleware

Incremental summarization that updates progressively instead of re-summarizing everything:

```python
from agentorchestrator.middleware import RollingSummaryMiddleware, RollingSummaryState

ao.use(RollingSummaryMiddleware(
    max_tokens=4000,
    summarizer=my_summarizer,
    recent_buffer_tokens=1000,  # Keep last 1000 tokens in full
    applies_to=["gather_news", "gather_social"],
))

# How it works:
# Iteration 1: 15K tokens → summarize → 2K tokens
# Iteration 2: +10K tokens → summarize NEW only → merge → 3K tokens
# Iteration 3: +8K tokens → summarize NEW only → merge → 3.5K tokens
#
# Total processed: 33K tokens
# Final summary: 3.5K tokens (vs re-summarizing 33K each time)
```

#### Rolling Summary State

```python
# Access rolling summary state
state = rolling_middleware.get_state(ctx, "gather_news")
# RollingSummaryState(
#     summary="...",
#     token_count=3500,
#     sources_included=["gather_news_v0", "gather_news_v1", ...],
#     version=3,
#     original_tokens_processed=33000,
# )

# Get just the summary
summary = rolling_middleware.get_summary(ctx, "gather_news")

# Reset state
rolling_middleware.reset(ctx, "gather_news")
```

### Query-Aware Compression

Filter and summarize based on query relevance:

```python
from agentorchestrator.middleware import create_openai_summarizer

summarizer = create_openai_summarizer(model="gpt-4")

# Summarize SEC filing focusing only on risk factors
summary = await summarizer.summarize_with_query(
    text=sec_10k_filing,  # 100K tokens
    query="What are the key risk factors and supply chain dependencies?",
    max_tokens=2000,
    relevance_threshold=0.3,  # Include chunks scoring >= 0.3 relevance
)

# How it works:
# 1. Split into chunks
# 2. Score each chunk's relevance to query (0.0-1.0)
# 3. Filter chunks below threshold
# 4. Summarize only relevant content with query focus
#
# Result: Focused summary on risks, ignoring irrelevant sections
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

## DSL Pipeline

Declarative pipeline builder for creating chains without decorators.

```python
from agentorchestrator.dsl import Pipeline, Step

# Define pipeline declaratively
pipeline = Pipeline(name="data_processing") \
    .add_step(Step(
        name="fetch",
        handler=fetch_data,
        produces=["raw_data"],
    )) \
    .add_step(Step(
        name="transform",
        handler=transform_data,
        deps=["fetch"],
        produces=["processed_data"],
    )) \
    .add_step(Step(
        name="save",
        handler=save_results,
        deps=["transform"],
    ))

# Register with orchestrator
ao.register_pipeline(pipeline)

# Or build from config
config = {
    "name": "my_pipeline",
    "steps": [
        {"name": "step1", "handler": "module:func1"},
        {"name": "step2", "handler": "module:func2", "deps": ["step1"]},
    ]
}
pipeline = Pipeline.from_config(config)
```

### Pipeline Methods

| Method | Description |
|--------|-------------|
| `add_step(step)` | Add a step to the pipeline |
| `add_middleware(middleware)` | Add middleware to the pipeline |
| `from_config(config)` | Build pipeline from dict/YAML |
| `to_config()` | Export pipeline as config dict |
| `validate()` | Validate pipeline structure |

---

## Event Bus

Event-driven workflows with pub/sub messaging.

```python
from agentorchestrator.core.event_bus import Event, get_event_bus

# Get event bus (auto-selects Redis if available)
bus = get_event_bus(prefer_redis=True)

# Publish events
await bus.publish(Event(
    type="DataFetched",
    payload={"company": "Apple", "data": {...}},
    run_id="run-123",
))

# Subscribe to events
async for event in bus.subscribe(event_types=["DataFetched"]):
    print(f"Received: {event.type} - {event.payload}")

# Event handlers with decorators
@ao.event_handler("ResearchTask")
async def handle_research(ctx, event):
    result = await do_research(event.payload)
    return Event(type="ResearchComplete", payload=result)

# Run event loop
await ao.run_event_loop(ctx, max_events=100)
```

### Event Class

```python
from agentorchestrator.core.event_bus import Event

event = Event(
    type="StepCompleted",        # Required: Event type string
    payload={"result": ...},     # Optional: Event data
    step="process_data",         # Optional: Associated step
    run_id="run-123",            # Optional: Run identifier
    metadata={"source": "api"},  # Optional: Additional metadata
)

# Serialization
json_str = event.to_json()
event = Event.from_json(json_str)
```

### Event Bus Implementations

| Implementation | Use Case |
|----------------|----------|
| `InMemoryEventBus` | Single process, testing |
| `RedisEventBus` | Multi-process, production |

---

## StateStore

Type-safe state management with Pydantic models.

```python
from pydantic import BaseModel, Field
from agentorchestrator import Context
from agentorchestrator.core.state import StateStore

# Define your state model
class PipelineState(BaseModel):
    counter: int = Field(default=0)
    items: list[str] = Field(default_factory=list)
    status: str = "pending"

# Use with context
ctx = Context(state_model=PipelineState)

# Type-safe access (IDE autocomplete!)
print(ctx.state.counter)  # 0
print(ctx.state.items)    # []

# Atomic updates
async with ctx.edit_state() as state:
    state.counter += 1
    state.items.append("new item")
    state.status = "processing"

# Validation happens automatically
try:
    async with ctx.edit_state() as state:
        state.counter = "invalid"  # Raises ValidationError
except ValueError as e:
    print("Validation failed:", e)
```

### StateStore Class

```python
from agentorchestrator.core.state import StateStore

store = StateStore(PipelineState)

# Get current state (immutable snapshot)
state = store.get_state()

# Update state
store.update({"counter": state.counter + 1})

# Reset to defaults
store.reset()

# Export for persistence
data = store.to_dict()
store.load_dict(data)
```

---

## Function Agent

LLM-powered agent that can use tools/functions.

```python
from agentorchestrator.squad.agents import FunctionAgent, FunctionAgentOptions

# Define tools
tools = [
    {
        "name": "search",
        "description": "Search the web for information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    }
]

# Tool implementation
async def execute_tool(name: str, args: dict) -> str:
    if name == "search":
        return await search_web(args["query"])
    raise ValueError(f"Unknown tool: {name}")

# Create agent
agent = FunctionAgent(FunctionAgentOptions(
    name="SearchAgent",
    description="Searches for information",
    tools=tools,
    tool_executor=execute_tool,
    system_prompt="You help users find information.",
))

# Use agent
result = await agent.process_request(
    input_text="Find recent news about AI",
    user_id="user-123",
    session_id="session-456",
)
print(result.content)
```

### FunctionAgentOptions

| Option | Type | Description |
|--------|------|-------------|
| `name` | str | Agent name |
| `description` | str | What the agent does |
| `tools` | list[dict] | OpenAI function schema |
| `tool_executor` | Callable | Function to execute tools |
| `system_prompt` | str | Agent instructions |
| `max_tool_calls` | int | Max tool calls per request (default: 10) |
| `llm_client` | LLMGatewayClient | LLM client (optional) |

---

## ReAct Agent

Reasoning and Acting agent pattern for complex problem solving.

```python
from agentorchestrator.agents import ReActAgent, ReActConfig, Tool

# Define tools
tools = [
    Tool(
        name="calculator",
        description="Calculate mathematical expressions",
        func=calculate,
        parameters={"expression": {"type": "string", "description": "Math expression to evaluate"}},
        required_params=["expression"],  # Validates required parameters
    ),
    Tool(
        name="search",
        description="Search for information",
        func=search,
        parameters={"query": {"type": "string", "description": "Search query"}},
        required_params=["query"],
    ),
]

# Create agent
agent = ReActAgent(
    llm_client=client,
    tools=tools,
    config=ReActConfig(
        max_iterations=10,
        thought_prompt="Let me think step by step...",
    ),
)

# Run
result = await agent.run("What is the population of France times 2?")
print(result.final_answer)
print(result.steps)  # Shows thought/action/observation chain
```

### ReActConfig

| Option | Default | Description |
|--------|---------|-------------|
| `max_iterations` | 10 | Max reasoning iterations |
| `thought_prompt` | None | Custom prompt for thought generation |
| `verbose` | False | Log intermediate steps |

---

## Tool Registry

Centralized tool management for agents.

```python
from agentorchestrator.agents import ToolRegistry, ToolCategory

# Create registry
registry = ToolRegistry(name="my_tools")

# Register tool with decorator
@registry.tool(
    name="calculate",
    description="Perform calculations",
    category=ToolCategory.UTILITY,
)
async def calculate(expression: str) -> str:
    return str(eval(expression))

# Register programmatically
registry.register(
    name="fetch_url",
    func=fetch_url,
    description="Fetch content from URL",
    category=ToolCategory.DATA,
)

# Discover tools
math_tools = registry.discover(category=ToolCategory.UTILITY)

# Get OpenAI schemas
schemas = registry.get_openai_schemas()

# Execute tool
result = await registry.execute("calculate", expression="2+2")
```

### Built-in Tools

```python
from agentorchestrator.agents.tools import register_builtin_tools

# Register built-in utility tools
register_builtin_tools(registry)

# Available: calculate, get_current_time, text_length
result = await registry.execute("calculate", expression="3.14 * 10")
```

---

## Multi-Agent Context Sharing

The framework uses **coordinator-mediated context sharing** rather than direct access between agents. This prevents "context pollution" and enables clean result aggregation.

### Multi-Agent Patterns Overview

| Pattern | Key Class | How Context Flows |
|---------|-----------|-------------------|
| **Supervisory** | `SupervisorAgent` | Supervisor coordinates team, shares context via `send_messages` tool |
| **Intent-Based** | `MultiAgentOrchestrator` | Classifier routes to best agent; each maintains independent history |
| **Squad** | `Squad` | High-level wrapper around SupervisorAgent |

### Context Isolation System

The key mechanism is the **AgentContextNamespace** which provides isolated storage for each agent:

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    AgentContextNamespace,
    IsolationLevel,
)

# Create isolation manager with coordinator context
isolation = ContextIsolationManager(coordinator_context=ctx)

# Create isolated namespaces for each agent
ns_research = isolation.create_namespace("research_agent", IsolationLevel.FULL)
ns_analyst = isolation.create_namespace("analyst_agent", IsolationLevel.FULL)
```

#### Isolation Levels

| Level | Behavior |
|-------|----------|
| `FULL` | Agent sees ONLY its own data + explicitly shared keys (recommended) |
| `PARTIAL` | Agent sees own data + coordinator CHAIN-scoped data (read-only) |
| `NONE` | No isolation (legacy mode, full context sharing) |

### Data Flow Architecture

```
Coordinator (ChainContext)
    │
    ├─→ ContextIsolationManager
    │   │
    │   ├─→ Agent1.Namespace (FULL isolation)
    │   │   ├─ Local Store (agent's private data)
    │   │   ├─ Shared Keys (query, user_id, etc.)
    │   │   └─ Published Keys (results for others)
    │   │
    │   ├─→ Agent2.Namespace (FULL isolation)
    │   │   └─ ...similar structure...
    │   │
    │   └─→ Provenance Tracking (audit trail)
    │
    └─→ ResultAggregator
        └─ Combines outputs using selected strategy
```

### ContextIsolationManager

Controls data flow between agents:

```python
from agentorchestrator.squad.context import ContextIsolationManager

isolation = ContextIsolationManager(coordinator_context=ctx)

# Create namespaces
ns1 = isolation.create_namespace("agent_1", IsolationLevel.FULL)
ns2 = isolation.create_namespace("agent_2", IsolationLevel.FULL)

# Share data with all agents
isolation.share_with_all("query")
isolation.share_with_all("user_id")

# Selective sharing between agents
isolation.share_between(
    source_agent="research_agent",
    key="findings",
    target_agents=["analyst_agent", "writer_agent"]
)

# Revoke sharing
isolation.revoke_sharing("sensitive_data", agent_ids=["untrusted_agent"])

# Execute agents in parallel with isolation
async def process_agent(agent, namespace):
    return await agent.process(namespace)

results = await isolation.execute_parallel(agents, process_agent)

# Get all results
all_results = isolation.get_all_results()

# Audit trail
provenance = isolation.get_shared_data_provenance()
stats = isolation.get_stats()
```

#### ContextIsolationManager Methods

| Method | Description |
|--------|-------------|
| `create_namespace(agent_id, level)` | Create isolated namespace for an agent |
| `get_namespace(agent_id)` | Get existing namespace |
| `share_with_all(key, value)` | Share data with all agents |
| `share_between(source, key, targets)` | Selective sharing between agents |
| `revoke_sharing(key, agent_ids)` | Revoke access to shared data |
| `execute_parallel(agents, process_fn)` | Run agents in parallel with isolation |
| `get_all_results()` | Collect results from all namespaces |
| `get_sharing_graph()` | Get visualization of sharing relationships |
| `get_shared_data_provenance()` | Audit trail of all sharing operations |

### AgentContextNamespace

Each agent interacts with context through its namespace:

```python
# Inside an agent's execution context
async def agent_process(namespace: AgentContextNamespace):
    # === Private Local Storage ===
    # Only this agent can see this data
    namespace.set("working_data", {"temp": "value"})
    data = namespace.get("working_data")

    if namespace.has("cached_result"):
        return namespace.get("cached_result")

    # === Access Shared Data ===
    # Request access to data shared by coordinator
    namespace.grant_access("query")
    query = namespace.get("query")

    # === Publish Results ===
    # Make data available to other agents (via coordinator)
    # Stored as "agent_id:findings" in coordinator context
    namespace.publish("findings", {
        "summary": "Analysis complete",
        "data": results
    })

    # === Set Final Result ===
    namespace.set_result(
        result={"answer": "..."},
        metadata={"confidence": 0.95, "sources": ["doc1", "doc2"]}
    )

    return namespace.get_result()
```

#### AgentContextNamespace Methods

| Method | Description |
|--------|-------------|
| `set(key, value)` | Store in agent's private local storage |
| `get(key, default)` | Retrieve from local or shared storage |
| `has(key)` | Check if key exists |
| `delete(key)` | Remove from local storage |
| `keys()` | List all accessible keys |
| `grant_access(key)` | Request access to shared data |
| `revoke_access(key)` | Release access to shared data |
| `publish(key, value)` | Publish data for other agents |
| `set_result(result, metadata)` | Set agent's final result |
| `get_result()` | Get agent's result |
| `get_all_results()` | Get all results from this namespace |
| `get_metadata()` | Get execution metadata |
| `snapshot()` | Export namespace state for debugging |

### Result Aggregation

Combine results from multiple isolated agents:

```python
from agentorchestrator.squad.context import ResultAggregator, AggregationStrategy

# Create aggregator with strategy
aggregator = ResultAggregator(
    strategy=AggregationStrategy.SYNTHESIZE,
    conflict_resolver=custom_resolver_fn  # Optional
)

# Add results from each agent's namespace
aggregator.add_from_namespace("research_agent", ns_research)
aggregator.add_from_namespace("analyst_agent", ns_analyst)

# Or add results manually
aggregator.add_result(
    agent_id="writer_agent",
    data={"report": "..."},
    confidence=0.9,
    priority=1,
    metadata={"word_count": 500}
)

# Aggregate all results
result = await aggregator.aggregate(llm=llm_client)

# Access aggregated data
print(result.data)        # Combined result
print(result.confidence)  # Overall confidence (reduced by conflicts)
print(result.conflicts)   # List of detected conflicts
print(result.metadata)    # Aggregation metadata
```

#### Aggregation Strategies

| Strategy | Behavior |
|----------|----------|
| `SYNTHESIZE` | LLM creates narrative combining all results (default) |
| `MERGE` | Deep merge structured data (JSON/dicts), tracks conflicts |
| `PRIORITIZE` | Select result with highest confidence or priority |
| `VOTE` | Majority voting for discrete answers |
| `CHAIN` | Sequential refinement by priority order |
| `CONCAT` | Simple concatenation of text results |

#### Conflict Resolution

During `MERGE` aggregation, conflicts are detected when multiple agents provide different values for the same key:

```python
def custom_resolver(key: str, values: list[tuple[str, Any]]) -> Any:
    """Resolve conflicts between agent outputs.

    Args:
        key: The conflicting key
        values: List of (agent_id, value) tuples

    Returns:
        The resolved value
    """
    # Example: prefer the agent with higher priority
    agent_priorities = {"analyst": 1, "researcher": 2}
    sorted_values = sorted(values, key=lambda x: agent_priorities.get(x[0], 0))
    return sorted_values[-1][1]

aggregator = ResultAggregator(
    strategy=AggregationStrategy.MERGE,
    conflict_resolver=custom_resolver
)
```

### Chat History Sharing (Supervisor Pattern)

In the supervisory pattern, the supervisor maintains conversation history via `ChatStorage`:

```python
from agentorchestrator.squad.storage import InMemoryChatStorage, RedisChatStorage
from agentorchestrator.squad.agents import SupervisorAgent

# In-memory for development
storage = InMemoryChatStorage()

# Redis for production (24-hour TTL, distributed)
storage = RedisChatStorage(redis_client=redis)

# Supervisor uses storage to maintain agent memory
supervisor = SupervisorAgent(
    lead_agent=lead,
    team_agents=[agent1, agent2],
    storage=storage,
)

# How context flows in supervisor pattern:
# 1. Supervisor fetches agent's history
history = await storage.fetch_chat(user_id, session_id, agent_id)

# 2. Passes to agent with current query
response = await agent.process_request(
    input_text=query,
    user_id=user_id,
    session_id=session_id,
    chat_history=history,
    additional_params={"shared_context": data}
)

# 3. Saves response back to storage
await storage.save_chat_messages(user_id, session_id, agent_id, messages)

# 4. Includes relevant history in next supervisor prompt via {{AGENTS_MEMORY}}
```

### Complete Example: Multi-Agent Research Pipeline

```python
from agentorchestrator import AgentOrchestrator, ChainContext
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
    IsolationLevel,
)

ao = AgentOrchestrator(name="research_pipeline")

@ao.step(name="multi_agent_research")
async def multi_agent_research(ctx: ChainContext):
    # Create isolation manager
    isolation = ContextIsolationManager(coordinator_context=ctx)

    # Create isolated namespaces
    ns_news = isolation.create_namespace("news_agent", IsolationLevel.FULL)
    ns_finance = isolation.create_namespace("finance_agent", IsolationLevel.FULL)
    ns_social = isolation.create_namespace("social_agent", IsolationLevel.FULL)

    # Share common data with all agents
    isolation.share_with_all("query", ctx.get("query"))
    isolation.share_with_all("company", ctx.get("company"))

    # Define agent processors
    async def process_news(ns):
        query = ns.get("query")
        results = await news_api.search(query)
        ns.publish("news_data", results)
        ns.set_result({"articles": results}, metadata={"count": len(results)})

    async def process_finance(ns):
        company = ns.get("company")
        data = await finance_api.get_metrics(company)
        ns.publish("financial_data", data)
        ns.set_result(data, metadata={"confidence": 0.95})

    async def process_social(ns):
        query = ns.get("query")
        sentiment = await social_api.analyze(query)
        ns.publish("sentiment", sentiment)
        ns.set_result(sentiment, metadata={"sample_size": 1000})

    # Execute all agents in parallel with isolation
    agents = [
        ("news_agent", ns_news, process_news),
        ("finance_agent", ns_finance, process_finance),
        ("social_agent", ns_social, process_social),
    ]

    await asyncio.gather(*[
        proc(ns) for _, ns, proc in agents
    ])

    # Aggregate results
    aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
    aggregator.add_from_namespace("news_agent", ns_news)
    aggregator.add_from_namespace("finance_agent", ns_finance)
    aggregator.add_from_namespace("social_agent", ns_social)

    result = await aggregator.aggregate(llm=llm_client)

    # Store aggregated result
    ctx.set("research_summary", result.data)
    ctx.set("confidence", result.confidence)

    # Get stats for observability
    stats = isolation.get_stats()
    ctx.set("isolation_stats", stats)

    return {
        "summary": result.data,
        "confidence": result.confidence,
        "conflicts": result.conflicts,
    }
```

### Why Context Isolation?

| Without Isolation | With Isolation |
|-------------------|----------------|
| N agents × full context = token explosion | Each agent sees only what it needs |
| Risk of context pollution | Clean separation of concerns |
| No audit trail | Full provenance tracking |
| Difficult to debug | Easy to inspect per-agent state |
| Hard to aggregate results | Built-in aggregation strategies |

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

The CLI is available as both `ao` (recommended shorthand) and `agentorchestrator` (full name):

```bash
# Execution
ao run my_chain --data '{"key": "value"}'      # Run a chain
ao run my_chain --resumable                    # With checkpointing
ao run my_chain --dry-run                      # Preview execution
ao run my_chain --step my_step                 # Test single step
ao resume <run_id>                             # Resume failed run
ao runs --status failed                        # List runs
ao run-info <run_id>                           # Run details
ao run-output <run_id>                         # Partial outputs

# Validation & Inspection
ao check                                       # Quick validation
ao validate my_chain                           # Comprehensive checks
ao list                                        # List components
ao graph my_chain                              # ASCII DAG
ao graph my_chain --format mermaid             # Mermaid diagram

# Development & Debugging
ao dev --watch                                 # Hot reload mode
ao debug my_chain --data '{}'                  # Debug with snapshots

# Health & Diagnostics
ao health                                      # Basic health
ao health --detailed                           # Full health check
ao doctor                                      # Diagnose issues
ao version                                     # Version info
ao config                                      # Show config

# Scaffolding
ao new agent MyAgent                           # Agent template
ao new chain MyChain                           # Chain template
ao new project my-app                          # Full project
```

See [CLI Reference](cli/index.md) for complete documentation.
