# AgentOrchestrator

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**AgentOrchestrator** - DAG-based orchestration framework for AI Workflows.

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

## S3 Service

AgentOrchestrator includes an enterprise S3 integration for object storage, supporting both AWS S3 and on-premises S3-compatible services (CAGE S3, MinIO, Ceph).

**Installation:**
```bash
pip install agentorchestrator[s3]
```

**Basic Usage:**
```python
from agentorchestrator.config import get_config

# Load S3 client from .env configuration
config = get_config()
s3 = config.get_s3_client()

# Connect and use
await s3.connect()

# Upload file
await s3.upload_file("local_file.txt", "remote/key.txt")

# Download file
await s3.download_file("remote/key.txt", "downloaded.txt")

# List objects
objects = await s3.list_objects(prefix="remote/")

# Generate presigned URL
url = s3.generate_presigned_url("remote/key.txt", expires_in=3600)

# Cleanup
await s3.close()
```

**Configuration:**
Configure S3 in your `.env` file:
```bash
S3_BUCKET_NAME=your-bucket-name
S3_AWS_ACCESS_KEY_ID=your-access-key
S3_AWS_SECRET_ACCESS_KEY=your-secret-key
S3_AWS_ENDPOINT_URL=https://your-s3-endpoint.com  # For on-prem S3
S3_REGION=us-east-1  # Optional for AWS
```

See `.env.example` for all available S3 configuration options.

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