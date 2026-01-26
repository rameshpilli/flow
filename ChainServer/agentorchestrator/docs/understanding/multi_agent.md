# Multi-Agent Systems

When a single agent isn't enough, **multi-agent systems** let you coordinate specialized agents to tackle complex tasks.

> **Implementation Status:**
> - ✅ **Supervisor Pattern** - Fully implemented (`SupervisorAgent`, `Squad`)
> - ✅ **Context Isolation** - Fully implemented (`IsolationLevel`, `ContextIsolationManager`)
> - ✅ **FunctionAgent Handoffs** - Implemented (`FunctionAgent.handoff()`)
> - 🚧 **Swarm Pattern** - Planned for future release
> - 🚧 **Network Pattern** - Planned for future release

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

## Supervisor Pattern ✅

A supervisor agent coordinates sub-agents, delegating tasks and aggregating results.

```python
from agentorchestrator.squad import (
    Squad,
    SquadOptions,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)

# Create specialist agents
research_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Researcher",
    description="Find and gather information on topics.",
))

analyst_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Analyst",
    description="Analyze data and provide insights.",
))

writer_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Writer",
    description="Write clear, compelling content.",
))

# Create supervisor (lead agent)
lead = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="ProjectLead",
    description="Coordinates team to answer complex questions",
))

# Form the squad
squad = Squad(
    supervisor=lead,
    agents=[research_agent, analyst_agent, writer_agent],
    options=SquadOptions(trace=True),
)

# Execute
result = await squad.run("Research AI trends and write a report")
print(result.content)
```

### When to Use Supervisor

- Clear task decomposition
- Quality control needed
- Results require synthesis
- Agents have distinct roles

## Swarm Pattern 🚧

> **Status:** Planned for future release. Not yet implemented.

Agents work as peers with shared state, no central coordinator.
This pattern is useful for emergent problem-solving and consensus-based tasks.

```python
# PLANNED - Not yet available
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

### When to Use Swarm (Future)

- Emergent problem-solving
- Debate/consensus needed
- No clear hierarchy
- Creative tasks

## Network Pattern 🚧

> **Status:** Planned for future release. Not yet implemented.

Agents route tasks to each other based on capability.
For current use cases, consider using `MultiAgentOrchestrator` with a classifier.

```python
# PLANNED - Not yet available
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

### Current Alternative: MultiAgentOrchestrator

For intent-based routing, use the implemented `MultiAgentOrchestrator`:

```python
from agentorchestrator.squad import (
    MultiAgentOrchestrator,
    LLMGatewayClassifier,
    LLMGatewayAgent,
)

orchestrator = MultiAgentOrchestrator(
    classifier=LLMGatewayClassifier(),
)
orchestrator.add_agent(technical_agent)
orchestrator.add_agent(billing_agent)

# Classifier routes to the right agent
response = await orchestrator.route_request(
    "I can't log into my account",
    user_id="user-1",
)
```

### When to Use Network (Future)

- Customer support routing
- Skill-based task assignment
- Dynamic workflows

## Agent Handoffs ✅

AgentOrchestrator supports two types of handoffs:

### 1. Explicit Handoff (FunctionAgent)
Use `FunctionAgent` for explicit agent-to-agent delegation with context transfer:

```python
from agentorchestrator.squad import FunctionAgent, FunctionAgentOptions

# Create agents with handoff permissions
researcher = FunctionAgent(FunctionAgentOptions(
    name="Researcher",
    description="Gathers information",
    can_handoff_to=["Writer"],  # Can only hand off to Writer
))

writer = FunctionAgent(FunctionAgentOptions(
    name="Writer",
    description="Writes reports",
    can_handoff_to=["User"],  # Terminal - returns to user
))

# Researcher hands off to Writer with context
handoff = await researcher.handoff(
    to_agent="Writer",
    context={"findings": findings, "sources": sources},
    message="Research complete. Please write a summary.",
)
```

### 2. Automatic Signal Handoff (MultiAgentOrchestrator)
Agents can now signal a handoff in their response metadata. The `MultiAgentOrchestrator` will automatically re-route to the new agent without user intervention.

```python
# In your agent's process_request:
return ConversationMessage(
    role="assistant",
    content=[{"text": "I'm handing you over to the Finance expert."}],
    handoff_to="finance-agent"  # Signal automatic handoff
)
```

The orchestrator allows up to 3 consecutive automatic handoffs to prevent loops.

## Context Isolation ✅

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

## Result Aggregation ✅

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
