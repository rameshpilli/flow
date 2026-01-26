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
        parameters={"expression": "str"},
    ),
    Tool(
        name="search",
        description="Search for information",
        func=search,
        parameters={"query": "str"},
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
print(result.answer)
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
