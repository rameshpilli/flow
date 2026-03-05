"""
Tests for Pydantic state management in ChainContext.

Tests the type-safe state management features including:
- StateStore with Pydantic models
- ChainContext with state_model parameter
- Atomic state updates via edit_state()
- Type safety and validation
- Concurrent access
"""

import asyncio
import pytest
from pydantic import BaseModel, Field, ValidationError

from agentorchestrator import AgentOrchestrator, Context
from agentorchestrator.core.context import ChainContext
from agentorchestrator.core.state import StateStore


# =============================================================================
# Test Models
# =============================================================================


class CounterState(BaseModel):
    """Simple counter state for testing."""
    count: int = Field(default=0)
    name: str = Field(default="default")


class PipelineState(BaseModel):
    """Complex state with multiple fields."""
    counter: int = Field(default=0)
    items: list[str] = Field(default_factory=list)
    processed: bool = Field(default=False)
    metadata: dict[str, int] = Field(default_factory=dict)


class ValidatedState(BaseModel):
    """State with validation rules."""
    count: int = Field(default=0, ge=0, le=100)  # Must be 0-100
    email: str = Field(default="user@example.com", pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")


# =============================================================================
# StateStore Tests
# =============================================================================


def test_state_store_init():
    """Test StateStore initialization."""
    store = StateStore(CounterState)
    assert store.state.count == 0
    assert store.state.name == "default"


def test_state_store_init_with_initial_state():
    """Test StateStore with initial state."""
    initial = CounterState(count=10, name="custom")
    store = StateStore(CounterState, initial_state=initial)
    assert store.state.count == 10
    assert store.state.name == "custom"


@pytest.mark.asyncio
async def test_state_store_edit():
    """Test atomic state updates via edit()."""
    store = StateStore(CounterState)
    
    async with store.edit() as state:
        state.count = 5
        state.name = "updated"
    
    assert store.state.count == 5
    assert store.state.name == "updated"


@pytest.mark.asyncio
async def test_state_store_edit_rollback_on_error():
    """Test that state is rolled back on error."""
    store = StateStore(CounterState)
    store._state.count = 10
    
    with pytest.raises(ValueError):
        async with store.edit() as state:
            state.count = 20
            raise ValueError("Simulated error")
    
    # State should be unchanged
    assert store.state.count == 10


@pytest.mark.asyncio
async def test_state_store_validation():
    """Test that invalid state raises ValidationError."""
    store = StateStore(ValidatedState, ValidatedState(count=50, email="test@example.com"))
    
    with pytest.raises(ValidationError):
        async with store.edit() as state:
            state.count = 150  # Exceeds max of 100


def test_state_store_to_dict():
    """Test state export to dictionary."""
    store = StateStore(CounterState)
    store._state.count = 42
    
    data = store.to_dict()
    assert data == {"count": 42, "name": "default"}


def test_state_store_from_dict():
    """Test state import from dictionary."""
    store = StateStore(CounterState)
    store.from_dict({"count": 99, "name": "loaded"})
    
    assert store.state.count == 99
    assert store.state.name == "loaded"


def test_state_store_reset():
    """Test state reset to initial values."""
    initial = CounterState(count=5, name="initial")
    store = StateStore(CounterState, initial_state=initial)
    
    store._state.count = 100
    store._state.name = "modified"
    
    store.reset()
    
    assert store.state.count == 5
    assert store.state.name == "initial"


def test_state_store_clone():
    """Test state store cloning."""
    store1 = StateStore(CounterState)
    store1._state.count = 10
    
    store2 = store1.clone()
    store2._state.count = 20
    
    # Original unchanged
    assert store1.state.count == 10
    assert store2.state.count == 20


@pytest.mark.asyncio
async def test_state_store_concurrent_edits():
    """Test that concurrent edits are serialized."""
    store = StateStore(CounterState)
    
    async def increment():
        async with store.edit() as state:
            current = state.count
            await asyncio.sleep(0.01)  # Simulate work
            state.count = current + 1
    
    # Run 10 concurrent increments
    await asyncio.gather(*[increment() for _ in range(10)])
    
    # Should be 10 (not less due to race conditions)
    assert store.state.count == 10


# =============================================================================
# ChainContext with State Model Tests
# =============================================================================


def test_context_with_state_model():
    """Test ChainContext with Pydantic state model."""
    ctx = ChainContext("req_1", state_model=CounterState)
    
    assert ctx.state.count == 0
    assert ctx.state.name == "default"


@pytest.mark.asyncio
async def test_context_edit_state():
    """Test atomic state updates via ctx.edit_state()."""
    ctx = ChainContext("req_1", state_model=PipelineState)
    
    async with ctx.edit_state() as state:
        state.counter += 1
        state.items.append("item1")
        state.processed = True
    
    assert ctx.state.counter == 1
    assert ctx.state.items == ["item1"]
    assert ctx.state.processed is True


@pytest.mark.asyncio
async def test_context_edit_state_rollback():
    """Test that state changes rollback on error."""
    ctx = ChainContext("req_1", state_model=PipelineState)
    
    async with ctx.edit_state() as state:
        state.counter = 5
    
    with pytest.raises(ValueError):
        async with ctx.edit_state() as state:
            state.counter = 10
            raise ValueError("Error")
    
    # Should still be 5
    assert ctx.state.counter == 5


def test_context_without_state_model_raises():
    """Test that accessing state without model raises error."""
    ctx = ChainContext("req_1")  # No state_model
    
    with pytest.raises(RuntimeError, match="not created with a state_model"):
        _ = ctx.state


@pytest.mark.asyncio
async def test_context_edit_state_without_model_raises():
    """Test that edit_state without model raises error."""
    ctx = ChainContext("req_1")  # No state_model
    
    with pytest.raises(RuntimeError, match="not created with a state_model"):
        async with ctx.edit_state() as state:
            pass


# =============================================================================
# Integration with Steps Tests
# =============================================================================


@pytest.mark.asyncio
async def test_step_with_state_model():
    """Test step decorated with state_model parameter."""
    ao = AgentOrchestrator(name="test", isolated=True)

    @ao.step(name="increment", state_model=CounterState)
    async def increment(ctx: Context[CounterState]):
        async with ctx.edit_state() as state:
            state.count += 1
        return {"count": ctx.state.count}
    
    # Verify the decorator stored the state_model
    step_spec = ao._step_registry.get_spec("increment")
    assert hasattr(increment, "_fg_state_model")
    assert increment._fg_state_model == CounterState

    @ao.chain(name="state_chain")
    class StateChain:
        steps = ["increment"]

    result = await ao.launch("state_chain")

    assert result["success"] is True
    assert result["results"][0]["output"]["count"] == 1


@pytest.mark.asyncio
async def test_multiple_steps_sharing_state():
    """Test multiple steps sharing typed state."""
    ctx = ChainContext("req_1", state_model=PipelineState)
    
    # Simulate step 1
    async with ctx.step_scope("step1"):
        async with ctx.edit_state() as state:
            state.counter = 1
            state.items.append("from_step1")
    
    # Simulate step 2
    async with ctx.step_scope("step2"):
        async with ctx.edit_state() as state:
            state.counter += 1
            state.items.append("from_step2")
            state.processed = True
    
    # Verify final state
    assert ctx.state.counter == 2
    assert ctx.state.items == ["from_step1", "from_step2"]
    assert ctx.state.processed is True


@pytest.mark.asyncio
async def test_state_with_parallel_steps():
    """Test state updates from parallel steps."""
    ctx = ChainContext("req_1", state_model=PipelineState)
    
    async def step_task(step_name: str, item: str):
        async with ctx.step_scope(step_name):
            async with ctx.edit_state() as state:
                state.items.append(item)
                state.counter += 1
    
    # Run 5 parallel "steps"
    await asyncio.gather(
        step_task("step1", "item1"),
        step_task("step2", "item2"),
        step_task("step3", "item3"),
        step_task("step4", "item4"),
        step_task("step5", "item5"),
    )
    
    # All updates should be applied atomically
    assert ctx.state.counter == 5
    assert len(ctx.state.items) == 5
    assert set(ctx.state.items) == {"item1", "item2", "item3", "item4", "item5"}


@pytest.mark.asyncio
async def test_chain_rejects_multiple_state_models():
    """Chains should not mix different state models."""
    ao = AgentOrchestrator(name="state_model_conflict", isolated=True)

    @ao.step(name="step1", state_model=CounterState)
    async def step1(ctx: Context[CounterState]):
        async with ctx.edit_state() as state:
            state.count += 1
        return {"count": ctx.state.count}

    @ao.step(name="step2", deps=["step1"], state_model=PipelineState)
    async def step2(ctx: Context[PipelineState]):
        async with ctx.edit_state() as state:
            state.counter += 1
        return {"counter": ctx.state.counter}

    @ao.chain(name="bad_state_chain")
    class BadStateChain:
        steps = ["step1", "step2"]

    with pytest.raises(ValueError, match="multiple state models"):
        await ao.launch("bad_state_chain")


# =============================================================================
# Type Safety Tests
# =============================================================================


@pytest.mark.asyncio
async def test_type_safety_with_validation():
    """Test that Pydantic validation catches type errors."""
    ctx = ChainContext("req_1", state_model=ValidatedState, initial_data={})
    
    # Initialize with valid state
    async with ctx.edit_state() as state:
        state.count = 50
        state.email = "test@example.com"
    
    # Try to set invalid count
    with pytest.raises(ValidationError):
        async with ctx.edit_state() as state:
            state.count = 150  # Exceeds max
    
    # Try to set invalid email
    with pytest.raises(ValidationError):
        async with ctx.edit_state() as state:
            state.email = "not-an-email"
    
    # Original valid state preserved
    assert ctx.state.count == 50
    assert ctx.state.email == "test@example.com"


# =============================================================================
# Edge Cases
# =============================================================================


def test_state_store_without_pydantic():
    """Test graceful handling when pydantic not installed."""
    # This test would need to mock the import
    # For now, just verify StateStore requires BaseModel
    
    class NotAModel:
        pass
    
    with pytest.raises(TypeError, match="must be a Pydantic BaseModel"):
        StateStore(NotAModel)  # type: ignore


@pytest.mark.asyncio
async def test_state_persists_across_step_scopes():
    """Test that state persists across step scopes (unlike STEP-scoped data)."""
    ctx = ChainContext("req_1", state_model=CounterState)
    
    async with ctx.step_scope("step1"):
        async with ctx.edit_state() as state:
            state.count = 10
    
    # State should persist after step scope exits
    assert ctx.state.count == 10
    
    async with ctx.step_scope("step2"):
        # State is still accessible
        assert ctx.state.count == 10
        async with ctx.edit_state() as state:
            state.count += 5
    
    assert ctx.state.count == 15


def test_context_repr_with_state():
    """Test that context repr includes state model info."""
    ctx = ChainContext("req_1", state_model=CounterState)
    repr_str = repr(ctx)
    
    assert "req_1" in repr_str
    assert "CounterState" in repr_str


def test_context_repr_without_state():
    """Test that context repr works without state model."""
    ctx = ChainContext("req_1")
    repr_str = repr(ctx)
    
    assert "req_1" in repr_str
    assert "CounterState" not in repr_str


# =============================================================================
# Documentation Tests (Verify Examples Work)
# =============================================================================


@pytest.mark.asyncio
async def test_readme_example():
    """Test the example from README/docs."""
    from pydantic import BaseModel, Field
    
    class PipelineState(BaseModel):
        counter: int = Field(default=0)
        items: list[str] = Field(default_factory=list)
    
    ao = AgentOrchestrator(name="test", isolated=True)
    
    @ao.step(name="process", state_model=PipelineState)
    async def process(ctx: Context[PipelineState]):
        # Type-safe access with IDE autocomplete
        async with ctx.edit_state() as state:
            state.counter += 1
            state.items.append("new_item")
        
        # Read-only access
        count = ctx.state.counter  # Typed!
        return {"count": count}
    
    @ao.chain(name="pipeline")
    class Pipeline:
        steps = ["process"]
    
    # Create context with state model
    ctx = ChainContext("req_1", state_model=PipelineState)
    
    # Execute step manually
    async with ctx.step_scope("process"):
        result = await process(ctx)
    
    assert result["count"] == 1
    assert ctx.state.counter == 1
    assert ctx.state.items == ["new_item"]


@pytest.mark.asyncio
async def test_llamaindex_style_example():
    """Test LlamaIndex Workflows-style state usage."""
    from pydantic import BaseModel, Field
    
    class RunState(BaseModel):
        num_runs: int = Field(default=0)
        errors: list[str] = Field(default_factory=list)
    
    ctx = ChainContext("req_1", state_model=RunState)
    
    # LlamaIndex style: async with ctx.store.edit_state()
    # Our style: async with ctx.edit_state()
    async with ctx.edit_state() as state:
        state.num_runs += 1
        state.errors.append("error1")
    
    assert ctx.state.num_runs == 1
    assert ctx.state.errors == ["error1"]
    
    # Run again
    async with ctx.edit_state() as state:
        state.num_runs += 1
    
    assert ctx.state.num_runs == 2


# =============================================================================
# Performance Tests
# =============================================================================


@pytest.mark.asyncio
async def test_state_performance_many_updates():
    """Test performance with many state updates."""
    import time
    
    ctx = ChainContext("req_1", state_model=CounterState)
    
    start = time.perf_counter()
    
    for i in range(100):
        async with ctx.edit_state() as state:
            state.count = i
    
    duration = time.perf_counter() - start
    
    assert ctx.state.count == 99
    assert duration < 1.0  # Should be fast


@pytest.mark.asyncio
async def test_state_vs_dict_comparison():
    """Compare state model vs dict-based approach."""
    # Dict-based (old way)
    ctx_dict = ChainContext("req_1")
    ctx_dict.set("counter", 0)
    
    # State-based (new way)
    ctx_state = ChainContext("req_2", state_model=CounterState)
    
    # Both should work
    ctx_dict.set("counter", ctx_dict.get("counter", 0) + 1)
    async with ctx_state.edit_state() as state:
        state.count += 1
    
    assert ctx_dict.get("counter") == 1
    assert ctx_state.state.count == 1
