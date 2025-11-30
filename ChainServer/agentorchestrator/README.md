# AgentOrchestrator

**A DAG-based Chain Orchestration Framework**

AgentOrchestrator is a lightweight, decorator-driven framework for building data processing pipelines with automatic dependency resolution, parallel execution, and production-grade resilience.

## Features

- **Decorator-Based**: Simple `@forge.step()`, `@forge.agent()`, `@forge.chain()` decorators
- **DAG Execution**: Automatic dependency resolution with parallel execution
- **Middleware**: Logging, caching, summarization, token management
- **Context Management**: Scoped storage with Redis offloading for large payloads
- **Resilience**: Circuit breakers, retry with backoff, fail-fast cancellation
- **Observability**: Structured logging, OpenTelemetry tracing
- **CLI**: Run, validate, visualize chains from command line

## Installation

```bash
pip install -e .

# With all optional features
pip install -e ".[all]"
```

## Quick Start

```python
from agentorchestrator import AgentOrchestrator

forge = AgentOrchestrator(name="my_app")

@forge.step(name="fetch")
async def fetch(ctx):
    ctx.set("data", [1, 2, 3])
    return {"fetched": True}

@forge.step(name="process", deps=["fetch"])
async def process(ctx):
    data = ctx.get("data")
    return {"sum": sum(data)}

@forge.chain(name="my_pipeline")
class MyPipeline:
    steps = ["fetch", "process"]

# Run
import asyncio
result = asyncio.run(forge.launch("my_pipeline", {}))
print(result)  # {"sum": 6, ...}
```

## CLI

```bash
agentorchestrator run my_pipeline --data '{"key": "value"}'
agentorchestrator check              # Validate definitions
agentorchestrator list               # List components
agentorchestrator graph my_pipeline  # Visualize DAG
agentorchestrator health             # Health check
agentorchestrator doctor             # Diagnose issues
```

## Documentation

| Document | Description |
|----------|-------------|
| [QUICKSTART](docs/QUICKSTART.md) | Get started in 5 minutes |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System design & diagrams |
| [USER_GUIDE](docs/USER_GUIDE.md) | Comprehensive usage guide |
| [API](docs/API.md) | Full API reference |
| [REQUIREMENTS](docs/REQUIREMENTS.md) | Dependencies & environment |
| [CMPT_CHAIN](docs/CMPT_CHAIN.md) | CMPT chain reference |
| [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) | Common issues |

## Project Structure

```
agentorchestrator/
├── core/           # AgentOrchestrator, Context, DAG, Registry
├── middleware/     # Cache, Logger, Summarizer, Offload
├── agents/         # BaseAgent, ResilientAgent
├── services/       # CMPT chain services
├── chains/         # Pre-built chains (CMPT)
├── utils/          # Logging, tracing, config
├── testing/        # Test utilities
└── examples/       # Example chains
```

## License

MIT
