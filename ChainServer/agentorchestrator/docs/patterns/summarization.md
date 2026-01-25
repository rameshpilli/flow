# Summarization Pattern

Compress large agent outputs to fit within context windows while preserving key information.

## The Problem

Agents often return more data than can fit in the LLM context:

```
Agent returns 50,000 tokens of SEC filings
LLM context window is 8,000 tokens
Result: Truncation, lost data, or crashes
```

## The Solution

Summarization compresses outputs while preserving key information:

```
Input: 50,000 tokens of SEC filings
         │
         ▼
┌──────────────────────────┐
│  Summarization Pipeline  │
│                          │
│  Chunk → Map → Reduce    │
└──────────────────────────┘
         │
         ▼
Output: 2,000 tokens (key facts preserved)
```

## When to Use

| Scenario | Strategy |
|----------|----------|
| Single large document | STUFF or REFINE |
| Multiple documents | MAP_REDUCE |
| Streaming data | REFINE |
| Known structure | Custom prompts |

## Strategies

### STUFF (Simple)

Fit everything in one call. Best for small documents.

```python
from agentorchestrator.middleware import (
    SummarizerMiddleware,
    SummarizationStrategy,
)

ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.STUFF,
    max_tokens=2000,
))
```

### MAP_REDUCE (Parallel)

Split into chunks, summarize each, then combine. Best for large documents.

```python
ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.MAP_REDUCE,
    chunk_size=4000,
    max_tokens=2000,
))
```

```
Document (50k tokens)
         │
    ┌────┼────┬────┬────┐
    ▼    ▼    ▼    ▼    ▼
  Chunk Chunk Chunk Chunk Chunk  (MAP phase)
    │    │    │    │    │
    ▼    ▼    ▼    ▼    ▼
  Sum1  Sum2  Sum3  Sum4  Sum5
    │    │    │    │    │
    └────┴────┴────┴────┘
              │
              ▼
         Final Summary              (REDUCE phase)
```

### REFINE (Sequential)

Build summary iteratively. Best for maintaining coherence.

```python
ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.REFINE,
    chunk_size=4000,
    max_tokens=2000,
))
```

```
Chunk 1 → Summary 1
              │
              ▼
Chunk 2 + Summary 1 → Summary 2
                          │
                          ▼
Chunk 3 + Summary 2 → Summary 3
                          │
                          ▼
                    Final Summary
```

## Implementation

### Basic Middleware

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware import SummarizerMiddleware

ao = AgentOrchestrator(name="my_app")

ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.MAP_REDUCE,
    max_tokens=3000,
    threshold_tokens=5000,  # Only summarize if > 5000 tokens
))

@ao.step(name="gather_data")
async def gather_data(ctx):
    huge_response = await fetch_all_filings()
    ctx.set("filings", huge_response)  # Auto-summarized if > threshold
    return {"gathered": True}
```

### Domain-Specific Prompts

Register custom prompts for your domain:

```python
from agentorchestrator.summarizers import LangChainSummarizer

# Register domain prompts
LangChainSummarizer.register_domain_prompts(
    domain="financial_news",
    map_prompt="""Summarize this financial news, preserving:
- Company names and tickers
- Key financial figures
- Market impact statements
- Dates and deadlines

NEWS:
{text}

SUMMARY:""",
    reduce_prompt="""Create a unified summary from these news summaries.
Organize by: market impact, company actions, regulatory changes.

SUMMARIES:
{text}

FINAL SUMMARY:""",
)

# Use domain-specific summarization
summarizer = LangChainSummarizer(
    strategy=SummarizationStrategy.MAP_REDUCE,
    domain="financial_news",
)

ao.use(SummarizerMiddleware(summarizer=summarizer))
```

### Step-Specific Configuration

```python
ao.use(SummarizerMiddleware(
    step_strategies={
        "gather_news": SummarizationStrategy.MAP_REDUCE,
        "gather_sec": SummarizationStrategy.REFINE,
        "gather_earnings": SummarizationStrategy.STUFF,
    },
    step_max_tokens={
        "gather_news": 2000,
        "gather_sec": 3000,
        "gather_earnings": 1500,
    },
))
```

## Combining with Cap Per Source

Limit items before summarizing:

```python
from agentorchestrator.core.context import cap_items_with_metadata

@ao.step(name="gather_news")
async def gather_news(ctx):
    raw_articles = await fetch_news()  # 100 articles

    # Cap to 10 most recent
    capped = cap_items_with_metadata(
        items=raw_articles,
        max_items=10,
        sort_key=lambda x: x["published_at"],
        reverse=True,
    )

    ctx.set("news", capped["items"])  # Then summarized by middleware
    return {"gathered": capped["metadata"]}
```

## Full Example

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware import (
    SummarizerMiddleware,
    TokenManagerMiddleware,
    OffloadMiddleware,
)
from agentorchestrator.summarizers import LangChainSummarizer, SummarizationStrategy
from agentorchestrator.services import RedisContextStore

ao = AgentOrchestrator(name="research_pipeline")

# Layer 1: Token budget management
ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,
    warning_threshold=0.8,
))

# Layer 2: Summarization with domain prompts
LangChainSummarizer.register_domain_prompts(
    domain="sec_filings",
    map_prompt="Extract key facts from this SEC filing...",
    reduce_prompt="Combine these filing summaries...",
)

ao.use(SummarizerMiddleware(
    summarizer=LangChainSummarizer(domain="sec_filings"),
    step_strategies={
        "gather_sec": SummarizationStrategy.REFINE,
    },
))

# Layer 3: Offload very large data to Redis
ao.use(OffloadMiddleware(
    store=RedisContextStore(),
    threshold_bytes=500_000,
))

@ao.step(name="gather_sec")
async def gather_sec(ctx):
    filings = await fetch_sec_filings(ctx.get("company"))
    ctx.set("sec_filings", filings)  # Summarized then offloaded if huge
    return {"gathered": len(filings)}
```

## Metrics & Debugging

```python
# Access summarization metrics
metrics = ao.get_middleware_metrics("summarizer")
print(f"Total compressions: {metrics['compression_count']}")
print(f"Avg compression ratio: {metrics['avg_ratio']:.1%}")
print(f"Tokens saved: {metrics['tokens_saved']}")
```

## Best Practices

!!! tip "Set Appropriate Thresholds"
    Only summarize when necessary. Small data doesn't need compression.

!!! tip "Use Domain Prompts"
    Generic prompts lose domain-specific details. Customize for your use case.

!!! tip "Chain with Offloading"
    Summarize first, then offload to Redis for very large data.

!!! warning "Test Summary Quality"
    Verify summaries preserve the information your downstream steps need.

## Related Patterns

- [Context Isolation](context_isolation.md) - Each agent summarizes independently
- [Aggregation](aggregation.md) - Combine summarized results

## API Reference

::: agentorchestrator.middleware.SummarizerMiddleware
::: agentorchestrator.summarizers.LangChainSummarizer
::: agentorchestrator.summarizers.SummarizationStrategy
