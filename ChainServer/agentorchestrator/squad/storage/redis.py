"""
Redis-based ChatStorage implementation.

Uses the existing RedisService from agentorchestrator.services.redis
for persistent conversation storage across sessions.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Union

from agentorchestrator.squad.storage.base import ChatStorage
from agentorchestrator.squad.types import (
    ConversationMessage,
    TimestampedMessage,
)
from agentorchestrator.services.redis import (
    RedisService,
    get_redis_client,
    REDIS_AVAILABLE,
)

logger = logging.getLogger(__name__)


class RedisChatStorage(ChatStorage):
    """
    Redis-based chat storage using the existing RedisService.

    Stores conversations in Redis with the following key structure:
    - chat:{user_id}:{session_id}:{agent_id} -> List of messages (JSON)
    - chat_index:{user_id}:{session_id} -> Set of agent IDs with chat history

    Example:
        ```python
        from agentorchestrator.squad.storage import RedisChatStorage
        from agentorchestrator.services.redis import init_redis_client

        # Initialize Redis (uses existing service)
        init_redis_client(
            host="redis-server.corp.com",
            port=6379,
            username="service_account",
            password="secret",
            ssl=True,
        )

        # Create storage
        storage = RedisChatStorage()

        # Or with custom TTL
        storage = RedisChatStorage(ttl_seconds=86400)  # 24 hours

        # Use in orchestrator
        orchestrator = MultiAgentOrchestrator(storage=storage)
        ```
    """

    # Default key prefix for chat data
    KEY_PREFIX = "squad:chat"
    INDEX_PREFIX = "squad:chat_index"
    SHARED_MEMORY_PREFIX = "squad:shared_memory"

    def __init__(
        self,
        redis_service: Optional[RedisService] = None,
        ttl_seconds: Optional[int] = None,
        key_prefix: Optional[str] = None,
    ):
        """
        Initialize Redis chat storage.

        Args:
            redis_service: RedisService instance (uses default if None)
            ttl_seconds: Optional TTL for chat data (None = no expiry)
            key_prefix: Custom key prefix (default: "squad:chat")
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis is not available. Install with: pip install redis>=4.5.0"
            )

        self.redis = redis_service or get_redis_client()
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix or self.KEY_PREFIX
        self.index_prefix = f"{self.key_prefix}_index"
        self.shared_memory_prefix = f"{self.key_prefix}_shared"

    def _chat_key(self, user_id: str, session_id: str, agent_id: str) -> str:
        """Generate Redis key for agent chat history."""
        return f"{self.key_prefix}:{user_id}:{session_id}:{agent_id}"

    def _index_key(self, user_id: str, session_id: str) -> str:
        """Generate Redis key for session's agent index."""
        return f"{self.index_prefix}:{user_id}:{session_id}"

    def _shared_memory_key(self, user_id: str, session_id: str) -> str:
        """Generate Redis key for shared session memory."""
        return f"{self.shared_memory_prefix}:{user_id}:{session_id}"

    async def update_shared_memory(
        self,
        user_id: str,
        session_id: str,
        key: str,
        value: Any
    ) -> bool:
        """Update shared memory for a session (e.g. summaries, context)."""
        await self._ensure_connected()
        try:
            shared_key = self._shared_memory_key(user_id, session_id)
            existing = await self.redis.get(shared_key)
            memory = json.loads(existing) if existing else {}
            memory[key] = value
            await self.redis.set(shared_key, json.dumps(memory), ttl=self.ttl_seconds)
            return True
        except Exception as e:
            logger.error(f"Failed to update shared memory: {e}")
            return False

    async def get_shared_memory(
        self,
        user_id: str,
        session_id: str
    ) -> dict[str, Any]:
        """Retrieve shared memory for a session."""
        await self._ensure_connected()
        try:
            shared_key = self._shared_memory_key(user_id, session_id)
            data = await self.redis.get(shared_key)
            return json.loads(data) if data else {}
        except Exception as e:
            logger.error(f"Failed to get shared memory: {e}")
            return {}

    def _message_to_dict(
        self,
        message: Union[ConversationMessage, TimestampedMessage]
    ) -> dict:
        """Convert a message to a dictionary for JSON storage."""
        data = {
            "role": message.role,
            "content": message.content,
        }
        if isinstance(message, TimestampedMessage):
            data["timestamp"] = message.timestamp.isoformat()
        return data

    def _dict_to_message(self, data: dict) -> ConversationMessage:
        """Convert a dictionary back to a ConversationMessage."""
        return ConversationMessage(
            role=data["role"],
            content=data["content"]
        )

    async def _ensure_connected(self) -> None:
        """Ensure Redis is connected."""
        await self.redis.ensure_connected()

    async def save_chat_message(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        new_message: Union[ConversationMessage, TimestampedMessage],
        max_history_size: Optional[int] = None
    ) -> bool:
        """
        Save a single chat message to Redis.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Agent identifier
            new_message: Message to save
            max_history_size: Max messages to retain

        Returns:
            True if saved successfully
        """
        await self._ensure_connected()

        try:
            key = self._chat_key(user_id, session_id, agent_id)
            index_key = self._index_key(user_id, session_id)

            # Get existing messages
            existing = await self.redis.get(key)
            messages = json.loads(existing) if existing else []

            # Handle consecutive same-role messages
            message_dict = self._message_to_dict(new_message)
            if messages and messages[-1]["role"] == new_message.role:
                # Append to last message
                last_text = messages[-1]["content"][0].get("text", "")
                new_text = new_message.content[0].get("text", "")
                messages[-1]["content"] = [{"text": f"{last_text}\n{new_text}"}]
            else:
                messages.append(message_dict)

            # Trim if needed
            if max_history_size:
                messages = self.trim_conversation(
                    [self._dict_to_message(m) for m in messages],
                    max_history_size
                )
                messages = [self._message_to_dict(m) for m in messages]

            # Save back to Redis
            await self.redis.set(key, json.dumps(messages), ttl=self.ttl_seconds)

            # Update agent index
            await self.redis.client.sadd(index_key, agent_id)
            if self.ttl_seconds:
                await self.redis.expire(index_key, self.ttl_seconds)

            return True

        except Exception as e:
            logger.error(f"Failed to save chat message to Redis: {e}")
            return False

    async def save_chat_messages(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        new_messages: Union[list[ConversationMessage], list[TimestampedMessage]],
        max_history_size: Optional[int] = None
    ) -> bool:
        """
        Save multiple chat messages to Redis.

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
            success = await self.save_chat_message(
                user_id, session_id, agent_id, message, max_history_size
            )
            if not success:
                return False
        return True

    async def fetch_chat(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        max_history_size: Optional[int] = None
    ) -> list[ConversationMessage]:
        """
        Fetch chat history for a specific agent from Redis.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Agent identifier
            max_history_size: Max messages to return

        Returns:
            List of conversation messages
        """
        await self._ensure_connected()

        try:
            key = self._chat_key(user_id, session_id, agent_id)
            data = await self.redis.get(key)

            if not data:
                return []

            messages = [
                self._dict_to_message(m)
                for m in json.loads(data)
            ]

            if max_history_size:
                messages = self.trim_conversation(messages, max_history_size)

            return messages

        except Exception as e:
            logger.error(f"Failed to fetch chat from Redis: {e}")
            return []

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
        await self._ensure_connected()

        try:
            index_key = self._index_key(user_id, session_id)

            # Get all agent IDs for this session
            agent_ids = await self.redis.client.smembers(index_key)

            if not agent_ids:
                return []

            # Fetch all messages
            all_messages: list[ConversationMessage] = []
            for agent_id in agent_ids:
                messages = await self.fetch_chat(user_id, session_id, agent_id)
                all_messages.extend(messages)

            return all_messages

        except Exception as e:
            logger.error(f"Failed to fetch all chats from Redis: {e}")
            return []

    async def clear_chat(
        self,
        user_id: str,
        session_id: str,
        agent_id: Optional[str] = None
    ) -> bool:
        """
        Clear chat history from Redis.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Optional agent ID (clears all if None)

        Returns:
            True if cleared successfully
        """
        await self._ensure_connected()

        try:
            if agent_id:
                # Clear specific agent
                key = self._chat_key(user_id, session_id, agent_id)
                await self.redis.delete(key)

                # Remove from index
                index_key = self._index_key(user_id, session_id)
                await self.redis.client.srem(index_key, agent_id)
            else:
                # Clear all agents for this session
                index_key = self._index_key(user_id, session_id)
                agent_ids = await self.redis.client.smembers(index_key)

                # Delete all chat keys
                for aid in agent_ids:
                    key = self._chat_key(user_id, session_id, aid)
                    await self.redis.delete(key)

                # Delete index
                await self.redis.delete(index_key)

            return True

        except Exception as e:
            logger.error(f"Failed to clear chat from Redis: {e}")
            return False

    async def get_session_agents(
        self,
        user_id: str,
        session_id: str
    ) -> list[str]:
        """
        Get list of agent IDs that have chat history in a session.

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            List of agent IDs
        """
        await self._ensure_connected()

        try:
            index_key = self._index_key(user_id, session_id)
            agent_ids = await self.redis.client.smembers(index_key)
            return list(agent_ids)
        except Exception as e:
            logger.error(f"Failed to get session agents from Redis: {e}")
            return []
