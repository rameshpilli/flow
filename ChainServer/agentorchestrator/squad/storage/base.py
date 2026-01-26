"""
AgentOrchestrator Chat Storage Base
===================================

This module defines the abstract interface for conversation storage in the
Multi-Agent Squad system.

Chat storage implementations handle persistence of conversation messages
across users, sessions, and agents. This enables conversation continuity,
context retrieval, and multi-agent collaboration.

Classes:
    ChatStorage: Abstract base class for all storage implementations.

Usage:
    from agentorchestrator.squad.storage.base import ChatStorage

    class MyDatabaseStorage(ChatStorage):
        async def save_chat_message(
            self, user_id, session_id, agent_id, new_message, max_history_size=None
        ) -> bool:
            # Save to your database
            await self.db.insert(...)
            return True

        async def fetch_chat(
            self, user_id, session_id, agent_id, max_history_size=None
        ) -> list[ConversationMessage]:
            # Fetch from your database
            return await self.db.query(...)

        # Implement other abstract methods...

Example:
    >>> from agentorchestrator.squad.storage import InMemoryChatStorage
    >>> from agentorchestrator.squad.types import ConversationMessage, ParticipantRole
    >>>
    >>> storage = InMemoryChatStorage()
    >>>
    >>> # Save a message
    >>> message = ConversationMessage(
    ...     role=ParticipantRole.USER.value,
    ...     content=[{"text": "Hello!"}]
    ... )
    >>> await storage.save_chat_message(
    ...     user_id="user-1",
    ...     session_id="session-1",
    ...     agent_id="assistant",
    ...     new_message=message,
    ... )
    >>>
    >>> # Fetch history
    >>> history = await storage.fetch_chat(
    ...     user_id="user-1",
    ...     session_id="session-1",
    ...     agent_id="assistant",
    ... )

See Also:
    - agentorchestrator.squad.storage.memory: In-memory implementation.
    - agentorchestrator.squad.types: ConversationMessage and related types.
"""

from abc import ABC, abstractmethod
from typing import Optional, Union

from agentorchestrator.squad.types import ConversationMessage, TimestampedMessage


class ChatStorage(ABC):
    """
    Abstract base class for conversation storage implementations.

    Provides the interface for persisting and retrieving chat messages
    across users, sessions, and agents. Implementations can use any
    backend (memory, Redis, PostgreSQL, DynamoDB, etc.).

    Attributes:
        None (implementations may add their own).

    Methods:
        is_same_role_as_last_message(): Check for consecutive same-role messages.
        trim_conversation(): Trim conversation to maximum size.
        save_chat_message(): Save a single message (abstract).
        save_chat_messages(): Save multiple messages (abstract).
        fetch_chat(): Fetch chat history for an agent (abstract).
        fetch_all_chats(): Fetch all chats for a session (abstract).
        clear_chat(): Clear chat history (abstract).

    Example:
        >>> class RedisStorage(ChatStorage):
        ...     def __init__(self, redis_client):
        ...         self.redis = redis_client
        ...
        ...     async def save_chat_message(
        ...         self, user_id, session_id, agent_id, new_message, max_history_size=None
        ...     ) -> bool:
        ...         key = f"chat:{user_id}:{session_id}:{agent_id}"
        ...         await self.redis.rpush(key, new_message.to_json())
        ...         if max_history_size:
        ...             await self.redis.ltrim(key, -max_history_size, -1)
        ...         return True
        ...
        ...     # ... implement other methods

    Implementation Notes:
        - Implementations should be thread-safe for async operations
        - Consider connection pooling for database backends
        - Handle serialization/deserialization of ConversationMessage

    See Also:
        InMemoryChatStorage: Simple in-memory implementation.
        ConversationMessage: Message type used throughout.
    """

    def is_same_role_as_last_message(
        self,
        conversation: list[ConversationMessage],
        new_message: ConversationMessage
    ) -> bool:
        """
        Check if a new message has the same role as the last message.

        Used to detect consecutive messages from the same participant,
        which may need special handling (e.g., merging content).

        Args:
            conversation (list[ConversationMessage]): Existing conversation
                messages in chronological order.
            new_message (ConversationMessage): The new message to check.

        Returns:
            bool: True if the new message has the same role as the last
                message in the conversation, False otherwise.
                Returns False if conversation is empty.

        Example:
            >>> conv = [
            ...     ConversationMessage(role="user", content=[{"text": "Hi"}]),
            ...     ConversationMessage(role="assistant", content=[{"text": "Hello!"}]),
            ... ]
            >>> new_msg = ConversationMessage(role="assistant", content=[{"text": "How can I help?"}])
            >>> storage.is_same_role_as_last_message(conv, new_msg)
            True

        Note:
            Some LLM APIs require alternating user/assistant messages.
            Use this method to detect and handle consecutive same-role messages.
        """
        if not conversation:
            return False
        return conversation[-1].role == new_message.role

    def trim_conversation(
        self,
        conversation: list[ConversationMessage],
        max_history_size: Optional[int] = None
    ) -> list[ConversationMessage]:
        """
        Trim a conversation to the maximum history size.

        Maintains complete user/assistant message pairs by ensuring
        the trimmed size is even. This prevents orphaned messages
        that could confuse LLM context.

        Args:
            conversation (list[ConversationMessage]): The conversation
                to trim, in chronological order.
            max_history_size (int | None): Maximum number of messages
                to keep. If None, returns conversation unchanged.
                Will be adjusted to even number.

        Returns:
            list[ConversationMessage]: Trimmed conversation with at most
                max_history_size messages, adjusted to maintain pairs.

        Example:
            >>> # Trim to last 4 messages (2 complete pairs)
            >>> history = [msg1, msg2, msg3, msg4, msg5, msg6]
            >>> trimmed = storage.trim_conversation(history, max_history_size=4)
            >>> len(trimmed)
            4  # [msg3, msg4, msg5, msg6]

        Note:
            If max_history_size is odd, it will be reduced by 1 to
            ensure an even number of messages.
        """
        if max_history_size is None:
            return conversation

        # Ensure even number to maintain complete pairs
        adjusted_size = max_history_size if max_history_size % 2 == 0 else max_history_size - 1
        return conversation[-adjusted_size:]

    @abstractmethod
    async def save_chat_message(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        new_message: Union[ConversationMessage, TimestampedMessage],
        max_history_size: Optional[int] = None
    ) -> bool:
        """
        Save a single chat message to storage.

        Persists a message for a specific user/session/agent combination.
        Handles history trimming if max_history_size is specified.

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the conversation session.
            agent_id (str): Identifier of the agent involved.
            new_message (ConversationMessage | TimestampedMessage): The message
                to save. Will be converted to ConversationMessage if needed.
            max_history_size (int | None): Maximum messages to retain after
                saving. Older messages will be discarded.

        Returns:
            bool: True if the message was saved successfully, False otherwise.

        Raises:
            NotImplementedError: If not overridden by subclass.

        Example:
            >>> message = ConversationMessage(
            ...     role=ParticipantRole.USER.value,
            ...     content=[{"text": "What's the weather?"}]
            ... )
            >>> success = await storage.save_chat_message(
            ...     user_id="user-123",
            ...     session_id="session-456",
            ...     agent_id="weather-agent",
            ...     new_message=message,
            ...     max_history_size=50,
            ... )

        See Also:
            save_chat_messages(): Save multiple messages at once.
        """
        pass

    @abstractmethod
    async def save_chat_messages(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        new_messages: Union[list[ConversationMessage], list[TimestampedMessage]],
        max_history_size: Optional[int] = None
    ) -> bool:
        """
        Save multiple chat messages at once.

        Batch save for efficiency when adding multiple messages
        (e.g., user question + assistant response pair).

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.
            agent_id (str): Identifier of the agent involved.
            new_messages (list[ConversationMessage] | list[TimestampedMessage]):
                List of messages to save, in chronological order.
            max_history_size (int | None): Maximum messages to retain.

        Returns:
            bool: True if all messages were saved successfully.

        Raises:
            NotImplementedError: If not overridden by subclass.

        Example:
            >>> messages = [
            ...     ConversationMessage(role="user", content=[{"text": "Hi"}]),
            ...     ConversationMessage(role="assistant", content=[{"text": "Hello!"}]),
            ... ]
            >>> await storage.save_chat_messages(
            ...     user_id="user-1",
            ...     session_id="session-1",
            ...     agent_id="greeter",
            ...     new_messages=messages,
            ... )

        See Also:
            save_chat_message(): Save a single message.
        """
        pass

    @abstractmethod
    async def fetch_chat(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        max_history_size: Optional[int] = None
    ) -> list[ConversationMessage]:
        """
        Fetch chat history for a specific agent in a session.

        Retrieves stored conversation messages for a particular
        user/session/agent combination.

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.
            agent_id (str): Identifier of the agent whose history to fetch.
            max_history_size (int | None): Maximum messages to return.
                If None, returns all available messages.

        Returns:
            list[ConversationMessage]: List of conversation messages in
                chronological order. Empty list if no history exists.

        Raises:
            NotImplementedError: If not overridden by subclass.

        Example:
            >>> history = await storage.fetch_chat(
            ...     user_id="user-123",
            ...     session_id="session-456",
            ...     agent_id="tech-support",
            ...     max_history_size=10,
            ... )
            >>> for msg in history:
            ...     print(f"{msg.role}: {msg.content[0]['text']}")

        See Also:
            fetch_all_chats(): Fetch from all agents in a session.
        """
        pass

    @abstractmethod
    async def fetch_all_chats(
        self,
        user_id: str,
        session_id: str
    ) -> list[ConversationMessage]:
        """
        Fetch all chat messages across all agents for a session.

        Retrieves the complete conversation history regardless of
        which agent was involved. Useful for cross-agent context.

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.

        Returns:
            list[ConversationMessage]: List of all conversation messages
                from all agents, typically sorted by timestamp.
                Empty list if no history exists.

        Raises:
            NotImplementedError: If not overridden by subclass.

        Example:
            >>> all_history = await storage.fetch_all_chats(
            ...     user_id="user-123",
            ...     session_id="session-456",
            ... )
            >>> print(f"Total messages: {len(all_history)}")

        Note:
            Implementation should handle sorting by timestamp
            for accurate chronological ordering.

        See Also:
            fetch_chat(): Fetch from a specific agent.
        """
        pass

    @abstractmethod
    async def clear_chat(
        self,
        user_id: str,
        session_id: str,
        agent_id: Optional[str] = None
    ) -> bool:
        """Clear chat history for a session."""
        pass

    @abstractmethod
    async def update_shared_memory(
        self,
        user_id: str,
        session_id: str,
        key: str,
        value: Any
    ) -> bool:
        """Update shared memory for a session (e.g. summaries, context)."""
        pass

    @abstractmethod
    async def get_shared_memory(
        self,
        user_id: str,
        session_id: str
    ) -> dict[str, Any]:
        """Retrieve shared memory for a session."""
        pass
