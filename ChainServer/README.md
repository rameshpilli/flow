# ChainServer

A client meeting prep (CMPT) chain server built with **AgentOrchestrator** - a DAG-based chain orchestration framework.

## Overview

This project implements a financial data pipeline that:
1. **Extracts context** from meeting requests (company info, temporal context, personas)
2. **Prioritizes content sources** based on earnings proximity and market cap
3. **Executes data agents** (SEC filings, news, earnings, transcripts)
4. **Generates meeting prep** content with financial metrics and strategic analysis

## Quick Start

```bash
# Install dependencies
pip install -e ./agentorchestrator

# Run the CMPT chain example
python examples/cmpt/run.py --company "Apple Inc"

# Run tests
pytest agentorchestrator/tests/ -v
```

## Developer Setup

```bash
python3 -m venv agentorchestrator/.venv
source agentorchestrator/.venv/bin/activate

# Install framework + dev tools (ruff/pytest)
pip install -e "agentorchestrator[dev]"

# Run the full suite
python -m pytest
# Optional: lint
ruff check agentorchestrator
```

## Project Structure

```
ChainServer/
├── agentorchestrator/           # AgentOrchestrator framework
│   ├── core/                    # Core framework (Orchestrator, Context, DAG)
│   ├── middleware/              # Middleware (Summarizer, Cache, Logger)
│   ├── agents/                  # Base agent classes
│   ├── services/                # Service wrappers (re-exports from examples)
│   ├── chains/                  # Pre-built chains (CMPTChain)
│   ├── testing/                 # Test utilities
│   ├── utils/                   # Utility functions
│   ├── plugins/                 # Plugin adapters (MCP, HTTP)
│   ├── docs/                    # Documentation
│   └── tests/                   # Test suite (167 tests)
├── examples/                    # Example implementations
│   ├── 01_quickstart.py         # Minimal example
│   ├── 02_custom_agents.py      # Custom agent integration
│   ├── 03_chain_composition.py  # Chain composition patterns
│   ├── 04_meeting_prep_chain.py # Meeting prep example
│   ├── 05_capiq_integration.py  # Capital IQ integration
│   └── cmpt/                    # Complete CMPT production example
│       ├── run.py               # Main entry point
│       └── services/            # Business logic services
├── Makefile                     # Build automation
└── pyproject.toml               # Package configuration
```

## AgentOrchestrator Framework

AgentOrchestrator provides:

- **Decorator-driven registration** - `@ao.agent()`, `@ao.step()`, `@ao.chain()`
- **Automatic dependency resolution** - Steps execute in optimal order
- **Parallel execution** - Independent steps run concurrently
- **Middleware system** - Logging, caching, summarization, token management
- **Domain-aware summarization** - Content-specific extraction for financial data

### Basic Usage

```python
from agentorchestrator import AgentOrchestrator, ChainContext

ao = AgentOrchestrator(name="my_app")

@ao.step(name="extract", produces=["data"])
async def extract(ctx: ChainContext):
    ctx.set("data", {"message": "Hello"})
    return {"data": ctx.get("data")}

@ao.step(name="transform", deps=["extract"])
async def transform(ctx: ChainContext):
    data = ctx.get("data")
    return {"result": f"Processed: {data}"}

@ao.chain(name="my_chain")
class MyChain:
    steps = ["extract", "transform"]

# Run
result = await ao.launch("my_chain", {})
```

### CMPT Chain Usage

```python
from agentorchestrator.chains import CMPTChain

chain = CMPTChain()
chain.check()       # Validate
chain.graph()       # Visualize DAG

result = await chain.run(
    corporate_company_name="Apple Inc",
    meeting_datetime="2025-01-15T10:00:00Z",
)

print(result.prepared_content)
```

### Domain-Aware Summarization

```python
from agentorchestrator import create_gateway_summarizer

# Automatically extracts key info based on content type
summarizer = create_gateway_summarizer(max_tokens=4000)
ao.use(summarizer)

# Content types: sec_filing, earnings, news, transcripts, pricing
```

## CLI Commands

```bash
# Run a chain
ao run my_chain --data '{"name": "Test"}'

# Validate chain definitions
ao check

# Run with explicit chain definitions
ao --definitions ./chains.py run my_chain

# List registered components
ao list

# Visualize chain DAG
ao graph my_chain

# Generate scaffolding
ao new agent my_agent
ao new chain my_chain
ao new project my_project
```

### CMPT example services (transitional)

The `agentorchestrator.services` module re-exports the CMPT example services/models for convenience. It depends on the example code under `examples/cmpt`; if that folder isn’t present (e.g., in a trimmed install), import will fail. For production, vendor your own services instead of relying on these re-exports.

Example: putting your own services outside this repo

```
myapp/
├── downstream_services/
│   ├── __init__.py
│   ├── models.py            # Pydantic models
│   └── context_builder.py   # Your ContextBuilderService
└── main.py
```

`downstream_services/context_builder.py`:

```python
from pydantic import BaseModel
from agentorchestrator.core.context import ChainContext


class ChainRequest(BaseModel):
    corporate_company_name: str
    meeting_datetime: str | None = None


class ContextBuilderService:
    async def execute(self, request: ChainRequest):
        # Your logic here (call APIs, enrich, etc.)
        return {"company_name": request.corporate_company_name}
```

`main.py`:

```python
from agentorchestrator import AgentOrchestrator
from downstream_services.context_builder import ChainRequest, ContextBuilderService

ao = AgentOrchestrator(name="my_app")

@ao.step(name="context_builder", produces=["context_output"])
async def context_builder_step(ctx):
    request_data = ctx.get("request", {})
    request = ChainRequest(**request_data)
    output = await ContextBuilderService().execute(request)
    ctx.set("context_output", output)
    return output

@ao.chain(name="my_chain")
class MyChain:
    steps = ["context_builder"]

# run
# asyncio.run(ao.launch("my_chain", {"request": {"corporate_company_name": "Acme"}}))
```

This keeps your domain services in your own package while still using AgentOrchestrator for orchestration.

### Observability toggles

Set `AO_ENABLE_LOGGING=true` to auto-enable structured logging (optionally `AO_LOG_JSON=true`) or `AO_ENABLE_TRACING=true` to wire OpenTelemetry tracing with `AO_TRACE_SERVICE` naming. These flags are picked up automatically by the CLI when it instantiates the orchestrator.

## Documentation

- [USER_GUIDE.md](agentorchestrator/docs/USER_GUIDE.md) - Comprehensive guide with examples
- [API.md](agentorchestrator/docs/API.md) - API reference
- [QUICKSTART.md](agentorchestrator/docs/QUICKSTART.md) - Quick start guide
- [Examples](examples/) - Working code examples

## Adding Custom Agents

See [examples/05_capiq_integration.py](examples/05_capiq_integration.py) for a complete example of:
- Creating a custom data agent (Capital IQ)
- Defining steps that use the agent
- Chaining with other data sources
- Generating analysis reports

```python
@ao.agent(name="capiq", capabilities=["financials", "estimates"])
class CapIQAgent(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        # Your API logic here
        return AgentResult(data=data, source="capiq", query=query)
```

## Dependencies

### Required
- Python 3.10+
- pydantic >= 2.0
- httpx >= 0.25.0

### Optional (for summarization)
- tiktoken
- langchain-core
- langchain-text-splitters
- langchain-openai (for OpenAI summarization)
- langchain-anthropic (for Claude summarization)

## License

MIT
