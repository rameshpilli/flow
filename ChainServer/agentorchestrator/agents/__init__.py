"""
AgentOrchestrator Agents Module

Provides base classes for building data agents.

Base Classes:
    - BaseAgent: Abstract base for all agents
    - AgentResult: Standard result container
    - CompositeAgent: Combines multiple agents
    - ResilientAgent: Adds retry/circuit breaker to any agent
    - ResilientCompositeAgent: Composite with built-in resilience

Usage:
    from agentorchestrator.agents import BaseAgent, AgentResult

    class MyAgent(BaseAgent):
        async def fetch(self, query: str, **kwargs) -> AgentResult:
            data = await self.call_api(query)
            return AgentResult(data=data, source="my_source", query=query)

    # Wrap with resilience
    from agentorchestrator.agents import ResilientAgent, ResilientAgentConfig

    resilient = ResilientAgent(
        agent=MyAgent(),
        config=ResilientAgentConfig(timeout_seconds=10, max_retries=3),
    )
"""

from agentorchestrator.agents.base import (
    AgentResult,
    BaseAgent,
    CompositeAgent,
    ResilienceConfig,  # Backward compatibility alias
    ResilientAgent,
    ResilientAgentConfig,
    ResilientCompositeAgent,
)

__all__ = [
    # Base classes
    "BaseAgent",
    "AgentResult",
    "CompositeAgent",
    # Resilient wrappers
    "ResilientAgent",
    "ResilientAgentConfig",
    "ResilienceConfig",  # Alias for ResilientAgentConfig
    "ResilientCompositeAgent",
]
