# FlowForge User Guide

A comprehensive guide to building data pipelines and AI chains with FlowForge.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [CLI Usage](#cli-usage)
5. [Core Concepts](#core-concepts)
6. [Building Your First Chain](#building-your-first-chain)
7. [Working with Agents](#working-with-agents)
8. [Middleware System](#middleware-system)
9. [Domain-Specific Summarization](#domain-specific-summarization)
10. [Production Features](#production-features)
11. [Configuration Management](#configuration-management)
12. [Health Checks and Monitoring](#health-checks-and-monitoring)
13. [Using the Built-in CMPT Chain](#using-the-built-in-cmpt-chain)
14. [Adding Custom Agents (CapIQ Example)](#adding-custom-agents-capiq-example)
15. [API Reference](#api-reference)
16. [Best Practices](#best-practices)
17. [Testing](#testing)

---

## Introduction

FlowForge is a DAG-based chain orchestration framework inspired by Dagster patterns. It provides:

- **Decorator-driven registration** - Define agents, steps, and chains with simple decorators
- **Automatic dependency resolution** - Dependencies are resolved and executed in the optimal order
- **Parallel execution** - Independent steps run concurrently for maximum performance
- **Explicit parallel groups** - Define custom execution ordering with `parallel_groups`
- **Per-step concurrency limits** - Control parallelism with `max_concurrency`
- **Middleware system** - Plug in caching, logging, summarization, and token management
- **Domain-aware summarization** - Smart content reduction for different data types
- **Clean validation APIs** - Validate your definitions before running
- **CLI tool** - Run chains, validate, visualize DAGs from command line
- **Production resilience** - Circuit breakers, retry, connection pooling
- **Observability** - OTel-compliant structured logging, distributed tracing
- **Resource management** - Dependency injection with lifecycle management
- **True fail-fast** - Immediate task cancellation on first failure
- **Typed configuration** - Environment variable validation with secret masking
- **Health endpoints** - Built-in health checks and version info

### Who Is This For?

- Data engineers building financial data pipelines
- AI/ML teams creating LLM-powered workflows
- Backend developers integrating multiple data sources
- Anyone needing to orchestrate complex multi-step processes

---

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd ChainServer

# Install dependencies
pip install -r requirements.txt

# Install FlowForge in development mode
pip install -e .
```

### Dependencies

```txt
# Core
pydantic>=2.0
httpx

# LangChain (for summarization)
langchain-core
langchain-text-splitters
langchain-openai      # Optional: for OpenAI summarization
langchain-anthropic   # Optional: for Claude summarization

# Token counting
tiktoken

# Optional: Observability
structlog             # For structured logging
opentelemetry-api     # For distributed tracing
opentelemetry-sdk
opentelemetry-exporter-otlp

# Optional: Development
watchdog              # For hot reload dev mode
pytest
pytest-asyncio
```

---

## Quick Start

### Minimal Example (3 Steps, 30 Lines)

```python
import asyncio
from flowforge import FlowForge, ChainContext

# 1. Create FlowForge instance
forge = FlowForge(name="quickstart")

# 2. Define steps with decorators
@forge.step(name="extract", produces=["data"])
async def extract(ctx: ChainContext):
    ctx.set("data", {"message": "Hello"})
    return {"data": ctx.get("data")}

@forge.step(name="transform", dependencies=["extract"], produces=["result"])
async def transform(ctx: ChainContext):
    data = ctx.get("data")
    ctx.set("result", f"Transformed: {data['message']}")
    return {"result": ctx.get("result")}

@forge.step(name="load", dependencies=["transform"])
async def load(ctx: ChainContext):
    return {"final": ctx.get("result")}

# 3. Define chain
@forge.chain(name="etl_chain")
class ETLChain:
    steps = ["extract", "transform", "load"]

# 4. Run it!
async def main():
    result = await forge.run("etl_chain")
    print(f"Success: {result['success']}")
    print(f"Output: {result['context']['data']['result']}")

asyncio.run(main())
```

**Output:**
```
Success: True
Output: Transformed: Hello
```

---

## CLI Usage

FlowForge includes a command-line interface for common operations.

### Running Chains

```bash
# Run a chain with initial data
flowforge run my_pipeline --data '{"company": "Apple"}'

# Run with a specific module
flowforge run my_pipeline --module myapp.chains

# Run with verbose output
flowforge run my_pipeline --verbose
```

### Debug Mode

Debug mode runs a chain with context snapshots after each step, making it easy to troubleshoot issues:

```bash
# Run in debug mode with context snapshots
flowforge debug my_pipeline --data '{"company": "Apple"}'

# Specify custom snapshot directory
flowforge debug my_pipeline --snapshot-dir ./debug_output

# Snapshots are saved as JSON files:
# ./snapshots/my_pipeline_20250128_143022/
#   ├── 00_summary.json      # Final execution summary
#   ├── 01_step_extract.json # Context after extract step
#   ├── 02_step_transform.json
#   └── 03_step_load.json
```

Each snapshot includes:
- Step name and execution status
- Context data at that point
- Timing information
- Error details (if any)

### Validation

```bash
# Check all definitions for errors
flowforge check

# Check a specific module
flowforge check --module myapp.chains
```

### Listing Definitions

```bash
# List all registered agents, steps, and chains
flowforge list

# Show detailed information
flowforge list --verbose
```

### DAG Visualization

```bash
# Show ASCII visualization
flowforge graph my_pipeline

# Generate Mermaid diagram syntax
flowforge graph my_pipeline --format mermaid

# Output to file
flowforge graph my_pipeline --format mermaid --output dag.md
```

### Scaffolding

Generate new agents and chains from templates:

```bash
# Create a new agent
flowforge new agent MyCustomAgent

# Create a new chain
flowforge new chain MyPipeline

# Specify output directory
flowforge new agent MyAgent --output ./myapp/agents/
```

### Development Mode

Hot reload mode for development:

```bash
# Watch for file changes and auto-restart
flowforge dev --watch

# Specify port for dev server
flowforge dev --watch --port 8000

# Watch specific directory
flowforge dev --watch --path ./myapp/
```

### Health and Configuration

```bash
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

---

## Core Concepts

### The FlowForge Instance

The `FlowForge` class is your entry point. It manages:
- Agent registration
- Step registration
- Chain registration
- Middleware
- Resource management and cleanup
- Execution

```python
from flowforge import FlowForge

forge = FlowForge(
    name="my_app",
    version="1.0.0",
    max_parallel=5,           # Max concurrent steps
    default_timeout_ms=60000, # 60 second timeout
    isolated=True,            # Isolated registries (default)
)

# Note: By default, FlowForge uses isolated registries to prevent
# state bleed between different instances or tests.

# Resource cleanup with timeout (prevents hanging)
async with forge:
    result = await forge.run("my_chain")
# Resources automatically cleaned up with 30s timeout
```

### Module-Level Decorators

For quick scripts, you can use module-level decorators that delegate to a global forge instance:

```python
from flowforge.core.decorators import agent, step, chain

# These register to the global FlowForge instance
@step
async def my_step(ctx):
    return {"done": True}

@step(name="custom_step", deps=[my_step], produces=["output"])
async def another_step(ctx):
    return {"output": "result"}

@chain
class MyChain:
    steps = ["my_step", "custom_step"]

# Access the global forge to run
from flowforge.core.forge import get_forge
result = await get_forge().run("mychain")
```

### Context (ChainContext)

The `ChainContext` is shared state that flows between steps:

```python
from flowforge import ChainContext

# In a step function:
async def my_step(ctx: ChainContext):
    # Read from context
    input_data = ctx.get("input_key", default_value)

    # Write to context
    ctx.set("output_key", processed_data)

    # Access request metadata
    request_id = ctx.request_id

    return {"output_key": processed_data}
```

### Steps

Steps are the building blocks of your chain:

```python
@forge.step(
    name="my_step",                    # Unique identifier
    dependencies=["previous_step"],    # Steps that must run first
    produces=["output_key"],           # Keys this step writes to context
    timeout_ms=30000,                  # Optional: step-specific timeout
    max_concurrency=5,                 # Optional: max parallel instances
    resources=["db", "llm"],           # Optional: resources to inject
)
async def my_step(ctx: ChainContext, db=None, llm=None):
    # Your logic here (resources injected if specified)
    return {"output_key": result}
```

### Chains

Chains group steps together:

```python
@forge.chain(
    name="my_chain",
    version="1.0",
    description="Does something useful",
)
class MyChain:
    steps = ["step_a", "step_b", "step_c"]
```

### Explicit Parallel Groups

Override automatic dependency-based ordering with explicit parallel groups:

```python
@forge.chain(
    name="my_pipeline",
    parallel_groups=[
        ["extract"],                              # Group 1: runs first
        ["fetch_news", "fetch_filings"],          # Group 2: runs in parallel
        ["combine"],                              # Group 3: runs after group 2
    ]
)
class MyPipeline:
    steps = ["extract", "fetch_news", "fetch_filings", "combine"]
```

When `parallel_groups` is specified:
- Steps within each group run in parallel
- Groups execute sequentially in order
- Dependencies are still validated (a step's deps must be in previous groups)

### Agents

Agents wrap data sources (APIs, databases, MCP servers):

```python
from flowforge.agents import BaseAgent, AgentResult

@forge.agent(
    name="my_agent",
    capabilities=["search", "fetch"],
)
class MyAgent(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        # Call your data source
        data = await call_api(query)
        return AgentResult(
            data=data,
            source="my_agent",
            query=query,
        )
```

---

## Building Your First Chain

### Step 1: Plan Your Flow

```
Input Request
     │
     ▼
┌─────────────┐
│  Extract    │ ─── Get raw data
└─────────────┘
     │
     ▼
┌─────────────┐
│  Transform  │ ─── Process data
└─────────────┘
     │
     ▼
┌─────────────┐
│    Load     │ ─── Output result
└─────────────┘
     │
     ▼
Final Output
```

### Step 2: Define Steps

```python
from flowforge import FlowForge, ChainContext

forge = FlowForge(name="data_pipeline")

@forge.step(name="extract", produces=["raw_data"])
async def extract(ctx: ChainContext):
    """Extract data from source"""
    company = ctx.get("company_name", "Unknown")

    raw_data = {
        "company": company,
        "revenue": 1000000,
        "employees": 500,
    }
    ctx.set("raw_data", raw_data)
    return {"raw_data": raw_data}


@forge.step(name="transform", dependencies=["extract"], produces=["metrics"])
async def transform(ctx: ChainContext):
    """Transform raw data into metrics"""
    raw = ctx.get("raw_data", {})

    metrics = {
        "revenue_per_employee": raw["revenue"] / raw["employees"],
        "company": raw["company"],
    }
    ctx.set("metrics", metrics)
    return {"metrics": metrics}


@forge.step(name="load", dependencies=["transform"], produces=["report"])
async def load(ctx: ChainContext):
    """Generate final report"""
    metrics = ctx.get("metrics", {})

    report = f"Report for {metrics['company']}: ${metrics['revenue_per_employee']:.2f}/employee"
    ctx.set("report", report)
    return {"report": report}
```

### Step 3: Define Chain

```python
@forge.chain(name="data_pipeline")
class DataPipeline:
    steps = ["extract", "transform", "load"]
```

### Step 4: Validate

```python
# Check for issues
forge.check()

# List all definitions
print(forge.list_agents())
print(forge.list_steps())
print(forge.list_chains())

# Visualize DAG
print(forge.visualize_chain("data_pipeline"))
```

### Step 5: Run

```python
async def main():
    result = await forge.run(
        "data_pipeline",
        initial_data={"company_name": "Acme Corp"}
    )

    if result["success"]:
        print(f"Report: {result['context']['data']['report']}")
    else:
        print(f"Error: {result['error']}")

asyncio.run(main())
```

---

## Working with Agents

### Built-in Agent Types

FlowForge provides base classes for common patterns:

```python
from flowforge.agents import BaseAgent, AgentResult
```

### Creating a Custom Agent

```python
@forge.agent(
    name="stock_api",
    version="1.0",
    capabilities=["quote", "history"],
)
class StockAPIAgent(BaseAgent):
    """Agent for fetching stock data"""

    def __init__(self, config=None):
        super().__init__(config)
        self.api_key = config.get("api_key") if config else None

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        import time
        start = time.perf_counter()

        # Your API call logic
        ticker = query.upper()
        data = {
            "ticker": ticker,
            "price": 150.25,
            "change": 2.5,
            "volume": 1000000,
        }

        duration = (time.perf_counter() - start) * 1000
        return AgentResult(
            data=data,
            source="stock_api",
            query=query,
            duration_ms=duration,
        )
```

### Using Agents in Steps

```python
@forge.step(name="fetch_stock", produces=["stock_data"])
async def fetch_stock(ctx: ChainContext):
    ticker = ctx.get("ticker", "AAPL")

    # Get agent instance
    agent = forge.get_agent("stock_api")

    # Call agent
    result = await agent.fetch(ticker)

    if result.success:
        ctx.set("stock_data", result.data)
    else:
        ctx.set("stock_data", {"error": result.error})

    return {"stock_data": ctx.get("stock_data")}
```

### Parallel Agent Execution

```python
import asyncio

@forge.step(name="fetch_all", produces=["all_data"])
async def fetch_all_data(ctx: ChainContext):
    company = ctx.get("company_name")

    # Get agents
    sec_agent = forge.get_agent("sec_filing")
    news_agent = forge.get_agent("news")
    earnings_agent = forge.get_agent("earnings")

    # Execute in parallel
    results = await asyncio.gather(
        sec_agent.fetch(company),
        news_agent.fetch(company),
        earnings_agent.fetch(company),
    )

    all_data = {
        "sec": results[0].data,
        "news": results[1].data,
        "earnings": results[2].data,
    }
    ctx.set("all_data", all_data)
    return {"all_data": all_data}
```

---

## Middleware System

Middleware intercepts step execution for cross-cutting concerns.

### Available Middleware

| Middleware | Purpose |
|------------|---------|
| `LoggerMiddleware` | Log step execution, timing, context |
| `CacheMiddleware` | Cache step results with TTL |
| `SummarizerMiddleware` | Summarize large outputs |
| `TokenManagerMiddleware` | Track token usage |

### Adding Middleware

```python
from flowforge import (
    FlowForge,
    LoggerMiddleware,
    CacheMiddleware,
    SummarizerMiddleware,
    TokenManagerMiddleware,
    create_domain_aware_middleware,
)

forge = FlowForge(name="my_app")

# Add logging
forge.use_middleware(LoggerMiddleware(level=logging.INFO))

# Add caching (5 minute TTL)
forge.use_middleware(CacheMiddleware(ttl_seconds=300))

# Add token tracking
forge.use_middleware(TokenManagerMiddleware(max_total_tokens=100000))

# Add domain-aware summarization
forge.use_middleware(create_domain_aware_middleware(
    llm=my_llm,
    max_tokens=4000,
))
```

### Custom Middleware

```python
from flowforge.middleware import Middleware
from flowforge.core.context import ChainContext, StepResult

class TimingMiddleware(Middleware):
    """Track detailed timing for each step"""

    def __init__(self):
        super().__init__(priority=10)  # Low number = runs first
        self.timings = {}

    async def before(self, ctx: ChainContext, step_name: str):
        """Called before step execution"""
        import time
        ctx.set(f"_timing_start_{step_name}", time.perf_counter())

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult):
        """Called after step execution"""
        import time
        start = ctx.get(f"_timing_start_{step_name}")
        self.timings[step_name] = (time.perf_counter() - start) * 1000

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception):
        """Called on step failure"""
        print(f"Step {step_name} failed: {error}")

# Use it
forge.use_middleware(TimingMiddleware())
```

---

## Domain-Specific Summarization

When processing financial data, generic summarization loses important details. FlowForge provides **domain-aware prompts** that know what to extract.

### Quick Setup

```python
from flowforge import create_domain_aware_middleware

# Create middleware with your LLM
middleware = create_domain_aware_middleware(
    llm=my_llm,      # LangChain LLM instance
    max_tokens=4000,
)
forge.use_middleware(middleware)
```

### What Each Domain Extracts

| Content Type | Key Information Extracted |
|--------------|---------------------------|
| `sec_filing` | Revenue, margins, forward guidance, risk factors, segment data |
| `earnings` | EPS actual vs estimate, beat/miss, YoY growth, guidance |
| `news` | Event type, date, sentiment, analyst opinions |
| `transcripts` | Management statements, targets, Q&A insights, tone |
| `pricing` | P/E, EV/EBITDA, price targets, peer comparisons |

### Manual Configuration

```python
from flowforge import SummarizerMiddleware, LangChainSummarizer

middleware = SummarizerMiddleware(
    summarizer=LangChainSummarizer(llm=my_llm),
    max_tokens=4000,
    step_content_types={
        "fetch_sec_filings": "sec_filing",
        "fetch_earnings": "earnings",
        "fetch_news": "news",
        "fetch_transcripts": "transcripts",
    },
)
```

### Direct Usage in Code

```python
from flowforge import LangChainSummarizer

summarizer = LangChainSummarizer(llm=my_llm)

# Generic summarization
summary = await summarizer.summarize(long_text, max_tokens=3000)

# Domain-specific summarization
summary = await summarizer.summarize(
    sec_filing_text,
    max_tokens=3000,
    content_type="sec_filing"  # Uses SEC-specific extraction prompts
)
```

---

## Production Features

FlowForge includes enterprise-grade features for production deployments.

### Circuit Breaker

Protect your chain from cascading failures when external services are down:

```python
from flowforge import CircuitBreaker, CircuitBreakerConfig, get_circuit_breaker

# Get or create a named circuit breaker
breaker = get_circuit_breaker("external_api")

# Or create with custom config
config = CircuitBreakerConfig(
    failure_threshold=5,      # Open after 5 consecutive failures
    recovery_timeout=30.0,    # Wait 30s before trying again
    half_open_max_calls=3,    # Allow 3 test calls in half-open state
)
breaker = CircuitBreaker("my_service", config)

# Use as decorator
@breaker
async def call_api():
    return await httpx.get("https://api.example.com/data")

# Use as context manager
async with breaker:
    result = await call_api()

# Check state
print(breaker.state)  # CircuitState.CLOSED, OPEN, or HALF_OPEN
```

**Circuit Breaker States:**
- **CLOSED**: Normal operation, requests pass through
- **OPEN**: After threshold failures, all requests fail immediately
- **HALF_OPEN**: After recovery timeout, limited test requests allowed

### Retry with Backoff

Configure automatic retries with exponential backoff:

```python
from flowforge import retry, async_retry, RetryPolicy

# Simple retry decorator
@async_retry(max_attempts=3, delay=1.0, backoff=2.0)
async def fetch_data():
    return await api_call()

# Or use RetryPolicy for more control
policy = RetryPolicy(
    max_attempts=5,
    initial_delay=0.5,
    max_delay=30.0,
    backoff_multiplier=2.0,
    retryable_exceptions=(httpx.HTTPError, TimeoutError),
)

@async_retry(policy=policy)
async def resilient_fetch():
    return await api_call()
```

### Resource Management

Register resources with automatic lifecycle management and dependency injection:

```python
from flowforge import FlowForge, ResourceScope

forge = FlowForge(name="my_app")

# Register a singleton resource (one instance for app lifetime)
forge.register_resource(
    "config",
    resource=load_config(),  # Pass instance directly
)

# Register with factory and cleanup
forge.register_resource(
    "db",
    factory=lambda: create_db_pool(),
    cleanup=lambda pool: pool.close(),
    scope=ResourceScope.SINGLETON,
)

# Register async resource
forge.register_resource(
    "cache",
    factory=create_redis_client,  # async factory auto-detected
    cleanup=lambda c: c.close(),
)

# Register with dependencies
forge.register_resource(
    "user_service",
    factory=lambda: UserService(),
    dependencies=["db", "cache"],  # Initialized first
)

# Inject into steps
@forge.step(name="process", resources=["db", "cache"])
async def process(ctx, db, cache):
    data = await db.query("SELECT ...")
    await cache.set("key", data)
    return {"processed": True}
```

**Resource Scopes:**
- `SINGLETON`: One instance for entire app lifetime
- `CHAIN`: New instance per chain execution
- `STEP`: New instance per step execution

### Structured Logging

Configure structured logging with optional JSON output:

```python
from flowforge import configure_logging, get_logger, LogContext, ChainLogger

# Configure at startup
configure_logging(
    level="INFO",      # DEBUG, INFO, WARNING, ERROR
    json_output=False, # Set True for production JSON logs
)

# Get a logger
logger = get_logger("my_module")

# Log with structured context
logger.info("Processing started", company="Apple", step="extract")
logger.error("API failed", error=str(e), retry_count=3)

# Use LogContext for request-scoped logging
with LogContext(request_id="req-123", chain="cmpt"):
    logger.info("Inside context")  # Includes request_id, chain

# Use ChainLogger for chain execution
chain_logger = ChainLogger("my_chain", "request-123")
chain_logger.chain_start()
chain_logger.step_start("fetch_data")
chain_logger.step_complete("fetch_data", duration_ms=150.5)
chain_logger.step_error("transform", error=str(e))
chain_logger.chain_complete(total_ms=1250.0, success=True)
```

### Distributed Tracing

FlowForge includes built-in OpenTelemetry tracing that's automatically integrated at the DAG executor layer:

```python
from flowforge import FlowForge, configure_tracing, get_tracer, trace_span, ChainTracer

# Configure at startup (requires opentelemetry packages)
configure_tracing(
    service_name="my-service",
    endpoint="http://jaeger:4317",  # OTLP endpoint
)

# Tracing is automatic for all chain executions
# Each chain creates a parent span with child spans for each step
forge = FlowForge(name="my_app")
result = await forge.run("my_chain")  # Automatically traced

# Get a tracer for custom operations
tracer = get_tracer("my_module")

# Create spans with context manager
with trace_span("my_operation", {"key": "value"}):
    result = do_something()

# Use ChainTracer for custom chain execution
chain_tracer = ChainTracer("my_chain", "request-123")
with chain_tracer.chain_span(total_steps=3):
    with chain_tracer.step_span("step1", agent="news"):
        # step execution with automatic timing
        pass
```

### Debug Callbacks

Debug callbacks let you inspect context state after each step, useful for troubleshooting and development:

```python
from flowforge import FlowForge, ChainContext

forge = FlowForge(name="my_app")

# Define a debug callback
def on_step_complete(ctx: ChainContext, step_name: str, result: dict):
    print(f"Step {step_name}:")
    print(f"  Success: {result['success']}")
    print(f"  Duration: {result['duration_ms']:.2f}ms")
    if result.get('error'):
        print(f"  Error: {result['error']}")

    # Save context snapshot
    import json
    snapshot = {
        "step": step_name,
        "result": result,
        "context_keys": list(ctx.to_dict().get("data", {}).keys()),
    }
    with open(f"debug_{step_name}.json", "w") as f:
        json.dump(snapshot, f, indent=2, default=str)

# Pass callback when running chains
result = await forge.launch(
    "my_chain",
    data={"company": "Apple"},
    debug_callback=on_step_complete,
)

# The CLI debug command uses this feature internally:
# flowforge debug my_chain --company "Apple" --snapshot-dir ./debug_output
```

**Debug callback signature:**
```python
def callback(ctx: ChainContext, step_name: str, result: dict) -> None:
    # result contains:
    # - success: bool
    # - output: dict | None
    # - duration_ms: float
    # - error: str | None
    # - error_type: str | None
    # - retry_count: int
    pass
```

### LLM Gateway with Resilience

The LLM Gateway includes built-in resilience features:

```python
from flowforge import LLMGatewayClient, create_managed_client

# Create a managed client (auto-cleanup on process exit)
client = create_managed_client(
    base_url="https://api.openai.com/v1",
    api_key="sk-...",
    timeout=30.0,
    max_retries=3,
    circuit_breaker_enabled=True,  # Built-in circuit breaker
)

# Use as context manager (recommended)
async with client:
    # Synchronous completion
    response = client.complete("Summarize this: ...")

    # Async completion
    response = await client.complete_async("Hello, world!")

    # Streaming response
    async for chunk in client.stream_async("Tell me a story"):
        print(chunk, end="", flush=True)

# Connection pooling is automatic
# - Shared httpx clients with keepalive
# - Configurable connection limits
# - Automatic cleanup on process exit
```

### Testing with Isolated Registries

Use isolated registries for testing:

```python
import pytest
from flowforge import FlowForge

def test_my_chain():
    # Use temp_registries for fully isolated test
    with FlowForge.temp_registries("test") as forge:
        @forge.step(name="test_step")
        async def test_step(ctx):
            return {"result": "ok"}

        @forge.chain(name="test_chain")
        class TestChain:
            steps = ["test_step"]

        # Run test
        import asyncio
        result = asyncio.run(forge.run("test_chain"))
        assert result["success"]

    # Registries automatically cleaned up after context exit
```

### Registry Strict Mode

Prevent accidental component overwrites:

```python
from flowforge.core.registry import get_step_registry

registry = get_step_registry()

# Default: silently overwrites
registry.register_step("my_step", handler1)
registry.register_step("my_step", handler2)  # Overwrites

# Strict mode: raises error if exists
registry.register_step("my_step", handler3, strict=True)
# ValueError: Component 'my_step' already registered. Use strict=False to overwrite.
```

### Resource Cleanup with Timeout

Prevent indefinite hanging during cleanup:

```python
from flowforge import FlowForge

forge = FlowForge(name="my_app")

# Register resource with potentially slow cleanup
forge.register_resource(
    "db_pool",
    factory=create_db_pool,
    cleanup=lambda pool: pool.close(),
)

# Async context manager uses 30s default timeout
async with forge:
    result = await forge.run("my_chain")
# Cleanup runs with timeout

# Manual cleanup with custom timeout
await forge.cleanup_resources(timeout_seconds=60.0)

# Handle timeout explicitly
try:
    await forge.cleanup_resources(timeout_seconds=5.0)
except asyncio.TimeoutError:
    logger.error("Cleanup timed out - some resources may not be freed")
```

### True Fail-Fast Execution

FlowForge implements true fail-fast behavior - when one task fails, all pending tasks are **immediately cancelled**:

```python
# OLD behavior (most frameworks):
# asyncio.gather(..., return_exceptions=True) waits for ALL tasks
# Even if task 1 fails in 100ms, you wait for tasks 2-5 (maybe 30s each)
# Side effects keep running!

# NEW behavior (FlowForge):
# - Task 1 fails after 100ms
# - Tasks 2, 3, 4, 5 are CANCELLED immediately
# - Total time: ~100ms, not 30+ seconds
# - No unwanted side effects

@forge.chain(name="my_chain", error_handling="fail_fast")
class MyChain:
    steps = ["step_a", "step_b", "step_c", "step_d"]
```

**Why this matters:**
- API calls stop immediately (no wasted quota)
- Database writes don't continue after failure
- You get errors faster in CI/CD pipelines
- Resource cleanup happens promptly

### Graceful Degradation (Continue Mode)

For multi-agent workflows where partial success is acceptable, use continue mode:

```python
@forge.chain(name="data_pipeline", error_handling="continue")
class DataPipeline:
    steps = ["fetch_news", "fetch_sec", "fetch_earnings", "aggregate"]

# Run the chain
result = await forge.run("data_pipeline", {"company": "Apple"})

# Check partial success
if result["success"]:
    print("All steps succeeded!")
elif result.get("partial_success"):
    print(f"Partial success: {result['completion_rate']}% completed")

    # Examine individual step results
    for step_result in result["results"]:
        if step_result["error"]:
            print(f"  {step_result['step_name']}: FAILED - {step_result['error']}")
        elif step_result.get("skipped_reason"):
            print(f"  {step_result['step_name']}: SKIPPED - {step_result['skipped_reason']}")
        else:
            print(f"  {step_result['step_name']}: SUCCESS")
```

### Rich Error Metadata

Each step result includes detailed error information for debugging:

```python
from flowforge.core.context import StepResult, ExecutionSummary

# StepResult includes:
# - step_name: str
# - output: Any
# - duration_ms: float
# - error: Exception | None
# - error_type: str | None (e.g., "ValueError", "TimeoutError")
# - error_traceback: str | None (full stack trace)
# - retry_count: int (how many retries were attempted)
# - skipped_reason: str | None (why the step was skipped)

# ExecutionSummary provides aggregate stats:
summary = ExecutionSummary(
    chain_name="my_chain",
    request_id="req-123",
    total_steps=4,
)

# After execution:
print(summary.completed_steps)   # 2
print(summary.failed_steps)      # 1
print(summary.skipped_steps)     # 1
print(summary.completion_rate)   # 50.0

# Helper methods
successful = summary.get_successful_steps()  # List[StepResult]
failed = summary.get_failed_steps()          # List[StepResult]
skipped = summary.get_skipped_steps()        # List[StepResult]
```

---

## Configuration Management

FlowForge provides a typed configuration system with automatic validation and secret masking.

### Loading Configuration

```python
from flowforge.utils import FlowForgeConfig, get_config, set_config

# Load from environment variables (lazy, cached)
config = get_config()

# Access typed values
print(config.llm_model)           # "gpt-4"
print(config.max_parallel)        # 10
print(config.llm_timeout_ms)      # 30000
print(config.environment)         # "development"

# Secrets are automatically masked
print(config.llm_api_key)         # ***REDACTED***
print(config.llm_api_key.get_masked(4))  # ***sk-1234

# Get actual value when needed (for API calls)
actual_key = str(config.llm_api_key)

# Access nested configuration
print(config.cache.ttl_seconds)       # 300
print(config.rate_limit.enabled)      # False
print(config.retry_policy.max_retries)  # 3
```

### External Secret Backends

For production deployments, use external secret backends instead of environment variables:

```python
from flowforge.utils import (
    FlowForgeConfig,
    AWSSecretsManagerBackend,
    VaultSecretBackend,
    EnvSecretBackend,
)

# AWS Secrets Manager
aws_backend = AWSSecretsManagerBackend(
    secret_name="flowforge/prod",
    region_name="us-east-1",
    cache_ttl_seconds=300,  # Cache secrets for 5 minutes
)
config = FlowForgeConfig.from_env(secret_backend=aws_backend)

# HashiCorp Vault
vault_backend = VaultSecretBackend(
    url="https://vault.example.com",
    token="hvs.xxxxx",  # Or use VAULT_TOKEN env var
    path="secret/data/flowforge",
)
config = FlowForgeConfig.from_env(secret_backend=vault_backend)

# Environment variables (default)
env_backend = EnvSecretBackend()
config = FlowForgeConfig.from_env(secret_backend=env_backend)
```

The secret backend is used to resolve any `ConfigField` marked as `secret=True`:

```python
# LLM_API_KEY will be fetched from the secret backend
print(config.llm_api_key)  # ***REDACTED*** (masked in logs)
actual = str(config.llm_api_key)  # Actual value for API calls
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWFORGE_SERVICE_NAME` | `flowforge` | Service name for telemetry |
| `FLOWFORGE_VERSION` | `1.0.0` | Service version |
| `FLOWFORGE_ENV` | `development` | Environment (dev/staging/prod) |
| `LLM_API_KEY` | - | LLM API key (secret, masked) |
| `LLM_BASE_URL` | `http://localhost:8000` | LLM service URL |
| `LLM_MODEL` | `gpt-4` | Default LLM model |
| `LLM_TIMEOUT_MS` | `30000` | LLM request timeout |
| `LLM_MAX_RETRIES` | `3` | Max retry attempts |
| `FLOWFORGE_MAX_PARALLEL` | `10` | Max parallel steps |
| `FLOWFORGE_DEFAULT_TIMEOUT_MS` | `30000` | Default step timeout |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | OTLP endpoint URL |
| `OTEL_SERVICE_NAME` | - | OTel service name |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `text` | Log format (text/json) |
| `FLOWFORGE_DEBUG` | `false` | Debug mode |

### Secret Masking

The `SecretString` class automatically masks secrets in logs and repr:

```python
from flowforge.utils import SecretString

api_key = SecretString("sk-1234567890abcdef")

# Safe for logging
print(api_key)              # ***REDACTED***
print(repr(api_key))        # ***REDACTED***
print(f"Key: {api_key}")    # Key: ***REDACTED***

# Show last N chars for debugging
print(api_key.get_masked(4))  # ***cdef

# Get actual value when needed
actual = str(api_key)       # "sk-1234567890abcdef"
actual = api_key.value      # "sk-1234567890abcdef"
```

### Safe Configuration Export

```python
# Get config as dict with all secrets masked (safe for logging)
safe_dict = config.to_safe_dict()
print(safe_dict)
# {
#     "service_name": "flowforge",
#     "llm_api_key": "***REDACTED***",
#     "llm_base_url": "http://localhost:8000",
#     ...
# }

# Use in health endpoints, logs, etc.
logger.info("Starting with config", extra=safe_dict)
```

### Fail-Fast Validation

Configuration errors are caught early:

```python
from flowforge.utils import FlowForgeConfig, ConfigError

try:
    config = FlowForgeConfig.from_env()
except ConfigError as e:
    print(f"Configuration error: {e}")
    # Configuration validation failed:
    #   - Required configuration 'LLM_API_KEY' is missing
```

---

## Health Checks and Monitoring

FlowForge provides built-in health checks for operational visibility.

### Health Status API

```python
from flowforge.utils import get_health, get_version, HealthStatus

# Get health status
health = get_health()

print(health.status)       # "healthy", "degraded", or "unhealthy"
print(health.version)      # "1.0.0"
print(health.environment)  # "development"
print(health.checks)       # {"config_loaded": True, "llm_configured": True}

# As dict (for JSON APIs)
health_dict = health.to_dict()
```

### Version Info

```python
version = get_version()
print(version)
# {
#     "name": "flowforge",
#     "version": "1.0.0",
#     "environment": "development"
# }
```

### CLI Health Check

Use in CI/CD pipelines or container health probes:

```bash
# Returns exit code 0 if healthy, 1 otherwise
flowforge health

# JSON output for parsing
flowforge health --json

# Example in Dockerfile
HEALTHCHECK --interval=30s --timeout=3s \
  CMD flowforge health || exit 1
```

### Health Check Statuses

| Status | Meaning |
|--------|---------|
| `healthy` | All checks passed |
| `degraded` | Some non-critical checks failed |
| `unhealthy` | Critical checks failed |

### Built-in Checks

| Check | What it validates |
|-------|-------------------|
| `config_loaded` | Configuration loaded successfully |
| `llm_configured` | LLM API key is set |
| `otel_configured` | OTel endpoint set (if enabled) |

### Custom Health Checks

Add custom checks for your services:

```python
from flowforge.utils import get_health, HealthStatus

def get_app_health() -> HealthStatus:
    health = get_health()

    # Add custom checks
    health.checks["database"] = check_database_connection()
    health.checks["redis"] = check_redis_connection()
    health.checks["external_api"] = check_external_api()

    # Recalculate status
    if not health.checks["database"]:
        health.status = "unhealthy"
    elif not all(health.checks.values()):
        health.status = "degraded"

    return health
```

---

## Using the Built-in CMPT Chain

FlowForge includes a pre-built Client Meeting Prep (CMPT) chain.

### Basic Usage

```python
from flowforge.chains import CMPTChain

# Create chain instance
chain = CMPTChain()

# Validate
chain.check()

# Visualize
chain.graph("ascii")

# Run
result = await chain.run(
    corporate_company_name="Apple Inc",
    meeting_datetime="2025-01-15T10:00:00Z",
    rbc_employee_email="john.doe@company.com",
    corporate_client_email="jane.smith@apple.com",
)

# Access results
print(result.success)
print(result.context_builder)          # Stage 1: Company info, temporal context
print(result.content_prioritization)   # Stage 2: Prioritized sources, subqueries
print(result.response_builder)         # Stage 3: Agent results, final content
```

### User Overrides

Users can override computed/extracted values in Stage 1 (Context Builder). This is useful when:
- The earnings calendar API is unavailable
- You know the correct fiscal quarter/year
- You want to skip API calls for faster testing
- You need to correct mismatched company data

#### Override Fields

| Field | Description | Example |
|-------|-------------|---------|
| `ticker` | Override ticker symbol | `"AAPL"` |
| `company_cik` | Override SEC CIK number | `"0000320193"` |
| `industry` | Override industry classification | `"Technology"` |
| `sector` | Override business sector | `"Consumer Electronics"` |
| `fiscal_quarter` | Override fiscal quarter | `"Q1"`, `"Q2"`, `"Q3"`, `"Q4"` |
| `fiscal_year` | Override fiscal year | `"2025"`, `"FY2025"` |
| `next_earnings_date` | Override next earnings date | `"2025-01-30"` |
| `news_lookback_days` | Override news lookback period (1-365) | `90` |
| `filing_quarters` | Override SEC filing lookback (1-20) | `12` |
| `rbc_persona_name` | Override RBC employee name | `"John Smith"` |
| `rbc_persona_role` | Override RBC employee role | `"Senior Analyst"` |
| `client_persona_name` | Override client contact name | `"Jane Doe"` |
| `client_persona_role` | Override client contact role | `"CFO"` |
| `skip_earnings_calendar_api` | Skip earnings calendar API call | `True` |
| `skip_company_lookup` | Skip company lookup API call | `True` |

#### Usage Example

```python
from flowforge.services.models import ChainRequest, ChainRequestOverrides

# Create request with user overrides
request = ChainRequest(
    corporate_company_name="Apple Inc",
    meeting_datetime="2025-02-15",
    rbc_employee_email="john.doe@rbc.com",

    # User overrides - these take precedence over API-extracted values
    overrides=ChainRequestOverrides(
        ticker="AAPL",                    # Override extracted ticker
        fiscal_quarter="Q1",              # Override to Q1 (instead of computed)
        fiscal_year="2025",               # Override fiscal year
        next_earnings_date="2025-01-30",  # Override earnings date
        news_lookback_days=90,            # Extended news lookback
        filing_quarters=12,               # More filing history
        skip_earnings_calendar_api=True,  # Skip the earnings API call
    ),
)

# Run the chain - overrides are applied automatically
result = await chain.run(request)

# The context_builder output will use override values
print(result.context_builder["ticker"])  # "AAPL"
print(result.context_builder["temporal_context"]["fiscal_quarter"])  # "1"
```

#### Skip API Calls

When developing or testing, you can skip external API calls entirely:

```python
request = ChainRequest(
    corporate_company_name="Test Company",
    meeting_datetime="2025-06-01",
    overrides=ChainRequestOverrides(
        # Provide required data directly
        ticker="TEST",
        industry="Technology",
        fiscal_quarter="Q2",

        # Skip API calls
        skip_company_lookup=True,         # Don't call company matching API
        skip_earnings_calendar_api=True,  # Don't call earnings calendar API
    ),
)
```

#### Override Priority

Overrides are applied in this order:
1. API extracts data (company lookup, earnings calendar, LDAP, ZoomInfo)
2. User overrides are applied on top of extracted data
3. If `skip_*` flags are set, those APIs are not called at all

### CMPT Chain Flow

```
ChainRequest (with optional overrides)
     │
     ▼
┌─────────────────────────────────────────────┐
│ Stage 1: Context Builder                    │
│ - Extract company info (ticker, industry)   │
│ - Extract temporal context (earnings date)  │
│ - Extract personas (RBC, client)            │
│ - ✨ Apply user overrides                   │
└─────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────┐
│ Stage 2: Content Prioritization             │
│ - Prioritize sources (SEC, News, Earnings)  │
│ - Generate subqueries for each agent        │
│ - Apply grid config (lookback periods)      │
└─────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────┐
│ Stage 3: Response Builder                   │
│ - Execute agents in parallel                │
│ - Extract financial metrics                 │
│ - Generate strategic analysis               │
│ - Build final prepared content              │
└─────────────────────────────────────────────┘
     │
     ▼
ChainResponse
├── context_builder: {...}
├── content_prioritization: {...}
├── response_builder: {...}
└── prepared_content: "# Meeting Prep..."
```

---

## Adding Custom Agents (CapIQ Example)

This example shows how to add a Capital IQ agent and chain it with existing flows.

### Step 1: Define the CapIQ Agent

```python
from flowforge import FlowForge, ChainContext
from flowforge.agents import BaseAgent, AgentResult
import httpx

forge = FlowForge(name="enhanced_pipeline")

@forge.agent(
    name="capiq",
    version="1.0",
    description="Capital IQ data agent for financial metrics",
    capabilities=["financials", "estimates", "ownership", "events"],
)
class CapIQAgent(BaseAgent):
    """
    Agent for fetching data from S&P Capital IQ API.

    Capabilities:
    - financials: Historical financial statements
    - estimates: Analyst estimates and consensus
    - ownership: Institutional ownership data
    - events: Corporate events (M&A, dividends)
    """

    def __init__(self, config=None):
        super().__init__(config)
        self.base_url = "https://api.capitaliq.com/v1"
        self.api_key = config.get("api_key") if config else None

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch data from Capital IQ.

        Args:
            query: Company identifier (ticker or CIQ ID)
            **kwargs:
                data_type: "financials" | "estimates" | "ownership" | "events"
                periods: Number of periods to fetch
                metrics: List of specific metrics

        Returns:
            AgentResult with Capital IQ data
        """
        import time
        start = time.perf_counter()

        data_type = kwargs.get("data_type", "financials")
        periods = kwargs.get("periods", 4)
        metrics = kwargs.get("metrics", ["revenue", "ebitda", "net_income"])

        try:
            # In production, make real API call
            # data = await self._call_capiq_api(query, data_type, periods, metrics)

            # Mock data for demonstration
            data = self._get_mock_data(query, data_type, periods, metrics)

            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=data,
                source="capiq",
                query=query,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source="capiq",
                query=query,
                duration_ms=duration,
                error=str(e),
            )

    def _get_mock_data(self, query: str, data_type: str, periods: int, metrics: list):
        """Generate mock data for testing"""
        if data_type == "financials":
            return {
                "company": query,
                "periods": [
                    {"period": "Q4 2024", "revenue": 119.6e9, "ebitda": 42.3e9, "net_income": 33.9e9},
                    {"period": "Q3 2024", "revenue": 94.9e9, "ebitda": 31.2e9, "net_income": 24.5e9},
                    {"period": "Q2 2024", "revenue": 85.8e9, "ebitda": 28.1e9, "net_income": 21.4e9},
                    {"period": "Q1 2024", "revenue": 90.8e9, "ebitda": 30.5e9, "net_income": 23.6e9},
                ][:periods],
            }
        elif data_type == "estimates":
            return {
                "company": query,
                "eps_estimate": 2.35,
                "eps_actual": 2.40,
                "revenue_estimate": 95.0e9,
                "revenue_actual": 94.9e9,
                "analyst_count": 42,
            }
        elif data_type == "ownership":
            return {
                "company": query,
                "institutional_ownership": 0.72,
                "top_holders": [
                    {"name": "Vanguard", "shares": 1.3e9, "pct": 0.08},
                    {"name": "BlackRock", "shares": 1.1e9, "pct": 0.07},
                ],
            }
        elif data_type == "events":
            return {
                "company": query,
                "upcoming_events": [
                    {"type": "earnings", "date": "2025-01-30"},
                    {"type": "dividend", "date": "2025-02-14"},
                ],
            }
        return {}

    async def _call_capiq_api(self, query: str, data_type: str, periods: int, metrics: list):
        """
        Make actual API call to Capital IQ.

        Production implementation:
        ```python
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/{data_type}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "identifier": query,
                    "periods": periods,
                    "metrics": metrics,
                },
            )
            response.raise_for_status()
            return response.json()
        ```
        """
        raise NotImplementedError("Implement with real API credentials")
```

### Step 2: Create Steps Using CapIQ

```python
@forge.step(
    name="fetch_capiq_financials",
    produces=["capiq_financials"],
)
async def fetch_capiq_financials(ctx: ChainContext):
    """Fetch financial statements from Capital IQ"""
    company = ctx.get("company_name", "")
    ticker = ctx.get("ticker", "")

    agent = forge.get_agent("capiq")
    result = await agent.fetch(
        ticker or company,
        data_type="financials",
        periods=8,
        metrics=["revenue", "ebitda", "net_income", "eps"],
    )

    ctx.set("capiq_financials", result.data)
    return {"capiq_financials": result.data}


@forge.step(
    name="fetch_capiq_estimates",
    produces=["capiq_estimates"],
)
async def fetch_capiq_estimates(ctx: ChainContext):
    """Fetch analyst estimates from Capital IQ"""
    ticker = ctx.get("ticker", "")

    agent = forge.get_agent("capiq")
    result = await agent.fetch(
        ticker,
        data_type="estimates",
    )

    ctx.set("capiq_estimates", result.data)
    return {"capiq_estimates": result.data}


@forge.step(
    name="fetch_capiq_ownership",
    produces=["capiq_ownership"],
)
async def fetch_capiq_ownership(ctx: ChainContext):
    """Fetch ownership data from Capital IQ"""
    ticker = ctx.get("ticker", "")

    agent = forge.get_agent("capiq")
    result = await agent.fetch(
        ticker,
        data_type="ownership",
    )

    ctx.set("capiq_ownership", result.data)
    return {"capiq_ownership": result.data}
```

### Step 3: Chain CapIQ with Other Steps

```python
@forge.step(
    name="aggregate_financial_data",
    dependencies=["fetch_capiq_financials", "fetch_capiq_estimates", "fetch_sec_filings"],
    produces=["aggregated_financials"],
)
async def aggregate_financial_data(ctx: ChainContext):
    """Combine CapIQ data with SEC filings"""
    capiq_fin = ctx.get("capiq_financials", {})
    capiq_est = ctx.get("capiq_estimates", {})
    sec_data = ctx.get("sec_filings", {})

    aggregated = {
        "source_capiq": {
            "financials": capiq_fin,
            "estimates": capiq_est,
        },
        "source_sec": sec_data,
        "combined_metrics": {
            "eps_beat": (
                capiq_est.get("eps_actual", 0) > capiq_est.get("eps_estimate", 0)
            ),
            "latest_revenue": capiq_fin.get("periods", [{}])[0].get("revenue"),
        },
    }
    ctx.set("aggregated_financials", aggregated)
    return {"aggregated_financials": aggregated}


@forge.step(
    name="generate_report",
    dependencies=["aggregate_financial_data", "fetch_capiq_ownership"],
    produces=["final_report"],
)
async def generate_report(ctx: ChainContext):
    """Generate final report with all data"""
    aggregated = ctx.get("aggregated_financials", {})
    ownership = ctx.get("capiq_ownership", {})
    company = ctx.get("company_name", "Unknown")

    report = {
        "company": company,
        "financial_summary": aggregated.get("combined_metrics", {}),
        "ownership_summary": {
            "institutional": ownership.get("institutional_ownership", 0),
            "top_holders": ownership.get("top_holders", [])[:5],
        },
        "generated_at": "2025-01-15T10:00:00Z",
    }
    ctx.set("final_report", report)
    return {"final_report": report}
```

### Step 4: Define the Complete Chain

```python
@forge.chain(
    name="enhanced_meeting_prep",
    version="2.0",
    description="Meeting prep with Capital IQ integration",
)
class EnhancedMeetingPrepChain:
    """
    Enhanced meeting prep chain that combines:
    - Context extraction (company, temporal)
    - Capital IQ financials, estimates, ownership
    - SEC filings
    - News
    - Final aggregation and report generation

    Flow:
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  extract_context ─────────────────────────────────────────────┐ │
    │       │                                                       │ │
    │       ├─► fetch_capiq_financials ──┐                          │ │
    │       ├─► fetch_capiq_estimates ───┼─► aggregate_financial ───┤ │
    │       ├─► fetch_sec_filings ───────┘                          │ │
    │       │                                                       │ │
    │       ├─► fetch_capiq_ownership ───────────────────────┐      │ │
    │       │                                                 │      │ │
    │       └─► fetch_news ──────────────────────────────────┼──────┤ │
    │                                                         │      │ │
    │                         generate_report ◄──────────────┘      │ │
    │                              │                                 │ │
    │                              ▼                                 │ │
    │                       Final Report                             │ │
    └─────────────────────────────────────────────────────────────────┘
    """

    steps = [
        # Stage 1: Context
        "extract_context",

        # Stage 2: Data fetching (parallel)
        "fetch_capiq_financials",
        "fetch_capiq_estimates",
        "fetch_capiq_ownership",
        "fetch_sec_filings",
        "fetch_news",

        # Stage 3: Aggregation
        "aggregate_financial_data",

        # Stage 4: Report
        "generate_report",
    ]
```

### Step 5: Run the Enhanced Chain

```python
async def main():
    # Validate
    forge.check()

    # Visualize
    print(forge.visualize_chain("enhanced_meeting_prep"))

    # Run
    result = await forge.run(
        "enhanced_meeting_prep",
        initial_data={
            "company_name": "Apple Inc",
            "ticker": "AAPL",
            "meeting_datetime": "2025-01-15T10:00:00Z",
        },
    )

    if result["success"]:
        report = result["context"]["data"]["final_report"]
        print(f"Company: {report['company']}")
        print(f"EPS Beat: {report['financial_summary']['eps_beat']}")
        print(f"Institutional Ownership: {report['ownership_summary']['institutional']:.1%}")
    else:
        print(f"Error: {result['error']}")

asyncio.run(main())
```

### Complete CapIQ Integration File

Save this as `examples/capiq_integration.py`:

```python
"""
FlowForge Example: Capital IQ Integration

Demonstrates:
1. Creating a custom CapIQ agent
2. Defining steps that use the agent
3. Chaining with other data sources
4. Running the complete pipeline
"""

import asyncio
from flowforge import FlowForge, ChainContext
from flowforge.agents import BaseAgent, AgentResult

# Full implementation as shown above...

if __name__ == "__main__":
    asyncio.run(main())
```

---

## API Reference

### FlowForge Class

```python
class FlowForge:
    def __init__(
        name: str,
        version: str = "0.1.0",
        max_parallel: int = 10,
        default_timeout_ms: int = 30000,
        isolated: bool = True,  # Use isolated registries (default)
    )

    # Decorators
    def agent(name, version, capabilities, description) -> Decorator
    def step(name, dependencies, produces, timeout_ms, max_concurrency, resources) -> Decorator
    def chain(name, version, description, parallel_groups) -> Decorator

    # Management
    def use_middleware(middleware: Middleware) -> None
    def list_agents() -> List[str]
    def list_steps() -> List[str]
    def list_chains() -> List[str]
    def get_agent(name: str) -> BaseAgent

    # Resources
    def register_resource(name, resource=None, factory=None, cleanup=None, dependencies=None) -> None
    async def get_resource(name: str) -> Any

    # Validation
    def check() -> None  # Raises on invalid definitions
    def visualize_chain(name: str) -> str  # ASCII DAG

    # Execution
    async def run(chain_name: str, initial_data: dict = None) -> dict

    # Context managers
    @classmethod
    def temp_registries(cls, name: str) -> FlowForge  # For isolated testing
    def __enter__(self) -> FlowForge
    async def __aenter__(self) -> FlowForge
```

### ChainContext Class

```python
class ChainContext:
    request_id: str

    def set(key: str, value: Any, scope: ContextScope = CHAIN) -> None
    def get(key: str, default: Any = None) -> Any
    def keys() -> List[str]
    def to_dict() -> dict

    # Step lifecycle
    def enter_step(step_name: str) -> Token  # Returns contextvar token
    def exit_step(token: Token = None) -> None  # Pass token for proper cleanup

    # Results
    def add_result(result: StepResult) -> None
    def get_result(step_name: str) -> StepResult
    @property
    def last_result() -> StepResult
    @property
    def results() -> List[StepResult]
```

### AgentResult Class

```python
@dataclass
class AgentResult:
    data: Any                    # The fetched data
    source: str                  # Agent name
    query: str                   # Original query
    duration_ms: float = 0.0     # Execution time
    error: Optional[str] = None  # Error message if failed
    metadata: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.error is None
```

---

## Best Practices

### 1. Name Steps Clearly

```python
# Good
@forge.step(name="fetch_sec_filings")
@forge.step(name="extract_company_info")
@forge.step(name="aggregate_financial_metrics")

# Avoid
@forge.step(name="step1")
@forge.step(name="do_stuff")
```

### 2. Always Define `produces`

```python
# Good - explicit output keys
@forge.step(name="fetch", produces=["raw_data", "metadata"])
async def fetch(ctx):
    ctx.set("raw_data", data)
    ctx.set("metadata", meta)
    return {"raw_data": data, "metadata": meta}
```

### 3. Use Middleware for Cross-Cutting Concerns

```python
# Don't repeat logging/caching in every step
# Use middleware instead
forge.use_middleware(LoggerMiddleware())
forge.use_middleware(CacheMiddleware(ttl_seconds=300))
```

### 4. Handle Errors Gracefully

```python
@forge.step(name="fetch_data")
async def fetch_data(ctx):
    try:
        agent = forge.get_agent("data_source")
        result = await agent.fetch(query)
        if result.success:
            ctx.set("data", result.data)
        else:
            ctx.set("data", {"error": result.error, "fallback": True})
    except Exception as e:
        ctx.set("data", {"error": str(e), "fallback": True})
    return {"data": ctx.get("data")}
```

### 5. Use Domain-Specific Summarization

```python
# For financial data, use content-aware summarization
forge.use_middleware(create_domain_aware_middleware(
    llm=my_llm,
    max_tokens=4000,
))
```

### 6. Validate Before Running

```python
# Always check your definitions first
forge.check()  # Raises if issues found

# Then run
result = await forge.run("my_chain")
```

---

## Troubleshooting

### "Step not found"

```python
# Make sure step is defined before chain
@forge.step(name="my_step")  # Define first
async def my_step(ctx): ...

@forge.chain(name="my_chain")  # Then reference
class MyChain:
    steps = ["my_step"]
```

### "Circular dependency detected"

```python
# Check your dependencies don't form a cycle
# A -> B -> C -> A  # BAD

# Use visualize_chain to debug
print(forge.visualize_chain("my_chain"))
```

### "Agent not registered"

```python
# Make sure agent is decorated
@forge.agent(name="my_agent")  # Required!
class MyAgent(BaseAgent):
    ...

# Then get it
agent = forge.get_agent("my_agent")
```

---

## Further Reading

- [FLOW_GUIDE.md](FLOW_GUIDE.md) - Detailed technical documentation
- [examples/quickstart.py](../examples/quickstart.py) - Minimal example
- [examples/meeting_prep_chain.py](../examples/meeting_prep_chain.py) - Full CMPT example
- [examples/custom_agent_example.py](../examples/custom_agent_example.py) - Custom agents

---

*FlowForge - Building AI chains, one step at a time.*
