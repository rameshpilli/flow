# AgentOrchestrator

> **A production-grade DAG-based chain orchestration framework for AI/ML pipelines**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status: Beta](https://img.shields.io/badge/status-beta-orange.svg)]()

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
  - [System Architecture Diagram](#system-architecture-diagram)
  - [Core Components](#core-components)
  - [Data Flow](#data-flow)
- [Getting Started](#getting-started)
  - [Installation](#installation)
  - [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
  - [Steps](#steps)
  - [Chains](#chains)
  - [Agents](#agents)
  - [Context](#context)
  - [Middleware](#middleware)
- [Execution Model](#execution-model)
  - [DAG Execution](#dag-execution)
  - [Parallel Execution](#parallel-execution)
  - [Error Handling](#error-handling)
- [Production Features](#production-features)
  - [Resilience](#resilience)
  - [Resumability](#resumability)
  - [Observability](#observability)
- [CLI Reference](#cli-reference)
- [API Reference](#api-reference)
- [Examples](#examples)
- [Configuration](#configuration)
- [FAQ](#faq)

---

## Overview

**AgentOrchestrator** is a Python framework for building and orchestrating AI/ML pipelines. Inspired by [Dagster](https://dagster.io/), it provides a decorator-driven approach to defining data pipelines with automatic dependency resolution, parallel execution, and production-grade resilience.

### What is AgentOrchestrator?

AgentOrchestrator helps you:

1. **Define data pipelines** using simple Python decorators (`@step`, `@chain`, `@agent`)
2. **Orchestrate execution** with automatic dependency resolution and parallel processing
3. **Build resilient systems** with retry logic, circuit breakers, and timeout handling
4. **Manage complexity** through middleware, context scoping, and resource injection

### Use Cases

- **Financial Data Aggregation**: Combine data from multiple sources (SEC filings, news, earnings)
- **Meeting Prep Pipelines**: Generate comprehensive briefing materials
- **RAG Pipelines**: Orchestrate retrieval-augmented generation workflows
- **Multi-Agent Systems**: Coordinate multiple AI agents working together
- **ETL Pipelines**: Extract, transform, and load data with observability

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Decorator-Driven** | Define steps, chains, and agents with simple Python decorators |
| **Automatic DAG Resolution** | Dependencies resolved via topological sort |
| **Parallel Execution** | Independent steps run concurrently |
| **Middleware System** | Pluggable processing hooks (logging, caching, summarization) |
| **Context Management** | Scoped storage (step/chain/global) with thread safety |
| **Resilience** | Retry, circuit breaker, timeout, fail-fast/continue modes |
| **Resumability** | Checkpoint-based resume for failed runs |
| **Observability** | OpenTelemetry tracing, structured logging, metrics |
| **Resource Injection** | Dependency injection for databases, APIs, etc. |
| **CLI** | Full command-line interface for operations |

---

## Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AgentOrchestrator                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌────────────────────────────────────────────────────────────────────────┐    │
│   │                          DECORATOR LAYER                                │    │
│   │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │    │
│   │  │  @ao.step   │    │  @ao.chain  │    │  @ao.agent  │                 │    │
│   │  │  Define     │    │  Compose    │    │  Register   │                 │    │
│   │  │  processing │    │  pipelines  │    │  data       │                 │    │
│   │  │  units      │    │             │    │  sources    │                 │    │
│   │  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                 │    │
│   └─────────┼──────────────────┼──────────────────┼────────────────────────┘    │
│             │                  │                  │                              │
│             ▼                  ▼                  ▼                              │
│   ┌────────────────────────────────────────────────────────────────────────┐    │
│   │                         REGISTRY SYSTEM (Thread-Safe)                   │    │
│   │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │    │
│   │  │  StepRegistry   │  │  ChainRegistry  │  │  AgentRegistry  │         │    │
│   │  │  - name         │  │  - steps list   │  │  - capabilities │         │    │
│   │  │  - dependencies │  │  - error mode   │  │  - fetch()      │         │    │
│   │  │  - produces     │  │  - parallel     │  │  - health()     │         │    │
│   │  └─────────────────┘  └─────────────────┘  └─────────────────┘         │    │
│   └────────────────────────────────────────────────────────────────────────┘    │
│                                      │                                          │
│                                      ▼                                          │
│   ┌────────────────────────────────────────────────────────────────────────┐    │
│   │                            DAG EXECUTOR                                 │    │
│   │                                                                         │    │
│   │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                │    │
│   │   │  Dependency │───▶│  Parallel   │───▶│  Execution  │                │    │
│   │   │  Resolution │    │  Groups     │    │  Engine     │                │    │
│   │   │  (topo-sort)│    │             │    │             │                │    │
│   │   └─────────────┘    └─────────────┘    └─────────────┘                │    │
│   │                                                                         │    │
│   │   Features: Retry | Circuit Breaker | Timeout | Fail-Fast              │    │
│   └────────────────────────────────────────────────────────────────────────┘    │
│                                      │                                          │
│                                      ▼                                          │
│   ┌────────────────────────────────────────────────────────────────────────┐    │
│   │                         MIDDLEWARE STACK                                │    │
│   │                                                                         │    │
│   │   Request ──▶ Logger ──▶ Cache ──▶ RateLimiter ──▶ [Step] ──▶ Response │    │
│   │                              │                         │                │    │
│   │                              └── Summarizer ◀─────────┘                │    │
│   │                              └── TokenManager                           │    │
│   │                              └── Offload (Redis)                        │    │
│   │                              └── Metrics                                │    │
│   └────────────────────────────────────────────────────────────────────────┘    │
│                                      │                                          │
│                                      ▼                                          │
│   ┌────────────────────────────────────────────────────────────────────────┐    │
│   │                          CHAIN CONTEXT                                  │    │
│   │                                                                         │    │
│   │   ┌─────────────────────────────────────────────────────────────────┐  │    │
│   │   │  Scoped Storage                                                  │  │    │
│   │   │  ├── STEP scope   (cleared after step completes)                │  │    │
│   │   │  ├── CHAIN scope  (persists through chain - default)            │  │    │
│   │   │  └── GLOBAL scope (persists across chains)                      │  │    │
│   │   └─────────────────────────────────────────────────────────────────┘  │    │
│   │   ┌─────────────────────────────────────────────────────────────────┐  │    │
│   │   │  Step Results | Token Tracking | Thread Safety                   │  │    │
│   │   └─────────────────────────────────────────────────────────────────┘  │    │
│   └────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. AgentOrchestrator (Entry Point)

The main class that provides decorator registration, chain execution, and resource management.

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(
    name="my_app",           # Unique instance name
    isolated=True,           # Isolated registries (recommended)
    max_parallel=10,         # Max concurrent steps
    default_timeout_ms=30000 # Step timeout
)
```

#### 2. Registry System

Thread-safe registries for all components:

| Registry | Purpose | Key Data |
|----------|---------|----------|
| `StepRegistry` | Processing steps | handler, deps, produces, retry, timeout |
| `ChainRegistry` | Chain definitions | steps list, error handling mode |
| `AgentRegistry` | Data agents | capabilities, fetch method, health check |

#### 3. DAG Executor

Executes chains with optimal parallelism:

```
Level 0: [step_a, step_b, step_c]  ← No dependencies, run in parallel
    │         │         │
    └─────────┼─────────┘
              ▼
Level 1: [step_d]                  ← Depends on a, b, c
              │
              ▼
Level 2: [step_e, step_f]          ← Depends on d, run in parallel
```

#### 4. ChainContext

Shared state across steps with scoped storage:

```python
# STEP scope - temporary, cleared after step
ctx.set("temp", value, scope=ContextScope.STEP)

# CHAIN scope - persists through chain (default)
ctx.set("data", value, scope=ContextScope.CHAIN)

# GLOBAL scope - persists across chains
ctx.set("config", value, scope=ContextScope.GLOBAL)
```

#### 5. Middleware Stack

Pluggable processing hooks:

| Middleware | Purpose |
|------------|---------|
| `LoggerMiddleware` | Structured logging per step |
| `CacheMiddleware` | Response caching with TTL |
| `SummarizerMiddleware` | LLM-based content summarization |
| `TokenManagerMiddleware` | Token budget enforcement |
| `RateLimiterMiddleware` | API rate limiting |
| `OffloadMiddleware` | Large payload offloading to Redis |
| `MetricsMiddleware` | Execution metrics collection |

### Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           CHAIN EXECUTION FLOW                                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   ao.launch("my_chain", initial_data)                                        │
│                    │                                                          │
│                    ▼                                                          │
│   ┌────────────────────────────────────┐                                     │
│   │  1. INPUT VALIDATION               │                                     │
│   │     Pydantic models if defined     │                                     │
│   │     Fail-fast on invalid data      │                                     │
│   └────────────────────────────────────┘                                     │
│                    │                                                          │
│                    ▼                                                          │
│   ┌────────────────────────────────────┐                                     │
│   │  2. CREATE CHAIN CONTEXT           │                                     │
│   │     - Generate request_id          │                                     │
│   │     - Store initial_data           │                                     │
│   │     - Initialize result tracking   │                                     │
│   └────────────────────────────────────┘                                     │
│                    │                                                          │
│                    ▼                                                          │
│   ┌────────────────────────────────────┐                                     │
│   │  3. BUILD EXECUTION DAG            │                                     │
│   │     - Parse step dependencies      │                                     │
│   │     - Detect circular deps         │                                     │
│   │     - Topological sort             │                                     │
│   │     - Group parallel steps         │                                     │
│   └────────────────────────────────────┘                                     │
│                    │                                                          │
│                    ▼                                                          │
│   ┌────────────────────────────────────┐                                     │
│   │  4. EXECUTE STEPS                  │                                     │
│   │                                    │                                     │
│   │     For each step (in order):      │                                     │
│   │     ┌────────────────────────────┐ │                                     │
│   │     │ middleware.before(ctx)     │ │                                     │
│   │     │         ▼                  │ │                                     │
│   │     │ inject resources           │ │                                     │
│   │     │         ▼                  │ │                                     │
│   │     │ step_handler(ctx)          │◀┼── retry on failure                  │
│   │     │         ▼                  │ │   (with exponential backoff)        │
│   │     │ validate output            │ │                                     │
│   │     │         ▼                  │ │                                     │
│   │     │ middleware.after(ctx)      │ │                                     │
│   │     │         ▼                  │ │                                     │
│   │     │ ctx.add_result(StepResult) │ │                                     │
│   │     └────────────────────────────┘ │                                     │
│   │                                    │                                     │
│   │     Parallel steps run concurrently│                                     │
│   └────────────────────────────────────┘                                     │
│                    │                                                          │
│                    ▼                                                          │
│   ┌────────────────────────────────────┐                                     │
│   │  5. RETURN RESULTS                 │                                     │
│   │     - All step outputs             │                                     │
│   │     - Execution metadata           │                                     │
│   │     - Timing information           │                                     │
│   │     - Error details (if any)       │                                     │
│   └────────────────────────────────────┘                                     │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Getting Started

### Installation

```bash
# Basic installation
pip install -e ./agentorchestrator

# With summarization support
pip install -e "./agentorchestrator[summarization]"

# With OpenAI provider
pip install -e "./agentorchestrator[openai]"

# With observability (tracing, structured logging)
pip install -e "./agentorchestrator[observability]"

# Everything
pip install -e "./agentorchestrator[all]"
```

**Dependencies:**

| Package | Version | Purpose |
|---------|---------|---------|
| `pydantic` | >=2.0 | Data validation |
| `httpx` | >=0.25.0 | Async HTTP client |
| `python-dotenv` | >=1.0.0 | Environment variables |

### Quick Start

#### Hello World

```python
from agentorchestrator import AgentOrchestrator

# Create instance
ao = AgentOrchestrator(name="hello")

# Define a step
@ao.step
async def greet(ctx):
    name = ctx.get("name", "World")
    return {"greeting": f"Hello, {name}!"}

# Define a chain
@ao.chain
class HelloChain:
    steps = [greet]

# Run it
import asyncio

async def main():
    result = await ao.launch("HelloChain", {"name": "AgentOrchestrator"})
    print(result["final_output"]["greeting"])  # Hello, AgentOrchestrator!

asyncio.run(main())
```

#### Multi-Step Pipeline

```python
from agentorchestrator import AgentOrchestrator, ChainContext

ao = AgentOrchestrator(name="pipeline", isolated=True)

@ao.step
async def fetch_data(ctx: ChainContext):
    """Step 1: Fetch data"""
    company = ctx.initial_data.get("company", "Unknown")
    data = {"company": company, "revenue": 394_328_000_000}
    ctx.set("company_data", data)
    return data

@ao.step(deps=[fetch_data])
async def process_data(ctx: ChainContext):
    """Step 2: Process (runs after fetch_data)"""
    data = ctx.get("company_data")
    processed = {
        "company": data["company"],
        "revenue_billions": data["revenue"] / 1_000_000_000
    }
    ctx.set("processed", processed)
    return processed

@ao.step(deps=[process_data])
async def generate_report(ctx: ChainContext):
    """Step 3: Generate report (runs after process_data)"""
    processed = ctx.get("processed")
    return {
        "title": f"{processed['company']} Overview",
        "revenue": f"${processed['revenue_billions']:.1f}B"
    }

@ao.chain
class DataPipeline:
    steps = [fetch_data, process_data, generate_report]

# Run
async def main():
    result = await ao.launch("DataPipeline", {"company": "Apple"})
    print(result["final_output"])
    # {'title': 'Apple Overview', 'revenue': '$394.3B'}

asyncio.run(main())
```

---

## Core Concepts

### Steps

Steps are the fundamental processing units. Define them with the `@ao.step` decorator:

```python
@ao.step(
    name="process_data",           # Optional: custom name (defaults to function name)
    deps=["fetch_data"],           # Dependencies: runs after these steps
    produces=["processed_data"],   # Keys this step produces
    retry=3,                       # Retry count on failure
    timeout_ms=30000,              # Timeout in milliseconds
    max_concurrency=5,             # Max parallel instances
)
async def process_data(ctx: ChainContext):
    # Access context
    input_data = ctx.get("raw_data")

    # Process
    result = transform(input_data)

    # Store in context
    ctx.set("processed_data", result)

    # Return output
    return {"processed": True, "count": len(result)}
```

**Step Execution Order:**

```
@ao.step
async def step_a(ctx): ...          # No deps

@ao.step
async def step_b(ctx): ...          # No deps

@ao.step(deps=[step_a, step_b])
async def step_c(ctx): ...          # Waits for a AND b

# Execution:
# step_a ──┐
#          ├──▶ step_c
# step_b ──┘
#
# step_a and step_b run in PARALLEL
# step_c runs AFTER both complete
```

### Chains

Chains compose steps into executable pipelines:

```python
@ao.chain(
    name="my_pipeline",
    error_handling="fail_fast",    # or "continue" to run all steps
)
class MyPipeline:
    steps = [
        "extract",
        "transform",
        "load",
    ]

    # Optional: explicit parallel groups
    parallel_groups = [
        ["extract_a", "extract_b"],  # Run together
        ["transform"],                # Then this
        ["load"],                     # Then this
    ]
```

**Error Handling Modes:**

| Mode | Behavior |
|------|----------|
| `fail_fast` | Stop immediately on first error |
| `continue` | Run all possible steps, collect errors |
| `skip_on_error` | Skip dependent steps on error |

### Agents

Agents are data fetching components:

```python
from agentorchestrator.agents import BaseAgent, AgentResult

@ao.agent(
    name="news_agent",
    capabilities=["search", "sentiment"],
)
class NewsAgent(BaseAgent):

    async def initialize(self):
        """Called once before first use"""
        self.api_key = os.environ.get("NEWS_API_KEY")

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch data for a query"""
        # Your API logic here
        data = await self._call_api(query)

        return AgentResult(
            data=data,
            source="news_api",
            query=query,
            duration_ms=elapsed,
            metadata={"articles_count": len(data)}
        )

    async def health_check(self) -> bool:
        """Return True if healthy"""
        return await self._ping_api()

# Use the agent
agent = ao.get_agent("news_agent")
result = await agent.fetch("Apple earnings", limit=10)
```

### Context

`ChainContext` provides shared state across steps:

```python
@ao.step
async def my_step(ctx: ChainContext):
    # Read initial data
    company = ctx.initial_data.get("company")

    # Read from context
    value = ctx.get("key", default=None)

    # Check existence
    if ctx.has("key"):
        ...

    # Write to context (with scope)
    ctx.set("output", data, scope=ContextScope.CHAIN)

    # Delete from context
    ctx.delete("temporary_key")

    # Access request ID
    request_id = ctx.request_id

    # Access step results
    previous_result = ctx.get_result("previous_step")
```

**Context Scopes:**

```
┌─────────────────────────────────────────────────────────────────┐
│                         CONTEXT SCOPES                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  STEP SCOPE                                                      │
│  ├── Lifecycle: Created at step start, cleared at step end      │
│  ├── Use case: Temporary variables within a step                │
│  └── Example: ctx.set("temp", value, scope=ContextScope.STEP)   │
│                                                                  │
│  CHAIN SCOPE (default)                                           │
│  ├── Lifecycle: Persists throughout chain execution              │
│  ├── Use case: Pass data between steps                          │
│  └── Example: ctx.set("data", value)                            │
│                                                                  │
│  GLOBAL SCOPE                                                    │
│  ├── Lifecycle: Persists across multiple chain executions        │
│  ├── Use case: Configuration, caches, shared state              │
│  └── Example: ctx.set("config", value, scope=ContextScope.GLOBAL)│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Middleware

Middleware intercepts step execution with before/after hooks:

```python
from agentorchestrator import Middleware

class TimingMiddleware(Middleware):
    def __init__(self, priority: int = 100):
        super().__init__(priority=priority)

    async def before(self, ctx, step_name):
        """Called before step execution"""
        ctx.set(f"_start_{step_name}", time.time(), scope=ContextScope.STEP)

    async def after(self, ctx, step_name, result):
        """Called after step execution"""
        start = ctx.get(f"_start_{step_name}")
        elapsed = time.time() - start
        print(f"{step_name}: {elapsed:.2f}s")

    async def on_error(self, ctx, step_name, error):
        """Called when step fails"""
        print(f"{step_name} FAILED: {error}")

# Register middleware
ao.use(TimingMiddleware(priority=50))
```

**Built-in Middleware:**

```python
from agentorchestrator import (
    LoggerMiddleware,
    CacheMiddleware,
    SummarizerMiddleware,
    TokenManagerMiddleware,
)
from agentorchestrator.middleware import (
    RateLimiterMiddleware,
    OffloadMiddleware,
    MetricsMiddleware,
)

# Logging
ao.use(LoggerMiddleware(level="INFO"))

# Caching (5 minute TTL)
ao.use(CacheMiddleware(ttl_seconds=300))

# Token management
ao.use(TokenManagerMiddleware(max_total_tokens=100000))

# Rate limiting
ao.use(RateLimiterMiddleware({
    "fetch_data": {"requests_per_second": 10},
}))
```

---

## Execution Model

### DAG Execution

AgentOrchestrator builds a Directed Acyclic Graph (DAG) from step dependencies:

```
Input: Steps with dependencies

@ao.step                     # fetch_a: no deps
async def fetch_a(ctx): ...

@ao.step                     # fetch_b: no deps
async def fetch_b(ctx): ...

@ao.step                     # fetch_c: no deps
async def fetch_c(ctx): ...

@ao.step(deps=[fetch_a, fetch_b])  # combine: needs a, b
async def combine(ctx): ...

@ao.step(deps=[combine, fetch_c])  # final: needs combine, c
async def final(ctx): ...

Result: Execution DAG

     fetch_a ───────┐
                    ├──▶ combine ───┐
     fetch_b ───────┘               │
                                    ├──▶ final
     fetch_c ───────────────────────┘

Execution Levels:
  Level 0: [fetch_a, fetch_b, fetch_c]  (parallel)
  Level 1: [combine]                     (waits for a, b)
  Level 2: [final]                       (waits for combine, c)
```

### Parallel Execution

Steps without dependencies run concurrently:

```python
@ao.step
async def fetch_sec(ctx):
    await asyncio.sleep(2)  # Simulates 2s API call
    return {"sec": "data"}

@ao.step
async def fetch_news(ctx):
    await asyncio.sleep(2)  # Simulates 2s API call
    return {"news": "data"}

@ao.step
async def fetch_earnings(ctx):
    await asyncio.sleep(2)  # Simulates 2s API call
    return {"earnings": "data"}

@ao.step(deps=[fetch_sec, fetch_news, fetch_earnings])
async def aggregate(ctx):
    return {"aggregated": True}

# Total execution time: ~2s (not 6s)
# Because fetch_sec, fetch_news, fetch_earnings run in PARALLEL
```

**Concurrency Control:**

```python
# Limit concurrent instances of a step
@ao.step(max_concurrency=3)
async def rate_limited_step(ctx):
    # Only 3 instances can run simultaneously
    ...

# Global parallel limit
ao = AgentOrchestrator(
    name="my_app",
    max_parallel=10  # Max 10 steps running at once
)
```

### Error Handling

**Retry with Exponential Backoff:**

```python
@ao.step(retry=3)  # Retry up to 3 times
async def flaky_step(ctx):
    response = await external_api()
    if response.status != 200:
        raise RetryableError("API failed")
    return response.data

# Retry timing: 1s → 2s → 4s (exponential backoff)
```

**Circuit Breaker:**

```
┌────────────────────────────────────────┐
│           CIRCUIT BREAKER              │
├────────────────────────────────────────┤
│                                        │
│    CLOSED ──(5 failures)──▶ OPEN       │
│       ▲                       │        │
│       │                       │ (30s)  │
│       │                       ▼        │
│    (success)◀─────────── HALF_OPEN     │
│                                        │
│  CLOSED: Normal operation              │
│  OPEN: Reject all requests (fail fast) │
│  HALF_OPEN: Allow 1 request to test    │
│                                        │
└────────────────────────────────────────┘
```

```python
from agentorchestrator import CircuitBreaker, CircuitBreakerConfig

config = CircuitBreakerConfig(
    failure_threshold=5,      # Open after 5 failures
    recovery_timeout=30.0,    # Wait 30s before half-open
    half_open_max_calls=3,    # 3 test calls in half-open
)

breaker = CircuitBreaker("external_api", config)

@breaker
async def call_api():
    return await httpx.get("https://api.example.com")
```

---

## Production Features

### Resilience

**Timeout Handling:**

```python
@ao.step(timeout_ms=5000)  # 5 second timeout
async def time_sensitive_step(ctx):
    # Raises TimeoutError if exceeds 5s
    ...
```

**Fail-Fast vs Continue:**

```python
# Fail-fast: Stop on first error
@ao.chain(error_handling="fail_fast")
class FailFastChain:
    steps = [step_a, step_b, step_c]

# Continue: Run all possible steps
@ao.chain(error_handling="continue")
class ResilientChain:
    steps = [step_a, step_b, step_c]
    # If step_a fails, step_b and step_c still run
    # (if they don't depend on step_a)
```

### Resumability

Resume failed chains from the last successful checkpoint:

```python
# Run with checkpointing
result = await ao.launch_resumable(
    "my_chain",
    {"company": "Apple"},
    checkpoint_dir="/tmp/runs"
)

run_id = result["run_id"]
# run_id: "my_chain_2025-01-15_10-30-45_abc123"

# If it fails, resume later
if not result["success"]:
    # Resume from last checkpoint
    resumed = await ao.resume(run_id)

    # Or retry only failed steps
    retried = await ao.retry_failed(run_id)

    # Get partial output from failed run
    partial = await ao.get_partial_output(run_id)
```

**Checkpoint Storage:**

```
┌────────────────────────────────────────────────────────────────┐
│                    CHECKPOINT STRUCTURE                         │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  /tmp/runs/my_chain_2025-01-15_abc123/                         │
│  ├── metadata.json        # Run metadata, status               │
│  ├── context.json         # Serialized ChainContext            │
│  ├── steps/                                                    │
│  │   ├── fetch_data.json      # Step result (completed)        │
│  │   ├── process_data.json    # Step result (completed)        │
│  │   └── generate.json        # Step result (failed)           │
│  └── errors/                                                   │
│      └── generate.json        # Error details                  │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### Observability

**Structured Logging:**

```python
from agentorchestrator import configure_logging, get_logger

configure_logging(level="INFO", json_output=True)
logger = get_logger("my_module")

logger.info("Processing", company="Apple", step="extract")
# {"level": "INFO", "message": "Processing", "company": "Apple", "step": "extract"}
```

**OpenTelemetry Tracing:**

```python
from agentorchestrator import configure_tracing, trace_span

configure_tracing(
    service_name="my-service",
    endpoint="http://jaeger:4317"
)

with trace_span("my_operation", {"key": "value"}):
    result = do_something()
```

**Metrics:**

```python
from agentorchestrator.middleware import MetricsMiddleware

ao.use(MetricsMiddleware(
    export_interval=60,  # Export every 60s
    endpoint="http://prometheus:9090"
))

# Automatically tracks:
# - step_duration_ms
# - step_success_rate
# - chain_duration_ms
# - retry_count
# - error_count
```

---

## CLI Reference

AgentOrchestrator includes a full CLI (`ao` command):

```bash
# Run a chain
ao run my_chain --data '{"company": "Apple"}'

# Run with checkpointing
ao run my_chain --resumable

# Resume a failed run
ao resume <run_id>

# Retry failed steps
ao retry <run_id>

# List runs
ao runs
ao runs --chain my_chain --status failed

# Show run details
ao run-info <run_id>

# Validate definitions
ao check
ao check my_chain

# List registered components
ao list

# Visualize chain DAG
ao graph my_chain
ao graph my_chain --format mermaid

# Health check
ao health
ao health --detailed

# Diagnose issues
ao doctor

# Development mode (auto-reload)
ao dev --watch

# Debug with snapshots
ao debug my_chain --data '{"company": "Apple"}'

# Scaffold new components
ao new agent MyAgent
ao new chain MyChain
ao new project my-app

# Version
ao version
```

**Example Output:**

```bash
$ ao graph my_chain

my_chain
========
  fetch_a ─┬──▶ combine ──▶ final
  fetch_b ─┤
  fetch_c ─┴──────────────────┘

Steps: 5 | Parallel groups: 3
```

```bash
$ ao list

Registered Components:

  Agents (3):
    - news_agent [search, sentiment]
    - sec_agent [filings, forms]
    - earnings_agent [quarterly, annual]

  Steps (8):
    - extract_context → [company_name, ticker]
    - fetch_news (deps: extract_context) → [news_data]
    - fetch_sec (deps: extract_context) → [sec_data]
    - aggregate (deps: fetch_news, fetch_sec) → [aggregated]
    ...

  Chains (2):
    - meeting_prep [8 steps]
    - quick_analysis [4 steps]
```

---

## API Reference

### AgentOrchestrator

```python
class AgentOrchestrator:
    def __init__(
        self,
        name: str,                          # Instance name
        isolated: bool = True,              # Isolated registries
        max_parallel: int = 10,             # Max concurrent steps
        default_timeout_ms: int = 30000,    # Default timeout
        checkpoint_dir: str = None,         # Checkpoint storage path
    ): ...

    # Decorators
    def step(self, name=None, deps=None, produces=None, retry=0,
             timeout_ms=None, max_concurrency=None) -> Callable: ...
    def chain(self, name=None, error_handling="fail_fast") -> Callable: ...
    def agent(self, name=None, capabilities=None) -> Callable: ...

    # Execution
    async def launch(self, chain_name: str, data: dict) -> dict: ...
    async def launch_resumable(self, chain_name: str, data: dict,
                               run_id: str = None) -> dict: ...
    async def resume(self, run_id: str, skip_completed: bool = True) -> dict: ...
    async def retry_failed(self, run_id: str) -> dict: ...

    # Middleware
    def use(self, middleware: Middleware) -> None: ...

    # Resources
    def register_resource(self, name: str, factory: Callable,
                          cleanup: Callable = None) -> None: ...
    def get_resource(self, name: str) -> Any: ...
    async def cleanup_resources(self) -> None: ...

    # Discovery
    def list_agents(self) -> list[str]: ...
    def list_steps(self) -> list[str]: ...
    def list_chains(self) -> list[str]: ...
    def list_defs(self) -> dict: ...
    def get_agent(self, name: str) -> BaseAgent: ...

    # Validation
    def check(self, chain_name: str = None) -> None: ...
    def graph(self, chain_name: str, format: str = "ascii") -> str: ...
```

### ChainContext

```python
class ChainContext:
    request_id: str                    # Unique request identifier
    initial_data: dict                 # Data passed to launch()

    # Data operations
    def get(self, key: str, default=None) -> Any: ...
    def set(self, key: str, value: Any,
            scope: ContextScope = ContextScope.CHAIN) -> None: ...
    def has(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...

    # Results
    def get_result(self, step_name: str) -> StepResult: ...
    def add_result(self, result: StepResult) -> None: ...

    # Serialization
    def to_dict(self) -> dict: ...
    def clone(self) -> ChainContext: ...
```

### BaseAgent

```python
class BaseAgent(ABC):
    def __init__(self, config: dict = None): ...

    async def initialize(self) -> None: ...
    async def cleanup(self) -> None: ...
    async def health_check(self) -> bool: ...

    @abstractmethod
    async def fetch(self, query: str, **kwargs) -> AgentResult: ...

@dataclass
class AgentResult:
    data: Any                          # Fetched data
    source: str                        # Source identifier
    query: str                         # Original query
    duration_ms: float = 0.0           # Execution time
    metadata: dict = None              # Additional metadata
    error: str = None                  # Error message if failed

    @property
    def success(self) -> bool:
        return self.error is None
```

### Middleware

```python
class Middleware(ABC):
    def __init__(self, priority: int = 100): ...

    async def before(self, ctx: ChainContext, step_name: str) -> None: ...
    async def after(self, ctx: ChainContext, step_name: str,
                    result: StepResult) -> None: ...
    async def on_error(self, ctx: ChainContext, step_name: str,
                       error: Exception) -> None: ...
```

---

## Examples

### 1. Simple Data Pipeline

```python
from agentorchestrator import AgentOrchestrator, ChainContext

ao = AgentOrchestrator(name="simple", isolated=True)

@ao.step
async def extract(ctx: ChainContext):
    ctx.set("raw", [1, 2, 3, 4, 5])
    return {"extracted": True}

@ao.step(deps=[extract])
async def transform(ctx: ChainContext):
    raw = ctx.get("raw")
    ctx.set("transformed", [x * 2 for x in raw])
    return {"transformed": True}

@ao.step(deps=[transform])
async def load(ctx: ChainContext):
    data = ctx.get("transformed")
    return {"sum": sum(data), "count": len(data)}

@ao.chain
class ETLPipeline:
    steps = [extract, transform, load]

# Run
result = await ao.launch("ETLPipeline", {})
print(result["final_output"])  # {'sum': 30, 'count': 5}
```

### 2. Parallel Data Fetching

```python
@ao.step
async def fetch_sec(ctx):
    ticker = ctx.initial_data["ticker"]
    data = await sec_api.get_filings(ticker)
    ctx.set("sec_data", data)
    return {"fetched": "sec"}

@ao.step
async def fetch_news(ctx):
    company = ctx.initial_data["company"]
    data = await news_api.search(company)
    ctx.set("news_data", data)
    return {"fetched": "news"}

@ao.step
async def fetch_earnings(ctx):
    ticker = ctx.initial_data["ticker"]
    data = await earnings_api.get_quarterly(ticker)
    ctx.set("earnings_data", data)
    return {"fetched": "earnings"}

@ao.step(deps=[fetch_sec, fetch_news, fetch_earnings])
async def aggregate(ctx):
    return {
        "sec": ctx.get("sec_data"),
        "news": ctx.get("news_data"),
        "earnings": ctx.get("earnings_data"),
    }

@ao.chain
class ParallelFetch:
    steps = [fetch_sec, fetch_news, fetch_earnings, aggregate]

# fetch_sec, fetch_news, fetch_earnings run in PARALLEL
# aggregate waits for all three
```

### 3. Custom Agent Integration

```python
from agentorchestrator.agents import BaseAgent, AgentResult

@ao.agent(
    name="capiq",
    capabilities=["financials", "estimates", "ownership"]
)
class CapIQAgent(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        data_type = kwargs.get("data_type", "financials")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.capitaliq.com/v1/{data_type}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"identifier": query},
            )

        return AgentResult(
            data=response.json(),
            source="capiq",
            query=query,
            metadata={"data_type": data_type}
        )

# Use in steps
@ao.step
async def fetch_financials(ctx):
    agent = ao.get_agent("capiq")
    result = await agent.fetch("AAPL", data_type="financials")
    ctx.set("financials", result.data)
    return {"success": result.success}
```

### 4. With Middleware

```python
from agentorchestrator import (
    AgentOrchestrator,
    LoggerMiddleware,
    CacheMiddleware,
    TokenManagerMiddleware,
)

ao = AgentOrchestrator(name="production", isolated=True)

# Add middleware stack
ao.use(LoggerMiddleware(level="INFO"))
ao.use(CacheMiddleware(ttl_seconds=300))
ao.use(TokenManagerMiddleware(max_total_tokens=100000))

# All steps now have logging, caching, and token tracking
@ao.step
async def my_step(ctx):
    # Automatically logged
    # Results cached for 5 minutes
    # Token usage tracked
    return {"result": "data"}
```

### 5. Complete Meeting Prep Chain

See [examples/04_meeting_prep_chain.py](examples/04_meeting_prep_chain.py) for a full production example:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MEETING PREP CHAIN                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   INPUT: { company: "Apple", meeting_date: "2025-01-15" }               │
│                                                                          │
│   extract_context                                                        │
│         │                                                                │
│         ├──► fetch_sec_filings ──────┐                                  │
│         ├──► fetch_news ──────────────┼──► aggregate ──► generate_prep  │
│         ├──► fetch_earnings ─────────┤                                  │
│         └──► fetch_transcripts ──────┘                                  │
│                                                                          │
│   OUTPUT: { meeting_prep: "..." }                                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### Environment Variables

```bash
# LLM Gateway
LLM_GATEWAY_URL=http://localhost:8000
LLM_MODEL_NAME=gpt-4
LLM_TEMPERATURE=0.0
LLM_MAX_TOKENS=4096
LLM_TIMEOUT=60.0

# Authentication
LLM_OAUTH_ENDPOINT=https://auth.example.com/token
LLM_CLIENT_ID=your-client-id
LLM_CLIENT_SECRET=your-secret
# OR
LLM_API_KEY=sk-...

# Redis (for payload offloading)
REDIS_URL=redis://localhost:6379
REDIS_TTL_SECONDS=86400

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json  # or "text"

# Performance
MAX_PARALLEL_STEPS=10
DEFAULT_TIMEOUT_MS=30000

# Summarization
SUMMARIZER_STRATEGY=map_reduce  # or "stuff", "refine"
SUMMARIZER_CHUNK_SIZE=4000
SUMMARIZER_MAX_TOKENS=2000
```

### Config File

Create a `.env` file or use `agentorchestrator/config.py`:

```python
from agentorchestrator.config import Config

config = Config(
    llm_gateway_url="http://localhost:8000",
    llm_model="gpt-4",
    redis_url="redis://localhost:6379",
    log_level="INFO",
)
```

---

## FAQ

### General

**Q: How is AgentOrchestrator different from Dagster?**

A: AgentOrchestrator is a lightweight alternative focused on AI/ML pipelines:
- No UI (CLI + programmatic API)
- Async-first (Python 3.10+)
- Simpler dependency model
- Built-in LLM features (summarization, token management)
- Optimized for real-time chains, not batch jobs

**Q: Can I use AgentOrchestrator with LangChain?**

A: Yes! AgentOrchestrator complements LangChain:
```python
from langchain.llms import OpenAI

@ao.step
async def llm_step(ctx):
    llm = OpenAI()
    response = llm("Summarize: " + ctx.get("text"))
    return {"summary": response}
```

### Execution

**Q: How do I handle slow steps?**

A: Use timeouts and consider these patterns:
```python
# Set timeout
@ao.step(timeout_ms=60000)  # 60 second timeout
async def slow_step(ctx):
    ...

# Or make it async with progress
@ao.step
async def slow_step(ctx):
    for i in range(10):
        await do_chunk(i)
        await asyncio.sleep(0)  # Yield control
```

**Q: How do I debug failed chains?**

A: Use the CLI debug mode:
```bash
ao debug my_chain --data '{"company": "Apple"}'
```

Or programmatically:
```python
result = await ao.launch("my_chain", data, debug=True)
print(result["debug_info"])
```

### Performance

**Q: How do I optimize parallel execution?**

A:
1. Minimize dependencies between steps
2. Group independent fetches together
3. Use `max_concurrency` for rate-limited APIs
4. Consider `OffloadMiddleware` for large payloads

**Q: What's the memory footprint?**

A: Minimal by default. For large data:
- Use `OffloadMiddleware` to store payloads in Redis
- Use `ContextScope.STEP` for temporary data
- Implement streaming for very large datasets

---

## Project Structure

```
agentorchestrator/
├── __init__.py              # Public API exports
├── cli.py                   # Command-line interface
├── config.py                # Configuration management
│
├── core/
│   ├── orchestrator.py      # AgentOrchestrator class
│   ├── context.py           # ChainContext & scopes
│   ├── dag.py               # DAG builder & executor
│   ├── registry.py          # Component registries
│   ├── decorators.py        # @step, @agent, @chain
│   ├── resources.py         # Dependency injection
│   ├── context_store.py     # Redis offloading
│   ├── run_store.py         # Resumability checkpoints
│   ├── validation.py        # Input/output contracts
│   └── visualize.py         # DAG visualization
│
├── middleware/
│   ├── base.py              # Middleware base class
│   ├── logger.py            # Structured logging
│   ├── cache.py             # Response caching
│   ├── summarizer.py        # LLM summarization
│   ├── token_manager.py     # Token budgets
│   ├── rate_limiter.py      # Rate limiting
│   ├── offload.py           # Payload offloading
│   └── metrics.py           # Execution metrics
│
├── agents/
│   ├── base.py              # BaseAgent, ResilientAgent
│   └── data_agents.py       # Pre-built agents
│
├── utils/
│   ├── circuit_breaker.py   # Circuit breaker
│   ├── retry.py             # Retry decorators
│   ├── logging.py           # Logging utilities
│   └── tracing.py           # OpenTelemetry
│
├── testing/
│   ├── fixtures.py          # Pytest fixtures
│   ├── mocks.py             # Mock implementations
│   └── assertions.py        # Test assertions
│
└── docs/
    ├── ARCHITECTURE.md      # This document
    ├── QUICKSTART.md        # Getting started
    ├── API.md               # API reference
    └── TROUBLESHOOTING.md   # Common issues
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/your-org/agentorchestrator/issues)
- **Documentation**: [docs/](agentorchestrator/docs/)
- **Examples**: [examples/](examples/)

---

*Built with Python 3.10+ | Async-first | Production-ready*
