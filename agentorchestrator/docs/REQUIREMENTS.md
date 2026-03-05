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

*Alias*: `agentorchestrator[langchain]`

#### OpenAI Support (`pip install agentorchestrator[openai]`)
| Package | Version | Purpose |
|---------|---------|---------|
| `langchain-core` | >=0.1.0 | LLM integration |
| `langchain-text-splitters` | >=0.0.1 | Text chunking |
| `tiktoken` | >=0.5.0 | Token counting |
| `langchain-openai` | >=0.0.5 | OpenAI LLM client |

#### Anthropic Support (`pip install agentorchestrator[anthropic]`)
| Package | Version | Purpose |
|---------|---------|---------|
| `langchain-core` | >=0.1.0 | LLM integration |
| `langchain-text-splitters` | >=0.0.1 | Text chunking |
| `tiktoken` | >=0.5.0 | Token counting |
| `langchain-anthropic` | >=0.1.0 | Claude LLM client |

#### Observability (`pip install agentorchestrator[observability]`)
| Package | Version | Purpose |
|---------|---------|---------|
| `opentelemetry-api` | >=1.20.0 | Tracing API |
| `opentelemetry-sdk` | >=1.20.0 | Tracing SDK |
| `opentelemetry-exporter-otlp` | >=1.20.0 | OTLP exporter |
| `structlog` | >=23.0.0 | Structured logging |

#### HTTP Connectors (`pip install agentorchestrator[http]`)
| Package | Version | Purpose |
|---------|---------|---------|
| `aiohttp` | >=3.9.0 | Async HTTP client for connectors/agents |

#### Redis Context Store (`pip install agentorchestrator[redis]`)
| Package | Version | Purpose |
|---------|---------|---------|
| `redis` | >=5.0.0 | Large payload offloading |

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

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_SERVER_URL` | - | LLM gateway endpoint |
| `LLM_GATEWAY_URL` | - | Alias for `LLM_SERVER_URL` |
| `LLM_MODEL_NAME` | `gpt-4` | Default model name |
| `LLM_TEMPERATURE` | `0.0` | Sampling temperature |
| `LLM_MAX_TOKENS` | `4096` | Max output tokens |
| `LLM_TIMEOUT` | `60.0` | Request timeout (seconds) |
| `LLM_VERIFY_SSL` | `true` | Verify TLS certificates |
| `LLM_OAUTH_ENDPOINT` | - | OAuth token endpoint |
| `LLM_CLIENT_ID` | - | OAuth client ID |
| `LLM_CLIENT_SECRET` | - | OAuth client secret |
| `LLM_OAUTH_GRANT_TYPE` | `client_credentials` | OAuth grant type |
| `LLM_OAUTH_SCOPE` | `read` | OAuth scope |
| `OAUTH_TOKEN_TTL` | `3500` | OAuth token cache TTL (seconds) |
| `LLM_API_KEY` | - | API key (alternative to OAuth) |

### Chain Execution

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAIN_MAX_PARALLEL_STEPS` | `5` | Max parallel steps |
| `CHAIN_DEFAULT_TIMEOUT_MS` | `30000` | Default step timeout (ms) |
| `CHAIN_DEFAULT_RETRIES` | `3` | Default retry count |
| `CHAIN_ERROR_HANDLING` | `fail_fast` | fail_fast, continue, retry |

### Context Store (large payload offloading)

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTEXT_STORE_BACKEND` | `memory` | memory, redis, mem0 |
| `CONTEXT_STORE_REDIS_HOST` | `localhost` | Redis host |
| `CONTEXT_STORE_REDIS_PORT` | `6379` | Redis port |
| `CONTEXT_STORE_REDIS_PASSWORD` | - | Redis password |
| `CONTEXT_STORE_REDIS_DB` | `0` | Redis DB index |
| `CONTEXT_STORE_REDIS_SSL` | `false` | Enable TLS for Redis |
| `CONTEXT_STORE_TTL` | `3600` | Default TTL (seconds) |
| `CONTEXT_STORE_OFFLOAD_THRESHOLD` | `100000` | Offload threshold (bytes) |
| `MEM0_URL` | - | Mem0 service URL |
| `MEM0_API_KEY` | - | Mem0 API key |
| `MEM0_AGENT_ID` | - | Agent/user ID for mem0 scoping |
| `MEM0_ORG_ID` | - | Mem0 organization ID |

### Summarizer

| Variable | Default | Description |
|----------|---------|-------------|
| `SUMMARIZER_MAX_TOKENS` | `4000` | Max output tokens for summaries |
| `SUMMARIZER_CHUNK_SIZE` | `2000` | Text chunk size |
| `SUMMARIZER_CHUNK_OVERLAP` | `200` | Chunk overlap |
| `SUMMARIZER_STRATEGY` | `map_reduce` | stuff, map_reduce, refine |

### Cache

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_TTL_SECONDS` | `300` | Cache TTL in seconds |

### Logging & Tracing

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `VERBOSE` | `false` | Enable verbose output |
| `AO_ENABLE_TRACING` | `false` | Enable OpenTelemetry tracing |
| `AO_TRACE_SERVICE` | `agentorchestrator` | Trace service name |
| `AO_TRACE_SAMPLING_RATE` | `1.0` | Trace sampling rate |
| `AO_TRACE_BATCH_SIZE` | `512` | Batch size for trace export |
| `AO_TRACE_BATCH_DELAY_MS` | `5000` | Batch export delay (ms) |

### Redis Service (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_USERNAME` | - | Redis username |
| `REDIS_PASSWORD` | - | Redis password |

---

## Minimum Viable Setup

### 1. Basic Pipeline (No External Dependencies)

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")

@ao.step(name="hello")
async def hello(ctx):
    return {"message": "Hello, World!"}

@ao.chain(name="hello_chain")
class HelloChain:
    steps = ["hello"]

# Run
import asyncio
result = asyncio.run(ao.launch("hello_chain", {}))
print(result)
```

**Requirements**: Core dependencies only.

### 2. With Summarization

```python
from agentorchestrator import AgentOrchestrator, create_openai_summarizer, SummarizerMiddleware

ao = AgentOrchestrator(name="my_app")
summarizer = create_openai_summarizer(api_key="sk-...")
ao.use(SummarizerMiddleware(summarizer=summarizer, max_tokens=4000))
```

**Requirements**: `pip install agentorchestrator[openai]`

### 3. With Redis Offloading

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.context_store import RedisContextStore

store = RedisContextStore(
    host="localhost",
    port=6379,
    maxmemory="512mb",
)
```

**Requirements**: `pip install agentorchestrator[redis]` + Redis server running.

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
- [ ] Structured logging enabled (configure logging for JSON output)
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

The CLI is available as `ao` (recommended) or `agentorchestrator`:

```bash
# Execution
ao run my_chain --data '{"key": "value"}'      # Run a chain
ao run my_chain --resumable                    # With checkpointing
ao resume <run_id>                             # Resume failed run

# Validation & Inspection
ao check                                       # Quick validation
ao validate my_chain                           # Comprehensive validation
ao list                                        # List components
ao graph my_chain                              # Visualize DAG

# Development
ao dev --watch                                 # Hot reload mode
ao debug my_chain --data '{}'                  # Debug with snapshots

# Diagnostics
ao health --detailed                           # Health check
ao doctor                                      # Diagnose issues
```

See [CLI Reference](cli/index.md) for complete documentation.

---

## Version Compatibility

| AgentOrchestrator | Python | Pydantic | LangChain |
|-----------|--------|----------|-----------|
| 0.1.x | 3.10+ | 2.x | 0.1.x |

---

## Support

- **GitHub Issues**: [github.com/your-org/agentorchestrator/issues](https://github.com/your-org/agentorchestrator/issues)
- **Documentation**: [agentorchestrator.readthedocs.io](https://agentorchestrator.readthedocs.io)
