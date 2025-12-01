# CMPT - Client Meeting Prep Tool

A production-ready example chain for generating client meeting preparation materials.

## Quick Start

```bash
# Run the CMPT chain
python cmpt/run.py --company "Apple Inc"

# With custom meeting date
python cmpt/run.py --company "Microsoft" --meeting-date "2025-01-15"

# With MCP agents (production)
python cmpt/run.py --company "Apple" --use-mcp
```

## What's from AgentOrchestrator vs CMPT-Specific?

This example demonstrates how to build domain-specific chains using AgentOrchestrator.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AGENTORCHESTRATOR (Framework)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  @ao.step() / @ao.chain()      → Chain orchestration                       │
│  BaseAgent / ResilientAgent    → Agent framework with retry/circuit breaker│
│  LLMGatewayClient              → LLM integration with OAuth                │
│  ChainContext                  → State management between steps            │
│  Middleware                    → Caching, metrics, summarization           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CMPT (Domain-Specific)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  SECFilingAgent, EarningsAgent, NewsAgent  → Domain-specific data agents   │
│  FinancialMetricsResponse                  → LLM structured output schemas │
│  GRID / TemporalSourcePrioritizer          → Priority rules                │
│  StaticSubqueryEngine                      → Query generation              │
│  llm_prompts.py                            → Financial/strategic prompts   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Architecture

The CMPT chain uses a 3-stage pipeline:

```
┌─────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│  Stage 1: Context   │───▶│  Stage 2: Priority   │───▶│  Stage 3: Response  │
│      Builder        │    │    Prioritization    │    │      Builder        │
├─────────────────────┤    ├──────────────────────┤    ├─────────────────────┤
│ • Company lookup    │    │ • Source ranking     │    │ • Execute agents    │
│ • Temporal context  │    │ • Subquery engine    │    │ • LLM generation    │
│ • Persona detection │    │ • Topic extraction   │    │ • Final formatting  │
└─────────────────────┘    └──────────────────────┘    └─────────────────────┘
```

## Folder Structure

```
cmpt/
├── README.md                          # This file
├── run.py                             # 👈 ENTRY POINT (runs the chain)
├── chain.py                           # 👈 CHAIN DEFINITION (@ao.step, @ao.chain)
├── config.py                          # Simple Config class with os.getenv()
├── .env.sample                        # Environment variables template
├── __init__.py                        # Package exports
│
├── services/                          # CMPT-specific business logic
│   ├── __init__.py                    # Re-exports from orchestrator + CMPT
│   ├── models.py                      # Pydantic data models + LLM schemas
│   ├── agents.py                      # CMPT agents (SEC, Earnings, News)
│   ├── _01_context_builder.py         # Stage 1: Extract company/temporal context
│   ├── _02_content_prioritization.py  # Stage 2: Prioritize sources, generate subqueries
│   ├── _03_response_builder.py        # Stage 3: Execute agents, build response
│   └── llm_prompts.py                 # Financial metrics & strategic prompts
│
├── 02_cmpt_tutorial.ipynb             # Interactive Jupyter notebook tutorial
└── 03_cmpt_tests.py                   # Test examples
```

## Key Files

### `chain.py` - The Pipeline Definition

This is where the 3-stage pipeline is defined using AgentOrchestrator decorators:

```python
from agentorchestrator import AgentOrchestrator

def register_cmpt_chain(ao: AgentOrchestrator):
    # Services do the actual work
    context_builder_service = ContextBuilderService()
    content_prioritization_service = ContentPrioritizationService()
    response_builder_service = ResponseBuilderService()

    # Step 1: Context Builder
    @ao.step(name="context_builder", produces=["context_output"])
    async def context_builder_step(ctx):
        request = ctx.get("request")
        output = await context_builder_service.execute(request)
        ctx.set("context_output", output)

    # Step 2: Content Prioritization (depends on Step 1)
    @ao.step(name="content_prioritization", deps=["context_builder"])
    async def content_prioritization_step(ctx):
        context = ctx.get("context_output")
        output = await content_prioritization_service.execute(context)
        ctx.set("prioritization_output", output)

    # Step 3: Response Builder (depends on Step 2)
    @ao.step(name="response_builder", deps=["content_prioritization"])
    async def response_builder_step(ctx):
        context = ctx.get("context_output")
        prioritization = ctx.get("prioritization_output")
        output = await response_builder_service.execute(context, prioritization)
        ctx.set("response_output", output)

    # Chain definition - ties the steps together
    @ao.chain(name="cmpt_chain")
    class CMPTChain:
        steps = ["context_builder", "content_prioritization", "response_builder"]
```

### `services/agents.py` - Data Agents

CMPT-specific agents that extend AgentOrchestrator's `MCPAgent`. Each agent receives parameters from `Subquery.params` which are propagated from the GRID configuration and temporal context:

```python
from agentorchestrator.agents.base import BaseAgent, ResilientAgent, ResilientAgentConfig
from agentorchestrator.connectors.mcp import MCPAgent

class SECFilingAgent(MCPAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        # kwargs contains: ticker, quarters, types, max_results
        args = {
            "reporting_entity": kwargs.get("ticker") or query,
            "retrieve": kwargs.get("quarters", 8),
            "filing_types": kwargs.get("types", ["10-K", "10-Q"]),
        }
        return await self.connector.call_tool("search_sec", args)

class EarningsAgent(MCPAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        # kwargs contains: ticker, fiscal_year, fiscal_quarter, quarters
        args = {
            "ticker": kwargs.get("ticker") or query,
            "fiscal_year": kwargs.get("fiscal_year", "2025"),
            "fiscal_quarter": kwargs.get("fiscal_quarter", "Q1"),
        }
        return await self.connector.call_tool("get_transcript", args)

class NewsAgent(MCPAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        # kwargs contains: ticker, days, sentiment, max_results
        args = {
            "search_query": f"{kwargs.get('ticker')} news",
            "days": kwargs.get("days", 30),
        }
        return await self.connector.call_tool("search_news", args)
```

**Key Features:**
- **Concurrent Execution**: All agents execute in parallel via `asyncio.gather()`
- **Parameter Propagation**: Temporal context (fiscal year/quarter, lookbacks) flows from `ContentPrioritization` → `Subquery.params` → `agent.fetch(**kwargs)`
- **Resilient Wrapping**: Each agent is wrapped with `ResilientAgent` for timeout/retry/circuit-breaker handling

## Files Explained

| File | Purpose | When to Use |
|------|---------|-------------|
| `run.py` | Entry point - runs the chain | **Start here** - CLI usage |
| `chain.py` | Chain definition with @ao.step/@ao.chain | Understanding the pipeline |
| `services/` | Modular business logic | Production - Maintainable, testable |
| `02_cmpt_tutorial.ipynb` | Interactive tutorial | Learning - Step-by-step walkthrough |
| `03_cmpt_tests.py` | Test examples | Testing - Validate your setup |

## Usage Options

### Option 1: Run from Command Line (Recommended)

```bash
python cmpt/run.py --company "Apple Inc"
```

### Option 2: Import and Use Programmatically

```python
from agentorchestrator import AgentOrchestrator
from cmpt.chain import register_cmpt_chain

ao = AgentOrchestrator(name="my_app", isolated=True)
register_cmpt_chain(ao)

result = await ao.launch("cmpt_chain", {
    "request": {
        "corporate_company_name": "Apple Inc",
        "meeting_datetime": "2025-01-15",
    }
})
```

### Option 3: Use the Convenience Function

```python
from cmpt.chain import run_cmpt_chain

result = await run_cmpt_chain("Apple Inc", "2025-01-15")
print(result["context"]["final_response"].prepared_content)
```

### Option 4: Use Services Directly (Without AgentOrchestrator)

```python
from cmpt.services import (
    ChainRequest,
    ContextBuilderService,
    ContentPrioritizationService,
    ResponseBuilderService,
)

# Create request
request = ChainRequest(corporate_company_name="Apple Inc")

# Stage 1: Build context
context_service = ContextBuilderService()
context_output = await context_service.execute(request)

# Stage 2: Prioritize content
priority_service = ContentPrioritizationService()
priority_output = await priority_service.execute(context_output)

# Stage 3: Build response
response_service = ResponseBuilderService()
response = await response_service.execute(context_output, priority_output)
```

## User Overrides

The chain supports user-provided overrides that take precedence over API-extracted values:

```python
from cmpt.services import ChainRequest, ChainRequestOverrides

request = ChainRequest(
    corporate_company_name="Apple Inc",
    meeting_datetime="2025-02-15T10:00:00Z",
    overrides=ChainRequestOverrides(
        ticker="AAPL",                    # Override ticker
        fiscal_quarter="Q1",              # Override fiscal quarter
        fiscal_year="2025",               # Override fiscal year
        next_earnings_date="2025-02-20",  # Set earnings date (triggers priority switching)
        news_lookback_days=60,            # Custom news lookback
        filing_quarters=12,               # Custom SEC filing quarters
    )
)
```

### Earnings Proximity Priority Switching

When `next_earnings_date` is provided and within 1 week of the meeting date, the chain automatically switches to **earnings_dominant** priority profile:

| Profile | Earnings | News | SEC |
|---------|----------|------|-----|
| **earnings_dominant** (within 1 week of earnings) | 50% | 30% | 20% |
| **news_dominant** (default) | 20% | 60% | 20% |

```python
# Example: Meeting on Feb 15, earnings on Feb 20 (5 days later)
# → earnings_dominant profile used, prioritizing earnings data
request = ChainRequest(
    corporate_company_name="Apple Inc",
    meeting_datetime="2025-02-15",
    overrides=ChainRequestOverrides(next_earnings_date="2025-02-20")
)
```

## Configuration

### Environment Variables

```bash
# LLM Gateway (required for response generation)
LLM_OAUTH_ENDPOINT=https://auth.example.com/oauth/token
LLM_CLIENT_ID=your-client-id
LLM_CLIENT_SECRET=your-client-secret
LLM_SERVER_URL=https://llm-gateway.example.com

# Optional: MCP server URLs for data agents
SEC_MCP_URL=http://localhost:8001
EARNINGS_MCP_URL=http://localhost:8002
NEWS_MCP_URL=http://localhost:8003
```

### Using Mock Mode (No API Keys)

The chain runs in mock mode by default when MCP URLs are not configured:

```python
# Services detect missing connectors and return mock data
result = await ao.launch("cmpt_chain", {"request": {...}})
# Returns structured mock data for testing
```

### Using MCP Agents (Production)

To connect to real MCP servers for SEC, Earnings, and News data:

```python
from agentorchestrator import AgentOrchestrator
from cmpt.chain import register_cmpt_chain

ao = AgentOrchestrator(name="cmpt_prod", isolated=True)

# Register chain with MCP enabled
register_cmpt_chain(
    ao,
    use_mcp=True,
    mcp_config={
        "sec_url": "http://localhost:8001",
        "earnings_url": "http://localhost:8002",
        "news_url": "http://localhost:8003",
    }
)

result = await ao.launch("cmpt_chain", {"request": {...}})
```

Or via CLI:

```bash
python cmpt/run.py --company "Apple Inc" --use-mcp
```

## Output Structure

```python
{
    "success": True,
    "duration_ms": 1250,
    "final_output": {
        "stage": "response_builder",
        "success": True
    },
    "context": {
        "company_name": "Apple Inc",
        "ticker": "AAPL",
        "context_output": {...},
        "prioritization_output": {...},
        "response_output": {...}
    }
}
```

## Extending the Chain

### Add a New Stage

```python
@ao.step(
    name="new_stage",
    deps=["response_builder"],  # Runs after response_builder
    produces=["new_output"],
)
async def new_stage_step(ctx):
    response = ctx.get("response_output")
    # Process response
    result = await process(response)
    ctx.set("new_output", result)
    return {"stage": "new_stage", "success": True}

# Update chain
@ao.chain(name="extended_cmpt_chain")
class ExtendedCMPTChain:
    steps = ["context_builder", "content_prioritization", "response_builder", "new_stage"]
```

### Add a Custom Agent

```python
from agentorchestrator.agents import BaseAgent, AgentResult

@ao.agent(name="custom_data_agent")
class CustomDataAgent(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        data = await self.call_api(query)
        return AgentResult(data=data, source="custom", query=query)
```

## Related Documentation

- [USER_GUIDE.md](../agentorchestrator/docs/USER_GUIDE.md) - Full framework guide
- [API.md](../agentorchestrator/docs/API.md) - API reference
- [CMPT_CHAIN.md](../agentorchestrator/docs/CMPT_CHAIN.md) - Detailed CMPT documentation

---

## What CMPT Uses from AgentOrchestrator

| Component | Used In | Purpose |
|-----------|---------|---------|
| **`AgentOrchestrator`** | chain.py, run.py | Main orchestrator with `@ao.step()`, `@ao.chain()`, `ao.launch()` |
| **`BaseAgent`** | agents.py | Base class for creating agents |
| **`ResilientAgent`** | agents.py | Wrapper adding retries, timeouts, circuit breaker |
| **`ResilientAgentConfig`** | agents.py | Config for resilient behavior |
| **`ResilientCompositeAgent`** | agents.py | Runs multiple agents in parallel |
| **`AgentResult`** | agents.py, response_builder | Standard result type from agents |
| **`MCPAgent`** | agents.py | Base class for MCP-connected agents |
| **`ConnectorConfig`** | agents.py | Config for MCP connectors |
| **`LLMGatewayClient`** | services/__init__.py | LLM client with OAuth support |
| **`OAuthTokenManager`** | services/__init__.py | Token management |
| **`timed_lru_cache`** | services/__init__.py | Caching decorator |

### Summary

**AgentOrchestrator provides:**
- Pipeline orchestration (`@ao.step()`, `@ao.chain()`, `ao.launch()`)
- Agent framework (`BaseAgent`, `ResilientAgent`, `MCPAgent`)
- LLM integration (`LLMGatewayClient`)

**CMPT provides:**
- Domain logic (financial metrics extraction, strategic analysis)
- Prompts (LLM prompts for SWOT analysis, metrics)
- Models (Pydantic schemas for chain I/O)
- Agents (SEC, Earnings, News agent implementations)
