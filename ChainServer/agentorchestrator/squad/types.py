"""
Type definitions for the Multi-Agent Squad module.

These types are used across the squad module for consistent
data structures and type safety.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TYPE_CHECKING, Union
from datetime import datetime

if TYPE_CHECKING:
    from agentorchestrator.squad.agents.base import Agent


class ParticipantRole(str, Enum):
    """Role of a participant in a conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ConversationMessage:
    """
    Represents a message in a conversation.

    Attributes:
        role: The role of the message sender (user, assistant, system)
        content: List of content blocks (text, etc.)
    """
    role: str
    content: list[dict[str, Any]]

    def get_text(self) -> str:
        """Extract text content from the message."""
        for block in self.content:
            if "text" in block:
                return block.get("text", "")
        return ""


@dataclass
class TimestampedMessage(ConversationMessage):
    """
    A conversation message with timestamp.

    Attributes:
        role: The role of the message sender
        content: List of content blocks
        timestamp: When the message was created
    """
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ClassifierResult:
    """
    Result from intent classification.

    Attributes:
        selected_agent: The agent selected to handle the request (or None)
        confidence: Confidence score (0.0 to 1.0)
    """
    selected_agent: Optional["Agent"] = None
    confidence: float = 0.0


@dataclass
class AgentProcessingResult:
    """
    Metadata about an agent's processing result.

    Attributes:
        user_input: The original user input
        agent_id: ID of the agent that processed the request
        agent_name: Name of the agent
        user_id: ID of the user
        session_id: ID of the session
        additional_params: Any additional parameters
    """
    user_input: str
    agent_id: str
    agent_name: str
    user_id: str
    session_id: str
    additional_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """
    Complete response from an agent.

    Attributes:
        metadata: Processing metadata
        output: The actual response (message or stream)
        streaming: Whether this is a streaming response
    """
    metadata: AgentProcessingResult
    output: Union[ConversationMessage, Any]
    streaming: bool = False


@dataclass
class SquadConfig:
    """
    Configuration for the MultiAgentOrchestrator.

    Attributes:
        LOG_AGENT_CHAT: Log agent chat messages
        LOG_CLASSIFIER_CHAT: Log classifier decisions
        LOG_CLASSIFIER_RAW_OUTPUT: Log raw classifier output
        LOG_CLASSIFIER_OUTPUT: Log parsed classifier output
        LOG_EXECUTION_TIMES: Log execution timing
        MAX_MESSAGE_PAIRS_PER_AGENT: Max conversation history per agent
        USE_DEFAULT_AGENT_IF_NONE_IDENTIFIED: Fall back to default agent
        NO_SELECTED_AGENT_MESSAGE: Message when no agent is selected
        GENERAL_ROUTING_ERROR_MSG_MESSAGE: Message on routing error
    """
    LOG_AGENT_CHAT: bool = False
    LOG_CLASSIFIER_CHAT: bool = False
    LOG_CLASSIFIER_RAW_OUTPUT: bool = False
    LOG_CLASSIFIER_OUTPUT: bool = True
    LOG_EXECUTION_TIMES: bool = True
    MAX_MESSAGE_PAIRS_PER_AGENT: int = 50
    USE_DEFAULT_AGENT_IF_NONE_IDENTIFIED: bool = True
    NO_SELECTED_AGENT_MESSAGE: str = "I'm sorry, I couldn't determine how to help with that. Could you please rephrase your request?"
    GENERAL_ROUTING_ERROR_MSG_MESSAGE: str = "An error occurred while processing your request. Please try again."


@dataclass
class AgentTool:
    """
    Represents a tool that an agent can use.

    Attributes:
        name: Tool name
        description: What the tool does
        properties: JSON schema for tool parameters
        required: List of required parameter names
        func: The function to call when tool is invoked
    """
    name: str
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    func: Optional[Callable[..., Any]] = None

    @property
    def func_description(self) -> str:
        """Get description for function calling."""
        return self.description


@dataclass
class AgentTools:
    """
    Collection of tools available to an agent.

    Attributes:
        tools: List of AgentTool objects
        callbacks: Optional callbacks for tool invocations
    """
    tools: list[AgentTool] = field(default_factory=list)
    callbacks: Optional[Any] = None

    def to_llm_tools(self) -> list[dict[str, Any]]:
        """Convert tools to LLM-compatible format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": tool.properties,
                        "required": tool.required
                    }
                }
            }
            for tool in self.tools
        ]
