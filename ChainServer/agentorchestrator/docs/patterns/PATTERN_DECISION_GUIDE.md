# Pattern Decision Guide

> **Quick Reference**: Which pattern should I use for my use case?

This guide helps you choose the right middleware and aggregation patterns for handling large agent responses.

---

## Decision Flowchart

```
Start
  │
  ▼
┌─────────────────────────────────────┐
│ Is your output > 50K tokens?        │
└─────────────────────────────────────┘
  │ YES                    │ NO
  ▼                        ▼
┌─────────────────┐   ┌─────────────────┐
│ Use TREE        │   │ Is output >     │
│ Summarization   │   │ 10K tokens?     │
└─────────────────┘   └─────────────────┘
                           │ YES    │ NO
                           ▼        ▼
                      ┌─────────┐ ┌─────────┐
                      │MAP_REDUCE│ │ STUFF  │
                      │or REFINE │ │ or none│
                      └─────────┘ └─────────┘
```

---

## Summarization Strategies

### STUFF (Simple)

**What it does**: Fits everything into a single LLM call.

**When to use**:
- Single document under 4K tokens
- Speed is critical
- Simple content that doesn't need chunking

**Example**:
```python
# A short document that fits in context
from agentorchestrator.middleware import SummarizerMiddleware, SummarizationStrategy

ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.STUFF,
    max_tokens=2000,
    applies_to=["gather_short_notes"],
))
```

**Input → Process → Output**:
```
Input: "Q3 earnings call notes (1,200 words)"
         │
         ▼
┌──────────────────────────┐
│  Single LLM call:        │
│  "Summarize this..."     │
└──────────────────────────┘
         │
         ▼
Output: "Revenue up 15%, guidance raised..."
        (300 words)
```

---

### MAP_REDUCE (Parallel)

**What it does**: Splits content into chunks, summarizes each in parallel, then combines.

**When to use**:
- Large documents (10K-100K tokens)
- Content can be split without losing meaning
- Speed matters (parallel processing)
- Multiple independent sections

**Example**:
```python
# Processing multiple news articles in parallel
ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.MAP_REDUCE,
    chunk_size=4000,
    max_tokens=3000,
    applies_to=["gather_news", "gather_articles"],
))
```

**Input → Process → Output**:
```
Input: 50 news articles (80K tokens total)
         │
    ┌────┼────┬────┬────┐
    ▼    ▼    ▼    ▼    ▼
  Chunk Chunk Chunk Chunk Chunk   (MAP: parallel)
  10    10    10    10    10
    │    │    │    │    │
    ▼    ▼    ▼    ▼    ▼
  Sum1  Sum2  Sum3  Sum4  Sum5    (each ~1K tokens)
    │    │    │    │    │
    └────┴────┴────┴────┘
              │
              ▼
       Final Summary              (REDUCE)
       (3K tokens)

Output: "Key themes: AI regulation (12 articles),
         Fed rates (8 articles), Tech earnings (30 articles)..."
```

---

### REFINE (Sequential)

**What it does**: Processes chunks sequentially, each refinement builds on the previous.

**When to use**:
- Narrative coherence is critical
- Content has logical flow that shouldn't be broken
- Quality over speed
- SEC filings, legal documents, research papers

**Example**:
```python
# SEC 10-K filings need coherent narrative
ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.REFINE,
    chunk_size=4000,
    max_tokens=5000,
    applies_to=["gather_sec_filings"],
))
```

**Input → Process → Output**:
```
Input: Apple 10-K filing (150K tokens)
         │
         ▼
Chunk 1 (Business Overview)
         │
         ▼
┌─────────────────────────────┐
│ Summary 1: "Apple designs,  │
│ manufactures..."            │
└─────────────────────────────┘
         │
         ▼
Chunk 2 (Risk Factors) + Summary 1
         │
         ▼
┌─────────────────────────────┐
│ Summary 2: "Apple designs...│
│ Key risks include supply    │
│ chain, China exposure..."   │
└─────────────────────────────┘
         │
         ▼
Chunk 3 (Financials) + Summary 2
         │
         ▼
┌─────────────────────────────┐
│ Final: Coherent narrative   │
│ covering all sections       │
└─────────────────────────────┘

Output: Complete, coherent summary preserving
        logical flow of the document
```

---

### TREE (Hierarchical)

**What it does**: Builds a summarization tree - summarizes groups, then summarizes summaries.

**When to use**:
- Massive documents (>50K tokens)
- Need to handle recursive depth
- Auto-selected when content exceeds thresholds
- Best compression ratio for very large inputs

**Example**:
```python
# Huge document collections
ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.TREE,
    chunk_size=4000,
    max_tokens=4000,
    tree_depth=3,  # How many levels of summarization
    applies_to=["gather_all_filings"],
))
```

**Input → Process → Output**:
```
Input: 500 documents (2M tokens)
         │
    ┌────┼────┬────┬────┐
    ▼    ▼    ▼    ▼    ▼
  Group Group Group Group Group   (Level 0: 100 docs each)
    │    │    │    │    │
    ▼    ▼    ▼    ▼    ▼
  Sum1  Sum2  Sum3  Sum4  Sum5    (Level 1: 5 summaries)
    │    │    │    │    │
    └────┴────┼────┴────┘
              ▼
         ┌─────────┐
         │ Sum6    │              (Level 2: meta-summary)
         └─────────┘
              │
              ▼
         Final Summary            (Level 3: executive summary)

Output: "Across 500 filings spanning 50 companies,
         key themes include..." (4K tokens)
```

---

## Result Aggregation Strategies

### SYNTHESIZE (LLM Narrative)

**What it does**: Uses LLM to create a coherent narrative from all agent outputs.

**When to use**:
- Multiple agents provide different perspectives
- Need unified, readable output
- Research reports, analysis summaries
- Quality and coherence matter most

**Example**:
```python
from agentorchestrator.squad.context import ResultAggregator, AggregationStrategy

aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)

# After agents execute
aggregator.add_result("sec_agent", data=sec_findings, confidence=0.9)
aggregator.add_result("news_agent", data=news_summary, confidence=0.85)
aggregator.add_result("analyst_agent", data=analyst_notes, confidence=0.8)

# LLM creates unified narrative
result = await aggregator.aggregate(llm=llm_client)
```

**Input → Process → Output**:
```
Input:
  SEC Agent: "Revenue: $394B, up 8% YoY..."
  News Agent: "Apple announced Vision Pro launch..."
  Analyst Agent: "Consensus price target: $200..."
         │
         ▼
┌─────────────────────────────────┐
│ LLM Synthesis:                  │
│ "Combine these perspectives..." │
└─────────────────────────────────┘
         │
         ▼
Output: "Apple demonstrates strong fundamentals with
         $394B revenue (+8% YoY) as reported in their
         latest 10-K. The company is positioning for
         growth with the Vision Pro launch, which
         analysts view favorably, setting a consensus
         price target of $200..."
```

---

### MERGE (Deep Combine)

**What it does**: Deep merges structured data (dicts/lists), tracks conflicts.

**When to use**:
- Agents return structured JSON data
- Complementary data from different sources
- Need to combine without losing fields
- Data pipeline outputs

**Example**:
```python
aggregator = ResultAggregator(
    strategy=AggregationStrategy.MERGE,
    conflict_resolver=lambda c: c.values[0],  # Take first on conflict
)

aggregator.add_result("profile_agent", {"name": "AAPL", "sector": "Tech"})
aggregator.add_result("metrics_agent", {"revenue": 394e9, "pe_ratio": 28.5})
aggregator.add_result("news_agent", {"sentiment": "positive", "articles": 45})

result = await aggregator.aggregate()
# result.data = {"name": "AAPL", "sector": "Tech", "revenue": 394e9,
#                "pe_ratio": 28.5, "sentiment": "positive", "articles": 45}
```

**Input → Process → Output**:
```
Input:
  Agent 1: {"name": "AAPL", "sector": "Tech"}
  Agent 2: {"revenue": 394e9, "pe_ratio": 28.5}
  Agent 3: {"sentiment": "positive", "articles": 45}
         │
         ▼
┌─────────────────────────────────┐
│ Deep Merge:                     │
│ Combine all keys, track         │
│ conflicts if same key differs   │
└─────────────────────────────────┘
         │
         ▼
Output: {
  "name": "AAPL",
  "sector": "Tech",
  "revenue": 394e9,
  "pe_ratio": 28.5,
  "sentiment": "positive",
  "articles": 45
}
```

---

### PRIORITIZE (Best Wins)

**What it does**: Selects the result with highest priority/confidence score.

**When to use**:
- Expert opinion should override others
- Tiered fallback (primary → secondary → tertiary)
- Classification where one answer is correct
- When agents have different authority levels

**Example**:
```python
aggregator = ResultAggregator(strategy=AggregationStrategy.PRIORITIZE)

# Expert agent gets highest priority
aggregator.add_result("expert_agent", data="Strong Buy", confidence=0.95, priority=10)
aggregator.add_result("junior_agent", data="Hold", confidence=0.75, priority=1)
aggregator.add_result("basic_agent", data="Buy", confidence=0.60, priority=0)

result = await aggregator.aggregate()
# result.data = "Strong Buy" (expert wins)
```

**Input → Process → Output**:
```
Input:
  Expert (priority=10, conf=0.95): "Strong Buy"
  Junior (priority=1, conf=0.75):  "Hold"
  Basic  (priority=0, conf=0.60):  "Buy"
         │
         ▼
┌─────────────────────────────────┐
│ Sort by priority, then conf    │
│ Select top result              │
└─────────────────────────────────┘
         │
         ▼
Output: "Strong Buy"
        (from expert_agent)
```

---

### VOTE (Majority)

**What it does**: Counts votes for discrete answers, returns majority.

**When to use**:
- Binary decisions (buy/sell, approve/reject)
- Classification tasks
- When consensus matters more than individual confidence
- Ensemble predictions

**Example**:
```python
aggregator = ResultAggregator(strategy=AggregationStrategy.VOTE)

aggregator.add_result("model_1", data="bullish", confidence=0.8)
aggregator.add_result("model_2", data="bullish", confidence=0.7)
aggregator.add_result("model_3", data="bearish", confidence=0.9)
aggregator.add_result("model_4", data="bullish", confidence=0.6)

result = await aggregator.aggregate()
# result.data = "bullish" (3 vs 1)
```

**Input → Process → Output**:
```
Input:
  Model 1: "bullish"
  Model 2: "bullish"
  Model 3: "bearish"
  Model 4: "bullish"
         │
         ▼
┌─────────────────────────────────┐
│ Count votes:                    │
│   bullish: 3                    │
│   bearish: 1                    │
│ Majority wins                   │
└─────────────────────────────────┘
         │
         ▼
Output: "bullish" (75% confidence)
```

---

### CHAIN (Sequential Refinement)

**What it does**: Each result builds on the previous, refining iteratively.

**When to use**:
- Review chains (draft → edit → polish)
- Iterative improvement
- Quality assurance pipelines
- When later agents should enhance earlier work

**Example**:
```python
aggregator = ResultAggregator(strategy=AggregationStrategy.CHAIN)

# Results applied in priority order (low to high)
aggregator.add_result("draft_agent", data="Initial report...", priority=0)
aggregator.add_result("editor_agent", data="Edited report...", priority=5)
aggregator.add_result("qa_agent", data="Final report...", priority=10)

result = await aggregator.aggregate()
# Each refinement builds on the previous
```

**Input → Process → Output**:
```
Input:
  Draft (pri=0):  "Initial report with typos..."
  Editor (pri=5): "Corrected report, better flow..."
  QA (pri=10):    "Final polished report..."
         │
         ▼
┌─────────────────────────────────┐
│ Apply in order:                 │
│ 1. Start with draft             │
│ 2. Editor refines               │
│ 3. QA polishes                  │
└─────────────────────────────────┘
         │
         ▼
Output: "Final polished report..."
        (refined through all stages)
```

---

### CONCAT (Simple Join)

**What it does**: Concatenates all results with agent headers.

**When to use**:
- Collecting multiple perspectives without synthesis
- Log aggregation
- When you want to preserve each agent's voice
- Debug/audit purposes

**Example**:
```python
aggregator = ResultAggregator(strategy=AggregationStrategy.CONCAT)

aggregator.add_result("agent_1", data="Perspective from agent 1...")
aggregator.add_result("agent_2", data="Perspective from agent 2...")
aggregator.add_result("agent_3", data="Perspective from agent 3...")

result = await aggregator.aggregate()
```

**Input → Process → Output**:
```
Input:
  Agent 1: "Market analysis shows..."
  Agent 2: "Technical indicators suggest..."
  Agent 3: "Fundamental analysis reveals..."
         │
         ▼
┌─────────────────────────────────┐
│ Simple concatenation:           │
│ Add headers for each agent      │
└─────────────────────────────────┘
         │
         ▼
Output:
  "## agent_1
   Market analysis shows...

   ## agent_2
   Technical indicators suggest...

   ## agent_3
   Fundamental analysis reveals..."
```

---

## Token Management Patterns

### TokenBudget with Reservations

**What it does**: Explicitly reserves tokens for output, system prompt, and history.

**When to use**:
- Always! This prevents output truncation
- Especially important for long-running agents
- Multi-turn conversations

**Example**:
```python
from agentorchestrator.middleware import TokenManagerMiddleware, TokenBudget

budget = TokenBudget(
    context_window=128000,    # Your LLM's context window
    reserved_output=8000,     # Reserve for model response
    reserved_system=3000,     # Reserve for system prompt
    reserved_history=15000,   # Reserve for chat history
)
# available_for_content = 128000 - 8000 - 3000 - 15000 = 102000

ao.use(TokenManagerMiddleware(
    budget=budget,
    auto_summarize=True,
    auto_offload=True,
))
```

---

### Rolling Summary Buffer

**What it does**: Keeps recent context uncompressed, summarizes older context incrementally.

**When to use**:
- Long conversations
- Iterative data gathering
- When recent context is more important
- Memory-efficient history management

**Example**:
```python
from agentorchestrator.middleware import RollingSummaryMiddleware

ao.use(RollingSummaryMiddleware(
    max_history_tokens=10000,      # Total history budget
    recent_buffer_tokens=3000,     # Keep this many recent tokens uncompressed
    compression_ratio=0.3,         # Target 30% of original size
    applies_to=["gather_*"],       # Apply to all gather steps
))
```

**Input → Process → Output**:
```
Turn 1: User asks about AAPL
        Response: 2000 tokens    ← Uncompressed (recent)

Turn 2: User asks about MSFT
        Response: 2000 tokens    ← Uncompressed (recent)

Turn 3: User asks about GOOGL
        Response: 2000 tokens    ← Uncompressed (recent)

Turn 4: User asks about AMZN
        │
        ▼
┌─────────────────────────────────┐
│ Rolling Summary:                │
│ Turn 1 compressed to 600 tokens │
│ Turns 2-4 stay uncompressed     │
└─────────────────────────────────┘
        │
        ▼
History: [Summary of T1] + [T2] + [T3] + [T4]
         600 + 2000 + 2000 + 2000 = 6600 tokens
```

---

## Quick Decision Matrix

| Scenario | Summarization | Aggregation | Token Mgmt |
|----------|---------------|-------------|------------|
| **Single large document** | STUFF or REFINE | - | TokenBudget |
| **Multiple documents** | MAP_REDUCE | MERGE | TokenBudget |
| **Research report** | REFINE | SYNTHESIZE | Rolling Summary |
| **Massive corpus (>50K)** | TREE | SYNTHESIZE | TokenBudget + Offload |
| **Ensemble classification** | - | VOTE | - |
| **Expert hierarchy** | - | PRIORITIZE | - |
| **Review pipeline** | - | CHAIN | - |
| **Multi-agent parallel** | MAP_REDUCE | MERGE | Namespace Budgets |
| **Multi-agent supervisor** | TREE | SYNTHESIZE | Rolling Summary |
| **Long conversation** | - | - | Rolling Summary |

---

## Related Documentation

- [Large Response Handling](large_response_handling.md) - Complete guide on token management and summarization
- [Context Isolation](context_isolation.md) - Multi-agent isolation
- [Aggregation Pattern](aggregation.md) - Result combining

---

## Next Steps

1. **Start simple**: Use `STUFF` or `MAP_REDUCE` for most cases
2. **Add TokenBudget**: Always configure explicit reservations
3. **Layer middleware**: TokenManager → Summarizer → Offload
4. **Monitor metrics**: Use `ao.get_middleware_metrics()` to tune
5. **Iterate**: Adjust thresholds based on actual usage patterns
