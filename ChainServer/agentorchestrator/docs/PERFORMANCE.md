# Performance Tuning Guide

This guide covers performance optimization for AgentOrchestrator applications.

## Performance Characteristics

### Execution Overhead

| Operation | Typical Latency | Notes |
|-----------|-----------------|-------|
| Step dispatch | <1ms | Fixed overhead per step |
| Context access | <0.1ms | In-memory |
| Redis context | 1-5ms | Network dependent |
| DAG build | 1-10ms | Scales with step count |
| Middleware chain | 0.1-1ms | Per middleware |

### Scaling Factors

- **Steps**: Linear scaling O(n)
- **Parallel steps**: Near-constant with proper concurrency
- **Middleware**: Linear per step
- **Context size**: Memory bound

## Configuration Tuning

### Parallel Execution

```python
# Tune based on workload
ao = AgentOrchestrator(
    max_parallel=10,  # Default: 10
    default_timeout_ms=30000,  # Default: 30s
)

# Group-level concurrency limits
# NOTE: max_concurrency applies at the parallel GROUP level, not per-step.
# If multiple steps in a group have different limits, the MINIMUM is used
# for the entire group. For true per-step limits, put rate-limited steps
# in their own parallel group or use in-handler rate limiting.
@ao.step(max_concurrency=3)  # Limits this step's parallel group
async def rate_limited_step(ctx):
    ...
```

### Guidelines

| Workload Type | Recommended `max_parallel` |
|---------------|---------------------------|
| I/O bound (API calls) | 10-50 |
| CPU bound | CPU cores |
| Mixed | 5-10 |
| Rate limited APIs | Match rate limit |

### Timeout Configuration

```python
# Global default
ao = AgentOrchestrator(default_timeout_ms=30000)

# Per-step override
@ao.step(timeout_ms=60000)  # 60 seconds for slow operations
async def long_running_step(ctx):
    ...
```

## Memory Optimization

### Context Cleanup

```python
# Enable automatic cleanup for long-running processes
await ao.start_auto_cleanup(
    interval_seconds=300,   # Every 5 minutes
    max_age_seconds=3600,   # Remove contexts older than 1 hour
)

# Manual cleanup after chain completion
await ao.launch("my_chain", data)
ao.remove_context(request_id)  # Free memory immediately
```

### Large Payload Handling

```python
from agentorchestrator.core import offload_to_redis, resolve_context_ref

# Offload large data to Redis
@ao.step
async def process_large_data(ctx):
    large_data = fetch_large_dataset()
    
    # Store in Redis, keep only reference in context
    ref = await offload_to_redis(large_data, ttl=3600)
    ctx.set("data_ref", ref)
    
    return {"reference": ref}

# Resolve when needed
@ao.step
async def use_large_data(ctx):
    ref = ctx.get("data_ref")
    data = await resolve_context_ref(ref)
    # Process data...
```

### Serialization Optimization

```python
from agentorchestrator.core import (
    create_safe_serializer,
    TruncatingSerializer,
)

# Create serializer that truncates large values
serializer = create_safe_serializer(
    max_string_length=1000,
    redact_keys=["password", "secret", "token"],
)

# Apply to context
ctx.set_serializer(serializer)
```

## Caching Strategies

### Step-Level Caching

```python
from agentorchestrator.middleware import CacheMiddleware

# Enable caching middleware
cache_middleware = CacheMiddleware(
    ttl_seconds=300,
    max_entries=1000,
    cache_key_fn=lambda ctx, step: f"{step}:{ctx.get('query')}",
)
ao.use(cache_middleware)

# Or use cache_key on step
@ao.step(cache_key=lambda ctx: f"search:{ctx.get('query')}")
async def cached_search(ctx):
    # This result will be cached
    return await expensive_search(ctx.get("query"))
```

### LLM Response Caching

```python
from agentorchestrator.services import LLMGatewayClient

# LLM client with caching
llm = LLMGatewayClient(
    cache_enabled=True,
    cache_ttl=3600,
    cache_backend="redis",  # or "memory"
)
```

## Async Best Practices

### Proper Async Usage

```python
# Good: Parallel async operations
@ao.step
async def fetch_multiple_sources(ctx):
    results = await asyncio.gather(
        fetch_from_api1(),
        fetch_from_api2(),
        fetch_from_api3(),
    )
    return {"results": results}

# Bad: Sequential async operations
@ao.step
async def fetch_sequential(ctx):  # DON'T DO THIS
    r1 = await fetch_from_api1()
    r2 = await fetch_from_api2()
    r3 = await fetch_from_api3()
    return {"results": [r1, r2, r3]}
```

### Connection Pooling

```python
import httpx

# Create pooled client as a resource
@ao.resource("http_client", cleanup=lambda c: c.aclose())
async def create_http_client():
    return httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
        ),
        timeout=httpx.Timeout(30.0),
    )

# Use in steps
@ao.step(resources=["http_client"])
async def fetch_data(ctx, http_client):
    response = await http_client.get("https://api.example.com/data")
    return {"data": response.json()}
```

## Profiling and Monitoring

### Timing Middleware

```python
from agentorchestrator.middleware import MetricsMiddleware

# Add timing metrics
metrics = MetricsMiddleware(
    histogram_buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)
ao.use(metrics)

# Access metrics
print(metrics.get_step_timings())
```

### OpenTelemetry Tracing

```python
from agentorchestrator.utils import configure_tracing

# Enable tracing
configure_tracing(
    service_name="my-service",
    endpoint="http://jaeger:4317",
)

# Traces are automatically collected for:
# - Chain execution
# - Step execution
# - LLM calls
# - External service calls
```

### Manual Profiling

```python
import cProfile
import pstats

# Profile a chain execution
profiler = cProfile.Profile()
profiler.enable()

result = ao.launch_sync("my_chain", data)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats("cumulative")
stats.print_stats(20)
```

## DAG Optimization

### Minimize Dependencies

```python
# Good: Parallel execution possible
@ao.step
async def step_a(ctx): ...

@ao.step
async def step_b(ctx): ...

@ao.step(deps=[step_a, step_b])
async def step_c(ctx): ...  # Runs after A and B (which run in parallel)

# Bad: Unnecessary sequential execution
@ao.step
async def step_a(ctx): ...

@ao.step(deps=[step_a])
async def step_b(ctx): ...  # Must wait for A even if not needed

@ao.step(deps=[step_b])
async def step_c(ctx): ...  # Must wait for B
```

### Explicit Parallel Groups

```python
@ao.chain
class OptimizedChain:
    steps = ["init", "process_a", "process_b", "finalize"]
    
    # Force parallel execution of independent steps
    parallel_groups = [
        ["process_a", "process_b"],
    ]
```

## Benchmarking

### Simple Benchmark

```python
import time
import statistics

async def benchmark_chain(ao, chain_name, data, iterations=100):
    times = []
    
    for _ in range(iterations):
        start = time.perf_counter()
        await ao.launch(chain_name, data)
        times.append(time.perf_counter() - start)
    
    return {
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "stdev": statistics.stdev(times),
        "min": min(times),
        "max": max(times),
        "p95": sorted(times)[int(len(times) * 0.95)],
    }

# Run benchmark
results = asyncio.run(benchmark_chain(ao, "my_chain", {"input": "test"}))
print(f"Mean: {results['mean']*1000:.2f}ms")
print(f"P95: {results['p95']*1000:.2f}ms")
```

## Common Performance Issues

### Issue: High Memory Usage

**Symptoms:** Memory grows over time, OOM errors

**Solutions:**
1. Enable auto context cleanup
2. Use context references for large data
3. Clear contexts after chain completion
4. Profile memory usage

### Issue: Slow Chain Execution

**Symptoms:** Chains take longer than expected

**Solutions:**
1. Check for unnecessary dependencies
2. Enable parallel execution
3. Add caching for repeated operations
4. Profile individual steps

### Issue: LLM Bottleneck

**Symptoms:** LLM calls dominate execution time

**Solutions:**
1. Enable LLM response caching
2. Use smaller/faster models where possible
3. Batch requests when supported
4. Consider streaming for long responses

### Issue: Redis Connection Issues

**Symptoms:** Timeouts, connection errors

**Solutions:**
1. Configure connection pooling
2. Use connection retry logic
3. Check network latency
4. Consider Redis cluster for high availability
