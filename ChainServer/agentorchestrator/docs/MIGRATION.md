# Migration Guide

This guide helps you migrate between versions of AgentOrchestrator.

## Version Compatibility

| From Version | To Version | Breaking Changes |
|--------------|------------|------------------|
| 0.x | 1.0 | Yes - see below |
| 1.0 | 1.1 | No |
| 1.1 | 1.2 | Minor - see below |

## Migrating to 1.0

### Import Changes

The package structure was reorganized for clarity:

```python
# Old (0.x)
from agentorchestrator import orchestrator
ao = orchestrator.get_default()

# New (1.0+)
from agentorchestrator import AgentOrchestrator
ao = AgentOrchestrator()
```

### Decorator Changes

Step registration now uses cleaner decorators:

```python
# Old (0.x)
@ao.register_step(name="my_step", dependencies=["other_step"])
async def my_step(context):
    return {"result": "value"}

# New (1.0+)
@ao.step(deps=["other_step"])
async def my_step(ctx):
    return {"result": "value"}
```

### Context API Changes

Context methods were renamed for consistency:

```python
# Old (0.x)
ctx.get_data("key")
ctx.set_data("key", value)
ctx.get_result("step_name")

# New (1.0+)
ctx.get("key")
ctx.set("key", value)
ctx.get_step_result("step_name")
```

### Chain Definition Changes

Chains now use class-based definitions:

```python
# Old (0.x)
ao.define_chain(
    name="MyChain",
    steps=["step1", "step2"],
    error_handling="continue",
)

# New (1.0+)
@ao.chain
class MyChain:
    steps = ["step1", "step2"]
    error_handling = "continue"
```

### Error Handling Changes

New exception hierarchy:

```python
# Old (0.x)
try:
    result = await ao.run("chain")
except Exception as e:
    if "not found" in str(e):
        # Handle not found
        pass

# New (1.0+)
from agentorchestrator.core.exceptions import (
    ChainNotFoundError,
    StepExecutionError,
)

try:
    result = await ao.launch("chain")
except ChainNotFoundError as e:
    print(f"Chain {e.chain_name} not found")
except StepExecutionError as e:
    print(f"Step {e.step_name} failed")
```

## Migrating to 1.2

### New Constants/Enums

Magic strings can now use enums (optional but recommended):

```python
# Old (1.1)
@ao.chain
class MyChain:
    error_handling = "fail_fast"

# New (1.2+) - both work
from agentorchestrator.core.constants import ErrorHandling

@ao.chain
class MyChain:
    error_handling = ErrorHandling.FAIL_FAST
    # or still: error_handling = "fail_fast"
```

### Pydantic Compatibility

New compat utilities for Pydantic v1/v2:

```python
# Old - manual version checking
if hasattr(model, "model_validate"):
    validated = model.model_validate(data)
else:
    validated = model.parse_obj(data)

# New - use compat utilities
from agentorchestrator.utils.compat import validate_model

validated = validate_model(Model, data)
```

### Event Bus Improvements

Subscription cleanup is now handled via context manager:

```python
# Old
sub = bus.subscribe()
try:
    async for event in sub:
        ...
finally:
    if hasattr(sub, "aclose"):
        await sub.aclose()

# New - recommended approach
sub = await bus.subscribe()
try:
    async for event in sub:
        ...
finally:
    await sub.aclose()  # Always available
```

### Auto Context Cleanup

New automatic cleanup for long-running processes:

```python
# Start auto cleanup (new in 1.2)
await ao.start_auto_cleanup(
    interval_seconds=300,
    max_age_seconds=3600,
)

# Stop when done
ao.stop_auto_cleanup()
```

## Migration Checklist

### From 0.x to 1.0

- [ ] Update imports
- [ ] Convert `@ao.register_step` to `@ao.step`
- [ ] Convert `@ao.register_chain` to `@ao.chain`
- [ ] Update context method calls (`get_data` → `get`)
- [ ] Replace `ao.run()` with `ao.launch()`
- [ ] Update error handling to use new exceptions
- [ ] Test all chains

### From 1.0/1.1 to 1.2

- [ ] (Optional) Convert magic strings to enums
- [ ] (Optional) Use compat utilities for Pydantic
- [ ] (Optional) Enable auto context cleanup
- [ ] Test all chains

## Deprecation Warnings

### Currently Deprecated (Will Remove in 2.0)

| Deprecated | Replacement | Since |
|------------|-------------|-------|
| `ao.run()` | `ao.launch()` | 1.0 |
| `ao.run_sync()` | `ao.launch_sync()` | 1.0 |
| `ctx.get_data()` | `ctx.get()` | 1.0 |
| `ctx.set_data()` | `ctx.set()` | 1.0 |

### Removed in 1.0

| Removed | Replacement |
|---------|-------------|
| `orchestrator.get_default()` | `AgentOrchestrator()` |
| `@ao.register_step()` | `@ao.step()` |
| `@ao.register_chain()` | `@ao.chain()` |

## Backward Compatibility

Most changes are backward compatible. The framework maintains aliases for deprecated methods:

```python
# These all work in 1.x
result = await ao.run("chain")      # Deprecated but works
result = await ao.launch("chain")   # Recommended

ctx.get_data("key")  # Deprecated but works
ctx.get("key")       # Recommended
```

Deprecation warnings are logged when using old methods:

```
DeprecationWarning: ao.run() is deprecated, use ao.launch() instead
```

## Testing Migration

### Create Migration Tests

```python
import pytest
from agentorchestrator import AgentOrchestrator

class TestMigration:
    """Tests to verify migration didn't break functionality."""
    
    @pytest.fixture
    def ao(self):
        return AgentOrchestrator(isolated=True)
    
    def test_chain_still_works(self, ao):
        @ao.step
        async def step1(ctx):
            return {"value": 1}
        
        @ao.chain
        class TestChain:
            steps = ["step1"]
        
        result = ao.launch_sync("TestChain")
        assert result["success"]
    
    def test_context_methods(self, ao):
        ctx = ao.create_context("test")
        ctx.set("key", "value")
        assert ctx.get("key") == "value"
```

### Run Full Test Suite

```bash
# Run all tests
pytest tests/ -v

# Run with deprecation warnings
pytest tests/ -v -W default::DeprecationWarning
```

## Getting Help

If you encounter issues during migration:

1. Check the [TROUBLESHOOTING.md](TROUBLESHOOTING.md) guide
2. Search existing issues
3. Create a new issue with:
   - Source version
   - Target version
   - Error messages
   - Minimal reproduction code
