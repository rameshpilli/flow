# Build a CMP-like Flow in 30 Minutes

This guide walks you through building a Client Meeting Prep (CMP) style flow using FlowForge. By the end, you'll have a working chain that:

1. Extracts context from meeting requests
2. Prioritizes data sources
3. Fetches data from multiple agents in parallel
4. Builds a comprehensive response

## Prerequisites

- Python 3.11+
- FlowForge installed (`pip install flowforge`)
- Redis running locally (optional, for context store)

## Step 1: Create a New Project (2 minutes)

```bash
# Create new project
flowforge new project meeting_prep

# Navigate to project
cd meeting_prep

# Install dependencies
pip install -e ".[dev]"

# Verify setup
flowforge check
```

## Step 2: Define Your Data Models (5 minutes)

Create `src/meeting_prep/models/request.py`:

```python
"""Request and response models for Meeting Prep chain."""

from datetime import datetime
from pydantic import BaseModel, Field


class MeetingRequest(BaseModel):
    """Input request for meeting preparation."""

    company_name: str = Field(..., description="Company name for the meeting")
    meeting_date: datetime = Field(default_factory=datetime.utcnow)
    attendees: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class CompanyContext(BaseModel):
    """Extracted company context."""

    company_name: str
    ticker: str | None = None
    sector: str | None = None
    market_cap: float | None = None


class PrioritizedSources(BaseModel):
    """Prioritized data sources."""

    primary_sources: list[str]
    secondary_sources: list[str]
    lookback_days: int = 30


class MeetingBrief(BaseModel):
    """Final meeting brief output."""

    company: CompanyContext
    key_points: list[str]
    recent_news: list[dict]
    financial_highlights: dict
    talking_points: list[str]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
```

## Step 3: Create Custom Agents (10 minutes)

Create `src/meeting_prep/agents/company_agent.py`:

```python
"""Company data agent."""

from flowforge.agents.base import BaseAgent, AgentResult
from flowforge.plugins.capability import CapabilitySchema, AgentCapability, CapabilityParameter


class CompanyAgent(BaseAgent):
    """Agent for fetching company information."""

    _flowforge_name = "company_agent"
    _flowforge_version = "1.0.0"

    CAPABILITIES = CapabilitySchema(
        name="company_agent",
        version="1.0.0",
        description="Fetches company information",
        capabilities=[
            AgentCapability(
                name="lookup",
                description="Look up company by name",
                parameters=[
                    CapabilityParameter(name="company_name", type="string", required=True),
                ],
            ),
        ],
    )

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch company information."""
        import time
        start = time.perf_counter()

        # In production, this would call a real API
        data = {
            "company_name": query,
            "ticker": "AAPL" if "apple" in query.lower() else "UNKNOWN",
            "sector": "Technology",
            "market_cap": 3000000000000,
        }

        duration = (time.perf_counter() - start) * 1000

        return AgentResult(
            data=data,
            source=self._flowforge_name,
            query=query,
            duration_ms=duration,
        )
```

Create `src/meeting_prep/agents/news_agent.py`:

```python
"""News agent using HTTP adapter."""

from flowforge.plugins.http_adapter import HTTPAdapterAgent, HTTPAdapterConfig


def create_news_agent():
    """Create a news agent using HTTP adapter."""

    config = HTTPAdapterConfig(
        base_url="https://newsapi.org/v2",
        auth_type="api_key",
        auth_token="YOUR_API_KEY",  # Set via env var
        api_key_header="X-Api-Key",
        timeout_seconds=10.0,
        max_retries=3,
    )

    agent = HTTPAdapterAgent(config)
    agent._flowforge_name = "news_agent"

    return agent
```

## Step 4: Build the Chain Steps (10 minutes)

Create `src/meeting_prep/chains/meeting_prep_chain.py`:

```python
"""Meeting Prep Chain - Full implementation."""

from flowforge import FlowForge, ChainContext, get_forge
from flowforge.utils.tracing import trace_span

from meeting_prep.models.request import (
    MeetingRequest,
    CompanyContext,
    PrioritizedSources,
    MeetingBrief,
)
from meeting_prep.agents.company_agent import CompanyAgent

# Get global forge instance
forge = get_forge()

# Register agents
forge.register_agent("company_agent", CompanyAgent)


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 1: Context Extraction
# ═══════════════════════════════════════════════════════════════════════════════

@forge.step(
    name="extract_context",
    produces=["company_context"],
    description="Extracts company context from meeting request",
    timeout_ms=10000,
)
async def extract_context(ctx: ChainContext):
    """Extract company and meeting context."""

    with trace_span("step.extract_context"):
        # Get request from context
        request_data = ctx.get("request", {})
        request = MeetingRequest(**request_data) if isinstance(request_data, dict) else request_data

        # Fetch company info
        company_agent = forge.get_agent("company_agent")
        result = await company_agent.fetch(request.company_name)

        if result.success:
            context = CompanyContext(**result.data)
        else:
            context = CompanyContext(company_name=request.company_name)

        ctx.set("company_context", context.model_dump())

        return context.model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 2: Source Prioritization
# ═══════════════════════════════════════════════════════════════════════════════

@forge.step(
    name="prioritize_sources",
    deps=[extract_context],
    produces=["prioritized_sources"],
    description="Prioritizes data sources based on context",
    timeout_ms=5000,
)
async def prioritize_sources(ctx: ChainContext):
    """Determine which data sources to query."""

    with trace_span("step.prioritize_sources"):
        company_context = ctx.get("company_context", {})

        # Simple prioritization logic
        primary = ["news", "financials"]
        secondary = ["sec_filings", "analyst_reports"]

        # Adjust based on sector
        if company_context.get("sector") == "Technology":
            primary.append("product_launches")

        sources = PrioritizedSources(
            primary_sources=primary,
            secondary_sources=secondary,
            lookback_days=30,
        )

        ctx.set("prioritized_sources", sources.model_dump())

        return sources.model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 3: Parallel Data Fetching
# ═══════════════════════════════════════════════════════════════════════════════

@forge.step(
    name="fetch_news",
    deps=[prioritize_sources],
    produces=["news_data"],
    description="Fetches recent news articles",
    timeout_ms=15000,
)
async def fetch_news(ctx: ChainContext):
    """Fetch news data in parallel with other sources."""

    company_context = ctx.get("company_context", {})
    company_name = company_context.get("company_name", "Unknown")

    # Simulated news fetch (replace with real API)
    news_data = [
        {
            "title": f"Latest update on {company_name}",
            "date": "2025-01-15",
            "source": "Financial Times",
            "sentiment": 0.7,
        },
    ]

    ctx.set("news_data", news_data)
    return {"articles": news_data, "count": len(news_data)}


@forge.step(
    name="fetch_financials",
    deps=[prioritize_sources],
    produces=["financial_data"],
    description="Fetches financial data",
    timeout_ms=15000,
)
async def fetch_financials(ctx: ChainContext):
    """Fetch financial data in parallel with news."""

    company_context = ctx.get("company_context", {})

    # Simulated financial data
    financial_data = {
        "revenue": 394.3e9,
        "net_income": 97.0e9,
        "eps": 6.13,
        "pe_ratio": 28.5,
    }

    ctx.set("financial_data", financial_data)
    return financial_data


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 4: Build Response
# ═══════════════════════════════════════════════════════════════════════════════

@forge.step(
    name="build_brief",
    deps=[fetch_news, fetch_financials],
    produces=["meeting_brief"],
    description="Builds the final meeting brief",
    timeout_ms=10000,
)
async def build_brief(ctx: ChainContext):
    """Combine all data into final meeting brief."""

    with trace_span("step.build_brief"):
        company_context = ctx.get("company_context", {})
        news_data = ctx.get("news_data", [])
        financial_data = ctx.get("financial_data", {})

        # Build brief
        brief = MeetingBrief(
            company=CompanyContext(**company_context),
            key_points=[
                f"Market cap: ${company_context.get('market_cap', 0) / 1e9:.1f}B",
                f"Sector: {company_context.get('sector', 'Unknown')}",
            ],
            recent_news=news_data,
            financial_highlights=financial_data,
            talking_points=[
                "Recent financial performance",
                "Market position and competition",
                "Growth opportunities",
            ],
        )

        ctx.set("meeting_brief", brief.model_dump())

        return brief.model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
#                         CHAIN DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════

@forge.chain(
    name="meeting_prep_chain",
    description="Prepares briefing materials for client meetings",
    version="1.0.0",
)
class MeetingPrepChain:
    """Meeting Prep Chain."""

    steps = [
        extract_context,
        prioritize_sources,
        fetch_news,
        fetch_financials,
        build_brief,
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#                         CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def run(company_name: str, **kwargs) -> dict:
    """Run the meeting prep chain."""

    request = MeetingRequest(company_name=company_name, **kwargs)

    return await forge.launch_resumable(
        "meeting_prep_chain",
        {"request": request.model_dump()},
    )


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run("Apple Inc"))
    print(result)
```

## Step 5: Test Your Chain (3 minutes)

```bash
# Validate the chain
flowforge validate meeting_prep_chain

# Run with sample data
flowforge run meeting_prep_chain --data '{"request": {"company_name": "Apple Inc"}}'

# Visualize the DAG
flowforge graph meeting_prep_chain --format mermaid
```

Expected DAG:

```
extract_context
       ↓
prioritize_sources
       ↓
   ┌───┴───┐
   ↓       ↓
fetch_news fetch_financials
   ↓       ↓
   └───┬───┘
       ↓
  build_brief
```

## Step 6: Add API Server (Optional)

Your project already has an API server in `src/meeting_prep/api.py`. Start it:

```bash
pip install -e ".[api]"
uvicorn meeting_prep.api:app --reload --port 8000
```

Test endpoints:

```bash
# Health check
curl http://localhost:8000/health

# Run chain
curl -X POST http://localhost:8000/run/meeting_prep_chain \
  -H "Content-Type: application/json" \
  -d '{"data": {"request": {"company_name": "Apple Inc"}}}'

# Check run status
curl http://localhost:8000/runs/{run_id}

# Get partial outputs
curl http://localhost:8000/runs/{run_id}/output
```

## Next Steps

1. **Add resilience**: Wrap agents with `ResilientAgent` for timeout/retry/circuit-breaker
2. **Add caching**: Use `CacheMiddleware` to cache expensive API calls
3. **Add tracing**: Enable OpenTelemetry for observability
4. **Deploy**: Use the included Dockerfile and docker-compose.yml

## Common Patterns

### Parallel Data Fetching

Steps with the same dependencies run in parallel:

```python
@forge.step(deps=[prioritize_sources])
async def fetch_news(ctx): ...

@forge.step(deps=[prioritize_sources])
async def fetch_financials(ctx): ...

# Both run in parallel after prioritize_sources completes
```

### Resumable Chains

```python
# Run with checkpointing
result = await forge.launch_resumable("my_chain", data)
run_id = result["run_id"]

# If failed, resume from checkpoint
result = await forge.resume(run_id)

# Get partial outputs
partial = await forge.get_partial_output(run_id)
```

### Input Validation

```python
from pydantic import BaseModel

class MyInput(BaseModel):
    company_name: str
    limit: int = 10

@forge.step(input_model=MyInput, input_key="request")
async def my_step(ctx):
    # Input is validated before step runs
    ...
```

## Troubleshooting

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for common issues and solutions.
