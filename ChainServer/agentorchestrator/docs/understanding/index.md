# Understanding AgentOrchestrator

This section covers the core concepts you need to understand how AgentOrchestrator works.

## Core Concepts

<div class="grid cards" markdown>

-   :material-cube-outline:{ .lg .middle } **[Context](context.md)**

    ---

    The shared state container that flows through your pipeline. Learn about scopes, storage, and data flow.

-   :material-cogs:{ .lg .middle } **[Steps & Chains](steps_and_chains.md)**

    ---

    Building blocks of pipelines. Steps are functions, chains combine them into DAGs.

-   :material-account-supervisor:{ .lg .middle } **[Agents](agents.md)**

    ---

    LLM-powered components with tools, memory, and reasoning. Build from BaseAgent or ResilientAgent.

-   :material-account-group:{ .lg .middle } **[Multi-Agent Systems](multi_agent.md)**

    ---

    Coordinate multiple agents with supervisors, squads, and routing strategies.

</div>

## How It All Fits Together

```
                    ┌─────────────────────────────────────┐
                    │         AgentOrchestrator           │
                    │   (Central facade, config, registry) │
                    └───────────────┬─────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
    ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
    │      Steps      │   │     Agents      │   │     Chains      │
    │  (Pure functions │   │  (LLM + Tools)  │   │  (DAG of steps) │
    │   for data flow) │   │                 │   │                 │
    └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
             │                     │                     │
             └─────────────────────┼─────────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────────────┐
                    │            ChainContext             │
                    │   (Shared state, scopes, storage)   │
                    └─────────────────────────────────────┘
```

## Learning Path

1. **Start with [Context](context.md)** - Understand how data flows through pipelines
2. **Learn [Steps & Chains](steps_and_chains.md)** - Build your first pipelines
3. **Add [Agents](agents.md)** - Power steps with LLMs
4. **Scale with [Multi-Agent Systems](multi_agent.md)** - Coordinate specialized agents
