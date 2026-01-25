# Multi-Agent Systems

When a single agent isn't enough, **multi-agent systems** let you coordinate specialized agents to tackle complex tasks.

## When to Use Multi-Agent

| Scenario | Single Agent | Multi-Agent |
|----------|--------------|-------------|
| Simple Q&A | :material-check: | |
| Domain-specific task | :material-check: | |
| Complex research | | :material-check: |
| Multi-step workflows | | :material-check: |
| Specialized expertise needed | | :material-check: |
| Parallel data gathering | | :material-check: |

## Architecture Patterns

AgentOrchestrator supports three multi-agent patterns:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Multi-Agent Patterns                         │
├─────────────────┬─────────────────────┬─────────────────────────┤
│   Supervisor    │      Swarm          │        Network          │
│                 │                     │                         │
│   ┌───────┐     │  ┌───┐ ┌───┐ ┌───┐ │    ┌───┐     ┌───┐      │
│   │  Sup  │     │  │ A │ │ B │ │ C │ │    │ A │────▶│ B │      │
│   └───┬───┘     │  └───┘ └───┘ └───┘ │    └───┘     └─┬─┘      │
│       │         │     │     │     │   │      ▲        │        │
│  ┌────┼────┐    │     └─────┴─────┘   │      │        ▼        │
│  ▼    ▼    ▼    │         │           │      └──────┌───┐      │
│ ┌─┐  ┌─┐  ┌─┐   │         ▼           │            │ C │      │
│ │A│  │B│  │C│   │    Shared State     │            └───┘      │
│ └─┘  └─┘  └─┘   │                     │                         │
│                 │                     │                         │
│ Hierarchical    │  Peer-to-Peer       │   Dynamic Routing       │
│ Central control │  Emergent behavior  │   Task-based handoff    │
└─────────────────┴─────────────────────┴─────────────────────────┘
```

## Supervisor Pattern

A supervisor agent coordinates sub-agents, delegating tasks and aggregating results.

```python
from agentorchestrator.squad import SupervisorAgent, Squad

# Define specialized agents
class ResearchAgent(BaseAgent):
    name = "researcher"
    instructions = "Find and gather information on topics."
    tools = [search_web, read_document]

class AnalystAgent(BaseAgent):
    name = "analyst"
    instructions = "Analyze data and provide insights."
    tools = [calculate_metrics, create_chart]

class WriterAgent(BaseAgent):
    name = "writer"
    instructions = "Write clear, compelling content."

# Create supervisor
supervisor = SupervisorAgent(
    name="project_lead",
    instructions="""
    You coordinate a research team. Delegate tasks to the right agent:
    - researcher: for gathering information
    - analyst: for data analysis
    - writer: for final documentation
    """,
)

# Form the squad
squad = Squad(
    supervisor=supervisor,
    agents=[ResearchAgent(), AnalystAgent(), WriterAgent()],
)

# Execute
result = await squad.run("Research AI trends and write a report")
```

### When to Use Supervisor

- Clear task decomposition
- Quality control needed
- Results require synthesis
- Agents have distinct roles

## Swarm Pattern

Agents work as peers with shared state, no central coordinator.

```python
from agentorchestrator.squad import Swarm

# Agents collaborate as equals
swarm = Swarm(
    agents=[
        BrainstormAgent(),
        CriticAgent(),
        RefinerAgent(),
    ],
    shared_memory=SharedMemory(),
    max_rounds=5,
)

result = await swarm.run("Design a new product feature")
```

### When to Use Swarm

- Emergent problem-solving
- Debate/consensus needed
- No clear hierarchy
- Creative tasks

## Network Pattern

Agents route tasks to each other based on capability.

```python
from agentorchestrator.squad import AgentNetwork, route

class TriageAgent(BaseAgent):
    @route(to=["technical", "billing", "general"])
    async def route_request(self, request: str) -> str:
        """Determine which agent should handle this."""
        ...

network = AgentNetwork(
    router=TriageAgent(),
    agents={
        "technical": TechnicalSupportAgent(),
        "billing": BillingAgent(),
        "general": GeneralHelpAgent(),
    },
)

result = await network.handle("I can't log into my account")
```

### When to Use Network

- Customer support routing
- Skill-based task assignment
- Dynamic workflows

## Context Isolation

In multi-agent systems, **context isolation** prevents agents from seeing each other's work-in-progress:

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    IsolationLevel,
)

# Supervisor creates isolation manager
isolation = ContextIsolationManager(coordinator_context=ctx)

# Each agent gets isolated namespace
for agent in squad.agents:
    namespace = isolation.create_namespace(
        agent.id,
        isolation_level=IsolationLevel.FULL,
    )
    agent.namespace = namespace

# Share only what's needed
isolation.share_with_all("query", user_query)
isolation.share_between("researcher", "findings", ["analyst", "writer"])
```

See [Context Isolation Pattern](../patterns/context_isolation.md) for full details.

## Result Aggregation

Combine outputs from multiple agents:

```python
from agentorchestrator.squad.context import (
    ResultAggregator,
    AggregationStrategy,
)

aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)

# Collect results
for agent in squad.agents:
    aggregator.add_result(
        agent_id=agent.id,
        data=agent.namespace.get_result(),
        confidence=agent.get_confidence(),
    )

# Synthesize with LLM
final = await aggregator.aggregate(llm=llm_client)
print(final.data)  # Unified narrative
```

### Aggregation Strategies

| Strategy | Description | Best For |
|----------|-------------|----------|
| `SYNTHESIZE` | LLM creates narrative from all results | Research, reports |
| `MERGE` | Deep merge dicts/lists | Structured data |
| `PRIORITIZE` | Pick highest confidence | Classification |
| `VOTE` | Majority voting | Discrete answers |
| `CHAIN` | Sequential refinement | Iterative improvement |
| `CONCAT` | Simple concatenation | Logs, timelines |

## Decision Matrix

| Need | Pattern | Complexity |
|------|---------|------------|
| Coordinate specialists | Supervisor | Low |
| Peer collaboration | Swarm | Medium |
| Dynamic routing | Network | Medium |
| Full control | Supervisor | Low |
| Emergent solutions | Swarm | High |
| Scalability | Network | High |

## Best Practices

!!! tip "Start with Supervisor"
    It's the simplest pattern and handles most use cases well.

!!! tip "Isolate Contexts"
    Always use context isolation for 3+ agents to prevent context pollution.

!!! tip "Define Clear Handoffs"
    Document when and why agents pass work to each other.

!!! warning "Monitor Token Usage"
    Multi-agent systems can consume tokens quickly. Use summarization middleware.

## Next Steps

- [Context Isolation Pattern](../patterns/context_isolation.md) - Deep dive into isolation
- [Summarization Pattern](../patterns/summarization.md) - Manage large outputs
- [Routing Pattern](../patterns/routing.md) - Dynamic agent selection
