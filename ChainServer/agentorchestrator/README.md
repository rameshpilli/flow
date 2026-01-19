# AgentOrchestrator

**A DAG-based Chain Orchestration Framework**

AgentOrchestrator is a lightweight, decorator-driven framework for building data processing pipelines with automatic dependency resolution, parallel execution, and production-grade resilience.

## Features

- **Decorator-Based**: Simple `@ao.step()`, `@ao.agent()`, `@ao.chain()` decorators
- **DAG Execution**: Automatic dependency resolution with parallel execution
- **Middleware**: Logging, caching, summarization, token management
- **Context Management**: Scoped storage with Redis offloading for large payloads; optional RAG context via pluggable vector store
- **Resilience**: Circuit breakers, retry with backoff, fail-fast cancellation
- **Observability**: Structured logging, OpenTelemetry tracing
- **CLI**: Run, validate, visualize chains from command line

## Installation

```bash
pip install -e .

# With all optional features
pip install -e ".[all]"
```

## Quick Start

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")

@ao.step(name="fetch")
async def fetch(ctx):
    ctx.set("data", [1, 2, 3])
    return {"fetched": True}

@ao.step(name="process", deps=["fetch"])
async def process(ctx):
    data = ctx.get("data")
    return {"sum": sum(data)}

@ao.chain(name="my_pipeline")
class MyPipeline:
    steps = ["fetch", "process"]

# Run
import asyncio
result = asyncio.run(ao.launch("my_pipeline", {}))
print(result)  # {"sum": 6, ...}
```

## CLI

```bash
agentorchestrator run my_pipeline --data '{"key": "value"}'
agentorchestrator check              # Validate definitions
agentorchestrator list               # List components
agentorchestrator graph my_pipeline  # Visualize DAG
agentorchestrator health             # Health check
agentorchestrator doctor             # Diagnose issues
```

## Documentation

| Document | Description |
|----------|-------------|
| [QUICKSTART](docs/QUICKSTART.md) | Get started in 5 minutes |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System design & diagrams |
| [USER_GUIDE](docs/USER_GUIDE.md) | Comprehensive usage guide |
| [API](docs/API.md) | Full API reference |
| [REQUIREMENTS](docs/REQUIREMENTS.md) | Dependencies & environment |
| [CMPT_CHAIN](docs/CMPT_CHAIN.md) | CMPT chain reference |
| [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) | Common issues |

## Project Structure

```
agentorchestrator/
├── core/           # AgentOrchestrator, Context, DAG, Registry
├── middleware/     # Cache, Logger, Summarizer, Offload
├── agents/         # BaseAgent, ResilientAgent
├── services/       # Gateway, Redis, Vector store services
├── chains/         # Pre-built chains (CMPT)
├── utils/          # Logging, tracing, config
├── testing/        # Test utilities
└── examples/       # Example chains
```

See `examples/usage_examples.py` for end-to-end samples (simple chain, decorator supervisor, squad supervisor).

## Environment (example)

```
# LLM Gateway
LLM_GATEWAY_SERVER_URL=https://llm-gateway/api/chat
LLM_GATEWAY_MODEL=claude-sonnet-4
LLM_GATEWAY_API_KEY=your_api_key_or_oauth_token

# Redis (optional, for chat/memory)
REDIS_HOST=redis.corp.local
REDIS_PORT=6379
REDIS_USERNAME=svc_user
REDIS_PASSWORD=secret
REDIS_SSL=true

# Vector store (optional, for RAG)
VECTOR_PROVIDER=memory          # or remote provider
VECTOR_HOST=https://vector/api  # required if using remote
VECTOR_API_KEY=vector_api_key
VECTOR_NAMESPACE=docs
```

## Optional RAG / Retrieval

You can inject retrieved context into chains using the pluggable vector store service:

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.services import VectorStoreService, VectorDocument

vs = VectorStoreService()  # in-memory by default, or configure VectorStoreConfig.from_env()
await vs.upsert([
    VectorDocument(id="doc1", text="Use async/await for I/O in Python APIs.")
])

ao = AgentOrchestrator(name="my_app")

@ao.step(name="retrieve")
async def retrieve(ctx):
    ctx.set("rag_context", await vs.query(ctx.get("query", "")))

@ao.step(name="answer", deps=["retrieve"])
async def answer(ctx):
    context = ctx.get("rag_context", [])
    return {"answer": f"Grounded answer with {len(context)} context snippets."}

@ao.chain(name="rag_chain")
class RAGChain:
    steps = ["retrieve", "answer"]
```

## Usage Patterns

### 1) Simple chain (with optional RAG + chat history)

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.services import VectorStoreService
from agentorchestrator.squad.storage.redis import RedisChatStorage

vs = VectorStoreService()           # in-memory unless VECTOR_* env set
chat = RedisChatStorage()           # use InMemoryChatStorage() if Redis is not set

ao = AgentOrchestrator(name="demo")

@ao.step(name="retrieve")
async def retrieve(ctx):
    ctx.set("rag_context", await vs.query(ctx.get("query", "")))

@ao.step(name="answer", deps=["retrieve"])
async def answer(ctx):
    snippets = ctx.get("rag_context", [])
    return {"answer": f"Answer with {len(snippets)} snippets"}

@ao.chain(name="demo_chain")
class DemoChain:
    steps = ["retrieve", "answer"]
```

- If you do not pass a vector store, `rag_context` is empty and the chain behaves as a non-RAG flow.
- If you do not pass chat storage, history is in-memory only.

### 2) Multi-agent supervisor (decorator path)

```python
from agentorchestrator.examples.supervisor_chain import create_supervisor_orchestrator
from agentorchestrator.services import VectorStoreService
from agentorchestrator.squad.storage.redis import RedisChatStorage
from agentorchestrator.services.llm_gateway import LLMGatewayClient

llm = LLMGatewayClient(server_url="https://llm-gateway/api/chat", api_key="api-key")
vs = VectorStoreService()
chat = RedisChatStorage()  # optional; defaults to in-memory if omitted

ao = create_supervisor_orchestrator(
    llm_client=llm,
    vector_store=vs,
    chat_storage=chat,
    agent_timeout_seconds=30.0,
)

result = await ao.launch("supervisor_chain", {
    "query": "How do I optimize my Python API?",
    "user_id": "u-123",
    "session_id": "s-456",
})
```

- If `vector_store` is omitted, retrieval is skipped.
- If `chat_storage` is omitted, history is stored in-memory.
- Agents receive `rag_context`, per-agent history, and metadata in `context` and are protected by per-agent timeouts.

## License

MIT
