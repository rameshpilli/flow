# Getting Started Examples

Start here if you're new to AgentOrchestrator.

## Examples

### 1. Hello World

The simplest possible chain - just one step.

```bash
python hello_world.py
```

**What you'll learn:**
- Creating an AgentOrchestrator instance
- Defining a step with `@ao.step()`
- Defining a chain with `@ao.chain()`
- Running a chain with `ao.launch()`

### 2. Simple Chain

A multi-step pipeline with dependencies.

```bash
python simple_chain.py
```

**What you'll learn:**
- Step dependencies with `deps=["step_name"]`
- Passing data between steps via context
- Chain execution order

### 3. Parallel Steps

Steps without dependencies run in parallel.

```bash
python parallel_steps.py
```

**What you'll learn:**
- Parallel execution optimization
- Multiple steps feeding into one
- Performance benefits of DAG execution

### 4. AI Workflow DAG

A tiny AI workflow with parallel research branches.

```bash
python ai_workflow_dag.py
```

**What you'll learn:**
- DAG-style AI workflows in a few steps
- Parallel branches with shared dependencies
- Clear data flow via context

### 5. Conditional Workflow

DAG workflows with conditional execution paths and routing.

```bash
python conditional_workflow.py
python conditional_workflow.py --query "simple question"
python conditional_workflow.py --query "complex analysis needed"
```

**What you'll learn:**
- Conditional step execution based on context
- Dynamic routing between workflow branches
- Early termination patterns

### 6. Error Handling

Production-ready error handling patterns.

```bash
python error_handling.py          # Run successfully
python error_handling.py --fail   # Simulate failure
```

**What you'll learn:**
- Try-except around `ao.launch()`
- Checking `result["success"]` status
- Accessing error details from `result["error"]`
- Step-level error handling
- Graceful degradation patterns

### 7. Input Validation

Pydantic-based input validation at chain and step level.

```bash
python input_validation.py                    # Valid input
python input_validation.py --invalid          # Trigger validation error
python input_validation.py --step-validation  # Step-level validation
```

**What you'll learn:**
- Chain-level `input_model` for fail-fast validation
- Step-level `input_model` for per-step validation
- Pydantic validators for custom rules (date format, sanitization)
- Catching `ContractValidationError`

**Key patterns:**

```python
from pydantic import BaseModel, Field

class MeetingRequest(BaseModel):
    company: str = Field(..., min_length=2)
    meeting_date: str

# Chain-level validation (recommended for API inputs)
@ao.chain(input_model=MeetingRequest, input_key="request")
class MeetingChain:
    steps = ["prepare", "process"]

# Step-level validation (first step validated at launch)
@ao.step(input_model=MeetingRequest, input_key="request")
async def prepare(ctx): ...
```

### 8. Dataflow Dependencies

Automatic dependency resolution using produces/consumes declarations.

```bash
python dataflow_example.py
```

**What you'll learn:**
- Using `@produces` and `@consumes` decorators
- Enabling `dataflow=True` on a chain
- Automatic dependency resolution based on data flow
- Validating dataflow with `ao.check()`

**Key patterns:**

```python
from agentorchestrator import AgentOrchestrator, produces, consumes

ao = AgentOrchestrator(name="dataflow_example")

@produces("company_data")
@ao.step(name="fetch_company")
async def fetch_company(ctx):
    ctx.set("company_data", {"ticker": "AAPL"})
    return {"fetched": True}

# This step automatically depends on fetch_company
@consumes("company_data")
@produces("analysis")
@ao.step(name="analyze")
async def analyze(ctx):
    data = ctx.get("company_data")
    return {"analysis": f"Analyzed {data['ticker']}"}

# Enable dataflow resolution
@ao.chain(name="research_chain", dataflow=True)
class ResearchChain:
    steps = ["fetch_company", "analyze"]
```

### 9. Self-Critique / Reflection

Agent self-critique with quality scoring and automatic revision.

```bash
python reflection_example.py
python reflection_example.py --low-quality  # Trigger revision cycle
```

**What you'll learn:**
- Using `ReflectionMiddleware` for automatic quality review
- Using `@reflect` decorator on specific steps
- Quality scoring and revision cycles
- Accessing reflection trace results

**Key patterns:**

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware import (
    ReflectionMiddleware,
    ReflectionConfig,
    reflect,
)

ao = AgentOrchestrator(name="reflection_example")

# Option 1: Global middleware configuration
ao.use(ReflectionMiddleware(
    config=ReflectionConfig(
        quality_threshold=0.8,  # Score needed to pass (0.0-1.0)
        max_revisions=2,        # Max revision attempts
    ),
    llm_client=llm_client,
))

# Option 2: Per-step decorator
@reflect(quality_threshold=0.85, max_revisions=1)
@ao.step(name="generate_report")
async def generate_report(ctx):
    return {"report": "..."}

# Access reflection trace after execution
traces = result["context"]["data"].get("_reflection_trace", {})
print(f"Quality Score: {traces['generate_report']['quality_score']}")
```

## Next Steps

After completing these examples:

1. [Memory examples](../memory/) - Add conversation storage
2. [RAG examples](../rag/) - Retrieval-augmented generation
3. [Agent examples](../agents/) - Multi-agent orchestration
