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

    Logging, caching, summarization, token management, reflection/self-critique, and more

-   :material-brain:{ .lg .middle } **Self-Critique (Reflection)**

    ---

    Agent self-critique with quality scoring, automatic revision cycles, and `@reflect` decorator

-   :material-connection:{ .lg .middle } **MCP Connectors**

    ---

    Model Context Protocol integration for external tool servers (HTTP, stdio, SSE)

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

## DAG in 60 Seconds

Define a DAG-style AI workflow with a single dependency list:

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="ai_workflow")

def fake_llm(prompt: str) -> str:
    return f"Plan: research '{prompt}'"

@ao.step(name="plan")
async def plan(ctx):
    question = ctx.get("question")
    ctx.set("query", question)
    return {"plan": fake_llm(question)}

# Parallel branches
@ao.step(name="search_web", deps=["plan"])
async def search_web(ctx):
    web = f"Web notes for {ctx.get('query')}"
    ctx.set("web", web)
    return {"web": web}

@ao.step(name="retrieve_docs", deps=["plan"])
async def retrieve_docs(ctx):
    docs = f"Doc notes for {ctx.get('query')}"
    ctx.set("docs", docs)
    return {"docs": docs}

@ao.step(name="synthesize", deps=["search_web", "retrieve_docs"])
async def synthesize(ctx):
    return {"summary": f"{ctx.get('web')}; {ctx.get('docs')}"}

@ao.chain(name="ai_workflow")
class AIWorkflow:
    steps = ["plan", "search_web", "retrieve_docs", "synthesize"]

import asyncio
result = asyncio.run(ao.launch("ai_workflow", {"question": "AI trends"}))
print(result["results"][-1]["output"]["summary"])

# Visualize the DAG
ao.graph("ai_workflow")
```

Swap the stubbed functions with real LLM/tool calls (LLMGateway, RAG, etc.) — the DAG stays the same.

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

The CLI is available as `ao` (recommended) or `agentorchestrator`:

```bash
# Execution
ao run my_pipeline --data '{"key": "value"}'   # Run chain
ao run my_pipeline --resumable                 # With checkpointing
ao run my_pipeline --dry-run                   # Preview execution
ao resume <run_id>                             # Resume failed run

# Validation & Inspection
ao check                                       # Quick validation
ao validate my_chain                           # Comprehensive validation
ao list                                        # List components
ao graph my_pipeline                           # Visualize DAG

# Development & Debugging
ao dev --watch                                 # Hot reload mode
ao debug my_chain --data '{}'                  # Debug with snapshots

# Health & Diagnostics
ao health --detailed                           # Full health check
ao doctor                                      # Diagnose issues
```

[CLI Reference](cli/index.md){ .md-button }

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
│   ├── agents/     # LLMGatewayAgent for squad coordination
│   ├── classifiers/# Intent classification (LLMGatewayClassifier)
│   ├── context/    # Context isolation & result aggregation
│   └── storage/    # Chat storage (InMemory, Redis)
├── agents/         # BaseAgent, ResilientAgent for data fetching
├── services/       # External service integrations
│   ├── llm_gateway.py   # LLMGatewayClient with OAuth
│   ├── redis.py         # RedisService
│   ├── vector_store.py  # VectorStoreService
│   └── mem0.py          # Mem0Memory (semantic memory)
├── connectors/     # MCP and external integrations
├── utils/          # Logging, tracing, circuit breaker, config
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

    Production patterns: [Context Isolation](patterns/context_isolation.md), [Large Response Handling](patterns/large_response_handling.md), [Routing](patterns/routing.md)

</div>

### Reference

| Section | Description |
|---------|-------------|
| [Quick Start](QUICKSTART.md) | Get started in 5 minutes |
| [API Reference](API.md) | Full API documentation |
| [Patterns Guide](patterns/index.md) | Multi-agent patterns & middleware |
| [Troubleshooting](TROUBLESHOOTING.md) | Common issues & solutions |

---

## License

AgentOrchestrator is released under the [MIT License](LICENSE).
