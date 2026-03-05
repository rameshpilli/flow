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
| [**Pattern Decision Guide**](PATTERN_DECISION_GUIDE.md) | Which pattern to use? | Start here for decision flowcharts |
| [**Middleware Selection**](middleware_selection.md) | Which middleware? | Quick reference for middleware choice |
| [Large Response Handling](large_response_handling.md) | Token management & summarization | Managing large agent outputs |
| [Context Isolation](context_isolation.md) | Pollution & explosion | 3+ agents working in parallel |
| [Idempotency](idempotency.md) | Duplicate execution | Prevent duplicate API calls/payments |
| [Routing](routing.md) | Task distribution | Dynamic agent selection |
| [Aggregation](aggregation.md) | Result synthesis | Combining specialist outputs |

!!! tip "New to patterns?"
    Start with the [Pattern Decision Guide](PATTERN_DECISION_GUIDE.md) for decision flowcharts and Input→Process→Output examples for each strategy.

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

[:material-arrow-right: Full Guide](large_response_handling.md)

### Routing

```python
# Route to the right agent dynamically
orchestrator = MultiAgentOrchestrator(classifier=LLMGatewayClassifier())
response = await orchestrator.route_request(user_input=query, user_id="user-1")
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
| **TREE Summarization** | :material-check: | - | :material-check: | - |
| Auto-Compaction | :material-check: | - | - | :material-check: |
| **Token Budget Reservation** | :material-check: | - | Partial | :material-check: |
| **Namespace-Aware Budgets** | :material-check: | - | - | - |
| Redis Offloading | :material-check: | - | - | - |
| Result Aggregation | :material-check: | Partial | Partial | - |
| **Pre-Aggregation Summarization** | :material-check: | - | - | - |
| **Middleware Metrics** | :material-check: | Callbacks | - | - |
| **Rolling Summary** | :material-check: | - | Partial | - |
| **Query-Aware Compression** | :material-check: | - | Partial | - |

## Next Steps

Choose the pattern that matches your need:

- **Not sure which pattern?** → [Pattern Decision Guide](PATTERN_DECISION_GUIDE.md) (start here!)
- **Agents interfering?** → [Context Isolation](context_isolation.md)
- **Responses too large?** → [Large Response Handling](large_response_handling.md)
- **Need dynamic routing?** → [Routing](routing.md)
- **Combining outputs?** → [Aggregation](aggregation.md)

## API Reference

For implementation details:

- **Token Management**: `TokenBudget`, `NamespaceBudgetManager`, `TokenManagerMiddleware`
- **Summarization**: `SummarizerMiddleware`, `RollingSummaryMiddleware`, `SummarizationStrategy`
- **Aggregation**: `ResultAggregator`, `AggregationStrategy`
- **Monitoring**: `ao.get_middleware_metrics()`, `ao.list_middleware()`
