# AgentOrchestrator

**A DAG-based Chain Orchestration Framework for AI/ML Pipelines**

AgentOrchestrator is a lightweight, decorator-driven framework for building data processing pipelines with automatic dependency resolution, parallel execution, and production-grade resilience.

## Features

- **Decorator-Based** - Simple `@ao.step()`, `@ao.agent()`, `@ao.chain()` decorators
- **DAG Execution** - Automatic dependency resolution with parallel execution
- **Middleware Stack** - Logging, caching, summarization, token management
- **Context Management** - Scoped storage with Redis offloading for large payloads
- **Multi-Agent Squad** - Supervisor patterns for coordinating specialized agents
- **Resilience** - Circuit breakers, retry with backoff, fail-fast cancellation
- **Observability** - Structured logging, OpenTelemetry tracing
- **CLI Tools** - Run, validate, visualize chains from command line

## Installation

```bash
pip install -e .

# With all optional features
pip install -e ".[all]"
```

## Quick Start

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")

@ao.step(name="fetch")
async def fetch(ctx):
    ctx.set("data", [1, 2, 3])
    return {"fetched": True}

@ao.step(name="process", deps=["fetch"])
async def process(ctx):
    return {"sum": sum(ctx.get("data"))}

@ao.chain(name="my_pipeline")
class MyPipeline:
    steps = ["fetch", "process"]

# Run
import asyncio
result = asyncio.run(ao.launch("my_pipeline", {}))
```

## CLI

```bash
ao run my_pipeline --data '{"key": "value"}'
ao check              # Validate definitions
ao list               # List components
ao graph my_pipeline  # Visualize DAG
ao health             # Health check
```

## Documentation

| Section | Description |
|---------|-------------|
| [Quick Start](docs/QUICKSTART.md) | Get started in 5 minutes |
| [Understanding](docs/understanding/) | Core concepts (Context, Steps, Agents, Multi-Agent) |
| [Patterns](docs/patterns/) | Production patterns (Isolation, Summarization, Routing) |
| [Architecture](docs/ARCHITECTURE.md) | System design & diagrams |
| [API Reference](docs/API.md) | Full API documentation |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues & solutions |

### Build Docs

```bash
pip install mkdocs-material mkdocs-minify-plugin
cd ..  # ChainServer root
mkdocs serve
```

## Project Structure

```
agentorchestrator/
├── core/           # AgentOrchestrator, Context, DAG, Registry
├── middleware/     # Cache, Logger, Summarizer, Token Manager
├── squad/          # Multi-agent orchestration with supervisors
├── agents/         # BaseAgent, ResilientAgent
├── services/       # LLM Gateway, Redis, Vector store
├── utils/          # Logging, tracing, config
├── examples/       # Example implementations
└── docs/           # Documentation (MkDocs site)
```

## License

MIT
