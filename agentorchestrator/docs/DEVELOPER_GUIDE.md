# Developer Guide: Building AI-Style DAG Workflows

This guide helps developers quickly adopt AgentOrchestrator and build production-ready AI workflows.

## Quick Discovery

When you're exploring the framework, use these interactive methods:

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")

# Interactive help - shows all methods categorized
ao.help()

# Topic-specific help
ao.help("decorators")      # @ao.step, @ao.chain, @ao.agent
ao.help("execution")       # launch(), run_step(), resume()
ao.help("middleware")      # use(), list_middleware(), metrics
ao.help("patterns")        # Common AI workflow patterns
ao.help("summarization")   # Large response handling
ao.help("multi-agent")     # Multi-agent patterns

# Discover what's registered
ao.discover()              # All categories
ao.discover("middleware")  # Just middleware

# Explain execution plan
ao.explain("my_chain")     # Show execution order

# Validate everything
ao.check()                 # Validate all definitions
```

## Using `dir()` and `help()`

Python's built-in introspection works well with AgentOrchestrator:

```python
# See all methods on AgentOrchestrator
dir(ao)

# Get detailed help on any method
help(ao.launch)
help(ao.step)
help(ao.use)

# See method signature and docstring
ao.launch?  # In Jupyter/IPython
```

## Core Concepts in 5 Minutes

### 1. Steps - Processing Units

```python
@ao.step(name="fetch_data")
async def fetch_data(ctx):
    """Fetch data from an API."""
    query = ctx.get("query")  # Read from context
    data = await api.fetch(query)
    ctx.set("data", data)  # Write to context
    return {"fetched": len(data)}  # Return for logging
```

### 2. Chains - Orchestrated Workflows

```python
@ao.chain(name="research_pipeline")
class ResearchPipeline:
    steps = ["fetch_data", "analyze", "summarize"]
```

### 3. Dependencies - Execution Order

```python
# Explicit dependencies
@ao.step(name="analyze", deps=["fetch_data"])
async def analyze(ctx): ...

# Or dataflow-based (automatic)
from agentorchestrator import produces, consumes

@produces("raw_data")
@ao.step(name="fetch")
async def fetch(ctx):
    ctx.set("raw_data", data)

@consumes("raw_data")
@ao.step(name="analyze")
async def analyze(ctx):
    data = ctx.get("raw_data")
```

### 4. Execution

```python
# Async (recommended)
result = await ao.launch("research_pipeline", {"query": "AI trends"})

# Sync (for scripts)
result = ao.launch_sync("research_pipeline", {"query": "AI trends"})

# Access results
if result["success"]:
    final_output = result["results"][-1]["output"]
    context_data = result["context"]
```

## Building Your First AI Workflow

### Step 1: Create Orchestrator

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_ai_app")
```

### Step 2: Define Steps

```python
@ao.step(name="plan")
async def plan(ctx):
    """Create a research plan from the query."""
    query = ctx.get("query")
    plan = await llm.generate(f"Create a research plan for: {query}")
    ctx.set("plan", plan)
    return {"plan_created": True}

@ao.step(name="research", deps=["plan"])
async def research(ctx):
    """Execute research based on the plan."""
    plan = ctx.get("plan")
    # Parallel data fetching
    results = await asyncio.gather(
        fetch_news(plan),
        fetch_papers(plan),
        fetch_data(plan),
    )
    ctx.set("research_data", results)
    return {"sources": len(results)}

@ao.step(name="synthesize", deps=["research"])
async def synthesize(ctx):
    """Synthesize findings into a report."""
    data = ctx.get("research_data")
    report = await llm.generate(f"Synthesize: {data}")
    ctx.set("report", report)
    return {"report_length": len(report)}
```

### Step 3: Define Chain

```python
@ao.chain(name="deep_research")
class DeepResearchChain:
    steps = ["plan", "research", "synthesize"]
```

### Step 4: Add Middleware (Production Ready)

```python
from agentorchestrator.middleware import (
    LoggerMiddleware,
    TokenManagerMiddleware,
    TokenBudget,
    SummarizerMiddleware,
    SummarizationStrategy,
)

# Logging
ao.use(LoggerMiddleware(level="INFO"))

# Token budget (prevents context overflow)
budget = TokenBudget(
    context_window=128000,
    reserved_output=8000,
    reserved_system=3000,
    reserved_history=15000,
)
ao.use(TokenManagerMiddleware(budget=budget, auto_summarize=True))

# Summarization for large responses
ao.use(SummarizerMiddleware(
    summarizer=my_summarizer,
    strategy=SummarizationStrategy.TREE,
    applies_to=["research"],
))
```

### Step 5: Run

```python
# Validate first
validation = ao.check()
if not validation.valid:
    print(f"Warnings: {validation.warnings}")

# Visualize
print(ao.graph("deep_research"))

# Execute
result = await ao.launch("deep_research", {"query": "AI in healthcare"})
print(result["context"]["report"])
```

## Pattern Reference

### Pattern 1: Parallel Data Fetching

```
        ┌─────────┐
        │  plan   │
        └────┬────┘
             │
     ┌───────┼───────┐
     │       │       │
     ▼       ▼       ▼
┌────────┐ ┌────┐ ┌────────┐
│  news  │ │ sec│ │ social │  ← Run in parallel
└────┬───┘ └──┬─┘ └───┬────┘
     │        │       │
     └────────┼───────┘
              │
              ▼
        ┌───────────┐
        │ synthesize│
        └───────────┘
```

```python
@ao.step(name="plan")
async def plan(ctx): ...

@ao.step(name="fetch_news", deps=["plan"])
async def fetch_news(ctx): ...

@ao.step(name="fetch_sec", deps=["plan"])
async def fetch_sec(ctx): ...

@ao.step(name="fetch_social", deps=["plan"])
async def fetch_social(ctx): ...

@ao.step(name="synthesize", deps=["fetch_news", "fetch_sec", "fetch_social"])
async def synthesize(ctx): ...
```

### Pattern 2: Type-Safe State

```python
from pydantic import BaseModel, Field

class ResearchState(BaseModel):
    query: str = ""
    sources_fetched: int = 0
    findings: list[str] = Field(default_factory=list)
    confidence: float = 0.0

@ao.step(name="research", state_model=ResearchState)
async def research(ctx):
    async with ctx.edit_state() as state:
        state.sources_fetched += 1
        state.findings.append("New finding")
        state.confidence = 0.85
```

### Pattern 3: Dataflow Dependencies

```python
from agentorchestrator import produces, consumes

@produces("company_info", "ticker")
@ao.step(name="extract_company")
async def extract_company(ctx):
    ctx.set("company_info", {...})
    ctx.set("ticker", "AAPL")

@consumes("ticker")
@produces("financials")
@ao.step(name="fetch_financials")
async def fetch_financials(ctx):
    ticker = ctx.get("ticker")
    ctx.set("financials", await get_financials(ticker))

@consumes("company_info", "financials")
@ao.step(name="generate_report")
async def generate_report(ctx):
    # Dependencies automatically resolved!
    company = ctx.get("company_info")
    financials = ctx.get("financials")

@ao.chain(name="research_chain", dataflow=True)
class ResearchChain:
    steps = ["extract_company", "fetch_financials", "generate_report"]
```

## Summarization Strategy Guide

| Strategy | Use When | Token Range |
|----------|----------|-------------|
| **STUFF** | Small documents | < 4K tokens |
| **MAP_REDUCE** | Medium docs, parallelizable | 10K-50K tokens |
| **REFINE** | Need high coherence | 10K-50K tokens |
| **TREE** | Massive documents | 50K+ tokens |

```python
# Choose based on expected response size
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    strategy=SummarizationStrategy.TREE,  # For 50K+ tokens
    max_tokens=4000,
    threshold_tokens=16000,
    applies_to=["gather_sec", "gather_research"],
))
```

## Middleware Metrics

Monitor your pipeline performance:

```python
# After execution
result = await ao.launch("my_chain", data)

# Get all metrics
metrics = ao.get_middleware_metrics()
for name, data in metrics.items():
    print(f"{name}: {data}")

# Get specific middleware
token_metrics = ao.get_middleware_metrics("token_manager")
print(f"Peak usage: {token_metrics['peak_usage']}")
print(f"Compressions: {token_metrics['total_compressions']}")
```

## Debugging Tips

### 1. Validate Before Running

```python
result = ao.check()
print(f"Valid: {result.valid}")
for warning in result.warnings:
    print(f"⚠️  {warning}")
```

### 2. Visualize the DAG

```python
# ASCII (terminal)
print(ao.graph("my_chain"))

# Mermaid (for documentation)
print(ao.graph("my_chain", format="mermaid"))
```

### 3. Test Steps in Isolation

```python
result = await ao.run_step("fetch_data", {"query": "test"})
print(result["output"])
```

### 4. Enable Debug Logging

```python
import logging
logging.getLogger("agentorchestrator").setLevel(logging.DEBUG)
```

### 5. Use the Explain Method

```python
ao.explain("my_chain")
# Shows execution order, parallel groups, dependencies
```

## IDE Support

AgentOrchestrator is fully typed. For best IDE experience:

1. **Type hints**: All methods have full type annotations
2. **Docstrings**: All methods have comprehensive docstrings
3. **State models**: Use Pydantic for type-safe state with autocomplete

```python
# Your IDE will provide autocomplete for:
ao.  # Shows all methods
ctx.  # Shows get(), set(), has(), etc.
state.  # Shows your Pydantic model fields
```

## Next Steps

1. **Read the Examples**: `examples/` folder has complete working examples
2. **Check the Patterns**: `docs/patterns/` for production patterns
3. **API Reference**: `docs/API.md` for full API documentation
4. **Run the CLI**: `ao help` for command-line tools

## Quick Reference Card

```python
# Define
@ao.step(name="my_step", deps=["other"], retry=3, timeout_ms=30000)
@ao.chain(name="my_chain", dataflow=True, error_handling="continue")
@ao.agent(name="my_agent", capabilities=["search"])

# Execute
await ao.launch("chain", data)
ao.launch_sync("chain", data)
await ao.run_step("step", data)
await ao.resume(run_id)

# Middleware
ao.use(middleware)
ao.list_middleware()
ao.get_middleware_metrics()

# Validate
ao.check()
ao.graph("chain")
ao.explain("chain")
ao.discover()

# Help
ao.help()
ao.help("patterns")
```
