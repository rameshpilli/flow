# FlowForge / ChainServer – Quick Pitch

## What it is
- A Python DAG-based orchestration library (FlowForge) plus a packaged Client Meeting Prep Tool (CMPT) chain that you can run as-is or customize.
- Decorator-driven: register agents, steps, and chains; FlowForge handles dependency resolution, parallelism, retries, timeouts, and scoped context.
- Middleware and resources are first-class: logging, caching, token tracking, metrics/tracing, rate limiting, offload, and managed resources (DB/HTTP clients, LLMs).

## Why it matters
- Faster to build “chain servers” that stitch multiple agents/LLMs together without bespoke glue code.
- Resilient by default: retry/backoff, circuit breaker options, step-level timeouts, resumable runs with checkpoints.
- Observable: metrics middleware, tracing hooks, DAG graph/CLI, partial-output retrieval on failures.

## Core features
- **Agents:** plug in your own or use hardened helpers like `HTTPAdapterAgent` (auth, retry, circuit breaker, rate limiting) or wrap any agent with `ResilientAgent`.
- **Steps/Chains:** define steps with `@forge.step`, wire them into chains with `@forge.chain`; supports parallel execution, subchains, versioning hooks, and input/output contracts.
- **Middleware:** logging, cache, token manager, metrics, tracing, rate limiter, offload. Add/remove per forge instance.
- **Resources:** managed lifecycle for shared clients; inject into steps with `resources=["llm", "db", ...]`.
- **Resumability:** checkpoint runs, resume or retry failed steps, fetch partial outputs.
- **Visualization & CLI:** ASCII/Mermaid DAGs, `flowforge check`, `flowforge graph`, `flowforge run`, `flowforge runs`, `flowforge resume`.

## CMPT packaged chain (example service)
- Implements a Client Meeting Prep flow: context building, content prioritization, response building.
- Typed request/response models (`ChainRequest`, `ChainResponse`); runnable via Python or CLI.
- Swap in real agents/APIs or keep mock/demo mode.

### Quick run (CLI)
```bash
make install-dev
flowforge run cmpt_chain --data '{
  "request": {
    "corporate_company_name": "Apple Inc",
    "meeting_datetime": "2025-01-15T10:00:00Z"
  }
}'
```

### Quick run (Python)
```python
from flowforge.chains.cmpt import CMPTChain

chain = CMPTChain()
result = await chain.run(
    corporate_company_name="Apple Inc",
    meeting_datetime="2025-01-15T10:00:00Z",
)
print(result.prepared_content)
```

## Integration options
1) **Use CMPT out-of-the-box**: run the chain as a service/worker; feed meeting requests, get prepared content.  
2) **Bring your own agents**: replace SEC/news/earnings/transcripts with your APIs; wrap with `ResilientAgent` or implement via `HTTPAdapterAgent`.  
3) **Build new chains**: use FlowForge primitives to compose entirely different workflows; reuse middleware/resources.  
4) **Expose via API**: thin FastAPI/Flask wrapper that validates `ChainRequest`, calls `CMPTChain().run()`, returns `ChainResponse`.

## Architecture

### Internal Structure
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FlowForge Core                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         Middleware Pipeline                           │  │
│  │  Logger → Cache → TokenManager → Metrics → Tracing → RateLimiter     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐    │
│  │    Registries   │  │   DAG Executor  │  │    Resource Manager     │    │
│  │                 │  │                 │  │                         │    │
│  │ • AgentRegistry │  │ • Build graph   │  │ • HTTP clients (pooled) │    │
│  │ • StepRegistry  │  │ • Resolve deps  │  │ • LLM clients           │    │
│  │ • ChainRegistry │  │ • Parallel exec │  │ • DB connections        │    │
│  │                 │  │ • Semaphore     │  │ • Lifecycle management  │    │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘    │
│           │                    │                       │                    │
│           └────────────────────┼───────────────────────┘                    │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        Chain Context                                  │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │  │
│  │  │   GLOBAL    │  │    CHAIN    │  │    STEP     │  │  Metadata  │  │  │
│  │  │  (config)   │  │ (summaries) │  │ (temp data) │  │ (request_id│  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         Run Store (Checkpoints)                       │  │
│  │  • Save state after each step  • Resume failed runs  • Partial output│  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Execution Flow (CMPT Example)
```
Request                                                              Response
   │                                                                     ▲
   ▼                                                                     │
┌──────────────────────────────────────────────────────────────────────────┐
│                            CMPT Chain                                     │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐     ┌─────────────────────────────────────────┐    │
│  │ Context Builder │     │         Content Prioritization          │    │
│  │                 │     │                                         │    │
│  │ • Company info  │────▶│ • Analyze query intent                  │    │
│  │ • Temporal data │     │ • Score sources by relevance            │    │
│  │ • Personas      │     │ • Generate prioritized subqueries       │    │
│  └─────────────────┘     └─────────────────────────────────────────┘    │
│                                           │                              │
│                                           ▼                              │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      Response Builder                              │  │
│  │                                                                    │  │
│  │   ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌────────────┐         │  │
│  │   │   SEC   │  │  News   │  │ Earnings │  │Transcripts │  ← Parallel│
│  │   │  Agent  │  │  Agent  │  │  Agent   │  │   Agent    │         │  │
│  │   └────┬────┘  └────┬────┘  └────┬─────┘  └─────┬──────┘         │  │
│  │        │            │            │              │                 │  │
│  │        └────────────┴─────┬──────┴──────────────┘                 │  │
│  │                           ▼                                       │  │
│  │              ┌─────────────────────────┐                          │  │
│  │              │      LLM Synthesis      │                          │  │
│  │              │  • Extract metrics      │                          │  │
│  │              │  • Generate analysis    │                          │  │
│  │              │  • Build final content  │                          │  │
│  │              └─────────────────────────┘                          │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### User's Deployment View
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Your Service / Kubernetes                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Your API Layer                               │   │
│  │                    (FastAPI / Flask / gRPC)                          │   │
│  │                                                                      │   │
│  │   POST /meeting-prep  ──────┐                                        │   │
│  │   POST /custom-chain  ──────┤                                        │   │
│  │   GET  /health        ──────┤                                        │   │
│  └─────────────────────────────┼────────────────────────────────────────┘   │
│                                │                                            │
│                                ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     FlowForge (pip installed)                        │   │
│  │                                                                      │   │
│  │   from flowforge import FlowForge                                    │   │
│  │   from flowforge.chains import CMPTChain                             │   │
│  │                                                                      │   │
│  │   forge = FlowForge()                                                │   │
│  │   forge.use(LoggerMiddleware(), MetricsMiddleware())                 │   │
│  │                                                                      │   │
│  │   # Register your agents                                             │   │
│  │   @forge.agent(name="my_news_agent")                                 │   │
│  │   class MyNewsAgent: ...                                             │   │
│  │                                                                      │   │
│  │   result = await forge.launch("cmpt_chain", data)                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Your APIs   │  │  Your LLM    │  │    Redis     │  │  Your DBs    │   │
│  │  (SEC, News) │  │  (Gateway)   │  │  (Context)   │  │              │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Files at a glance
- `flowforge/core`: executor, DAG builder, context, registry, resources, resumable run store
- `flowforge/middleware`: logging, cache, token manager, metrics, tracing, rate limiter, offload
- `flowforge/agents` + `flowforge/plugins/http_adapter.py`: base agent contracts, resilient wrappers
- `flowforge/chains/cmpt.py`: packaged CMPT chain definition
- `flowforge/cli.py`: CLI for run/check/graph/resume/list
- `examples/`: quickstart and CMPT example usage

## Ops & observability
- Metrics middleware for step durations and success/fail counts.
- Tracing hooks (`flowforge/utils/tracing.py`) to emit spans per step/agent.
- Health checks and run history (`flowforge run`, `flowforge runs`, `flowforge resume`, partial outputs).
- Caching and rate limiting middleware for API friendliness.

## How to extend safely
- Add middleware early (metrics/tracing/rate limiting).
- Validate inputs with `input_model` on steps/chains to fail fast.
- Use resilient agents for any external API; prefer shared resources for clients/LLMs.
- Keep DAGs explicit and visualize (`flowforge graph`) before shipping.

## Testing
```python
from flowforge import IsolatedForge, MockAgent, create_test_context

# Isolated test environment
async with IsolatedForge() as forge:
    @forge.step(name="my_step")
    async def my_step(ctx):
        return {"result": "ok"}

    result = await forge.launch("my_chain", {})

# Mock agents for predictable responses
mock = MockAgent(name="news", responses={"Apple": {"articles": [...]}})
```

## Troubleshooting
```bash
flowforge doctor   # Diagnose dependencies, env vars, imports
flowforge health   # Quick health check
flowforge check    # Validate chain definitions
```

## Key files to know
| File | Purpose |
|------|---------|
| `flowforge/core/forge.py` | Main FlowForge class |
| `flowforge/core/dag.py` | DAG builder & executor |
| `flowforge/core/context.py` | Shared context with scopes |
| `flowforge/chains/cmpt.py` | CMPT chain implementation |
| `flowforge/agents/base.py` | Agent base classes |
| `flowforge/middleware/` | All middleware (cache, logger, etc.) |
| `examples/cmpt_chain_tutorial.ipynb` | Full walkthrough notebook |
