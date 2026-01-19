# AgentOrchestrator Quickstart

Get up and running with AgentOrchestrator in 5 minutes.

## Installation

```bash
pip install -e ./agentorchestrator
```

## Hello World

```python
from agentorchestrator import AgentOrchestrator

# Create a ao instance
ao = AgentOrchestrator(name="my_app")

# Define a step
@ao.step(name="greet")
async def greet(ctx):
    name = ctx.get("name", "World")
    return {"greeting": f"Hello, {name}!"}

# Define a chain
@ao.chain(name="hello_chain")
class HelloChain:
    steps = ["greet"]

# Run it
import asyncio

async def main():
    result = await ao.launch("hello_chain", {"name": "AgentOrchestrator"})
    print(result["greeting"])  # "Hello, AgentOrchestrator!"

asyncio.run(main())
```

## Multi-Step Pipeline

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="pipeline")

@ao.step(name="fetch")
async def fetch(ctx):
    # Simulate fetching data
    ctx.set("data", [1, 2, 3, 4, 5])
    return {"fetched": True}

@ao.step(name="process", deps=["fetch"])  # Runs after fetch
async def process(ctx):
    data = ctx.get("data")
    result = [x * 2 for x in data]
    ctx.set("processed", result)
    return {"processed": result}

@ao.step(name="summarize", deps=["process"])
async def summarize(ctx):
    data = ctx.get("processed")
    return {"sum": sum(data), "count": len(data)}

@ao.chain(name="data_pipeline")
class DataPipeline:
    steps = ["fetch", "process", "summarize"]

# Run
async def main():
    result = await ao.launch("data_pipeline", {})
    print(f"Sum: {result['sum']}, Count: {result['count']}")

asyncio.run(main())
```

## Parallel Execution

Steps without dependencies run in parallel:

```python
@ao.step(name="fetch_a")
async def fetch_a(ctx):
    await asyncio.sleep(1)  # Simulates slow API
    return {"a": "data_a"}

@ao.step(name="fetch_b")
async def fetch_b(ctx):
    await asyncio.sleep(1)  # Simulates slow API
    return {"b": "data_b"}

@ao.step(name="combine", deps=["fetch_a", "fetch_b"])
async def combine(ctx):
    return {"combined": True}

@ao.chain(name="parallel_chain")
class ParallelChain:
    steps = ["fetch_a", "fetch_b", "combine"]

# fetch_a and fetch_b run in parallel (total ~1s, not 2s)
```

## Add Middleware

```python
from agentorchestrator import AgentOrchestrator, LoggerMiddleware, CacheMiddleware

ao = AgentOrchestrator(name="my_app")

# Add logging
ao.use(LoggerMiddleware())

# Add caching (5 minute TTL)
ao.use(CacheMiddleware(ttl_seconds=300))
```

## Testing

```python
from agentorchestrator.testing import IsolatedOrchestrator

async def test_my_chain():
    async with IsolatedOrchestrator() as ao:
        @ao.step(name="test_step")
        async def test_step(ctx):
            return {"result": "ok"}

        @ao.chain(name="test_chain")
        class TestChain:
            steps = ["test_step"]

        result = await ao.launch("test_chain", {})
        assert result["success"]
```

## Optional RAG + Chat History (quick peek)

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.services import VectorStoreService, VectorDocument
from agentorchestrator.squad.storage.memory import InMemoryChatStorage

vs = VectorStoreService()
chat = InMemoryChatStorage()
await vs.upsert([VectorDocument(id="d1", text="Use async/await for I/O")])

ao = AgentOrchestrator(name="rag_demo")

@ao.step(name="retrieve")
async def retrieve(ctx):
    ctx.set("rag_context", await vs.query(ctx.get("query", "")))

@ao.step(name="answer", deps=["retrieve"])
async def answer(ctx):
    return {"answer": f"Using {len(ctx.get('rag_context', []))} snippets"}

@ao.chain(name="rag_chain")
class RAGChain:
    steps = ["retrieve", "answer"]
```

## CLI

```bash
# Run a chain
agentorchestrator run my_chain --data '{"name": "Test"}'

# Validate definitions
agentorchestrator check

# List all registered components
agentorchestrator list

# Visualize chain DAG
agentorchestrator graph my_chain
```

## Next Steps

- See [API.md](API.md) for full API reference
- See [REQUIREMENTS.md](REQUIREMENTS.md) for production setup
- See [examples/](../examples/) for more complex examples
