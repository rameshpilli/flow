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

FlowForge is a general-purpose chain orchestration library. Here are complete, working examples you can adapt:

---

### 1. Multi-Model AI Router

Route queries to different LLMs based on complexity — use cheap/fast models for simple queries, powerful models for complex ones.

```python
from flowforge import FlowForge
from pydantic import BaseModel

forge = FlowForge(name="ai_router")

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Classify the query complexity
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="classify_complexity")
async def classify_complexity(ctx):
    query = ctx.get("query")

    # Simple heuristic (replace with your own classifier)
    complex_keywords = ["analyze", "compare", "explain why", "multi-step", "reasoning"]
    is_complex = any(kw in query.lower() for kw in complex_keywords)

    return {
        "complexity": "high" if is_complex else "low",
        "model": "gpt-4" if is_complex else "gpt-3.5-turbo",
        "max_tokens": 2000 if is_complex else 500,
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Route to appropriate model and get response
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="generate_response", deps=["classify_complexity"])
async def generate_response(ctx):
    model = ctx.get("model")
    max_tokens = ctx.get("max_tokens")
    query = ctx.get("query")

    # Get the LLM client (registered as resource)
    llm = forge.get_resource("llm_client")

    response = await llm.chat(
        model=model,
        messages=[{"role": "user", "content": query}],
        max_tokens=max_tokens,
    )

    return {
        "response": response.content,
        "model_used": model,
        "tokens_used": response.usage.total_tokens,
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Log usage for cost tracking
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="log_usage", deps=["generate_response"])
async def log_usage(ctx):
    return {
        "logged": True,
        "summary": {
            "query": ctx.get("query")[:50] + "...",
            "model": ctx.get("model_used"),
            "tokens": ctx.get("tokens_used"),
            "complexity": ctx.get("complexity"),
        }
    }

# ═══════════════════════════════════════════════════════════════════
# CHAIN: Wire it together
# ═══════════════════════════════════════════════════════════════════
@forge.chain(name="smart_router")
class SmartRouterChain:
    steps = ["classify_complexity", "generate_response", "log_usage"]

# ═══════════════════════════════════════════════════════════════════
# RUN IT
# ═══════════════════════════════════════════════════════════════════
async def main():
    # Register LLM client as a resource
    forge.register_resource("llm_client", lambda: YourLLMClient())

    result = await forge.launch("smart_router", {
        "query": "Explain the implications of quantum computing on cryptography"
    })

    print(f"Model used: {result['model_used']}")
    print(f"Response: {result['response']}")

# Run: python router.py
```

---

### 2. RAG Document Pipeline

Ingest documents, chunk, embed, index, and query — complete RAG pipeline.

```python
from flowforge import FlowForge, ResilientAgent
from pydantic import BaseModel
from typing import List

forge = FlowForge(name="rag_pipeline")

# ═══════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════
class Document(BaseModel):
    id: str
    content: str
    metadata: dict = {}

class Chunk(BaseModel):
    doc_id: str
    chunk_id: str
    text: str
    embedding: List[float] = []

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Ingest documents from source
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="ingest")
async def ingest(ctx):
    source = ctx.get("source")  # e.g., "s3://bucket/docs/"

    # Mock: In reality, fetch from S3/GCS/local
    documents = [
        Document(id="doc1", content="FlowForge is a DAG orchestration library..."),
        Document(id="doc2", content="Chains consist of steps with dependencies..."),
    ]

    return {"documents": [d.model_dump() for d in documents], "count": len(documents)}

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Parse documents (extract text from PDF/DOCX)
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="parse", deps=["ingest"])
async def parse(ctx):
    documents = ctx.get("documents")

    parsed = []
    for doc in documents:
        # Mock: In reality, use pypdf, python-docx, etc.
        parsed.append({
            **doc,
            "content": doc["content"],  # Already text in this example
            "parsed": True,
        })

    return {"documents": parsed}

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Chunk into smaller pieces
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="chunk", deps=["parse"])
async def chunk(ctx):
    documents = ctx.get("documents")
    chunk_size = ctx.get("chunk_size", 500)

    chunks = []
    for doc in documents:
        text = doc["content"]
        # Simple chunking (use tiktoken/langchain for production)
        for i in range(0, len(text), chunk_size):
            chunks.append(Chunk(
                doc_id=doc["id"],
                chunk_id=f"{doc['id']}_chunk_{i}",
                text=text[i:i + chunk_size],
            ).model_dump())

    return {"chunks": chunks, "chunk_count": len(chunks)}

# ═══════════════════════════════════════════════════════════════════
# STEP 4: Generate embeddings
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="embed", deps=["chunk"])
async def embed(ctx):
    chunks = ctx.get("chunks")
    embedder = forge.get_resource("embedder")

    for chunk in chunks:
        # Generate embedding for each chunk
        chunk["embedding"] = await embedder.embed(chunk["text"])

    return {"chunks": chunks}

# ═══════════════════════════════════════════════════════════════════
# STEP 5: Index in vector store
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="index", deps=["embed"])
async def index(ctx):
    chunks = ctx.get("chunks")
    vector_store = forge.get_resource("vector_store")

    # Upsert all chunks
    await vector_store.upsert(
        vectors=[
            {"id": c["chunk_id"], "values": c["embedding"], "metadata": {"text": c["text"]}}
            for c in chunks
        ]
    )

    return {"indexed": len(chunks), "status": "success"}

# ═══════════════════════════════════════════════════════════════════
# CHAIN: Indexing pipeline
# ═══════════════════════════════════════════════════════════════════
@forge.chain(name="index_pipeline")
class IndexPipeline:
    steps = ["ingest", "parse", "chunk", "embed", "index"]

# ═══════════════════════════════════════════════════════════════════
# QUERY CHAIN (separate chain for retrieval)
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="embed_query")
async def embed_query(ctx):
    query = ctx.get("query")
    embedder = forge.get_resource("embedder")
    embedding = await embedder.embed(query)
    return {"query_embedding": embedding}

@forge.step(name="retrieve", deps=["embed_query"])
async def retrieve(ctx):
    query_embedding = ctx.get("query_embedding")
    vector_store = forge.get_resource("vector_store")

    results = await vector_store.query(
        vector=query_embedding,
        top_k=5,
        include_metadata=True,
    )

    return {"retrieved_chunks": [r.metadata["text"] for r in results.matches]}

@forge.step(name="generate_answer", deps=["retrieve"])
async def generate_answer(ctx):
    query = ctx.get("query")
    chunks = ctx.get("retrieved_chunks")
    llm = forge.get_resource("llm_client")

    context = "\n\n".join(chunks)
    prompt = f"Based on the following context, answer the question.\n\nContext:\n{context}\n\nQuestion: {query}"

    response = await llm.chat(messages=[{"role": "user", "content": prompt}])

    return {"answer": response.content, "sources": chunks}

@forge.chain(name="query_pipeline")
class QueryPipeline:
    steps = ["embed_query", "retrieve", "generate_answer"]

# ═══════════════════════════════════════════════════════════════════
# RUN IT
# ═══════════════════════════════════════════════════════════════════
async def main():
    # Register resources
    forge.register_resource("embedder", lambda: OpenAIEmbedder())
    forge.register_resource("vector_store", lambda: PineconeClient())
    forge.register_resource("llm_client", lambda: OpenAIClient())

    # Index documents
    await forge.launch("index_pipeline", {"source": "s3://my-bucket/docs/"})

    # Query
    result = await forge.launch("query_pipeline", {
        "query": "How do I define dependencies between steps?"
    })
    print(f"Answer: {result['answer']}")
```

---

### 3. Customer Support Bot with Escalation

Classify tickets, auto-respond to simple ones, escalate complex/angry ones.

```python
from flowforge import FlowForge
from flowforge.middleware import LoggerMiddleware, MetricsMiddleware
from pydantic import BaseModel
from enum import Enum

forge = FlowForge(name="support_bot")
forge.use(LoggerMiddleware())
forge.use(MetricsMiddleware())

# ═══════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════
class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TicketClassification(BaseModel):
    category: str
    priority: Priority
    sentiment: str
    confidence: float

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Classify the support ticket
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="classify_ticket")
async def classify_ticket(ctx):
    ticket_text = ctx.get("ticket_text")
    customer_tier = ctx.get("customer_tier", "standard")

    llm = forge.get_resource("llm_client")

    response = await llm.chat(
        messages=[{
            "role": "system",
            "content": """Classify this support ticket. Return JSON:
            {"category": "billing|technical|account|general",
             "priority": "low|medium|high|urgent",
             "sentiment": "positive|neutral|negative|angry",
             "confidence": 0.0-1.0}"""
        }, {
            "role": "user",
            "content": ticket_text
        }],
        response_format={"type": "json_object"}
    )

    classification = TicketClassification.model_validate_json(response.content)

    # Boost priority for premium customers
    if customer_tier == "enterprise" and classification.priority == Priority.MEDIUM:
        classification.priority = Priority.HIGH

    return classification.model_dump()

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Decide routing based on classification
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="route_ticket", deps=["classify_ticket"])
async def route_ticket(ctx):
    priority = ctx.get("priority")
    sentiment = ctx.get("sentiment")
    category = ctx.get("category")

    # Escalate if high priority, angry, or low confidence
    needs_human = (
        priority in ["high", "urgent"] or
        sentiment == "angry" or
        ctx.get("confidence", 1.0) < 0.7
    )

    return {
        "route": "human" if needs_human else "auto",
        "queue": f"{category}_{'urgent' if priority == 'urgent' else 'normal'}",
        "reason": "High priority or negative sentiment" if needs_human else "Auto-response eligible"
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 3A: Auto-generate response (if eligible)
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="generate_auto_response", deps=["route_ticket"])
async def generate_auto_response(ctx):
    if ctx.get("route") == "human":
        return {"response": None, "auto_responded": False}

    ticket_text = ctx.get("ticket_text")
    category = ctx.get("category")

    llm = forge.get_resource("llm_client")
    kb = forge.get_resource("knowledge_base")

    # Get relevant KB articles
    relevant_docs = await kb.search(ticket_text, category=category, limit=3)

    response = await llm.chat(
        messages=[{
            "role": "system",
            "content": f"""You are a helpful support agent. Use these knowledge base articles:
            {relevant_docs}

            Be concise, friendly, and helpful. If you can't fully answer, say so."""
        }, {
            "role": "user",
            "content": ticket_text
        }]
    )

    return {
        "response": response.content,
        "auto_responded": True,
        "kb_articles_used": [d["id"] for d in relevant_docs]
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 3B: Create escalation ticket (if needed)
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="escalate_to_human", deps=["route_ticket"])
async def escalate_to_human(ctx):
    if ctx.get("route") != "human":
        return {"escalated": False}

    ticketing_system = forge.get_resource("ticketing_system")

    ticket_id = await ticketing_system.create_ticket(
        title=f"[{ctx.get('priority').upper()}] {ctx.get('category')} - Customer Support",
        body=ctx.get("ticket_text"),
        priority=ctx.get("priority"),
        queue=ctx.get("queue"),
        metadata={
            "sentiment": ctx.get("sentiment"),
            "classification_confidence": ctx.get("confidence"),
            "customer_id": ctx.get("customer_id"),
        }
    )

    return {
        "escalated": True,
        "ticket_id": ticket_id,
        "message": "Your request has been escalated to our support team. We'll respond within 2 hours."
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 4: Send response to customer
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="send_response", deps=["generate_auto_response", "escalate_to_human"])
async def send_response(ctx):
    email_client = forge.get_resource("email_client")
    customer_email = ctx.get("customer_email")

    if ctx.get("auto_responded"):
        message = ctx.get("response")
    else:
        message = ctx.get("message")  # Escalation message

    await email_client.send(
        to=customer_email,
        subject="Re: Your Support Request",
        body=message,
    )

    return {"sent": True, "response_type": "auto" if ctx.get("auto_responded") else "escalation"}

# ═══════════════════════════════════════════════════════════════════
# CHAIN
# ═══════════════════════════════════════════════════════════════════
@forge.chain(name="support_chain")
class SupportChain:
    steps = [
        "classify_ticket",
        "route_ticket",
        "generate_auto_response",
        "escalate_to_human",
        "send_response",
    ]

# ═══════════════════════════════════════════════════════════════════
# RUN IT
# ═══════════════════════════════════════════════════════════════════
async def main():
    result = await forge.launch("support_chain", {
        "ticket_text": "I've been charged twice for my subscription! This is unacceptable!",
        "customer_email": "customer@example.com",
        "customer_id": "cust_123",
        "customer_tier": "standard",
    })

    print(f"Route: {result['route']}")
    print(f"Response type: {result['response_type']}")
```

---

### 4. Code Review Bot

Fetch PR, run parallel checks (style, security, tests), generate AI review, post comments.

```python
from flowforge import FlowForge
from flowforge.agents import ResilientAgent, ResilienceConfig

forge = FlowForge(name="code_review_bot")

# ═══════════════════════════════════════════════════════════════════
# AGENTS (external services wrapped with resilience)
# ═══════════════════════════════════════════════════════════════════
@forge.agent(name="github_agent")
class GitHubAgent(ResilientAgent):
    def __init__(self):
        super().__init__(
            agent=GitHubAPIClient(),
            config=ResilienceConfig(timeout_ms=10000, retry_count=3)
        )

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Fetch PR diff from GitHub
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="fetch_pr")
async def fetch_pr(ctx):
    github = forge.get_agent("github_agent")
    pr_url = ctx.get("pr_url")

    pr_data = await github.fetch(f"/repos/{owner}/{repo}/pulls/{pr_number}")
    diff = await github.fetch(f"/repos/{owner}/{repo}/pulls/{pr_number}/files")

    return {
        "pr_title": pr_data["title"],
        "pr_body": pr_data["body"],
        "files_changed": [f["filename"] for f in diff],
        "diff": diff,
        "additions": sum(f["additions"] for f in diff),
        "deletions": sum(f["deletions"] for f in diff),
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 2A: Check code style (runs in parallel)
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="check_style", deps=["fetch_pr"])
async def check_style(ctx):
    diff = ctx.get("diff")

    issues = []
    for file in diff:
        if file["filename"].endswith(".py"):
            # Run ruff/flake8/black check
            result = await run_linter(file["patch"])
            issues.extend(result)

    return {
        "style_issues": issues,
        "style_passed": len(issues) == 0,
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 2B: Check security (runs in parallel)
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="check_security", deps=["fetch_pr"])
async def check_security(ctx):
    diff = ctx.get("diff")

    vulnerabilities = []
    for file in diff:
        # Run bandit/semgrep
        result = await run_security_scan(file["patch"])
        vulnerabilities.extend(result)

    return {
        "security_issues": vulnerabilities,
        "security_passed": len(vulnerabilities) == 0,
        "severity_counts": count_by_severity(vulnerabilities),
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 2C: Check test coverage (runs in parallel)
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="check_tests", deps=["fetch_pr"])
async def check_tests(ctx):
    files_changed = ctx.get("files_changed")

    # Check if tests exist for changed files
    missing_tests = []
    for file in files_changed:
        if file.endswith(".py") and not file.startswith("test_"):
            test_file = f"test_{file}"
            if not await test_exists(test_file):
                missing_tests.append(file)

    # Run tests and get coverage delta
    coverage_before = await get_coverage("main")
    coverage_after = await get_coverage("pr_branch")

    return {
        "missing_tests": missing_tests,
        "coverage_delta": coverage_after - coverage_before,
        "tests_passed": len(missing_tests) == 0 and (coverage_after - coverage_before) >= 0,
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Generate AI review summary
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="generate_review", deps=["check_style", "check_security", "check_tests"])
async def generate_review(ctx):
    llm = forge.get_resource("llm_client")

    review_context = {
        "pr_title": ctx.get("pr_title"),
        "files_changed": ctx.get("files_changed"),
        "additions": ctx.get("additions"),
        "deletions": ctx.get("deletions"),
        "style_issues": ctx.get("style_issues"),
        "security_issues": ctx.get("security_issues"),
        "coverage_delta": ctx.get("coverage_delta"),
    }

    response = await llm.chat(
        messages=[{
            "role": "system",
            "content": """You are a senior code reviewer. Generate a concise, actionable review.
            Structure: Summary → Critical Issues → Suggestions → Approval Status"""
        }, {
            "role": "user",
            "content": f"Review this PR:\n{json.dumps(review_context, indent=2)}"
        }]
    )

    # Determine if we should approve, request changes, or comment
    all_passed = (
        ctx.get("style_passed") and
        ctx.get("security_passed") and
        ctx.get("tests_passed")
    )

    return {
        "review_body": response.content,
        "action": "APPROVE" if all_passed else "REQUEST_CHANGES",
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 4: Post review to GitHub
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="post_review", deps=["generate_review"])
async def post_review(ctx):
    github = forge.get_agent("github_agent")

    await github.execute("post_review", {
        "pr_number": ctx.get("pr_number"),
        "body": ctx.get("review_body"),
        "event": ctx.get("action"),  # APPROVE, REQUEST_CHANGES, COMMENT
    })

    # Post inline comments for specific issues
    for issue in ctx.get("style_issues", []) + ctx.get("security_issues", []):
        await github.execute("post_comment", {
            "pr_number": ctx.get("pr_number"),
            "path": issue["file"],
            "line": issue["line"],
            "body": issue["message"],
        })

    return {"posted": True}

# ═══════════════════════════════════════════════════════════════════
# CHAIN: Run checks in parallel, then review
# ═══════════════════════════════════════════════════════════════════
@forge.chain(name="code_review")
class CodeReviewChain:
    steps = [
        "fetch_pr",
        "check_style",      # ─┐
        "check_security",   # ─┼─ These run in PARALLEL
        "check_tests",      # ─┘
        "generate_review",
        "post_review",
    ]
    parallel_groups = [
        ["check_style", "check_security", "check_tests"],
    ]

# ═══════════════════════════════════════════════════════════════════
# RUN IT (webhook handler)
# ═══════════════════════════════════════════════════════════════════
async def handle_pr_webhook(payload: dict):
    result = await forge.launch("code_review", {
        "pr_url": payload["pull_request"]["url"],
        "pr_number": payload["pull_request"]["number"],
        "owner": payload["repository"]["owner"]["login"],
        "repo": payload["repository"]["name"],
    })

    return {"status": "reviewed", "action": result["action"]}
```

---

### 5. ETL Pipeline with Validation & Resumability

Extract from source, transform with validation, load to destination — resumable on failure.

```python
from flowforge import FlowForge
from flowforge.core import FileRunStore, ResumableChainRunner
from pydantic import BaseModel, validator
from typing import List

forge = FlowForge(name="etl_pipeline")

# ═══════════════════════════════════════════════════════════════════
# MODELS with validation
# ═══════════════════════════════════════════════════════════════════
class RawRecord(BaseModel):
    id: str
    data: dict

class CleanRecord(BaseModel):
    id: str
    name: str
    email: str
    amount: float

    @validator("email")
    def validate_email(cls, v):
        if "@" not in v:
            raise ValueError("Invalid email")
        return v

    @validator("amount")
    def validate_amount(cls, v):
        if v < 0:
            raise ValueError("Amount cannot be negative")
        return v

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Extract from source
# ═══════════════════════════════════════════════════════════════════
@forge.step(
    name="extract",
    output_model=List[RawRecord],  # Validates output
)
async def extract(ctx):
    source = ctx.get("source")
    db = forge.get_resource("source_db")

    # Fetch all records (or paginate for large datasets)
    records = await db.query(f"SELECT * FROM {source}")

    return {
        "raw_records": [RawRecord(id=r["id"], data=r).model_dump() for r in records],
        "record_count": len(records),
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Transform and validate
# ═══════════════════════════════════════════════════════════════════
@forge.step(
    name="transform",
    deps=["extract"],
)
async def transform(ctx):
    raw_records = ctx.get("raw_records")

    clean_records = []
    errors = []

    for raw in raw_records:
        try:
            clean = CleanRecord(
                id=raw["id"],
                name=raw["data"]["name"],
                email=raw["data"]["email"],
                amount=float(raw["data"]["amount"]),
            )
            clean_records.append(clean.model_dump())
        except Exception as e:
            errors.append({"id": raw["id"], "error": str(e)})

    return {
        "clean_records": clean_records,
        "transform_errors": errors,
        "success_rate": len(clean_records) / len(raw_records) if raw_records else 0,
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Load to destination
# ═══════════════════════════════════════════════════════════════════
@forge.step(
    name="load",
    deps=["transform"],
    retry=3,  # Retry on failure
    timeout_ms=60000,  # 60 second timeout
)
async def load(ctx):
    clean_records = ctx.get("clean_records")
    dest_db = forge.get_resource("dest_db")

    # Batch insert
    inserted = 0
    batch_size = 100

    for i in range(0, len(clean_records), batch_size):
        batch = clean_records[i:i + batch_size]
        await dest_db.insert_many("clean_data", batch)
        inserted += len(batch)

        # Checkpoint progress (resumable if this step fails)
        ctx.set("inserted_so_far", inserted)

    return {
        "inserted": inserted,
        "destination": "clean_data",
    }

# ═══════════════════════════════════════════════════════════════════
# STEP 4: Generate report
# ═══════════════════════════════════════════════════════════════════
@forge.step(name="report", deps=["load"])
async def report(ctx):
    return {
        "summary": {
            "source_records": ctx.get("record_count"),
            "transformed": len(ctx.get("clean_records")),
            "errors": len(ctx.get("transform_errors")),
            "loaded": ctx.get("inserted"),
            "success_rate": ctx.get("success_rate"),
        },
        "errors": ctx.get("transform_errors"),
    }

# ═══════════════════════════════════════════════════════════════════
# CHAIN
# ═══════════════════════════════════════════════════════════════════
@forge.chain(name="etl")
class ETLChain:
    steps = ["extract", "transform", "load", "report"]
    error_handling = "fail_fast"  # Stop on first error

# ═══════════════════════════════════════════════════════════════════
# RUN IT (with resumability)
# ═══════════════════════════════════════════════════════════════════
async def main():
    # Use file-based run store for persistence
    store = FileRunStore("./etl_checkpoints")
    runner = ResumableChainRunner(forge, store=store)

    try:
        result = await runner.run("etl", {
            "source": "raw_customers",
        })
        print(f"ETL complete: {result['summary']}")

    except Exception as e:
        print(f"ETL failed: {e}")

        # Get the run ID from the error
        run_id = runner.last_run_id

        # Later, resume from where it failed
        result = await runner.resume(run_id)
        print(f"Resumed ETL complete: {result['summary']}")

# Or use CLI:
# flowforge run etl --resumable --data '{"source": "raw_customers"}'
# flowforge resume <run_id>  # If it fails
```

---

### 6. Multi-Tenant SaaS Workflow

Isolated execution per tenant with tenant-specific agents and rate limits.

```python
from flowforge import FlowForge, IsolatedForge
from flowforge.middleware import RateLimiterMiddleware, LoggerMiddleware

# ═══════════════════════════════════════════════════════════════════
# TENANT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
TENANT_CONFIGS = {
    "tenant_free": {
        "rate_limit": 10,  # requests per minute
        "max_tokens": 1000,
        "models": ["gpt-3.5-turbo"],
    },
    "tenant_pro": {
        "rate_limit": 100,
        "max_tokens": 4000,
        "models": ["gpt-3.5-turbo", "gpt-4"],
    },
    "tenant_enterprise": {
        "rate_limit": 1000,
        "max_tokens": 8000,
        "models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
    },
}

# ═══════════════════════════════════════════════════════════════════
# TENANT-AWARE REQUEST HANDLER
# ═══════════════════════════════════════════════════════════════════
async def handle_tenant_request(tenant_id: str, request: dict):
    """
    Each tenant gets:
    - Isolated registries (no cross-contamination)
    - Tenant-specific rate limits
    - Tenant-specific model access
    """
    config = TENANT_CONFIGS.get(tenant_id, TENANT_CONFIGS["tenant_free"])

    # Create isolated forge for this tenant
    async with IsolatedForge(name=f"forge_{tenant_id}") as forge:

        # Apply tenant-specific middleware
        forge.use(LoggerMiddleware(prefix=f"[{tenant_id}]"))
        forge.use(RateLimiterMiddleware({
            "generate": {"requests_per_second": config["rate_limit"] / 60}
        }))

        # Register tenant-specific steps
        @forge.step(name="validate_request")
        async def validate_request(ctx):
            model = ctx.get("model", "gpt-3.5-turbo")
            if model not in config["models"]:
                raise ValueError(f"Model {model} not available for your plan")

            if ctx.get("max_tokens", 0) > config["max_tokens"]:
                raise ValueError(f"Max tokens exceeds plan limit of {config['max_tokens']}")

            return {"validated": True, "model": model}

        @forge.step(name="generate", deps=["validate_request"])
        async def generate(ctx):
            llm = get_llm_client()  # Shared client, but rate-limited per tenant

            response = await llm.chat(
                model=ctx.get("model"),
                messages=ctx.get("messages"),
                max_tokens=min(ctx.get("max_tokens", 500), config["max_tokens"]),
            )

            return {"response": response.content}

        @forge.step(name="log_usage", deps=["generate"])
        async def log_usage(ctx):
            # Log to tenant-specific usage table
            await log_to_db(tenant_id, {
                "tokens": ctx.get("tokens_used"),
                "model": ctx.get("model"),
                "timestamp": datetime.now(),
            })
            return {"logged": True}

        @forge.chain(name="tenant_workflow")
        class TenantWorkflow:
            steps = ["validate_request", "generate", "log_usage"]

        # Run the workflow
        return await forge.launch("tenant_workflow", request)

# ═══════════════════════════════════════════════════════════════════
# API ENDPOINT
# ═══════════════════════════════════════════════════════════════════
from fastapi import FastAPI, Header

app = FastAPI()

@app.post("/generate")
async def generate(
    request: dict,
    x_tenant_id: str = Header(...),
):
    result = await handle_tenant_request(x_tenant_id, request)
    return {"response": result["response"]}
```

---

### Quick Reference: Pattern → FlowForge Features

| Pattern | Example | Key Features |
|---------|---------|--------------|
| **Router** | Multi-model AI | Conditional logic in steps, resource injection |
| **Pipeline** | RAG, ETL | `deps`, input/output contracts, sequential flow |
| **Fan-out/Fan-in** | Code review | `parallel_groups`, multiple agents |
| **Saga** | Support bot | `error_handling="continue"`, compensating actions |
| **Multi-tenant** | SaaS | `IsolatedForge`, per-tenant middleware |
| **Resumable** | ETL | `FileRunStore`, `ResumableChainRunner`, `flowforge resume` |

---

### The FlowForge Advantage

| Without FlowForge | With FlowForge |
|-------------------|----------------|
| 50+ lines of retry/backoff code | `@forge.step(retry=3, backoff=2.0)` |
| Manual asyncio.gather orchestration | `parallel_groups=[["a", "b", "c"]]` |
| Custom error handling per service | `error_handling="continue"` / `"fail_fast"` |
| No visibility into partial failures | `flowforge runs --status failed` |
| Re-run entire pipeline on crash | `flowforge resume <run_id>` |
| Scattered logging across services | `LoggerMiddleware` + `MetricsMiddleware` |
| Per-service rate limiting | `RateLimiterMiddleware` with per-step config |
| Hardcoded client initialization | `forge.register_resource()` + DI |
| Manual test isolation | `IsolatedForge` context manager |

---

**Bottom line**: FlowForge handles the orchestration plumbing — retries, parallelism, context, logging, resumability — so you focus on your business logic.
