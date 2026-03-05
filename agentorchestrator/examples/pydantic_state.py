"""
Type-Safe State Management with Pydantic Models
================================================

This example demonstrates how to use Pydantic models for type-safe state
management in AgentOrchestrator chains. This provides IDE autocomplete,
type checking, and validation for your chain state.

Key Features:
- Type-safe state access with IDE autocomplete
- Automatic validation via Pydantic
- Atomic state updates via context manager
- Thread-safe concurrent access
- Clean separation of state from context data

Inspired by LlamaIndex Workflows' state management pattern.

Run:
    python -m agentorchestrator.examples.pydantic_state
"""

import asyncio
from pydantic import BaseModel, Field

from agentorchestrator import AgentOrchestrator, Context


# =============================================================================
# Example 1: Simple Counter Pipeline
# =============================================================================


class CounterState(BaseModel):
    """Simple state model with a counter."""
    count: int = Field(default=0, description="Current count")
    name: str = Field(default="counter", description="Counter name")


async def example_1_simple_counter():
    """Example 1: Basic counter with type-safe state."""
    print("\n" + "=" * 70)
    print("Example 1: Simple Counter Pipeline")
    print("=" * 70)
    
    ao = AgentOrchestrator(name="counter_example", isolated=True)
    
    @ao.step(name="increment", state_model=CounterState)
    async def increment(ctx: Context[CounterState]):
        """Increment the counter."""
        async with ctx.edit_state() as state:
            state.count += 1  # Type-safe! IDE autocomplete works!
            print(f"  Incremented: {state.name} = {state.count}")
        
        return {"count": ctx.state.count}
    
    @ao.step(name="double", deps=["increment"], state_model=CounterState)
    async def double(ctx: Context[CounterState]):
        """Double the counter."""
        async with ctx.edit_state() as state:
            state.count *= 2
            print(f"  Doubled: {state.name} = {state.count}")
        
        return {"count": ctx.state.count}
    
    @ao.chain(name="counter_chain")
    class CounterChain:
        steps = ["increment", "double"]
    
    # Create context with state model
    from agentorchestrator.core.context import ChainContext
    ctx = ChainContext("req_1", state_model=CounterState)
    
    # Initialize state
    async with ctx.edit_state() as state:
        state.name = "my_counter"
    
    print(f"\nInitial state: count={ctx.state.count}, name={ctx.state.name}")
    print("\nExecuting steps:")
    
    # Execute steps manually for demo
    async with ctx.step_scope("increment"):
        await increment(ctx)
    
    async with ctx.step_scope("double"):
        await double(ctx)
    
    print(f"\nFinal state: count={ctx.state.count}, name={ctx.state.name}")
    print("✓ Type-safe state management working!")


# =============================================================================
# Example 2: Data Processing Pipeline
# =============================================================================


class PipelineState(BaseModel):
    """State for a data processing pipeline."""
    items_processed: int = Field(default=0)
    items: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    completed: bool = Field(default=False)


async def example_2_data_pipeline():
    """Example 2: Data processing pipeline with rich state."""
    print("\n" + "=" * 70)
    print("Example 2: Data Processing Pipeline")
    print("=" * 70)
    
    ao = AgentOrchestrator(name="pipeline_example", isolated=True)
    
    @ao.step(name="fetch_data", state_model=PipelineState)
    async def fetch_data(ctx: Context[PipelineState]):
        """Fetch data items."""
        # Simulate fetching data
        raw_items = ["item1", "item2", "item3", "item4", "item5"]
        
        async with ctx.edit_state() as state:
            state.items = raw_items
            print(f"  Fetched {len(raw_items)} items")
        
        return {"fetched": len(raw_items)}
    
    @ao.step(name="process_items", deps=["fetch_data"], state_model=PipelineState)
    async def process_items(ctx: Context[PipelineState]):
        """Process each item."""
        items = ctx.state.items.copy()  # Read-only access
        
        for item in items:
            try:
                # Simulate processing
                if item == "item3":
                    raise ValueError(f"Failed to process {item}")
                
                async with ctx.edit_state() as state:
                    state.items_processed += 1
                    print(f"  Processed: {item}")
            
            except ValueError as e:
                async with ctx.edit_state() as state:
                    state.errors.append(str(e))
                    print(f"  Error: {e}")
        
        return {"processed": ctx.state.items_processed}
    
    @ao.step(name="finalize", deps=["process_items"], state_model=PipelineState)
    async def finalize(ctx: Context[PipelineState]):
        """Finalize the pipeline."""
        async with ctx.edit_state() as state:
            state.completed = True
            print(f"  Finalized: {state.items_processed} items, {len(state.errors)} errors")
        
        return {
            "success": ctx.state.items_processed > 0,
            "processed": ctx.state.items_processed,
            "errors": len(ctx.state.errors),
        }
    
    @ao.chain(name="pipeline")
    class DataPipeline:
        steps = ["fetch_data", "process_items", "finalize"]
    
    # Create context
    from agentorchestrator.core.context import ChainContext
    ctx = ChainContext("req_2", state_model=PipelineState)
    
    print("\nExecuting pipeline:")
    
    # Execute steps
    async with ctx.step_scope("fetch_data"):
        await fetch_data(ctx)
    
    async with ctx.step_scope("process_items"):
        await process_items(ctx)
    
    async with ctx.step_scope("finalize"):
        result = await finalize(ctx)
    
    print(f"\nFinal state:")
    print(f"  Items processed: {ctx.state.items_processed}")
    print(f"  Errors: {ctx.state.errors}")
    print(f"  Completed: {ctx.state.completed}")
    print("✓ Pipeline completed successfully!")


# =============================================================================
# Example 3: Validated State with Constraints
# =============================================================================


class ValidatedState(BaseModel):
    """State with validation constraints."""
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage (0-100)")
    email: str = Field(default="user@example.com", pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$", description="Valid email")
    retries: int = Field(default=0, ge=0, le=3, description="Retry count (max 3)")


async def example_3_validated_state():
    """Example 3: State with Pydantic validation."""
    print("\n" + "=" * 70)
    print("Example 3: Validated State with Constraints")
    print("=" * 70)
    
    from agentorchestrator.core.context import ChainContext
    from pydantic import ValidationError
    
    ctx = ChainContext("req_3", state_model=ValidatedState)
    
    # Initialize with valid values
    async with ctx.edit_state() as state:
        state.progress = 0
        state.email = "user@example.com"
        state.retries = 0
    
    print(f"\nInitial state: progress={ctx.state.progress}, email={ctx.state.email}")
    
    # Valid update
    print("\n1. Valid update (progress=50):")
    async with ctx.edit_state() as state:
        state.progress = 50
    print(f"   ✓ Progress updated to {ctx.state.progress}")
    
    # Invalid update - exceeds max
    print("\n2. Invalid update (progress=150):")
    try:
        async with ctx.edit_state() as state:
            state.progress = 150  # Exceeds max of 100
    except ValidationError as e:
        print(f"   ✗ Validation error: {e.errors()[0]['msg']}")
        print(f"   ✓ State unchanged: progress={ctx.state.progress}")
    
    # Invalid email
    print("\n3. Invalid email:")
    try:
        async with ctx.edit_state() as state:
            state.email = "not-an-email"
    except ValidationError as e:
        print(f"   ✗ Validation error: {e.errors()[0]['msg']}")
        print(f"   ✓ State unchanged: email={ctx.state.email}")
    
    print("\n✓ Validation prevents invalid state!")


# =============================================================================
# Example 4: Concurrent State Updates
# =============================================================================


class ConcurrentState(BaseModel):
    """State for concurrent operations."""
    counter: int = Field(default=0)
    items: list[str] = Field(default_factory=list)


async def example_4_concurrent_updates():
    """Example 4: Thread-safe concurrent state updates."""
    print("\n" + "=" * 70)
    print("Example 4: Concurrent State Updates")
    print("=" * 70)
    
    from agentorchestrator.core.context import ChainContext
    
    ctx = ChainContext("req_4", state_model=ConcurrentState)
    
    async def worker(worker_id: int):
        """Simulate concurrent worker."""
        async with ctx.edit_state() as state:
            state.counter += 1
            state.items.append(f"worker_{worker_id}")
            await asyncio.sleep(0.01)  # Simulate work
    
    print("\nRunning 10 concurrent workers...")
    
    # Run 10 workers concurrently
    await asyncio.gather(*[worker(i) for i in range(10)])
    
    print(f"\nFinal state:")
    print(f"  Counter: {ctx.state.counter}")
    print(f"  Items: {len(ctx.state.items)}")
    print(f"  All workers: {sorted(ctx.state.items)}")
    
    # Verify no race conditions
    assert ctx.state.counter == 10, "Race condition detected!"
    assert len(ctx.state.items) == 10, "Lost updates detected!"
    
    print("\n✓ No race conditions - all updates atomic!")


# =============================================================================
# Example 5: State vs Context Data
# =============================================================================


async def example_5_state_vs_context():
    """Example 5: When to use state vs context data."""
    print("\n" + "=" * 70)
    print("Example 5: State vs Context Data")
    print("=" * 70)
    
    from agentorchestrator.core.context import ChainContext, ContextScope
    
    class WorkflowState(BaseModel):
        """Typed state for workflow progress."""
        stage: str = Field(default="init")
        progress: int = Field(default=0)
    
    ctx = ChainContext(
        "req_5",
        initial_data={
            "user_query": "What is the revenue?",  # Input data
            "company": "Apple Inc",  # Extracted data
        },
        state_model=WorkflowState,
    )
    
    print("\n1. Context Data (untyped, flexible):")
    print(f"   user_query: {ctx.get('user_query')}")
    print(f"   company: {ctx.get('company')}")
    
    print("\n2. State (typed, validated):")
    async with ctx.edit_state() as state:
        state.stage = "processing"
        state.progress = 50
    print(f"   stage: {ctx.state.stage}")
    print(f"   progress: {ctx.state.progress}")
    
    print("\n3. Step-scoped data (temporary):")
    async with ctx.step_scope("process"):
        ctx.set("temp_result", {"data": [1, 2, 3]}, scope=ContextScope.STEP)
        print(f"   temp_result: {ctx.get('temp_result')}")
    
    print(f"   temp_result after step: {ctx.get('temp_result')}")  # None
    
    print("\nGuidelines:")
    print("  - Use STATE for: workflow progress, counters, flags, typed data")
    print("  - Use CONTEXT for: input data, extracted entities, step outputs")
    print("  - Use STEP scope for: temporary data, intermediate results")
    print("\n✓ Choose the right storage for your needs!")


# =============================================================================
# Main
# =============================================================================


async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("PYDANTIC STATE MANAGEMENT EXAMPLES")
    print("=" * 70)
    
    await example_1_simple_counter()
    await example_2_data_pipeline()
    await example_3_validated_state()
    await example_4_concurrent_updates()
    await example_5_state_vs_context()
    
    print("\n" + "=" * 70)
    print("ALL EXAMPLES COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("  1. Use Context[StateModel] for type hints")
    print("  2. Use ctx.edit_state() for atomic updates")
    print("  3. Use ctx.state for read-only access")
    print("  4. Pydantic validates all state changes")
    print("  5. State updates are thread-safe")
    print("\nFor more info, see:")
    print("  - agentorchestrator/core/state.py")
    print("  - agentorchestrator/docs/CONTEXT_MANAGEMENT.md")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
