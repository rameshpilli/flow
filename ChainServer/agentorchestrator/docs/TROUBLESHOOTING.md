# AgentOrchestrator Troubleshooting Guide

Common issues and solutions for AgentOrchestrator applications.

## Quick Diagnostics

```bash
# Check chain definitions
agentorchestrator check

# Validate specific chain with dry-run
agentorchestrator validate my_chain

# Full health check
agentorchestrator health --detailed

# Debug mode with snapshots
agentorchestrator debug my_chain --company "Apple" --snapshot-dir ./debug
```

---

## Chain Execution Issues

### Chain Not Found

**Error:** `ValueError: Chain 'my_chain' not found`

**Solution:**
1. Ensure chain is imported before running:
   ```python
   # In your main file or chains/__init__.py
   from my_app.chains import my_chain  # noqa: F401
   ```
2. Check chain registration:
   ```bash
   agentorchestrator list
   ```
3. Verify chain decorator:
   ```python
   @forge.chain(name="my_chain")  # Name must match
   class MyChain:
       steps = [...]
   ```

### Step Dependency Cycle

**Error:** `DAGValidationError: Cycle detected in step dependencies`

**Solution:**
1. Visualize the DAG:
   ```bash
   agentorchestrator graph my_chain
   ```
2. Remove circular dependencies:
   ```python
   # BAD: Circular dependency
   @forge.step(deps=[step_b])
   async def step_a(ctx): ...

   @forge.step(deps=[step_a])
   async def step_b(ctx): ...

   # GOOD: Linear dependency
   @forge.step()
   async def step_a(ctx): ...

   @forge.step(deps=[step_a])
   async def step_b(ctx): ...
   ```

### Step Timeout

**Error:** `asyncio.TimeoutError: Step 'my_step' timed out after 30s`

**Solutions:**
1. Increase timeout:
   ```python
   @forge.step(timeout_ms=60000)  # 60 seconds
   async def my_step(ctx): ...
   ```
2. Add progress logging to identify bottleneck
3. Break into smaller steps

### Missing Context Data

**Error:** `KeyError: 'my_data' not found in context`

**Solutions:**
1. Check step dependency order:
   ```python
   @forge.step(name="producer", produces=["my_data"])
   async def producer(ctx):
       ctx.set("my_data", {...})  # Must set the data
       return {...}

   @forge.step(deps=[producer])  # Must depend on producer
   async def consumer(ctx):
       data = ctx.get("my_data")  # Now available
   ```
2. Use default value:
   ```python
   data = ctx.get("my_data", default={})
   ```

---

## Agent Issues

### Agent Health Check Failed

**Error:** `Agent 'news_agent' health check failed`

**Solutions:**
1. Check agent configuration:
   ```python
   agent = forge.get_agent("news_agent")
   print(agent.config)  # Verify settings
   ```
2. Test agent directly:
   ```python
   result = await agent.fetch("test query")
   print(result.error)  # Check for errors
   ```
3. Use ResilientAgent for automatic retry:
   ```python
   from agentorchestrator.agents import ResilientAgent, ResilientAgentConfig

   resilient = ResilientAgent(
       agent=my_agent,
       config=ResilientAgentConfig(
           timeout_seconds=10.0,
           max_retries=3,
       ),
   )
   ```

### Circuit Breaker Open

**Error:** `Circuit breaker open for 'news_agent'`

**Cause:** Too many consecutive failures triggered the circuit breaker.

**Solutions:**
1. Wait for recovery timeout (default 30s)
2. Check underlying service health
3. Reset circuit manually:
   ```python
   from agentorchestrator.utils.circuit_breaker import reset_all_circuit_breakers
   reset_all_circuit_breakers()
   ```
4. Adjust thresholds:
   ```python
   config = ResilientAgentConfig(
       circuit_failure_threshold=10,  # More failures before opening
       circuit_recovery_seconds=60.0,  # Longer recovery
   )
   ```

### Plugin Not Found

**Error:** `Plugin 'my_plugin' not found`

**Solutions:**
1. Check entry point registration in `pyproject.toml`:
   ```toml
   [project.entry-points."agentorchestrator.agents"]
   my_plugin = "my_package.agents:MyAgent"
   ```
2. Reinstall package:
   ```bash
   pip install -e .
   ```
3. Verify discovery:
   ```python
   from agentorchestrator.plugins import discover_plugins
   plugins = discover_plugins()
   print(plugins)
   ```

---

## Context Store Issues

### Redis Connection Failed

**Error:** `ConnectionError: Cannot connect to Redis`

**Solutions:**
1. Verify Redis is running:
   ```bash
   redis-cli ping  # Should return PONG
   ```
2. Check connection settings:
   ```python
   from agentorchestrator.core.context_store import RedisContextStore

   store = RedisContextStore(
       host="localhost",
       port=6379,
       password=None,  # If needed
   )
   ```
3. Use in-memory store for development:
   ```python
   from agentorchestrator.core.context_store import InMemoryContextStore
   store = InMemoryContextStore()
   ```

### Large Payload Error

**Error:** `PayloadTooLarge: Data exceeds maximum size`

**Solutions:**
1. Use offloading middleware:
   ```python
   from agentorchestrator.middleware import OffloadMiddleware
   from agentorchestrator.core import RedisContextStore

   forge.use_middleware(OffloadMiddleware(
       store=RedisContextStore(),
       default_threshold_bytes=100_000,  # 100KB
   ))
   ```
2. Manually offload large data:
   ```python
   from agentorchestrator.core import offload_to_redis

   ref = await offload_to_redis(
       ctx, "large_data", big_payload,
       threshold_bytes=50_000,
   )
   ctx.set("data_ref", ref)  # Store ref, not full data
   ```

---

## Resumable Chain Issues

### Cannot Resume Run

**Error:** `ValueError: Run 'run_xxx' not found`

**Solutions:**
1. Check run exists:
   ```bash
   agentorchestrator runs --limit 50
   agentorchestrator run-info run_xxx
   ```
2. Verify checkpoint directory:
   ```python
   forge = AgentOrchestrator(checkpoint_dir="./checkpoints")
   ```
3. Check run status:
   ```python
   run = await forge.get_run(run_id)
   print(run.status)  # Must be "partial" or "failed"
   ```

### Stale Checkpoint Data

**Problem:** Resuming uses outdated data after code changes.

**Solutions:**
1. Clear old checkpoints:
   ```bash
   rm -rf ./checkpoints/*
   ```
2. Start fresh run:
   ```python
   result = await forge.launch_resumable(chain_name, data, run_id=None)
   ```

---

## Validation Issues

### Input Validation Failed

**Error:** `ContractValidationError: Field 'company_name' required`

**Solutions:**
1. Provide required fields:
   ```python
   await forge.launch("my_chain", {
       "company_name": "Apple Inc",  # Required field
   })
   ```
2. Check model definition:
   ```python
   class MyInput(BaseModel):
       company_name: str  # Required
       limit: int = 10    # Optional with default
   ```

### Schema Drift

**Problem:** Old data doesn't match new schema after update.

**Solutions:**
1. Use migrations:
   ```python
   from agentorchestrator.core.versioning import MigrationManager

   # Create a manager per service (no global helper)
   manager = MigrationManager()

   @manager.migration("1.0.0", "2.0.0")
   def migrate(data):
       return {
           "new_field": data.get("old_field"),
           **data,
       }
   ```
2. Validate before migration:
   ```bash
   agentorchestrator validate my_chain --data '{"old_format": "data"}'
   ```

---

## Performance Issues

### Slow Chain Execution

**Diagnostics:**
1. Enable debug mode:
   ```bash
   agentorchestrator debug my_chain --snapshot-dir ./debug
   ```
2. Check step timings in snapshots
3. Enable tracing:
   ```python
   from agentorchestrator.utils.tracing import configure_tracing
   configure_tracing(service_name="my-app", endpoint="http://jaeger:4317")
   ```

**Solutions:**
1. Add caching:
   ```python
   from agentorchestrator.middleware import CacheMiddleware
   forge.use_middleware(CacheMiddleware(ttl_seconds=300))
   ```
2. Increase parallelism:
   ```python
   forge = AgentOrchestrator(max_parallel=20)  # Default is 10
   ```
3. Use parallel groups:
   ```python
   @forge.chain(
       parallel_groups=[
           ["extract"],
           ["fetch_news", "fetch_sec", "fetch_earnings"],  # Parallel
           ["combine"],
       ]
   )
   ```

### Memory Issues

**Problem:** High memory usage with large payloads.

**Solutions:**
1. Use context offloading (see Large Payload Error above)
2. Enable auto-summarization:
   ```python
   forge.use_middleware(TokenManagerMiddleware(
       max_total_tokens=100000,
       auto_summarize=True,
       auto_offload=True,
   ))
   ```
3. Process data in chunks:
   ```python
   for chunk in chunks(large_dataset, size=1000):
       await process_chunk(chunk)
   ```

---

## API Server Issues

### Server Won't Start

**Error:** `ModuleNotFoundError: No module named 'fastapi'`

**Solution:**
```bash
pip install -e ".[api]"
```

### CORS Errors

**Error:** `Access-Control-Allow-Origin` header missing

**Solution:** Check CORS middleware in `api.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Health Check Failing

**Endpoint:** `GET /health` returns 503

**Solutions:**
1. Check component health:
   ```bash
   agentorchestrator health --detailed --verbose
   ```
2. Verify dependencies (Redis, LLM):
   ```python
   result = await run_health_checks(include_external=True)
   for comp in result.components:
       print(f"{comp.name}: {comp.status} - {comp.message}")
   ```

---

## Getting Help

1. **Check logs:** Enable debug logging:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Run diagnostics:**
   ```bash
   agentorchestrator health --detailed --json > health.json
   agentorchestrator validate my_chain --json > validation.json
   ```

3. **Report issues:** https://github.com/agentorchestrator/agentorchestrator/issues
   - Include error message
   - Include AgentOrchestrator version: `agentorchestrator version --json`
   - Include diagnostic output
