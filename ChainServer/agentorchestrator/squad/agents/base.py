"""
Base Agent interface for the Multi-Agent Squad module.

Defines the abstract Agent interface that all agent implementations
must follow for compatibility with the MultiAgentOrchestrator.
"""

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Union, AsyncIterable

from agentorchestrator.squad.types import (
    ConversationMessage,
    ParticipantRole,
    AgentTools,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentOptions:
    """
    Configuration options for an agent.

    Attributes:
        name: Display name of the agent
        description: Description of the agent's capabilities
        save_chat: Whether to save chat history for this agent
        log_debug: Enable debug logging for this agent
    """
    name: str
    description: str
    save_chat: bool = True
    log_debug: bool = False


class Agent(ABC):
    """
    Abstract base class for all agents in the Squad system.

    Agents process user requests and generate responses.
    They can be specialized for different domains or tasks.

    Example:
        ```python
        class MyAgent(Agent):
            async def process_request(
                self,
                input_text: str,
                user_id: str,
                session_id: str,
                chat_history: list[ConversationMessage],
                additional_params: Optional[dict] = None,
            ) -> ConversationMessage:
                # Process and return response
                return ConversationMessage(
                    role=ParticipantRole.ASSISTANT.value,
                    content=[{"text": "My response"}]
                )
        ```
    """

    def __init__(self, options: AgentOptions):
        """
        Initialize the agent.

        Args:
            options: Agent configuration options
        """
        self.name = options.name
        self.id = self.generate_key_from_name(options.name)
        self.description = options.description
        self.save_chat = options.save_chat
        self.log_debug = options.log_debug

    @staticmethod
    def generate_key_from_name(name: str) -> str:
        """
        Generate a standardized ID from agent name.

        Args:
            name: Agent display name

        Returns:
            Lowercase, hyphenated ID
        """
        # Remove special characters and replace spaces with hyphens
        key = re.sub(r"[^a-zA-Z0-9\s-]", "", name)
        key = re.sub(r"\s+", "-", key)
        return key.lower()

    def is_streaming_enabled(self) -> bool:
        """
        Whether this agent supports streaming responses.

        Returns:
            True if streaming is supported
        """
        return False

    @abstractmethod
    async def process_request(
        self,
        input_text: str,
        user_id: str,
        session_id: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]] = None,
    ) -> Union[ConversationMessage, AsyncIterable[Any]]:
        """
        Process a user request and generate a response.

        Args:
            input_text: The user's input text
            user_id: User identifier
            session_id: Session identifier
            chat_history: Previous conversation messages
            additional_params: Optional additional parameters

        Returns:
            ConversationMessage or async iterable for streaming
        """
        pass

    def _log_debug(self, message: str, data: Any = None) -> None:
        """
        Log debug message if debug logging is enabled.

        Args:
            message: Message to log
            data: Optional data to include
        """
        if self.log_debug:
            if data:
                logger.debug(f"[{self.name}] {message}: {data}")
            else:
                logger.debug(f"[{self.name}] {message}")


@dataclass
class AgentStreamResponse:
    """
    Represents a streaming response chunk from an agent.

    Attributes:
        text: Current text chunk
        final_message: Complete message when streaming is done
    """
    text: str = ""
    final_message: Optional[ConversationMessage] = None
