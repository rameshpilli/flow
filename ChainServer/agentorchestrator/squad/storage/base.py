"""
Base ChatStorage interface for conversation persistence.

This module defines the abstract interface for storing and retrieving
conversation history across agents and sessions.
"""

from abc import ABC, abstractmethod
from typing import Optional, Union

from agentorchestrator.squad.types import ConversationMessage, TimestampedMessage


class ChatStorage(ABC):
    """
    Abstract base class for conversation storage.

    Implementations handle persistence of chat messages across
    sessions, users, and agents.
    """

    def is_same_role_as_last_message(
        self,
        conversation: list[ConversationMessage],
        new_message: ConversationMessage
    ) -> bool:
        """
        Check if new message has same role as the last message.

        Args:
            conversation: Existing conversation messages
            new_message: New message to check

        Returns:
            True if roles match, False otherwise
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
        Trim conversation to maximum history size.

        Maintains complete user/assistant pairs by ensuring
        the trimmed size is even.

        Args:
            conversation: Conversation to trim
            max_history_size: Maximum messages to keep

        Returns:
            Trimmed conversation
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
        Save a single chat message.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Agent identifier
            new_message: Message to save
            max_history_size: Max messages to retain

        Returns:
            True if saved successfully
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

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Agent identifier
            new_messages: Messages to save
            max_history_size: Max messages to retain

        Returns:
            True if saved successfully
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
        Fetch chat history for a specific agent.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Agent identifier
            max_history_size: Max messages to return

        Returns:
            List of conversation messages
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

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            List of all conversation messages
        """
        pass

    @abstractmethod
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
        pass
