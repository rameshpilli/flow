"""
Tests for Redis Chat Storage
=============================

Tests Redis-backed storage for multi-agent systems.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from agentorchestrator.squad.storage.redis import (
        RedisChatStorage,
        RedisStorageConfig,
    )
    from agentorchestrator.squad.types import ConversationMessage, ParticipantRole
    REDIS_STORAGE_AVAILABLE = True
except ImportError:
    REDIS_STORAGE_AVAILABLE = False


pytestmark = pytest.mark.skipif(not REDIS_STORAGE_AVAILABLE, reason="Redis storage not available")


class MockRedis:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self._data = {}
        self._expires = {}
    
    async def get(self, key):
        return self._data.get(key)
    
    async def set(self, key, value, ex=None):
        self._data[key] = value
        if ex:
            self._expires[key] = ex
    
    async def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                deleted += 1
        return deleted
    
    async def lpush(self, key, *values):
        if key not in self._data:
            self._data[key] = []
        for v in values:
            self._data[key].insert(0, v)
        return len(self._data[key])
    
    async def lrange(self, key, start, end):
        if key not in self._data:
            return []
        return self._data[key][start:end+1 if end != -1 else None]
    
    async def ltrim(self, key, start, end):
        if key in self._data:
            self._data[key] = self._data[key][start:end+1 if end != -1 else None]


class TestRedisChatStorage:
    """Tests for Redis chat storage."""

    @pytest.fixture
    def mock_redis(self):
        return MockRedis()

    @pytest.fixture
    def storage(self, mock_redis):
        storage = RedisChatStorage(
            redis_url="redis://localhost:6379",
            key_prefix="test:",
        )
        storage._redis = mock_redis
        return storage

    @pytest.mark.asyncio
    async def test_save_message(self, storage, mock_redis):
        """Test saving a message to Redis."""
        message = ConversationMessage(
            role=ParticipantRole.USER,
            content="Hello, world!",
        )
        
        await storage.save_message(
            user_id="user-123",
            session_id="session-456",
            message=message,
        )
        
        # Verify message was saved
        key = "test:chat:user-123:session-456"
        assert key in mock_redis._data

    @pytest.mark.asyncio
    async def test_get_messages(self, storage, mock_redis):
        """Test retrieving messages from Redis."""
        # Pre-populate messages
        import json
        messages_data = [
            json.dumps({"role": "user", "content": "Hello"}),
            json.dumps({"role": "assistant", "content": "Hi!"}),
        ]
        mock_redis._data["test:chat:user-123:session-456"] = messages_data
        
        messages = await storage.get_messages(
            user_id="user-123",
            session_id="session-456",
        )
        
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, storage, mock_redis):
        """Test retrieving limited messages."""
        import json
        messages_data = [
            json.dumps({"role": "user", "content": f"Message {i}"})
            for i in range(10)
        ]
        mock_redis._data["test:chat:user-123:session-456"] = messages_data
        
        messages = await storage.get_messages(
            user_id="user-123",
            session_id="session-456",
            limit=5,
        )
        
        assert len(messages) <= 5

    @pytest.mark.asyncio
    async def test_clear_session(self, storage, mock_redis):
        """Test clearing a session's messages."""
        # Pre-populate
        mock_redis._data["test:chat:user-123:session-456"] = ["msg1", "msg2"]
        
        await storage.clear_session(
            user_id="user-123",
            session_id="session-456",
        )
        
        # Verify cleared
        assert "test:chat:user-123:session-456" not in mock_redis._data


class TestRedisStorageConfig:
    """Tests for Redis storage configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RedisStorageConfig()
        
        assert config.redis_url == "redis://localhost:6379"
        assert config.key_prefix == "ao:chat:"
        assert config.ttl_seconds == 86400

    def test_custom_config(self):
        """Test custom configuration."""
        config = RedisStorageConfig(
            redis_url="redis://custom:6379",
            key_prefix="custom:",
            ttl_seconds=3600,
        )
        
        assert config.redis_url == "redis://custom:6379"
        assert config.key_prefix == "custom:"
        assert config.ttl_seconds == 3600

    def test_from_env(self):
        """Test loading config from environment."""
        with patch.dict("os.environ", {
            "REDIS_URL": "redis://env-redis:6379",
            "REDIS_CHAT_TTL": "7200",
        }):
            config = RedisStorageConfig.from_env()
            
            assert config.redis_url == "redis://env-redis:6379"
