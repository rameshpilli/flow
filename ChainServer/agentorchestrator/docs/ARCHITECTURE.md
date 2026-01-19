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
│  │  @ao.    │    │  @ao.    │    │  @ao.    │                  │
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
│                        Chain Execution Flow                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   ao.launch("my_chain", initial_data)                             │
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
│   ├── ao.py         # AgentOrchestrator main class
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

## Multi-Agent Squad Module

The Squad module provides native multi-agent orchestration that works with corporate LLM Gateway (OAuth-enabled).

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Multi-Agent Squad Module                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                  MultiAgentOrchestrator                          │    │
│  │  • Agent registration                                            │    │
│  │  • Request routing                                               │    │
│  │  • Session management                                            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    LLMGatewayClassifier                          │    │
│  │  • Intent classification                                         │    │
│  │  • Agent selection                                               │    │
│  │  • Confidence scoring                                            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│         ┌────────────────────┼────────────────────┐                     │
│         │                    │                    │                      │
│         ▼                    ▼                    ▼                      │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐             │
│  │ LLMGateway  │      │ LLMGateway  │      │ Supervisor  │             │
│  │   Agent 1   │      │   Agent 2   │      │   Agent     │             │
│  └─────────────┘      └─────────────┘      └──────┬──────┘             │
│                                                   │                      │
│                                            ┌──────┴──────┐              │
│                                            │  Team of    │              │
│                                            │  Agents     │              │
│                                            └─────────────┘              │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      ChatStorage                                 │    │
│  │  • InMemoryChatStorage (development)                            │    │
│  │  • RedisChatStorage (production)                                │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
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

### Usage Example

```python
from agentorchestrator.squad import (
    MultiAgentOrchestrator,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
    SupervisorAgent,
    SupervisorAgentOptions,
    LLMGatewayClassifier,
    LLMGatewayClassifierOptions,
    InMemoryChatStorage,
)

# Create specialist agents
tech_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="TechAgent",
    description="Handles technical questions",
    system_prompt="You are a helpful technical assistant.",
))

finance_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="FinanceAgent",
    description="Handles financial queries",
    system_prompt="You are a helpful financial analyst.",
))

# Create orchestrator
orchestrator = MultiAgentOrchestrator(
    classifier=LLMGatewayClassifier(LLMGatewayClassifierOptions()),
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

## Separation of Concerns (6-Layer Model)

For complex deployments, consider organizing code into these layers:

### Layer 1: Orchestration Core
```
core/
├── orchestrator.py      # Main class
├── dag.py               # DAG execution
├── context.py           # Context management
├── registry.py          # Component registration
└── resources.py         # Resource lifecycle
```

### Layer 2: Routing & Intent
```
routing/
├── classifier.py        # Intent classification
├── router.py            # Request routing
└── planner.py           # Execution planning
```

### Layer 3: Tool & Agent Execution
```
execution/
├── agent_executor.py    # Agent execution
├── tool_executor.py     # Tool execution
└── parallel.py          # Parallel execution
```

### Layer 4: Memory & Storage
```
memory/
├── context_store.py     # Context persistence
├── chat_storage.py      # Conversation storage
└── run_store.py         # Checkpoint storage
```

### Layer 5: Response Formatting
```
response/
├── formatter.py         # Output formatting
├── citation.py          # Citation handling
└── streaming.py         # Streaming support
```

### Layer 6: Observability
```
observability/
├── metrics.py           # Metrics collection
├── tracing.py           # Distributed tracing
├── logging.py           # Structured logging
└── health.py            # Health checks
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
- [REQUIREMENTS.md](REQUIREMENTS.md) - Dependencies & setup
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
- [examples/supervisor_chain.py](../examples/supervisor_chain.py) - Multi-agent example
