# AgentOrchestrator - Presentation Guide

> A conversational guide for presenting the AgentOrchestrator framework.
> Estimated time: 20-30 minutes

---

## Opening (2 min)

### The Problem We Solved

"Before I show you what we built, let me explain the problem.

When you're building AI applications with LLMs, you quickly run into challenges:

1. **Coordination** - How do you run multiple LLM calls in the right order?
2. **Context explosion** - LLMs have token limits, but real data is huge
3. **Reliability** - API calls fail, retries cause duplicates
4. **Multi-agent chaos** - Multiple agents stepping on each other's data

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

## Section 5: Multi-Agent Systems (5 min)

### The Squad Pattern

"This is where it gets interesting. Real applications need multiple specialized agents.

We built the **Squad** pattern for this:"

```python
from agentorchestrator.squad import Squad, LLMGatewayAgent

# Create specialist agents
tech_agent = LLMGatewayAgent(
    name="TechExpert",
    description="Handles technical questions about software"
)

finance_agent = LLMGatewayAgent(
    name="FinanceExpert",
    description="Handles questions about money and investments"
)

# Create a squad with automatic routing
squad = Squad(
    name="support_team",
    agents=[tech_agent, finance_agent],
)

# The squad automatically routes to the right agent
response = await squad.process_request(
    input_text="How do I optimize my React app?",  # → TechExpert
    user_id="user-123",
)
```

### Agent Handoffs

"Here's the key insight: agents can hand off to each other.

When TechExpert realizes a question is about 'tech stock prices', it can say 'this is actually a finance question' and hand off to FinanceExpert.

We handle this with the MultiAgentOrchestrator:"

```python
from agentorchestrator.squad import MultiAgentOrchestrator

orchestrator = MultiAgentOrchestrator(
    agents=[tech_agent, finance_agent, general_agent],
    classifier=LLMGatewayClassifier(),  # Uses LLM to pick the right agent
    default_agent="general_agent",       # Fallback
)

# Process with automatic classification and handoff
response = await orchestrator.route_request(
    user_input="What tech stocks should I buy?",
    user_id="user-123",
)
```

"The classifier looks at the question, picks an agent, and if that agent says 'not my area', it can redirect. All automatic."

---

## Section 6: Context Isolation (3 min)

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

## Section 7: Handling Large Responses (4 min)

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

---

## Section 8: Reliability Features (3 min)

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

## Section 9: The RAG Agent (2 min)

### Grounded Answers

"We also built a specialized RAG (Retrieval-Augmented Generation) agent:"

```python
from agentorchestrator.squad.agents.rag_agent import RAGAgent, RAGAgentOptions

agent = RAGAgent(RAGAgentOptions(
    name="knowledge_agent",
    description="Answers using company docs",
    vector_store_config=VectorStoreConfig(
        provider="chroma",
        collection_name="company_docs",
    ),
    top_k=5,  # Retrieve top 5 relevant docs
))

response = await agent.process_request(
    input_text="What's our refund policy?",
    user_id="user-123",
)
```

"Instead of hallucinating, it:
1. Searches your vector store for relevant documents
2. Injects them into the prompt
3. Generates an answer grounded in your actual data

You can combine this with Squad - route factual questions to RAG, general questions to a chat agent."

---

## Section 10: Developer Experience (2 min)

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
```

"No more print statements. You can see exactly what's in context at each step."

---

## Closing (2 min)

### What We Built

"Let me summarize what AgentOrchestrator gives you:

| Problem | Our Solution |
|---------|--------------|
| Coordinating steps | DAG-based execution with automatic parallelization |
| Data sharing | Scoped context with automatic cleanup |
| Multi-agent chaos | Squad pattern with context isolation |
| Token limits | TokenManager + Summarizer + Offload middleware |
| Duplicate operations | IdempotencyMiddleware |
| Long-running failures | Resumable chains with checkpoints |
| Need grounded answers | Built-in RAG agent |
| Debugging | CLI with visualization and snapshots |

### One Complete Example

Here's everything working together:"

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.squad import Squad, LLMGatewayAgent
from agentorchestrator.middleware import (
    TokenManagerMiddleware,
    SummarizerMiddleware,
    IdempotencyMiddleware,
    LoggerMiddleware,
)

# Create orchestrator
ao = AgentOrchestrator(name="research_app")

# Add middleware stack
ao.use(LoggerMiddleware())
ao.use(IdempotencyMiddleware())
ao.use(TokenManagerMiddleware(budget=TokenBudget(context_window=128000)))
ao.use(SummarizerMiddleware(max_tokens=4000))

# Define steps
@ao.step(name="gather_data")
async def gather_data(ctx):
    company = ctx.get("company")
    # Fetch SEC filings, news, earnings...
    ctx.set("research", huge_data)
    return {"gathered": True}

@ao.step(name="analyze", deps=["gather_data"])
async def analyze(ctx):
    research = ctx.get("research")  # Auto-summarized!
    return {"analysis": "..."}

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
| Squad multi-agent | `squad/orchestrator.py` |
| Context isolation | `squad/context/isolation.py` |
| Middleware | `middleware/` |
| CLI | `cli.py` |
| Documentation | `docs/` |

---

## Q&A Preparation

**Q: How does this compare to LangChain?**
"LangChain is great for chaining LLM calls. We focus on orchestration - running steps in parallel, managing context size, coordinating multiple agents. They're complementary - we integrate with LangChain for summarization."

**Q: What about LangGraph?**
"Similar space, different approach. LangGraph uses a state machine model. We use DAGs with declarative dependencies. Both work; we find decorators more intuitive for most developers."

**Q: Production ready?**
"We're using it internally. Key production features: Redis-backed context for scale, idempotency for reliability, observability with OpenTelemetry."

**Q: Performance?**
"The orchestrator overhead is minimal - microseconds. The real time is in LLM calls. Parallel execution typically saves 40-60% time vs sequential."
