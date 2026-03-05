# AgentOrchestrator Architecture

## Overview

AgentOrchestrator is a DAG-based chain orchestration framework. It provides decorator-driven registration, automatic dependency resolution, and production-grade resilience.

---

## Core Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AgentOrchestrator                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │   Agents    │    │    Steps    │    │   Chains    │                 │
│  │  @ao.       │    │  @ao.       │    │  @ao.       │                 │
│  │   agent()   │    │   step()    │    │   chain()   │                 │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                 │
│         │                  │                  │                         │
│         ▼                  ▼                  ▼                         │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │                    Registry System                       │           │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │           │
│  │  │AgentRegistry│  │StepRegistry │  │ChainRegistry│      │           │
│  │  └─────────────┘  └─────────────┘  └─────────────┘      │           │
│  └─────────────────────────────────────────────────────────┘           │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │                    DAG Executor                          │           │
│  │  • Dependency resolution                                 │           │
│  │  • Parallel execution                                    │           │
│  │  • Retry & circuit breaker                               │           │
│  │  • True fail-fast cancellation                           │           │
│  └─────────────────────────────────────────────────────────┘           │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │                    Middleware Stack                      │           │
│  │  LoggerMiddleware → CacheMiddleware → SummarizerMiddleware          │
│  └─────────────────────────────────────────────────────────┘           │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │                    ChainContext                          │           │
│  │  • Scoped storage (step/chain/global)                    │           │
│  │  • Token tracking                                        │           │
│  │  • Step results                                          │           │
│  └─────────────────────────────────────────────────────────┘           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## State Machine Diagrams

### Chain Execution State Machine

```
                              ┌─────────────┐
                              │   CREATED   │
                              └──────┬──────┘
                                     │ launch()
                                     ▼
                              ┌─────────────┐
                              │ VALIDATING  │
                              └──────┬──────┘
                                     │ validation passed
                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                         EXECUTING                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │    ┌─────────┐     ┌─────────┐     ┌─────────┐              │ │
│  │    │STEP_WAIT│────▶│STEP_RUN │────▶│STEP_DONE│              │ │
│  │    └─────────┘     └────┬────┘     └─────────┘              │ │
│  │                         │                                    │ │
│  │                    step failed                               │ │
│  │                         │                                    │ │
│  │                         ▼                                    │ │
│  │                   ┌───────────┐                              │ │
│  │                   │STEP_RETRY │───▶ (retry limit)            │ │
│  │                   └───────────┘                              │ │
│  │                                                              │ │
│  └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────┬──────────────────────────────────────┘
                            │
           ┌────────────────┼────────────────┐
           │                │                │
           ▼                ▼                ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │  COMPLETED  │  │   FAILED    │  │  CANCELLED  │
    └─────────────┘  └─────────────┘  └─────────────┘
```

### Circuit Breaker State Machine

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    │         success_count++             │
                    ▼                                     │
             ┌─────────────┐                              │
             │             │                              │
     ───────▶│   CLOSED    │◀─────────────────────────────┘
             │             │         success_threshold reached
             └──────┬──────┘
                    │
                    │ failure_count >= failure_threshold
                    │
                    ▼
             ┌─────────────┐
             │             │
             │    OPEN     │────────────────────┐
             │             │                    │
             └──────┬──────┘                    │
                    │                           │
                    │ recovery_timeout elapsed  │ request arrives
                    │                           │ (fail immediately)
                    ▼                           │
             ┌─────────────┐                    │
             │             │                    │
             │  HALF_OPEN  │◀───────────────────┘
             │             │     (after timeout)
             └──────┬──────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
   success                   failure
        │                       │
        ▼                       ▼
   → CLOSED                  → OPEN
```

### Step Execution State Machine

```
     ┌──────────────┐
     │   PENDING    │
     └───────┬──────┘
             │ dependencies satisfied
             ▼
     ┌──────────────┐
     │   WAITING    │ ──────────────────────────┐
     └───────┬──────┘                           │
             │ acquired execution slot           │ chain cancelled
             ▼                                   │
     ┌──────────────┐                           │
     │   RUNNING    │────────────┐              │
     └───────┬──────┘            │              │
             │                   │              ▼
    ┌────────┴────────┐     step threw     ┌──────────────┐
    │                 │     exception      │  CANCELLED   │
    ▼                 ▼          │         └──────────────┘
┌────────┐      ┌──────────┐    │
│SUCCESS │      │ RETRYING │◀───┘
└────────┘      └────┬─────┘
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
    retry succeeds        retry exhausted
          │                     │
          ▼                     ▼
     → SUCCESS              ┌────────┐
                            │ FAILED │
                            └────────┘
```

### Agent Request Processing State Machine

```
                    ┌──────────────┐
        request ───▶│   RECEIVED   │
                    └───────┬──────┘
                            │
                            ▼
                    ┌──────────────┐
                    │  CLASSIFYING │
                    └───────┬──────┘
                            │ agent selected
                            ▼
                    ┌──────────────┐
                    │  PROCESSING  │
                    └───────┬──────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
     ┌──────────────┐            ┌──────────────┐
     │ TOOL_CALLING │            │  GENERATING  │
     └───────┬──────┘            └───────┬──────┘
              │ tool results              │
              └─────────────┬─────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │   COMPLETE   │
                    └──────────────┘
```

### Context Isolation State Machine

```
     ┌───────────────┐
     │   ISOLATED    │ ◀──────────────────────────────────┐
     └───────┬───────┘                                    │
             │ create_namespace()                         │
             ▼                                            │
     ┌───────────────┐                                    │
     │   NAMESPACE   │                                    │
     │   CREATED     │                                    │
     └───────┬───────┘                                    │
             │                                            │
    ┌────────┴────────────────┐                          │
    │                         │                          │
    ▼                         ▼                          │
┌───────────┐           ┌───────────┐                    │
│   LOCAL   │           │  SHARED   │                    │
│   WRITE   │           │   READ    │                    │
└─────┬─────┘           └─────┬─────┘                    │
      │                       │                          │
      └───────────┬───────────┘                          │
                  │                                       │
                  ▼                                       │
          ┌───────────────┐                              │
          │  RESULT_SET   │                              │
          └───────┬───────┘                              │
                  │ namespace closed                     │
                  ▼                                       │
          ┌───────────────┐                              │
          │  AGGREGATING  │ ─────────────────────────────┘
          └───────┬───────┘      next request
                  │
                  ▼
          ┌───────────────┐
          │   COMPLETE    │
          └───────────────┘
```

---

## Component Details

### 1. AgentOrchestrator (Entry Point)

The main orchestrator that provides:
- Decorator registration (`@ao.step`, `@ao.agent`, `@ao.chain`)
- Chain execution (`ao.launch()`, `ao.run()`)
- Middleware management (`ao.use()`)
- Resource management (`ao.register_resource()`)

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")
```

### 2. Registry System

Thread-safe registries for all components:

| Registry | Purpose |
|----------|---------|
| `AgentRegistry` | Data fetching agents |
| `StepRegistry` | Processing steps with dependencies |
| `ChainRegistry` | Chain definitions |

### 3. DAG Executor

Executes chains with:
- **Dependency Resolution**: Topological sort of steps
- **Parallel Execution**: Independent steps run concurrently
- **Parallel Groups**: Explicit execution ordering
- **Per-Step Concurrency**: `max_concurrency` limits
- **Retry Logic**: Configurable retry with backoff
- **Circuit Breaker**: Failure protection for external calls
- **Fail-Fast**: Immediate cancellation on first failure

### 4. ChainContext

Shared state across steps:

```python
@ao.step(name="my_step")
async def my_step(ctx: ChainContext):
    # Read data
    value = ctx.get("key", default=None)

    # Write data (scoped)
    ctx.set("output", data, scope=ContextScope.CHAIN)

    return {"result": value}
```

**Scopes:**
- `STEP`: Cleared after step completes
- `CHAIN`: Persists throughout chain execution (default)
- `GLOBAL`: Persists across multiple chains

### 5. Middleware

Pluggable processing hooks:

| Middleware | Purpose |
|------------|---------|
| `LoggerMiddleware` | Structured logging |
| `CacheMiddleware` | Response caching |
| `SummarizerMiddleware` | LLM-based summarization |
| `TokenManagerMiddleware` | Token budget management |
| `OffloadMiddleware` | Redis payload offloading |
| `RateLimiterMiddleware` | Request rate limiting |
| `MetricsMiddleware` | Execution metrics |

---

## Execution Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Chain Execution Flow                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ao.launch("my_chain", initial_data)                                │
│                      │                                               │
│                      ▼                                               │
│   ┌──────────────────────────────────────┐                          │
│   │  1. Input Validation                  │                          │
│   │     (Pydantic models if defined)      │                          │
│   └──────────────────────────────────────┘                          │
│                      │                                               │
│                      ▼                                               │
│   ┌──────────────────────────────────────┐                          │
│   │  2. Create ChainContext               │                          │
│   │     - request_id                      │                          │
│   │     - initial_data                    │                          │
│   └──────────────────────────────────────┘                          │
│                      │                                               │
│                      ▼                                               │
│   ┌──────────────────────────────────────┐                          │
│   │  3. Build DAG                         │                          │
│   │     - Resolve dependencies            │                          │
│   │     - Create execution plan           │                          │
│   └──────────────────────────────────────┘                          │
│                      │                                               │
│                      ▼                                               │
│   ┌──────────────────────────────────────┐                          │
│   │  4. Execute Steps (in order)          │                          │
│   │                                       │                          │
│   │     For each step:                    │                          │
│   │     ├─ middleware.before()            │                          │
│   │     ├─ step_handler(ctx)              │                          │
│   │     ├─ middleware.after()             │                          │
│   │     └─ ctx.add_result(StepResult)     │                          │
│   │                                       │                          │
│   │     Parallel steps run concurrently   │                          │
│   └──────────────────────────────────────┘                          │
│                      │                                               │
│                      ▼                                               │
│   ┌──────────────────────────────────────┐                          │
│   │  5. Return Results                    │                          │
│   │     - All step outputs                │                          │
│   │     - Execution metadata              │                          │
│   │     - Error info (if any)             │                          │
│   └──────────────────────────────────────┘                          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Services Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Services Layer                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     LLMGatewayClient                             │    │
│  │  • OAuth token management (auto-refresh)                         │    │
│  │  • OpenAI-compatible API                                         │    │
│  │  • Structured output with Pydantic                               │    │
│  │  • Streaming support                                             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│         ┌────────────────────┼────────────────────┐                     │
│         │                    │                    │                      │
│         ▼                    ▼                    ▼                      │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐             │
│  │   Redis     │      │   Vector    │      │    Mem0     │             │
│  │  Service    │      │   Store     │      │   Memory    │             │
│  │             │      │             │      │             │             │
│  │ • Caching   │      │ • Upsert    │      │ • Semantic  │             │
│  │ • Sessions  │      │ • Query     │      │   search    │             │
│  │ • Offload   │      │ • RAG       │      │ • Cross-    │             │
│  │             │      │             │      │   session   │             │
│  └─────────────┘      └─────────────┘      └─────────────┘             │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Context Isolation for Multi-Agent Systems

Prevents context pollution when running multiple agents in parallel:

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Context Isolation Architecture                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │              Coordinator Context (SupervisorAgent)               │    │
│  │  ├─ request_id, user_query, execution_plan                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                    │ Creates isolated namespaces                         │
│        ┌───────────┼───────────┐                                        │
│        ↓           ↓           ↓                                        │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐                                  │
│   │ Agent 1 │ │ Agent 2 │ │ Agent 3 │                                  │
│   │Namespace│ │Namespace│ │Namespace│                                  │
│   │         │ │         │ │         │                                  │
│   │ - temp  │ │ - temp  │ │ - temp  │  ← Each agent has isolated      │
│   │ - data  │ │ - data  │ │ - data  │    working storage               │
│   │ - result│ │ - result│ │ - result│                                  │
│   └─────────┘ └─────────┘ └─────────┘                                  │
│        │           │           │                                        │
│        └───────────┴───────────┘                                        │
│                    ↓                                                     │
│        ┌─────────────────────────┐                                      │
│        │    ResultAggregator     │                                      │
│        │ - Collect results       │                                      │
│        │ - Detect conflicts      │                                      │
│        │ - Synthesize/merge      │                                      │
│        └─────────────────────────┘                                      │
│                    ↓                                                     │
│              Final Response                                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Aggregation Strategies

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `SYNTHESIZE` | LLM creates narrative from all results | Research, reports |
| `MERGE` | Deep merge dicts/lists | Structured data |
| `PRIORITIZE` | Select highest confidence result | Single-answer questions |
| `VOTE` | Majority voting | Discrete choices |
| `CHAIN` | Sequential refinement | Iterative improvement |

---

## Production Features

### Resilience

```
┌────────────────────────────────────────────┐
│            Circuit Breaker Flow            │
├────────────────────────────────────────────┤
│  CLOSED ──(failures)──▶ OPEN               │
│     ▲                      │               │
│     │                      │ (timeout)     │
│     │                      ▼               │
│  (success)◀─────────── HALF_OPEN           │
└────────────────────────────────────────────┘
```

### Large Payload Handling

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Offload Middleware Flow                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Step Output (>100KB)                                              │
│         │                                                           │
│         ▼                                                           │
│   ┌──────────────────┐    ┌──────────────────┐                     │
│   │ Extract Key      │    │ Store in Redis   │                     │
│   │ Fields & Summary │───▶│ (with TTL)       │                     │
│   └──────────────────┘    └──────────────────┘                     │
│         │                          │                                │
│         ▼                          ▼                                │
│   ┌────────────────────────────────────────┐                       │
│   │ ContextRef (lightweight reference)      │                       │
│   │ ├─ ref_id: "ctx:abc123"                │                       │
│   │ ├─ summary: "Q4 2024 earnings..."      │                       │
│   │ ├─ key_fields: {ticker: "AAPL", ...}   │                       │
│   │ └─ original_size: 1.2MB                │                       │
│   └────────────────────────────────────────┘                       │
│                                                                     │
│   Context stays lightweight (~500 bytes per ref)                    │
│   Full data retrievable via: store.retrieve(ref)                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
agentorchestrator/
├── __init__.py              # Public API exports
├── config.py                # Configuration management
├── cli.py                   # Command-line interface
│
├── core/
│   ├── orchestrator.py      # AgentOrchestrator main class
│   ├── context.py           # ChainContext & scopes
│   ├── registry.py          # Component registries
│   ├── dag.py               # DAG builder & executor
│   ├── decorators.py        # @step, @agent, @chain
│   ├── resources.py         # Dependency injection
│   ├── context_store.py     # Redis offloading
│   ├── run_store.py         # Resumability checkpoints
│   ├── validation.py        # Input/output contracts
│   ├── serializers.py       # Context serialization
│   ├── versioning.py        # Chain versioning
│   └── visualize.py         # DAG visualization
│
├── middleware/
│   ├── base.py              # Middleware base class
│   ├── cache.py             # Response caching
│   ├── logger.py            # Structured logging
│   ├── summarizer.py        # LLM summarization
│   ├── token_manager.py     # Token budgets
│   ├── offload.py           # Payload offloading
│   ├── rate_limiter.py      # Rate limiting
│   └── metrics.py           # Execution metrics
│
├── agents/
│   ├── base.py              # BaseAgent, ResilientAgent, AgentResult
│   └── data_agents.py       # Pre-built data fetching agents
│
├── services/
│   ├── __init__.py          # Service exports
│   ├── llm_gateway.py       # LLMGatewayClient with OAuth
│   ├── redis.py             # RedisService
│   ├── vector_store.py      # VectorStoreService for RAG
│   └── mem0.py              # Mem0Memory (semantic memory)
│
├── squad/                   # Multi-agent orchestration
│   ├── __init__.py          # Squad exports
│   ├── orchestrator.py      # MultiAgentOrchestrator
│   ├── agents/
│   │   ├── base.py          # Agent base class
│   │   ├── llm_gateway_agent.py  # LLMGatewayAgent
│   │   └── supervisor.py    # SupervisorAgent
│   ├── classifiers/
│   │   └── llm_gateway.py   # LLMGatewayClassifier
│   ├── context/
│   │   ├── isolation.py     # ContextIsolationManager
│   │   └── aggregator.py    # ResultAggregator
│   └── storage/
│       ├── base.py          # ChatStorage interface
│       ├── memory.py        # InMemoryChatStorage
│       └── redis.py         # RedisChatStorage
│
├── connectors/              # MCP connectors
├── utils/                   # Logging, tracing, circuit breaker, caching
├── testing/                 # Test utilities
└── examples/                # Example implementations
    ├── getting_started/     # Hello world, simple chain, parallel
    ├── memory/              # Chat storage, semantic memory
    ├── rag/                 # RAG pipelines
    └── agents/              # Multi-agent patterns
```

---

## Multi-Agent Squad Module

The Squad module provides native multi-agent orchestration that works with corporate LLM Gateway (OAuth-enabled).

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Multi-Agent Squad Module                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                  MultiAgentOrchestrator                          │   │
│  │  • Agent registration                                            │   │
│  │  • Request routing                                               │   │
│  │  • Session management                                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    LLMGatewayClassifier                          │   │
│  │  • Intent classification                                         │   │
│  │  • Agent selection                                               │   │
│  │  • Confidence scoring                                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│         ┌────────────────────┼────────────────────┐                    │
│         │                    │                    │                     │
│         ▼                    ▼                    ▼                     │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐            │
│  │ LLMGateway  │      │ LLMGateway  │      │ Supervisor  │            │
│  │   Agent 1   │      │   Agent 2   │      │   Agent     │            │
│  └─────────────┘      └─────────────┘      └──────┬──────┘            │
│                                                   │                     │
│                                            ┌──────┴──────┐             │
│                                            │  Team of    │             │
│                                            │  Agents     │             │
│                                            └─────────────┘             │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      ChatStorage                                 │   │
│  │  • InMemoryChatStorage (development)                             │   │
│  │  • RedisChatStorage (production)                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Components

| Component | Purpose | Location |
|-----------|---------|----------|
| `MultiAgentOrchestrator` | Main orchestrator for agent routing | `squad/orchestrator.py` |
| `LLMGatewayAgent` | Agent using LLMGatewayClient | `squad/agents/llm_gateway_agent.py` |
| `SupervisorAgent` | Coordinates team of specialist agents | `squad/agents/supervisor.py` |
| `LLMGatewayClassifier` | Intent classification | `squad/classifiers/llm_gateway.py` |
| `ChatStorage` | Conversation persistence | `squad/storage/` |
| `ContextIsolationManager` | Multi-agent context isolation | `squad/context/isolation.py` |
| `ResultAggregator` | Multi-agent result aggregation | `squad/context/aggregator.py` |

### Usage Example

```python
from agentorchestrator.squad import (
    MultiAgentOrchestrator,
    LLMGatewayAgent,
    SupervisorAgent,
    LLMGatewayClassifier,
)
from agentorchestrator.squad.storage import InMemoryChatStorage
from agentorchestrator.services import LLMGatewayClient

# Create LLM client
client = LLMGatewayClient.from_env()

# Create specialist agents
tech_agent = LLMGatewayAgent(
    name="TechAgent",
    description="Handles technical questions",
    system_prompt="You are a helpful technical assistant.",
    llm_client=client,
)

finance_agent = LLMGatewayAgent(
    name="FinanceAgent",
    description="Handles financial queries",
    system_prompt="You are a helpful financial analyst.",
    llm_client=client,
)

# Create orchestrator
orchestrator = MultiAgentOrchestrator(
    classifier=LLMGatewayClassifier(llm_client=client),
    storage=InMemoryChatStorage(),
)
orchestrator.add_agent(tech_agent)
orchestrator.add_agent(finance_agent)

# Route request
response = await orchestrator.route_request(
    user_input="How do I optimize Python code?",
    user_id="user-123",
    session_id="session-456",
)
```

### Supervisor Pattern

The SupervisorAgent coordinates a team of specialists:

```
                    User Query
                         │
                         ▼
                ┌─────────────────┐
                │   Supervisor    │
                │   Lead Agent    │
                └────────┬────────┘
                         │
            ┌────────────┼────────────┐
            │            │            │
            ▼            ▼            ▼
     ┌──────────┐ ┌──────────┐ ┌──────────┐
     │ Agent 1  │ │ Agent 2  │ │ Agent N  │
     │(Parallel)│ │(Parallel)│ │(Parallel)│
     └────┬─────┘ └────┬─────┘ └────┬─────┘
          │            │            │
          └────────────┼────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │   Synthesize    │
              │   Responses     │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  Final Response │
              └─────────────────┘
```

---

## Integration: @ao Decorators with Squad

You can combine AgentOrchestrator's `@ao` decorators with the Squad module:

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.squad import MultiAgentOrchestrator as SquadOrchestrator

ao = AgentOrchestrator(name="hybrid_app")

# Register squad as a resource
@ao.resource("squad")
def create_squad():
    squad = SquadOrchestrator(...)
    squad.add_agent(...)
    return squad

# Use in a step
@ao.step(resources=["squad"])
async def route_query(ctx, squad):
    response = await squad.route_request(ctx.get("query"), ...)
    return {"response": response.output.get_text()}

@ao.chain(name="hybrid_chain")
class HybridChain:
    steps = ["route_query"]
```

See [examples/supervisor_chain.py](../examples/supervisor_chain.py) for a complete example.

---

## See Also

- [QUICKSTART.md](QUICKSTART.md) - Get started in 5 minutes
- [API.md](API.md) - Full API reference
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues
- [examples/](../examples/) - Example implementations
