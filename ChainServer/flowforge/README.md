# FlowForge

**A DAG-based Chain Orchestration Framework**

FlowForge is a lightweight, decorator-driven framework for building data processing pipelines with automatic dependency resolution, context management, and middleware support. Built for production with enterprise-grade resilience and observability.

## Features

- **Decorator-Based Registration**: Simple `@forge.agent()`, `@forge.step()`, `@forge.chain()` decorators
- **DAG Execution**: Automatic dependency resolution with parallel execution
- **Explicit Parallel Groups**: Define custom execution ordering with `parallel_groups`
- **Per-Step Concurrency Limits**: Control parallelism with `max_concurrency` per step
- **Context Management**: Shared state across steps with scoped storage
- **Middleware Support**: Logging, caching, summarization, token management
- **Agent System**: Pre-built and custom data agents
- **MCP Integration**: Connect external MCP servers as agents
- **Extensible**: Register your own agents, steps, and chains

### Production Features

- **CLI Tool**: Run chains, validate definitions, visualize DAGs from command line
- **Debug Mode**: Context snapshots after each step for troubleshooting
- **Circuit Breakers**: Automatic failure protection for external services
- **Retry with Backoff**: Configurable retry policies with exponential backoff
- **Connection Pooling**: Shared HTTP client pools for high concurrency
- **Structured Logging**: OTel-compliant structured logging with JSON output
- **Distributed Tracing**: OpenTelemetry support for observability
- **Resource Management**: Dependency injection with lifecycle management
- **Cleanup Timeout**: Configurable timeout for resource cleanup (prevents hanging)
- **Hot Reload Dev Mode**: Auto-restart on file changes during development
- **Registry Isolation**: Isolated registries by default to prevent state bleed
- **Registry Strict Mode**: Optional strict mode to prevent accidental overwrites
- **True Fail-Fast**: Immediate task cancellation on first failure (not wait-for-all)
- **Graceful Degradation**: Partial success tracking with continue-on-error mode
- **Rich Error Metadata**: Per-step error types, tracebacks, and retry counts
- **Typed Configuration**: Environment variable validation with secret masking
- **External Secret Backends**: AWS Secrets Manager, HashiCorp Vault support
- **Health Endpoints**: Built-in health checks and version info for ops visibility

## Installation

```bash
# From source
pip install -e ./flowforge

# With observability support (structlog, OpenTelemetry)
pip install -e "./flowforge[observability]"

# With dev tools (pytest, watchdog for hot reload)
pip install -e "./flowforge[dev]"

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

## CLI Usage

FlowForge includes a CLI for running chains, validation, and development:

```bash
# Run a chain
flowforge run my_pipeline --data '{"company": "Apple"}'

# Validate all definitions
flowforge check

# List all registered agents, steps, and chains
flowforge list

# Visualize chain DAG
flowforge graph my_pipeline
flowforge graph my_pipeline --format mermaid

# Generate new agent/chain from template
flowforge new agent MyCustomAgent
flowforge new chain MyPipeline

# Development mode with hot reload
flowforge dev --watch
flowforge dev --watch --port 8000

# Debug mode - context snapshots after each step
flowforge debug my_pipeline --company "Apple"
flowforge debug my_pipeline --snapshot-dir ./debug_output

# Health check (returns exit code 1 if unhealthy)
flowforge health
flowforge health --json

# Version info
flowforge version
flowforge version --json

# Show configuration (secrets masked)
flowforge config
flowforge config --json
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
│  ┌─────────────────────────────────────────────────────┐   │
│  │             Resource Manager                         │   │
│  │  Dependency Injection | Lifecycle | Cleanup          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │             Production Utilities                     │   │
│  │  Circuit Breaker | Retry | Logging | Tracing         │   │
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

### Explicit Parallel Groups

Define custom execution ordering with `parallel_groups`:

```python
@forge.chain(
    name="my_pipeline",
    parallel_groups=[
        ["extract"],                              # Group 1: runs first
        ["fetch_news", "fetch_filings"],          # Group 2: runs in parallel
        ["combine", "validate"],                  # Group 3: runs after group 2
    ]
)
class MyPipeline:
    steps = ["extract", "fetch_news", "fetch_filings", "combine", "validate"]
```

### Per-Step Concurrency Limits

Control parallelism for rate-limited APIs:

```python
@forge.step(
    name="fetch_from_api",
    max_concurrency=3,  # Max 3 concurrent instances
)
async def fetch_from_api(ctx): ...
```

### Resource Injection

Register resources with automatic lifecycle management:

```python
from flowforge import FlowForge

forge = FlowForge(name="my_app")

# Register resources with cleanup handlers
forge.register_resource(
    "db",
    factory=lambda: create_db_pool(),
    cleanup=lambda pool: pool.close(),
)

forge.register_resource(
    "llm",
    factory=lambda: LLMGatewayClient(base_url="..."),
    cleanup=lambda client: client.close_sync(),
)

# Inject resources into steps
@forge.step(name="fetch_data", resources=["db", "llm"])
async def fetch_data(ctx, db, llm):
    # db and llm are automatically injected
    data = await db.query("SELECT * FROM ...")
    summary = await llm.complete_async(str(data))
    return {"data": summary}

# Resource cleanup with timeout (prevents hanging)
async with forge:
    result = await forge.run("my_chain")
# Resources cleaned up with 30s timeout (configurable)

# Manual cleanup with custom timeout
await forge.cleanup_resources(timeout_seconds=60.0)
```

### Registry Strict Mode

Prevent accidental component overwrites with strict mode:

```python
from flowforge import FlowForge

forge = FlowForge(name="my_app")

# First registration succeeds
@forge.step(name="my_step")
async def my_step(ctx):
    return {"done": True}

# Second registration with same name silently overwrites (default)
# To prevent this, use strict mode in the registry directly:
from flowforge.core.registry import get_step_registry

registry = get_step_registry()
registry.register_step("unique_step", handler, strict=True)  # Raises if exists

# Or when registering chains/agents:
registry.register_chain("unique_chain", steps, strict=True)
registry.register_agent("unique_agent", AgentClass, strict=True)
```

### Circuit Breaker

Protect external services from cascading failures:

```python
from flowforge import CircuitBreaker, CircuitBreakerConfig

# Configure circuit breaker
config = CircuitBreakerConfig(
    failure_threshold=5,      # Open after 5 failures
    recovery_timeout=30.0,    # Wait 30s before trying again
    half_open_max_calls=3,    # Allow 3 test calls in half-open
)

breaker = CircuitBreaker("external_api", config)

# Use as decorator
@breaker
async def call_external_api():
    return await httpx.get("https://api.example.com")

# Or use as context manager
async with breaker:
    result = await call_external_api()
```

### Structured Logging

Configure structured logging with optional JSON output:

```python
from flowforge import configure_logging, get_logger, ChainLogger

# Configure logging (uses structlog if available)
configure_logging(level="INFO", json_output=False)

# Get a logger
logger = get_logger("my_module")
logger.info("Processing started", company="Apple", step="extract")

# Use ChainLogger for chain-specific logging
chain_logger = ChainLogger("my_chain", "request-123")
chain_logger.step_start("fetch_data")
chain_logger.step_complete("fetch_data", duration_ms=150.5)
```

### Distributed Tracing

FlowForge includes built-in OpenTelemetry tracing that's automatically integrated at the DAG executor layer:

```python
from flowforge import FlowForge, configure_tracing, trace_span, ChainTracer

# Configure tracing (requires opentelemetry packages)
configure_tracing(service_name="my-service", endpoint="http://jaeger:4317")

# Tracing is automatically enabled for all chains
# Each chain execution creates a parent span with child spans for each step
result = await forge.run("my_chain")

# Disable tracing for specific chains (if needed)
executor = forge._executor
executor.enable_tracing = False

# Manual tracing with trace_span context manager
with trace_span("my_operation", {"key": "value"}):
    result = do_something()

# Use ChainTracer for custom chain execution
tracer = ChainTracer("my_chain", "request-123")
with tracer.chain_span(total_steps=3):
    with tracer.step_span("step1"):
        # step execution
        pass
```

### Debug Callbacks

Debug callbacks allow you to inspect context state after each step:

```python
from flowforge import FlowForge, ChainContext

forge = FlowForge(name="my_app")

# Define a debug callback
def on_step_complete(ctx: ChainContext, step_name: str, result: dict):
    print(f"Step {step_name} completed:")
    print(f"  Success: {result['success']}")
    print(f"  Duration: {result['duration_ms']:.2f}ms")
    print(f"  Context keys: {list(ctx.to_dict().get('data', {}).keys())}")

    # Save snapshot to file
    import json
    with open(f"debug_{step_name}.json", "w") as f:
        json.dump({
            "step": step_name,
            "result": result,
            "context": ctx.to_dict(),
        }, f, indent=2, default=str)

# Pass callback to launch/run
result = await forge.launch(
    "my_chain",
    data={"company": "Apple"},
    debug_callback=on_step_complete,
)

# The CLI debug command uses this feature:
# flowforge debug my_chain --company "Apple" --snapshot-dir ./debug_output
```

### LLM Gateway with Resilience

Use the LLM Gateway with built-in retry, circuit breaker, and connection pooling:

```python
from flowforge import LLMGatewayClient, create_managed_client

# Create a managed client (auto-cleanup on process exit)
client = create_managed_client(
    base_url="https://api.openai.com/v1",
    api_key="sk-...",
    timeout=30.0,
    max_retries=3,
    circuit_breaker_enabled=True,
)

# Use as context manager for explicit cleanup
async with client:
    response = await client.complete_async("Hello, world!")

    # Streaming responses
    async for chunk in client.stream_async("Tell me a story"):
        print(chunk, end="")
```

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

### Typed Configuration with Secret Masking

FlowForge provides a typed configuration system with automatic environment variable validation and secret masking:

```python
from flowforge.utils import FlowForgeConfig, get_config, SecretString

# Load configuration from environment variables
config = get_config()

# Access typed values
print(config.llm_model)        # "gpt-4"
print(config.max_parallel)     # 10
print(config.llm_api_key)      # ***REDACTED*** (masked in logs)

# Get actual secret value when needed
api_key = str(config.llm_api_key)  # Returns actual value

# Safe dict for logging (all secrets masked)
safe_config = config.to_safe_dict()
```

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWFORGE_SERVICE_NAME` | `flowforge` | Service name for telemetry |
| `FLOWFORGE_ENV` | `development` | Environment (development/staging/production) |
| `LLM_API_KEY` | - | LLM API key (masked in logs) |
| `LLM_BASE_URL` | `http://localhost:8000` | LLM service URL |
| `LLM_MODEL` | `gpt-4` | Default LLM model |
| `FLOWFORGE_MAX_PARALLEL` | `10` | Max parallel step execution |
| `FLOWFORGE_CACHE_ENABLED` | `true` | Enable response caching |
| `FLOWFORGE_CACHE_TTL_SECONDS` | `300` | Cache TTL |
| `FLOWFORGE_RATE_LIMIT_ENABLED` | `false` | Enable rate limiting |
| `FLOWFORGE_RATE_LIMIT_RPS` | `10.0` | Requests per second |
| `FLOWFORGE_RETRY_MAX` | `3` | Max retry attempts |
| `FLOWFORGE_DEBUG` | `false` | Enable debug mode |
| `FLOWFORGE_DEBUG_SNAPSHOT_DIR` | `.flowforge/snapshots` | Debug snapshot directory |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | OTLP endpoint URL |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `text` | Log format (text/json) |

### External Secret Backends

For production, load secrets from external providers instead of environment variables:

```python
from flowforge.utils import (
    AWSSecretsManagerBackend,
    VaultSecretBackend,
    set_secret_backend,
)

# AWS Secrets Manager
backend = AWSSecretsManagerBackend(
    secret_name="prod/flowforge",
    region_name="us-east-1",
)
set_secret_backend(backend)

# OR HashiCorp Vault
backend = VaultSecretBackend(
    url="https://vault.example.com",
    path="secret/data/flowforge",
)
set_secret_backend(backend)

# Now LLM_API_KEY will be loaded from the secret backend
from flowforge.utils import get_config
config = get_config()
```

### Health Checks

Built-in health checks for operational visibility:

```python
from flowforge.utils import get_health, get_version

# Get health status
health = get_health()
print(health.status)      # "healthy", "degraded", or "unhealthy"
print(health.version)     # "1.0.0"
print(health.checks)      # {"config_loaded": True, "llm_configured": True}

# Get version info
version = get_version()
print(version)  # {"name": "flowforge", "version": "1.0.0", "environment": "development"}
```

Use `flowforge health` in CI/CD pipelines or container health probes:

```bash
# Returns exit code 0 if healthy, 1 otherwise
flowforge health || exit 1
```

### True Fail-Fast Execution

FlowForge implements true fail-fast behavior that immediately cancels all pending tasks when one fails:

```python
# When error_handling="fail_fast" (default):
# - If step A fails after 100ms
# - Steps B, C, D (still running) are CANCELLED immediately
# - Side effects stop right away
# - You don't wait 30s for other tasks to complete

@forge.chain(name="my_chain", error_handling="fail_fast")
class MyChain:
    steps = ["step_a", "step_b", "step_c", "step_d"]

# For "continue" mode, all tasks run to completion:
@forge.chain(name="my_chain", error_handling="continue")
class MyChain:
    steps = ["step_a", "step_b", "step_c", "step_d"]
```

### Graceful Degradation with Partial Success

In "continue" mode, FlowForge tracks partial success so you know exactly what worked:

```python
from flowforge.core.context import ExecutionSummary

# After running a chain with continue mode
result = await forge.run("my_chain")

# Check partial success
if result.get("partial_success"):
    print(f"Completed: {result['completed_steps']}/{result['total_steps']}")
    print(f"Completion rate: {result['completion_rate']}")

# Get detailed step results
for step_result in result["results"]:
    if step_result.get("skipped_reason"):
        print(f"SKIPPED: {step_result['step_name']} - {step_result['skipped_reason']}")
    elif step_result.get("error"):
        print(f"FAILED: {step_result['step_name']} - {step_result['error_type']}")
        print(f"  Traceback: {step_result['error_traceback'][:200]}...")
    else:
        print(f"SUCCESS: {step_result['step_name']}")
```

**Rich Error Metadata:**
- `error_type`: Exception class name (e.g., "ValueError", "TimeoutError")
- `error_traceback`: Full stack trace for debugging
- `retry_count`: Number of retry attempts made
- `skipped_reason`: Why a step was skipped (e.g., "dependency failed: step_b")

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
| `forge.register_resource(name, ...)` | Register a resource for injection |
| `forge.check()` | Validate all definitions |
| `FlowForge.temp_registries(name)` | Context manager for isolated testing |

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

## Testing

FlowForge provides isolated registries for testing:

```python
import pytest
from flowforge import FlowForge

def test_my_chain():
    # Use temp_registries for isolated test
    with FlowForge.temp_registries("test") as forge:
        @forge.step(name="test_step")
        async def test_step(ctx):
            return {"result": "ok"}

        @forge.chain(name="test_chain")
        class TestChain:
            steps = ["test_step"]

        # Run test
        result = asyncio.run(forge.run("test_chain"))
        assert result["success"]
    # Registries automatically cleaned up
```

## License

MIT
