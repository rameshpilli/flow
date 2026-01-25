"""
Context Isolation for Multi-Agent Systems.

This module implements the Manus-style "context isolation" pattern where each
sub-agent operates in its own isolated namespace, preventing context pollution
and enabling clean result aggregation.

Key Components:
    - AgentContextNamespace: Isolated context for each agent
    - ContextIsolationManager: Creates and manages agent namespaces
    - ResultAggregator: Collects and synthesizes agent outputs

Why Context Isolation?
    Without isolation, if a root agent passes its full history to each sub-agent,
    you get context explosion: N agents × full context = massive token usage.

    With isolation:
    - Each agent sees only what it needs
    - Coordinator mediates all data sharing
    - Results are aggregated cleanly
    - Scales linearly with agent count

Usage:
    from agentorchestrator.squad.context import (
        ContextIsolationManager,
        ResultAggregator,
        AggregationStrategy,
    )

    # Create isolation manager for a supervisor
    isolation = ContextIsolationManager(coordinator_context=ctx)

    # Create isolated namespaces for each agent
    for agent in team:
        agent.namespace = isolation.create_namespace(agent.id)

    # Execute agents in parallel with isolated contexts
    async with isolation.execute_isolated(agents, query) as results:
        # Each agent only saw its own context
        pass

    # Aggregate results
    aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
    for agent in team:
        aggregator.add_result(agent.id, agent.namespace.get_result())

    final = await aggregator.aggregate(llm=llm)

References:
    - Manus: "Share memory by communicating, don't communicate by sharing memory"
    - Google ADK: Context compaction at session layer
    - LangChain: Context engineering for agents
"""

from agentorchestrator.squad.context.namespace import (
    AgentContextNamespace,
    IsolationLevel,
)
from agentorchestrator.squad.context.isolation import (
    ContextIsolationManager,
)
from agentorchestrator.squad.context.aggregator import (
    ResultAggregator,
    AggregationStrategy,
    AgentResult,
    AggregatedResult,
)

__all__ = [
    # Namespace
    "AgentContextNamespace",
    "IsolationLevel",
    # Manager
    "ContextIsolationManager",
    # Aggregator
    "ResultAggregator",
    "AggregationStrategy",
    "AgentResult",
    "AggregatedResult",
]
