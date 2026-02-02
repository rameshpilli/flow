
# AgentOrchestrator - Presentation Guide

> A conversational guide for presenting the AgentOrchestrator framework.
> Estimated time: 35-45 minutes

---

## Opening (2 min)

### The Problem We Solved

"Before I show you what we built, let me explain the problem.

When you're building AI applications with LLMs, you quickly run into challenges:

1. **Coordination** - How do you run multiple LLM calls in the right order?
2. **Context explosion** - LLMs have token limits, but real data is huge
3. **Reliability** - API calls fail, retries cause duplicates
4. **Multi-agent chaos** - Multiple agents stepping on each other's data
5. **Quality assurance** - How do you ensure LLM outputs are actually good?

We built AgentOrchestrator to solve all of these."

---

## Section 1: The Core Idea (3 min)

### DAG-Based Execution

"At its heart, AgentOrchestrator uses a DAG - a Directed Acyclic Graph - to orchestrate work.

Think of it like a recipe:
- Some steps can happen in parallel (chopping vegetables while water boils)
- Some steps must wait (you can't serve before cooking)

Here's the simplest example:"

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")

@ao.step(name="fetch_data")
async def fetch_data(ctx):
    ctx.set("data", {"users": 100})
    return {"fetched": True}

@ao.step(name="process", deps=["fetch_data"])  # <-- This runs AFTER fetch_data
async def process(ctx):
    data = ctx.get("data")
    return {"processed": data["users"] * 2}

@ao.chain(name="pipeline")
class Pipeline:
    steps = ["fetch_data", "process"]

# Run it
result = await ao.launch("pipeline", {})
```

"That `deps=["fetch_data"]` is the key. It says 'wait for fetch_data before running me.'

The orchestrator automatically figures out:
- What can run in parallel
- What must run sequentially
- How to pass data between steps"

---

## Section 2: Why We Built It This Way (2 min)

### The Design Decisions

"We made three key design choices:

**1. Decorator-based** - No config files, no YAML. Just Python decorators.
- Why? Developers already know Python. No learning curve.

**2. Context as the data bus** - Steps don't call each other directly.
- Why? Loose coupling. You can swap steps without breaking others.

**3. Async-first** - Everything is async/await.
- Why? LLM calls are slow. You need parallelism."

---

## Section 3: Parallel Execution (3 min)

### The Power of DAGs

"Let me show you where this really shines - parallel execution."

```python
@ao.step(name="plan")
async def plan(ctx):
    question = ctx.get("question")
    ctx.set("query", question)
    return {"plan": "Research this topic"}

# These two steps have the SAME dependency
@ao.step(name="search_web", deps=["plan"])
async def search_web(ctx):
    return {"web_results": "..."}

@ao.step(name="search_docs", deps=["plan"])
async def search_docs(ctx):
    return {"doc_results": "..."}

# This waits for BOTH
@ao.step(name="synthesize", deps=["search_web", "search_docs"])
async def synthesize(ctx):
    web = ctx.get("web_results")
    docs = ctx.get("doc_results")
    return {"answer": f"Combined: {web} + {docs}"}
```

"What happens when you run this?

```
plan (1s)
    ↓
    ├── search_web (2s) ──┐
    │                     ├── synthesize (1s)
    └── search_docs (2s) ─┘

Total time: 4 seconds (not 6!)
```

The orchestrator sees that `search_web` and `search_docs` have no dependency on each other, so it runs them in parallel. You get this for free just by declaring your dependencies."

---

## Section 4: The Context System (3 min)

### How Data Flows

"Now let's talk about Context - the shared memory between steps."

```python
@ao.step(name="producer")
async def producer(ctx):
    # Store data
    ctx.set("user_data", {"name": "Alice", "score": 95})
    return {"produced": True}

@ao.step(name="consumer", deps=["producer"])
async def consumer(ctx):
    # Retrieve data
    user = ctx.get("user_data")
    return {"message": f"Hello, {user['name']}!"}
```

"Context has scopes for different lifetimes:

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| STEP | Single step | Temporary scratch data |
| CHAIN | Entire chain | Share between steps (default) |
| GLOBAL | Application | Configuration, constants |

This prevents memory leaks - step-scoped data is automatically cleaned up."

---

## Section 5: Type-Safe State with Pydantic (3 min)

### IDE Autocomplete for Your Pipeline State

"One thing that sets us apart - type-safe state management with Pydantic.

Instead of `ctx.get()` and `ctx.set()` with strings everywhere, you get full IDE autocomplete:"

```python
from pydantic import BaseModel, Field
from agentorchestrator.core.context import Context

class PipelineState(BaseModel):
    """Strongly-typed state for the pipeline."""
    counter: int = 0
    items: list[str] = Field(default_factory=list)
    company: str | None = None
    analysis_complete: bool = False

@ao.step(name="process", state_model=PipelineState)
async def process(ctx: Context[PipelineState]):
    # Type-safe access with IDE autocomplete!
    async with ctx.edit_state() as state:
        state.counter += 1
        state.items.append("new_item")

    # Read-only access
    print(ctx.state.counter)  # IDE knows this is an int!
    return {"count": ctx.state.counter}
```

"Why this matters:
- **Catch bugs at development time** - typos like `ctx.get('conuter')` become compile errors
- **IDE autocomplete** - your editor knows what fields exist
- **Self-documenting** - the state model IS the documentation
- **Validation** - Pydantic validates data types automatically"

---

## Section 6: Dataflow-Based Dependencies (2 min)

### Automatic Dependency Resolution

"There's an alternative to explicit `deps=[]` - dataflow-based dependencies.

Instead of saying 'this step runs after that step', you declare what data each step produces and consumes:"

```python
from agentorchestrator.core.decorators import produces, consumes

@produces("company_data")
@ao.step(name="fetch_company")
async def fetch_company(ctx):
    data = await api.get_company("AAPL")
    ctx.set("company_data", data)
    return data

# This step will AUTOMATICALLY depend on fetch_company
@consumes("company_data")
@produces("analysis")
@ao.step(name="analyze")
async def analyze(ctx):
    data = ctx.get("company_data")
    return {"analysis": analyze_data(data)}

# Enable dataflow resolution
@ao.chain(name="pipeline", dataflow=True)
class Pipeline:
    steps = ["fetch_company", "analyze"]
```

"The orchestrator sees that `analyze` consumes `company_data` and `fetch_company` produces it - so it automatically creates the dependency. This makes refactoring easier - you don't have to update deps everywhere."

---

## Section 7: Multi-Agent Systems (5 min)

### The Squad Pattern

"This is where it gets interesting. Real applications need multiple specialized agents.

We built the **Squad** pattern for this:"

```python
from agentorchestrator.squad import (
    Squad,
    SquadOptions,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)

# Create specialist agents
tech_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="TechExpert",
    description="Handles technical questions about software",
    system_prompt="You are a helpful technical assistant specializing in software development.",
))

finance_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="FinanceExpert",
    description="Handles questions about money and investments",
    system_prompt="You are a financial analyst assistant.",
))

# Create the supervisor (team lead) - REQUIRED
supervisor = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="TeamLead",
    description="Coordinates the team and delegates tasks",
    system_prompt="You coordinate a team of specialists. Analyze requests and delegate to the right expert.",
))

# Create a squad - supervisor coordinates the team
squad = Squad(
    supervisor=supervisor,  # Required: the lead agent
    agents=[tech_agent, finance_agent],
    options=SquadOptions(
        name="support_team",
        max_concurrent_agents=5,
    ),
)

# The squad runs - supervisor analyzes and delegates
result = await squad.run("How do I optimize my React app?")
print(result.content)  # Response from TechExpert, synthesized by supervisor
```

### Agent Handoffs

"Here's the key insight: agents can hand off to each other.

When TechExpert realizes a question is about 'tech stock prices', it can say 'this is actually a finance question' and hand off to FinanceExpert.

We handle this with the MultiAgentOrchestrator:"

```python
from agentorchestrator.squad import MultiAgentOrchestrator
from agentorchestrator.squad.classifiers import LLMGatewayClassifier

orchestrator = MultiAgentOrchestrator(
    agents=[tech_agent, finance_agent, general_agent],
    classifier=LLMGatewayClassifier(),  # Uses LLM to pick the right agent
    default_agent=general_agent,        # Fallback
)

# Process with automatic classification and handoff
response = await orchestrator.route_request(
    user_input="What tech stocks should I buy?",
    user_id="user-123",
)
```

"The classifier looks at the question, picks an agent, and if that agent says 'not my area', it can redirect. All automatic."

---

## Section 8: Context Isolation (3 min)

### The Pollution Problem

"When you have multiple agents, there's a problem: context pollution.

Agent A writes 'temperature: 72' (weather).
Agent B writes 'temperature: 350' (oven).
Now your data is corrupted.

We solve this with **namespaced isolation**:"

```python
from agentorchestrator.squad.context import ContextIsolationManager, IsolationLevel

# Create isolation manager
isolation = ContextIsolationManager(
    coordinator_context=ctx,
    default_level=IsolationLevel.FULL,  # Complete isolation
)

# Each agent gets its own namespace
for agent in [tech_agent, finance_agent]:
    namespace = isolation.create_namespace(agent.name)

    # Agent can only see/modify its own data
    namespace.set("temperature", 72)  # Isolated!

    # But can read shared data from coordinator
    shared_data = namespace.get("user_query")
```

"Three isolation levels:

| Level | What Agent Sees | Use Case |
|-------|-----------------|----------|
| NONE | Everything | Trusted agents sharing context |
| PARTIAL | Own writes + coordinator reads | Most common |
| FULL | Only own namespace | Untrusted or conflicting agents |

This is how you run 10 agents in parallel without them corrupting each other's data."

---

## Section 9: Handling Large Responses (4 min)

### The Token Problem

"LLMs have context limits. GPT-4 Turbo is 128K tokens. Sounds like a lot until:

- SEC filings: 500KB
- News articles: 200KB
- Earnings transcripts: 150KB
- **Total: 850KB = Way over the limit**

We built middleware to handle this automatically:"

```python
from agentorchestrator.middleware import (
    TokenManagerMiddleware,
    SummarizerMiddleware,
    OffloadMiddleware,
    RollingSummaryMiddleware,
)

# Layer 1: Track token budget
ao.use(TokenManagerMiddleware(
    budget=TokenBudget(
        context_window=128000,
        reserved_output=8000,    # Reserve for model response
        warning_threshold=0.8,   # Warn at 80%
    ),
))

# Layer 2: Summarize large outputs
ao.use(SummarizerMiddleware(
    max_tokens=4000,
    strategy=SummarizationStrategy.MAP_REDUCE,
))

# Layer 3: Offload huge data to Redis
ao.use(OffloadMiddleware(
    store=RedisContextStore(),
    threshold_bytes=100_000,
))
```

"How it works:

1. **TokenManager** tracks how much context you're using
2. When you hit 80%, it warns you
3. At 95%, it auto-triggers **Summarizer**
4. Summarizer compresses 50K tokens → 2K tokens (key facts preserved)
5. If data is still huge, **Offload** stores it in Redis, keeps a reference

All this happens automatically. Your step just does `ctx.set('data', huge_result)` and the middleware handles the rest."

### Rolling Summary - Incremental Compression

"For iterative data gathering (pagination, streaming), we have RollingSummaryMiddleware:"

```python
ao.use(RollingSummaryMiddleware(
    max_tokens=4000,
    recent_buffer_tokens=1000,  # Keep last 1000 tokens uncompressed
    summarizer=langchain_summarizer,
    applies_to=["gather_*"],  # Only for gather steps
))
```

"Instead of re-summarizing everything on each update:
- Iteration 1: 15K tokens → summarize → 2K tokens
- Iteration 2: +10K tokens → summarize NEW only → merge → 3K tokens
- Iteration 3: +8K tokens → summarize NEW only → merge → 3.5K tokens

Much more efficient than starting over each time."

---

## Section 10: Agent Self-Critique with Reflection (3 min)

### The "Think Twice" Pattern

"Here's a powerful feature: agents can critique and revise their own outputs.

This implements the common AI pattern of 'think twice' - generate, evaluate, improve:"

```python
from agentorchestrator.middleware.reflection import (
    ReflectionMiddleware,
    ReflectionConfig,
    reflect,
)

# Option 1: Apply middleware globally
ao.use(ReflectionMiddleware(
    config=ReflectionConfig(
        quality_threshold=0.8,   # Accept if quality >= 80%
        max_revisions=2,         # Max 2 revision attempts
    ),
))

# Option 2: Use @reflect decorator on specific steps
@ao.step(name="draft_report")
@reflect(
    critique_prompt="Review this report for accuracy, completeness, and clarity. Score 0-1.",
    quality_threshold=0.85,
    max_revisions=2,
)
async def draft_report(ctx):
    return {"report": generate_report(ctx.get("data"))}
```

"What happens:
1. Step generates initial output
2. LLM critiques the output, assigns quality score
3. If score < threshold, step revises based on critique
4. Repeat until quality meets threshold or max revisions reached
5. Return final output with full reflection trace

This dramatically improves output quality, especially for complex generation tasks."

---

## Section 11: Citation Tracking (2 min)

### Source Attribution for RAG

"When building RAG pipelines, you need to track where information came from. We built citation middleware for this:"

```python
from agentorchestrator.middleware.citation import (
    CitationMiddleware,
    cite,
    get_citation_report,
)

ao.use(CitationMiddleware(
    require_citations=True,
    validate_against_sources=True,
    min_coverage=0.8,  # 80% of claims must be cited
))

@ao.step(name="extract_revenue")
async def extract_revenue(ctx):
    # Use cite() helper for automatic tracking
    return cite(
        value=394.3,
        source_name="sec_filing_agent",
        content="Total net sales were $394,328 million",
        reasoning="Direct revenue figure from 10-K filing",
    )

# After execution, get citation report
result = await ao.launch("research_chain", {})
report = get_citation_report(ctx)
print(f"Citation coverage: {report['coverage_rate']:.1%}")
```

"This is essential for enterprise RAG - you can prove where every number came from."

---

## Section 12: Memory Lifecycle (2 min)

### Automatic Session → Long-Term Memory Promotion

"For conversational AI, you want to remember important things from sessions.

MemoryLifecycleMiddleware automatically promotes important session data to long-term memory:"

```python
from agentorchestrator.middleware.memory_lifecycle import (
    MemoryLifecycleMiddleware,
    MemoryLifecycleConfig,
    LLMImportanceEvaluator,
)

middleware = MemoryLifecycleMiddleware(
    session_storage=redis_storage,
    longterm_memory=mem0_memory,
    evaluator=LLMImportanceEvaluator(llm_client),  # LLM scores importance
    config=MemoryLifecycleConfig(
        importance_threshold=0.7,      # Promote if importance >= 70%
        auto_promote_patterns=True,    # Detect user preferences
        batch_size=10,                 # Batch promotions for efficiency
    ),
)

ao.use(middleware)
```

"Now when a step discovers 'user prefers technical explanations', the middleware:
1. Scores importance using LLM
2. If important enough, promotes to Mem0 long-term memory
3. Future sessions can retrieve this preference

No manual memory management required."

---

## Section 13: Reliability Features (3 min)

### Idempotency - No Duplicate Charges

"Here's a real problem: your payment step fails halfway through. You retry. Does the customer get charged twice?

With IdempotencyMiddleware, no:"

```python
from agentorchestrator.middleware.idempotency import IdempotencyMiddleware

ao.use(IdempotencyMiddleware(ttl_seconds=3600))

@ao.step(
    name="process_payment",
    idempotency_key=lambda ctx: f"payment:{ctx.get('order_id')}",
)
async def process_payment(ctx):
    # First call: runs payment, caches result
    # Retry: returns cached result, doesn't charge again
    return await payment_gateway.charge(ctx.get("amount"))
```

"The middleware hashes the inputs. Same inputs = return cached result. Different inputs = run again.

For production, we store in Redis so it works across multiple server instances."

### Rate Limiting & Circuit Breaker

"For external API calls, we provide resilience patterns:"

```python
from agentorchestrator.middleware import RateLimiterMiddleware
from agentorchestrator.utils.circuit_breaker import CircuitBreaker

# Rate limiting
ao.use(RateLimiterMiddleware(
    requests_per_second=10,
    burst_size=20,
))

# Circuit breaker for external APIs
@ao.step(name="call_external_api")
async def call_external_api(ctx):
    breaker = CircuitBreaker(
        failure_threshold=5,    # Open after 5 failures
        recovery_timeout=30,    # Try again after 30s
    )
    async with breaker:
        return await external_api.call(...)
```

### Resumable Chains

"Long-running chains can fail in the middle. You don't want to re-run completed steps:"

```python
# Start a resumable chain
result = await ao.launch_resumable("long_chain", {"data": "..."}, run_id="run-123")

# If it fails at step 5...
# Resume from where it left off
result = await ao.resume("run-123")
```

"The orchestrator checkpoints after each step. On resume, it skips completed steps and continues from the failure point."

---

## Section 14: The RAG Agent (2 min)

### Grounded Answers

"We also built a specialized RAG (Retrieval-Augmented Generation) agent:"

```python
from agentorchestrator.squad.agents.rag_agent import RAGAgent, RAGAgentOptions
from agentorchestrator.services.vector_store import VectorStoreConfig

agent = RAGAgent(RAGAgentOptions(
    name="knowledge_agent",
    description="Answers using company docs",
    vector_store_config=VectorStoreConfig(
        provider="chroma",           # or "pinecone", "qdrant"
        collection_name="company_docs",
    ),
    top_k=5,  # Retrieve top 5 relevant docs
    include_sources=True,  # Return source documents
))

response = await agent.process_request(
    input_text="What's our refund policy?",
    user_id="user-123",
)

print(response.content)
print(response.sources)  # List of source documents used
```

"Instead of hallucinating, it:
1. Searches your vector store for relevant documents
2. Injects them into the prompt
3. Generates an answer grounded in your actual data

You can combine this with Squad - route factual questions to RAG, general questions to a chat agent."

---

## Section 15: Event-Driven Workflows (2 min)

### Reactive Pipelines

"For complex workflows, we support event-driven patterns:"

```python
from agentorchestrator.core.event_bus import get_event_bus, Event

# Get event bus (Redis-backed in production, in-memory for dev)
bus = get_event_bus(prefer_redis=True)

# Publish events from steps
@ao.step(name="process_order")
async def process_order(ctx):
    result = await process(ctx.get("order"))

    # Publish event for downstream systems
    await bus.publish(Event(
        type="order_processed",
        payload={"order_id": result["id"], "status": "complete"},
    ))
    return result

# Subscribe to events
@bus.subscribe("order_processed")
async def on_order_processed(event: Event):
    await notify_customer(event.payload["order_id"])
    await update_inventory(event.payload)
```

"This enables loose coupling between chains - one chain can trigger another without direct dependencies."

---

## Section 16: Built-in Services & Connectors (4 min)

### Enterprise-Ready Integrations

"One thing I want to emphasize - we didn't just build an orchestration framework. We built **production-ready service connectors** that work out of the box in enterprise environments.

Here's what's included:"

### The Services Layer

```
agentorchestrator/services/
├── llm_gateway.py      # LLM Gateway with OAuth/API key auth
├── redis.py            # Redis for distributed state & caching
├── vector_store.py     # Vector DB abstraction (Chroma, Pinecone, Qdrant)
├── mem0.py             # Semantic long-term memory
├── secrets.py          # HashiCorp Vault integration
├── observability.py    # OpenTelemetry tracing
└── cohere_compass.py   # Cohere Compass integration
```

"Each of these is **pre-built and customized** for enterprise use. You don't write boilerplate - you just configure."

### How It Works - Just Pass Your Credentials

"Let me show you how simple this is. Take our LLM Gateway client:"

```python
from agentorchestrator.services import LLMGatewayClient

# Option 1: Environment variables (recommended for production)
# Set: LLM_SERVER_URL, LLM_OAUTH_ENDPOINT, LLM_CLIENT_ID, LLM_CLIENT_SECRET
client = LLMGatewayClient.from_env()

# Option 2: Direct configuration
client = LLMGatewayClient(
    server_url="https://llm-gateway.yourcompany.com/v1/chat/completions",
    oauth_endpoint="https://auth.yourcompany.com/oauth/token",
    client_id="your-app-id",
    client_secret="your-secret",
)

# That's it - now use it
response = await client.generate_async("Summarize this document...")

# Structured output with Pydantic
from pydantic import BaseModel

class Analysis(BaseModel):
    sentiment: str
    confidence: float
    key_points: list[str]

result = await client.generate_structured_async(
    prompt="Analyze this earnings call...",
    response_model=Analysis,
)
print(result.sentiment)  # Type-safe access!
```

"Notice what you **didn't** have to do:
- Write OAuth token refresh logic (we handle expiration)
- Implement retry with exponential backoff (built-in)
- Handle rate limiting (built-in)
- Set up connection pooling (automatic)

All you provide is your subscription credentials."

### Available Service Connectors

| Service | Class | What It Handles |
|---------|-------|-----------------|
| **LLM Gateway** | `LLMGatewayClient` | OAuth/API auth, token refresh, retries, structured output |
| **Redis** | `RedisService` | Connection pooling, pub/sub, distributed locks |
| **Vector Store** | `VectorStoreService` | Chroma, Pinecone, Qdrant - unified API |
| **Semantic Memory** | `Mem0Memory` | Long-term memory with embeddings |
| **Secrets** | `VaultSecretProvider` | HashiCorp Vault, env fallback |
| **Observability** | `ObservabilityService` | OpenTelemetry spans, metrics |
| **Cohere Compass** | `CohereCompassService` | Enterprise RAG retrieval |

### Configuration via Environment Variables

"For production, everything is driven by environment variables:"

```bash
# LLM Gateway
LLM_SERVER_URL=https://llm-gateway.yourcompany.com/v1/chat/completions
LLM_OAUTH_ENDPOINT=https://auth.yourcompany.com/oauth/token
LLM_CLIENT_ID=my-app
LLM_CLIENT_SECRET=secret

# Redis (for distributed context)
CONTEXT_STORE_BACKEND=redis
CONTEXT_STORE_REDIS_HOST=redis.internal
CONTEXT_STORE_REDIS_PORT=6379
CONTEXT_STORE_REDIS_PASSWORD=secure-password

# Semantic Memory
MEM0_API_KEY=your-key
MEM0_AGENT_ID=my-agent

# Vector Store
VECTOR_STORE_PROVIDER=pinecone
PINECONE_API_KEY=your-key
```

"Set these in your deployment, and the framework auto-configures everything."

### MCP Connectors (Model Context Protocol)

"We also support MCP - the Model Context Protocol - for external tool servers:"

```python
from agentorchestrator.connectors import MCPConnector

# Connect to an MCP tool server
connector = MCPConnector(
    base_url="http://tools.internal:8000",
    transport="http",  # or "stdio", "sse"
)

# List available tools
tools = await connector.list_tools()

# Call a tool
result = await connector.call_tool("search_documents", {"query": "quarterly report"})
```

"MCP lets you integrate any external tool server without writing custom code."

### What If Something Is Missing?

"Now, an important point about extensibility.

We've built connectors for the most common enterprise services. But if you need something we don't have:

1. **Check what's available** - Import from `agentorchestrator.services`:
   ```python
   from agentorchestrator.services import (
       LLMGatewayClient,
       RedisService,
       VectorStoreService,
       Mem0Memory,
       VaultSecretProvider,
   )
   ```

2. **If it's not there** - Work with our team. We'll prioritize it for the next release.

3. **Custom connectors** - You can extend `BaseConnector` for proprietary systems:
   ```python
   from agentorchestrator.connectors.base import BaseConnector

   class MyCustomConnector(BaseConnector):
       async def connect(self):
           # Your connection logic
           pass
   ```

We're actively developing this framework, so feature requests go into our roadmap for upcoming versions."

---

## Section 17: Developer Experience (3 min)

### CLI Tools

"We built a full CLI for development and debugging:"

```bash
# Run a chain
ao run my_chain --data '{"input": "test"}'

# Validate everything is wired correctly
ao check

# Visualize the DAG
ao graph my_chain
# Output:
#   plan
#     ├── search_web
#     └── search_docs
#           └── synthesize

# Health check
ao health --detailed

# Debug mode with context snapshots
ao debug my_chain --data '{}'

# Development mode with hot reload
ao dev --watch

# Diagnose common issues
ao doctor

# Scaffold new components
ao new agent MyAgent
ao new chain MyChain
ao new step my_step
```

"No more print statements. You can see exactly what's in context at each step."

---

## Section 18: Complete Middleware Reference (2 min)

### Available Middleware

"Here's the full middleware stack available:

| Middleware | Purpose | Priority |
|------------|---------|----------|
| `LoggerMiddleware` | Structured logging | 50 |
| `MetricsMiddleware` | Performance metrics | 50 |
| `TokenManagerMiddleware` | Token budget tracking | 25 |
| `SummarizerMiddleware` | Compress large outputs | 30 |
| `RollingSummaryMiddleware` | Incremental summarization | 30 |
| `OffloadMiddleware` | Store huge data in Redis | 35 |
| `IdempotencyMiddleware` | Prevent duplicate execution | 20 |
| `CacheMiddleware` | Response caching | 25 |
| `RateLimiterMiddleware` | Rate limiting | 15 |
| `ReflectionMiddleware` | Agent self-critique | 75 |
| `CitationMiddleware` | Source attribution | 70 |
| `MemoryLifecycleMiddleware` | Session → long-term promotion | 80 |
| `AnalyticsMiddleware` | Usage analytics | 90 |

Lower priority = runs earlier. You can customize:"

```python
ao.use(MyMiddleware(), priority=42)
```

---

## Closing (2 min)

### What We Built

"Let me summarize what AgentOrchestrator gives you:

| Problem | Our Solution |
|---------|--------------|
| Coordinating steps | DAG-based execution with automatic parallelization |
| Data sharing | Scoped context with automatic cleanup |
| Type safety | Pydantic state models with IDE autocomplete |
| Multi-agent chaos | Squad pattern with context isolation |
| Token limits | TokenManager + Summarizer + RollingSummary + Offload |
| Quality assurance | Reflection middleware for self-critique |
| Source tracking | Citation middleware for RAG pipelines |
| Memory management | Automatic session → long-term promotion |
| Duplicate operations | IdempotencyMiddleware |
| Long-running failures | Resumable chains with checkpoints |
| Rate limits / failures | Rate limiter + Circuit breaker |
| Need grounded answers | Built-in RAG agent |
| Debugging | CLI with visualization, diagnostics, and scaffolding |

### One Complete Example

Here's everything working together:"

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.squad import Squad, SquadOptions, LLMGatewayAgent, LLMGatewayAgentOptions
from agentorchestrator.middleware import (
    TokenManagerMiddleware,
    SummarizerMiddleware,
    IdempotencyMiddleware,
    LoggerMiddleware,
    ReflectionMiddleware,
    CitationMiddleware,
)
from pydantic import BaseModel

# Define typed state
class ResearchState(BaseModel):
    company: str = ""
    research_complete: bool = False
    citations: list[str] = []

# Create orchestrator
ao = AgentOrchestrator(name="research_app")

# Add middleware stack
ao.use(LoggerMiddleware())
ao.use(IdempotencyMiddleware())
ao.use(TokenManagerMiddleware(budget=TokenBudget(context_window=128000)))
ao.use(SummarizerMiddleware(max_tokens=4000))
ao.use(ReflectionMiddleware(config=ReflectionConfig(quality_threshold=0.8)))
ao.use(CitationMiddleware(require_citations=True))

# Define steps with typed state
@ao.step(name="gather_data", state_model=ResearchState)
async def gather_data(ctx):
    async with ctx.edit_state() as state:
        state.company = ctx.get("company")
    # Fetch SEC filings, news, earnings...
    ctx.set("research", huge_data)
    return {"gathered": True}

@ao.step(name="analyze", deps=["gather_data"], state_model=ResearchState)
@reflect(critique_prompt="Is this analysis thorough and accurate?")
async def analyze(ctx):
    research = ctx.get("research")  # Auto-summarized!
    async with ctx.edit_state() as state:
        state.research_complete = True
    return cite(
        value={"analysis": "..."},
        source_name="research",
        content="Based on gathered data...",
    )

# Create chain
@ao.chain(name="research_chain")
class ResearchChain:
    steps = ["gather_data", "analyze"]

# Run it
result = await ao.launch("research_chain", {"company": "AAPL"})
```

"Questions?"

---

## Appendix: Key Files Reference

| Component | Location |
|-----------|----------|
| Core orchestrator | `core/orchestrator.py` |
| Context management | `core/context.py` |
| DAG execution | `core/dag.py` |
| Decorators | `core/decorators.py` |
| Squad multi-agent | `squad/squad.py` |
| Multi-agent orchestrator | `squad/orchestrator.py` |
| Context isolation | `squad/context/isolation.py` |
| All middleware | `middleware/` |
| Services | `services/` |
| Connectors | `connectors/` |
| CLI | `cli.py` |
| Documentation | `docs/` |

---

## Q&A Preparation

**Q: How does this compare to LangChain?**
"LangChain is great for chaining LLM calls. We focus on orchestration - running steps in parallel, managing context size, coordinating multiple agents, type-safe state. They're complementary - we integrate with LangChain for summarization."

**Q: What about LangGraph?**
"Similar space, different approach. LangGraph uses a state machine model. We use DAGs with declarative dependencies. Both work; we find decorators more intuitive for most developers. We also have dataflow-based dependency resolution which LangGraph doesn't."

**Q: Production ready?**
"We're using it internally. Key production features: Redis-backed context for scale, idempotency for reliability, observability with OpenTelemetry, reflection for quality, memory lifecycle for conversational AI."

**Q: Performance?**
"The orchestrator overhead is minimal - microseconds. The real time is in LLM calls. Parallel execution typically saves 40-60% time vs sequential."

**Q: What about observability?**
"Full OpenTelemetry integration. Every step creates spans with timing, token counts, and custom attributes. Integrates with Jaeger, Datadog, New Relic - whatever you use."

**Q: How do you handle secrets?**
"VaultSecretProvider for HashiCorp Vault with automatic fallback to environment variables. Never hardcode secrets."

**Q: Can I use this with my existing agents?**
"Yes. Extend BaseAgent or wrap any async function. We don't force you into our agent model."

**Q: What's the learning curve?**
"If you know async Python and decorators, you can be productive in an hour. Start with `@ao.step` and `@ao.chain`, add middleware as you need it."
