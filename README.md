# AgentOrchestrator

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A DAG-based orchestration framework for AI/ML pipelines.

## Why AgentOrchestrator?

| Feature | AgentOrchestrator | LangChain | LlamaIndex |
|---------|-------------------|-----------|------------|
| **Decorator-driven API** | ✅ `@ao.step()`, `@ao.chain()` | ❌ Class-based chains | ❌ Class-based |
| **DAG execution** | ✅ Auto-parallel, resumable | ⚠️ Sequential chains | ⚠️ Limited |
| **Type-safe state** | ✅ Pydantic models | ❌ Dict-based | ❌ Dict-based |
| **Event-driven workflows** | ✅ Redis/in-memory bus | ❌ No native support | ❌ No native support |
| **Multi-agent patterns** | ✅ Squad, Supervisor, ReAct | ⚠️ Agent executor only | ⚠️ Agent runner |
| **Built-in resilience** | ✅ Retry, circuit breaker | ❌ Manual setup | ❌ Manual setup |
| **Checkpointing/Resume** | ✅ Automatic | ❌ Manual | ❌ Manual |
| **Corporate auth (OAuth)** | ✅ LLM Gateway | ❌ API keys only | ❌ API keys only |

**Best for**: Teams that want Dagster-style ergonomics for AI pipelines with built-in resilience, multi-agent support, and enterprise authentication.

## Architecture

```
├── agentorchestrator/    # Core framework
│   ├── core/             # Orchestrator, Context, DAG, Registry
│   ├── middleware/       # Cache, Logger, Summarizer, Token Manager
│   ├── squad/            # Multi-agent orchestration
│   ├── agents/           # BaseAgent, ResilientAgent
│   └── services/         # LLM Gateway, Redis, Vector store
├── Makefile              # Build, test, run targets
└── pyproject.toml        # Package config
```

See [gist.MD](gist.MD) for the full architecture diagram.

## Quick Start

```bash
pip install -e ".[dev]"
make test
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

The CLI is available as both `ao` (shorthand) and `agentorchestrator` (full name):

```bash
# Execution
ao run my_pipeline --data '{"key": "value"}'  # Run a chain
ao run my_pipeline --resumable                # Run with checkpointing
ao run my_pipeline --dry-run                  # Preview execution plan
ao resume <run_id>                            # Resume failed run

# Validation & Inspection
ao check              # Quick validation
ao validate my_chain  # Comprehensive validation
ao list               # List all components
ao graph my_chain     # Visualize DAG

# Development
ao dev --watch        # Hot reload mode
ao debug my_chain     # Debug with snapshots

# Diagnostics
ao health --detailed  # Full health check
ao doctor             # Diagnose issues
ao version            # Show version
```

See [CLI Reference](agentorchestrator/docs/cli/index.md) for complete documentation.

## License

MIT
