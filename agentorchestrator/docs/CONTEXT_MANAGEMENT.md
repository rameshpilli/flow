# Context Management Guide

> Comprehensive guide to managing LLM context windows in multi-agent systems.
> Prevent token overflow, optimize costs, and scale to 10+ agents.

---

## Overview

When building multi-agent systems, context management becomes critical:
- **Single agent**: 100K tokens might be enough
- **5 agents**: 5 × 100K = 500K tokens (expensive, slow)
- **10 agents**: Context explosion breaks everything

AgentOrchestrator provides a **layered approach** to context management:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Context Management Layers                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Layer 1: Source-Level Capping                                              │
│  └─ cap_per_source, cap_items_with_metadata                                │
│  └─ Fast, no LLM calls, preserves metadata about omissions                 │
│                                                                              │
│  Layer 2: Summarization                                                     │
│  └─ SummarizerMiddleware with MAP_REDUCE, REFINE, STUFF strategies        │
│  └─ LLM-powered compression with domain-specific prompts                   │
│                                                                              │
│  Layer 3: Offloading                                                        │
│  └─ OffloadMiddleware stores large payloads in Redis                       │
│  └─ 100% data preservation with lightweight ContextRefs                    │
│                                                                              │
│  Layer 4: Token Budget Management                                           │
│  └─ TokenManagerMiddleware tracks total tokens                             │
│  └─ Auto-triggers summarization or offloading at thresholds               │
│                                                                              │
│  Layer 5: Context Isolation                                                 │
│  └─ Each agent gets isolated namespace                                     │
│  └─ Coordinator mediates sharing, aggregator synthesizes                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference

| Pattern | When to Use | Implementation |
|---------|-------------|----------------|
| **Cap Per Source** | Many items from multiple sources | `cap_per_source()` |
| **Summarization** | Large text that needs compression | `SummarizerMiddleware` |
| **Offloading** | Large payloads you might need later | `OffloadMiddleware` |
| **Token Budget** | Overall context limit management | `TokenManagerMiddleware` |
| **Context Isolation** | 5+ agents, prevent pollution | `ContextIsolationManager` |
| **Type-Safe State** | Workflow progress, counters, flags | `Context[StateModel]` + Pydantic |

---

## 0. Type-Safe State Management (NEW)

**Purpose**: Type-safe, validated state management using Pydantic models for workflow progress, counters, and structured data.

### Why Use Type-Safe State?

Traditional context storage is untyped and flexible:

```python
ctx.set("counter", 0)
ctx.set("items", [])
count = ctx.get("counter")  # No type hints, no validation
```

**Problems**:
- No IDE autocomplete
- No type checking
- No validation
- Easy to introduce bugs

**Solution**: Pydantic state models provide:
- ✅ Type hints and IDE autocomplete
- ✅ Automatic validation
- ✅ Atomic updates via context manager
- ✅ Thread-safe concurrent access
- ✅ Clean separation of state from context data

### Basic Usage

```python
from pydantic import BaseModel, Field
from agentorchestrator import AgentOrchestrator, Context

class PipelineState(BaseModel):
    counter: int = Field(default=0)
    items: list[str] = Field(default_factory=list)
    processed: bool = Field(default=False)

ao = AgentOrchestrator()

@ao.step(name="process", state_model=PipelineState)
async def process(ctx: Context[PipelineState]):
    # Type-safe access with IDE autocomplete!
    async with ctx.edit_state() as state:
        state.counter += 1  # ← IDE knows this is an int
        state.items.append("new_item")  # ← IDE knows this is a list
    
    # Read-only access
    count = ctx.state.counter  # ← Typed!
    return {"count": count}
```

### Creating Context with State Model

```python
from agentorchestrator.core.context import ChainContext

# Create context with state model
ctx = ChainContext("req_123", state_model=PipelineState)

# Access state
print(ctx.state.counter)  # 0

# Update state atomically
async with ctx.edit_state() as state:
    state.counter = 10
    state.processed = True
```

### Atomic Updates

State updates are atomic and validated:

```python
async with ctx.edit_state() as state:
    state.counter += 1
    state.items.append("item1")
    # If an exception occurs here, ALL changes are rolled back
    # Validation happens on exit
```

### Validation with Pydantic

Add validation rules to your state model:

```python
from pydantic import BaseModel, Field, ValidationError

class ValidatedState(BaseModel):
    progress: int = Field(default=0, ge=0, le=100)  # 0-100
    email: str = Field(
        default="user@example.com",
        pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$"
    )
    retries: int = Field(default=0, ge=0, le=3)  # Max 3 retries

# Invalid updates raise ValidationError
try:
    async with ctx.edit_state() as state:
        state.progress = 150  # Exceeds max!
except ValidationError as e:
    print("Validation failed:", e)
    # State is unchanged
```

### State vs Context Data

**When to use State**:
- Workflow progress tracking
- Counters and flags
- Structured data with validation
- Data that needs type safety

**When to use Context**:
- Input data (user queries, parameters)
- Extracted entities (company names, dates)
- Step outputs (API responses, results)
- Flexible, unstructured data

**Example**:

```python
from agentorchestrator.core.context import ChainContext, ContextScope

class WorkflowState(BaseModel):
    stage: str = Field(default="init")
    progress: int = Field(default=0)

ctx = ChainContext(
    "req_123",
    initial_data={
        "user_query": "What is the revenue?",  # ← Context data
        "company": "Apple Inc",  # ← Context data
    },
    state_model=WorkflowState,  # ← State model
)

# Context data (untyped, flexible)
query = ctx.get("user_query")

# State (typed, validated)
async with ctx.edit_state() as state:
    state.stage = "processing"
    state.progress = 50

# Step-scoped data (temporary)
async with ctx.step_scope("process"):
    ctx.set("temp", {...}, scope=ContextScope.STEP)
    # Auto-cleaned after step
```

### Thread-Safe Concurrent Updates

State updates are automatically serialized for thread safety:

```python
async def worker(worker_id: int):
    async with ctx.edit_state() as state:
        state.counter += 1
        await asyncio.sleep(0.01)  # Simulate work

# Run 10 workers concurrently
await asyncio.gather(*[worker(i) for i in range(10)])

# Counter will be exactly 10 (no race conditions!)
assert ctx.state.counter == 10
```

### Complete Example

```python
from pydantic import BaseModel, Field
from agentorchestrator import AgentOrchestrator, Context
from agentorchestrator.core.context import ChainContext

class DataPipelineState(BaseModel):
    items_processed: int = Field(default=0)
    items: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    completed: bool = Field(default=False)

ao = AgentOrchestrator()

@ao.step(name="fetch", state_model=DataPipelineState)
async def fetch_data(ctx: Context[DataPipelineState]):
    raw_items = ["item1", "item2", "item3"]
    async with ctx.edit_state() as state:
        state.items = raw_items
    return {"fetched": len(raw_items)}

@ao.step(name="process", deps=["fetch"], state_model=DataPipelineState)
async def process_items(ctx: Context[DataPipelineState]):
    for item in ctx.state.items:  # Read-only access
        try:
            # Process item
            async with ctx.edit_state() as state:
                state.items_processed += 1
        except Exception as e:
            async with ctx.edit_state() as state:
                state.errors.append(str(e))
    return {"processed": ctx.state.items_processed}

@ao.step(name="finalize", deps=["process"], state_model=DataPipelineState)
async def finalize(ctx: Context[DataPipelineState]):
    async with ctx.edit_state() as state:
        state.completed = True
    return {
        "success": ctx.state.items_processed > 0,
        "processed": ctx.state.items_processed,
        "errors": len(ctx.state.errors),
    }

@ao.chain(name="pipeline")
class DataPipeline:
    steps = ["fetch", "process", "finalize"]

# Execute
ctx = ChainContext("req_123", state_model=DataPipelineState)
# ... execute steps ...
print(f"Processed: {ctx.state.items_processed}")
print(f"Errors: {ctx.state.errors}")
print(f"Completed: {ctx.state.completed}")
```

### API Reference

**ChainContext**:
- `ChainContext(request_id, state_model=MyState)` - Create context with state
- `ctx.state` - Read-only state access (typed)
- `ctx.edit_state()` - Async context manager for atomic updates

**Context Type Alias**:
- `Context[StateModel]` - Type hint for steps with state

**StateStore** (advanced):
- `StateStore(model_class)` - Low-level state management
- `store.state` - Read-only state
- `store.edit()` - Atomic updates
- `store.to_dict()` - Export state
- `store.from_dict(data)` - Import state
- `store.reset()` - Reset to initial values

### See Also

- `agentorchestrator/core/state.py` - StateStore implementation
- `agentorchestrator/examples/pydantic_state.py` - Complete examples
- `agentorchestrator/tests/unit/test_pydantic_state.py` - Test suite

---

## 1. Source-Level Capping

**Purpose**: Limit items from each data source while preserving metadata about what was omitted.

### cap_per_source

Ensures balanced representation across sources (e.g., news from 5 companies, not 50 from 1).

```python
from agentorchestrator.middleware.offload import cap_per_source

# Raw data: 200 articles from 5 companies (unbalanced)
all_articles = [
    {"title": "...", "company": "AAPL", ...},  # 100 articles
    {"title": "...", "company": "MSFT", ...},  # 50 articles
    {"title": "...", "company": "GOOGL", ...}, # 30 articles
    {"title": "...", "company": "TSLA", ...},  # 15 articles
    {"title": "...", "company": "NVDA", ...},  # 5 articles
]

# Cap to 10 per company, 30 total
capped, metadata = cap_per_source(
    all_articles,
    source_field="company",
    max_per_source=10,
    total_max=30,
)

# Result: Balanced 10+10+10 = 30 (or less if source has fewer)
print(metadata)
# {
#     "original_count": 200,
#     "kept_count": 30,
#     "omitted_count": 170,
#     "was_capped": True,
#     "sources": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"],
#     "per_source_counts": {"AAPL": 100, "MSFT": 50, ...},
#     "omitted_per_source": {"AAPL": 90, "MSFT": 40, ...},
# }
```

### cap_items_with_metadata

Cap by relevance score while tracking what was omitted.

```python
from agentorchestrator.middleware.offload import cap_items_with_metadata

# 150 search results, keep top 20 by relevance
results, metadata = cap_items_with_metadata(
    search_results,
    max_items=20,
    sort_key=lambda x: x.get("relevance_score", 0),
    sort_reverse=True,  # Highest first
)

print(metadata)
# {
#     "original_count": 150,
#     "kept_count": 20,
#     "omitted_count": 130,
#     "was_capped": True,
# }

# IMPORTANT: Tell the LLM about omissions
prompt = f"""
Analyze these search results:
{results}

Note: Showing top {metadata['kept_count']} of {metadata['original_count']} results
by relevance. {metadata['omitted_count']} lower-relevance results were omitted.
"""
```

---

## 2. Summarization

**Purpose**: Compress large text outputs using LLM-powered summarization.

### Strategies

| Strategy | How It Works | Best For |
|----------|--------------|----------|
| **STUFF** | Single LLM call with all text | Small documents (<4K tokens) |
| **MAP_REDUCE** | Parallel chunk summaries → combine | Large documents, speed |
| **REFINE** | Sequential refinement per chunk | Quality over speed |

### Basic Usage

```python
from agentorchestrator.middleware.summarizer import (
    SummarizerMiddleware,
    SummarizationStrategy,
    create_gateway_summarizer,
)

# Create summarizer with your LLM
summarizer = create_gateway_summarizer(
    server_url="https://llm-gateway/v1",
    model_name="claude-sonnet-4",
    strategy=SummarizationStrategy.MAP_REDUCE,
    chunk_size=2000,      # Tokens per chunk
    chunk_overlap=200,    # Overlap for context continuity
)

# Add as middleware
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    max_tokens=8000,              # Trigger summarization above this
    preserve_original=True,       # Keep original in context for retrieval
))
```

### Domain-Specific Prompts

Register custom prompts for your content types:

```python
from agentorchestrator.middleware.summarizer import LangChainSummarizer

# Register at application startup
LangChainSummarizer.register_domain_prompts(
    domain="financial_news",
    map_prompt=(
        "Summarize this financial news, preserving:\n"
        "- Company names and tickers\n"
        "- Key metrics and numbers\n"
        "- Dates and timeframes\n"
        "- Sentiment (bullish/bearish)\n\n"
        "{text}\n\n"
        "Summary:"
    ),
    reduce_prompt=(
        "Combine these news summaries into a cohesive analysis.\n"
        "Preserve all key metrics and company mentions.\n\n"
        "{text}\n\n"
        "Combined Analysis:"
    ),
)

LangChainSummarizer.register_domain_prompts(
    domain="sec_filings",
    map_prompt=(
        "Extract key data from this SEC filing section:\n"
        "- Revenue and earnings\n"
        "- Risk factors\n"
        "- Forward guidance\n"
        "- Material changes\n\n"
        "{text}\n\n"
        "Key Data:"
    ),
)

# Map steps to domains
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    step_content_types={
        "gather_news": "financial_news",
        "gather_sec": "sec_filings",
        "gather_earnings": "financial_news",
    },
))
```

### Manual Summarization

```python
# Summarize text directly
summarized = await summarizer.summarize(
    text=long_document,
    max_tokens=2000,
    strategy=SummarizationStrategy.MAP_REDUCE,
    content_type="sec_filings",  # Uses registered prompts
)
```

### Token Counting

```python
from agentorchestrator.middleware.summarizer import count_tokens

tokens = count_tokens(my_text)
# Uses tiktoken if available, else estimates ~4 chars/token
```

---

## 3. Offloading

**Purpose**: Store large payloads externally, keep lightweight references in context.

### Key Principle: Never Lose Data

Offloading preserves 100% of data - it just moves storage location.

```
Before Offload:
  context["sec_filings"] = [1.2MB of filing data]  # Huge!

After Offload:
  context["sec_filings"] = ContextRef(
      ref_id="abc123",
      summary="45 SEC filings from 5 companies",
      key_fields={"companies": ["AAPL", "MSFT", ...], "count": 45},
  )  # 500 bytes!

  Redis["abc123"] = [1.2MB of filing data]  # Still accessible
```

### Basic Usage

```python
from agentorchestrator.middleware.offload import OffloadMiddleware
from agentorchestrator.core.context_store import RedisContextStore

# Create Redis store
store = RedisContextStore(
    host="localhost",
    port=6379,
    # Or from environment:
    # url=os.getenv("REDIS_URL")
)

# Add offload middleware
ao.use(OffloadMiddleware(
    store=store,
    default_threshold_bytes=100_000,  # 100KB
    step_thresholds={
        "gather_sec": 200_000,    # SEC filings can be larger
        "gather_news": 50_000,    # News should be smaller
    },
    ttl_seconds=3600,  # Expire after 1 hour
))
```

### Custom Key Field Extraction

Tell the middleware what key fields to preserve in the reference:

```python
# Register domain-specific extractor
def extract_filing_fields(data):
    """Extract key fields from SEC filing data."""
    if isinstance(data, list):
        return {
            "count": len(data),
            "companies": list(set(f.get("ticker") for f in data)),
            "filing_types": list(set(f.get("type") for f in data)),
            "date_range": {
                "earliest": min(f.get("date") for f in data),
                "latest": max(f.get("date") for f in data),
            },
        }
    return {"type": type(data).__name__}

def generate_filing_summary(data, key_fields):
    """Generate human-readable summary."""
    return (
        f"{key_fields['count']} SEC filings from "
        f"{len(key_fields['companies'])} companies "
        f"({key_fields['date_range']['earliest']} to {key_fields['date_range']['latest']})"
    )

# Register with middleware
middleware = OffloadMiddleware(store=store)
middleware.register_extractor("gather_sec", extract_filing_fields)
middleware.register_generator("gather_sec", generate_filing_summary)
ao.use(middleware)
```

### Retrieving Offloaded Data

```python
from agentorchestrator.core.context_store import is_context_ref

# In a later step, check if data was offloaded
filings = ctx.get("sec_filings")

if is_context_ref(filings):
    # Data was offloaded - retrieve full data
    full_data = await store.retrieve(filings)

    # Or just use the summary/key_fields
    print(filings.summary)  # "45 SEC filings from 5 companies"
    print(filings.key_fields["companies"])  # ["AAPL", "MSFT", ...]
else:
    # Data is still in context
    full_data = filings
```

### Storage Backends

```python
from agentorchestrator.core.context_store import (
    create_context_store,
    InMemoryContextStore,
    RedisContextStore,
)

# In-memory (development/testing)
store = InMemoryContextStore()

# Redis (production)
store = RedisContextStore(
    host="localhost",
    port=6379,
    db=0,
    password="...",
    ssl=True,  # For cloud Redis
)

# From environment variable
store = create_context_store()  # Uses REDIS_URL if set

# With mem0 semantic search
from agentorchestrator.core.context_store import Mem0ContextStore
store = Mem0ContextStore(client=mem0_client)
```

---

## 4. Token Budget Management

**Purpose**: Track total context tokens and auto-trigger compression when approaching limits.

### Basic Usage

```python
from agentorchestrator.middleware.token_manager import TokenManagerMiddleware

ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,    # Total budget
    warning_threshold=0.8,       # Warn at 80%
    auto_summarize=True,         # Auto-summarize when over limit
    auto_offload=True,           # Auto-offload large payloads
    summarize_oldest_first=True, # Compress oldest steps first
))
```

### With Auto-Summarization

```python
from agentorchestrator.middleware.token_manager import TokenManagerMiddleware
from agentorchestrator.middleware.summarizer import SummarizerMiddleware

# Create summarizer
summarizer_mw = SummarizerMiddleware(
    summarizer=create_gateway_summarizer(...),
    max_tokens=8000,
)

# Create token manager that hooks to summarizer
ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,
    warning_threshold=0.8,
    auto_summarize=True,
    summarizer=summarizer_mw,  # Hook to summarizer
    summarize_oldest_first=True,
))

ao.use(summarizer_mw)
```

### With Auto-Offloading

```python
from agentorchestrator.core.context_store import RedisContextStore

store = RedisContextStore()

ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,
    auto_offload=True,
    context_store=store,
    offload_threshold_bytes=50_000,
))
```

### Custom Threshold Callback

```python
def on_over_limit(ctx, total_tokens):
    """Called when token limit exceeded."""
    logger.warning(f"Token limit exceeded: {total_tokens}")
    # Send alert, trigger manual review, etc.

ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,
    on_threshold_exceeded=on_over_limit,
))
```

### Get Usage Statistics

```python
# After chain execution
token_manager = ao.get_middleware(TokenManagerMiddleware)
usage = token_manager.get_usage()

print(usage)
# {
#     "by_step": {"gather_news": 5000, "gather_sec": 12000, ...},
#     "total": 45000,
#     "max": 100000,
#     "usage_ratio": 0.45,
#     "remaining": 55000,
# }
```

---

## 5. Context Isolation

**Purpose**: Give each agent its own isolated context to prevent pollution and scale to 10+ agents.

### The Problem

Without isolation:
```
Agent A writes to context["data"] = "A's data"
Agent B writes to context["data"] = "B's data"  # Overwrites A!
Agent C reads context["data"]  # Gets B's data, not what it expected
```

With isolation:
```
Agent A: namespace_A["data"] = "A's data"  # Isolated
Agent B: namespace_B["data"] = "B's data"  # Isolated
Agent C: namespace_C["data"] = "C's data"  # Isolated
Coordinator: Aggregates results from all namespaces
```

### Basic Usage

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
    IsolationLevel,
)

# Supervisor creates isolation manager
isolation = ContextIsolationManager(coordinator_context=ctx)

# Create isolated namespaces for each agent
for agent in team:
    agent.namespace = isolation.create_namespace(
        agent_id=agent.id,
        isolation_level=IsolationLevel.FULL,
    )

# Share request data with all agents
isolation.share_with_all("query", user_query)
isolation.share_with_all("user_id", user_id)

# Execute agents in parallel with isolation
async with isolation.execute_parallel(team, process_agent, query) as results:
    for agent_id, result in results.items():
        print(f"{agent_id}: {result}")

# Aggregate results
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
for agent in team:
    aggregator.add_from_namespace(agent.id, agent.namespace)

final = await aggregator.aggregate(llm=llm_client)
```

### Isolation Levels

| Level | Visibility |
|-------|------------|
| `FULL` | Only sees own data + explicitly shared keys |
| `PARTIAL` | Sees own data + all coordinator CHAIN data (read-only) |
| `NONE` | No isolation (legacy mode) |

### Selective Data Sharing

```python
# Share from one agent to specific others
isolation.share_between(
    source_agent="researcher",
    key="findings",
    target_agents=["writer", "reviewer"],
)

# Agent publishes data for coordinator to share
async with namespace:
    namespace.publish("important_insight", finding)
    # Coordinator decides who sees it
```

### Aggregation Strategies

```python
from agentorchestrator.squad.context import AggregationStrategy

# LLM synthesizes narrative from all results
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)

# Deep merge structured data
aggregator = ResultAggregator(strategy=AggregationStrategy.MERGE)

# Select highest confidence result
aggregator = ResultAggregator(strategy=AggregationStrategy.PRIORITIZE)

# Majority voting
aggregator = ResultAggregator(strategy=AggregationStrategy.VOTE)

# Sequential refinement
aggregator = ResultAggregator(strategy=AggregationStrategy.CHAIN)
```

### Full Example: Research Team

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
)

class ResearchSupervisor:
    def __init__(self, team, llm):
        self.team = team
        self.llm = llm

    async def research(self, query, ctx):
        # Create isolation for this execution
        isolation = ContextIsolationManager(coordinator_context=ctx)

        # Create namespaces
        for agent in self.team:
            agent.namespace = isolation.create_namespace(agent.id)

        # Share the query with all agents
        isolation.share_with_all("query", query)

        # Execute each agent in isolation
        async def run_agent(agent, namespace):
            async with namespace:
                # Agent only sees: query + its own work
                result = await agent.research(namespace.get("query"))
                namespace.set_result(result, metadata={
                    "confidence": result.confidence,
                })
                return result

        async with isolation.execute_parallel(
            self.team,
            run_agent
        ) as results:
            pass

        # Aggregate with LLM synthesis
        aggregator = ResultAggregator(
            strategy=AggregationStrategy.SYNTHESIZE
        )
        for agent in self.team:
            aggregator.add_from_namespace(agent.id, agent.namespace)

        final = await aggregator.aggregate(llm=self.llm)

        return final.data
```

---

## Choosing the Right Pattern

### Decision Tree

```
Is context too large?
├── Yes: How many sources?
│   ├── Multiple sources → Use cap_per_source (Layer 1)
│   └── Single source → Continue below
│
├── Is data too large for LLM call?
│   ├── Yes, but need to analyze → Use SummarizerMiddleware (Layer 2)
│   └── Yes, but just storing → Use OffloadMiddleware (Layer 3)
│
├── Running multiple agents?
│   ├── 5+ agents → Use ContextIsolationManager (Layer 5)
│   └── 2-4 agents → Consider TokenManagerMiddleware (Layer 4)
│
└── No: Proceed without context management
```

### Recommended Stack for Production

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware import (
    TokenManagerMiddleware,
    SummarizerMiddleware,
    OffloadMiddleware,
)
from agentorchestrator.core.context_store import RedisContextStore

ao = AgentOrchestrator(name="production_pipeline")

# 1. Token budget management (runs first, tracks everything)
ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,
    warning_threshold=0.8,
    auto_summarize=True,
    auto_offload=True,
))

# 2. Summarization (compresses large outputs)
ao.use(SummarizerMiddleware(
    summarizer=create_gateway_summarizer(...),
    max_tokens=8000,
))

# 3. Offloading (stores very large payloads)
ao.use(OffloadMiddleware(
    store=RedisContextStore(),
    default_threshold_bytes=100_000,
))

# For multi-agent: Use ContextIsolationManager in supervisor
```

---

## Environment Variables

```bash
# Redis for offloading
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=your_password

# LLM for summarization
LLM_SERVER_URL=https://llm-gateway/v1
LLM_MODEL_NAME=claude-sonnet-4

# Token limits
MAX_CONTEXT_TOKENS=100000
SUMMARIZATION_THRESHOLD=8000
OFFLOAD_THRESHOLD_BYTES=100000
```

---

## Comparison with Industry Approaches

| Pattern | AgentOrchestrator | LangChain | LlamaIndex | Google ADK |
|---------|-------------------|-----------|------------|------------|
| **Map-Reduce** | `SummarizationStrategy.MAP_REDUCE` | `load_summarize_chain` | `tree_summarize` | - |
| **Refine** | `SummarizationStrategy.REFINE` | `refine` chain | `refine` mode | - |
| **Context Compression** | `TokenManagerMiddleware` | `ContextualCompression` | - | Session compaction |
| **Offloading** | `OffloadMiddleware` + Redis | - | - | - |
| **Context Isolation** | `ContextIsolationManager` | - | - | Per-agent context |
| **Cap Per Source** | `cap_per_source()` | - | - | - |

---

## What's Not Implemented (Yet)

| Pattern | Status | Notes |
|---------|--------|-------|
| **Observation Masking** | Not implemented | Redacting sensitive fields from LLM context |
| **True Hierarchical Tree** | Partial | MAP_REDUCE uses flat recursion, not tree structure |
| **Adaptive Chunk Sizing** | Not implemented | Dynamic sizing based on content complexity |
| **Cross-Source Token Quotas** | Not implemented | Per-source token budgets |

See [beads issues](https://github.com/your-repo/flow/issues) for roadmap.
