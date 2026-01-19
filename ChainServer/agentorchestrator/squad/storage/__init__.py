"""
Storage implementations for the Multi-Agent Squad module.

Provides interfaces and implementations for persisting
conversation history across sessions and agents.

Use REDIS_AVAILABLE to check if Redis storage is available:
    from agentorchestrator.squad.storage import REDIS_AVAILABLE, RedisChatStorage
    if REDIS_AVAILABLE:
        storage = RedisChatStorage(redis_service)
"""

from agentorchestrator.squad.storage.base import ChatStorage
from agentorchestrator.squad.storage.memory import InMemoryChatStorage

# Conditional import for Redis storage
try:
    from agentorchestrator.squad.storage.redis import RedisChatStorage
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    RedisChatStorage = None  # type: ignore

__all__ = [
    "ChatStorage",
    "InMemoryChatStorage",
    "RedisChatStorage",
    "REDIS_AVAILABLE",
]
