"""
Agent implementations for the Multi-Agent Squad module.

Provides base agent interface and concrete implementations
that work with the corporate LLM Gateway.
"""

from agentorchestrator.squad.agents.base import (
    Agent,
    AgentOptions,
    AgentStreamResponse,
)
from agentorchestrator.squad.agents.llm_gateway_agent import (
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)
from agentorchestrator.squad.agents.supervisor import (
    SupervisorAgent,
    SupervisorAgentOptions,
)

__all__ = [
    # Base
    "Agent",
    "AgentOptions",
    "AgentStreamResponse",
    # LLM Gateway Agent
    "LLMGatewayAgent",
    "LLMGatewayAgentOptions",
    # Supervisor
    "SupervisorAgent",
    "SupervisorAgentOptions",
]
