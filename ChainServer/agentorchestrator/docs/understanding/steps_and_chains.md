# Steps & Chains

**Steps** are the building blocks of pipelines. **Chains** combine steps into directed acyclic graphs (DAGs) with automatic dependency resolution.

## Steps

A step is an async function decorated with `@ao.step()`:

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")

@ao.step(name="fetch_data")
async def fetch_data(ctx):
    data = await fetch_from_api()
    ctx.set("raw_data", data)
    return {"fetched": len(data)}
```

### Step Properties

| Property | Description |
|----------|-------------|
| `name` | Unique identifier for the step |
| `deps` | List of step names this depends on |
| `timeout_ms` | Maximum execution time (milliseconds) |
| `timeout` | Alias for timeout in seconds |
| `retry` | Number of retry attempts |
| `retry_delay` | Delay between retries (seconds) |

```python
@ao.step(
    name="process",
    deps=["fetch_data"],
    timeout=30,
    retry=3,
    retry_delay=1.0,
)
async def process(ctx):
    ...
```

### Step Return Values

Steps can return:

- **Dict** - Merged into chain result
- **None** - No contribution to result
- **Raise an exception** - Fails the step (with retry if configured)

```python
@ao.step(name="compute")
async def compute(ctx):
    return {"result": 42, "confidence": 0.95}
```

## Chains

A chain combines steps into a pipeline:

```python
@ao.chain(name="data_pipeline")
class DataPipeline:
    steps = ["fetch_data", "process", "summarize"]
```

### Dependency Resolution

The framework automatically determines execution order:

> Note: `steps = [...]` is not treated as an execution order unless you
> declare dependencies. Use `deps`, `dataflow=True`, or `parallel_groups`
> to enforce ordering.

```python
@ao.step(name="a")
async def step_a(ctx): ...

@ao.step(name="b")
async def step_b(ctx): ...

@ao.step(name="c", deps=["a", "b"])  # Waits for both
async def step_c(ctx): ...

@ao.step(name="d", deps=["c"])
async def step_d(ctx): ...

@ao.chain(name="my_chain")
class MyChain:
    steps = ["a", "b", "c", "d"]
```

Execution flow:
```
  ┌───┐   ┌───┐
  │ A │   │ B │   ← Run in parallel
  └─┬─┘   └─┬─┘
    │       │
    └───┬───┘
        ▼
      ┌───┐
      │ C │         ← Waits for A and B
      └─┬─┘
        │
        ▼
      ┌───┐
      │ D │         ← Waits for C
      └───┘
```

### Launching Chains

```python
# Async launch
result = await ao.launch("my_chain", {"input": "data"})

# Sync launch (wraps in asyncio.run)
result = ao.run_sync("my_chain", {"input": "data"})
```

## Advanced Patterns

### Dynamic DAG Modification (NEW)

Steps can dynamically inject new steps into the DAG during execution. This is useful for map-reduce patterns or conditional branching.

To inject steps, return a dictionary containing the special `__dynamic_steps__` key:

```python
@ao.step(name="planner")
async def planner(ctx):
    tasks = ["task_1", "task_2", "task_3"]
    
    # Create dynamic steps
    dynamic_steps = []
    for i, t in enumerate(tasks):
        dynamic_steps.append({
            "name": f"worker_{i}",
            "handler": my_worker_func,
            "deps": ["planner"]
        })
    
    return {
        "plan_complete": True,
        "__dynamic_steps__": dynamic_steps
    }
```

The executor will automatically:
1. Register the new steps
2. Execute them immediately after the current step
3. Make their outputs available to subsequent steps

### Sub-Chains

Chains can invoke other chains:

```python
@ao.step(name="run_analysis")
async def run_analysis(ctx):
    # Invoke another chain
    result = await ao.launch("analysis_chain", ctx.to_dict())
    ctx.set("analysis", result)
    return result

@ao.chain(name="main_pipeline")
class MainPipeline:
    steps = ["gather", "run_analysis", "report"]
```

### Step Middleware

Apply middleware to specific steps:

```python
from agentorchestrator.middleware import CacheMiddleware

# Cache only this step
ao.use(CacheMiddleware(ttl_seconds=3600, applies_to=["expensive_compute"]))

@ao.step(name="expensive_compute")
async def expensive_compute(ctx):
    ...
```

## Error Handling

### Retry Configuration

```python
@ao.step(name="flaky_api", retry=3, retry_delay=1.0)
async def flaky_api(ctx):
    response = await call_external_api()
    return response
```

### Fail-Fast vs Continue

```python
@ao.chain(name="resilient_chain")
class ResilientChain:
    steps = ["a", "b", "c"]
    error_handling = "continue"  # Continue on step failure
```

### Circuit Breaker

```python
from agentorchestrator.utils import CircuitBreaker

breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60)

@ao.step(name="protected")
@breaker
async def protected(ctx):
    ...
```

## Best Practices

!!! tip "Keep Steps Focused"
    Each step should do one thing well. Prefer many small steps over few large ones.

!!! tip "Use Dependencies Wisely"
    Only declare deps on steps you actually need data from. This maximizes parallelism.

!!! tip "Name Meaningfully"
    Use verb-noun names: `fetch_users`, `process_orders`, `generate_report`

!!! warning "Avoid Circular Dependencies"
    The DAG resolver will raise an error if cycles are detected.

## Next Steps

- [Agents](agents.md) - Add LLM capabilities to your steps
- [Context](context.md) - Deep dive into data flow
