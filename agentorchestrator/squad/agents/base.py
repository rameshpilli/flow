"""
AgentOrchestrator Squad Agent Base
==================================

This module provides the base classes for agents in the Multi-Agent Squad system.

Agents in the Squad module process user requests and generate responses. Unlike
data-fetching agents in agentorchestrator.agents, these agents are designed for
conversational AI with support for chat history, session management, and streaming.

Classes:
    AgentOptions: Configuration dataclass for agent settings.
    Agent: Abstract base class that all squad agents must inherit from.
    AgentStreamResponse: Dataclass for streaming response chunks.

Usage:
    from agentorchestrator.squad.agents import Agent, AgentOptions

    class MyAgent(Agent):
        async def process_request(
            self,
            input_text: str,
            user_id: str,
            session_id: str,
            chat_history: list[ConversationMessage],
            additional_params: Optional[dict] = None,
        ) -> ConversationMessage:
            # Process the request and return response
            return ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": "My response"}]
            )

Example:
    >>> from agentorchestrator.squad.agents import Agent, AgentOptions
    >>> from agentorchestrator.squad.types import ConversationMessage, ParticipantRole
    >>>
    >>> options = AgentOptions(
    ...     name="Support Agent",
    ...     description="Handles customer support inquiries",
    ...     save_chat=True,
    ...     log_debug=True,
    ... )
    >>>
    >>> class SupportAgent(Agent):
    ...     async def process_request(self, input_text, user_id, session_id, chat_history, additional_params=None):
    ...         return ConversationMessage(
    ...             role=ParticipantRole.ASSISTANT.value,
    ...             content=[{"text": f"I can help you with: {input_text}"}]
    ...         )
    >>>
    >>> agent = SupportAgent(options)
    >>> print(agent.id)  # "support-agent"

See Also:
    - agentorchestrator.squad.agents.llm_gateway_agent: LLM-powered agent implementation.
    - agentorchestrator.squad.types: ConversationMessage and related types.
    - agentorchestrator.squad.storage: Chat history persistence.
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
    Configuration options for a squad agent.

    This dataclass holds all configuration needed to initialize an agent
    in the Multi-Agent Squad system.

    Attributes:
        name (str): Display name of the agent. Used for identification
            and logging. Will be converted to a URL-safe ID.
            Example: "Tech Support Agent" -> "tech-support-agent"
        description (str): Description of the agent's capabilities.
            Used by orchestrators to route requests to appropriate agents.
        save_chat (bool): Whether to persist chat history for this agent.
            Default: True. Set to False for stateless agents.
        log_debug (bool): Enable debug-level logging for this agent.
            Default: False. Useful for development and troubleshooting.

    Example:
        >>> options = AgentOptions(
        ...     name="Financial Analyst",
        ...     description="Analyzes financial data and market trends",
        ...     save_chat=True,
        ...     log_debug=True,
        ... )
        >>> print(options.name)  # "Financial Analyst"

    See Also:
        Agent: Uses AgentOptions for initialization.
        LLMGatewayAgentOptions: Extended options for LLM agents.
    """

    name: str
    description: str
    save_chat: bool = True
    log_debug: bool = False


class Agent(ABC):
    """
    Abstract base class for all agents in the Multi-Agent Squad system.

    Agents process user requests and generate conversational responses.
    They support session-based chat history, streaming, and integration
    with the MultiAgentOrchestrator for routing and coordination.

    Attributes:
        name (str): Display name of the agent.
        id (str): URL-safe identifier generated from name.
        description (str): Description of agent capabilities.
        save_chat (bool): Whether chat history is persisted.
        log_debug (bool): Whether debug logging is enabled.

    Methods:
        generate_key_from_name(): Static method to create URL-safe ID.
        is_streaming_enabled(): Check if agent supports streaming.
        process_request(): Process user input and return response (abstract).

    Example:
        >>> from agentorchestrator.squad.agents import Agent, AgentOptions
        >>> from agentorchestrator.squad.types import ConversationMessage, ParticipantRole
        >>>
        >>> class EchoAgent(Agent):
        ...     async def process_request(
        ...         self,
        ...         input_text: str,
        ...         user_id: str,
        ...         session_id: str,
        ...         chat_history: list[ConversationMessage],
        ...         additional_params: Optional[dict] = None,
        ...     ) -> ConversationMessage:
        ...         return ConversationMessage(
        ...             role=ParticipantRole.ASSISTANT.value,
        ...             content=[{"text": f"You said: {input_text}"}]
        ...         )
        >>>
        >>> options = AgentOptions(name="Echo", description="Echoes input")
        >>> agent = EchoAgent(options)
        >>> # Use with orchestrator
        >>> orchestrator.add_agent(agent)

    Streaming Support:
        Override is_streaming_enabled() to return True and return an
        AsyncIterable from process_request() for streaming responses.

        >>> class StreamingAgent(Agent):
        ...     def is_streaming_enabled(self) -> bool:
        ...         return True
        ...
        ...     async def process_request(self, ...) -> AsyncIterable[AgentStreamResponse]:
        ...         async for chunk in stream_response():
        ...             yield AgentStreamResponse(text=chunk)

    See Also:
        AgentOptions: Configuration for agents.
        LLMGatewayAgent: Full implementation using LLM Gateway.
        MultiAgentOrchestrator: Coordinates multiple agents.
    """

    def __init__(self, options: AgentOptions):
        """
        Initialize the agent with configuration options.

        Args:
            options (AgentOptions): Configuration containing name,
                description, and behavior settings.

        Example:
            >>> options = AgentOptions(
            ...     name="My Agent",
            ...     description="Does helpful things",
            ... )
            >>> agent = MyAgent(options)
            >>> print(agent.name)  # "My Agent"
            >>> print(agent.id)    # "my-agent"
        """
        self.name = options.name
        self.id = self.generate_key_from_name(options.name)
        self.description = options.description
        self.save_chat = options.save_chat
        self.log_debug = options.log_debug

    @staticmethod
    def generate_key_from_name(name: str) -> str:
        """
        Generate a URL-safe identifier from an agent name.

        Converts the agent's display name into a lowercase,
        hyphen-separated ID suitable for URLs and keys.

        Args:
            name (str): The agent's display name.
                Example: "Tech Support Agent"

        Returns:
            str: Lowercase, hyphenated identifier.
                Example: "tech-support-agent"

        Example:
            >>> Agent.generate_key_from_name("Financial Analyst 2.0")
            'financial-analyst-20'
            >>> Agent.generate_key_from_name("Q&A Bot")
            'qa-bot'

        Note:
            Special characters are removed, spaces become hyphens,
            and the result is lowercased.
        """
        # Remove special characters and replace spaces with hyphens
        key = re.sub(r"[^a-zA-Z0-9\s-]", "", name)
        key = re.sub(r"\s+", "-", key)
        return key.lower()

    def is_streaming_enabled(self) -> bool:
        """
        Check if this agent supports streaming responses.

        Override this method in subclasses that support streaming.
        When True, process_request() should return an AsyncIterable
        of AgentStreamResponse objects.

        Returns:
            bool: True if streaming is supported, False otherwise.
                Default: False.

        Example:
            >>> class StreamingAgent(Agent):
            ...     def is_streaming_enabled(self) -> bool:
            ...         return True
            >>>
            >>> agent = StreamingAgent(options)
            >>> if agent.is_streaming_enabled():
            ...     async for chunk in await agent.process_request(...):
            ...         print(chunk.text)

        See Also:
            AgentStreamResponse: Streaming response chunk type.
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

        This is the main method that agents must implement. It receives
        the user's input along with context (history, session info) and
        returns a response message.

        Args:
            input_text (str): The user's input message to process.
            user_id (str): Unique identifier for the user making the request.
                Used for personalization and history retrieval.
            session_id (str): Unique identifier for the conversation session.
                Groups related messages together.
            chat_history (list[ConversationMessage]): Previous messages in
                this conversation. Use for context-aware responses.
            additional_params (dict[str, Any] | None): Optional extra parameters.
                Common keys include:
                - rag_context: Retrieved documents for RAG
                - user_profile: User preferences/metadata
                - session_data: Session-specific data

        Returns:
            ConversationMessage: The agent's response message.
            AsyncIterable[AgentStreamResponse]: For streaming agents,
                yields response chunks.

        Raises:
            NotImplementedError: If not overridden by subclass.

        Example:
            >>> async def process_request(
            ...     self,
            ...     input_text: str,
            ...     user_id: str,
            ...     session_id: str,
            ...     chat_history: list[ConversationMessage],
            ...     additional_params: Optional[dict] = None,
            ... ) -> ConversationMessage:
            ...     # Use chat history for context
            ...     context = "\\n".join(m.get_text() for m in chat_history[-5:])
            ...
            ...     # Process with your logic
            ...     response = await self.generate_response(input_text, context)
            ...
            ...     return ConversationMessage(
            ...         role=ParticipantRole.ASSISTANT.value,
            ...         content=[{"text": response}]
            ...     )

        See Also:
            ConversationMessage: Return type for responses.
            AgentStreamResponse: Chunk type for streaming.
        """
        pass

    def _log_debug(self, message: str, data: Any = None) -> None:
        """
        Log a debug message if debug logging is enabled.

        Args:
            message (str): The message to log.
            data (Any | None): Optional data to include in the log.
                Will be appended after a colon.

        Example:
            >>> self._log_debug("Processing input", {"length": len(input_text)})
            # Logs: "[AgentName] Processing input: {'length': 42}"
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

    Used when an agent returns responses incrementally (streaming).
    Each chunk contains a text fragment, and the final chunk includes
    the complete message.

    Attributes:
        text (str): Current text chunk being streamed. Default: "".
            For intermediate chunks, contains partial text.
        final_message (ConversationMessage | None): Complete message
            when streaming is finished. Default: None.
            Only set on the final chunk.

    Example:
        >>> # Streaming agent implementation
        >>> async def process_request(self, ...) -> AsyncIterable[AgentStreamResponse]:
        ...     full_text = ""
        ...     async for token in llm_stream:
        ...         full_text += token
        ...         yield AgentStreamResponse(text=token)
        ...
        ...     # Final chunk with complete message
        ...     yield AgentStreamResponse(
        ...         text="",
        ...         final_message=ConversationMessage(
        ...             role=ParticipantRole.ASSISTANT.value,
        ...             content=[{"text": full_text}]
        ...         )
        ...     )

    Consumer Example:
        >>> async for chunk in agent.process_request(...):
        ...     if chunk.final_message:
        ...         # Streaming complete
        ...         save_message(chunk.final_message)
        ...     else:
        ...         # Stream partial text to user
        ...         print(chunk.text, end="", flush=True)

    See Also:
        Agent.is_streaming_enabled(): Check if agent supports streaming.
        Agent.process_request(): Returns this type for streaming agents.
    """

    text: str = ""
    final_message: Optional[ConversationMessage] = None