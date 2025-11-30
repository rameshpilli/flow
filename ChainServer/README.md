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
make install-dev

# Run the CMPT chain test
make run

# Run tests
make test
```

## Project Structure

```
ChainServer/
├── agentorchestrator/                    # AgentOrchestrator framework
│   ├── core/                     # Core framework (AgentOrchestrator, Context, DAG)
│   ├── middleware/               # Middleware (Summarizer, Cache, Logger)
│   ├── agents/                   # Data agents (SEC, News, Earnings)
│   ├── services/                 # CMPT services (Context, Prioritization, Response)
│   ├── chains/                   # Chain implementations
│   ├── USER_GUIDE.md            # Comprehensive user guide
│   └── FLOW_GUIDE.md            # Technical flow documentation
├── examples/                     # Example implementations
│   ├── quickstart.py            # Minimal example
│   ├── meeting_prep_chain.py    # Full CMPT example
│   ├── custom_agent_example.py  # Custom agent integration
│   └── capiq_integration.py     # Capital IQ integration
├── tests/                        # Test suite
├── Makefile                      # Build automation
└── pyproject.toml               # Package configuration
```

## AgentOrchestrator Framework

AgentOrchestrator provides:

- **Decorator-driven registration** - `@forge.agent()`, `@forge.step()`, `@forge.chain()`
- **Automatic dependency resolution** - Steps execute in optimal order
- **Parallel execution** - Independent steps run concurrently
- **Middleware system** - Logging, caching, summarization, token management
- **Domain-aware summarization** - Content-specific extraction for financial data

### Basic Usage

```python
from agentorchestrator import AgentOrchestrator, ChainContext

forge = AgentOrchestrator(name="my_app")

@forge.step(name="extract", produces=["data"])
async def extract(ctx: ChainContext):
    ctx.set("data", {"message": "Hello"})
    return {"data": ctx.get("data")}

@forge.step(name="transform", dependencies=["extract"])
async def transform(ctx: ChainContext):
    data = ctx.get("data")
    return {"result": f"Processed: {data}"}

@forge.chain(name="my_chain")
class MyChain:
    steps = ["extract", "transform"]

# Run
result = await forge.run("my_chain")
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

print(result.response_builder['prepared_content'])
```

### Domain-Aware Summarization

```python
from agentorchestrator import create_domain_aware_middleware

# Automatically extracts key info based on content type
middleware = create_domain_aware_middleware(llm=my_llm, max_tokens=4000)
forge.use_middleware(middleware)

# Content types: sec_filing, earnings, news, transcripts, pricing
```

## Make Commands

| Command | Description |
|---------|-------------|
| `make install` | Install production dependencies |
| `make install-dev` | Install all dependencies (including dev) |
| `make test` | Run tests |
| `make lint` | Run linters (ruff, black) |
| `make format` | Format code |
| `make check` | Run all checks (format, lint, type-check, test) |
| `make run` | Run CMPT chain test |
| `make run-capiq` | Run CapIQ integration example |
| `make docs` | Build documentation |
| `make clean` | Remove build artifacts |
| `make help` | Show all available commands |

## Documentation

- [USER_GUIDE.md](agentorchestrator/USER_GUIDE.md) - Comprehensive guide with examples
- [FLOW_GUIDE.md](agentorchestrator/FLOW_GUIDE.md) - Technical flow documentation
- [Examples](examples/) - Working code examples

## Adding Custom Agents

See [examples/capiq_integration.py](examples/capiq_integration.py) for a complete example of:
- Creating a custom data agent (Capital IQ)
- Defining steps that use the agent
- Chaining with other data sources
- Generating analysis reports

```python
@forge.agent(name="capiq", capabilities=["financials", "estimates"])
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

Install all optional dependencies:
```bash
make install-all
# or
poetry install --all-extras
```

## License

MIT
