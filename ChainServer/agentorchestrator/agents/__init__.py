"""
AgentOrchestrator Agents Module

Provides base classes for building data agents.

Base Classes:
    - BaseAgent: Abstract base for all agents
    - AgentResult: Standard result container
    - CompositeAgent: Combines multiple agents
    - ResilientAgent: Adds retry/circuit breaker to any agent
    - ResilientCompositeAgent: Composite with built-in resilience

Agent Patterns:
    - ReActAgent: Industry-standard Thought→Action→Observation loop
    - Tool/ToolRegistry: Centralized tool discovery and management

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

    # Use ReAct pattern
    from agentorchestrator.agents import ReActAgent, ToolRegistry

    registry = ToolRegistry()
    registry.register("search", search_func, "Search the web")

    agent = ReActAgent(llm_client, tools=registry.list_tools())
    result = await agent.run("What is the capital of France?")
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
from agentorchestrator.agents.react import (
    ReActAgent,
    ReActConfig,
    ReActResult,
    ReActStep,
    StepType,
    Tool,
    ToolResult,
    create_react_agent,
)
from agentorchestrator.agents.tools import (
    ToolRegistry,
    ToolDefinition,
    ToolCategory,
    ToolExecutionResult,
    get_default_registry,
    tool,
    register_builtin_tools,
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
    # ReAct pattern
    "ReActAgent",
    "ReActConfig",
    "ReActResult",
    "ReActStep",
    "StepType",
    "Tool",
    "ToolResult",
    "create_react_agent",
    # Tool Registry
    "ToolRegistry",
    "ToolDefinition",
    "ToolCategory",
    "ToolExecutionResult",
    "get_default_registry",
    "tool",
    "register_builtin_tools",
]
