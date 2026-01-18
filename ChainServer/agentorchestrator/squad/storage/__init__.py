"""
Storage implementations for the Multi-Agent Squad module.

Provides interfaces and implementations for persisting
conversation history across sessions and agents.
"""

from agentorchestrator.squad.storage.base import ChatStorage
from agentorchestrator.squad.storage.memory import InMemoryChatStorage

# Conditional import for Redis storage
try:
    from agentorchestrator.squad.storage.redis import RedisChatStorage
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    RedisChatStorage = None  # type: ignore

__all__ = [
    "ChatStorage",
    "InMemoryChatStorage",
    "RedisChatStorage",
]
