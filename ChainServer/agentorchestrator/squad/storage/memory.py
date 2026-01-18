"""
In-memory implementation of ChatStorage.

Provides a simple dictionary-based storage for development
and testing. Data is lost when the process terminates.
"""

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Optional, Union

from agentorchestrator.squad.storage.base import ChatStorage
from agentorchestrator.squad.types import (
    ConversationMessage,
    TimestampedMessage,
)


class InMemoryChatStorage(ChatStorage):
    """
    In-memory chat storage implementation.

    Stores conversations in a nested dictionary structure:
    {user_id: {session_id: {agent_id: [messages]}}}

    Thread-safe for async operations using asyncio.Lock.
    """

    def __init__(self):
        """Initialize empty storage with thread safety."""
        self._storage: dict[str, dict[str, dict[str, list[ConversationMessage]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )
        self._lock = asyncio.Lock()

    def _get_storage_key(self, user_id: str, session_id: str, agent_id: str) -> list[ConversationMessage]:
        """Get the message list for a specific user/session/agent combination."""
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
        Save a single chat message to memory.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Agent identifier
            new_message: Message to save
            max_history_size: Max messages to retain

        Returns:
            True if saved successfully
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

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Agent identifier
            new_messages: Messages to save
            max_history_size: Max messages to retain

        Returns:
            True if saved successfully
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
        Fetch chat history for a specific agent.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Agent identifier
            max_history_size: Max messages to return

        Returns:
            List of conversation messages
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

        Messages are returned sorted by timestamp if available,
        otherwise in agent order.

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            List of all conversation messages
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
        Clear chat history.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Optional agent ID (if None, clears all agents)

        Returns:
            True if cleared successfully
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

        Args:
            user_id: User identifier

        Returns:
            Number of sessions
        """
        async with self._lock:
            if user_id in self._storage:
                return len(self._storage[user_id])
            return 0

    async def get_agent_count(self, user_id: str, session_id: str) -> int:
        """
        Get the number of agents with chat history in a session.

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            Number of agents
        """
        async with self._lock:
            if user_id in self._storage and session_id in self._storage[user_id]:
                return len(self._storage[user_id][session_id])
            return 0
