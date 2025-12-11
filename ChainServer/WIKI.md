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
  - [Summarization](#summarization)
  - [Token Management](#token-management)
  - [Rate Limiting & Circuit Breakers](#rate-limiting--circuit-breakers)
  - [Context Store (Redis Offloading)](#context-store-redis-offloading)
  - [Health Checks](#health-checks)
  - [Input/Output Validation](#inputoutput-validation)
  - [Observability](#observability)
  - [Plugin System](#plugin-system)
- [Middleware Reference](#middleware-reference)
- [CLI Reference](#cli-reference)
  - [Scaffolding Commands](#scaffolding-commands)
- [API Reference](#api-reference)
- [Examples](#examples)
- [Configuration](#configuration)
- [FAQ](#faq)
- [Architecture Diagrams](#architecture-diagrams)
- [Framework Comparison](#framework-comparison)
- [Go Crazy: What You Can Build](#go-crazy-what-you-can-build)
- [Quick Reference: Pattern → Features](#quick-reference-pattern--features)
- [The AgentOrchestrator Advantage](#the-agentorchestrator-advantage)

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

### Summarization

AgentOrchestrator includes a powerful summarization system for managing large outputs from agents and steps. This is critical when dealing with LLM context limits.

**How Summarization Works:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SUMMARIZATION FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Agent Output (e.g., 10,000 tokens)                                        │
│       │                                                                     │
│       ▼                                                                     │
│   ┌────────────────────┐                                                    │
│   │ Token Count Check  │  Uses tiktoken (or ~4 chars/token estimate)       │
│   └─────────┬──────────┘                                                    │
│             │                                                               │
│    ┌────────┴────────┐                                                      │
│    │                 │                                                      │
│    ▼                 ▼                                                      │
│ ≤ max_tokens     > max_tokens                                               │
│ (pass through)        │                                                     │
│                       ▼                                                     │
│               ┌───────────────┐                                             │
│               │ Split into    │  LangChain TokenTextSplitter               │
│               │ Chunks        │  (2000 tokens, 200 overlap)                │
│               └───────┬───────┘                                             │
│                       │                                                     │
│                       ▼                                                     │
│               ┌───────────────┐                                             │
│               │ Choose        │                                             │
│               │ Strategy      │                                             │
│               └───────┬───────┘                                             │
│                       │                                                     │
│     ┌─────────────────┼─────────────────┐                                   │
│     ▼                 ▼                 ▼                                   │
│  ┌──────┐       ┌───────────┐     ┌─────────┐                              │
│  │STUFF │       │MAP_REDUCE │     │ REFINE  │                              │
│  │      │       │ (default) │     │         │                              │
│  └──────┘       └───────────┘     └─────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**The 3 Summarization Strategies:**

| Strategy | How It Works | Best For | Speed |
|----------|--------------|----------|-------|
| **STUFF** | Single LLM call with all text | Small docs (< chunk_size) | Fastest |
| **MAP_REDUCE** | Parallel chunk summaries → combine | Large docs, speed matters | Fast |
| **REFINE** | Sequential refinement per chunk | Highest quality needed | Slowest |

**MAP_REDUCE Flow (Default):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MAP_REDUCE STRATEGY                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Original Text (10,000 tokens)                                              │
│       │                                                                     │
│       ▼                                                                     │
│  ┌────────────────────────────────────────────────────────┐                │
│  │  CHUNKING (No LLM - just text splitting)               │                │
│  │  • Splits by token count (2000 tokens/chunk)           │                │
│  │  • 200 token overlap between chunks                    │                │
│  │  • NO TEXT IS REMOVED - just divided into pieces       │                │
│  └────────────────────────────────────────────────────────┘                │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
│  │ Chunk 1 │  │ Chunk 2 │  │ Chunk 3 │  │ Chunk 4 │  │ Chunk 5 │          │
│  │ 2000 tk │  │ 2000 tk │  │ 2000 tk │  │ 2000 tk │  │ 2000 tk │          │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘          │
│       │            │            │            │            │                │
│       ▼            ▼            ▼            ▼            ▼                │
│  ┌────────────────────────────────────────────────────────┐                │
│  │  MAP PHASE (LLM calls - IN PARALLEL)                   │                │
│  │  Each chunk → LLM → Summary of that chunk              │                │
│  │  (5 parallel API calls using asyncio.gather)           │                │
│  └────────────────────────────────────────────────────────┘                │
│       │            │            │            │            │                │
│       ▼            ▼            ▼            ▼            ▼                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
│  │Summary 1│  │Summary 2│  │Summary 3│  │Summary 4│  │Summary 5│          │
│  │ ~400 tk │  │ ~400 tk │  │ ~400 tk │  │ ~400 tk │  │ ~400 tk │          │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘          │
│       │            │            │            │            │                │
│       └────────────┴─────┬──────┴────────────┴────────────┘                │
│                          ▼                                                  │
│  ┌────────────────────────────────────────────────────────┐                │
│  │  REDUCE PHASE (LLM call)                               │                │
│  │  Combine all chunk summaries → Final summary           │                │
│  └────────────────────────────────────────────────────────┘                │
│                          │                                                  │
│                          ▼                                                  │
│                 ┌─────────────────┐                                        │
│                 │  Final Summary  │                                        │
│                 │   ~800 tokens   │                                        │
│                 └─────────────────┘                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Insight - Chunking vs Summarization:**

| Step | Uses LLM? | What Happens |
|------|-----------|--------------|
| **Chunking** | NO | Text is split into pieces (like cutting a book into chapters) |
| **Map** | YES | Each chunk is summarized by LLM (parallel calls) |
| **Reduce** | YES | All chunk summaries combined into final summary |

The LLM sees ALL the original text - just in smaller bites that it can process.

**Why Overlap Between Chunks?**

```
Chunk 1: "...the company reported Q3 revenue of $50B, which was..."
                                           ↑ overlap ↓
Chunk 2: "...revenue of $50B, which was a 10% increase from Q2..."
```

The 200-token overlap ensures context isn't lost at chunk boundaries.

**Dependencies Used:**

| Component | Library | Purpose |
|-----------|---------|---------|
| Text Splitting | `langchain-text-splitters` | TokenTextSplitter, RecursiveCharacterTextSplitter |
| Token Counting | `tiktoken` | Accurate token estimation (falls back to len/4) |
| LLM Orchestration | `langchain-core` | ChatPromptTemplate, StrOutputParser |
| LLM Backend | Your choice | OpenAI, Anthropic, or LLM Gateway |

**Domain-Specific Prompts:**

The summarizer uses different prompts based on content type for better extraction:

```python
# Maps step names to content types
step_content_types = {
    "fetch_sec": "sec_filing",      # → Extracts revenue, margins, risks
    "fetch_earnings": "earnings",   # → Extracts EPS, beats/misses
    "fetch_news": "news",           # → Extracts events, dates, sentiment
    "fetch_transcripts": "transcripts", # → Extracts management commentary
    "fetch_pricing": "pricing",     # → Extracts multiples, targets
}
```

**Usage Examples:**

```python
from agentorchestrator import (
    SummarizerMiddleware,
    create_openai_summarizer,
    create_anthropic_summarizer,
    create_gateway_summarizer,
)

# Option 1: OpenAI
summarizer = create_openai_summarizer(model="gpt-4")

# Option 2: Anthropic Claude
summarizer = create_anthropic_summarizer(model="claude-3-sonnet-20240229")

# Option 3: Enterprise LLM Gateway (with OAuth)
summarizer = create_gateway_summarizer(
    server_url="https://llm.company.com/v1",
    oauth_endpoint="https://auth.company.com/oauth/token",
    client_id="my-client-id",
    client_secret="my-secret",
)

# Add to orchestrator
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    max_tokens=4000,              # Trigger threshold
    preserve_original=True,       # Keep original in context
    step_content_types={          # Domain-specific prompts
        "fetch_sec": "sec_filing",
        "fetch_news": "news",
    },
))
```

**Accessing Original Data:**

```python
@ao.step(deps=["fetch_sec"])
async def process_sec(ctx):
    # Get summarized output (smaller, fits in context)
    summary = ctx.get("sec_data")

    # Access original if needed (stored as _original_{step}_output)
    original = ctx.get("_original_fetch_sec_output")

    # Check if summarization occurred
    result = ctx.get_result("fetch_sec")
    if result.metadata.get("summarized"):
        print(f"Reduced from {result.metadata['original_tokens']} to {result.metadata['summarized_tokens']} tokens")
```

**Strategy Comparison:**

```
STUFF (Small docs):
  Text ──▶ LLM ──▶ Summary

  Pros: Simple, fast, preserves context
  Cons: Limited by LLM context window
  Use when: Text < 2000 tokens

MAP_REDUCE (Default):
  Text ──▶ [Chunk₁, Chunk₂, Chunk₃, ...]
              │       │       │
              ▼       ▼       ▼
           [LLM]   [LLM]   [LLM]  (parallel)
              │       │       │
              ▼       ▼       ▼
           [Sum₁]  [Sum₂]  [Sum₃]
              └───────┼───────┘
                      ▼
                    [LLM] (reduce)
                      │
                      ▼
                Final Summary

  Pros: Fast (parallel), handles any size
  Cons: May lose some nuance between chunks
  Use when: Speed matters, large documents

REFINE (Highest quality):
  Chunk₁ ──▶ LLM ──▶ Summary₁
                         │
  Chunk₂ + Summary₁ ──▶ LLM ──▶ Summary₂
                                    │
  Chunk₃ + Summary₂ ──▶ LLM ──▶ Summary₃
                                    │
                                   ...
                                    │
                                    ▼
                              Final Summary

  Pros: Best quality, builds coherent narrative
  Cons: Sequential (slow), more LLM calls
  Use when: Quality is paramount
```

### Token Management

The `TokenManagerMiddleware` tracks and manages token usage across your chain to stay within LLM context limits.

**How Token Management Works:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TOKEN MANAGEMENT FLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Step Output                                                               │
│       │                                                                     │
│       ▼                                                                     │
│   ┌────────────────────┐                                                    │
│   │ Count Tokens       │  tiktoken or ~4 chars/token                       │
│   └─────────┬──────────┘                                                    │
│             │                                                               │
│             ▼                                                               │
│   ┌────────────────────┐                                                    │
│   │ Update Budget      │  Track total_tokens, step_tokens                  │
│   └─────────┬──────────┘                                                    │
│             │                                                               │
│    ┌────────┴────────┬────────────────┐                                     │
│    ▼                 ▼                ▼                                     │
│ < 80% budget     80-100% budget   > 100% budget                             │
│ (pass through)   (warning + auto-  (auto-offload                            │
│                   summarize)        to Redis)                               │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────┐               │
│   │  PRINCIPLE: NEVER lose data                             │               │
│   │  • Large data → Redis (full preservation)               │               │
│   │  • Context gets ContextRef (lightweight, ~500 bytes)    │               │
│   │  • Ref contains summary + key fields + hash             │               │
│   │  • Full data retrievable on demand                      │               │
│   └─────────────────────────────────────────────────────────┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Configuration:**

```python
from agentorchestrator import TokenManagerMiddleware
from agentorchestrator.middleware import SummarizerMiddleware
from agentorchestrator.core import RedisContextStore

# Basic token tracking
ao.use(TokenManagerMiddleware(
    max_total_tokens=100000,       # Token budget for entire chain
    warning_threshold=0.8,         # Warn at 80% usage
))

# With auto-summarization
summarizer = SummarizerMiddleware(summarizer=create_openai_summarizer())
ao.use(TokenManagerMiddleware(
    max_total_tokens=100000,
    auto_summarize=True,           # Auto-trigger summarization
    summarizer=summarizer,
))

# With auto-offload to Redis
store = RedisContextStore(redis_url="redis://localhost:6379")
ao.use(TokenManagerMiddleware(
    max_total_tokens=100000,
    auto_offload=True,             # Offload to Redis when over limit
    context_store=store,
    offload_threshold_bytes=50000, # Size threshold for offloading
))
```

**Usage Statistics:**

```python
# Get token usage after chain execution
usage = token_middleware.get_usage()
print(f"Total tokens: {usage['total_tokens']}")
print(f"Per-step tokens: {usage['step_tokens']}")
print(f"Budget utilization: {usage['utilization_percent']}%")
```

### Rate Limiting & Circuit Breakers

Protect external services with rate limiting and circuit breakers.

**Rate Limiting:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RATE LIMITING                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Incoming Requests                                                         │
│       │                                                                     │
│       ▼                                                                     │
│   ┌────────────────────┐                                                    │
│   │ Token Bucket       │  Refills at requests_per_second rate              │
│   │ Algorithm          │  Allows burst_size initial burst                  │
│   └─────────┬──────────┘                                                    │
│             │                                                               │
│    ┌────────┴────────┐                                                      │
│    ▼                 ▼                                                      │
│ Tokens available   No tokens                                                │
│ (proceed)          (wait or reject)                                         │
│                                                                             │
│   Concurrency Control:                                                      │
│   ┌─────────────────────────────────────────────────────────┐               │
│   │  Semaphore limits max_concurrent requests               │               │
│   │  Prevents overwhelming backend services                 │               │
│   └─────────────────────────────────────────────────────────┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Circuit Breaker Pattern:**

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         CIRCUIT BREAKER STATES                              │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                    ┌──────────────────────┐                                 │
│       ┌───────────▶│       CLOSED         │◀──────────┐                     │
│       │            │   (Normal operation) │           │                     │
│       │            └──────────┬───────────┘           │                     │
│       │                       │                       │                     │
│       │           5 consecutive failures              │                     │
│       │                       │                       │                     │
│       │                       ▼                       │                     │
│       │            ┌──────────────────────┐           │                     │
│   success          │        OPEN          │      2 successes                │
│   (close)          │   (Fail fast mode)   │      in half-open               │
│       │            └──────────┬───────────┘           │                     │
│       │                       │                       │                     │
│       │              After 60 seconds                 │                     │
│       │                       │                       │                     │
│       │                       ▼                       │                     │
│       │            ┌──────────────────────┐           │                     │
│       └────────────│     HALF_OPEN        │───────────┘                     │
│                    │ (Testing recovery)   │                                 │
│                    │  Allow 1 test call   │                                 │
│                    └──────────────────────┘                                 │
│                               │                                             │
│                          if fails                                           │
│                               │                                             │
│                               ▼                                             │
│                          Back to OPEN                                       │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

**Configuration:**

```python
from agentorchestrator.middleware import (
    RateLimiterMiddleware,
    CircuitBreakerMiddleware,
    RateLimitAndCircuitBreakerMiddleware,
)

# Rate limiting per step
ao.use(RateLimiterMiddleware({
    "fetch_sec": {
        "requests_per_second": 10,    # Max 10 req/sec
        "max_concurrent": 5,          # Max 5 concurrent
        "burst_size": 20,             # Allow initial burst of 20
        "wait_on_limit": True,        # Wait vs. raise exception
        "max_wait_seconds": 30,       # Max wait time
    },
    "fetch_news": {
        "requests_per_second": 5,
        "max_concurrent": 3,
    },
}))

# Circuit breaker per step
ao.use(CircuitBreakerMiddleware({
    "fetch_external_api": {
        "failure_threshold": 5,        # Open after 5 failures
        "success_threshold": 2,        # Close after 2 successes
        "recovery_timeout_seconds": 60, # Wait 60s before testing
        "half_open_max_requests": 1,   # Allow 1 test request
    },
}))

# Combined protection (recommended)
ao.use(RateLimitAndCircuitBreakerMiddleware(
    rate_limits={
        "fetch_sec": {"requests_per_second": 10, "max_concurrent": 5},
    },
    circuit_breakers={
        "fetch_sec": {"failure_threshold": 5, "recovery_timeout_seconds": 60},
    },
))
```

**Get Statistics:**

```python
stats = rate_limiter.get_stats()
# {'fetch_sec': {'requests': 150, 'rejected': 5, 'waited': 20}}

circuit_states = circuit_breaker.get_circuit_states()
# {'fetch_external_api': 'CLOSED', 'fetch_backup_api': 'HALF_OPEN'}
```

### Context Store (Redis Offloading)

Large payloads are automatically offloaded to Redis, keeping the chain context lightweight.

**How Context Store Works:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CONTEXT STORE ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Step produces large output (e.g., 1.2MB SEC filing)                       │
│       │                                                                     │
│       ▼                                                                     │
│   ┌────────────────────────────────────────────────────────┐                │
│   │  OffloadMiddleware checks size                          │                │
│   │  1.2MB > 100KB threshold → Offload                      │                │
│   └─────────────────────────┬──────────────────────────────┘                │
│                             │                                               │
│              ┌──────────────┴──────────────┐                                │
│              ▼                             ▼                                │
│   ┌──────────────────────┐      ┌──────────────────────┐                   │
│   │      REDIS           │      │   CHAIN CONTEXT      │                   │
│   │  (Full Data Store)   │      │   (Lightweight)      │                   │
│   ├──────────────────────┤      ├──────────────────────┤                   │
│   │ Key: ref_abc123      │      │ sec_data: ContextRef │                   │
│   │ Value: {             │◀────▶│   ref_id: abc123     │                   │
│   │   full SEC filing    │      │   size: 1.2MB        │                   │
│   │   with all tables,   │      │   summary: "Q3..."   │                   │
│   │   exhibits, etc.     │      │   key_fields: {      │                   │
│   │ }                    │      │     revenue: $50B    │                   │
│   │ TTL: 24 hours        │      │     eps: $1.42       │                   │
│   └──────────────────────┘      │   }                  │                   │
│                                 │   hash: sha256...    │                   │
│                                 └──────────────────────┘                   │
│                                          │                                  │
│   Later steps can:                       │                                  │
│   • Use summary/key_fields directly      │                                  │
│   • Retrieve full data when needed  ─────┘                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**ContextRef Properties:**

| Property | Description |
|----------|-------------|
| `ref_id` | Unique reference ID for Redis lookup |
| `size_bytes` | Exact size of stored data |
| `content_hash` | SHA256 for integrity verification |
| `summary` | Human-readable summary (always preserved) |
| `key_fields` | Critical extracted fields (revenue, dates, etc.) |
| `item_count` | For lists: total items stored |
| `omitted_count` | For lists: items not in key_fields |
| `source_step` | Origin step name |
| `ttl_seconds` | Time-to-live in Redis |

**Configuration:**

```python
from agentorchestrator.core import RedisContextStore
from agentorchestrator.middleware import OffloadMiddleware

# Create Redis store
store = RedisContextStore(
    redis_url="redis://localhost:6379",
    default_ttl=86400,  # 24 hours
    prefix="ao:",       # Key prefix
)

# Add offload middleware
ao.use(OffloadMiddleware(
    store=store,
    default_threshold_bytes=100_000,  # 100KB default
    step_thresholds={
        "fetch_sec": 50_000,           # Lower threshold for SEC
        "fetch_news": 200_000,         # Higher for news
    },
))
```

**Retrieving Full Data:**

```python
@ao.step(deps=["fetch_sec"])
async def analyze_sec(ctx):
    # Get the ContextRef
    sec_ref = ctx.get("sec_data")

    # Use summary for quick decisions
    if "material weakness" in sec_ref.summary:
        # Need full data for detailed analysis
        full_data = await store.retrieve(sec_ref)
        # full_data contains the complete 1.2MB SEC filing

    # Or just use key_fields
    revenue = sec_ref.key_fields.get("revenue")
    eps = sec_ref.key_fields.get("eps")
```

### Health Checks

Comprehensive health monitoring for all dependencies.

**Health Check Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HEALTH CHECK SYSTEM                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ao health --detailed                                                      │
│       │                                                                     │
│       ▼                                                                     │
│   ┌────────────────────────────────────────────────────────┐                │
│   │  HealthAggregator (parallel checks)                     │                │
│   └────────────────────────────────────────────────────────┘                │
│       │           │           │           │           │                     │
│       ▼           ▼           ▼           ▼           ▼                     │
│   ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐               │
│   │ Config │  │ Redis  │  │  LLM   │  │ Agents │  │ Chains │               │
│   │ Check  │  │ Check  │  │Gateway │  │ Check  │  │ Check  │               │
│   └────┬───┘  └────┬───┘  └────┬───┘  └────┬───┘  └────┬───┘               │
│        │           │           │           │           │                    │
│        ▼           ▼           ▼           ▼           ▼                    │
│   ┌─────────────────────────────────────────────────────────┐               │
│   │  Health Statuses:                                        │               │
│   │  • HEALTHY   - All checks passed                        │               │
│   │  • DEGRADED  - Some non-critical checks failed          │               │
│   │  • UNHEALTHY - Critical checks failed                   │               │
│   │  • UNKNOWN   - Check could not complete                 │               │
│   └─────────────────────────────────────────────────────────┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Usage:**

```python
from agentorchestrator.utils.health import (
    HealthAggregator,
    run_health_checks,
    is_ready,
    is_live,
)

# Quick health check
health = await run_health_checks(ao)
print(f"Status: {health.status}")  # HEALTHY, DEGRADED, UNHEALTHY
print(f"Components: {health.components}")

# Kubernetes probes
if await is_ready(ao):
    print("Ready to accept traffic")

if await is_live(ao):
    print("Application is alive")

# Detailed health aggregator
aggregator = HealthAggregator(ao, timeout_seconds=10)
result = await aggregator.check_all()

for component, status in result.components.items():
    print(f"{component}: {status.status} ({status.latency_ms}ms)")
    if status.details:
        print(f"  Details: {status.details}")
```

**CLI:**

```bash
# Quick health check
ao health
# Status: HEALTHY ✓

# Detailed output
ao health --detailed
# ┌────────────────────────────────────────────┐
# │ Component      │ Status   │ Latency │ Details
# ├────────────────────────────────────────────┤
# │ config         │ HEALTHY  │ 1ms     │ Valid
# │ redis          │ HEALTHY  │ 5ms     │ Connected
# │ llm_gateway    │ HEALTHY  │ 150ms   │ Model: gpt-4
# │ agents         │ DEGRADED │ 200ms   │ 2/3 healthy
# │ chains         │ HEALTHY  │ 2ms     │ 5 chains valid
# └────────────────────────────────────────────┘

# JSON output for monitoring systems
ao health --json
```

### Input/Output Validation

Pydantic-based validation for step contracts.

```python
from pydantic import BaseModel
from agentorchestrator.core import validates_input, validates_output

class CompanyRequest(BaseModel):
    company_name: str
    ticker: str
    include_financials: bool = True

class CompanyData(BaseModel):
    name: str
    ticker: str
    revenue: float
    eps: float

@ao.step
@validates_input(CompanyRequest)
@validates_output(CompanyData)
async def fetch_company(ctx, request: CompanyRequest) -> CompanyData:
    # request is already validated Pydantic model
    data = await api.get_company(request.ticker)

    # Output is validated before returning
    return CompanyData(
        name=data["name"],
        ticker=request.ticker,
        revenue=data["revenue"],
        eps=data["eps"],
    )
```

**Error Handling:**

```python
from agentorchestrator.core import ContractValidationError

try:
    result = await ao.launch("my_chain", {"invalid": "data"})
except ContractValidationError as e:
    print(f"Step: {e.step_name}")
    print(f"Contract: {e.contract_type}")  # "input" or "output"
    print(f"Errors: {e.errors}")
    # [{'loc': ('company_name',), 'msg': 'field required', 'type': 'missing'}]
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

### Plugin System

Extend AgentOrchestrator with custom plugins via Python entry points.

**Plugin Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PLUGIN SYSTEM                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   pyproject.toml                                                            │
│   ├── [project.entry-points."agentorchestrator.agents"]                    │
│   ├── [project.entry-points."agentorchestrator.connectors"]                │
│   └── [project.entry-points."agentorchestrator.middleware"]                │
│                                                                             │
│       │                                                                     │
│       ▼                                                                     │
│   ┌────────────────────────────────────────────────────────┐                │
│   │  PluginManager                                          │                │
│   │  • discover() - Find all installed plugins              │                │
│   │  • load() - Import and instantiate                      │                │
│   │  • get() - Retrieve by name                             │                │
│   │  • list() - List all available                          │                │
│   └────────────────────────────────────────────────────────┘                │
│                                                                             │
│   Entry Point Groups:                                                       │
│   • agentorchestrator.agents     → Custom data agents                      │
│   • agentorchestrator.connectors → Custom connectors                       │
│   • agentorchestrator.middleware → Custom middleware                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Creating a Plugin:**

```toml
# In your package's pyproject.toml
[project.entry-points."agentorchestrator.agents"]
my_agent = "my_package.agents:MyCustomAgent"

[project.entry-points."agentorchestrator.middleware"]
my_middleware = "my_package.middleware:MyCustomMiddleware"
```

**Using Plugins:**

```python
from agentorchestrator.plugins import PluginManager

# Discover all installed plugins
manager = PluginManager()
manager.discover()

# List available plugins
for plugin in manager.list("agents"):
    print(f"{plugin.name}: {plugin.description}")

# Load a specific plugin
MyAgent = manager.load("my_agent", group="agents")
agent = MyAgent()

# Get plugin info
info = manager.get_info("my_agent")
print(f"Version: {info.version}")
print(f"Capabilities: {info.capabilities}")
```

---

## Middleware Reference

Complete reference for all built-in middleware with priority ordering.

**Middleware Execution Order:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MIDDLEWARE STACK                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Request Flow (before hooks - ascending priority):                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ CircuitBreaker(5) → RateLimiter(10) → Logger(10) → Cache(20)       │   │
│   │       → TokenManager(15) → [Step Execution]                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Response Flow (after hooks - descending priority):                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ [Step Result] → Summarizer(50) → TokenManager(15) → Cache(20)      │   │
│   │       → Logger(10) → RateLimiter(10) → CircuitBreaker(5)           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Priority: Lower number = earlier in before(), later in after()            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Middleware Quick Reference:**

| Middleware | Priority | Purpose | Key Options |
|------------|----------|---------|-------------|
| `CircuitBreakerMiddleware` | 5 | Prevent cascading failures | failure_threshold, recovery_timeout |
| `RateLimiterMiddleware` | 10 | Rate limit API calls | requests_per_second, max_concurrent |
| `LoggerMiddleware` | 10 | Structured logging | level, include_context |
| `TokenManagerMiddleware` | 15 | Track token budget | max_total_tokens, auto_summarize |
| `CacheMiddleware` | 20 | Cache step outputs | ttl_seconds, max_entries |
| `MetricsMiddleware` | 30 | Collect metrics | backend, export_interval |
| `SummarizerMiddleware` | 50 | Summarize large outputs | max_tokens, strategy |
| `OffloadMiddleware` | 60 | Offload to Redis | threshold_bytes, store |

**Recommended Production Stack:**

```python
from agentorchestrator import (
    AgentOrchestrator,
    LoggerMiddleware,
    CacheMiddleware,
    TokenManagerMiddleware,
    SummarizerMiddleware,
    create_openai_summarizer,
)
from agentorchestrator.middleware import (
    RateLimiterMiddleware,
    CircuitBreakerMiddleware,
    MetricsMiddleware,
    OffloadMiddleware,
)
from agentorchestrator.core import RedisContextStore

ao = AgentOrchestrator(name="production", isolated=True)

# Create dependencies
store = RedisContextStore(redis_url="redis://localhost:6379")
summarizer = create_openai_summarizer(model="gpt-4")

# Add middleware stack (order doesn't matter - priority controls execution)
ao.use(LoggerMiddleware(level="INFO"))
ao.use(CacheMiddleware(ttl_seconds=300))
ao.use(MetricsMiddleware())
ao.use(RateLimiterMiddleware({
    "fetch_sec": {"requests_per_second": 10, "max_concurrent": 5},
    "fetch_news": {"requests_per_second": 20, "max_concurrent": 10},
}))
ao.use(CircuitBreakerMiddleware({
    "fetch_sec": {"failure_threshold": 5},
    "fetch_news": {"failure_threshold": 3},
}))
ao.use(TokenManagerMiddleware(
    max_total_tokens=100000,
    auto_summarize=True,
    summarizer=SummarizerMiddleware(summarizer=summarizer),
))
ao.use(OffloadMiddleware(
    store=store,
    default_threshold_bytes=100_000,
))
```

**Creating Custom Middleware:**

```python
from agentorchestrator.middleware import Middleware
from agentorchestrator.core import ChainContext, StepResult

class MyCustomMiddleware(Middleware):
    def __init__(self, priority: int = 25, applies_to: list[str] = None):
        super().__init__(priority=priority, applies_to=applies_to)
        # applies_to: ["step1", "step2"] or None for all steps

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """Called before step execution."""
        print(f"Starting {step_name}")

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Called after step execution (success or failure)."""
        print(f"Finished {step_name}: {'success' if result.success else 'failed'}")

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """Called when step raises an exception."""
        print(f"Error in {step_name}: {error}")

# Register
ao.use(MyCustomMiddleware(priority=35, applies_to=["important_step"]))
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

### Scaffolding Commands

Generate ready-to-use templates for agents, chains, and full projects:

#### Create a New Agent

```bash
# Basic agent
ao new agent MyCustomAgent

# Specify output directory
ao new agent MyCustomAgent --output ./src/agents/

# Overwrite existing file
ao new agent MyCustomAgent --force
```

**Generated file (`mycustomagent_agent.py`):**

```python
"""
MyCustomAgent Agent

Custom data agent for fetching mycustomagent data.
"""

from agentorchestrator.agents.base import BaseAgent, AgentResult


class MyCustomAgentAgent(BaseAgent):
    """
    Agent for fetching mycustomagent data.

    Usage:
        agent = MyCustomAgentAgent()
        result = await agent.fetch(query="search term")
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # Add your initialization here

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch data based on query."""
        # TODO: Implement your data fetching logic here
        data = {
            "query": query,
            "results": [],
        }

        return AgentResult(
            data=data,
            metadata={
                "source": "mycustomagent",
                "query": query,
            }
        )

    async def health_check(self) -> bool:
        """Check if agent is healthy."""
        return True


# Register with AgentOrchestrator
def register(forge):
    """Register this agent with AgentOrchestrator instance."""
    forge.register_agent("mycustomagent", MyCustomAgentAgent)
```

#### Create a New Chain

```bash
# Basic chain
ao new chain DataPipeline

# Specify output directory
ao new chain DataPipeline --output ./src/chains/
```

**Generated file (`datapipeline_chain.py`):**

```python
"""
DataPipeline Chain

Custom chain for datapipeline workflow.
"""

from agentorchestrator import AgentOrchestrator, ChainContext


# Create AgentOrchestrator instance (isolated for this chain)
forge = AgentOrchestrator(name="datapipeline", isolated=True)


# Define steps
@forge.step
async def step_1(ctx: ChainContext) -> dict:
    """First step: Initialize and prepare data."""
    initial_data = ctx.initial_data or {}
    result = {"status": "initialized", "input": initial_data}
    ctx.set("step_1_result", result)
    return result


@forge.step(deps=[step_1])
async def step_2(ctx: ChainContext) -> dict:
    """Second step: Process data from step 1."""
    step_1_result = ctx.get("step_1_result")
    result = {"status": "processed", "previous": step_1_result}
    ctx.set("step_2_result", result)
    return result


@forge.step(deps=[step_2])
async def step_3(ctx: ChainContext) -> dict:
    """Final step: Generate output."""
    step_2_result = ctx.get("step_2_result")
    return {"status": "completed", "output": step_2_result}


# Define chain
@forge.chain
class DataPipelineChain:
    """DataPipeline workflow chain."""
    steps = [step_1, step_2, step_3]


# Run if executed directly
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await forge.launch("DataPipelineChain", {"input": "test"})
        print(result)

    asyncio.run(main())
```

#### Create a New Project

```bash
# Full project with structure
ao new project my-app

# With API support
ao new project my-app --with-api

# Without Docker files
ao new project my-app --no-docker
```

**Generated project structure:**

```
my-app/
├── src/
│   └── my_app/
│       ├── __init__.py
│       ├── chains/
│       │   └── __init__.py
│       ├── agents/
│       │   └── __init__.py
│       └── config.py
├── tests/
│   └── __init__.py
├── pyproject.toml
├── README.md
├── .env.example
└── docker-compose.yml  (if --no-docker not specified)
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
│   ├── sec_agent.py         # SECFilingAgent
│   ├── news_agent.py        # NewsAgent
│   ├── earnings_agent.py    # EarningsAgent
│   └── data_agents.py       # Re-exports (backward compat)
│
├── services/                 # Re-exports from examples/cmpt/services
│   ├── __init__.py          # Main exports
│   ├── models.py            # ChainRequest, ChainResponse, etc.
│   ├── context_builder.py   # ContextBuilderService
│   ├── content_prioritization.py  # ContentPrioritizationService
│   ├── response_builder.py  # ResponseBuilderService
│   └── llm_gateway.py       # LLMGatewayClient
│
├── chains/                   # Pre-built chains
│   ├── __init__.py          # Chain exports
│   └── cmpt.py              # CMPTChain implementation
│
├── plugins/                  # Plugin adapters
│   ├── http_adapter.py      # HTTP-based agent adapter
│   └── mcp_adapter.py       # MCP protocol adapter
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

## Architecture Diagrams

### Internal Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AgentOrchestrator Core                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         Middleware Pipeline                           │  │
│  │  Logger → Cache → TokenManager → Metrics → Tracing → RateLimiter     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐    │
│  │    Registries   │  │   DAG Executor  │  │    Resource Manager     │    │
│  │                 │  │                 │  │                         │    │
│  │ • AgentRegistry │  │ • Build graph   │  │ • HTTP clients (pooled) │    │
│  │ • StepRegistry  │  │ • Resolve deps  │  │ • LLM clients           │    │
│  │ • ChainRegistry │  │ • Parallel exec │  │ • DB connections        │    │
│  │                 │  │ • Semaphore     │  │ • Lifecycle management  │    │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘    │
│           │                    │                       │                    │
│           └────────────────────┼───────────────────────┘                    │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        Chain Context                                  │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │  │
│  │  │   GLOBAL    │  │    CHAIN    │  │    STEP     │  │  Metadata  │  │  │
│  │  │  (config)   │  │ (summaries) │  │ (temp data) │  │ (request_id│  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         Run Store (Checkpoints)                       │  │
│  │  • Save state after each step  • Resume failed runs  • Partial output│  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Execution Flow (CMPT Example)

```
Request                                                              Response
   │                                                                     ▲
   ▼                                                                     │
┌──────────────────────────────────────────────────────────────────────────┐
│                            CMPT Chain                                     │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐     ┌─────────────────────────────────────────┐    │
│  │ Context Builder │     │         Content Prioritization          │    │
│  │                 │     │                                         │    │
│  │ • Company info  │────▶│ • Analyze query intent                  │    │
│  │ • Temporal data │     │ • Score sources by relevance            │    │
│  │ • Personas      │     │ • Generate prioritized subqueries       │    │
│  └─────────────────┘     └─────────────────────────────────────────┘    │
│                                           │                              │
│                                           ▼                              │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      Response Builder                              │  │
│  │                                                                    │  │
│  │   ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌────────────┐         │  │
│  │   │   SEC   │  │  News   │  │ Earnings │  │Transcripts │  ← Parallel│
│  │   │  Agent  │  │  Agent  │  │  Agent   │  │   Agent    │         │  │
│  │   └────┬────┘  └────┬────┘  └────┬─────┘  └─────┬──────┘         │  │
│  │        │            │            │              │                 │  │
│  │        └────────────┴─────┬──────┴──────────────┘                 │  │
│  │                           ▼                                       │  │
│  │              ┌─────────────────────────┐                          │  │
│  │              │      LLM Synthesis      │                          │  │
│  │              │  • Extract metrics      │                          │  │
│  │              │  • Generate analysis    │                          │  │
│  │              │  • Build final content  │                          │  │
│  │              └─────────────────────────┘                          │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### User's Deployment View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Your Service / Kubernetes                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Your API Layer                               │   │
│  │                    (FastAPI / Flask / gRPC)                          │   │
│  │                                                                      │   │
│  │   POST /meeting-prep  ──────┐                                        │   │
│  │   POST /custom-chain  ──────┤                                        │   │
│  │   GET  /health        ──────┤                                        │   │
│  └─────────────────────────────┼────────────────────────────────────────┘   │
│                                │                                            │
│                                ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     AgentOrchestrator (pip installed)                │   │
│  │                                                                      │   │
│  │   from agentorchestrator import AgentOrchestrator                    │   │
│  │   from agentorchestrator.chains import CMPTChain                     │   │
│  │                                                                      │   │
│  │   ao = AgentOrchestrator()                                           │   │
│  │   ao.use(LoggerMiddleware(), MetricsMiddleware())                    │   │
│  │                                                                      │   │
│  │   # Register your agents                                             │   │
│  │   @ao.agent(name="my_news_agent")                                    │   │
│  │   class MyNewsAgent: ...                                             │   │
│  │                                                                      │   │
│  │   result = await ao.launch("cmpt_chain", data)                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Your APIs   │  │  Your LLM    │  │    Redis     │  │  Your DBs    │   │
│  │  (SEC, News) │  │  (Gateway)   │  │  (Context)   │  │              │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Go Crazy: What You Can Build

AgentOrchestrator is a general-purpose chain orchestration library. Here are complete, working examples you can adapt:

### 1. Multi-Model AI Router

Route queries to different LLMs based on complexity — use cheap/fast models for simple queries, powerful models for complex ones.

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="ai_router")

@ao.step(name="classify_complexity")
async def classify_complexity(ctx):
    query = ctx.get("query")
    complex_keywords = ["analyze", "compare", "explain why", "multi-step", "reasoning"]
    is_complex = any(kw in query.lower() for kw in complex_keywords)

    return {
        "complexity": "high" if is_complex else "low",
        "model": "gpt-4" if is_complex else "gpt-3.5-turbo",
        "max_tokens": 2000 if is_complex else 500,
    }

@ao.step(name="generate_response", deps=["classify_complexity"])
async def generate_response(ctx):
    model = ctx.get("model")
    max_tokens = ctx.get("max_tokens")
    query = ctx.get("query")

    llm = ao.get_resource("llm_client")
    response = await llm.chat(
        model=model,
        messages=[{"role": "user", "content": query}],
        max_tokens=max_tokens,
    )

    return {"response": response.content, "model_used": model}

@ao.chain(name="smart_router")
class SmartRouterChain:
    steps = ["classify_complexity", "generate_response"]

# Run
result = await ao.launch("smart_router", {"query": "Explain quantum computing"})
```

### 2. RAG Document Pipeline

Ingest documents, chunk, embed, index, and query — complete RAG pipeline.

```python
ao = AgentOrchestrator(name="rag_pipeline")

@ao.step(name="ingest")
async def ingest(ctx):
    source = ctx.get("source")
    documents = await fetch_documents(source)
    return {"documents": documents, "count": len(documents)}

@ao.step(name="chunk", deps=["ingest"])
async def chunk(ctx):
    documents = ctx.get("documents")
    chunks = []
    for doc in documents:
        for i in range(0, len(doc["content"]), 500):
            chunks.append({"doc_id": doc["id"], "text": doc["content"][i:i+500]})
    return {"chunks": chunks}

@ao.step(name="embed", deps=["chunk"])
async def embed(ctx):
    chunks = ctx.get("chunks")
    embedder = ao.get_resource("embedder")
    for chunk in chunks:
        chunk["embedding"] = await embedder.embed(chunk["text"])
    return {"chunks": chunks}

@ao.step(name="index", deps=["embed"])
async def index(ctx):
    chunks = ctx.get("chunks")
    vector_store = ao.get_resource("vector_store")
    await vector_store.upsert(chunks)
    return {"indexed": len(chunks)}

@ao.chain(name="index_pipeline")
class IndexPipeline:
    steps = ["ingest", "chunk", "embed", "index"]
```

### 3. Customer Support Bot with Escalation

Classify tickets, auto-respond to simple ones, escalate complex/angry ones.

```python
ao = AgentOrchestrator(name="support_bot")

@ao.step(name="classify_ticket")
async def classify_ticket(ctx):
    ticket_text = ctx.get("ticket_text")
    llm = ao.get_resource("llm_client")

    response = await llm.chat(
        messages=[{
            "role": "system",
            "content": 'Classify: {"priority": "low|medium|high", "sentiment": "positive|neutral|angry"}'
        }, {"role": "user", "content": ticket_text}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.content)

@ao.step(name="route_ticket", deps=["classify_ticket"])
async def route_ticket(ctx):
    priority = ctx.get("priority")
    sentiment = ctx.get("sentiment")
    needs_human = priority == "high" or sentiment == "angry"
    return {"route": "human" if needs_human else "auto"}

@ao.step(name="generate_auto_response", deps=["route_ticket"])
async def generate_auto_response(ctx):
    if ctx.get("route") == "human":
        return {"response": None, "auto_responded": False}

    llm = ao.get_resource("llm_client")
    response = await llm.chat(messages=[{"role": "user", "content": ctx.get("ticket_text")}])
    return {"response": response.content, "auto_responded": True}

@ao.step(name="escalate_to_human", deps=["route_ticket"])
async def escalate_to_human(ctx):
    if ctx.get("route") != "human":
        return {"escalated": False}

    ticketing = ao.get_resource("ticketing_system")
    ticket_id = await ticketing.create_ticket(
        body=ctx.get("ticket_text"),
        priority=ctx.get("priority"),
    )
    return {"escalated": True, "ticket_id": ticket_id}

@ao.chain(name="support_chain")
class SupportChain:
    steps = ["classify_ticket", "route_ticket", "generate_auto_response", "escalate_to_human"]
```

### 4. Code Review Bot

Fetch PR, run parallel checks (style, security, tests), generate AI review.

```python
ao = AgentOrchestrator(name="code_review_bot")

@ao.step(name="fetch_pr")
async def fetch_pr(ctx):
    github = ao.get_agent("github_agent")
    pr_data = await github.fetch(ctx.get("pr_url"))
    return {"pr_title": pr_data["title"], "diff": pr_data["diff"]}

@ao.step(name="check_style", deps=["fetch_pr"])
async def check_style(ctx):
    issues = await run_linter(ctx.get("diff"))
    return {"style_issues": issues, "style_passed": len(issues) == 0}

@ao.step(name="check_security", deps=["fetch_pr"])
async def check_security(ctx):
    vulns = await run_security_scan(ctx.get("diff"))
    return {"security_issues": vulns, "security_passed": len(vulns) == 0}

@ao.step(name="check_tests", deps=["fetch_pr"])
async def check_tests(ctx):
    coverage = await run_tests()
    return {"coverage": coverage, "tests_passed": coverage > 80}

@ao.step(name="generate_review", deps=["check_style", "check_security", "check_tests"])
async def generate_review(ctx):
    llm = ao.get_resource("llm_client")
    all_passed = ctx.get("style_passed") and ctx.get("security_passed") and ctx.get("tests_passed")

    response = await llm.chat(messages=[{
        "role": "user",
        "content": f"Review: {json.dumps(ctx.get_all())}"
    }])
    return {"review": response.content, "action": "APPROVE" if all_passed else "REQUEST_CHANGES"}

@ao.chain(name="code_review")
class CodeReviewChain:
    steps = ["fetch_pr", "check_style", "check_security", "check_tests", "generate_review"]
```

### 5. ETL Pipeline with Validation & Resumability

Extract, transform with validation, load — resumable on failure.

```python
from agentorchestrator import AgentOrchestrator
from pydantic import BaseModel, validator

ao = AgentOrchestrator(name="etl_pipeline")

class CleanRecord(BaseModel):
    id: str
    email: str
    amount: float

    @validator("email")
    def validate_email(cls, v):
        if "@" not in v:
            raise ValueError("Invalid email")
        return v

@ao.step(name="extract")
async def extract(ctx):
    db = ao.get_resource("source_db")
    records = await db.query("SELECT * FROM raw_data")
    return {"raw_records": records}

@ao.step(name="transform", deps=["extract"])
async def transform(ctx):
    raw_records = ctx.get("raw_records")
    clean, errors = [], []

    for raw in raw_records:
        try:
            clean.append(CleanRecord(**raw).model_dump())
        except Exception as e:
            errors.append({"id": raw["id"], "error": str(e)})

    return {"clean_records": clean, "errors": errors}

@ao.step(name="load", deps=["transform"], retry=3)
async def load(ctx):
    dest_db = ao.get_resource("dest_db")
    await dest_db.insert_many("clean_data", ctx.get("clean_records"))
    return {"loaded": len(ctx.get("clean_records"))}

@ao.chain(name="etl")
class ETLChain:
    steps = ["extract", "transform", "load"]

# Run with resumability via CLI:
# ao run etl --resumable
# ao resume <run_id>  # If it fails
```

### 6. Multi-Tenant SaaS Workflow

Isolated execution per tenant with tenant-specific rate limits.

```python
from agentorchestrator import AgentOrchestrator, IsolatedOrchestrator
from agentorchestrator.middleware import RateLimiterMiddleware

TENANT_CONFIGS = {
    "free": {"rate_limit": 10, "max_tokens": 1000},
    "pro": {"rate_limit": 100, "max_tokens": 4000},
    "enterprise": {"rate_limit": 1000, "max_tokens": 8000},
}

async def handle_tenant_request(tenant_id: str, request: dict):
    config = TENANT_CONFIGS.get(tenant_id, TENANT_CONFIGS["free"])

    async with IsolatedOrchestrator(name=f"ao_{tenant_id}") as ao:
        ao.use(RateLimiterMiddleware({"generate": {"rpm": config["rate_limit"]}}))

        @ao.step(name="validate")
        async def validate(ctx):
            if ctx.get("max_tokens", 0) > config["max_tokens"]:
                raise ValueError(f"Exceeds plan limit: {config['max_tokens']}")
            return {"validated": True}

        @ao.step(name="generate", deps=["validate"])
        async def generate(ctx):
            llm = get_llm_client()
            return {"response": await llm.chat(messages=ctx.get("messages"))}

        @ao.chain(name="tenant_workflow")
        class TenantWorkflow:
            steps = ["validate", "generate"]

        return await ao.launch("tenant_workflow", request)
```

---

## Quick Reference: Pattern → Features

| Pattern | Example | Key Features |
|---------|---------|--------------|
| **Router** | Multi-model AI | Conditional logic in steps, resource injection |
| **Pipeline** | RAG, ETL | `deps`, input/output contracts, sequential flow |
| **Fan-out/Fan-in** | Code review | Parallel step execution, multiple agents |
| **Saga** | Support bot | Error handling modes, compensating actions |
| **Multi-tenant** | SaaS | `IsolatedOrchestrator`, per-tenant middleware |
| **Resumable** | ETL | Run store, `ao resume`, partial output retrieval |

---

## The AgentOrchestrator Advantage

| Without AgentOrchestrator | With AgentOrchestrator |
|---------------------------|------------------------|
| 50+ lines of retry/backoff code | `@ao.step(retry=3, backoff=2.0)` |
| Manual asyncio.gather orchestration | Automatic parallel execution via DAG |
| Custom error handling per service | `error_handling="continue"` / `"fail_fast"` |
| No visibility into partial failures | `ao runs --status failed` |
| Re-run entire pipeline on crash | `ao resume <run_id>` |
| Scattered logging across services | `LoggerMiddleware` + `MetricsMiddleware` |
| Per-service rate limiting | `RateLimiterMiddleware` with per-step config |
| Hardcoded client initialization | `ao.register_resource()` + dependency injection |
| Manual test isolation | `IsolatedOrchestrator` context manager |

**Bottom line**: AgentOrchestrator handles the orchestration plumbing — retries, parallelism, context, logging, resumability — so you focus on your business logic.

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

---

## Framework Comparison

### How AgentOrchestrator Compares to Other Frameworks

AgentOrchestrator is designed for **DAG-based workflow orchestration** with production resilience. Here's how it compares to other popular AI orchestration frameworks:

- [LangGraph](https://www.langchain.com/langgraph) - MIT licensed, focuses on stateful agent graphs with cycles
- [CrewAI](https://www.crewai.com/) - MIT licensed, focuses on role-based multi-agent collaboration
- [Semantic Kernel](https://github.com/microsoft/semantic-kernel) - MIT licensed, Microsoft's multi-language AI SDK
- [ControlFlow](https://www.prefect.io/controlflow) - Apache 2.0, Prefect's LLM orchestration (archived Aug 2025)

### What They Have That We Don't

| Feature | Who Has It | Gap for AgentOrchestrator |
|---------|-----------|---------------------------|
| Cyclic Graphs | LangGraph | ⚠️ **Yes** - We only support DAG (acyclic) |
| Time-Travel Debugging | LangGraph | ⚠️ **Yes** - Rewind state to any checkpoint |
| Human-in-the-Loop Interrupts | LangGraph, CrewAI | ⚠️ **Partial** - We have resumable runs but no pause/approve pattern |
| Role-Based Agents | CrewAI | ❌ **No** - Not our use case (orchestration, not role-play) |
| Agent-to-Agent Messaging | CrewAI, Semantic Kernel | ⚠️ **Yes** - Our steps communicate via context, not direct messaging |
| Multi-Language SDK | Semantic Kernel (C#, Python, Java) | ❌ **No** - Python-only is fine for our use case |
| Model Context Protocol (MCP) | Semantic Kernel, LangGraph | ✅ **We have this** |
| Native Observability Dashboard | All of them | ⚠️ **Yes** - We have tracing hooks but no built-in UI |

### What We Already Have

| Feature | LangGraph | CrewAI | Semantic Kernel | ControlFlow | AgentOrchestrator |
|---------|-----------|--------|-----------------|-------------|-------------------|
| DAG Execution | ✅ | ✅ | ✅ | ✅ | ✅ |
| Parallel Step Execution | ✅ | ✅ | ✅ | ✅ | ✅ |
| Checkpointing/Resume | ✅ | ❌ | ✅ | ✅ | ✅ |
| Middleware/Hooks | ✅ | ❌ | ✅ (filters) | ✅ | ✅ |
| Context/State Management | ✅ | ✅ | ✅ | ✅ | ✅ |
| Circuit Breaker | ❌ | ❌ | ❌ | ✅ (via Prefect) | ✅ |
| Rate Limiting | ❌ | ❌ | ❌ | ❌ | ✅ |
| MCP Support | ✅ | ❌ | ✅ | ❌ | ✅ |
| Decorator-based API | ❌ | ❌ | ❌ | ✅ | ✅ |

### Our Differentiators

| Strength | Description |
|----------|-------------|
| **Simpler API** | `@ao.step()` decorator vs LangGraph's graph builder complexity |
| **Pythonic** | Native Python patterns vs role-play abstractions |
| **Middleware Stack** | Built-in cache, rate limit, circuit breaker, summarization |
| **Production Resilience** | Retry policies, circuit breakers, health checks out of the box |
| **No Lock-in** | Uses LangChain at runtime for LLM calls, not a competing abstraction |



CMPT Application Logs - What They Look Like
Scenario 1: Successful Chain Execution
================================================================================
                         CMPT CHAIN - SUCCESSFUL RUN
================================================================================

2025-12-10T14:32:15.123Z | INFO | agentorchestrator.chain.cmpt | Chain started
    request_id: req_abc123
    chain: cmpt_chain
    total_steps: 3
    input: {"company": "Apple Inc", "meeting_date": "2025-12-15"}

--------------------------------------------------------------------------------
STAGE 1: CONTEXT BUILDER
--------------------------------------------------------------------------------

2025-12-10T14:32:15.125Z | INFO | agentorchestrator.execution | [req_abc123] Starting step: context_builder
    event: step_start
    step: context_builder

2025-12-10T14:32:15.130Z | DEBUG | agentorchestrator.chain.cmpt | Looking up company
    company_input: "Apple Inc"
    
2025-12-10T14:32:15.250Z | DEBUG | agentorchestrator.chain.cmpt | Company resolved
    ticker: AAPL
    cik: 0000320193
    sector: Technology
    market_cap: 3.2T

2025-12-10T14:32:15.255Z | DEBUG | agentorchestrator.chain.cmpt | Temporal context extracted
    fiscal_year: 2024
    fiscal_quarter: Q4
    earnings_date: 2025-01-30

2025-12-10T14:32:15.280Z | INFO | agentorchestrator.execution | [req_abc123] Step context_builder completed in 155.00ms
    event: step_complete
    step: context_builder
    success: true
    duration_ms: 155.00
    output_keys: [company_name, ticker, temporal_context, persona]

--------------------------------------------------------------------------------
STAGE 2: CONTENT PRIORITIZATION
--------------------------------------------------------------------------------

2025-12-10T14:32:15.282Z | INFO | agentorchestrator.execution | [req_abc123] Starting step: content_prioritization
    event: step_start
    step: content_prioritization

2025-12-10T14:32:15.290Z | DEBUG | agentorchestrator.chain.cmpt | Computing source priorities
    days_to_earnings: 51
    market_cap_tier: large_cap

2025-12-10T14:32:15.295Z | DEBUG | agentorchestrator.chain.cmpt | Priority distribution calculated
    priorities:
      news_tool: 60%
      earnings_tool: 20%
      sec_tool: 20%

2025-12-10T14:32:15.310Z | DEBUG | agentorchestrator.chain.cmpt | Subqueries generated
    subqueries:
      - agent: sec_tool, query: "AAPL 10-K filings", params: {filing_type: "10-K", limit: 4}
      - agent: earnings_tool, query: "AAPL earnings", params: {quarters: 4}
      - agent: news_tool, query: "Apple Inc news", params: {days: 30}

2025-12-10T14:32:15.350Z | INFO | agentorchestrator.execution | [req_abc123] Step content_prioritization completed in 68.00ms
    event: step_complete
    step: content_prioritization
    success: true
    duration_ms: 68.00

--------------------------------------------------------------------------------
STAGE 3: RESPONSE BUILDER (Parallel Agent Execution)
--------------------------------------------------------------------------------

2025-12-10T14:32:15.352Z | INFO | agentorchestrator.execution | [req_abc123] Starting step: response_builder
    event: step_start
    step: response_builder

2025-12-10T14:32:15.355Z | INFO | agentorchestrator.agents | Executing 3 agents in parallel
    agents: [sec_tool, earnings_tool, news_tool]

  ┌─────────────────────────────────────────────────────────────────────────────
  │ PARALLEL AGENT EXECUTION
  ├─────────────────────────────────────────────────────────────────────────────
  │
  │ [sec_tool]      ████████████████████░░░░░░░░░░  650ms  ✓ 4 filings
  │ [earnings_tool] ████████████░░░░░░░░░░░░░░░░░░  420ms  ✓ 4 quarters  
  │ [news_tool]     ██████████████████████████████  890ms  ✓ 12 articles
  │
  └─────────────────────────────────────────────────────────────────────────────

2025-12-10T14:32:16.245Z | INFO | agentorchestrator.agents | Agent execution complete
    agents_succeeded: 3
    agents_failed: 0
    total_duration_ms: 890  (bounded by slowest)

2025-12-10T14:32:16.250Z | DEBUG | agentorchestrator.chain.cmpt | Combining agent chunks
    sec_tool: 15,234 chars
    earnings_tool: 8,456 chars
    news_tool: 22,891 chars

2025-12-10T14:32:16.255Z | INFO | agentorchestrator.middleware.summarizer | Summarizing content
    strategy: MAP_REDUCE
    input_tokens: 12,450
    
2025-12-10T14:32:17.100Z | INFO | agentorchestrator.middleware.summarizer | Summarization complete
    output_tokens: 2,340
    reduction_ratio: 81%

2025-12-10T14:32:17.105Z | INFO | agentorchestrator.llm | Extracting financial metrics via LCEL chain
    chain: financial_metrics_chain
    model: gpt-4o
    retries_configured: 3

2025-12-10T14:32:18.500Z | INFO | agentorchestrator.llm | Financial metrics extracted
    duration_ms: 1395
    fields_extracted: [revenue, eps, stock_price, margins, guidance]

2025-12-10T14:32:18.505Z | INFO | agentorchestrator.llm | Generating strategic analysis via LCEL chain
    chain: strategic_analysis_chain
    model: gpt-4o

2025-12-10T14:32:19.800Z | INFO | agentorchestrator.llm | Strategic analysis complete
    duration_ms: 1295
    swot_items: {strengths: 4, weaknesses: 2, opportunities: 3, threats: 2}

2025-12-10T14:32:19.850Z | INFO | agentorchestrator.execution | [req_abc123] Step response_builder completed in 4498.00ms
    event: step_complete
    step: response_builder
    success: true
    duration_ms: 4498.00

================================================================================
                              CHAIN COMPLETE
================================================================================

2025-12-10T14:32:19.852Z | INFO | agentorchestrator.chain.cmpt | Chain completed
    request_id: req_abc123
    chain: cmpt_chain
    success: true
    total_duration_ms: 4729
    steps_executed: 3
    steps_succeeded: 3
    steps_failed: 0

TIMING BREAKDOWN:
    ├── context_builder:        155ms  (3.3%)
    ├── content_prioritization:  68ms  (1.4%)
    └── response_builder:      4498ms (95.3%)
        ├── agent_execution:    890ms
        ├── summarization:      845ms
        ├── financial_metrics: 1395ms
        └── strategic_analysis:1295ms

OUTPUT SUMMARY:
    company: Apple Inc (AAPL)
    financial_metrics: ✓
    strategic_analysis: ✓ (4 strengths, 2 weaknesses, 3 opportunities, 2 threats)
    prepared_content: 2,340 chars
Scenario 2: Partial Agent Failure (Resilient)
================================================================================
                    CMPT CHAIN - PARTIAL FAILURE (RECOVERED)
================================================================================

2025-12-10T14:35:00.000Z | INFO | agentorchestrator.chain.cmpt | Chain started
    request_id: req_def456
    chain: cmpt_chain
    input: {"company": "Tesla Inc"}

[... context_builder and content_prioritization succeed ...]

--------------------------------------------------------------------------------
STAGE 3: RESPONSE BUILDER (Partial Agent Failure)
--------------------------------------------------------------------------------

2025-12-10T14:35:00.500Z | INFO | agentorchestrator.agents | Executing 3 agents in parallel

  ┌─────────────────────────────────────────────────────────────────────────────
  │ PARALLEL AGENT EXECUTION (with failures)
  ├─────────────────────────────────────────────────────────────────────────────
  │
  │ [sec_tool]      ████████████████░░░░░░░░░░░░░░  520ms  ✓ 3 filings
  │ [earnings_tool] ██████░░░░░░░░░░░░░░░░░░░░░░░░  180ms  ✗ TIMEOUT
  │                 ↳ Retry 1/3...
  │                 ██████░░░░░░░░░░░░░░░░░░░░░░░░  200ms  ✗ TIMEOUT  
  │                 ↳ Retry 2/3...
  │                 ██████░░░░░░░░░░░░░░░░░░░░░░░░  210ms  ✗ TIMEOUT
  │                 ↳ Circuit breaker: OPEN (3 failures)
  │ [news_tool]     ██████████████████████████████  780ms  ✓ 8 articles
  │
  └─────────────────────────────────────────────────────────────────────────────

2025-12-10T14:35:01.890Z | WARN | agentorchestrator.agents.resilient | Agent failed after retries
    agent: earnings_tool
    attempts: 3
    last_error: "TimeoutError: Agent timed out after 10.0s"
    circuit_state: OPEN

2025-12-10T14:35:01.895Z | INFO | agentorchestrator.agents | Agent execution complete (partial)
    agents_succeeded: 2
    agents_failed: 1
    failed_agents: [earnings_tool]
    partial_success: true

2025-12-10T14:35:01.900Z | WARN | agentorchestrator.chain.cmpt | Proceeding with partial data
    missing_sources: [earnings_tool]
    available_sources: [sec_tool, news_tool]

[... LLM extraction continues with available data ...]

================================================================================
                              CHAIN COMPLETE (PARTIAL)
================================================================================

2025-12-10T14:35:05.000Z | INFO | agentorchestrator.chain.cmpt | Chain completed
    request_id: req_def456
    success: true
    partial_success: true
    total_duration_ms: 5000

AGENT STATUS:
    ├── sec_tool:      ✓ SUCCESS (520ms, 3 items)
    ├── earnings_tool: ✗ FAILED (circuit open after 3 retries)
    └── news_tool:     ✓ SUCCESS (780ms, 8 items)

⚠️  WARNING: Results may be incomplete due to agent failures
    Missing data: Earnings estimates, EPS beat/miss history
Scenario 3: LLM Fallback Triggered
================================================================================
                    CMPT CHAIN - LLM FALLBACK TRIGGERED
================================================================================

[... agents execute successfully ...]

2025-12-10T14:40:15.000Z | INFO | agentorchestrator.llm | Extracting financial metrics via LCEL chain
    chain: financial_metrics_chain
    primary_model: gpt-4o
    fallback_model: claude-sonnet-4-20250514

2025-12-10T14:40:16.500Z | WARN | agentorchestrator.llm | Primary LLM failed, trying fallback
    primary_error: "RateLimitError: Rate limit exceeded"
    fallback_model: claude-sonnet-4-20250514

2025-12-10T14:40:18.200Z | INFO | agentorchestrator.llm | Financial metrics extracted (via fallback)
    model_used: claude-sonnet-4-20250514
    duration_ms: 3200
    fallback_triggered: true
Scenario 4: Circuit Breaker Opens
================================================================================
                    CMPT CHAIN - CIRCUIT BREAKER PROTECTION
================================================================================

2025-12-10T14:45:00.000Z | INFO | agentorchestrator.agents | Executing agents

2025-12-10T14:45:00.001Z | WARN | agentorchestrator.utils.circuit_breaker | Circuit breaker OPEN
    agent: sec_tool
    state: OPEN
    failures: 5
    recovery_timeout: 30s
    last_failure: "ConnectionError: API unreachable"

2025-12-10T14:45:00.002Z | INFO | agentorchestrator.agents.resilient | Skipping agent (circuit open)
    agent: sec_tool
    reason: "Circuit breaker open, will retry in 25s"

  ┌─────────────────────────────────────────────────────────────────────────────
  │ AGENT EXECUTION (circuit breaker active)
  ├─────────────────────────────────────────────────────────────────────────────
  │
  │ [sec_tool]      ⊘ CIRCUIT OPEN (skipped)
  │ [earnings_tool] ████████████████████░░░░░░░░░░  650ms  ✓
  │ [news_tool]     ██████████████████████████████  890ms  ✓
  │
  └─────────────────────────────────────────────────────────────────────────────

2025-12-10T14:45:01.550Z | INFO | agentorchestrator.agents | Execution complete
    agents_succeeded: 2
    agents_skipped: 1 (circuit open)
    circuit_breakers:
      sec_tool: OPEN (recovery in 25s)
      earnings_tool: CLOSED
      news_tool: CLOSED
Scenario 5: JSON Structured Logs (Production)
When json_output=True:
{"timestamp":"2025-12-10T14:50:00.123Z","level":"info","logger":"agentorchestrator.chain.cmpt","event":"chain_started","request_id":"req_xyz789","chain":"cmpt_chain","total_steps":3}
{"timestamp":"2025-12-10T14:50:00.125Z","level":"info","logger":"agentorchestrator.execution","event":"step_start","request_id":"req_xyz789","step":"context_builder"}
{"timestamp":"2025-12-10T14:50:00.280Z","level":"info","logger":"agentorchestrator.execution","event":"step_complete","request_id":"req_xyz789","step":"context_builder","success":true,"duration_ms":155.0}
{"timestamp":"2025-12-10T14:50:00.282Z","level":"info","logger":"agentorchestrator.execution","event":"step_start","request_id":"req_xyz789","step":"content_prioritization"}
{"timestamp":"2025-12-10T14:50:00.350Z","level":"info","logger":"agentorchestrator.execution","event":"step_complete","request_id":"req_xyz789","step":"content_prioritization","success":true,"duration_ms":68.0}
{"timestamp":"2025-12-10T14:50:00.352Z","level":"info","logger":"agentorchestrator.execution","event":"step_start","request_id":"req_xyz789","step":"response_builder"}
{"timestamp":"2025-12-10T14:50:00.355Z","level":"info","logger":"agentorchestrator.agents","event":"parallel_execution_start","request_id":"req_xyz789","agents":["sec_tool","earnings_tool","news_tool"]}
{"timestamp":"2025-12-10T14:50:01.245Z","level":"info","logger":"agentorchestrator.agents","event":"parallel_execution_complete","request_id":"req_xyz789","agents_succeeded":3,"agents_failed":0,"duration_ms":890}
{"timestamp":"2025-12-10T14:50:04.850Z","level":"info","logger":"agentorchestrator.execution","event":"step_complete","request_id":"req_xyz789","step":"response_builder","success":true,"duration_ms":4498.0}
{"timestamp":"2025-12-10T14:50:04.852Z","level":"info","logger":"agentorchestrator.chain.cmpt","event":"chain_complete","request_id":"req_xyz789","success":true,"total_duration_ms":4729,"steps_executed":3}
How to Enable These Logs
from agentorchestrator import AgentOrchestrator, configure_logging
from agentorchestrator.middleware import LoggerMiddleware
import logging

# Configure logging
configure_logging(
    level="DEBUG",        # DEBUG for development, INFO for production
    json_output=False,    # True for production (structured JSON)
)

# Create orchestrator with logging middleware
ao = AgentOrchestrator(name="cmpt")

ao.use_middleware(LoggerMiddleware(
    level=logging.INFO,
    include_context=True,   # Log context keys
    include_output=True,    # Log output previews
    max_output_length=500,  # Truncate large outputs
))

# Run chain - logs will appear automatically
result = await ao.launch("cmpt_chain", {"company": "Apple Inc"})
The framework automatically logs:
Chain start/complete with timing
Each step start/complete with duration
Agent execution (parallel, with individual timings)
Retries and failures
Circuit breaker state changes
LLM chain invocations and fallbacks
Summarization metrics (token counts, reduction ratios)