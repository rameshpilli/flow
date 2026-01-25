# ChainServer

A financial data pipeline built with **AgentOrchestrator** - a DAG-based orchestration framework for AI/ML pipelines.

## Architecture

```
ChainServer/
├── agentorchestrator/    # Core framework (domain-agnostic)
│   ├── core/             # Orchestrator, Context, DAG, Registry
│   ├── middleware/       # Cache, Logger, Summarizer, Token Manager
│   ├── squad/            # Multi-agent orchestration
│   ├── agents/           # BaseAgent, ResilientAgent
│   ├── services/         # LLM Gateway, Redis, Vector store
│   └── docs/             # Documentation (MkDocs)
├── cmpt/                 # Domain-specific CMPT implementation
└── tests/                # Test suite
```

## Quick Start

```bash
# Install
pip install -e ./agentorchestrator

# Run tests
pytest tests/ -v

# Use the CLI
ao --help
```

## Documentation

Full documentation is in [`agentorchestrator/docs/`](agentorchestrator/docs/):

| Section | Description |
|---------|-------------|
| [Quick Start](agentorchestrator/docs/QUICKSTART.md) | Get started in 5 minutes |
| [Understanding](agentorchestrator/docs/understanding/) | Core concepts (Context, Steps, Agents, Multi-Agent) |
| [Patterns](agentorchestrator/docs/patterns/) | Production patterns (Isolation, Summarization, Routing) |
| [Architecture](agentorchestrator/docs/ARCHITECTURE.md) | System design |
| [API Reference](agentorchestrator/docs/API.md) | Full API docs |

### Build Docs Locally

```bash
pip install mkdocs-material mkdocs-minify-plugin
mkdocs serve
# Open http://localhost:8000
```

## Basic Usage

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
ao check       # Validate definitions
ao list        # List components
ao graph       # Visualize DAG
ao health      # Health check
```

## License

MIT
