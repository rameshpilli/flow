"""
Agent implementations for the Multi-Agent Squad module.

Provides base agent interface and concrete implementations
that work with the corporate LLM Gateway.

Classes:
    Agent: Abstract base class for all agents.
    AgentOptions: Base configuration for agents.
    AgentStreamResponse: Streaming response container.
    LLMGatewayAgent: Agent using corporate LLM Gateway.
    LLMGatewayAgentOptions: Configuration for LLMGatewayAgent.
    SupervisorAgent: Coordinates a team of specialist agents.
    SupervisorAgentOptions: Configuration for SupervisorAgent.
    FunctionAgent: Agent with explicit handoff capabilities.
    FunctionAgentOptions: Configuration for FunctionAgent.
    HandoffResult: Result of agent-to-agent handoff.
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
from agentorchestrator.squad.agents.function_agent import (
    FunctionAgent,
    FunctionAgentOptions,
    HandoffResult,
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
    # Function Agent with Handoffs
    "FunctionAgent",
    "FunctionAgentOptions",
    "HandoffResult",
]
