# Create New Step

Create a new AgentOrchestrator step for an existing chain.

## Usage
```
/new-step <step_name> <chain_name> <description>
```

Example: `/new-step validation cmpt "Validates financial metrics and analysis"`

---

## Step Pattern

Steps are decorated functions that:
1. Read data from context (`ctx.get()`)
2. Execute business logic (usually via a Service)
3. Write results to context (`ctx.set()`)
4. Return status dict for logging

```python
@ao.step(
    name="step_name",
    description="What this step does",
    deps=["previous_step"],      # Steps this depends on
    produces=["output_key"],     # Keys this step writes to context
    timeout_ms=30000,            # Step timeout (default: 30s)
)
async def step_function(ctx) -> dict[str, Any]:
    # Read from context
    input_data = ctx.get("input_key")

    # Execute service
    service = MyService()
    output = await service.execute(input_data)

    # Write to context
    ctx.set("output_key", output)

    # Return status for logging
    return {"step": "step_name", "success": True}
```

---

## Step Template

```python
# Add to your chain.py file

@ao.step(
    name="{step_name}",
    description="{step_description}",
    deps=[{dependencies}],  # e.g., ["context_builder", "content_prioritization"]
    produces=["{output_key}"],
    timeout_ms={timeout},  # e.g., 30000 (30 seconds)
)
async def {step_name}_step(ctx) -> dict[str, Any]:
    """
    {Step Description}

    Input (from ctx):
        {input_key}: {InputType} from {previous_step}

    Output (to ctx):
        {output_key}: {OutputType}
    """
    # ───────────────────────────────────────────────────────────────────────
    # GET INPUT FROM CONTEXT
    # ───────────────────────────────────────────────────────────────────────

    input_data = ctx.get("{input_key}")

    if input_data is None:
        logger.error("[{step_name}] Missing required input: {input_key}")
        return {
            "step": "{step_name}",
            "success": False,
            "error": "Missing required input",
        }

    logger.info(f"[{step_name}] Processing...")

    # ───────────────────────────────────────────────────────────────────────
    # EXECUTE SERVICE
    # ───────────────────────────────────────────────────────────────────────

    try:
        output = await {service_name}_service.execute(input_data)
    except Exception as e:
        logger.error(f"[{step_name}] Service failed: {e}")
        return {
            "step": "{step_name}",
            "success": False,
            "error": str(e),
        }

    # ───────────────────────────────────────────────────────────────────────
    # STORE RESULTS IN CONTEXT
    # ───────────────────────────────────────────────────────────────────────

    ctx.set("{output_key}", output)

    # ───────────────────────────────────────────────────────────────────────
    # RETURN STATUS
    # ───────────────────────────────────────────────────────────────────────

    return {
        "step": "{step_name}",
        "success": len(output.errors) == 0,
        "result_count": len(output.results) if hasattr(output, 'results') else None,
        "timing_ms": output.timing_ms.get("total") if output.timing_ms else None,
    }
```

---

## Step Types

### 1. Context Builder Step (First Step)
```python
@ao.step(
    name="context_builder",
    description="Extract context from the incoming request",
    produces=["context_output", "company_name", "ticker"],
)
async def context_builder_step(ctx) -> dict[str, Any]:
    """Stage 1: Build context from the incoming request."""
    # Get raw request from initial context
    request_data = ctx.get("request", {})

    # Convert dict to typed model if needed
    if isinstance(request_data, dict):
        request = ChainRequest(**request_data)
    else:
        request = request_data

    logger.info(f"[Step 1] Context Builder: {request.primary_input}")

    # Execute service
    output = await context_builder_service.execute(request)

    # Store multiple values in context
    ctx.set("context_output", output)
    ctx.set("company_name", output.company_name)
    ctx.set("ticker", output.ticker)

    return {
        "step": "context_builder",
        "company": output.company_name,
        "ticker": output.ticker,
    }
```

### 2. Processing Step (Middle Step)
```python
@ao.step(
    name="content_prioritization",
    description="Prioritize data sources and generate subqueries",
    deps=["context_builder"],  # Depends on previous step
    produces=["prioritization_output"],
)
async def content_prioritization_step(ctx) -> dict[str, Any]:
    """Stage 2: Prioritize content sources and generate subqueries."""
    # Get output from previous step
    context_output = ctx.get("context_output")

    logger.info(f"[Step 2] Content Prioritization: {ctx.get('company_name')}")

    output = await content_prioritization_service.execute(context_output)

    ctx.set("prioritization_output", output)

    return {
        "step": "content_prioritization",
        "sources_count": len(output.prioritized_sources),
        "subqueries_count": len(output.subqueries),
    }
```

### 3. Agent Execution Step
```python
@ao.step(
    name="response_builder",
    description="Execute agents and build final response",
    deps=["content_prioritization"],
    produces=["response_output", "final_response"],
    timeout_ms=120000,  # Longer timeout for agent calls
)
async def response_builder_step(ctx) -> dict[str, Any]:
    """Stage 3: Execute agents and build response."""
    context_output = ctx.get("context_output")
    prioritization_output = ctx.get("prioritization_output")

    logger.info(f"[Step 3] Response Builder: {ctx.get('company_name')}")

    output = await response_builder_service.execute(
        context_output,
        prioritization_output,
    )

    # Build final response model
    final_response = ChainResponse(
        result=output.final_output,
        agent_results={k: v.model_dump() for k, v in output.agent_results.items()},
        timing_ms=output.timing_ms,
    )

    ctx.set("response_output", output)
    ctx.set("final_response", final_response)

    return {
        "step": "response_builder",
        "agents_succeeded": output.agents_succeeded,
        "agents_failed": output.agents_failed,
    }
```

### 4. Validation Step
```python
@ao.step(
    name="validation",
    description="Validate extracted data and analysis",
    deps=["response_builder"],
    produces=["validation_output"],
    timeout_ms=10000,  # Quick validation
)
async def validation_step(ctx) -> dict[str, Any]:
    """Stage 4: Validate extracted metrics and analysis."""
    response_output = ctx.get("response_output")
    final_response = ctx.get("final_response")

    logger.info("[Step 4] Validation")

    # Perform validation
    validation_results = await validation_service.validate(
        response_output.financial_metrics,
        response_output.strategic_analysis,
    )

    # Update final response with validation
    final_response.validation_results = validation_results

    ctx.set("validation_output", validation_results)
    ctx.set("final_response", final_response)  # Update

    return {
        "step": "validation",
        "is_valid": validation_results.get("is_valid", False),
        "issues_count": len(validation_results.get("issues", [])),
    }
```

---

## Step Decorator Options

```python
@ao.step(
    name="step_name",              # Required: Unique step identifier
    description="...",             # Required: Human-readable description
    deps=["step1", "step2"],       # Optional: Dependencies (runs after these)
    produces=["key1", "key2"],     # Optional: Context keys this step writes
    timeout_ms=30000,              # Optional: Step timeout (default: 30000)
    retries=0,                     # Optional: Retry count on failure
    retry_delay_ms=1000,           # Optional: Delay between retries
)
```

---

## Context API

```python
# Reading from context
value = ctx.get("key")                    # Get value, None if missing
value = ctx.get("key", default="value")   # Get with default

# Writing to context
ctx.set("key", value)                     # Set value

# Check if key exists
if ctx.has("key"):
    ...

# Get all context data
data = ctx.data

# Get run metadata
run_id = ctx.run_id
chain_name = ctx.chain_name
```

---

## Adding Step to Chain

After creating your step function, add it to the chain class:

```python
@ao.chain(
    name="{chain_name}_chain",
    description="{Chain description}",
)
class {ChainName}Chain:
    """Chain with the new step included."""

    steps = [
        "context_builder",
        "content_prioritization",
        "response_builder",
        "{step_name}",  # Add new step here
    ]
```

---

## Step Dependencies (DAG)

Steps form a Directed Acyclic Graph (DAG) based on `deps`:

```
No deps:        deps=["a"]:      deps=["a", "b"]:
    ┌─┐             ┌─┐              ┌─┐   ┌─┐
    │a│             │a│              │a│   │b│
    └─┘             └┬┘              └┬┘   └┬┘
                     │                └──┬──┘
                    ┌▼┐               ┌──▼──┐
                    │b│               │  c  │
                    └─┘               └─────┘
```

The executor automatically:
1. Builds the DAG from `deps`
2. Runs steps in parallel when possible
3. Waits for dependencies before executing a step

---

## Best Practices

### 1. Keep Steps Focused
```python
# Good: Single responsibility
@ao.step(name="extract_metrics")
async def extract_metrics_step(ctx): ...

@ao.step(name="validate_metrics", deps=["extract_metrics"])
async def validate_metrics_step(ctx): ...

# Bad: Too much in one step
@ao.step(name="extract_and_validate_metrics")
async def extract_and_validate_metrics_step(ctx): ...
```

### 2. Type Your Inputs/Outputs
```python
# Good: Explicit types
context_output: ContextBuilderOutput = ctx.get("context_output")
output: ResponseBuilderOutput = await service.execute(context_output)

# Bad: Untyped
context_output = ctx.get("context_output")
output = await service.execute(context_output)
```

### 3. Handle Missing Dependencies
```python
# Good: Check for required input
input_data = ctx.get("required_input")
if input_data is None:
    return {"step": "my_step", "success": False, "error": "Missing input"}

# Bad: Assume input exists
input_data = ctx.get("required_input")
output = await service.execute(input_data)  # May fail with None
```

### 4. Return Useful Status
```python
# Good: Informative return
return {
    "step": "response_builder",
    "agents_succeeded": 3,
    "agents_failed": 1,
    "has_metrics": output.financial_metrics is not None,
}

# Bad: Minimal return
return {"success": True}
```

---

## Reference Files

- **Step Examples**: [cmpt/chain.py:151](cmpt/chain.py#L151) (context_builder), [line 203](cmpt/chain.py#L203) (content_prioritization), [line 248](cmpt/chain.py#L248) (response_builder)
- **Context API**: [agentorchestrator/core/context.py](agentorchestrator/core/context.py)
- **DAG Executor**: [agentorchestrator/core/dag.py](agentorchestrator/core/dag.py)
