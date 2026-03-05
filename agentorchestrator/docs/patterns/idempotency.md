# Idempotency Middleware

**IdempotencyMiddleware** prevents duplicate execution of expensive steps by caching results based on idempotency keys. This is critical for production reliability when steps may be retried or re-executed.

## Why Idempotency?

Without idempotency:
- Retrying a failed chain re-runs expensive API calls
- Network timeouts may cause duplicate operations
- User refreshes can trigger duplicate payments/actions

With IdempotencyMiddleware:
- Same inputs = same outputs (cached)
- Failed retries skip already-completed steps
- Duplicate requests return cached results

## Quick Start

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware.idempotency import (
    IdempotencyMiddleware,
    IdempotencyConfig,
)

ao = AgentOrchestrator(name="my_app")

# Add idempotency middleware
middleware = IdempotencyMiddleware()
ao.add_middleware(middleware)

# Steps are automatically deduplicated based on inputs
@ao.step(name="expensive_api_call")
async def expensive_api_call(ctx):
    data = ctx.get("query")
    result = await call_expensive_api(data)
    return {"result": result}
```

## Configuration

### IdempotencyConfig Options

```python
from agentorchestrator.middleware.idempotency import IdempotencyConfig

config = IdempotencyConfig(
    # TTL for cached results (None = no expiration)
    ttl_seconds=3600,  # 1 hour

    # Include step name in key generation
    include_step_name=True,

    # Include request_id (False = cross-request dedup)
    include_request_id=False,

    # Fields to exclude from auto-generated keys
    exclude_fields=["timestamp", "request_id"],

    # Whether to log cache hits
    log_hits=True,

    # Maximum cached entries (memory backend only)
    max_entries=10000,
)

middleware = IdempotencyMiddleware(config=config)
```

### Key Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `ttl_seconds` | `3600` | Cache expiration time |
| `include_step_name` | `True` | Include step name in cache key |
| `include_request_id` | `False` | If `True`, cache is per-request only |
| `exclude_fields` | `["timestamp", "request_id"]` | Fields to ignore in key generation |
| `log_hits` | `True` | Log when cache is hit |
| `max_entries` | `10000` | Max entries for in-memory backend |

## Custom Idempotency Keys

### Per-Step Key Functions

Define custom key functions for specific steps:

```python
@ao.step(
    name="fetch_stock_data",
    idempotency_key=lambda ctx: f"{ctx.get('ticker')}:{ctx.get('date')}",
)
async def fetch_stock_data(ctx):
    ticker = ctx.get("ticker")
    date = ctx.get("date")
    return await fetch_market_data(ticker, date)
```

### Middleware-Level Key Functions

Register key functions with the middleware:

```python
def stock_key(ctx):
    return f"stock:{ctx.get('ticker')}:{ctx.get('date')}"

def user_key(ctx):
    return f"user:{ctx.get('user_id')}"

middleware = IdempotencyMiddleware(
    key_functions={
        "fetch_stock_data": stock_key,
        "get_user_profile": user_key,
    }
)
```

### Disabling Idempotency

For steps that should always run:

```python
@ao.step(name="send_notification", idempotent=False)
async def send_notification(ctx):
    # This step runs every time, even with same inputs
    await send_email(ctx.get("email"), ctx.get("message"))
    return {"sent": True}
```

## Storage Backends

### In-Memory (Default)

Good for development and single-process deployments:

```python
middleware = IdempotencyMiddleware()  # Uses InMemoryIdempotencyBackend
```

### Redis (Production)

For distributed deployments with multiple workers:

```python
from agentorchestrator.middleware.idempotency import (
    create_redis_idempotency_middleware,
    IdempotencyConfig,
)

# Simple setup
middleware = create_redis_idempotency_middleware(
    redis_url="redis://localhost:6379",
)

# With configuration
middleware = create_redis_idempotency_middleware(
    redis_url="redis://redis-service:6379",
    config=IdempotencyConfig(ttl_seconds=7200),
    key_prefix="ao:idempotency:",
)
```

**Note**: Redis backend requires the `redis` package:
```bash
pip install 'agentorchestrator[redis]'
```

## How It Works

### Key Generation

1. **Custom key function** (if provided) takes priority
2. **Step-level `idempotency_key`** is checked next
3. **Auto-generation** hashes context data (excluding specified fields)

Auto-generated keys look like:
```
step:fetch_data:data:a1b2c3d4e5f6
```

### Execution Flow

```
Request arrives
    ↓
Generate idempotency key
    ↓
Check cache for key
    ↓
┌─────────────┐     ┌─────────────┐
│ Cache HIT   │     │ Cache MISS  │
└─────────────┘     └─────────────┘
       ↓                   ↓
Return cached         Execute step
result                     ↓
                    Store result
                    in cache
                          ↓
                    Return result
```

## Monitoring & Statistics

### Get Cache Statistics

```python
stats = middleware.stats()
print(stats)
# {
#     "hits": 150,
#     "misses": 50,
#     "total": 200,
#     "hit_rate_percent": 75.0,
#     "backend": {
#         "total_entries": 120,
#         "expired_entries": 5,
#         "max_entries": 10000
#     }
# }
```

### Check for Cached Results in Steps

```python
@ao.step(name="expensive_computation")
async def expensive_computation(ctx):
    # Check if result was cached
    cached = middleware.get_cached_result(ctx, "expensive_computation")
    if cached:
        logger.info("Using cached result")
        return cached

    # Compute if not cached
    result = await compute_expensive_result()
    return result
```

## Cache Management

### Invalidate Specific Key

```python
# Invalidate when underlying data changes
await middleware.invalidate("step:fetch_data:data:a1b2c3d4")
```

### Clear All Cached Results

```python
# Clear cache on deployment or data refresh
await middleware.clear_cache()
```

## Use Cases

### 1. API Rate Limiting Protection

```python
@ao.step(
    name="call_rate_limited_api",
    idempotency_key=lambda ctx: f"api:{ctx.get('endpoint')}:{ctx.get('params_hash')}",
)
async def call_rate_limited_api(ctx):
    # Same request returns cached result, saving API quota
    return await external_api.call(ctx.get("endpoint"), ctx.get("params"))
```

### 2. Payment Processing

```python
@ao.step(
    name="process_payment",
    idempotency_key=lambda ctx: f"payment:{ctx.get('order_id')}:{ctx.get('amount')}",
)
async def process_payment(ctx):
    # Retries don't cause duplicate charges
    return await payment_gateway.charge(
        order_id=ctx.get("order_id"),
        amount=ctx.get("amount"),
    )
```

### 3. Data Pipeline Resumability

```python
middleware = create_redis_idempotency_middleware(
    redis_url="redis://localhost:6379",
    config=IdempotencyConfig(ttl_seconds=86400),  # 24 hour TTL
)

@ao.step(name="transform_large_dataset")
async def transform_large_dataset(ctx):
    # If pipeline fails and restarts, completed transforms are skipped
    return await transform(ctx.get("dataset_partition"))
```

## Best Practices

### 1. Choose Appropriate TTL

- **Short TTL (5-15 min)**: Real-time data, frequent updates
- **Medium TTL (1-4 hours)**: API responses, computed results
- **Long TTL (24+ hours)**: Expensive computations, stable data

### 2. Design Good Keys

```python
# Good: Specific, deterministic
idempotency_key=lambda ctx: f"{ctx.get('user_id')}:{ctx.get('action')}:{ctx.get('resource_id')}"

# Bad: Too broad (may return wrong cached result)
idempotency_key=lambda ctx: ctx.get('user_id')

# Bad: Non-deterministic (defeats caching)
idempotency_key=lambda ctx: f"{ctx.get('data')}:{time.time()}"
```

### 3. Use Redis for Production

```python
# Development
middleware = IdempotencyMiddleware()

# Production
middleware = create_redis_idempotency_middleware(
    redis_url=os.getenv("REDIS_URL"),
    config=IdempotencyConfig(ttl_seconds=3600),
)
```

### 4. Exclude Volatile Fields

```python
config = IdempotencyConfig(
    exclude_fields=["timestamp", "request_id", "trace_id", "random_seed"],
)
```

## Comparison with CacheMiddleware

| Feature | IdempotencyMiddleware | CacheMiddleware |
|---------|----------------------|-----------------|
| Primary Use | Prevent duplicate execution | Speed up repeated calls |
| Key Generation | Context-based hash | Custom key functions |
| Storage | Memory or Redis | Memory or Redis |
| TTL | Configurable | Configurable |
| Statistics | Hits/misses tracking | Basic |
| Best For | Payment, API calls | Read-heavy workloads |

## Next Steps

- [Middleware Decision Guide](middleware_selection.md) - Choose the right middleware
- [Resumable Chains](../understanding/resumability.md) - Combine with checkpointing
- [Rate Limiting](rate_limiting.md) - Control request rates
