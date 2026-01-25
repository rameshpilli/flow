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
├── ChainServer/
│   ├── agentorchestrator/     # THE FRAMEWORK (domain-agnostic)
│   │   ├── core/              # Orchestrator, Context, DAG, Registry
│   │   ├── middleware/        # Cache, Logger, Summarizer, TokenManager
│   │   ├── agents/            # BaseAgent, ResilientAgent, CompositeAgent
│   │   ├── services/          # LLMGatewayClient, VectorStoreService
│   │   ├── squad/             # Multi-agent orchestration
│   │   │   ├── agents/        # LLMGatewayAgent, SupervisorAgent
│   │   │   ├── storage/       # ChatStorage (InMemory, Redis)
│   │   │   └── types.py       # AgentTool, AgentTools
│   │   ├── connectors/        # MCPConnector
│   │   ├── plugins/           # Plugin discovery, capability schemas
│   │   ├── llm/               # LCEL chain builders
│   │   ├── templates/         # Project scaffolding
│   │   ├── utils/             # Logging, tracing
│   │   └── config.py          # Environment configuration
│   └── cmpt/                  # DOMAIN EXAMPLE (Client Meeting Prep Tool)
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

### 2. Context Scopes
- `ContextScope.STEP` - Auto-cleaned after step (temp data)
- `ContextScope.CHAIN` - Lives for entire chain execution
- `ContextScope.GLOBAL` - Persists across executions

### 3. Middleware Pipeline
Middleware wraps step execution: `before()` → step → `after()` / `on_error()`

### 4. Squad Multi-Agent
- `MultiAgentOrchestrator` - Routes to best agent
- `SupervisorAgent` - Coordinates a team of specialists
- `LLMGatewayAgent` - Single agent with LLM backend

---

## Key Files to Know

| When you need... | Look at... |
|-----------------|------------|
| Core orchestration | `core/orchestrator.py`, `core/dag.py` |
| Context management | `core/context.py` |
| Step/chain decorators | `core/decorators.py` |
| Middleware base | `middleware/base.py` |
| LLM client | `services/llm_gateway.py` |
| Vector store | `services/vector_store.py` |
| Multi-agent routing | `squad/orchestrator.py` |
| Supervisor pattern | `squad/agents/supervisor.py` |
| Tool schemas | `plugins/capability.py`, `squad/types.py` |
| Tracing | `utils/tracing.py` |
| Config loading | `config.py` |
| Project templates | `templates/scaffolding.py` |

---

## What's Implemented (Use These)

| Feature | Location | Notes |
|---------|----------|-------|
| DAG Execution | `core/dag.py` | Automatic parallelization |
| Context Management | `core/context.py` | 3 scopes, thread-safe, token tracking |
| Middleware Pipeline | `middleware/` | Cache, Logger, Summarizer, TokenManager, etc. |
| LLM Integration | `services/llm_gateway.py` | OAuth + API key, structured output |
| Vector Store | `services/vector_store.py` | In-memory + HTTP remote provider |
| Multi-Agent Routing | `squad/orchestrator.py` | Intent classification, routing |
| Supervisor Pattern | `squad/agents/supervisor.py` | Team coordination, validation |
| Resilience | `agents/resilient.py` | Timeout, retry, circuit breaker |
| Streaming | `squad/agents/` | LLM token streaming |
| OpenTelemetry | `utils/tracing.py` | Spans, traces, graceful fallback |
| Tool Schemas | `plugins/capability.py` | JSON Schema, validation, @capability |
| Checkpointing | `core/run_store.py` | Resume from last successful step |
| CLI | `cli.py` | run, check, list, graph, new |
| Scaffolding | `templates/scaffolding.py` | Full project generation |
| MCP Connector | `connectors/mcp.py` | Tool discovery, execution |
| Citations | `models/citation.py` | Collection, verification |

---

## What's Partially Done (Gaps to Fill)

| Feature | Current State | What's Missing |
|---------|--------------|----------------|
| **Human-in-Loop** | Checkpointing works, supervisor has validators | Need: @ao.approval_step(), pause/resume UI, external integrations (Slack) |
| **Tool Streaming** | LLM tokens stream | Need: ToolEvent (start/progress/complete), tool result streaming |
| **Agent Reflection** | Validator callbacks exist | Need: Built-in critique prompts, @ao.reflect(), quality scoring |
| **Debugger UI** | ASCII/Mermaid visualization | Need: Web UI, real-time event viewer, breakpoints |

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
ruff check agentorchestrator cmpt
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

### Active Feature Issues
- `flow-9hm` - Human-in-the-Loop Workflows (P1, partial)
- `flow-p7y` - Tool Result Streaming (P2, partial)
- `flow-954` - Agent Reflection/Self-Critique (P2, partial)
- `flow-hwk` - Workflow Debugger UI (P3, partial)

### Recently Closed (Already Implemented)
- `flow-znf` - Long-term Memory/Vector Stores ✓
- `flow-8gn` - OpenTelemetry Integration ✓
- `flow-8ey` - Structured Tool Definitions ✓
- `flow-b1u` - Pre-built Agent Templates ✓

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

---

## Questions to Ask Before Implementing

1. Does this belong in `agentorchestrator/` (framework) or `cmpt/` (domain)?
2. Should this be a middleware, or part of core?
3. Does this need environment variable configuration?
4. Does this require streaming support?
5. Should this integrate with the existing tracing?
