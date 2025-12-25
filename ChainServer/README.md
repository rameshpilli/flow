# ChainServer

A financial data pipeline built with **AgentOrchestrator** - a domain-agnostic DAG-based orchestration framework.

## Architecture

This project consists of two main layers:

1. **AgentOrchestrator** (`agentorchestrator/`) - A reusable orchestration framework
2. **CMPT** (`cmpt/`) - Domain-specific Client Meeting Prep Tool implementation

## Quick Start

```bash
# Install dependencies
pip install -e ./agentorchestrator

# Run tests
pytest tests/ -v

# Use the CLI
ao --help
```

## Developer Setup

```bash
python3 -m venv .venv
source .venv/bin/activate

# Install framework + dev tools (ruff/pytest)
pip install -e "agentorchestrator[dev]"

# Run the full suite
python -m pytest

# Lint
ruff check agentorchestrator cmpt
```

## Project Structure

```
ChainServer/
├── agentorchestrator/           # AgentOrchestrator framework (domain-agnostic)
│   ├── core/                    # Core framework (Orchestrator, Context, DAG)
│   ├── middleware/              # Middleware (Summarizer, Cache, Logger)
│   ├── agents/                  # Base agent classes
│   ├── services/                # Service interfaces (LLM Gateway)
│   ├── connectors/              # External service connectors (MCP)
│   ├── llm/                     # LCEL chain builders
│   ├── testing/                 # Test utilities
│   ├── utils/                   # Utility functions
│   ├── plugins/                 # Plugin adapters (MCP, HTTP)
│   ├── templates/               # Project templates
│   └── docs/                    # Documentation
├── cmpt/                        # CMPT domain implementation
│   ├── domain_config.py         # Domain-specific prompts & extractors
│   ├── mcp_auth.py              # MCP authentication
│   └── services/                # CMPT business logic services
│       ├── models.py            # Pydantic models
│       ├── agents.py            # MCP agent integrations
│       └── _01_context_builder.py  # Context extraction
│       └── _02_content_prioritization.py  # Content prioritization
│       └── _03_response_builder.py  # Response generation
├── tests/                       # Test suite
├── workflows/                   # Example workflows
├── Makefile                     # Build automation
└── pyproject.toml               # Package configuration
```

## AgentOrchestrator Framework

AgentOrchestrator is a **domain-agnostic** orchestration framework that provides:

- **Decorator-driven registration** - `@ao.agent()`, `@ao.step()`, `@ao.chain()`
- **Automatic dependency resolution** - Steps execute in optimal order
- **Parallel execution** - Independent steps run concurrently
- **Middleware system** - Logging, caching, summarization, token management
- **Pluggable summarization** - Register domain-specific extractors at runtime

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

### Domain-Aware Summarization (Pluggable)

```python
from agentorchestrator.middleware import LangChainSummarizer

# Register domain-specific extractors at runtime
LangChainSummarizer.register_key_field_extractor(
    "sec_filing",
    lambda doc: extract_sec_fields(doc)
)

LangChainSummarizer.register_summary_generator(
    "earnings",
    lambda doc: generate_earnings_summary(doc)
)

# Use the summarizer
summarizer = LangChainSummarizer(max_tokens=4000)
ao.use(summarizer)
```

### LCEL Chain Builders

```python
from agentorchestrator.llm import create_extraction_chain
from pydantic import BaseModel

class FinancialMetrics(BaseModel):
    revenue: float
    growth_rate: float

chain = create_extraction_chain(
    prompt_template="Extract financial metrics from: {text}",
    response_model=FinancialMetrics,
)
result = await chain.ainvoke({"text": "Revenue was $10B, up 15%..."})
# result is FinancialMetrics(revenue=10000000000, growth_rate=0.15)
```

## CMPT Implementation

The `cmpt/` directory contains the domain-specific Client Meeting Prep Tool:

```python
from cmpt.domain_config import DOMAIN_PROMPTS, register_cmpt_extractors
from cmpt.services.agents import CapIQMCPAgent

# Register CMPT-specific extractors with the framework
register_cmpt_extractors()

# Use domain-specific prompts
prompt = DOMAIN_PROMPTS["sec_filing"]["system"]
```

## CLI Commands

```bash
# Run a chain
ao run my_chain --data '{"name": "Test"}'

# Validate chain definitions
ao check

# List registered components
ao list

# Visualize chain DAG
ao graph my_chain

# Generate scaffolding
ao new agent my_agent
ao new chain my_chain
ao new project my_project

# Dry-run mode (simulate without side effects)
ao run my_chain --dry-run --data '{"name": "Test"}'

# Validate with detailed checks
ao validate my_chain
```

### Observability Toggles

Set environment variables to enable observability:

```bash
# Enable structured logging
export AO_ENABLE_LOGGING=true
export AO_LOG_JSON=true  # Optional: JSON format

# Enable OpenTelemetry tracing
export AO_ENABLE_TRACING=true
export AO_TRACE_SERVICE=my_service
```

## Documentation

- [USER_GUIDE.md](agentorchestrator/docs/USER_GUIDE.md) - Comprehensive guide with examples
- [API.md](agentorchestrator/docs/API.md) - API reference
- [QUICKSTART.md](agentorchestrator/docs/QUICKSTART.md) - Quick start guide

## Adding Custom Agents

```python
from agentorchestrator.agents import BaseAgent, AgentResult

@ao.agent(name="my_data_agent", capabilities=["fetch", "search"])
class MyDataAgent(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        # Your API logic here
        data = await self.call_external_api(query)
        return AgentResult(data=data, source="my_source", query=query)
```

## Creating Your Own Domain Layer

To create a domain-specific implementation like CMPT:

```
myapp/
├── domain_config.py             # Domain-specific prompts & extractors
├── services/
│   ├── models.py                # Pydantic models
│   └── my_service.py            # Business logic
└── main.py                      # Entry point
```

```python
# domain_config.py
from agentorchestrator.middleware import LangChainSummarizer

DOMAIN_PROMPTS = {
    "my_content_type": {
        "system": "You are analyzing...",
        "user": "Extract key information from: {content}"
    }
}

def register_my_extractors():
    LangChainSummarizer.register_key_field_extractor(
        "my_content_type",
        lambda doc: {"key": doc.page_content[:100]}
    )
```

## Dependencies

### Required
- Python 3.10+
- pydantic >= 2.0
- httpx >= 0.25.0

### Optional (for LLM features)
- tiktoken
- langchain-core
- langchain-text-splitters
- langchain-openai (for OpenAI)
- langchain-anthropic (for Claude)

## License

MIT
