# AgentOrchestrator

**A DAG-based Chain Orchestration Framework for AI/ML Pipelines**

AgentOrchestrator is a lightweight, decorator-driven framework for building data processing pipelines with automatic dependency resolution, parallel execution, and production-grade resilience. It works alongside existing frameworks like LangChain, LlamaIndex, and CrewAI without requiring platform migration.

---

## Key Capabilities

| Capability | Description |
|------------|-------------|
| **Decorator-Based Pipelines** | Simple `@ao.step()`, `@ao.chain()`, `@ao.agent()` decorators for intuitive pipeline definition |
| **DAG Execution Engine** | Automatic dependency resolution with parallel execution for optimal performance |
| **Multi-Agent Patterns** | Squad, Supervisor, FunctionAgent with handoffs, and intent-based routing |
| **Type-Safe State Management** | Pydantic models for validated, type-safe workflow state with IDE autocomplete |
| **LLM Gateway Integration** | OAuth-enabled LLM client for corporate environments with structured output support |
| **Memory & Storage** | InMemory, Redis, and Mem0 semantic memory for conversation persistence |
| **Middleware Stack** | Pluggable logging, caching, summarization, rate limiting, and circuit breakers |
| **Resilience Patterns** | Retry with backoff, circuit breakers, timeouts, and fail-fast cancellation |
| **Observability** | Structured logging, OpenTelemetry tracing, and metrics collection |
| **CLI Tools** | Run, validate, visualize, and debug chains from command line |
| **Event-Driven Workflows** | Event bus (Redis-backed or in-memory), event handlers, streaming step/agent/tool events |
| **Declarative DSL (Preview)** | Build pipelines via a fluent builder instead of decorators; register steps, chains, and events together |

---

## Agent Patterns

AgentOrchestrator provides multiple patterns for building AI agents:

| Pattern | Use Case | Example |
|---------|----------|---------|
| **Squad** | Team coordination with supervisor | Research teams, complex analysis |
| **Supervisor Agent** | Central coordinator with specialists | Customer support, multi-domain Q&A |
| **FunctionAgent** | Explicit handoffs between agents | Pipeline workflows (Research → Write → Review) |
| **MultiAgentOrchestrator** | Intent-based routing | Route to specialists based on query type |
| **Linear Chains** | Sequential DAG execution | ETL pipelines, data processing |
| **Deep Research Agent** | Multi-source research synthesis | Financial analysis, market research |

### Quick Comparison

```
┌─────────────────────┬─────────────────────┬─────────────────────┐
│     SQUAD           │   SUPERVISOR        │   FUNCTION AGENT    │
│                     │                     │                     │
│ squad.run(query)    │ supervisor.process()│ agent.handoff()     │
│                     │                     │                     │
│   ┌───────┐         │      ┌───┐          │  ┌───┐    ┌───┐     │
│   │ Lead  │         │      │ S │          │  │ A │ →  │ B │     │
│   └───┬───┘         │      └─┬─┘          │  └───┘    └───┘     │
│   ┌───┴───┐         │    ┌───┼───┐        │                     │
│ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐   │  ┌─┴─┐ ┌─┴─┐ ┌─┴─┐  │  Explicit handoff   │
│ │ A │ │ B │ │ C │   │  │ A │ │ B │ │ C │  │  with context        │
│ └───┘ └───┘ └───┘   │  └───┘ └───┘ └───┘  │                     │
│                     │                     │                     │
│ Simple API          │ Full control        │  Pipeline pattern   │
└─────────────────────┴─────────────────────┴─────────────────────┘
```

---

## Installation

```bash
# Basic installation
pip install -e .

# With all optional features
pip install -e ".[all]"

# With specific extras
pip install -e ".[redis,langchain]"

# Event-driven workflows (Redis-backed bus, falls back to memory)
pip install -e ".[workflows]"
```

**Requirements**: Python 3.10+

---

## Quick Start

### Hello World

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="hello_world")

@ao.step(name="greet")
async def greet(ctx):
    name = ctx.get("name", "World")
    return {"greeting": f"Hello, {name}!"}

@ao.chain(name="hello_chain")
class HelloChain:
    steps = ["greet"]

# Run
import asyncio
result = asyncio.run(ao.launch("hello_chain", {"name": "AgentOrchestrator"}))
print(result["greeting"])  # "Hello, AgentOrchestrator!"
```

### Multi-Step Pipeline with Dependencies

```python
@ao.step(name="fetch")
async def fetch(ctx):
    ctx.set("data", [1, 2, 3, 4, 5])
    return {"fetched": True}

@ao.step(name="process", deps=["fetch"])  # Runs after fetch
async def process(ctx):
    data = ctx.get("data")
    ctx.set("processed", [x * 2 for x in data])
    return {"processed": True}

@ao.step(name="summarize", deps=["process"])
async def summarize(ctx):
    data = ctx.get("processed")
    return {"sum": sum(data), "count": len(data)}

@ao.chain(name="data_pipeline")
class DataPipeline:
    steps = ["fetch", "process", "summarize"]

result = asyncio.run(ao.launch("data_pipeline", {}))
# {"sum": 30, "count": 5, ...}
```

### Type-Safe State with Pydantic

Use Pydantic models for validated, type-safe workflow state:

```python
from pydantic import BaseModel, Field
from agentorchestrator import AgentOrchestrator, Context

class PipelineState(BaseModel):
    counter: int = Field(default=0)
    items: list[str] = Field(default_factory=list)
    processed: bool = Field(default=False)

ao = AgentOrchestrator()

@ao.step(name="process", state_model=PipelineState)
async def process(ctx: Context[PipelineState]):
    # Type-safe access with IDE autocomplete!
    async with ctx.edit_state() as state:
        state.counter += 1  # ← IDE knows this is an int
        state.items.append("new_item")  # ← IDE knows this is a list
    
    # Read-only access
    count = ctx.state.counter  # ← Typed!
    return {"count": count}

# Create context with state model
from agentorchestrator.core.context import ChainContext
ctx = ChainContext("req_123", state_model=PipelineState)
```

**Benefits**:
- ✅ IDE autocomplete and type hints
- ✅ Automatic validation via Pydantic
- ✅ Atomic updates via context manager
- ✅ Thread-safe concurrent access

### Parallel Execution

Steps without dependencies run in parallel automatically:

```python
@ao.step(name="fetch_news")
async def fetch_news(ctx):
    await asyncio.sleep(1)  # Simulates API call
    return {"news": ["headline1", "headline2"]}

@ao.step(name="fetch_stocks")
async def fetch_stocks(ctx):
    await asyncio.sleep(1)  # Simulates API call
    return {"stocks": {"AAPL": 150, "GOOGL": 140}}

@ao.step(name="combine", deps=["fetch_news", "fetch_stocks"])
async def combine(ctx):
    return {"combined": True}

@ao.chain(name="parallel_chain")
class ParallelChain:
    steps = ["fetch_news", "fetch_stocks", "combine"]

# fetch_news and fetch_stocks run in parallel (~1s total, not 2s)
```

---

## Multi-Agent Patterns

### 1. Squad Pattern (Recommended for Teams)

The simplest way to coordinate multiple agents:

```python
from agentorchestrator.squad import (
    Squad,
    SquadOptions,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)

# Create specialist agents
research_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Researcher",
    description="Find and gather information on topics.",
    llm_client=llm_client,
))

analyst_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Analyst",
    description="Analyze data and provide insights.",
    llm_client=llm_client,
))

writer_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Writer",
    description="Write clear, compelling content.",
    llm_client=llm_client,
))

# Create supervisor (lead agent)
lead = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="ProjectLead",
    description="Coordinates team to answer complex questions",
    llm_client=llm_client,
))

# Form the squad
squad = Squad(
    supervisor=lead,
    agents=[research_agent, analyst_agent, writer_agent],
    options=SquadOptions(trace=True),
)

# Execute - supervisor coordinates the team automatically
result = await squad.run("Research AI trends and write a report")
print(result.content)
```

See: [examples/supervisor_chain.py](examples/supervisor_chain.py)

### 2. FunctionAgent with Handoffs (Pipeline Pattern)

For explicit agent-to-agent workflows:

```python
from agentorchestrator.squad import FunctionAgent, FunctionAgentOptions

# Create agents with handoff permissions
researcher = FunctionAgent(FunctionAgentOptions(
    name="Researcher",
    description="Gathers information",
    llm_client=llm_client,
    can_handoff_to=["Writer"],  # Can only hand off to Writer
))

writer = FunctionAgent(FunctionAgentOptions(
    name="Writer",
    description="Writes reports",
    llm_client=llm_client,
    can_handoff_to=["User"],  # Terminal - returns to user
))

# Researcher hands off to Writer with context
handoff = await researcher.handoff(
    to_agent="Writer",
    context={"findings": findings, "sources": sources},
    message="Research complete. Please write a summary.",
)

# Orchestrator routes using handoff.to_agent
print(f"{handoff.from_agent} → {handoff.to_agent}")
# "Researcher → Writer"
```

### 3. Deep Research Agent (Financial Analysis)

Multi-source research with context management:

```python
from agentorchestrator.examples.financial_research_agent import (
    FinancialResearchAgent,
    ResearchConfig,
)

# Create agent with context management
agent = FinancialResearchAgent(ResearchConfig(
    max_context_tokens=100_000,
    enable_auto_summarization=True,
))

# Run comprehensive research
report = await agent.research(
    topic="Analyze Tesla's competitive position in the EV market",
    focus_areas=["market share", "technology", "financials"],
    depth="comprehensive",
)

print(report.executive_summary)
for finding in report.key_findings:
    print(f"- {finding.finding} ({finding.confidence:.0%} confidence)")
```

See: [examples/financial_research_agent.py](examples/financial_research_agent.py)

### 4. MultiAgentOrchestrator (Intent-Based Routing)

Route queries to specialists based on intent:

```python
from agentorchestrator.squad import (
    MultiAgentOrchestrator,
    LLMGatewayClassifier,
    LLMGatewayAgent,
)

# Create orchestrator with classifier
orchestrator = MultiAgentOrchestrator(
    classifier=LLMGatewayClassifier(llm_client=llm_client),
)

# Add specialist agents
orchestrator.add_agent(tech_agent)
orchestrator.add_agent(finance_agent)
orchestrator.add_agent(support_agent)

# Classifier automatically routes to the right agent
response = await orchestrator.route_request(
    "How do I optimize my Python code?",
    user_id="user-123",
)
# Routes to tech_agent based on query content
```

---

## LLM Gateway (Corporate Environments)

For corporate environments behind an LLM gateway with OAuth authentication:

```python
from agentorchestrator.services import LLMGatewayClient, LLMGatewayConfig

# Option 1: Direct configuration
client = LLMGatewayClient(
    server_url="https://llm-gateway.corp.com/v1/chat/completions",
    oauth_endpoint="https://auth.corp.com/token",
    client_id="my-app",
    client_secret="secret",
    model_name="gpt-4",
)

# Option 2: From environment variables
# Set: LLM_SERVER_URL, LLM_OAUTH_ENDPOINT, LLM_CLIENT_ID, LLM_CLIENT_SECRET
client = LLMGatewayClient.from_env()

# Generate text
response = await client.generate_async("What is 2+2?")

# Structured output with Pydantic
from pydantic import BaseModel

class Answer(BaseModel):
    result: int
    explanation: str

result = await client.generate_structured_async(
    "What is 2+2?",
    response_model=Answer,
)
print(result.result)  # 4
```

---

## Memory & Storage

### Chat Storage (Conversation History)

```python
from agentorchestrator.squad.storage import InMemoryChatStorage

# In-memory storage (development)
storage = InMemoryChatStorage()

# Save messages
await storage.save_chat_message(
    user_id="user-123",
    session_id="session-abc",
    agent_id="assistant",
    new_message={"role": "user", "content": "Hello!"}
)

# Fetch history
history = await storage.fetch_chat("user-123", "session-abc", "assistant")
```

### Redis Storage (Production)

```python
from agentorchestrator.squad.storage.redis import RedisChatStorage

# Redis storage (production)
storage = RedisChatStorage(
    host="redis.corp.com",
    port=6379,
    password="secret",
)
```

### Semantic Memory (Mem0)

```python
from agentorchestrator.services import Mem0Memory
from your_app import MemoryStoreClient

# Connect to corporate mem0
client = MemoryStoreClient(
    base_url="https://mem0.corp.com",
    agent_id="my-agent"
)
memory = Mem0Memory(client=client)

# Store memories
await memory.add("User prefers technical explanations")

# Search memories semantically
results = await memory.search("What are user's preferences?")
for mem in results:
    print(mem.content)
```

---

## Context Isolation

Prevent context pollution in multi-agent systems:

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    IsolationLevel,
    ResultAggregator,
    AggregationStrategy,
)

# Create isolation manager
isolation = ContextIsolationManager(
    coordinator_context=ctx,
    isolation_level=IsolationLevel.FULL,
)

# Each agent gets isolated namespace
for agent in team:
    isolation.create_namespace(agent.id)

# Share only what's needed
isolation.share_with_all("query", user_query)
isolation.share_between("researcher", "findings", ["analyst", "writer"])

# Aggregate results
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
final = await aggregator.aggregate(llm=client)
```

---

## Middleware

Add cross-cutting concerns to your pipelines:

```python
from agentorchestrator.middleware import (
    LoggerMiddleware,
    CacheMiddleware,
    SummarizerMiddleware,
    RateLimiterMiddleware,
    MiddlewareCircuitBreakerConfig,
    CircuitBreakerMiddleware,
)

ao = AgentOrchestrator(name="my_app")

# Logging
ao.use(LoggerMiddleware(level="INFO"))

# Caching (5 minute TTL)
ao.use(CacheMiddleware(ttl_seconds=300))

# Summarization for large outputs
ao.use(SummarizerMiddleware(summarizer=summarizer, max_tokens=4000))

# Rate limiting
ao.use(RateLimiterMiddleware({
    "fetch_data": {"requests_per_second": 10},
}))

# Circuit breaker for resilience
ao.use(CircuitBreakerMiddleware({
    "external_api": MiddlewareCircuitBreakerConfig(failure_threshold=5),
}))
```

---

## Examples

| Example | Description | Location |
|---------|-------------|----------|
| **Hello World** | Basic step and chain setup | [examples/getting_started/](examples/getting_started/) |
| **Supervisor Chain** | Multi-agent supervisor pattern | [examples/supervisor_chain.py](examples/supervisor_chain.py) |
| **Financial Research** | Deep research agent with MCP servers | [examples/financial_research_agent.py](examples/financial_research_agent.py) |
| **RAG Pipeline** | Retrieval-augmented generation | [examples/rag/](examples/rag/) |
| **Memory Integration** | Chat storage and semantic memory | [examples/memory/](examples/memory/) |

### Running Examples

```bash
# Run the supervisor chain example
python -m agentorchestrator.examples.supervisor_chain

# Run the financial research agent
python -m agentorchestrator.examples.financial_research_agent \
    "Analyze Tesla's competitive position" \
    --focus "market share" "technology" \
    --depth comprehensive

# Or use the CLI
ao run hello_chain --data '{"name": "World"}'
```

---

## CLI

The CLI is available as both `ao` (shorthand, recommended) and `agentorchestrator` (full name):

```bash
# Execution Commands
ao run my_pipeline --data '{"key": "value"}'      # Run a chain
ao run my_pipeline --resumable                    # With checkpointing
ao run my_pipeline --dry-run                      # Preview execution plan
ao run my_pipeline --step my_step                 # Test single step
ao resume <run_id>                                # Resume failed run
ao runs --status failed                           # List failed runs
ao run-info <run_id>                              # Show run details
ao run-output <run_id>                            # Get partial outputs

# Validation & Inspection
ao check                                          # Quick validation
ao validate my_chain                              # Comprehensive validation
ao validate my_chain --data '{"sample": "data"}'  # With sample data
ao list                                           # List all components
ao graph my_pipeline                              # ASCII DAG visualization
ao graph my_pipeline --format mermaid             # Mermaid diagram

# Development & Debugging
ao dev --watch                                    # Hot reload mode
ao debug my_chain --data '{"key": "value"}'       # Debug with snapshots

# Health & Diagnostics
ao health                                         # Basic health check
ao health --detailed                              # Full dependency check
ao doctor                                         # Diagnose setup issues
ao version                                        # Show version
ao config                                         # Show config (masked)

# Scaffolding
ao new agent MyAgent                              # Generate agent template
ao new chain MyChain                              # Generate chain template
ao new project my-app                             # Generate full project
```

See [CLI Reference](docs/cli/index.md) for complete documentation.

---

## Documentation

| Section | Description |
|---------|-------------|
| [Quick Start](docs/QUICKSTART.md) | Get started in 5 minutes |
| [Understanding](docs/understanding/) | Core concepts: Context, Steps, Agents, Multi-Agent |
| [Patterns](docs/patterns/) | Production patterns: Isolation, Summarization, Routing |
| [API Reference](docs/API.md) | Full API documentation |
| [Architecture](docs/ARCHITECTURE.md) | System design & diagrams |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues & solutions |

### Build Documentation Site

```bash
pip install mkdocs-material mkdocs-minify-plugin
cd ..  # ChainServer root
mkdocs serve
```

---

## Project Structure

```
agentorchestrator/
├── core/               # AgentOrchestrator, Context, DAG, Registry
├── middleware/         # Cache, Logger, Summarizer, Rate Limiter
├── squad/              # Multi-agent orchestration
│   ├── agents/         # LLMGatewayAgent, SupervisorAgent, FunctionAgent
│   ├── classifiers/    # Intent classification
│   ├── context/        # Context isolation & result aggregation
│   └── storage/        # Chat storage (InMemory, Redis)
├── agents/             # BaseAgent, ResilientAgent
├── services/           # External integrations
│   ├── llm_gateway.py  # LLMGatewayClient with OAuth
│   ├── redis.py        # RedisService
│   ├── vector_store.py # VectorStoreService
│   └── mem0.py         # Mem0Memory (semantic memory)
├── utils/              # Logging, tracing, circuit breaker
├── examples/           # Example implementations
│   ├── getting_started/# Hello world, simple chains
│   ├── agents/         # Multi-agent examples
│   ├── rag/            # RAG pipeline examples
│   └── memory/         # Memory integration examples
└── docs/               # Documentation
```

---

## Key Imports

```python
# Core
from agentorchestrator import AgentOrchestrator, Context

# Services
from agentorchestrator.services import (
    LLMGatewayClient,       # LLM with OAuth
    LLMGatewayConfig,       # LLM configuration
    RedisService,           # Redis client
    VectorStoreService,     # Vector search
    VectorDocument,         # Document for vector store
    Mem0Memory,             # Semantic memory
    CompositeMemory,        # Combined memory strategies
)

# Storage
from agentorchestrator.squad.storage import InMemoryChatStorage
from agentorchestrator.squad.storage.redis import RedisChatStorage

# Agents
from agentorchestrator.agents import BaseAgent, ResilientAgent, AgentResult

# Squad (Multi-Agent) - All patterns
from agentorchestrator.squad import (
    # High-level Squad wrapper
    Squad,
    SquadOptions,
    # Agent types
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
    SupervisorAgent,
    SupervisorAgentOptions,
    FunctionAgent,
    FunctionAgentOptions,
    HandoffResult,
    # Routing
    MultiAgentOrchestrator,
    LLMGatewayClassifier,
    # Context management
    IsolationLevel,
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
)

# Middleware
from agentorchestrator.middleware import (
    CacheMiddleware,
    LoggerMiddleware,
    SummarizerMiddleware,
    RateLimiterMiddleware,
    CircuitBreakerMiddleware,
    MiddlewareCircuitBreakerConfig,
)

# Utilities
from agentorchestrator.utils import (
    CircuitBreaker,
    configure_logging,
    get_logger,
)
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_SERVER_URL` | LLM Gateway endpoint | - |
| `LLM_MODEL_NAME` | Model to use | `gpt-4` |
| `LLM_OAUTH_ENDPOINT` | OAuth token endpoint | - |
| `LLM_CLIENT_ID` | OAuth client ID | - |
| `LLM_CLIENT_SECRET` | OAuth client secret | - |
| `LLM_API_KEY` | API key (alternative to OAuth) | - |
| `LLM_TEMPERATURE` | Sampling temperature | `0.2` |
| `LLM_MAX_TOKENS` | Max output tokens | `4096` |
| `REDIS_HOST` | Redis server host | `localhost` |
| `REDIS_PORT` | Redis server port | `6379` |

---

## License

MIT
