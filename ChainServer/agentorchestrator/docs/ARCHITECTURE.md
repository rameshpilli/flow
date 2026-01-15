# AgentOrchestrator Architecture

## Overview

AgentOrchestrator is a DAG-based chain orchestration framework. It provides decorator-driven registration, automatic dependency resolution, and production-grade resilience.

---

## Core Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AgentOrchestrator                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │   Agents    │    │    Steps    │    │   Chains    │                  │
│  │  @forge.    │    │  @forge.    │    │  @forge.    │                  │
│  │   agent()   │    │   step()    │    │   chain()   │                  │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                  │
│         │                  │                  │                          │
│         ▼                  ▼                  ▼                          │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │                    Registry System                       │            │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │            │
│  │  │AgentRegistry│  │StepRegistry │  │ChainRegistry│     │            │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │            │
│  └─────────────────────────────────────────────────────────┘            │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │                    DAG Executor                          │            │
│  │  • Dependency resolution                                 │            │
│  │  • Parallel execution                                    │            │
│  │  • Retry & circuit breaker                              │            │
│  │  • True fail-fast cancellation                          │            │
│  └─────────────────────────────────────────────────────────┘            │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │                    Middleware Stack                      │            │
│  │  LoggerMiddleware → CacheMiddleware → SummarizerMiddleware           │
│  └─────────────────────────────────────────────────────────┘            │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │                    ChainContext                          │            │
│  │  • Scoped storage (step/chain/global)                   │            │
│  │  • Token tracking                                        │            │
│  │  • Step results                                          │            │
│  └─────────────────────────────────────────────────────────┘            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. AgentOrchestrator (Entry Point)

The main orchestrator that provides:
- Decorator registration (`@forge.step`, `@forge.agent`, `@forge.chain`)
- Chain execution (`forge.launch()`, `forge.run()`)
- Middleware management (`forge.use()`)
- Resource management (`forge.register_resource()`)

```python
from agentorchestrator import AgentOrchestrator

forge = AgentOrchestrator(name="my_app")
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
@forge.step(name="my_step")
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
│                        Chain Execution Flow                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   forge.launch("my_chain", initial_data)                             │
│                      │                                                │
│                      ▼                                                │
│   ┌──────────────────────────────────────┐                           │
│   │  1. Input Validation                  │                           │
│   │     (Pydantic models if defined)      │                           │
│   └──────────────────────────────────────┘                           │
│                      │                                                │
│                      ▼                                                │
│   ┌──────────────────────────────────────┐                           │
│   │  2. Create ChainContext               │                           │
│   │     - request_id                      │                           │
│   │     - initial_data                    │                           │
│   └──────────────────────────────────────┘                           │
│                      │                                                │
│                      ▼                                                │
│   ┌──────────────────────────────────────┐                           │
│   │  3. Build DAG                         │                           │
│   │     - Resolve dependencies            │                           │
│   │     - Create execution plan           │                           │
│   └──────────────────────────────────────┘                           │
│                      │                                                │
│                      ▼                                                │
│   ┌──────────────────────────────────────┐                           │
│   │  4. Execute Steps (in order)          │                           │
│   │                                       │                           │
│   │     For each step:                    │                           │
│   │     ├─ middleware.before()            │                           │
│   │     ├─ step_handler(ctx)              │                           │
│   │     ├─ middleware.after()             │                           │
│   │     └─ ctx.add_result(StepResult)     │                           │
│   │                                       │                           │
│   │     Parallel steps run concurrently   │                           │
│   └──────────────────────────────────────┘                           │
│                      │                                                │
│                      ▼                                                │
│   ┌──────────────────────────────────────┐                           │
│   │  5. Return Results                    │                           │
│   │     - All step outputs                │                           │
│   │     - Execution metadata              │                           │
│   │     - Error info (if any)             │                           │
│   └──────────────────────────────────────┘                           │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## CMPT Chain Architecture

The built-in Client Meeting Prep (CMPT) chain has 3 stages:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CMPT Chain Flow                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   INPUT: ChainRequest                                                    │
│   ├─ corporate_company_name: "Apple Inc"                                │
│   ├─ meeting_datetime: "2025-01-15T10:00:00Z"                           │
│   ├─ rbc_employee_email: "john.doe@rbc.com"                             │
│   └─ corporate_client_email: "jane.smith@apple.com"                     │
│                                                                          │
│                              │                                           │
│                              ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  STAGE 1: Context Builder                                        │   │
│   │  ─────────────────────────────────────────────────────────────  │   │
│   │  Extractors:                                                     │   │
│   │  ├─ extract_company_info    → CompanyInfo (ticker, industry)    │   │
│   │  ├─ extract_temporal_context → TemporalContext (fiscal year)    │   │
│   │  ├─ extract_rbc_persona     → PersonaInfo                       │   │
│   │  └─ extract_client_personas → List[PersonaInfo]                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  STAGE 2: Content Prioritization                                 │   │
│   │  ─────────────────────────────────────────────────────────────  │   │
│   │  Steps:                                                          │   │
│   │  ├─ prioritize_sources → Prioritized data sources               │   │
│   │  ├─ build_subqueries   → Agent-specific queries                 │   │
│   │  └─ allocate_tokens    → Token budget per source                │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  STAGE 3: Response Builder                                       │   │
│   │  ─────────────────────────────────────────────────────────────  │   │
│   │  Steps (parallel where possible):                                │   │
│   │  ├─ fetch_news_data      ─┐                                     │   │
│   │  ├─ fetch_sec_data        ├─ Parallel agent execution           │   │
│   │  ├─ fetch_earnings_data  ─┘                                     │   │
│   │  ├─ parse_agent_responses → Structure raw data                  │   │
│   │  ├─ build_prompts        → LLM prompts                          │   │
│   │  ├─ generate_financial_metrics ─┐                               │   │
│   │  ├─ generate_strategic_analysis ├─ Parallel LLM calls          │   │
│   │  └─ validate_metrics     → Verify against sources               │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│   OUTPUT: CMPTResult                                                     │
│   ├─ context_builder: {...}                                             │
│   ├─ content_prioritization: {...}                                      │
│   ├─ response_builder: {...}                                            │
│   └─ timings: {...}                                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Production Features

### Resilience

```
┌────────────────────────────────────────────┐
│            Circuit Breaker                  │
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
│                    Offload Middleware Flow                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Step Output (>100KB)                                               │
│         │                                                            │
│         ▼                                                            │
│   ┌──────────────────┐    ┌──────────────────┐                      │
│   │ Extract Key      │    │ Store in Redis   │                      │
│   │ Fields & Summary │───▶│ (with TTL)       │                      │
│   └──────────────────┘    └──────────────────┘                      │
│         │                          │                                 │
│         ▼                          ▼                                 │
│   ┌────────────────────────────────────────┐                        │
│   │ ContextRef (lightweight reference)      │                        │
│   │ ├─ ref_id: "ctx:abc123"                │                        │
│   │ ├─ summary: "Q4 2024 earnings..."      │                        │
│   │ ├─ key_fields: {ticker: "AAPL", ...}   │                        │
│   │ └─ original_size: 1.2MB                │                        │
│   └────────────────────────────────────────┘                        │
│                                                                      │
│   Context stays lightweight (~500 bytes per ref)                     │
│   Full data retrievable via: store.retrieve(ref)                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
agentorchestrator/
├── __init__.py          # Public API exports
├── config.py            # Configuration management
├── cli.py               # Command-line interface
│
├── core/
│   ├── forge.py         # AgentOrchestrator main class
│   ├── context.py       # ChainContext & scopes
│   ├── registry.py      # Component registries
│   ├── dag.py           # DAG builder & executor
│   ├── decorators.py    # @step, @agent, @chain
│   ├── resources.py     # Dependency injection
│   ├── context_store.py # Redis offloading
│   ├── run_store.py     # Resumability checkpoints
│   ├── validation.py    # Input/output contracts
│   ├── serializers.py   # Context serialization
│   ├── versioning.py    # Chain versioning
│   └── visualize.py     # DAG visualization
│
├── middleware/
│   ├── base.py          # Middleware base class
│   ├── cache.py         # Response caching
│   ├── logger.py        # Structured logging
│   ├── summarizer.py    # LLM summarization
│   ├── token_manager.py # Token budgets
│   ├── offload.py       # Payload offloading
│   ├── rate_limiter.py  # Rate limiting
│   └── metrics.py       # Execution metrics
│
├── agents/
│   ├── base.py          # BaseAgent, ResilientAgent
│   └── data_agents.py   # Pre-built agents
│
├── services/
│   ├── context_builder.py
│   ├── content_prioritization.py
│   ├── response_builder.py
│   ├── llm_gateway.py
│   └── models.py
│
├── chains/
│   └── cmpt.py          # CMPT chain implementation
│
├── plugins/             # Plugin system
├── connectors/          # MCP connectors
├── utils/               # Logging, tracing, config
├── testing/             # Test utilities
├── templates/           # Project scaffolding
└── examples/            # Example chains
```

---

## See Also

- [QUICKSTART.md](QUICKSTART.md) - Get started in 5 minutes
- [API.md](API.md) - Full API reference
- [REQUIREMENTS.md](REQUIREMENTS.md) - Dependencies & setup
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
