# Handling Large Agent Responses

> Practical guide to managing huge outputs from agents using middleware.
> Apply summarization, offloading, and token management selectively per step.

---

## The Problem

Agents often return massive amounts of data:

```
SEC Agent → 500KB of 10-K filings
News Agent → 200KB of articles
Earnings Agent → 150KB of transcripts
─────────────────────────────────────
Total: 850KB → Exceeds LLM context!
```

Without management, this causes:
- **LLM truncation**: Key information lost
- **Token explosion**: Expensive and slow
- **Memory issues**: Application crashes

---

## Quick Start: Per-Step Middleware

Apply middleware to specific steps that return large responses:

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware import (
    SummarizerMiddleware,
    OffloadMiddleware,
    TokenManagerMiddleware,
)
from agentorchestrator.core.context_store import RedisContextStore

ao = AgentOrchestrator(name="research_pipeline")

# Summarize only the heavy agent steps
ao.use(SummarizerMiddleware(
    max_tokens=4000,
    applies_to=["gather_sec", "gather_news", "gather_earnings"],  # Only these steps
))

# Offload only SEC filings (largest)
ao.use(OffloadMiddleware(
    store=RedisContextStore(),
    default_threshold_bytes=100_000,
    applies_to=["gather_sec"],  # Only this step
))
```

---

## Middleware Options for Large Responses

### 1. SummarizerMiddleware

**Purpose**: Compress large text outputs while preserving key information.

**When to Use**:
- Agent returns documents that need to be analyzed
- Next steps need content, but summarized
- Want to reduce token costs

**Configuration**:

```python
from agentorchestrator.middleware import SummarizerMiddleware
from agentorchestrator.middleware.summarizer import SummarizationStrategy

# Global summarization (all steps)
ao.use(SummarizerMiddleware(
    max_tokens=4000,           # Summarize outputs > 4000 tokens
    strategy=SummarizationStrategy.MAP_REDUCE,  # Best for large docs
))

# Per-step configuration
ao.use(SummarizerMiddleware(
    step_strategies={
        "gather_sec": SummarizationStrategy.REFINE,    # Quality over speed
        "gather_news": SummarizationStrategy.MAP_REDUCE,  # Speed over quality
        "gather_earnings": SummarizationStrategy.STUFF,  # Small docs
    },
    step_max_tokens={
        "gather_sec": 5000,      # Allow more tokens for filings
        "gather_news": 2000,     # Compress news heavily
        "gather_earnings": 3000, # Medium compression
    },
    applies_to=["gather_sec", "gather_news", "gather_earnings"],
))
```

**Strategies Comparison**:

| Strategy | Speed | Quality | Use When |
|----------|-------|---------|----------|
| `STUFF` | Fast | Good | Single doc < 4K tokens |
| `MAP_REDUCE` | Medium | Good | Large docs, parallelizable |
| `REFINE` | Slow | Best | Need coherent narrative |

### 2. OffloadMiddleware

**Purpose**: Store large payloads externally, keep lightweight references in context.

**When to Use**:
- Data too large for context, but needed later
- Want 100% data preservation
- Full retrieval needed downstream

**Configuration**:

```python
from agentorchestrator.middleware import OffloadMiddleware
from agentorchestrator.core.context_store import RedisContextStore

# Create store
store = RedisContextStore(
    host="localhost",
    port=6379,
    # Or from env: url=os.getenv("REDIS_URL")
)

# Offload large payloads
ao.use(OffloadMiddleware(
    store=store,
    default_threshold_bytes=100_000,  # 100KB global threshold
    step_thresholds={
        "gather_sec": 200_000,    # SEC can be larger
        "gather_news": 50_000,    # News should be smaller
    },
    ttl_seconds=3600,  # Expire after 1 hour
    applies_to=["gather_sec", "gather_news"],  # Only these steps
))
```

**Key Fields Extraction**:

Tell the middleware what metadata to preserve in the reference:

```python
from agentorchestrator.middleware.offload import OffloadMiddleware

middleware = OffloadMiddleware(store=store)

# Register custom extractor for SEC data
middleware.register_extractor("gather_sec", lambda data: {
    "count": len(data),
    "tickers": list(set(f.get("ticker") for f in data)),
    "filing_types": list(set(f.get("type") for f in data)),
})

# Register summary generator
middleware.register_generator("gather_sec", lambda data, fields: (
    f"{fields['count']} SEC filings from {len(fields['tickers'])} companies"
))

ao.use(middleware)
```

### 3. TokenManagerMiddleware

**Purpose**: Track total context tokens and auto-trigger compression.

**When to Use**:
- Managing overall token budget
- Want automatic compression when approaching limits
- Need usage metrics

**Configuration**:

```python
from agentorchestrator.middleware import TokenManagerMiddleware

ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,      # Total budget
    warning_threshold=0.8,         # Warn at 80%
    auto_summarize=True,           # Auto-summarize when over limit
    auto_offload=True,             # Auto-offload large payloads
    summarize_oldest_first=True,   # Compress oldest steps first
))
```

---

## Combining Middleware (Layered Approach)

The middleware stack processes in **priority order**. Use all three together:

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware import (
    LoggerMiddleware,
    TokenManagerMiddleware,
    SummarizerMiddleware,
    OffloadMiddleware,
)
from agentorchestrator.core.context_store import RedisContextStore

ao = AgentOrchestrator(name="production_pipeline")

# Layer 1: Logging (priority 10)
ao.use(LoggerMiddleware(level="INFO"))

# Layer 2: Token budget (priority 20)
# Tracks all tokens, triggers auto-actions
ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,
    warning_threshold=0.8,
    auto_summarize=True,
    auto_offload=True,
))

# Layer 3: Summarization (priority 50)
# Compresses large outputs
ao.use(SummarizerMiddleware(
    max_tokens=5000,
    step_strategies={
        "gather_sec": SummarizationStrategy.REFINE,
        "gather_news": SummarizationStrategy.MAP_REDUCE,
    },
    applies_to=["gather_sec", "gather_news", "gather_earnings"],
))

# Layer 4: Offloading (priority 60)
# Stores very large payloads externally
ao.use(OffloadMiddleware(
    store=RedisContextStore(),
    default_threshold_bytes=100_000,
    applies_to=["gather_sec"],
))
```

**Data Flow**:

```
Agent Output (500KB)
        │
        ▼
┌───────────────────┐
│ TokenManager      │ ← Tracks tokens, may trigger auto-actions
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Summarizer        │ ← Compresses to 5000 tokens (~20KB)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Offload           │ ← If still > 100KB, store in Redis
└───────────────────┘
        │
        ▼
   Context (small!)
```

---

## Per-Step Configuration Patterns

### Pattern 1: Heavy vs Light Steps

```python
# Heavy agents get full treatment
heavy_steps = ["gather_sec", "gather_news", "gather_earnings"]

ao.use(SummarizerMiddleware(
    max_tokens=3000,
    applies_to=heavy_steps,
))

ao.use(OffloadMiddleware(
    store=store,
    applies_to=heavy_steps,
))

# Light steps (extraction, formatting) skip middleware
# - extract_context
# - format_response
# - etc.
```

### Pattern 2: Different Strategies Per Data Type

```python
from agentorchestrator.middleware.summarizer import LangChainSummarizer

# Register domain-specific prompts
LangChainSummarizer.register_domain_prompts(
    domain="sec_filings",
    map_prompt="""Extract from this SEC filing:
- Revenue and key metrics
- Risk factors
- Forward guidance
- Material changes

FILING:
{text}

KEY DATA:""",
)

LangChainSummarizer.register_domain_prompts(
    domain="news",
    map_prompt="""Summarize this news, preserving:
- Companies and tickers mentioned
- Key events and dates
- Market sentiment

NEWS:
{text}

SUMMARY:""",
)

# Map steps to domains
ao.use(SummarizerMiddleware(
    step_content_types={
        "gather_sec": "sec_filings",
        "gather_news": "news",
        "gather_earnings": "news",  # Similar treatment
    },
    applies_to=["gather_sec", "gather_news", "gather_earnings"],
))
```

### Pattern 3: Conditional Processing

```python
@ao.step(name="gather_sec")
async def gather_sec(ctx):
    filings = await fetch_sec_filings(ctx.get("company"))

    # Only set if substantial data
    if filings and len(str(filings)) > 10000:
        ctx.set("sec_filings", filings)  # Will be summarized/offloaded
    else:
        ctx.set("sec_filings_small", filings)  # Skips middleware

    return {"filing_count": len(filings)}
```

---

## Retrieving Offloaded Data

When data is offloaded, it becomes a `ContextRef`:

```python
from agentorchestrator.core.context_store import is_context_ref

@ao.step(name="analyze_filings", deps=["gather_sec"])
async def analyze_filings(ctx):
    data = ctx.get("sec_filings")

    if is_context_ref(data):
        # Data was offloaded - use the summary for LLM
        summary = data.summary  # "45 SEC filings from 5 companies"
        key_fields = data.key_fields  # {"tickers": ["AAPL", "MSFT"], ...}

        # If full data needed, retrieve it
        store = ctx.get("_offload_store")  # Injected by middleware
        full_data = await store.retrieve(data)

        # Or process just the metadata
        return {"analysis": f"Analyzed {key_fields['count']} filings"}
    else:
        # Data is still in context
        return {"analysis": analyze_data(data)}
```

---

## Performance Trade-offs

### Summarization

| Setting | Performance | Quality | Cost |
|---------|-------------|---------|------|
| `STUFF` + 8K max | Fast | Good | Low |
| `MAP_REDUCE` + 4K max | Medium | Good | Medium |
| `REFINE` + 2K max | Slow | Best | High |

**Recommendation**: Use `MAP_REDUCE` for most cases. Use `REFINE` only when narrative coherence is critical.

### Offloading

| Threshold | Redis Load | Context Size | Retrieval Latency |
|-----------|------------|--------------|-------------------|
| 50KB | High | Small | More frequent |
| 100KB | Medium | Medium | Balanced |
| 200KB | Low | Larger | Less frequent |

**Recommendation**: Start with 100KB, adjust based on your retrieval patterns.

### Token Budget

| Budget | Throughput | Quality | Cost |
|--------|------------|---------|------|
| 50K tokens | High (more summarization) | Lower | Lower |
| 100K tokens | Medium | Good | Medium |
| 200K tokens | Lower (less compression) | Higher | Higher |

**Recommendation**: 100K is a good balance for most pipelines.

---

## Troubleshooting

### Problem: Summarization losing important data

**Symptoms**: Downstream steps missing key information

**Solutions**:
1. Use domain-specific prompts that preserve your key fields
2. Increase `max_tokens` for critical steps
3. Use `REFINE` strategy for better coherence
4. Add key fields to `preserve_fields` list

```python
ao.use(SummarizerMiddleware(
    max_tokens=6000,  # Increase token budget
    preserve_fields=["ticker", "revenue", "risk_factors"],
))
```

### Problem: Too many Redis calls

**Symptoms**: High latency, Redis connection issues

**Solutions**:
1. Increase offload threshold
2. Summarize before offloading
3. Use connection pooling

```python
ao.use(OffloadMiddleware(
    default_threshold_bytes=200_000,  # Higher threshold
    connection_pool_size=10,
))
```

### Problem: Token budget exceeded

**Symptoms**: Warning logs about token limits

**Solutions**:
1. Enable `auto_summarize` and `auto_offload`
2. Add more aggressive per-step summarization
3. Reduce the number of parallel agents

```python
ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,
    auto_summarize=True,
    auto_offload=True,
    aggressive_threshold=0.7,  # Start compressing at 70%
))
```

### Problem: Slow chain execution

**Symptoms**: Long execution times due to summarization

**Solutions**:
1. Use `MAP_REDUCE` strategy (parallelizable)
2. Reduce chunk sizes
3. Apply middleware only to necessary steps

```python
ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.MAP_REDUCE,
    chunk_size=2000,  # Smaller chunks, more parallel
    applies_to=["gather_sec"],  # Only where needed
))
```

---

## Complete Example: CMPT Chain

Here's how the Client Meeting Prep Tool (CMPT) chain handles large responses:

```python
from agentorchestrator import AgentOrchestrator, produces, consumes
from agentorchestrator.middleware import (
    LoggerMiddleware,
    TokenManagerMiddleware,
    SummarizerMiddleware,
    OffloadMiddleware,
    CircuitBreakerMiddleware,
)
from agentorchestrator.middleware.summarizer import SummarizationStrategy
from agentorchestrator.core.context_store import RedisContextStore

ao = AgentOrchestrator(name="cmpt")

# Heavy agent steps that return large responses
HEAVY_STEPS = ["context_builder", "content_prioritization"]

# Middleware stack
ao.use(LoggerMiddleware(level="INFO"))

ao.use(CircuitBreakerMiddleware(
    failure_threshold=3,
    recovery_timeout=30.0,
))

ao.use(TokenManagerMiddleware(
    max_total_tokens=150_000,
    warning_threshold=0.8,
    auto_summarize=True,
))

ao.use(SummarizerMiddleware(
    max_tokens=5000,
    strategy=SummarizationStrategy.MAP_REDUCE,
    step_strategies={
        "context_builder": SummarizationStrategy.REFINE,  # Quality for context
    },
    applies_to=HEAVY_STEPS,
))

ao.use(OffloadMiddleware(
    store=RedisContextStore(),
    default_threshold_bytes=100_000,
    applies_to=["context_builder"],  # Only the heaviest step
))

# Steps
@produces("context_output")
@ao.step(name="context_builder", retry=2)
async def context_builder_step(ctx):
    """Fetches company data, news, SEC filings - returns LARGE output."""
    service = ContextBuilderService()
    output = await service.execute(ctx.get("request"))
    ctx.set("context_output", output)  # Auto-summarized/offloaded
    return {"extracted": True}

@consumes("context_output")
@produces("prioritization_output")
@ao.step(name="content_prioritization", retry=2)
async def content_prioritization_step(ctx):
    """Prioritizes sources - may receive summarized/offloaded data."""
    context_output = ctx.get("context_output")

    # Works with both full data or ContextRef
    service = ContentPrioritizationService()
    output = await service.execute(context_output)
    ctx.set("prioritization_output", output)
    return {"prioritized": True}

@consumes("prioritization_output")
@produces("final_response")
@ao.step(name="response_builder", retry=2)
async def response_builder_step(ctx):
    """Builds final response - uses summarized data."""
    prioritization = ctx.get("prioritization_output")
    service = ResponseBuilderService()
    response = await service.execute(prioritization)
    ctx.set("final_response", response)
    return {"response": response}

@ao.chain(name="cmpt_chain", dataflow=True, error_handling="continue")
class CMPTChain:
    steps = ["context_builder", "content_prioritization", "response_builder"]
```

---

## Best Practices

1. **Apply middleware selectively** - Don't summarize/offload everything, only heavy steps
2. **Use domain prompts** - Generic summarization loses domain-specific details
3. **Layer middleware correctly** - TokenManager → Summarizer → Offload
4. **Test summary quality** - Verify downstream steps get what they need
5. **Monitor metrics** - Use `ao.get_middleware_metrics()` to tune thresholds
6. **Start conservative** - Begin with higher thresholds, reduce as needed

---

## Related Documentation

- [Context Management Guide](../CONTEXT_MANAGEMENT.md) - Full context management patterns
- [Summarization Pattern](summarization.md) - Deep dive on summarization strategies
- [Middleware API](../API.md#middleware) - Middleware class reference
- [Troubleshooting](../TROUBLESHOOTING.md) - General troubleshooting guide
