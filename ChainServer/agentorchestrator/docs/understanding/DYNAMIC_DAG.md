# Dynamic DAG Execution

AgentOrchestrator supports dynamic step injection, allowing steps to spawn new steps at runtime. This enables powerful patterns like:

- Adaptive workflows based on intermediate results
- Recursive decomposition of complex tasks
- Conditional branching with dynamic step creation
- Self-modifying pipelines

## Overview

When a step returns a special `__dynamic_steps__` key in its output, the executor will:

1. Register the new steps dynamically
2. Execute them immediately after the current step
3. Make their outputs available to subsequent steps

```
┌─────────────────┐
│   Parent Step   │
│  returns:       │
│  __dynamic_steps__
└────────┬────────┘
         │
    ┌────▼────┐
    │ Register │  Dynamic steps registered
    │ + Execute│  and executed immediately
    └────┬────┘
         │
    ┌────▼────┐
    │  Next   │  Continues with normal flow
    │  Step   │
    └─────────┘
```

## Basic Usage

### Injecting Dynamic Steps

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="dynamic_example")

@ao.step(name="analyze_task")
async def analyze_task(ctx):
    task = ctx.get("task")
    
    # Based on analysis, decide what additional steps are needed
    if "research" in task.lower():
        # Inject a research step dynamically
        return {
            "analysis": "Task requires research",
            "__dynamic_steps__": [
                {
                    "name": "do_research",
                    "handler": research_handler,
                    # NOTE: deps are registered for documentation but IGNORED
                    # at runtime - dynamic steps always execute immediately
                    "produces": ["research_results"],
                },
            ],
        }
    
    return {"analysis": "Simple task, no extra steps needed"}

async def research_handler(ctx):
    """Handler for the dynamically injected step."""
    return {"research_results": "Found relevant information..."}

@ao.step(name="finalize", deps=["analyze_task"])
async def finalize(ctx):
    # Can access results from dynamic steps
    research = ctx.get("research_results")
    return {"final_result": f"Done. Research: {research}"}
```

### Using Existing Steps

You can also reference already-registered steps by name:

```python
@ao.step(name="decision_step")
async def decision_step(ctx):
    score = ctx.get("score", 0)
    
    if score > 80:
        # Use existing high-value processing step
        return {
            "decision": "high_value",
            "__dynamic_steps__": ["premium_processing"],
        }
    else:
        return {
            "decision": "standard",
            "__dynamic_steps__": ["standard_processing"],
        }
```

## Dynamic Step Definition Format

Each dynamic step can be defined as either:

### 1. Dictionary with Handler

```python
{
    "name": "step_name",           # Required: Unique step name
    "handler": async_function,      # Required: Async function to execute
    "deps": ["parent_step"],        # Optional: Registered for documentation only (IGNORED at runtime)
    "produces": ["output_key"],     # Optional: Keys this step produces
}
```

> **Important**: Dynamic steps execute IMMEDIATELY after their parent step completes.
> The `deps` field is stored for documentation/introspection purposes only—it does NOT
> affect execution order. If you need complex dependency orchestration, consider using
> `ctx.set("__dag_needs_rebuild__", True)` to trigger a full DAG rebuild instead.

### 2. String Reference

```python
"existing_step_name"  # Reference to already-registered step
```

## Advanced Patterns

### Recursive Decomposition

A step can recursively spawn more steps based on problem complexity:

```python
@ao.step(name="decompose")
async def decompose(ctx):
    problem = ctx.get("problem")
    depth = ctx.get("decomposition_depth", 0)
    max_depth = ctx.get("max_depth", 3)
    
    if depth >= max_depth or is_simple(problem):
        return {"solution": solve_directly(problem)}
    
    # Decompose into sub-problems
    sub_problems = split_problem(problem)
    
    dynamic_steps = []
    for i, sub in enumerate(sub_problems):
        dynamic_steps.append({
            "name": f"solve_sub_{depth}_{i}",
            "handler": create_solver(sub, depth + 1),
        })
    
    return {
        "decomposed": True,
        "sub_count": len(sub_problems),
        "__dynamic_steps__": dynamic_steps,
    }
```

### Conditional Pipelines

Create entirely different processing paths based on input:

```python
@ao.step(name="route_request")
async def route_request(ctx):
    request_type = ctx.get("request_type")
    
    pipeline_map = {
        "order": ["validate_order", "process_payment", "ship_order"],
        "return": ["validate_return", "process_refund", "schedule_pickup"],
        "inquiry": ["analyze_inquiry", "generate_response"],
    }
    
    steps = pipeline_map.get(request_type, ["handle_unknown"])
    
    return {
        "routed_to": request_type,
        "__dynamic_steps__": steps,
    }
```

### Map-Reduce Pattern

Process items in parallel with dynamically created steps:

```python
@ao.step(name="map_items")
async def map_items(ctx):
    items = ctx.get("items", [])
    
    # Create a processing step for each item
    dynamic_steps = []
    for i, item in enumerate(items):
        async def process_item(ctx, item=item, idx=i):
            result = await process(item)
            ctx.set(f"item_result_{idx}", result)
            return {"processed": True}
        
        dynamic_steps.append({
            "name": f"process_item_{i}",
            "handler": process_item,
            "produces": [f"item_result_{i}"],
        })
    
    return {
        "mapped_count": len(items),
        "__dynamic_steps__": dynamic_steps,
    }

@ao.step(name="reduce_results", deps=["map_items"])
async def reduce_results(ctx):
    # Collect all item results
    results = []
    for key in ctx.keys():
        if key.startswith("item_result_"):
            results.append(ctx.get(key))
    
    return {"combined": aggregate(results)}
```

## Events

When dynamic steps are injected, the executor emits a `DynamicStepInjected` event:

```python
from agentorchestrator.core.event_bus import get_event_bus

bus = get_event_bus()

@ao.event_handler("DynamicStepInjected")
async def on_dynamic_steps(ctx, event):
    print(f"Dynamic steps added: {event.payload['injected_steps']}")
    print(f"By parent step: {event.payload['parent_step']}")
```

## Best Practices

### 1. Keep Dynamic Steps Focused

```python
# Good: Single responsibility
return {
    "__dynamic_steps__": [
        {"name": "fetch_data", "handler": fetch_handler},
        {"name": "transform_data", "handler": transform_handler},
    ]
}

# Avoid: Monolithic dynamic handlers
return {
    "__dynamic_steps__": [
        {"name": "do_everything", "handler": giant_handler},
    ]
}
```

### 2. Use Meaningful Names

```python
# Good: Descriptive names
return {
    "__dynamic_steps__": [
        {"name": f"process_{item_type}_{item_id}", "handler": handler},
    ]
}

# Avoid: Generic names
return {
    "__dynamic_steps__": [
        {"name": f"step_{i}", "handler": handler},
    ]
}
```

### 3. Handle Errors Gracefully

```python
@ao.step(name="with_error_handling")
async def with_error_handling(ctx):
    try:
        # Attempt dynamic step creation
        steps = determine_steps(ctx)
        return {"__dynamic_steps__": steps}
    except Exception as e:
        # Fallback to known-good steps
        logger.warning(f"Dynamic step creation failed: {e}")
        return {"__dynamic_steps__": ["fallback_step"]}
```

### 4. Avoid Infinite Recursion

```python
@ao.step(name="recursive_with_limit")
async def recursive_with_limit(ctx):
    depth = ctx.get("_recursion_depth", 0)
    max_depth = 10
    
    if depth >= max_depth:
        logger.warning("Max recursion depth reached")
        return {"terminated": True}
    
    # Track depth in context
    ctx.set("_recursion_depth", depth + 1)
    
    return {
        "depth": depth,
        "__dynamic_steps__": [...],
    }
```

## Limitations

1. **Immediate Execution**: Dynamic steps execute IMMEDIATELY after their parent step completes. They bypass the normal DAG scheduling—any `deps` declared on dynamic steps are registered for documentation but **IGNORED at runtime**.

2. **No Retroactive Dependencies**: Dynamic steps can only access data from steps that have already executed. They cannot wait for parallel branches to complete.

3. **Performance**: Heavy use of dynamic steps can impact performance due to registration overhead.

4. **Debugging**: Dynamic DAGs are harder to visualize and debug. Use events and logging liberally.

5. **Double-Execution Protection**: If you inject a step by name that has already executed, it will be skipped (the executor checks `ctx.get_result()` to prevent re-execution).

### Alternative: Full DAG Rebuild

If you need dynamic steps that respect complex dependencies, use the DAG rebuild mechanism instead:

```python
@ao.step(name="inject_with_deps")
async def inject_with_deps(ctx):
    # Register the new step
    ao.step_registry.register_step(
        name="new_step",
        handler=new_handler,
        dependencies=["step_a", "step_b"],  # These WILL be honored
    )

    # Add to chain and trigger rebuild
    chain_spec = ao.chain_registry.get_spec("my_chain")
    chain_spec.steps.append("new_step")

    # Signal executor to rebuild DAG
    ctx.set("__dag_needs_rebuild__", True)

    return {"injected": "new_step"}
```

With `__dag_needs_rebuild__`, the executor rebuilds the DAG and processes steps according to the normal topological order, respecting all declared dependencies.

## See Also

- [Event-Driven Workflows](./EVENT_WORKFLOWS.md) - For event-based dynamic execution
- [Steps and Chains](./steps_and_chains.md) - Core step concepts
- [Examples: Deep Research Agent](../examples/deep_research_agent.py) - Dynamic decomposition example
