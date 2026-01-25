# Multi-Agent Patterns

This section covers patterns for building robust multi-agent systems that scale.

## The Problem

When you have multiple agents working together, you face several challenges:

1. **Context Explosion** - N agents × full context = massive token usage
2. **Context Pollution** - Agent A's work accidentally influences Agent B
3. **Large Responses** - Individual agents return more data than fits in context
4. **Result Synthesis** - Combining outputs from multiple specialists

## Pattern Overview

| Pattern | Problem Solved | When to Use |
|---------|---------------|-------------|
| [Context Isolation](context_isolation.md) | Pollution & explosion | 3+ agents working in parallel |
| [Summarization](summarization.md) | Large responses | Single agent returns huge data |
| [Routing](routing.md) | Task distribution | Dynamic agent selection |
| [Aggregation](aggregation.md) | Result synthesis | Combining specialist outputs |

## Decision Tree

```
                    ┌─────────────────────┐
                    │  Multiple agents?   │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                   Yes                    No
                    │                     │
        ┌───────────▼───────────┐    ┌────▼────┐
        │  Parallel execution?  │    │  Skip   │
        └───────────┬───────────┘    └─────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
        Yes                    No
         │                     │
    ┌────▼────┐           ┌────▼────┐
    │ Context │           │ Routing │
    │Isolation│           │ Pattern │
    └────┬────┘           └─────────┘
         │
         │ Large responses?
         │
    ┌────▼────┐
    │Summarize│
    │ Pattern │
    └────┬────┘
         │
         │ Need unified output?
         │
    ┌────▼────┐
    │Aggregate│
    │ Pattern │
    └─────────┘
```

## Quick Comparison

### Context Isolation

```python
# Each agent sees only what it needs
isolation = ContextIsolationManager(ctx)
for agent in team:
    namespace = isolation.create_namespace(agent.id)
    # Agent works in isolated sandbox
```

[:material-arrow-right: Full Guide](context_isolation.md)

### Summarization

```python
# Compress large outputs to fit context
ao.use(SummarizerMiddleware(
    strategy=SummarizationStrategy.MAP_REDUCE,
    max_tokens=2000,
))
```

[:material-arrow-right: Full Guide](summarization.md)

### Routing

```python
# Route to the right agent dynamically
router = RouterAgent(agents={
    "research": researcher,
    "analysis": analyst,
})
result = await router.route(query)
```

[:material-arrow-right: Full Guide](routing.md)

### Aggregation

```python
# Synthesize outputs from multiple agents
aggregator = ResultAggregator(
    strategy=AggregationStrategy.SYNTHESIZE
)
final = await aggregator.aggregate(llm=llm)
```

[:material-arrow-right: Full Guide](aggregation.md)

## Combining Patterns

In practice, you'll often use multiple patterns together:

```python
# 1. Isolate contexts
isolation = ContextIsolationManager(ctx)

# 2. Add summarization middleware
ao.use(SummarizerMiddleware(max_tokens=3000))

# 3. Execute agents in parallel
async with isolation.execute_parallel(agents, process_fn):
    pass

# 4. Aggregate results
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
for agent in agents:
    aggregator.add_from_namespace(agent.id, agent.namespace)

final = await aggregator.aggregate(llm=llm)
```

## Industry Comparison

| Feature | AgentOrchestrator | LangChain | LlamaIndex | Google ADK |
|---------|-------------------|-----------|------------|------------|
| Context Isolation | :material-check: | Partial | Partial | :material-check: |
| Map-Reduce Summarization | :material-check: | :material-check: | :material-check: | :material-check: |
| Refine Summarization | :material-check: | :material-check: | :material-check: | - |
| Auto-Compaction | :material-check: | - | - | :material-check: |
| Token Budget | :material-check: | - | - | :material-check: |
| Redis Offloading | :material-check: | - | - | - |
| Result Aggregation | :material-check: | Partial | Partial | - |

## Next Steps

Choose the pattern that matches your need:

- **Agents interfering?** → [Context Isolation](context_isolation.md)
- **Responses too large?** → [Summarization](summarization.md)
- **Need dynamic routing?** → [Routing](routing.md)
- **Combining outputs?** → [Aggregation](aggregation.md)
