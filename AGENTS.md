# Agent Context: AgentOrchestrator Framework

> This file provides context for AI agents working on this codebase.
> It describes what we're building, current state, and how to work effectively with the code.

---

## What Is This Project?

We're building **AgentOrchestrator** - a production-grade, DAG-based agent orchestration framework. Think LangChain or LlamaIndex, but with:

- Decorator-driven API (like Dagster)
- Built-in services configured via environment variables
- Users just set their config and build agents - we handle dependencies

**Goal**: Users tap into our services, set env vars, and build agents from simple to complex.

---

## Repository Structure

```
flow/
├── agentorchestrator/         # THE FRAMEWORK (domain-agnostic)
│   ├── core/                  # Orchestrator, Context, DAG, Registry
│   │   ├── state.py           # StateStore (Pydantic state management)
│   │   └── event_bus.py       # EventBus (in-memory, Redis)
│   ├── middleware/            # Cache, Logger, Summarizer, TokenManager
│   ├── agents/                # BaseAgent, ResilientAgent, CompositeAgent
│   ├── services/              # LLMGatewayClient, VectorStoreService
│   ├── squad/                 # Multi-agent orchestration
│   │   ├── agents/            # LLMGatewayAgent, SupervisorAgent
│   │   ├── storage/           # ChatStorage (InMemory, Redis)
│   │   └── types.py           # AgentTool, AgentTools
│   ├── dsl/                   # Declarative pipeline builder
│   ├── connectors/            # MCPConnector
│   ├── plugins/               # Plugin discovery, capability schemas
│   ├── llm/                   # LCEL chain builders
│   ├── templates/             # Project scaffolding
│   ├── utils/                 # Logging, tracing
│   └── config.py              # Environment configuration
├── AGENTS.md                  # THIS FILE - agent context
└── .beads/                    # Issue tracking database
```

---

## Core Patterns You'll See

### 1. Decorator Registration
```python
ao = AgentOrchestrator()

@ao.step(name="fetch", produces=["data"])
async def fetch(ctx: ChainContext): ...

@ao.agent(name="my_agent", capabilities=["search"])
class MyAgent(BaseAgent): ...

@ao.chain(name="pipeline")
class Pipeline:
    steps = ["fetch", "process"]
```

### 2. Type-Safe State (NEW)
```python
from pydantic import BaseModel, Field
from agentorchestrator import Context

class PipelineState(BaseModel):
    counter: int = Field(default=0)
    items: list[str] = Field(default_factory=list)

@ao.step(name="process", state_model=PipelineState)
async def process(ctx: Context[PipelineState]):
    async with ctx.edit_state() as state:
        state.counter += 1  # Type-safe! IDE autocomplete!
    return {"count": ctx.state.counter}
```

### 3. Context Scopes
- `ContextScope.STEP` - Auto-cleaned after step (temp data)
- `ContextScope.CHAIN` - Lives for entire chain execution
- `ContextScope.GLOBAL` - Persists across executions

### 4. Event-Driven Workflows (NEW)
```python
@ao.event_handler("ResearchTask")
async def worker(ctx: Context, event: Event):
    # Process event and emit new ones
    return Event(type="Finding", payload={...})

await ao.run_event_loop(ctx)  # Process all events
```

### 5. Middleware Pipeline
Middleware wraps step execution: `before()` → step → `after()` / `on_error()`

### 6. Squad Multi-Agent
- `MultiAgentOrchestrator` - Routes to best agent
- `SupervisorAgent` - Coordinates a team of specialists
- `LLMGatewayAgent` - Single agent with LLM backend

---

## Key Files to Know

| When you need... | Look at... |
|-----------------|------------|
| Core orchestration | `core/orchestrator.py`, `core/dag.py` |
| Context management | `core/context.py` |
| Type-safe state | `core/state.py`, `core/context.py` |
| Event-driven workflows | `core/event_bus.py` |
| Step/chain decorators | `core/decorators.py` |
| Declarative pipelines | `dsl/pipeline.py` |
| Middleware base | `middleware/base.py` |
| **Agent reflection** | `middleware/reflection.py` |
| LLM client | `services/llm_gateway.py` |
| Vector store | `services/vector_store.py` |
| Multi-agent routing | `squad/orchestrator.py` |
| Supervisor pattern | `squad/agents/supervisor.py` |
| **ReAct pattern** | `agents/react.py` |
| **Tool registry** | `agents/tools.py` |
| Tool schemas | `plugins/capability.py`, `squad/types.py` |
| Tracing | `utils/tracing.py` |
| Config loading | `config.py` |
| Project templates | `templates/scaffolding.py` |
| **Deep research example** | `examples/deep_research_agent.py` |
| **Supervisor-in-chain** | `examples/supervisor_in_chain.py` |

---

## What's Implemented (Use These)

| Feature | Location | Notes |
|---------|----------|-------|
| DAG Execution | `core/dag.py` | Automatic parallelization with **Dynamic Steps** ✓ |
| Context Management | `core/context.py` | 3 scopes, thread-safe, token tracking |
| **Pydantic State** | `core/state.py` | Type-safe state with validation, atomic updates |
| **Event-Driven Workflows** | `core/event_bus.py` | Event handlers, pub/sub, Redis or in-memory |
| **Declarative DSL** | `dsl/pipeline.py` | Build pipelines without decorators |
| Middleware Pipeline | `middleware/` | Cache, Logger, Summarizer, TokenManager, etc. |
| LLM Integration | `services/llm_gateway.py` | OAuth + API key, structured output, **tiktoken** ✓ |
| Vector Store | `services/vector_store.py` | In-memory + **Cohere Compass** integration ✓ |
| Multi-Agent Routing | `squad/orchestrator.py` | Intent classification, **Agent Handoffs** ✓ |
| Supervisor Pattern | `squad/agents/supervisor.py` | Team coordination, validation |
| Shared Memory | `squad/storage/redis.py` | **Cross-agent shared context** ✓ |
| Secret Management | `services/secrets.py` | **HashiCorp Vault** + Env fallback ✓ |
| Resilience | `agents/resilient.py` | Timeout, retry, circuit breaker |
| Streaming | `squad/agents/` | LLM token streaming |
| OpenTelemetry | `utils/tracing.py` | Spans, traces, graceful fallback |
| Observability | `services/observability.py`| **Standardized service placeholder** ✓ |
| **ReAct Pattern** | `agents/react.py` | Thought→Action→Observation loop with tools ✓ |
| **Tool Registry** | `agents/tools.py` | Centralized tool discovery + built-in tools ✓ |
| **Agent Reflection** | `middleware/reflection.py` | `@reflect()` decorator, quality scoring, auto-revision ✓ |
| **Dynamic DAG** | `core/dag.py` | `__dynamic_steps__` with immediate execution ✓ |
| **Event Types** | `core/event_bus.py` | Agent/Tool events with `EventTypes` constants ✓ |
| **Run Isolation** | `core/orchestrator.py` | Event loop filters by `run_id` on shared buses ✓ |
| **Retry Jitter** | `core/dag.py` | ±25% jitter to prevent thundering herd ✓ |
| Async-safe Context | `core/context.py` | `async_set()` for concurrent parallel steps ✓ |

---

## Roadmap: What We're Building Towards

### Near-Term (High Priority)
| Feature | Why It Matters |
|---------|----------------|
| **Human-in-the-Loop Workflows** | Production approval workflows, Slack integration |
| **Memory Pattern Strategies** | Sliding window, summary, entity extraction for chat |
| **Workflow Debugger UI** | Visual debugging, breakpoints, real-time events |
| **Test Coverage Expansion** | Tests for EventBus, ReAct, Reflection components |

### Recently Implemented
| Feature | Location | Notes |
|---------|----------|-------|
| **Deep Research Agent** | `examples/deep_research_agent.py` | Multi-stage research with decomposition ✓ |
| **Agent Reflection** | `middleware/reflection.py` | `@reflect()` decorator, quality scoring ✓ |
| **Subchain Merge Mapping** | `core/orchestrator.py` | `merge_map` and `merge_mode` for safe merges ✓ |
| **Retry Jitter** | `core/dag.py` | ±25% jitter prevents thundering herd ✓ |
| **Event Loop Persistence** | `core/orchestrator.py` | `run_store` integration, `resume_event_loop()` ✓ |
| **Agent/Tool Events** | `core/event_bus.py` | `EventTypes`, `emit_agent_event()`, `emit_tool_event()` ✓ |
| **Run Isolation** | `core/orchestrator.py` | `isolate_run=True` filters by run_id ✓ |
| **Dynamic DAG** | `core/dag.py` | `__dynamic_steps__` with immediate execution ✓ |

### Partial Implementations (Need Enhancement)
| Feature | Current State | What's Missing |
|---------|--------------|----------------|
| **Human-in-Loop** | Checkpointing, validators | @ao.approval_step(), pause UI, Slack integration |
| **Memory Patterns** | Mem0 integration | Summary, window, entity, semantic strategies |
| **Debugger UI** | ASCII/Mermaid viz | Web UI, breakpoints, real-time events |

---

## Environment Variables

```bash
# LLM (required for real usage)
LLM_SERVER_URL=https://llm-gateway/v1/chat/completions
LLM_MODEL_NAME=claude-sonnet-4
LLM_OAUTH_ENDPOINT=https://auth/token  # or LLM_API_KEY
LLM_CLIENT_ID=your_id
LLM_CLIENT_SECRET=your_secret

# Chain Execution
CHAIN_MAX_PARALLEL_STEPS=5
CHAIN_DEFAULT_TIMEOUT_MS=30000
CHAIN_ERROR_HANDLING=fail_fast  # continue, retry

# Context Storage
CONTEXT_STORE_BACKEND=redis  # memory, mem0
CONTEXT_STORE_REDIS_HOST=localhost
CONTEXT_STORE_REDIS_PORT=6379

# Vector Store (for RAG)
VECTOR_PROVIDER=memory  # remote
VECTOR_HOST=https://vector/api
VECTOR_API_KEY=your_key

# Observability
AO_ENABLE_TRACING=true
AO_TRACE_SERVICE=my_service
```

---

## How to Work on This Codebase

### Running Tests
```bash
cd ChainServer
pip install -e "agentorchestrator[dev]"
pytest tests/ -v
```

### Linting
```bash
ruff check agentorchestrator
```

### CLI Commands
```bash
ao run chain_name --data '{}'
ao check
ao list
ao graph chain_name
ao new project my_project
```

### Adding a New Feature

1. **New middleware**: Add to `middleware/`, inherit from `BaseMiddleware`
2. **New agent type**: Add to `agents/` or `squad/agents/`, inherit from `BaseAgent`
3. **New service**: Add to `services/`, follow `VectorStoreService` pattern
4. **New step decorator option**: Modify `core/decorators.py`

---

## Current Work Tracking

This project uses **beads** (`bd`) for issue tracking.

```bash
bd ready              # See available work
bd show <id>          # View issue details
bd update <id> --status in_progress
bd close <id>
bd sync               # Sync with git
```

### Priority 1 - Core Enhancements
- `flow-9hm` - **Human-in-the-Loop Workflows** (partial) - Need `@ao.approval_step()` decorator
- `flow-01k` - **Conversation Memory Patterns** - Need sliding window, summary strategies
- `flow-hwk` - **Workflow Debugger UI** (partial) - Need web UI, breakpoints

### Priority 2 - Production Hardening
- Test coverage for new features (EventBus, ReAct, Reflection)
- Distributed execution support
- Plugin system via entry_points

### Priority 3 - Nice to Have
- Prometheus/StatsD metrics export
- Schema registry for multi-agent systems

### Recently Implemented ✓
| Feature | Location | Status |
|---------|----------|--------|
| **Deep Research Agent** | `examples/deep_research_agent.py` | ✓ Complete |
| **Agent Handoff Protocol** | `squad/orchestrator.py` | ✓ Complete |
| **ReAct Agent Pattern** | `agents/react.py` | ✓ Complete |
| **Event-Driven Workflows** | `core/event_bus.py`, `core/orchestrator.py` | ✓ Complete |
| **Tool Hub / Registry** | `agents/tools.py` | ✓ Complete |
| **Agent Reflection** | `middleware/reflection.py` | ✓ Complete |
| **Pydantic State Management** | `core/state.py`, `core/context.py` | ✓ Complete |
| **Declarative DSL** | `dsl/pipeline.py` | ✓ Complete |
| **Long-term Memory/Vector** | `services/vector_store.py`, `services/mem0.py` | ✓ Complete |
| **OpenTelemetry Integration** | `utils/tracing.py` | ✓ Complete |
| **Structured Tool Definitions** | `plugins/capability.py`, `squad/types.py` | ✓ Complete |
| **Pre-built Agent Templates** | `templates/scaffolding.py` | ✓ Complete |
| **Exception Hierarchy** | `core/exceptions.py` | ✓ Complete |
| **Pydantic v1/v2 Compat** | `utils/compat.py` | ✓ Complete |
| **Constants/Enums** | `core/constants.py` | ✓ Complete |

---

## Session Completion Checklist

When ending a work session:

1. **File issues** for remaining work (`bd create`)
2. **Run quality gates**: `pytest && ruff check`
3. **Update issue status**: `bd close` or `bd update`
4. **Push to remote**:
   ```bash
   git pull --rebase && bd sync && git push
   git status  # Must show "up to date"
   ```
5. **Hand off** context for next session

**Work is NOT complete until `git push` succeeds.**

---

## Common Patterns for Implementation

### Adding streaming to a component
```python
async def stream_something():
    async for chunk in source.stream():
        yield StreamEvent(type="chunk", data=chunk)
```

### Adding a new middleware
```python
class MyMiddleware(BaseMiddleware):
    async def before(self, ctx, step_name):
        # Pre-processing
        pass

    async def after(self, ctx, step_name, result):
        # Post-processing
        return result

    async def on_error(self, ctx, step_name, error):
        # Error handling
        raise error
```

### Adding validation to a step
```python
@ao.step(
    input_model=MyInputModel,   # Pydantic model
    output_model=MyOutputModel,
    input_key="request"
)
async def validated_step(ctx):
    request = ctx.get("request")  # Already validated
    return MyOutputModel(...)     # Auto-validated
```

### Using type-safe state in a step
```python
from pydantic import BaseModel, Field
from agentorchestrator import Context

class MyState(BaseModel):
    counter: int = Field(default=0)
    items: list[str] = Field(default_factory=list)

@ao.step(state_model=MyState)
async def process(ctx: Context[MyState]):
    # Type-safe with IDE autocomplete
    async with ctx.edit_state() as state:
        state.counter += 1
        state.items.append("item")
    return {"count": ctx.state.counter}
```

### Adding event handlers
```python
from agentorchestrator.core.event_bus import Event
from agentorchestrator.core.context import Context

@ao.event_handler("MyEvent")
async def handler(ctx: Context, event: Event):
    # Process event
    result = process(event.payload)
    # Emit new event
    return Event(type="ResultEvent", payload=result)
```

---

## Questions to Ask Before Implementing

1. Does this belong in `agentorchestrator/` (framework) or a domain-specific package?
2. Should this be a middleware, or part of core?
3. Does this need environment variable configuration?
4. Does this require streaming support?
5. Should this integrate with the existing tracing?
