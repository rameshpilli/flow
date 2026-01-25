# AgentOrchestrator

<div class="hero" markdown>

**A DAG-based Chain Orchestration Framework for AI/ML Pipelines**

AgentOrchestrator is a lightweight, decorator-driven framework for building data processing pipelines with automatic dependency resolution, parallel execution, and production-grade resilience.

[Get Started](QUICKSTART.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/your-org/agentorchestrator){ .md-button }

</div>

---

## Key Features

<div class="grid cards" markdown>

-   :material-lightning-bolt:{ .lg .middle } **Decorator-Based**

    ---

    Simple `@ao.step()`, `@ao.agent()`, `@ao.chain()` decorators for intuitive pipeline definition

-   :material-graph:{ .lg .middle } **DAG Execution**

    ---

    Automatic dependency resolution with parallel execution for optimal performance

-   :material-layers:{ .lg .middle } **Middleware Stack**

    ---

    Logging, caching, summarization, token management, and more out of the box

-   :material-database:{ .lg .middle } **Context Management**

    ---

    Scoped storage with Redis offloading for large payloads and optional RAG support

-   :material-shield-check:{ .lg .middle } **Resilience**

    ---

    Circuit breakers, retry with exponential backoff, fail-fast cancellation

-   :material-chart-line:{ .lg .middle } **Observability**

    ---

    Structured logging, OpenTelemetry tracing, and comprehensive metrics

-   :material-account-group:{ .lg .middle } **Multi-Agent Squad**

    ---

    Built-in supervisor patterns for coordinating multiple specialized agents

-   :material-console:{ .lg .middle } **CLI Tools**

    ---

    Run, validate, visualize, and debug chains from the command line

</div>

---

## Quick Example

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")

@ao.step(name="fetch")
async def fetch(ctx):
    ctx.set("data", [1, 2, 3])
    return {"fetched": True}

@ao.step(name="process", deps=["fetch"])
async def process(ctx):
    data = ctx.get("data")
    return {"sum": sum(data)}

@ao.chain(name="my_pipeline")
class MyPipeline:
    steps = ["fetch", "process"]

# Run the pipeline
import asyncio
result = asyncio.run(ao.launch("my_pipeline", {}))
print(result)  # {"sum": 6, ...}
```

---

## Installation

=== "Basic"

    ```bash
    pip install agentorchestrator
    ```

=== "With All Features"

    ```bash
    pip install agentorchestrator[all]
    ```

=== "Development"

    ```bash
    git clone https://github.com/your-org/agentorchestrator.git
    cd agentorchestrator
    pip install -e ".[dev,all]"
    ```

---

## CLI Usage

```bash
# Run a chain
agentorchestrator run my_pipeline --data '{"key": "value"}'

# Validate definitions
agentorchestrator check

# List all components
agentorchestrator list

# Visualize DAG
agentorchestrator graph my_pipeline

# Health check
agentorchestrator health

# Diagnose issues
agentorchestrator doctor
```

---

## Architecture Overview

AgentOrchestrator is built on a clean 6-layer architecture:

```
┌─────────────────────────────────────────────────────────┐
│                     Entry Points                         │
│              (CLI / API / Direct Import)                 │
├─────────────────────────────────────────────────────────┤
│                   AgentOrchestrator                      │
│         (Central facade, config, plugin loading)         │
├─────────────────────────────────────────────────────────┤
│                    Middleware Stack                      │
│     (Logging, Caching, Token Mgmt, Summarization)        │
├─────────────────────────────────────────────────────────┤
│                      Execution                           │
│          (DAG Resolution, Parallel Runner)               │
├─────────────────────────────────────────────────────────┤
│                    Core Services                         │
│        (Context, Registry, Resources, Validation)        │
├─────────────────────────────────────────────────────────┤
│                   External Services                      │
│            (LLM Gateway, Redis, Vector Store)            │
└─────────────────────────────────────────────────────────┘
```

[Learn more about the architecture](ARCHITECTURE.md){ .md-button }

---

## Project Structure

```
agentorchestrator/
├── core/           # AgentOrchestrator, Context, DAG, Registry
├── middleware/     # Cache, Logger, Summarizer, Token Manager
├── squad/          # Multi-agent orchestration with supervisors
├── agents/         # BaseAgent, ResilientAgent
├── services/       # LLM Gateway, Redis, Vector store
├── llm/            # LCEL chain builders
├── connectors/     # MCP and external integrations
├── utils/          # Logging, tracing, config
├── testing/        # Test utilities
└── examples/       # Example implementations
```

---

## Documentation

### Learning Path

<div class="grid cards" markdown>

-   :material-school:{ .lg .middle } **Understanding**

    ---

    Core concepts: [Context](understanding/context.md), [Steps & Chains](understanding/steps_and_chains.md), [Agents](understanding/agents.md), [Multi-Agent](understanding/multi_agent.md)

-   :material-puzzle:{ .lg .middle } **Patterns**

    ---

    Production patterns: [Context Isolation](patterns/context_isolation.md), [Summarization](patterns/summarization.md), [Aggregation](patterns/aggregation.md), [Routing](patterns/routing.md)

</div>

### Reference

| Section | Description |
|---------|-------------|
| [Quick Start](QUICKSTART.md) | Get started in 5 minutes |
| [Architecture](ARCHITECTURE.md) | System design & diagrams |
| [API Reference](API.md) | Full API documentation |
| [Context Management](CONTEXT_MANAGEMENT.md) | Deep dive into context patterns |
| [Feature Examples](FEATURE_EXAMPLES.md) | Code examples for all features |
| [Troubleshooting](TROUBLESHOOTING.md) | Common issues & solutions |

---

## License

AgentOrchestrator is released under the [MIT License](https://github.com/your-org/agentorchestrator/blob/main/LICENSE).
