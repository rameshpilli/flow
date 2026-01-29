# AgentOrchestrator Quickstart

Get up and running in 5 minutes.

## Installation

```bash
pip install -e ./agentorchestrator
```

## Hello World

```python
from agentorchestrator import AgentOrchestrator
import asyncio

ao = AgentOrchestrator(name="my_app")

@ao.step(name="greet")
async def greet(ctx):
    name = ctx.get("name", "World")
    return {"greeting": f"Hello, {name}!"}

@ao.chain(name="hello_chain")
class HelloChain:
    steps = ["greet"]

result = asyncio.run(ao.launch("hello_chain", {"name": "AgentOrchestrator"}))
print(result["results"][0]["output"]["greeting"])  # "Hello, AgentOrchestrator!"
```

## Multi-Step Pipeline

```python
@ao.step(name="fetch")
async def fetch(ctx):
    ctx.set("data", [1, 2, 3, 4, 5])
    return {"fetched": True}

@ao.step(name="process", deps=["fetch"])  # Runs after fetch
async def process(ctx):
    result = [x * 2 for x in ctx.get("data")]
    ctx.set("processed", result)
    return {"processed": result}

@ao.step(name="summarize", deps=["process"])
async def summarize(ctx):
    data = ctx.get("processed")
    return {"sum": sum(data), "count": len(data)}

@ao.chain(name="pipeline")
class Pipeline:
    steps = ["fetch", "process", "summarize"]
```

## Parallel Execution

Steps without dependencies run in parallel:

```python
@ao.step(name="fetch_a")
async def fetch_a(ctx):
    await asyncio.sleep(1)
    return {"a": "data_a"}

@ao.step(name="fetch_b")
async def fetch_b(ctx):
    await asyncio.sleep(1)
    return {"b": "data_b"}

@ao.step(name="combine", deps=["fetch_a", "fetch_b"])
async def combine(ctx):
    return {"combined": True}

@ao.chain(name="parallel_chain")
class ParallelChain:
    steps = ["fetch_a", "fetch_b", "combine"]

# fetch_a and fetch_b run in parallel (~1s total, not 2s)
```

## Add Middleware

```python
from agentorchestrator.middleware import LoggerMiddleware, CacheMiddleware

ao.use(LoggerMiddleware())
ao.use(CacheMiddleware(ttl_seconds=300))
```

## CLI

```bash
ao run my_chain --data '{"name": "Test"}'  # Run chain
ao check                                    # Validate
ao graph my_chain                           # Visualize DAG
ao health                                   # Health check
```

## Next Steps

| Topic | Guide |
|-------|-------|
| Core concepts | [Understanding](understanding/index.md) |
| Multi-agent systems | [Multi-Agent](understanding/multi_agent.md) |
| Production patterns | [Patterns](patterns/index.md) |
| Large response handling | [Response Handling](patterns/large_response_handling.md) |
| CLI reference | [CLI](cli/index.md) |
| API reference | [API](API.md) |
