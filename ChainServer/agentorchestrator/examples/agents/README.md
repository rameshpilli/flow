# Agent Examples

Multi-agent orchestration patterns and coordination examples.

## Overview

AgentOrchestrator supports multiple agent patterns:

| Pattern | Description | Use Case |
|---------|-------------|----------|
| Supervisor | Central coordinator delegates to specialists | Research, analysis |
| Squad | Team of agents with shared context | Complex workflows |
| Resilient | Fault-tolerant agent wrapper | Production systems |

## Examples

### 1. Supervisor Chain

Supervisor coordinating specialized agents.

```bash
python supervisor_chain.py
```

**What you'll learn:**
- Creating specialized agents (researcher, analyst)
- Supervisor delegation patterns
- Result aggregation strategies

### 2. Financial Research Agent

Deep research agent with multiple data sources.

```bash
python financial_research_agent.py
```

**What you'll learn:**
- Multi-source data gathering
- Context isolation for parallel agents
- Report generation pipelines

## Quick Reference

### LLMGatewayAgent

```python
from agentorchestrator.squad import LLMGatewayAgent

agent = LLMGatewayAgent(
    name="researcher",
    instructions="Find and analyze information on given topics.",
    llm_client=client,
)

response = await agent.process_message("Research AI trends")
```

### SupervisorAgent

```python
from agentorchestrator.squad import SupervisorAgent

supervisor = SupervisorAgent(
    name="coordinator",
    team=[researcher, analyst, writer],
    llm_client=client,
)

result = await supervisor.process_message("Analyze market trends and write report")
```

### Context Isolation

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
)

# Isolate each agent's context
isolation = ContextIsolationManager(ctx)
for agent in team:
    isolation.create_namespace(agent.id)

# Share only necessary data
isolation.share_with_all("query", user_query)

# Aggregate results
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
final = await aggregator.aggregate(llm=client)
```

## Architecture

### Supervisor Pattern

```
                    ┌─────────────────┐
                    │   Supervisor    │
                    │  (Coordinator)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │Researcher│  │ Analyst  │  │  Writer  │
        └──────────┘  └──────────┘  └──────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Aggregated     │
                    │    Result       │
                    └─────────────────┘
```

### Context Isolation

```
        Coordinator Context
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│Agent A │ │Agent B │ │Agent C │
│Context │ │Context │ │Context │
│(isolated)│(isolated)│(isolated)│
└────────┘ └────────┘ └────────┘
```

## Best Practices

1. **Use Context Isolation** - Prevents context pollution between agents
2. **Define Clear Roles** - Each agent should have specific instructions
3. **Handle Failures** - Use ResilientAgent for production systems
4. **Aggregate Strategically** - Choose the right aggregation strategy for your use case
