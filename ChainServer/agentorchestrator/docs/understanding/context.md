# Context

The **ChainContext** is the shared state container that flows through every step in your pipeline. It's how steps communicate data without tight coupling.

## What is Context?

Context is a scoped key-value store that:

- Stores data produced by steps
- Provides data to downstream steps
- Manages lifecycle with automatic cleanup
- Supports different visibility scopes

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")

@ao.step(name="producer")
async def producer(ctx):
    # Store data in context
    ctx.set("user_data", {"name": "Alice", "score": 95})
    return {"produced": True}

@ao.step(name="consumer", deps=["producer"])
async def consumer(ctx):
    # Retrieve data from context
    user = ctx.get("user_data")
    return {"message": f"Hello, {user['name']}!"}
```

## Context Scopes

Data can be stored with different lifetimes:

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| `STEP` | Single step | Temporary scratch data |
| `CHAIN` | Entire chain | Share between steps |
| `SESSION` | User session | Persist across chains |
| `GLOBAL` | Application | Configuration, constants |

```python
from agentorchestrator.core.context import Scope

@ao.step(name="example")
async def example(ctx):
    # Step-scoped (cleared after this step)
    ctx.set("temp", "scratch", scope=Scope.STEP)

    # Chain-scoped (default - lives for chain duration)
    ctx.set("shared", "between steps")

    # Session-scoped (persists across chains in session)
    ctx.set("user_prefs", {"theme": "dark"}, scope=Scope.SESSION)
```

## Context Methods

### Basic Operations

```python
# Set a value
ctx.set("key", value)

# Get with default
data = ctx.get("key", default=None)

# Check existence
if ctx.has("key"):
    ...

# Delete
ctx.delete("key")
```

### Batch Operations

```python
# Get multiple keys
values = ctx.get_many(["key1", "key2", "key3"])

# Set multiple at once
ctx.set_many({
    "key1": "value1",
    "key2": "value2",
})
```

### Metadata

```python
# Add metadata for tracing
ctx.set("result", data, metadata={
    "source": "api_call",
    "timestamp": datetime.now(),
})

# Retrieve with metadata
value, meta = ctx.get_with_metadata("result")
```

## Large Data Handling

For large payloads, context supports Redis offloading:

```python
from agentorchestrator.middleware import OffloadMiddleware
from agentorchestrator.services import RedisContextStore

ao.use(OffloadMiddleware(
    store=RedisContextStore(),
    threshold_bytes=100_000,  # Offload data > 100KB
))

@ao.step(name="big_data")
async def big_data(ctx):
    huge_result = fetch_large_dataset()

    # Automatically offloaded to Redis if > threshold
    ctx.set("dataset", huge_result)
    return {"stored": True}
```

When offloaded, context stores a `ContextRef` that transparently retrieves data on access.

## Context in Multi-Agent Systems

For multi-agent scenarios, each agent can have isolated context via namespaces:

```python
from agentorchestrator.squad.context import ContextIsolationManager

# Supervisor creates isolation
isolation = ContextIsolationManager(coordinator_context=ctx)

# Each agent gets isolated namespace
for agent in team:
    namespace = isolation.create_namespace(agent.id)
    # Agent only sees its own data + explicitly shared keys
```

See [Multi-Agent Systems](multi_agent.md) for full details on context isolation.

## Best Practices

!!! tip "Use Descriptive Keys"
    Prefix keys with their source: `news_headlines`, `sec_filings`, `earnings_data`

!!! tip "Scope Appropriately"
    Use STEP scope for temporary data to reduce memory pressure

!!! tip "Cap Large Collections"
    Use `ctx.set("items", data[:100])` to prevent context bloat

!!! warning "Don't Store Secrets"
    Never store API keys or credentials in context

## Next Steps

- [Steps & Chains](steps_and_chains.md) - Learn how context flows through pipelines
- [Agents](agents.md) - See how agents use context for memory
