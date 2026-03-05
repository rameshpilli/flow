# ChainServer / AgentOrchestrator

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A DAG-based orchestration framework for AI/ML pipelines. See [`ChainServer/`](ChainServer/) for the full implementation.

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
ChainServer/
├── agentorchestrator/    # Core framework (domain-agnostic)
│   ├── core/             # Orchestrator, Context, DAG, Registry
│   ├── middleware/       # Cache, Logger, Summarizer, Token Manager
│   ├── squad/            # Multi-agent orchestration
│   ├── agents/           # BaseAgent, ResilientAgent
│   └── services/         # LLM Gateway, Redis, Vector store
├── cmpt/                 # Domain-specific CMPT implementation
├── Makefile              # Build, test, run targets
└── pyproject.toml        # Package config
```

See [gist.MD](gist.MD) for the full architecture diagram.

## Quick Start

```bash
cd ChainServer
pip install -e ".[dev]"
make test
ao --help
```

## License

MIT
