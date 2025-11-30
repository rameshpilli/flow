# AgentOrchestrator - Project Requirements

## Overview

AgentOrchestrator is a DAG-based chain orchestration framework for building AI/ML pipelines. It provides decorator-driven registration, automatic dependency resolution, and production-grade resilience features.

---

## System Requirements

### Python Version
- **Minimum**: Python 3.10
- **Recommended**: Python 3.11 or 3.12
- **Supported**: Python 3.10, 3.11, 3.12, 3.13

### Operating Systems
- Linux (Ubuntu 20.04+, CentOS 8+, Debian 11+)
- macOS (11.0+)
- Windows (10+, with WSL2 recommended for production)

---

## Dependencies

### Core Dependencies (Required)

| Package | Version | Purpose |
|---------|---------|---------|
| `pydantic` | >=2.0 | Data validation and settings |
| `httpx` | >=0.25.0 | Async HTTP client |
| `python-dotenv` | >=1.0.0 | Environment variable loading |

### Optional Dependencies

#### Summarization (`pip install agentorchestrator[summarization]`)
| Package | Version | Purpose |
|---------|---------|---------|
| `tiktoken` | >=0.5.0 | Token counting |
| `langchain-core` | >=0.1.0 | LLM integration |
| `langchain-text-splitters` | >=0.0.1 | Text chunking |

#### OpenAI Support (`pip install agentorchestrator[openai]`)
| Package | Version | Purpose |
|---------|---------|---------|
| `langchain-openai` | >=0.0.5 | OpenAI LLM client |

#### Anthropic Support (`pip install agentorchestrator[anthropic]`)
| Package | Version | Purpose |
|---------|---------|---------|
| `langchain-anthropic` | >=0.1.0 | Claude LLM client |

#### Observability (`pip install agentorchestrator[observability]`)
| Package | Version | Purpose |
|---------|---------|---------|
| `opentelemetry-api` | >=1.20.0 | Tracing API |
| `opentelemetry-sdk` | >=1.20.0 | Tracing SDK |
| `opentelemetry-exporter-otlp` | >=1.20.0 | OTLP exporter |
| `structlog` | >=23.0.0 | Structured logging |

#### Redis Context Store (`pip install redis`)
| Package | Version | Purpose |
|---------|---------|---------|
| `redis` | >=4.0.0 | Large payload offloading |

#### Full Installation (`pip install agentorchestrator[all]`)
Includes all optional dependencies.

---

## Installation

### From Source
```bash
# Clone the repository
git clone https://github.com/your-org/agentorchestrator.git
cd agentorchestrator

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .

# With all extras
pip install -e ".[all]"

# With development tools
pip install -e ".[dev]"
```

### From PyPI (when published)
```bash
pip install agentorchestrator

# With extras
pip install "agentorchestrator[all]"
```

---

## Environment Variables

### Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWFORGE_SERVICE_NAME` | `agentorchestrator` | Service name for telemetry |
| `FLOWFORGE_ENV` | `development` | Environment (development/staging/production) |
| `FLOWFORGE_DEBUG` | `false` | Enable debug mode |
| `FLOWFORGE_MAX_PARALLEL` | `10` | Max parallel step execution |

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_KEY` | - | LLM API key (required for summarization) |
| `LLM_BASE_URL` | `http://localhost:8000` | LLM service URL |
| `LLM_MODEL` | `gpt-4` | Default LLM model |

### Caching

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWFORGE_CACHE_ENABLED` | `true` | Enable response caching |
| `FLOWFORGE_CACHE_TTL_SECONDS` | `300` | Cache TTL in seconds |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWFORGE_RATE_LIMIT_ENABLED` | `false` | Enable rate limiting |
| `FLOWFORGE_RATE_LIMIT_RPS` | `10.0` | Requests per second |

### Retry Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWFORGE_RETRY_MAX` | `3` | Max retry attempts |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | OTLP endpoint URL |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_FORMAT` | `text` | Log format (text/json) |

### Redis (for large payload offloading)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6380` | Redis port (default uses separate port) |
| `REDIS_PASSWORD` | - | Redis password |
| `REDIS_MAXMEMORY` | - | Redis memory limit (e.g., "512mb") |

---

## Minimum Viable Setup

### 1. Basic Pipeline (No External Dependencies)

```python
from agentorchestrator import AgentOrchestrator

forge = AgentOrchestrator(name="my_app")

@forge.step(name="hello")
async def hello(ctx):
    return {"message": "Hello, World!"}

@forge.chain(name="hello_chain")
class HelloChain:
    steps = ["hello"]

# Run
import asyncio
result = asyncio.run(forge.launch("hello_chain", {}))
print(result)
```

**Requirements**: Core dependencies only.

### 2. With Summarization

```python
from agentorchestrator import AgentOrchestrator, create_openai_summarizer, SummarizerMiddleware

forge = AgentOrchestrator(name="my_app")
summarizer = create_openai_summarizer(api_key="sk-...")
forge.use(SummarizerMiddleware(summarizer=summarizer, max_tokens=4000))
```

**Requirements**: `pip install agentorchestrator[openai]`

### 3. With Redis Offloading

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.context_store import RedisContextStore

store = RedisContextStore(
    host="localhost",
    port=6380,
    maxmemory="512mb",
)
```

**Requirements**: `pip install redis` + Redis server running.

---

## Production Checklist

### Security
- [ ] API keys stored in environment variables or secret manager
- [ ] Redis password configured (if using)
- [ ] HTTPS for all external LLM calls
- [ ] Input validation enabled on all steps

### Reliability
- [ ] Circuit breakers configured for external services
- [ ] Retry policies set for transient failures
- [ ] Timeout configured for all HTTP calls
- [ ] Graceful shutdown handling

### Observability
- [ ] Structured logging enabled (`LOG_FORMAT=json`)
- [ ] OpenTelemetry tracing configured (if using)
- [ ] Health check endpoint exposed
- [ ] Metrics collection enabled

### Performance
- [ ] Redis context store for large payloads (>100KB)
- [ ] Token budgets configured for LLM calls
- [ ] Connection pooling enabled for HTTP clients
- [ ] Parallel execution limits set appropriately

---

## Testing

```bash
# Run all tests
pytest agentorchestrator/tests/ -v

# Run with coverage
pytest agentorchestrator/tests/ --cov=agentorchestrator --cov-report=html

# Run specific test categories
pytest agentorchestrator/tests/unit/ -v
pytest agentorchestrator/tests/integration/ -v
```

---

## CLI Commands

```bash
# Run a chain
agentorchestrator run my_chain --data '{"key": "value"}'

# Validate definitions
agentorchestrator check

# List all registered components
agentorchestrator list

# Visualize chain DAG
agentorchestrator graph my_chain

# Health check
agentorchestrator health

# Diagnose issues
agentorchestrator doctor

# Development mode with hot reload
agentorchestrator dev --watch
```

---

## Version Compatibility

| AgentOrchestrator | Python | Pydantic | LangChain |
|-----------|--------|----------|-----------|
| 0.1.x | 3.10+ | 2.x | 0.1.x |

---

## Support

- **GitHub Issues**: [github.com/your-org/agentorchestrator/issues](https://github.com/your-org/agentorchestrator/issues)
- **Documentation**: [agentorchestrator.readthedocs.io](https://agentorchestrator.readthedocs.io)
