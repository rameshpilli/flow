# AgentOrchestrator Framework

> A production-grade, DAG-based agent orchestration framework with services under the hood.
> Users tap into our services, set environment variables, and build agents—from simple to complex.
> We handle all dependencies, similar to LangChain or LlamaIndex agent frameworks.

---

## What We're Building

**AgentOrchestrator** is a domain-agnostic, decorator-driven chain orchestration framework inspired by Dagster patterns. It provides:

- **Clean API** for building complex AI/ML pipelines
- **Automatic dependency resolution** with parallel execution
- **Built-in services** (LLM, vector stores, context storage) configured via environment variables
- **Multi-agent orchestration** with routing, supervision, and team coordination
- **Production-ready features**: resilience, caching, streaming, observability

```
┌─────────────────────────────────────────────────────────────────┐
│                     AgentOrchestrator                           │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                  @ao.step() / @ao.agent() / @ao.chain()│    │
│  └────────────────────────────────────────────────────────┘    │
│           ↓                         ↓                           │
│  ┌──────────────────────┐  ┌─────────────────────────┐         │
│  │ Registry + DAG       │  │ Middleware Pipeline     │         │
│  │ Execution Engine     │  │ (Cache, Token, Logs)    │         │
│  └──────────────────────┘  └─────────────────────────┘         │
│           ↓                         ↓                           │
│  ┌──────────────────────┐  ┌─────────────────────────┐         │
│  │ Services Layer       │  │ Context Management      │         │
│  │ (LLM, VectorStore)   │  │ (Scoped, Thread-Safe)   │         │
│  └──────────────────────┘  └─────────────────────────┘         │
│           ↓                         ↓                           │
│  ┌──────────────────────┐  ┌─────────────────────────┐         │
│  │ Multi-Agent Squad    │  │ Storage Backends        │         │
│  │ (Routing, Supervisor)│  │ (Memory, Redis, mem0)   │         │
│  └──────────────────────┘  └─────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.core import ChainContext

ao = AgentOrchestrator()

@ao.step(name="fetch_data")
async def fetch_data(ctx: ChainContext):
    # Access services via context
    return {"data": "fetched"}

@ao.step(name="process", deps=["fetch_data"])
async def process_data(ctx: ChainContext):
    data = ctx.get("fetch_data")
    return {"processed": data}

@ao.chain(name="my_pipeline", steps=[fetch_data, process_data])
class MyPipeline:
    pass

# Execute
result = await ao.launch("my_pipeline", {"input": "value"})
```

---

## Core Concepts

### 1. Context Management

**ChainContext** is the central shared state manager for chain execution.

```python
from agentorchestrator.core import ChainContext, ContextScope

async def my_step(ctx: ChainContext):
    # Store data with different scopes
    ctx.set("temp_data", value, scope=ContextScope.STEP)    # Auto-cleaned after step
    ctx.set("shared_data", value, scope=ContextScope.CHAIN)  # Available throughout chain
    ctx.set("persistent", value, scope=ContextScope.GLOBAL)  # Persists across executions

    # Retrieve data
    data = ctx.get("shared_data")

    # Access from within tools
    request_id = ctx.request_id
    citations = ctx.citations
```

**Features:**
- **Three scope levels**: STEP (auto-cleanup), CHAIN (execution-wide), GLOBAL (persistent)
- **Thread-safe**: Uses `asyncio.Lock` + `threading.RLock` + `contextvars`
- **Token tracking**: Automatic token counting per context entry
- **Citation support**: Built-in citation collection and verification

### 2. Accessing Context from Within Tools

Tools can access the current execution context:

```python
from agentorchestrator.core import get_current_context

def my_tool(input_data: str) -> str:
    # Access context from any tool
    ctx = get_current_context()

    # Read shared state
    user_preferences = ctx.get("user_preferences")

    # Store tool results
    ctx.set("tool_result", result, scope=ContextScope.CHAIN)

    # Add citations
    ctx.add_citation(Citation(
        source_type="api",
        source_name="my_api",
        content="quoted content",
    ))

    return result
```

### 3. Agent Execution & User Visibility

Agents can take a long time to run. We provide mechanisms to give users visibility into what's happening:

#### Agent Input

```python
from pydantic import BaseModel

class AgentInput(BaseModel):
    query: str
    context: dict | None = None
    options: dict | None = None

@ao.step(input_model=AgentInput, input_key="request")
async def my_agent_step(ctx: ChainContext):
    request: AgentInput = ctx.get("request")  # Validated automatically
    # ... process
```

#### Agent Output

```python
from agentorchestrator.agents import AgentResult

@dataclass
class AgentResult(Generic[T]):
    data: T                          # The actual result data
    source: str                      # Which agent produced this
    query: str                       # Original query
    error: str | None = None         # Error if failed
    duration_ms: float = 0           # Execution time
    citations: list[Citation] = []   # Source citations
    metadata: dict = field(...)      # Additional metadata
```

#### Execution Details (Tool Calls & Results)

```python
# ExecutionSummary provides full visibility
result = await ao.launch("my_chain", input_data)

summary: ExecutionSummary = result["execution_summary"]

# Per-step details
for step_name, step_result in summary.step_results.items():
    print(f"Step: {step_name}")
    print(f"  Status: {step_result.status}")      # success/failed/skipped
    print(f"  Duration: {step_result.duration_ms}ms")
    print(f"  Tokens: {step_result.token_count}")
    print(f"  Retries: {step_result.retry_count}")
    if step_result.error:
        print(f"  Error: {step_result.error}")
```

#### Agent Stream (Real-Time LLM Streaming)

```python
from agentorchestrator.squad import LLMGatewayAgent

agent = LLMGatewayAgent(options)

# Streaming response - tokens arrive in real-time
async for chunk in agent.stream_message(user_input, user_id, session_id):
    # chunk contains streaming data from the LLM
    print(chunk.content, end="", flush=True)

    # Access intermediate state
    if chunk.tool_calls:
        for tool_call in chunk.tool_calls:
            print(f"Calling tool: {tool_call.name}")
```

**Stream Events Include:**
- Token-by-token text generation
- Tool call initiation and completion
- Intermediate reasoning steps
- Error events

---

## Services Layer

All services are configured via environment variables—users just set their config and go.

### LLM Service

```bash
# Environment Configuration
LLM_SERVER_URL=https://llm-gateway/v1/chat/completions
LLM_MODEL_NAME=claude-sonnet-4
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096

# Authentication (OAuth or API Key)
LLM_OAUTH_ENDPOINT=https://auth/token
LLM_CLIENT_ID=your_id
LLM_CLIENT_SECRET=your_secret
# OR
LLM_API_KEY=your_api_key
```

```python
from agentorchestrator.config import get_config

config = get_config()
llm_client = config.get_llm_client()

# Text generation
response = await llm_client.generate_async("Your prompt here")

# Structured output with Pydantic
from pydantic import BaseModel

class ExtractedData(BaseModel):
    name: str
    value: float

result = await llm_client.generate_structured_async(
    prompt="Extract data from: ...",
    response_model=ExtractedData
)
```

### Vector Store Service

```bash
VECTOR_STORE_BACKEND=pinecone  # or chroma, weaviate, etc.
VECTOR_STORE_API_KEY=your_key
VECTOR_STORE_INDEX=your_index
```

```python
vector_store = config.get_vector_store()
results = await vector_store.similarity_search(query, k=5)
```

### Context Storage

```bash
CONTEXT_STORE_BACKEND=redis  # or memory, mem0
CONTEXT_STORE_REDIS_HOST=redis-service
CONTEXT_STORE_REDIS_PORT=6379
CONTEXT_STORE_TTL=3600
```

---

## Middleware Pipeline

Cross-cutting concerns handled uniformly:

```python
from agentorchestrator.middleware import (
    LoggerMiddleware,
    CacheMiddleware,
    TokenManagerMiddleware,
    SummarizerMiddleware,
    CitationMiddleware,
)

ao = AgentOrchestrator()

# Add middleware (priority determines order)
ao.use(LoggerMiddleware(priority=1))
ao.use(CacheMiddleware(ttl=300, priority=2))
ao.use(TokenManagerMiddleware(max_tokens=8000, priority=3))
ao.use(SummarizerMiddleware(strategy="map_reduce", priority=4))
ao.use(CitationMiddleware(priority=5))
```

| Middleware | Purpose |
|-----------|---------|
| `LoggerMiddleware` | Structured logging |
| `CacheMiddleware` | In-memory result caching with TTL |
| `SummarizerMiddleware` | LLM-based text summarization (stuff/map_reduce/refine) |
| `TokenManagerMiddleware` | Context token budget management |
| `OffloadMiddleware` | Auto-offload large data to Redis |
| `MetricsMiddleware` | Performance tracking |
| `CitationMiddleware` | Citation collection and verification |
| `IdempotencyMiddleware` | Deduplication by request ID |
| `RateLimiterMiddleware` | Per-step rate limiting |

---

## Multi-Agent Orchestration (Squad)

### Single Agent

```python
from agentorchestrator.squad import LLMGatewayAgent, LLMGatewayAgentOptions

agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="TechAgent",
    description="Technical assistance",
    system_prompt="You are a tech expert.",
))

result = await agent.process_message(
    user_input="How do I optimize Python?",
    user_id="user-123",
    session_id="session-456",
)
```

### Multi-Agent Routing

```python
from agentorchestrator.squad import MultiAgentOrchestrator

orchestrator = MultiAgentOrchestrator()
orchestrator.add_agent(tech_agent)
orchestrator.add_agent(finance_agent)

# Routes to best agent automatically
result = await orchestrator.route_request(user_input)
```

### Supervisor Pattern

```python
from agentorchestrator.squad import SupervisorAgent, SupervisorAgentOptions

supervisor = SupervisorAgent(SupervisorAgentOptions(
    name="Supervisor",
    lead_agent=lead,
    team=[tech_agent, finance_agent, research_agent],
    trace=True,  # Enable execution tracing
))

# Supervisor coordinates team
response = await supervisor.process_message(user_input)
```

---

## Resilience Patterns

### Timeout, Retry, Circuit Breaker

```python
from agentorchestrator.agents import ResilientAgent

resilient = ResilientAgent(
    agent=my_agent,
    timeout_ms=30000,
    max_retries=3,
    retry_backoff=1.5,
    circuit_failure_threshold=5,
)

result = await resilient.fetch(query, ctx)
# Automatically handles: timeouts, retries with backoff, circuit breaking
```

### Composite Agents with Partial Success

```python
from agentorchestrator.agents import ResilientCompositeAgent

composite = ResilientCompositeAgent(
    agents=[sec_agent, news_agent, earnings_agent],
    require_all=False,  # Continue even if some fail
)

result = await composite.fetch(query, ctx)
# Returns results from successful agents, tracks failures per-agent
```

---

## Input/Output Validation

```python
from pydantic import BaseModel

class ChainRequest(BaseModel):
    company: str
    date_range: tuple[str, str]

class ChainOutput(BaseModel):
    summary: str
    confidence: float

@ao.step(
    input_model=ChainRequest,
    output_model=ChainOutput,
    input_key="request",
)
async def validated_step(ctx: ChainContext):
    request = ctx.get("request")  # Already validated
    # ... process
    return ChainOutput(summary="...", confidence=0.95)  # Auto-validated
```

---

## Checkpointing & Resume

```python
# Execute with checkpointing
result = await ao.launch_resumable(
    "long_chain",
    input_data,
    run_id="run-123",
)

# If interrupted, resume from last checkpoint
result = await ao.launch_resumable(
    "long_chain",
    input_data,
    run_id="run-123",  # Same run_id resumes
)
```

---

## CLI

```bash
ao run chain_name --data '{"key":"value"}'  # Execute chain
ao check                                      # Validate all chains
ao list                                       # List registered components
ao graph chain_name                          # Visualize DAG
ao new agent my_agent                        # Generate boilerplate
ao validate chain_name --detailed            # Detailed validation
```

---

## Environment Variables Reference

### Minimal Setup (Development)
```bash
# No env vars needed - uses in-memory stores, mock LLM
```

### Production Setup
```bash
# LLM Configuration
LLM_SERVER_URL=https://llm-gateway/v1/chat/completions
LLM_MODEL_NAME=claude-sonnet-4
LLM_OAUTH_ENDPOINT=https://auth/token
LLM_CLIENT_ID=your_id
LLM_CLIENT_SECRET=your_secret

# Chain Execution
CHAIN_MAX_PARALLEL_STEPS=5
CHAIN_DEFAULT_TIMEOUT_MS=30000
CHAIN_DEFAULT_RETRIES=3
CHAIN_ERROR_HANDLING=fail_fast  # or continue, retry

# Context Storage
CONTEXT_STORE_BACKEND=redis
CONTEXT_STORE_REDIS_HOST=redis-service
CONTEXT_STORE_REDIS_PORT=6379
CONTEXT_STORE_TTL=3600

# Summarization
SUMMARIZER_STRATEGY=map_reduce  # or stuff, refine
SUMMARIZER_MAX_TOKENS=4000

# Cache
CACHE_TTL_SECONDS=300

# Dynamic Agent Registration
AGENT_CONFIG='[{"name":"sec","mcp_url":"...","mcp_bearer_token":"..."}]'
```

---

## Project Structure

```
chainserver/
├── agentorchestrator/
│   ├── core/
│   │   ├── context.py      # ChainContext, scoped storage
│   │   ├── dag.py          # DAG builder & executor
│   │   ├── registry.py     # Agent/Step/Chain registries
│   │   ├── orchestrator.py # Main AgentOrchestrator class
│   │   ├── decorators.py   # @step, @agent, @chain
│   │   └── validation.py   # Input/output contracts
│   ├── middleware/
│   │   ├── base.py         # Middleware interface
│   │   ├── cache.py        # CacheMiddleware
│   │   ├── summarizer.py   # SummarizerMiddleware
│   │   ├── token_manager.py
│   │   └── ...
│   ├── agents/
│   │   ├── base.py         # BaseAgent
│   │   ├── resilient.py    # ResilientAgent
│   │   └── composite.py    # CompositeAgent
│   ├── services/
│   │   ├── llm_gateway.py  # LLMGatewayClient
│   │   └── vector_store.py # Vector store interface
│   ├── squad/
│   │   ├── orchestrator.py # MultiAgentOrchestrator
│   │   ├── agents/         # LLMGatewayAgent, SupervisorAgent
│   │   └── storage.py      # ChatStorage
│   ├── connectors/
│   │   ├── base.py         # BaseConnector
│   │   └── mcp.py          # MCPConnector
│   ├── plugins/            # Plugin discovery
│   ├── llm/                # LCEL chain builders
│   ├── config.py           # Environment config
│   └── cli.py              # CLI commands
├── cmpt/                   # Domain implementation example
└── tests/
```

---

## What We Have vs. What's Missing

### Currently Implemented

| Feature | Status | Notes |
|---------|--------|-------|
| DAG Execution | ✅ | Automatic parallelization |
| Step Dependencies | ✅ | Declarative via `deps` |
| Context Management | ✅ | Three-scope, thread-safe |
| Middleware Pipeline | ✅ | Extensible, priority-based |
| LLM Integration | ✅ | OAuth + API key support |
| Streaming Responses | ✅ | Token-by-token via Squad agents |
| Multi-Agent Routing | ✅ | Via MultiAgentOrchestrator |
| Supervisor Pattern | ✅ | Team coordination |
| Resilience (Retry/Timeout/Circuit) | ✅ | ResilientAgent wrapper |
| Caching | ✅ | In-memory with TTL |
| Token Management | ✅ | Middleware-based |
| Summarization | ✅ | Stuff/MapReduce/Refine |
| Citations | ✅ | Collection + verification |
| Input/Output Validation | ✅ | Pydantic contracts |
| Checkpointing/Resume | ✅ | RunStore interface |
| CLI | ✅ | Basic commands |
| Plugin System | ✅ | Entry point discovery |
| MCP Connector | ✅ | Tool integration |

### Missing / Future Features (Beads)

See `bd ready` for tracked issues. Key gaps compared to LangChain/LlamaIndex:

| Feature | Priority | Description |
|---------|----------|-------------|
| **Long-term Memory** | High | Semantic memory with vector stores (like LangChain's ConversationSummaryMemory) |
| **Human-in-the-Loop** | High | Built-in approval workflows, breakpoints, user confirmation steps |
| **Tool Result Streaming** | Medium | Stream intermediate tool results back to user (not just final LLM output) |
| **OpenTelemetry Integration** | Medium | Built-in observability with spans/traces (like LlamaIndex) |
| **Workflow Debugger UI** | Medium | Visual workflow debugger, event logs, run comparison |
| **Agent Reflection** | Medium | Self-critique and iterative improvement loops |
| **Structured Tool Definitions** | Medium | OpenAI function-calling style tool schemas |
| **Conversation Memory Types** | Medium | Buffer, Summary, Window, Entity memory patterns |
| **Graph Visualization** | Low | Runtime DAG visualization (beyond CLI) |
| **Pre-built Agent Templates** | Low | Document agents, research agents, code agents |
| **A2A Protocol** | Low | Agent-to-Agent communication standard |

---

## Beads Integration

This project uses **bd** (beads) for issue tracking.

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

### Landing the Plane (Session Completion)

**When ending a work session**, complete ALL steps:

1. **File issues for remaining work** - Create issues for anything needing follow-up
2. **Run quality gates** - Tests, linters, builds
3. **Update issue status** - Close finished work
4. **PUSH TO REMOTE** - MANDATORY:
   ```bash
   git pull --rebase && bd sync && git push
   git status  # MUST show "up to date with origin"
   ```
5. **Hand off** - Provide context for next session

**Work is NOT complete until `git push` succeeds.**
