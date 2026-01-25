"""
Storage implementations for the Multi-Agent Squad module.

Provides interfaces and implementations for persisting
conversation history across sessions and agents.

Use REDIS_AVAILABLE to check if Redis storage is available:
    from agentorchestrator.squad.storage import REDIS_AVAILABLE, RedisChatStorage
    if REDIS_AVAILABLE:
        storage = RedisChatStorage(redis_service)

Use Mem0Memory for semantic memory with corporate mem0 service:
    from app import MemoryStoreClient
    from agentorchestrator.squad.storage import Mem0Memory

    client = MemoryStoreClient(
        base_url="https://mem0.cfk.devfg.rbc.com",
        agent_id="my-agent-001"
    )
    memory = Mem0Memory(client=client)
"""

from agentorchestrator.squad.storage.base import ChatStorage
from agentorchestrator.squad.storage.memory import InMemoryChatStorage
from agentorchestrator.squad.storage.mem0 import (
    BaseMemory,
    CompositeMemory,
    Mem0Memory,
    MemoryEntry,
)

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
    # Semantic memory (mem0 integration)
    "BaseMemory",
    "Mem0Memory",
    "CompositeMemory",
    "MemoryEntry",
]
