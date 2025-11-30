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

---

## Go Crazy: What You Can Build

FlowForge is a general-purpose chain orchestration library. Here's what you can build beyond CMPT:

### 1. Multi-Model AI Pipeline
Route queries to different LLMs based on complexity, cost, or capability:
```python
@forge.step(name="classify_query")
async def classify(ctx):
    query = ctx.get("query")
    # Simple queries → fast/cheap model, complex → powerful model
    return {"model": "gpt-4" if is_complex(query) else "gpt-3.5-turbo"}

@forge.step(name="route_to_model", deps=["classify_query"])
async def route(ctx):
    model = ctx.get("model")
    llm = ctx.get_resource(f"llm_{model}")
    return await llm.complete(ctx.get("query"))
```

### 2. Document Processing Pipeline
```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Ingest  │───▶│  Parse   │───▶│  Chunk   │───▶│  Embed   │
│  (S3/GCS)│    │(PDF/DOCX)│    │ (tokens) │    │(vectors) │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                      │
┌──────────┐    ┌──────────┐    ┌──────────┐         │
│  Answer  │◀───│ Retrieve │◀───│  Index   │◀────────┘
│  (LLM)   │    │ (top-k)  │    │(Pinecone)│
└──────────┘    └──────────┘    └──────────┘
```
```python
@forge.chain(name="doc_pipeline")
class DocPipeline:
    steps = ["ingest", "parse", "chunk", "embed", "index"]
    parallel_groups = [["chunk", "embed"]]  # These can overlap
```

### 3. Real-Time Trading Signal Generator
```python
@forge.agent(name="market_data")
class MarketDataAgent(ResilientAgent):
    # Circuit breaker prevents hammering failing exchange APIs
    pass

@forge.chain(name="trading_signals", error_handling="continue")
class TradingChain:
    steps = [
        "fetch_prices",      # Market data
        "fetch_sentiment",   # News/social sentiment
        "fetch_fundamentals",# SEC filings
        "generate_signals",  # ML model
        "validate_risk",     # Risk checks
        "publish_signals",   # Push to execution
    ]
```

### 4. Customer Support Automation
```python
@forge.step(name="classify_ticket")
async def classify(ctx):
    return {"category": "billing", "priority": "high", "sentiment": "angry"}

@forge.step(name="route_ticket", deps=["classify_ticket"])
async def route(ctx):
    if ctx.get("priority") == "high":
        return {"action": "escalate_human"}
    return {"action": "auto_respond"}

@forge.step(name="generate_response", deps=["route_ticket"])
async def respond(ctx):
    if ctx.get("action") == "auto_respond":
        return await llm.generate_support_response(ctx)
    return {"response": None, "escalated": True}
```

### 5. Code Review Bot
```python
@forge.chain(name="code_review")
class CodeReviewChain:
    steps = [
        "fetch_diff",           # GitHub PR diff
        "parse_changes",        # AST analysis
        "check_style",          # Linting
        "check_security",       # SAST scan
        "check_tests",          # Coverage delta
        "generate_review",      # LLM summary
        "post_comments",        # GitHub API
    ]
    parallel_groups = [
        ["check_style", "check_security", "check_tests"],  # Run in parallel
    ]
```

### 6. ETL with Validation
```python
@forge.step(name="extract", input_model=ExtractRequest, output_model=RawData)
async def extract(ctx): ...

@forge.step(name="transform", deps=["extract"], output_model=CleanData)
async def transform(ctx):
    # If this fails, chain stops (fail-fast with contracts)
    ...

@forge.step(name="load", deps=["transform"])
async def load(ctx):
    # Resumable: if load fails, resume from here (not re-extract)
    ...
```

### 7. Multi-Tenant SaaS Workflows
```python
# Each tenant gets isolated registries
async def handle_request(tenant_id: str, request: dict):
    async with IsolatedForge() as forge:
        # Load tenant-specific agents
        load_tenant_agents(forge, tenant_id)

        # Run with tenant's rate limits
        forge.use(RateLimiterMiddleware(get_tenant_limits(tenant_id)))

        return await forge.launch("workflow", request)
```

### 8. Agentic Loop (ReAct Pattern)
```python
@forge.step(name="think")
async def think(ctx):
    return await llm.generate_thought(ctx.get("observation"))

@forge.step(name="act", deps=["think"])
async def act(ctx):
    action = ctx.get("thought")["action"]
    tool = ctx.get_agent(action["tool"])
    return await tool.execute(action["input"])

@forge.step(name="observe", deps=["act"])
async def observe(ctx):
    result = ctx.get("action_result")
    if is_final(result):
        return {"done": True, "answer": result}
    ctx.set("observation", result)
    return {"done": False}

# Loop until done (via chain composition)
@forge.chain(name="react_loop")
class ReactLoop:
    steps = ["think", "act", "observe"]
    loop_until = lambda ctx: ctx.get("done", False)  # Custom loop condition
```

### 9. Batch Processing with Progress
```python
@forge.step(name="process_batch")
async def process_batch(ctx):
    items = ctx.get("items")
    results = []

    for i, item in enumerate(items):
        result = await process_one(item)
        results.append(result)

        # Checkpoint after each item (resumable on failure)
        ctx.checkpoint({"processed": i + 1, "results": results})

    return {"results": results}
```

### 10. A/B Testing LLM Prompts
```python
@forge.step(name="ab_test_prompt")
async def ab_test(ctx):
    variant = random.choice(["A", "B"])
    prompt = PROMPTS[variant]

    result = await llm.complete(prompt.format(**ctx.get("inputs")))

    # Track for analysis
    ctx.set("variant", variant, scope=ContextScope.CHAIN)
    metrics.record("prompt_variant", variant)

    return {"response": result, "variant": variant}
```

### Mix & Match Patterns

| Pattern | Use Case | Key Features Used |
|---------|----------|-------------------|
| Fan-out/Fan-in | Query multiple sources, merge | `parallel_groups`, agents |
| Pipeline | Sequential processing | `deps`, input/output contracts |
| Router | Dynamic step selection | Conditional logic in steps |
| Saga | Distributed transactions | `error_handling="continue"`, compensating steps |
| Retry Loop | Iterative refinement | Chain composition, `loop_until` |
| Batch | Process large datasets | Checkpointing, resumability |
| Multi-tenant | SaaS isolation | `IsolatedForge`, per-tenant middleware |

### The FlowForge Advantage

| Without FlowForge | With FlowForge |
|-------------------|----------------|
| Manual retry/backoff code | `@forge.step(retry=3, backoff=2.0)` |
| Custom parallel execution | `parallel_groups=[["a", "b", "c"]]` |
| Ad-hoc error handling | `error_handling="continue"` / `"fail_fast"` |
| No visibility into failures | `flowforge runs --status failed` |
| Start from scratch on crash | `flowforge resume <run_id>` |
| Scattered logging | `LoggerMiddleware` + `MetricsMiddleware` |
| No rate limiting | `RateLimiterMiddleware` per-step |
| Hardcoded dependencies | `resources=["llm", "db"]` injection |

---

**Bottom line**: If you're stitching together APIs, LLMs, databases, or any async operations with dependencies — FlowForge gives you the plumbing for free so you can focus on the logic.
