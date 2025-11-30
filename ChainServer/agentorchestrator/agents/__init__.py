"""AgentOrchestrator Agents Module"""

from agentorchestrator.agents.base import (
    AgentResult,
    BaseAgent,
    CompositeAgent,
    ResilienceConfig,  # Backward compatibility alias
    ResilientAgent,
    ResilientAgentConfig,
    ResilientCompositeAgent,
)
from agentorchestrator.agents.data_agents import (
    EarningsAgent,
    NewsAgent,
    SECFilingAgent,
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
    # Data agents
    "SECFilingAgent",
    "NewsAgent",
    "EarningsAgent",
]
