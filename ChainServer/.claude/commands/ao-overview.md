# AgentOrchestrator Overview

A quick reference guide to the AgentOrchestrator framework and project patterns.

## Usage
```
/ao-overview
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AgentOrchestrator                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐                 │
│  │   Chains    │ ───► │    Steps    │ ───► │  Services   │                 │
│  └─────────────┘      └─────────────┘      └─────────────┘                 │
│         │                    │                    │                         │
│         │                    │                    ▼                         │
│         │                    │             ┌─────────────┐                 │
│         │                    │             │   Agents    │                 │
│         │                    │             └─────────────┘                 │
│         │                    │                    │                         │
│         ▼                    ▼                    ▼                         │
│  ┌──────────────────────────────────────────────────────────┐              │
│  │                    Middleware Stack                       │              │
│  │  ┌────────┐ ┌───────┐ ┌─────────┐ ┌────────┐ ┌────────┐ │              │
│  │  │Offload │ │ Cache │ │ Logger  │ │Metrics │ │Citation│ │              │
│  │  └────────┘ └───────┘ └─────────┘ └────────┘ └────────┘ │              │
│  └──────────────────────────────────────────────────────────┘              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Concepts

### 1. Chain
A pipeline of steps that execute in order based on dependencies.

```python
@ao.chain(name="my_chain", description="...")
class MyChain:
    steps = ["step_1", "step_2", "step_3"]
```

### 2. Step
A decorated async function that performs a unit of work.

```python
@ao.step(name="step_1", produces=["output"])
async def step_1(ctx) -> dict:
    ctx.set("output", result)
    return {"success": True}
```

### 3. Service
A stateless class that encapsulates business logic.

```python
class MyService:
    async def execute(self, input) -> Output:
        return await self._process(input)
```

### 4. Agent
A data fetcher that connects to external sources (MCP, APIs).

```python
class MyAgent(BaseAgent):
    async def fetch(self, query, **kwargs) -> AgentResult:
        return AgentResult(data=..., source=self._ao_name, query=query)
```

### 5. Middleware
Cross-cutting concerns (logging, caching, metrics).

```python
class MyMiddleware(Middleware):
    async def before(self, ctx, step_name): ...
    async def after(self, ctx, step_name, result): ...
```

---

## Project Structure

```
project/
├── agentorchestrator/          # Framework core
│   ├── core/                   # Core components
│   │   ├── orchestrator.py     # Main AgentOrchestrator class
│   │   ├── context.py          # ChainContext
│   │   ├── dag.py              # DAG executor
│   │   ├── registry.py         # Step/Chain/Agent registries
│   │   └── decorators.py       # @step, @chain, @agent decorators
│   ├── agents/                 # Agent base classes
│   │   └── base.py             # BaseAgent, ResilientAgent
│   ├── middleware/             # Built-in middleware
│   │   ├── base.py             # Middleware base class
│   │   ├── offload.py          # Large payload offloading
│   │   ├── cache.py            # Result caching
│   │   ├── logger.py           # Logging
│   │   ├── metrics.py          # Metrics collection
│   │   └── ...
│   ├── plugins/                # Plugin adapters
│   │   └── mcp_adapter.py      # MCP protocol adapter
│   ├── utils/                  # Utilities
│   │   ├── retry.py            # Retry logic
│   │   └── circuit_breaker.py  # Circuit breaker
│   └── templates/              # Project scaffolding
│       └── scaffolding.py
│
├── cmpt/                       # Example chain (Client Meeting Prep Tool)
│   ├── chain.py                # Chain definition
│   ├── run.py                  # CLI runner
│   ├── config.py               # Configuration
│   └── services/
│       ├── __init__.py         # Exports
│       ├── models.py           # Pydantic models
│       ├── _01_context_builder.py
│       ├── _02_content_prioritization.py
│       ├── _03_response_builder.py
│       ├── agents.py           # Agent registration
│       └── llm_prompts.py      # LLM prompts
│
└── .claude/commands/           # Claude Code skills
    ├── new-chain.md
    ├── new-agent.md
    ├── new-service.md
    ├── new-step.md
    └── new-middleware.md
```

---

## Quick Reference

### Creating a Chain
```bash
# Use the skill
/new-chain risk_analysis "Risk analysis pipeline"
```

### Creating an Agent
```bash
/new-agent portfolio_agent "Fetches portfolio data" --mcp
```

### Creating a Service
```bash
/new-service risk_calculator "Calculates risk metrics"
```

### Creating a Step
```bash
/new-step validation cmpt "Validates financial metrics"
```

### Creating Middleware
```bash
/new-middleware audit_logger "Logs for compliance"
```

---

## Key APIs

### AgentOrchestrator
```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app", isolated=True)

# Register and run
register_my_chain(ao)
result = await ao.launch("my_chain", {"request": {...}})
```

### ChainContext
```python
# In a step
value = ctx.get("key")           # Read
ctx.set("key", value)            # Write
ctx.has("key")                   # Check exists
```

### AgentResult
```python
result = AgentResult(
    data={"items": [...]},
    source="my_agent",
    query="search query",
    duration_ms=123.45,
    error=None,  # or error message
)
```

### Middleware
```python
ao.add_middleware(OffloadMiddleware(threshold=100_000))
ao.add_middleware(LoggerMiddleware())
```

---

## Patterns

### 1. Three-Stage Pipeline
```
Context Builder → Content Prioritization → Response Builder
```

### 2. Service Pattern
```python
class MyService:
    def __init__(self, config=None, llm=None, agents=None): ...
    async def execute(self, input) -> output: ...
```

### 3. Agent Registration
```python
@testable(...)
def register_agents(ao):
    ao.agent(name=..., resilient=True)(AgentClass)

def get_agents(ao, **config) -> dict[str, Agent]:
    return {name: Agent(**config)}
```

### 4. Error Handling
```python
output = Output(errors={}, timing_ms={})
try:
    result = await operation()
except Exception as e:
    errors["operation"] = str(e)
```

---

## Common Commands

```bash
# Run a chain
python -m cmpt.run "Apple Inc" --meeting-date 2025-01-15

# Validate chain
ao check my_chain

# Visualize DAG
ao graph my_chain --format mermaid

# Test agents
await register_my_agents.test(ao)
```

---

## Reference Files

| Component | File |
|-----------|------|
| Chain Example | [cmpt/chain.py](cmpt/chain.py) |
| Models Example | [cmpt/services/models.py](cmpt/services/models.py) |
| Service Example | [cmpt/services/_01_context_builder.py](cmpt/services/_01_context_builder.py) |
| Agent Example | [cmpt/services/agents.py](cmpt/services/agents.py) |
| Base Agent | [agentorchestrator/agents/base.py](agentorchestrator/agents/base.py) |
| Middleware | [agentorchestrator/middleware/](agentorchestrator/middleware/) |
| Core | [agentorchestrator/core/](agentorchestrator/core/) |

---

## Skills Available

| Skill | Description |
|-------|-------------|
| `/new-chain` | Create a new chain with 3-stage pipeline |
| `/new-agent` | Create a new MCP/HTTP/mock agent |
| `/new-service` | Create a new service class |
| `/new-step` | Create a new step for a chain |
| `/new-middleware` | Create custom middleware |
| `/ao-overview` | This overview document |
