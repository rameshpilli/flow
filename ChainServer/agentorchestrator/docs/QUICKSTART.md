# AgentOrchestrator Quickstart

Get up and running with AgentOrchestrator in 5 minutes.

## Installation

```bash
pip install -e ./agentorchestrator
```

## Hello World

```python
from agentorchestrator import AgentOrchestrator

# Create a forge instance
forge = AgentOrchestrator(name="my_app")

# Define a step
@forge.step(name="greet")
async def greet(ctx):
    name = ctx.get("name", "World")
    return {"greeting": f"Hello, {name}!"}

# Define a chain
@forge.chain(name="hello_chain")
class HelloChain:
    steps = ["greet"]

# Run it
import asyncio

async def main():
    result = await forge.launch("hello_chain", {"name": "AgentOrchestrator"})
    print(result["greeting"])  # "Hello, AgentOrchestrator!"

asyncio.run(main())
```

## Multi-Step Pipeline

```python
from agentorchestrator import AgentOrchestrator

forge = AgentOrchestrator(name="pipeline")

@forge.step(name="fetch")
async def fetch(ctx):
    # Simulate fetching data
    ctx.set("data", [1, 2, 3, 4, 5])
    return {"fetched": True}

@forge.step(name="process", deps=["fetch"])  # Runs after fetch
async def process(ctx):
    data = ctx.get("data")
    result = [x * 2 for x in data]
    ctx.set("processed", result)
    return {"processed": result}

@forge.step(name="summarize", deps=["process"])
async def summarize(ctx):
    data = ctx.get("processed")
    return {"sum": sum(data), "count": len(data)}

@forge.chain(name="data_pipeline")
class DataPipeline:
    steps = ["fetch", "process", "summarize"]

# Run
async def main():
    result = await forge.launch("data_pipeline", {})
    print(f"Sum: {result['sum']}, Count: {result['count']}")

asyncio.run(main())
```

## Parallel Execution

Steps without dependencies run in parallel:

```python
@forge.step(name="fetch_a")
async def fetch_a(ctx):
    await asyncio.sleep(1)  # Simulates slow API
    return {"a": "data_a"}

@forge.step(name="fetch_b")
async def fetch_b(ctx):
    await asyncio.sleep(1)  # Simulates slow API
    return {"b": "data_b"}

@forge.step(name="combine", deps=["fetch_a", "fetch_b"])
async def combine(ctx):
    return {"combined": True}

@forge.chain(name="parallel_chain")
class ParallelChain:
    steps = ["fetch_a", "fetch_b", "combine"]

# fetch_a and fetch_b run in parallel (total ~1s, not 2s)
```

## Add Middleware

```python
from agentorchestrator import AgentOrchestrator, LoggerMiddleware, CacheMiddleware

forge = AgentOrchestrator(name="my_app")

# Add logging
forge.use(LoggerMiddleware())

# Add caching (5 minute TTL)
forge.use(CacheMiddleware(ttl_seconds=300))
```

## Testing

```python
from agentorchestrator.testing import IsolatedForge

async def test_my_chain():
    async with IsolatedForge() as forge:
        @forge.step(name="test_step")
        async def test_step(ctx):
            return {"result": "ok"}

        @forge.chain(name="test_chain")
        class TestChain:
            steps = ["test_step"]

        result = await forge.launch("test_chain", {})
        assert result["success"]
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
