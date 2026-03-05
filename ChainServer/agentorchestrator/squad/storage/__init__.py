"""
Storage implementations for the Multi-Agent Squad module.

Provides interfaces and implementations for persisting
conversation history across sessions and agents.

Chat Storage (message history):
    from agentorchestrator.squad.storage import ChatStorage, InMemoryChatStorage

    # In-memory (for testing/development)
    storage = InMemoryChatStorage()

    # Redis (for production)
    from agentorchestrator.squad.storage import REDIS_AVAILABLE, RedisChatStorage
    if REDIS_AVAILABLE:
        storage = RedisChatStorage(redis_service)

Semantic Memory (mem0):
    # Import from services module
    from agentorchestrator.services import Mem0Memory
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
    # Chat storage (raw message history)
    "ChatStorage",
    "InMemoryChatStorage",
    "RedisChatStorage",
    "REDIS_AVAILABLE",
]
