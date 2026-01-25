# Context Isolation Pattern

Prevent context pollution and explosion in multi-agent systems by giving each agent an isolated namespace.

## The Problem

Without isolation, multi-agent systems suffer from:

```
Traditional Approach (Problems):
┌────────────────────────────────────────────────────────┐
│                   Shared Context                        │
│                                                        │
│  Agent A writes "draft_1" ──────┐                      │
│  Agent B writes "draft_1" ──────┼──▶ COLLISION!        │
│  Agent C reads "draft_1"  ──────┘    (wrong data)      │
│                                                        │
│  All agents see everything = context explosion         │
└────────────────────────────────────────────────────────┘
```

## The Solution

Context isolation gives each agent its own namespace:

```
Isolated Approach:
┌────────────────────────────────────────────────────────┐
│                    Coordinator                         │
│                         │                              │
│         ┌───────────────┼───────────────┐              │
│         ▼               ▼               ▼              │
│   ┌───────────┐   ┌───────────┐   ┌───────────┐       │
│   │ Agent A   │   │ Agent B   │   │ Agent C   │       │
│   │ Namespace │   │ Namespace │   │ Namespace │       │
│   │           │   │           │   │           │       │
│   │ draft_1 ✓│   │ draft_1 ✓│   │ draft_1 ✓│       │
│   └───────────┘   └───────────┘   └───────────┘       │
│                                                        │
│   Each agent has its own "draft_1" - no collision!    │
└────────────────────────────────────────────────────────┘
```

## When to Use

| Scenario | Use Context Isolation? |
|----------|------------------------|
| 3+ agents in parallel | :material-check: Yes |
| Agents with overlapping data keys | :material-check: Yes |
| Long-running multi-step workflows | :material-check: Yes |
| Simple sequential agents | :material-close: No |
| 2 agents with distinct outputs | :material-close: Optional |

## Implementation

### Basic Setup

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    IsolationLevel,
)

# 1. Create isolation manager
isolation = ContextIsolationManager(coordinator_context=ctx)

# 2. Create namespace for each agent
for agent in team:
    namespace = isolation.create_namespace(
        agent_id=agent.id,
        isolation_level=IsolationLevel.FULL,
    )
    agent.namespace = namespace

# 3. Share the query with all
isolation.share_with_all("query", user_query)

# 4. Execute in parallel
async with isolation.execute_parallel(team, process_agent) as results:
    for agent_id, result in results.items():
        print(f"{agent_id}: {result}")
```

### Isolation Levels

| Level | Agent Can See | Use Case |
|-------|---------------|----------|
| `FULL` | Only own data + explicit shares | Maximum isolation |
| `PARTIAL` | Own data + all coordinator data (read-only) | Need parent context |
| `NONE` | Everything (legacy mode) | Migration from shared context |

```python
# Full isolation (recommended)
namespace = isolation.create_namespace(
    agent_id="researcher",
    isolation_level=IsolationLevel.FULL,
)

# Partial - can read coordinator context
namespace = isolation.create_namespace(
    agent_id="analyst",
    isolation_level=IsolationLevel.PARTIAL,
)
```

### Selective Sharing

```python
# Share specific data between agents
isolation.share_between(
    source_agent="researcher",
    key="findings",
    target_agents=["analyst", "writer"],
)

# Share value from coordinator to specific agents
isolation.share_between(
    source_agent="coordinator",
    key="config",
    target_agents=["researcher"],
    value={"max_results": 10},
)

# Revoke access
isolation.revoke_sharing("findings", agent_ids=["analyst"])
```

### Working Within a Namespace

```python
async def process_agent(agent, namespace):
    async with namespace:
        # Read shared data
        query = namespace.get("query")

        # Work in isolation
        namespace.set("working_notes", "...")
        namespace.set("intermediate_result", {...})

        # Set final result for aggregation
        namespace.set_result(
            final_answer,
            metadata={"confidence": 0.95},
        )

        return final_answer
```

## Full Example

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.agents import BaseAgent
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
    IsolationLevel,
)

ao = AgentOrchestrator(name="research_squad")

class NewsAgent(BaseAgent):
    name = "news"
    instructions = "Find recent news articles."

class SECAgent(BaseAgent):
    name = "sec"
    instructions = "Find SEC filings."

class EarningsAgent(BaseAgent):
    name = "earnings"
    instructions = "Find earnings reports."

@ao.step(name="parallel_research")
async def parallel_research(ctx):
    team = [NewsAgent(), SECAgent(), EarningsAgent()]

    # Setup isolation
    isolation = ContextIsolationManager(ctx)
    for agent in team:
        isolation.create_namespace(agent.id)

    # Share query
    isolation.share_with_all("query", ctx.get("query"))
    isolation.share_with_all("company", ctx.get("company"))

    # Execute in parallel
    async def run_agent(agent, namespace):
        async with namespace:
            result = await agent.process(namespace.get("query"))
            namespace.set_result(result)
            return result

    async with isolation.execute_parallel(team, run_agent) as results:
        pass

    # Aggregate
    aggregator = ResultAggregator(
        strategy=AggregationStrategy.SYNTHESIZE
    )
    for agent in team:
        aggregator.add_from_namespace(agent.id, agent.namespace)

    final = await aggregator.aggregate(llm=ao.llm)
    return {"research": final.data}

@ao.chain(name="research_chain")
class ResearchChain:
    steps = ["parallel_research"]
```

## Provenance Tracking

Track where shared data came from:

```python
# Get sharing graph
graph = isolation.get_sharing_graph()
# {'coordinator': ['news', 'sec', 'earnings'],
#  'news': ['analyst']}

# Get full provenance
for entry in isolation.get_shared_data_provenance():
    print(f"{entry.key}: {entry.source_agent} -> {entry.target_agents}")
```

## Debugging

```python
# Get stats on isolation state
stats = isolation.get_stats()
print(stats)
# {
#     'namespace_count': 3,
#     'shared_keys_count': 2,
#     'namespaces': {
#         'news': {'isolation_level': 'full', 'local_store_size': 5},
#         'sec': {'isolation_level': 'full', 'local_store_size': 3},
#         ...
#     }
# }

# Take namespace snapshot
snapshot = namespace.snapshot()
print(f"Agent {snapshot.agent_id} has {snapshot.result_count} results")
```

## Best Practices

!!! tip "Use FULL Isolation by Default"
    Start with maximum isolation and selectively share what's needed.

!!! tip "Share Minimally"
    Only share what agents actually need. More sharing = more coupling.

!!! tip "Name Keys Clearly"
    Use prefixes like `news_headlines`, `sec_filings` to avoid confusion.

!!! warning "Don't Share Mutable Objects"
    Pass copies or immutable data to prevent accidental modification.

## Related Patterns

- [Summarization](summarization.md) - Compress large results before sharing
- [Aggregation](aggregation.md) - Combine isolated results
- [Routing](routing.md) - Decide which agent to use

## API Reference

::: agentorchestrator.squad.context.ContextIsolationManager
::: agentorchestrator.squad.context.AgentContextNamespace
::: agentorchestrator.squad.context.IsolationLevel
