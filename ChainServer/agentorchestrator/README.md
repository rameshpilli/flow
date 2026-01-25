# AgentOrchestrator

**A DAG-based Chain Orchestration Framework for AI/ML Pipelines**

AgentOrchestrator is a lightweight, decorator-driven framework for building data processing pipelines with automatic dependency resolution, parallel execution, and production-grade resilience. It works alongside existing frameworks like LangChain, LlamaIndex, and CrewAI without requiring platform migration.

---

## Key Capabilities

| Capability | Description |
|------------|-------------|
| **Decorator-Based Pipelines** | Simple `@ao.step()`, `@ao.chain()`, `@ao.agent()` decorators for intuitive pipeline definition |
| **DAG Execution Engine** | Automatic dependency resolution with parallel execution for optimal performance |
| **Multi-Agent Orchestration** | Supervisor patterns, context isolation, and result aggregation for coordinating specialized agents |
| **LLM Gateway Integration** | OAuth-enabled LLM client for corporate environments with structured output support |
| **Memory & Storage** | InMemory, Redis, and Mem0 semantic memory for conversation persistence |
| **Middleware Stack** | Pluggable logging, caching, summarization, rate limiting, and circuit breakers |
| **Resilience Patterns** | Retry with backoff, circuit breakers, timeouts, and fail-fast cancellation |
| **Observability** | Structured logging, OpenTelemetry tracing, and metrics collection |
| **CLI Tools** | Run, validate, visualize, and debug chains from command line |

---

## Installation

```bash
# Basic installation
pip install -e .

# With all optional features
pip install -e ".[all]"

# With specific extras
pip install -e ".[redis,langchain]"
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

## Multi-Agent Orchestration

### Supervisor Pattern

```python
from agentorchestrator.squad import SupervisorAgent, LLMGatewayAgent

# Create specialized agents
researcher = LLMGatewayAgent(
    name="researcher",
    instructions="Find and gather information.",
    llm_client=client,
)

analyst = LLMGatewayAgent(
    name="analyst",
    instructions="Analyze data and provide insights.",
    llm_client=client,
)

# Create supervisor to coordinate
supervisor = SupervisorAgent(
    name="coordinator",
    team=[researcher, analyst],
    llm_client=client,
)

# Execute
result = await supervisor.process_message("Research AI trends and analyze impact")
```

### Context Isolation

Prevent context pollution in multi-agent systems:

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
)

# Create isolation manager
isolation = ContextIsolationManager(coordinator_context=ctx)

# Each agent gets isolated namespace
for agent in team:
    isolation.create_namespace(agent.id)

# Share only what's needed
isolation.share_with_all("query", user_query)

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

## Examples

| Example | Description |
|---------|-------------|
| [Hello World](examples/getting_started/) | Basic step and chain setup |
| [RAG Pipeline](examples/rag/) | Retrieval-augmented generation with VectorStore |
| [Multi-Agent Research](examples/agents/) | Supervisor coordinating specialized agents |
| [Memory Integration](examples/memory/) | Chat storage and semantic memory |

See [examples/](examples/) for full implementations with READMEs.

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
│   ├── agents/         # LLMGatewayAgent for squad coordination
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

# Squad (Multi-Agent)
from agentorchestrator.squad import (
    SupervisorAgent,
    LLMGatewayAgent,
    LLMGatewayClassifier,
)
from agentorchestrator.squad.context import (
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
