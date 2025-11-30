"""
FlowForge Project Scaffolding

Generates complete project structures for new FlowForge applications.

Usage:
    flowforge new project my_app
    flowforge new project my_app --template cmpt
    flowforge new project my_app --with-api --with-docker
"""

import os
import re
from pathlib import Path
from typing import Any


def to_snake_case(name: str) -> str:
    """Convert CamelCase or kebab-case to snake_case."""
    name = re.sub(r'[-\s]+', '_', name)
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    name = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', name)
    return name.lower()


def to_pascal_case(name: str) -> str:
    """Convert snake_case or kebab-case to PascalCase."""
    return ''.join(word.capitalize() for word in re.split(r'[-_\s]+', name))


def to_kebab_case(name: str) -> str:
    """Convert snake_case or CamelCase to kebab-case."""
    name = to_snake_case(name)
    return name.replace('_', '-')


# ═══════════════════════════════════════════════════════════════════════════════
#                         PROJECT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════


def get_pyproject_toml(name: str, description: str) -> str:
    """Generate pyproject.toml content."""
    snake_name = to_snake_case(name)
    return f'''[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{snake_name}"
version = "0.1.0"
description = "{description}"
readme = "README.md"
requires-python = ">=3.11"
license = {{text = "MIT"}}
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

dependencies = [
    "flowforge>=0.1.0",
    "pydantic>=2.0.0",
    "httpx>=0.24.0",
    "redis>=4.5.0",
]

[project.optional-dependencies]
api = [
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.22.0",
]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "black>=23.0.0",
    "ruff>=0.0.270",
    "mypy>=1.0.0",
]

[project.scripts]
{snake_name} = "{snake_name}.cli:main"

[project.entry-points."flowforge.agents"]
# Register custom agents as plugins
# my_agent = "{snake_name}.agents:MyAgent"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.black]
line-length = 100
target-version = ["py311"]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
'''


def get_readme(name: str, description: str) -> str:
    """Generate README.md content."""
    pascal_name = to_pascal_case(name)
    snake_name = to_snake_case(name)
    return f'''# {pascal_name}

{description}

Built with [FlowForge](https://github.com/flowforge/flowforge) - A DAG-based Chain Orchestration Framework.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Validate chain definitions
flowforge check

# Run a chain
flowforge run hello_chain --data '{{"message": "Hello World"}}'

# Visualize chain DAG
flowforge graph hello_chain --format mermaid
```

## Project Structure

```
{snake_name}/
├── src/{snake_name}/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point
│   ├── chains/             # Chain definitions
│   │   ├── __init__.py
│   │   └── hello_chain.py
│   ├── agents/             # Custom agents
│   │   ├── __init__.py
│   │   └── example_agent.py
│   ├── services/           # Business logic services
│   │   └── __init__.py
│   └── models/             # Pydantic models
│       └── __init__.py
├── tests/
├── config/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Running the API Server

```bash
# Install API dependencies
pip install -e ".[api]"

# Start the server
uvicorn {snake_name}.api:app --reload --port 8000

# Or with Docker
docker-compose up
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/ready` | GET | Readiness check |
| `/run/{{chain_name}}` | POST | Run a chain |
| `/runs/{{run_id}}` | GET | Get run status |
| `/runs/{{run_id}}/output` | GET | Get partial outputs |

## Development

```bash
# Run tests
pytest

# Type checking
mypy src/

# Lint
ruff check src/
black --check src/
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `{snake_name.upper()}_ENV` | `development` | Environment |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `LLM_API_KEY` | - | LLM API key |
| `LOG_LEVEL` | `INFO` | Logging level |

## License

MIT
'''


def get_dockerfile() -> str:
    """Generate Dockerfile content."""
    return '''# syntax=docker/dockerfile:1
FROM python:3.11-slim as base

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_NO_CACHE_DIR=1 \\
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appgroup && \\
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Builder stage
FROM base as builder

COPY pyproject.toml .
COPY src/ src/

RUN pip install --user -e ".[api]"

# Runtime stage
FROM base as runtime

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY --chown=appuser:appgroup src/ src/
COPY --chown=appuser:appgroup config/ config/

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
'''


def get_docker_compose(name: str) -> str:
    """Generate docker-compose.yml content."""
    snake_name = to_snake_case(name)
    return f'''version: "3.8"

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - {snake_name.upper()}_ENV=production
      - REDIS_URL=redis://redis:6379
      - LOG_LEVEL=INFO
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    command: redis-server --appendonly yes

volumes:
  redis_data:
'''


def get_github_workflow(name: str) -> str:
    """Generate GitHub Actions CI workflow."""
    snake_name = to_snake_case(name)
    return f'''name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{{{ matrix.python-version }}}}
        uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint
        run: |
          ruff check src/
          black --check src/

      - name: Type check
        run: mypy src/

      - name: Test
        run: pytest --cov=src --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  validate:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -e .

      - name: Validate chains
        run: flowforge check

  build:
    runs-on: ubuntu-latest
    needs: [test, validate]
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t {snake_name}:${{{{ github.sha }}}} .

      - name: Test Docker image
        run: |
          docker run -d --name test -p 8000:8000 {snake_name}:${{{{ github.sha }}}}
          sleep 5
          curl -f http://localhost:8000/health
          docker stop test
'''


def get_env_example(name: str) -> str:
    """Generate .env.example content."""
    snake_name = to_snake_case(name)
    return f'''# {snake_name} Configuration
# Copy to .env and fill in values

# Environment
{snake_name.upper()}_ENV=development

# Redis
REDIS_URL=redis://localhost:6379

# LLM Configuration
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=text

# OpenTelemetry (optional)
OTEL_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=

# FlowForge
FLOWFORGE_MAX_PARALLEL=10
FLOWFORGE_CACHE_ENABLED=true
FLOWFORGE_CACHE_TTL_SECONDS=300
'''


def get_init_py(name: str) -> str:
    """Generate __init__.py content."""
    pascal_name = to_pascal_case(name)
    return f'''"""
{pascal_name} - Built with FlowForge
"""

__version__ = "0.1.0"
'''


def get_cli_py(name: str) -> str:
    """Generate cli.py content."""
    snake_name = to_snake_case(name)
    pascal_name = to_pascal_case(name)
    return f'''#!/usr/bin/env python3
"""
{pascal_name} CLI

Command-line interface for {pascal_name}.
"""

import argparse
import asyncio
import json
import sys

from {snake_name} import __version__


def get_forge():
    """Get or create the FlowForge instance."""
    from flowforge import get_forge as _get_forge

    # Import chains to register them
    from {snake_name}.chains import hello_chain  # noqa: F401

    return _get_forge()


def cmd_run(args: argparse.Namespace) -> int:
    """Run a chain."""
    forge = get_forge()

    data = {{}}
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"Error parsing --data JSON: {{e}}")
            return 1

    print(f"Running {{args.chain_name}}...")

    try:
        result = asyncio.run(forge.launch(args.chain_name, data))
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("success") else 1
    except Exception as e:
        print(f"Error: {{e}}")
        return 1


def cmd_check(args: argparse.Namespace) -> int:
    """Validate chain definitions."""
    forge = get_forge()
    result = forge.check(args.chain_name)
    return 0 if result.get("valid") else 1


def cmd_list(args: argparse.Namespace) -> int:
    """List all definitions."""
    forge = get_forge()
    forge.list_defs()
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="{snake_name}",
        description="{pascal_name} CLI",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {{__version__}}")

    subparsers = parser.add_subparsers(dest="command")

    # run command
    run_parser = subparsers.add_parser("run", help="Run a chain")
    run_parser.add_argument("chain_name", help="Chain to run")
    run_parser.add_argument("--data", "-d", help="JSON input data")
    run_parser.set_defaults(func=cmd_run)

    # check command
    check_parser = subparsers.add_parser("check", help="Validate definitions")
    check_parser.add_argument("chain_name", nargs="?", help="Chain to check")
    check_parser.set_defaults(func=cmd_check)

    # list command
    list_parser = subparsers.add_parser("list", help="List definitions")
    list_parser.set_defaults(func=cmd_list)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
'''


def get_api_py(name: str) -> str:
    """Generate api.py content with FastAPI server."""
    snake_name = to_snake_case(name)
    pascal_name = to_pascal_case(name)
    return f'''"""
{pascal_name} API Server

FastAPI server exposing chain execution endpoints.

Usage:
    uvicorn {snake_name}.api:app --reload --port 8000
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from flowforge import get_forge
from flowforge.utils.health import run_health_checks, is_ready, is_live, HealthStatus

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                         REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class RunRequest(BaseModel):
    """Request to run a chain."""
    data: dict[str, Any] = Field(default_factory=dict)
    resumable: bool = Field(default=True, description="Enable checkpointing")
    run_id: str | None = Field(default=None, description="Custom run ID")


class RunResponse(BaseModel):
    """Response from chain execution."""
    run_id: str
    chain_name: str
    status: str
    success: bool
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    environment: str
    checks: dict[str, Any] = Field(default_factory=dict)


class RunStatusResponse(BaseModel):
    """Run status response."""
    run_id: str
    chain_name: str
    status: str
    completed_steps: int
    total_steps: int
    created_at: str
    updated_at: str
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
#                         APPLICATION SETUP
# ═══════════════════════════════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting {pascal_name} API server")

    # Import chains to register them
    from {snake_name}.chains import hello_chain  # noqa: F401

    yield

    # Shutdown
    logger.info("Shutting down {pascal_name} API server")
    forge = get_forge()
    await forge.cleanup_resources()


app = FastAPI(
    title="{pascal_name} API",
    description="Chain execution API built with FlowForge",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
#                         HEALTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Full health check with dependency status.

    Returns detailed health information for monitoring.
    """
    result = await run_health_checks(include_external=True, timeout_seconds=5.0)
    return HealthResponse(
        status=result.status.value,
        version=result.version,
        environment=result.environment,
        checks={{
            "components": [
                {{
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                }}
                for c in result.components
            ],
            "summary": {{
                "healthy": result.healthy_count,
                "degraded": result.degraded_count,
                "unhealthy": result.unhealthy_count,
            }},
        }},
    )


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """
    Kubernetes readiness probe.

    Returns 200 if the service can handle requests.
    """
    if await is_ready():
        return {{"status": "ready"}}
    raise HTTPException(status_code=503, detail="Service not ready")


@app.get("/live", tags=["Health"])
async def liveness_check():
    """
    Kubernetes liveness probe.

    Returns 200 if the service is alive.
    """
    if await is_live():
        return {{"status": "alive"}}
    raise HTTPException(status_code=503, detail="Service not alive")


# ═══════════════════════════════════════════════════════════════════════════════
#                         CHAIN EXECUTION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.post("/run/{{chain_name}}", response_model=RunResponse, tags=["Chains"])
async def run_chain(chain_name: str, request: RunRequest):
    """
    Execute a chain.

    Args:
        chain_name: Name of the chain to run
        request: Run request with input data

    Returns:
        RunResponse with execution results
    """
    forge = get_forge()
    started_at = datetime.utcnow()

    try:
        if request.resumable:
            result = await forge.launch_resumable(
                chain_name,
                request.data,
                run_id=request.run_id,
            )
            run_id = result.get("run_id", "unknown")
        else:
            result = await forge.launch(chain_name, request.data)
            run_id = request.run_id or f"run_{{started_at.timestamp()}}"

        completed_at = datetime.utcnow()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        return RunResponse(
            run_id=run_id,
            chain_name=chain_name,
            status="completed" if result.get("success") else "failed",
            success=result.get("success", False),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            result=result,
            error=result.get("error"),
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error running chain {{chain_name}}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{{run_id}}", response_model=RunStatusResponse, tags=["Chains"])
async def get_run_status(run_id: str):
    """
    Get status of a chain run.

    Args:
        run_id: ID of the run

    Returns:
        RunStatusResponse with current status
    """
    forge = get_forge()

    try:
        run = await forge.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {{run_id}}")

        return RunStatusResponse(
            run_id=run.run_id,
            chain_name=run.chain_name,
            status=run.status,
            completed_steps=run.completed_steps,
            total_steps=run.total_steps,
            created_at=run.created_at,
            updated_at=run.updated_at,
            error=run.error if hasattr(run, "error") else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting run status: {{run_id}}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{{run_id}}/output", tags=["Chains"])
async def get_run_output(run_id: str):
    """
    Get partial outputs from a run.

    Useful for getting results from partially completed chains.

    Args:
        run_id: ID of the run

    Returns:
        Dict with step outputs
    """
    forge = get_forge()

    try:
        result = await forge.get_partial_output(run_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Run not found: {{run_id}}")
        return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error getting run output: {{run_id}}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/runs/{{run_id}}/resume", response_model=RunResponse, tags=["Chains"])
async def resume_run(run_id: str):
    """
    Resume a failed or partial run.

    Args:
        run_id: ID of the run to resume

    Returns:
        RunResponse with execution results
    """
    forge = get_forge()
    started_at = datetime.utcnow()

    try:
        result = await forge.resume(run_id)
        completed_at = datetime.utcnow()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        return RunResponse(
            run_id=run_id,
            chain_name=result.get("chain_name", "unknown"),
            status="completed" if result.get("success") else "failed",
            success=result.get("success", False),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            result=result,
            error=result.get("error"),
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error resuming run: {{run_id}}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
#                         CHAIN MANAGEMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/chains", tags=["Chains"])
async def list_chains():
    """List all registered chains."""
    forge = get_forge()
    chains = list(forge._chain_registry.keys())
    return {{"chains": chains, "count": len(chains)}}


@app.get("/chains/{{chain_name}}/validate", tags=["Chains"])
async def validate_chain(chain_name: str):
    """Validate a chain definition."""
    forge = get_forge()
    try:
        result = forge.check(chain_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/chains/{{chain_name}}/graph", tags=["Chains"])
async def get_chain_graph(chain_name: str, format: str = "mermaid"):
    """Get chain DAG visualization."""
    forge = get_forge()
    try:
        graph = forge.graph(chain_name, format=format)
        return {{"chain_name": chain_name, "format": format, "graph": graph}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
'''


def get_hello_chain_py(name: str) -> str:
    """Generate hello_chain.py content."""
    snake_name = to_snake_case(name)
    pascal_name = to_pascal_case(name)
    return f'''"""
Hello Chain

A simple example chain demonstrating FlowForge basics.
"""

from flowforge import FlowForge, ChainContext
from pydantic import BaseModel


# Get or create the global FlowForge instance
from flowforge import get_forge
forge = get_forge()


# ═══════════════════════════════════════════════════════════════════════════════
#                         INPUT/OUTPUT MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class HelloInput(BaseModel):
    """Input for the hello chain."""
    message: str = "Hello"
    name: str = "World"


class HelloOutput(BaseModel):
    """Output from the hello chain."""
    greeting: str
    timestamp: str


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEPS
# ═══════════════════════════════════════════════════════════════════════════════


@forge.step(
    name="prepare_greeting",
    produces=["greeting_data"],
    description="Prepares the greeting message",
)
async def prepare_greeting(ctx: ChainContext):
    """Prepare the greeting data."""
    from datetime import datetime

    # Get input from context
    message = ctx.get("message", "Hello")
    name = ctx.get("name", "World")

    # Prepare greeting
    greeting = f"{{message}}, {{name}}!"
    timestamp = datetime.utcnow().isoformat()

    # Store in context
    result = {{
        "greeting": greeting,
        "timestamp": timestamp,
        "original_message": message,
        "original_name": name,
    }}
    ctx.set("greeting_data", result)

    return result


@forge.step(
    name="format_output",
    deps=[prepare_greeting],
    produces=["final_output"],
    description="Formats the final output",
)
async def format_output(ctx: ChainContext):
    """Format the output."""
    greeting_data = ctx.get("greeting_data")

    # Create final output
    output = HelloOutput(
        greeting=greeting_data["greeting"],
        timestamp=greeting_data["timestamp"],
    )

    ctx.set("final_output", output.model_dump())

    return output.model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
#                         CHAIN DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════


@forge.chain(
    name="hello_chain",
    description="A simple greeting chain",
)
class HelloChain:
    """Hello chain - demonstrates basic FlowForge patterns."""
    steps = [prepare_greeting, format_output]


# ═══════════════════════════════════════════════════════════════════════════════
#                         CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


async def run(message: str = "Hello", name: str = "World") -> dict:
    """Run the hello chain."""
    return await forge.launch("hello_chain", {{"message": message, "name": name}})


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run())
    print(result)
'''


def get_chains_init_py() -> str:
    """Generate chains/__init__.py content."""
    return '''"""
Chain Definitions

Import chains here to register them with FlowForge.
"""

from .hello_chain import HelloChain, run as run_hello

__all__ = ["HelloChain", "run_hello"]
'''


def get_agents_init_py() -> str:
    """Generate agents/__init__.py content."""
    return '''"""
Custom Agents

Define custom agents here. Register them as entry points in pyproject.toml
for plugin discovery.
"""

# Example:
# from .example_agent import ExampleAgent
# __all__ = ["ExampleAgent"]
'''


def get_example_agent_py(name: str) -> str:
    """Generate example_agent.py content."""
    return '''"""
Example Agent

Demonstrates how to create a custom FlowForge agent.
"""

from flowforge.agents.base import BaseAgent, AgentResult


class ExampleAgent(BaseAgent):
    """
    Example agent demonstrating the agent interface.

    Register this agent in pyproject.toml:

        [project.entry-points."flowforge.agents"]
        example = "my_app.agents:ExampleAgent"
    """

    _flowforge_name = "example_agent"
    _flowforge_version = "1.0.0"

    # Agent capability schema (for plugin discovery)
    CAPABILITIES = {
        "search": {
            "description": "Search for data",
            "parameters": {
                "query": {"type": "string", "required": True},
                "limit": {"type": "integer", "default": 10},
            },
        },
        "fetch": {
            "description": "Fetch specific item by ID",
            "parameters": {
                "item_id": {"type": "string", "required": True},
            },
        },
    }

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.api_url = config.get("api_url") if config else None

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch data based on query.

        Args:
            query: Search query
            **kwargs: Additional parameters (limit, filters, etc.)

        Returns:
            AgentResult with fetched data
        """
        import time
        start = time.perf_counter()

        # TODO: Implement actual data fetching
        data = {
            "query": query,
            "results": [
                {"id": "1", "title": f"Result for: {query}"},
            ],
        }

        duration = (time.perf_counter() - start) * 1000

        return AgentResult(
            data=data,
            source=self._flowforge_name,
            query=query,
            duration_ms=duration,
            metadata={
                "result_count": len(data["results"]),
            },
        )

    async def health_check(self) -> bool:
        """Check if agent is healthy."""
        # TODO: Implement actual health check (e.g., ping API)
        return True
'''


def get_models_init_py() -> str:
    """Generate models/__init__.py content."""
    return '''"""
Pydantic Models

Shared data models for input/output validation.
"""

from pydantic import BaseModel, Field


class ChainRequest(BaseModel):
    """Base request model for chain execution."""
    pass


class ChainResponse(BaseModel):
    """Base response model from chain execution."""
    success: bool = Field(default=True)
    error: str | None = Field(default=None)


__all__ = ["ChainRequest", "ChainResponse"]
'''


def get_services_init_py() -> str:
    """Generate services/__init__.py content."""
    return '''"""
Business Logic Services

Encapsulate complex business logic in services, then use them in steps.
"""
'''


def get_conftest_py(name: str) -> str:
    """Generate conftest.py for pytest."""
    snake_name = to_snake_case(name)
    return f'''"""
Pytest configuration and fixtures.
"""

import asyncio
import pytest
from flowforge import FlowForge


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def forge():
    """Create isolated FlowForge instance for testing."""
    with FlowForge.temp_registries("test") as f:
        yield f


@pytest.fixture
def sample_input():
    """Sample input data for testing."""
    return {{
        "message": "Test",
        "name": "User",
    }}
'''


def get_test_chains_py(name: str) -> str:
    """Generate test_chains.py content."""
    snake_name = to_snake_case(name)
    return f'''"""
Chain Tests
"""

import pytest
from flowforge import FlowForge


class TestHelloChain:
    """Tests for hello_chain."""

    @pytest.fixture
    def forge(self):
        """Create isolated FlowForge instance."""
        with FlowForge.temp_registries("test") as f:
            # Import and register chain
            from {snake_name}.chains import hello_chain  # noqa: F401
            yield f

    @pytest.mark.asyncio
    async def test_hello_chain_success(self, forge, sample_input):
        """Test successful chain execution."""
        result = await forge.launch("hello_chain", sample_input)

        assert result["success"]
        assert "final_output" in result.get("context", {{}}).get("data", {{}})

    @pytest.mark.asyncio
    async def test_hello_chain_default_values(self, forge):
        """Test chain with default values."""
        result = await forge.launch("hello_chain", {{}})

        assert result["success"]

    def test_chain_validation(self, forge):
        """Test chain definition is valid."""
        result = forge.check("hello_chain")
        assert result.get("valid", False)
'''


def get_gitignore() -> str:
    """Generate .gitignore content."""
    return '''# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.venv/
venv/
ENV/
env/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/

# Type checking
.mypy_cache/

# Documentation
docs/_build/

# Local config
.env
.env.local
*.local

# FlowForge
.flowforge/
checkpoints/

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db
'''


def get_config_yaml(name: str) -> str:
    """Generate config/default.yaml content."""
    snake_name = to_snake_case(name)
    return f'''# {snake_name} Configuration
# Override with environment variables or .env file

app:
  name: {snake_name}
  environment: development

flowforge:
  max_parallel: 10
  default_timeout_ms: 30000
  cache:
    enabled: true
    ttl_seconds: 300

redis:
  url: redis://localhost:6379

logging:
  level: INFO
  format: text  # text or json
'''


# ═══════════════════════════════════════════════════════════════════════════════
#                         PROJECT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════


def generate_project(
    name: str,
    output_dir: Path,
    description: str = "",
    with_api: bool = True,
    with_docker: bool = True,
    with_ci: bool = True,
    template: str = "default",
) -> list[str]:
    """
    Generate a complete FlowForge project.

    Args:
        name: Project name
        output_dir: Directory to create project in
        description: Project description
        with_api: Include FastAPI server
        with_docker: Include Docker files
        with_ci: Include CI/CD configuration
        template: Template to use (default, cmpt)

    Returns:
        List of created file paths
    """
    snake_name = to_snake_case(name)
    pascal_name = to_pascal_case(name)

    if not description:
        description = f"{pascal_name} - A FlowForge-based data processing pipeline"

    project_dir = output_dir / snake_name
    src_dir = project_dir / "src" / snake_name
    chains_dir = src_dir / "chains"
    agents_dir = src_dir / "agents"
    services_dir = src_dir / "services"
    models_dir = src_dir / "models"
    tests_dir = project_dir / "tests"
    config_dir = project_dir / "config"

    created_files = []

    # Create directories
    for d in [src_dir, chains_dir, agents_dir, services_dir, models_dir, tests_dir, config_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Core files
    files = {
        project_dir / "pyproject.toml": get_pyproject_toml(name, description),
        project_dir / "README.md": get_readme(name, description),
        project_dir / ".gitignore": get_gitignore(),
        project_dir / ".env.example": get_env_example(name),
        config_dir / "default.yaml": get_config_yaml(name),
        # Source files
        src_dir / "__init__.py": get_init_py(name),
        src_dir / "cli.py": get_cli_py(name),
        chains_dir / "__init__.py": get_chains_init_py(),
        chains_dir / "hello_chain.py": get_hello_chain_py(name),
        agents_dir / "__init__.py": get_agents_init_py(),
        agents_dir / "example_agent.py": get_example_agent_py(name),
        services_dir / "__init__.py": get_services_init_py(),
        models_dir / "__init__.py": get_models_init_py(),
        # Tests
        tests_dir / "__init__.py": "",
        tests_dir / "conftest.py": get_conftest_py(name),
        tests_dir / "test_chains.py": get_test_chains_py(name),
    }

    # Optional API server
    if with_api:
        files[src_dir / "api.py"] = get_api_py(name)

    # Optional Docker files
    if with_docker:
        files[project_dir / "Dockerfile"] = get_dockerfile()
        files[project_dir / "docker-compose.yml"] = get_docker_compose(name)

    # Optional CI/CD
    if with_ci:
        github_dir = project_dir / ".github" / "workflows"
        github_dir.mkdir(parents=True, exist_ok=True)
        files[github_dir / "ci.yml"] = get_github_workflow(name)

    # Write all files
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        created_files.append(str(path.relative_to(project_dir)))

    return created_files
