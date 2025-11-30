# CMPT - Client Meeting Prep Tool

A production-ready example chain for generating client meeting preparation materials.

## Quick Start

```bash
# Run the CMPT chain
python examples/cmpt/run.py --company "Apple Inc"

# With custom meeting date
python examples/cmpt/run.py --company "Microsoft" --meeting-date "2025-01-15"
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
├── README.md                     # This file
├── run.py                        # 👈 MAIN ENTRY POINT
├── __init__.py                   # Package exports
│
├── services/                     # Business logic (modular services)
│   ├── models.py                 # Pydantic data models
│   ├── context_builder.py        # Stage 1 implementation
│   ├── content_prioritization.py # Stage 2 implementation
│   ├── response_builder.py       # Stage 3 implementation
│   └── llm_gateway.py            # LLM client with OAuth support
│
├── standalone_example.py         # Self-contained reference (all-in-one)
└── 03_cmpt_tests.py              # Test examples
```

## Files Explained

| File | Purpose | When to Use |
|------|---------|-------------|
| `run.py` | Main entry point using services | **Start here** - Production use |
| `standalone_example.py` | Self-contained implementation | Learning/reference - All code in one file |
| `services/` | Modular business logic | Production - Maintainable, testable |

## Usage Options

### Option 1: Run from Command Line (Recommended)

```bash
python examples/cmpt/run.py --company "Apple Inc"
```

### Option 2: Import and Use Programmatically

```python
from examples.cmpt.run import create_cmpt_chain
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app", isolated=True)
create_cmpt_chain(ao)

result = await ao.launch("cmpt_chain", {
    "request": {
        "corporate_company_name": "Apple Inc",
        "meeting_datetime": "2025-01-15",
    }
})
```

### Option 3: Use Services Directly (Without AgentOrchestrator)

```python
from examples.cmpt.services import (
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

## Configuration

### Environment Variables

```bash
# LLM Gateway (required for response generation)
LLM_OAUTH_ENDPOINT=https://auth.example.com/oauth/token
LLM_CLIENT_ID=your-client-id
LLM_CLIENT_SECRET=your-client-secret
LLM_SERVER_URL=https://llm-gateway.example.com

# Optional: API keys for data agents
SEC_API_KEY=your-sec-api-key
NEWS_API_KEY=your-news-api-key
```

### Using Mock Mode (No API Keys)

The chain runs in mock mode by default when API keys are not configured:

```python
# Services detect missing keys and return mock data
result = await ao.launch("cmpt_chain", {"request": {...}})
# Returns structured mock data for testing
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

- [USER_GUIDE.md](../../agentorchestrator/docs/USER_GUIDE.md) - Full framework guide
- [API.md](../../agentorchestrator/docs/API.md) - API reference
- [CMPT_CHAIN.md](../../agentorchestrator/docs/CMPT_CHAIN.md) - Detailed CMPT documentation
