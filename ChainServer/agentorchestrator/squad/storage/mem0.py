"""
Mem0 Memory - Re-exported from services for backward compatibility.

New location: agentorchestrator.services.mem0

Usage:
    # Preferred (new location)
    from agentorchestrator.services import Mem0Memory

    # Still works (deprecated location)
    from agentorchestrator.squad.storage import Mem0Memory
"""

# Re-export from new location for backward compatibility
from agentorchestrator.services.mem0 import (
    BaseMemory,
    CompositeMemory,
    Mem0Memory,
    MemoryEntry,
    MemoryStoreClientProtocol,
)

__all__ = [
    "BaseMemory",
    "CompositeMemory",
    "Mem0Memory",
    "MemoryEntry",
    "MemoryStoreClientProtocol",
]
