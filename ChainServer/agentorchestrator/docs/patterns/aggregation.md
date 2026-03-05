# Aggregation Pattern

Combine outputs from multiple agents into a unified result using various synthesis strategies.

## The Problem

Multiple agents produce separate outputs that need to be combined:

```
News Agent → "Tech stocks rally on AI news..."
SEC Agent  → "NVIDIA files 10-Q showing..."
Earnings   → "Q3 earnings beat estimates..."

User needs: One coherent research report
```

## The Solution

The ResultAggregator collects and synthesizes agent outputs:

```
┌──────────────────────────────────────────────────────────┐
│                   Result Aggregator                       │
│                                                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                  │
│  │ News    │  │ SEC     │  │Earnings │                  │
│  │ Result  │  │ Result  │  │ Result  │                  │
│  └────┬────┘  └────┬────┘  └────┬────┘                  │
│       │            │            │                        │
│       └────────────┼────────────┘                        │
│                    ▼                                     │
│            ┌──────────────┐                              │
│            │  Synthesize  │   ← LLM creates narrative   │
│            └──────┬───────┘                              │
│                   │                                      │
│                   ▼                                      │
│         "Comprehensive Report:                           │
│          NVIDIA shows strong momentum                    │
│          with Q3 beats and AI demand..."                │
└──────────────────────────────────────────────────────────┘
```

## When to Use

| Strategy | Best For |
|----------|----------|
| SYNTHESIZE | Creating narratives from multiple sources |
| MERGE | Combining structured data (dicts, lists) |
| PRIORITIZE | Selecting best answer by confidence |
| VOTE | Consensus on discrete answers |
| CHAIN | Iterative refinement |
| CONCAT | Simple concatenation |

## Strategies

### SYNTHESIZE

Use LLM to create a unified narrative:

```python
from agentorchestrator.squad.context import (
    ResultAggregator,
    AggregationStrategy,
)

aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)

# Add results
aggregator.add_result("news", news_data, confidence=0.9)
aggregator.add_result("sec", sec_data, confidence=0.95)
aggregator.add_result("earnings", earnings_data, confidence=0.85)

# Synthesize with LLM
final = await aggregator.aggregate(llm=llm_client)
print(final.data)  # Unified narrative
```

### MERGE

Deep merge dictionaries and lists:

```python
aggregator = ResultAggregator(strategy=AggregationStrategy.MERGE)

aggregator.add_result("agent_a", {"metrics": {"revenue": 100}})
aggregator.add_result("agent_b", {"metrics": {"profit": 20}})

final = await aggregator.aggregate()
print(final.data)
# {"metrics": {"revenue": 100, "profit": 20}}
```

### PRIORITIZE

Select result with highest confidence/priority:

```python
aggregator = ResultAggregator(strategy=AggregationStrategy.PRIORITIZE)

aggregator.add_result("fast_model", answer, confidence=0.7, priority=1)
aggregator.add_result("slow_model", answer, confidence=0.95, priority=2)

final = await aggregator.aggregate()
# Returns slow_model's answer (higher priority and confidence)
```

### VOTE

Majority voting for discrete answers:

```python
aggregator = ResultAggregator(strategy=AggregationStrategy.VOTE)

aggregator.add_result("model_a", "bullish")
aggregator.add_result("model_b", "bullish")
aggregator.add_result("model_c", "bearish")

final = await aggregator.aggregate()
print(final.data)  # "bullish" (2/3 votes)
```

### CHAIN

Sequential refinement:

```python
aggregator = ResultAggregator(strategy=AggregationStrategy.CHAIN)

aggregator.add_result("draft", initial_text, priority=1)
aggregator.add_result("editor", edited_text, priority=2)
aggregator.add_result("reviewer", final_text, priority=3)

final = await aggregator.aggregate()
# Each result builds on previous
```

### CONCAT

Simple concatenation:

```python
aggregator = ResultAggregator(strategy=AggregationStrategy.CONCAT)

aggregator.add_result("section_1", "Introduction...")
aggregator.add_result("section_2", "Analysis...")
aggregator.add_result("section_3", "Conclusion...")

final = await aggregator.aggregate()
# "## section_1\nIntroduction...\n\n## section_2\nAnalysis..."
```

## Implementation

### Basic Usage

```python
from agentorchestrator.squad.context import (
    ResultAggregator,
    AggregationStrategy,
)

aggregator = ResultAggregator(
    strategy=AggregationStrategy.SYNTHESIZE
)

# Add results from each agent
for agent in team:
    aggregator.add_result(
        agent_id=agent.id,
        data=agent.get_result(),
        confidence=agent.get_confidence(),
        priority=agent.priority,
        metadata={"model": agent.model},
    )

# Aggregate
final = await aggregator.aggregate(llm=llm_client)
```

### From Namespaces

When using context isolation:

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
)

isolation = ContextIsolationManager(ctx)

# ... agents execute with isolated namespaces ...

# Aggregate from namespaces
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)

for agent in team:
    aggregator.add_from_namespace(agent.id, agent.namespace)

final = await aggregator.aggregate(llm=llm_client)
```

### Custom Synthesis Prompt

```python
final = await aggregator.aggregate(
    llm=llm_client,
    prompt_template="""You are synthesizing research from multiple analysts.

ANALYST OUTPUTS:
{context}

Create a unified research report that:
1. Highlights key findings from each source
2. Identifies common themes
3. Notes any disagreements
4. Provides actionable insights

RESEARCH REPORT:""",
)
```

### Conflict Handling

```python
def resolve_conflict(conflict):
    """Custom conflict resolver."""
    # conflict.key - the conflicting key
    # conflict.agents - agents with different values
    # conflict.values - the different values

    # Return the resolved value
    return conflict.values[0]  # Use first agent's value

aggregator = ResultAggregator(
    strategy=AggregationStrategy.MERGE,
    conflict_resolver=resolve_conflict,
)
```

## Full Example

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
)

ao = AgentOrchestrator(name="research_squad")

@ao.step(name="research")
async def research(ctx):
    team = [NewsAgent(), SECAgent(), EarningsAgent()]

    # Setup isolation
    isolation = ContextIsolationManager(ctx)
    for agent in team:
        isolation.create_namespace(agent.id)
    isolation.share_with_all("query", ctx.get("query"))

    # Execute in parallel
    async def run_agent(agent, namespace):
        async with namespace:
            result = await agent.process(namespace.get("query"))
            namespace.set_result(result, metadata={
                "confidence": agent.get_confidence(),
                "tokens_used": agent.tokens_used,
            })
            return result

    async with isolation.execute_parallel(team, run_agent):
        pass

    # Aggregate results
    aggregator = ResultAggregator(
        strategy=AggregationStrategy.SYNTHESIZE
    )

    for agent in team:
        aggregator.add_from_namespace(agent.id, agent.namespace)

    final = await aggregator.aggregate(
        llm=ao.llm,
        prompt_template="""Create a comprehensive research report...

{context}

REPORT:""",
    )

    # Return aggregated result
    return {
        "report": final.data,
        "confidence": final.confidence,
        "sources": list(final.agent_contributions.keys()),
        "conflicts": len(final.conflicts),
    }
```

## Inspecting Results

```python
# Get aggregated result details
final = await aggregator.aggregate(llm=llm)

# Main output
print(final.data)

# Confidence score (reduced if conflicts)
print(f"Confidence: {final.confidence:.1%}")

# What each agent contributed
for agent_id, contrib in final.agent_contributions.items():
    print(f"{agent_id}: {contrib['data_preview'][:100]}...")

# Any conflicts detected
for conflict in final.conflicts:
    print(f"Conflict on '{conflict.key}':")
    print(f"  Values: {conflict.values}")
    print(f"  Resolved: {conflict.resolution}")
```

## Best Practices

!!! tip "Choose Strategy Wisely"
    SYNTHESIZE for narratives, MERGE for data, VOTE for classification.

!!! tip "Include Confidence Scores"
    Helps PRIORITIZE strategy and informs synthesis.

!!! tip "Track Conflicts"
    Review `final.conflicts` to understand disagreements.

!!! warning "Validate Synthesis"
    LLM synthesis can hallucinate. Cross-check critical facts.

## Related Patterns

- [Context Isolation](context_isolation.md) - Isolate before aggregating
- [Large Response Handling](large_response_handling.md) - Compress large results first

## API Reference

::: agentorchestrator.squad.context.ResultAggregator
::: agentorchestrator.squad.context.AggregationStrategy
::: agentorchestrator.squad.context.ContextAgentResult
::: agentorchestrator.squad.context.AggregatedResult
