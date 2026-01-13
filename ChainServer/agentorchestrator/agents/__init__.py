"""
AgentOrchestrator Agents Module

Provides base classes for building data agents.

Base Classes:
    - BaseAgent: Abstract base for all agents
    - AgentResult: Standard result container
    - CompositeAgent: Combines multiple agents
    - ResilientAgent: Adds retry/circuit breaker to any agent
    - ResilientCompositeAgent: Composite with built-in resilience

Agent Squad Integration:
    - SupervisorAgent: Lead agent coordinates team agents
    - AgentSquadBridge: Bridge for intelligent routing
    - AOAgentAdapter: Wrap AO agents for Agent Squad

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

    # Use supervisor pattern (Agent Squad integration)
    from agentorchestrator.agents import SupervisorAgent, SupervisorConfig

    supervisor = SupervisorAgent(
        team=[agent1, agent2, agent3],
        config=SupervisorConfig(lead_model="anthropic.claude-3-sonnet"),
    )
    result = await supervisor.fetch("Analyze company financials")
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

# Agent Squad integration (lazy imports to avoid requiring agent-squad)
from agentorchestrator.integrations.agent_squad import (
    # Core classes
    AgentSquadBridge,
    AgentSquadConfig,
    AOAgentAdapter,
    SupervisorAgent,
    SupervisorConfig,
    # Enums
    ResponseStrategy,
    RoutingStrategy,
    # Pluggable interfaces
    ConversationMemoryStore,
    InMemoryStore,
    AgentClassifier,
    KeywordClassifier,
    LLMClassifier,
    LLMGatewayClassifier,  # Uses your LLM Gateway with OAuth
    ResponseHandler,
    # Utilities
    create_squad_from_agents,
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
    # Agent Squad integration - Core
    "SupervisorAgent",
    "SupervisorConfig",
    "AgentSquadBridge",
    "AgentSquadConfig",
    "AOAgentAdapter",
    # Agent Squad integration - Enums
    "ResponseStrategy",
    "RoutingStrategy",
    # Agent Squad integration - Pluggable interfaces
    "ConversationMemoryStore",
    "InMemoryStore",
    "AgentClassifier",
    "KeywordClassifier",
    "LLMClassifier",
    "LLMGatewayClassifier",  # Uses your LLM Gateway with OAuth
    "ResponseHandler",
    # Utilities
    "create_squad_from_agents",
]