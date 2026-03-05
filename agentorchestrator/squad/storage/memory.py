"""
AgentOrchestrator In-Memory Chat Storage
=========================================

This module provides an in-memory implementation of the ChatStorage interface.

InMemoryChatStorage is a simple dictionary-based storage suitable for
development, testing, and single-process deployments. Data is stored in
memory and lost when the process terminates.

Classes:
    InMemoryChatStorage: In-memory implementation of ChatStorage.

Usage:
    from agentorchestrator.squad.storage import InMemoryChatStorage

    storage = InMemoryChatStorage()

    # Save messages
    await storage.save_chat_message(
        user_id="user-1",
        session_id="session-1",
        agent_id="assistant",
        new_message=message,
    )

    # Fetch history
    history = await storage.fetch_chat(
        user_id="user-1",
        session_id="session-1",
        agent_id="assistant",
    )

Example:
    >>> from agentorchestrator.squad.storage import InMemoryChatStorage
    >>> from agentorchestrator.squad.types import ConversationMessage, ParticipantRole
    >>>
    >>> # Initialize storage
    >>> storage = InMemoryChatStorage()
    >>>
    >>> # Create and save a message
    >>> msg = ConversationMessage(
    ...     role=ParticipantRole.USER.value,
    ...     content=[{"text": "Hello, how are you?"}]
    ... )
    >>> await storage.save_chat_message("user-1", "session-1", "bot", msg)
    True
    >>>
    >>> # Fetch the conversation
    >>> history = await storage.fetch_chat("user-1", "session-1", "bot")
    >>> len(history)
    1
    >>>
    >>> # Get session statistics
    >>> session_count = await storage.get_session_count("user-1")
    >>> agent_count = await storage.get_agent_count("user-1", "session-1")

See Also:
    - agentorchestrator.squad.storage.base: ChatStorage base class.
    - agentorchestrator.squad.types: ConversationMessage and related types.
"""

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional, Union

from agentorchestrator.squad.storage.base import ChatStorage
from agentorchestrator.squad.types import (
    ConversationMessage,
    TimestampedMessage,
)


class InMemoryChatStorage(ChatStorage):
    """
    In-memory chat storage implementation.

    Stores conversations in a nested dictionary structure organized by
    user, session, and agent. Thread-safe for async operations using
    asyncio.Lock.

    Attributes:
        _storage (dict): Nested dictionary storing messages.
            Structure: {user_id: {session_id: {agent_id: [messages]}}}
        _lock (asyncio.Lock): Lock for thread-safe async operations.

    Methods:
        save_chat_message(): Save a single message.
        save_chat_messages(): Save multiple messages.
        fetch_chat(): Fetch agent's chat history.
        fetch_all_chats(): Fetch all chats in session.
        clear_chat(): Clear chat history.
        get_session_count(): Count sessions for a user.
        get_agent_count(): Count agents in a session.

    Example:
        >>> storage = InMemoryChatStorage()
        >>>
        >>> # Save user and assistant messages
        >>> user_msg = ConversationMessage(
        ...     role=ParticipantRole.USER.value,
        ...     content=[{"text": "What's 2+2?"}]
        ... )
        >>> await storage.save_chat_message("u1", "s1", "math-bot", user_msg)
        >>>
        >>> assistant_msg = ConversationMessage(
        ...     role=ParticipantRole.ASSISTANT.value,
        ...     content=[{"text": "2+2 equals 4"}]
        ... )
        >>> await storage.save_chat_message("u1", "s1", "math-bot", assistant_msg)
        >>>
        >>> # Fetch conversation
        >>> history = await storage.fetch_chat("u1", "s1", "math-bot")
        >>> for msg in history:
        ...     print(f"{msg.role}: {msg.content[0]['text']}")
        user: What's 2+2?
        assistant: 2+2 equals 4

    Thread Safety:
        All async methods use an internal lock to ensure thread-safe
        access to the storage dictionary. Safe for concurrent use
        from multiple asyncio tasks.

    Limitations:
        - Data is lost when the process terminates
        - Not suitable for multi-process or distributed deployments
        - Memory usage grows with conversation history
        - No persistence or backup capabilities

    See Also:
        ChatStorage: Abstract base class.
    """

    def __init__(self):
        """
        Initialize empty in-memory storage with thread safety.
        """
        self._storage: dict[str, dict[str, dict[str, list[ConversationMessage]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )
        self._shared_memory: dict[str, dict[str, dict[str, Any]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        self._lock = asyncio.Lock()

    async def update_shared_memory(
        self,
        user_id: str,
        session_id: str,
        key: str,
        value: Any
    ) -> bool:
        """Update shared memory for a session."""
        async with self._lock:
            self._shared_memory[user_id][session_id][key] = value
            return True

    async def get_shared_memory(
        self,
        user_id: str,
        session_id: str
    ) -> dict[str, Any]:
        """Retrieve shared memory for a session."""
        async with self._lock:
            return self._shared_memory[user_id][session_id].copy()

    def _get_storage_key(self, user_id: str, session_id: str, agent_id: str) -> list[ConversationMessage]:
        """
        Get the message list for a specific user/session/agent combination.

        Args:
            user_id (str): User identifier.
            session_id (str): Session identifier.
            agent_id (str): Agent identifier.

        Returns:
            list[ConversationMessage]: The message list (may be empty).
        """
        return self._storage[user_id][session_id][agent_id]

    async def save_chat_message(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        new_message: Union[ConversationMessage, TimestampedMessage],
        max_history_size: Optional[int] = None
    ) -> bool:
        """
        Save a single chat message to in-memory storage.

        Handles consecutive same-role messages by merging their content,
        as some LLM APIs require alternating user/assistant messages.

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.
            agent_id (str): Identifier of the agent involved.
            new_message (ConversationMessage | TimestampedMessage): The message
                to save. TimestampedMessage is converted to ConversationMessage.
            max_history_size (int | None): Maximum messages to retain.
                Older messages are discarded after saving.

        Returns:
            bool: True (always succeeds for in-memory storage).

        Example:
            >>> msg = ConversationMessage(
            ...     role=ParticipantRole.USER.value,
            ...     content=[{"text": "Hello!"}]
            ... )
            >>> success = await storage.save_chat_message(
            ...     user_id="user-123",
            ...     session_id="session-456",
            ...     agent_id="greeter",
            ...     new_message=msg,
            ...     max_history_size=100,
            ... )

        Note:
            If the new message has the same role as the last message,
            their content is merged with a newline separator.
        """
        async with self._lock:
            messages = self._get_storage_key(user_id, session_id, agent_id)

            # Convert TimestampedMessage to ConversationMessage if needed
            if isinstance(new_message, TimestampedMessage):
                msg = ConversationMessage(
                    role=new_message.role,
                    content=new_message.content
                )
            else:
                msg = new_message

            # Handle consecutive messages with same role
            if self.is_same_role_as_last_message(messages, msg):
                # Append content to last message
                last_msg = messages[-1]
                last_text = last_msg.get_text()
                new_text = msg.get_text()
                last_msg.content = [{"text": f"{last_text}\n{new_text}"}]
            else:
                messages.append(msg)

            # Trim if needed
            if max_history_size:
                trimmed = self.trim_conversation(messages, max_history_size)
                self._storage[user_id][session_id][agent_id] = trimmed

            return True

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

        Iteratively saves each message, handling same-role merging
        and history trimming.

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.
            agent_id (str): Identifier of the agent involved.
            new_messages (list[ConversationMessage] | list[TimestampedMessage]):
                List of messages to save in chronological order.
            max_history_size (int | None): Maximum messages to retain.

        Returns:
            bool: True (always succeeds for in-memory storage).

        Example:
            >>> messages = [
            ...     ConversationMessage(role="user", content=[{"text": "Hi"}]),
            ...     ConversationMessage(role="assistant", content=[{"text": "Hello!"}]),
            ... ]
            >>> await storage.save_chat_messages(
            ...     "user-1", "session-1", "bot", messages
            ... )
        """
        for message in new_messages:
            await self.save_chat_message(
                user_id, session_id, agent_id, message, max_history_size
            )
        return True

    async def fetch_chat(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        max_history_size: Optional[int] = None
    ) -> list[ConversationMessage]:
        """
        Fetch chat history for a specific agent in a session.

        Returns a copy of the messages to prevent external modification.

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.
            agent_id (str): Identifier of the agent whose history to fetch.
            max_history_size (int | None): Maximum messages to return.
                If None, returns all messages.

        Returns:
            list[ConversationMessage]: List of messages in chronological order.
                Empty list if no history exists.

        Example:
            >>> history = await storage.fetch_chat(
            ...     "user-1", "session-1", "assistant",
            ...     max_history_size=10
            ... )
            >>> for msg in history:
            ...     print(f"{msg.role}: {msg.content[0]['text']}")
        """
        async with self._lock:
            messages = self._get_storage_key(user_id, session_id, agent_id).copy()
            if max_history_size:
                return self.trim_conversation(messages, max_history_size)
            return messages

    async def fetch_all_chats(
        self,
        user_id: str,
        session_id: str
    ) -> list[ConversationMessage]:
        """
        Fetch all chat messages across all agents for a session.

        Collects messages from all agents that have interacted in
        this session. Messages are returned in agent order, not
        necessarily chronological order.

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.

        Returns:
            list[ConversationMessage]: All messages from all agents.
                Empty list if no history exists.

        Example:
            >>> all_msgs = await storage.fetch_all_chats("user-1", "session-1")
            >>> print(f"Total messages from all agents: {len(all_msgs)}")

        Note:
            For strict chronological ordering, consider using
            TimestampedMessage and sorting by timestamp.
        """
        async with self._lock:
            all_messages: list[ConversationMessage] = []

            if user_id in self._storage and session_id in self._storage[user_id]:
                for agent_id, messages in self._storage[user_id][session_id].items():
                    all_messages.extend(messages)

            return all_messages

    async def clear_chat(
        self,
        user_id: str,
        session_id: str,
        agent_id: Optional[str] = None
    ) -> bool:
        """
        Clear chat history from in-memory storage.

        Can clear a specific agent's history or all agents in a session.

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.
            agent_id (str | None): If provided, clears only this agent's
                history. If None, clears all agents in the session.

        Returns:
            bool: True (always succeeds, even if nothing to clear).

        Example:
            >>> # Clear specific agent
            >>> await storage.clear_chat("user-1", "session-1", "bot")
            >>>
            >>> # Clear entire session
            >>> await storage.clear_chat("user-1", "session-1")
        """
        async with self._lock:
            if user_id not in self._storage:
                return True

            if session_id not in self._storage[user_id]:
                return True

            if agent_id:
                # Clear specific agent
                if agent_id in self._storage[user_id][session_id]:
                    self._storage[user_id][session_id][agent_id] = []
            else:
                # Clear all agents for this session
                self._storage[user_id][session_id] = defaultdict(list)

            return True

    async def get_session_count(self, user_id: str) -> int:
        """
        Get the number of sessions for a user.

        Counts how many unique session IDs exist for the given user.

        Args:
            user_id (str): Unique identifier for the user.

        Returns:
            int: Number of sessions. Returns 0 if user not found.

        Example:
            >>> session_count = await storage.get_session_count("user-1")
            >>> print(f"User has {session_count} active sessions")
        """
        async with self._lock:
            if user_id in self._storage:
                return len(self._storage[user_id])
            return 0

    async def get_agent_count(self, user_id: str, session_id: str) -> int:
        """
        Get the number of agents with chat history in a session.

        Counts how many unique agent IDs have messages stored
        for this user/session combination.

        Args:
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.

        Returns:
            int: Number of agents with history. Returns 0 if
                user or session not found.

        Example:
            >>> agent_count = await storage.get_agent_count("user-1", "session-1")
            >>> print(f"Session involves {agent_count} agents")
        """
        async with self._lock:
            if user_id in self._storage and session_id in self._storage[user_id]:
                return len(self._storage[user_id][session_id])
            return 0