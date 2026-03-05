"""Tests for Mem0Memory service."""
import asyncio
from unittest import mock

import pytest

from agentorchestrator.services.mem0 import Mem0Memory, MemoryEntry


class MockMemoryClient:
    """Mock client implementing MemoryStoreClientProtocol."""

    def __init__(self):
        self.memories = []
        self._id_counter = 0

    def add(self, memory: str, metadata: dict | None = None) -> dict:
        self._id_counter += 1
        entry = {"id": str(self._id_counter), "memory": memory, "metadata": metadata or {}}
        self.memories.append(entry)
        return {"id": entry["id"]}

    def search(self, query: str, limit: int = 10) -> list[dict]:
        # Simple mock: return all memories with a score
        return [
            {"id": m["id"], "memory": m["memory"], "score": 0.9, "metadata": m["metadata"]}
            for m in self.memories[:limit]
        ]

    def get_all(self) -> list[dict]:
        return [
            {"id": m["id"], "memory": m["memory"], "metadata": m["metadata"]}
            for m in self.memories
        ]

    def delete(self, memory_id: str) -> bool:
        for i, m in enumerate(self.memories):
            if m["id"] == memory_id:
                self.memories.pop(i)
                return True
        return False


@pytest.mark.asyncio
async def test_mem0_memory_add_and_search():
    """Test basic add and search operations."""
    client = MockMemoryClient()
    memory = Mem0Memory(client=client, default_user_id="test-user")

    entry = await memory.add("User prefers Python")
    assert entry.content == "User prefers Python"
    assert entry.id == "1"

    results = await memory.search("programming language")
    assert len(results) == 1
    assert results[0].content == "User prefers Python"
    assert results[0].relevance_score == 0.9


@pytest.mark.asyncio
async def test_mem0_memory_get_all():
    """Test get_all operation."""
    client = MockMemoryClient()
    memory = Mem0Memory(client=client)

    await memory.add("Memory 1")
    await memory.add("Memory 2")

    all_memories = await memory.get_all()
    assert len(all_memories) == 2


@pytest.mark.asyncio
async def test_mem0_memory_delete():
    """Test delete operation."""
    client = MockMemoryClient()
    memory = Mem0Memory(client=client)

    entry = await memory.add("To be deleted")
    assert len(await memory.get_all()) == 1

    success = await memory.delete(entry.id)
    assert success is True
    assert len(await memory.get_all()) == 0


@pytest.mark.asyncio
async def test_mem0_memory_get_context_for_query():
    """Test get_context_for_query formats memories properly."""
    client = MockMemoryClient()
    memory = Mem0Memory(client=client)

    await memory.add("User likes dark mode")
    await memory.add("User prefers concise responses")

    context = await memory.get_context_for_query("user preferences")
    assert "Relevant memories:" in context
    assert "User likes dark mode" in context


def test_mem0_memory_requires_async_context():
    """Test that Mem0Memory raises clear error when used outside async context."""
    client = MockMemoryClient()
    memory = Mem0Memory(client=client)

    # Calling _get_loop outside of async context should raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        memory._get_loop()

    assert "async context" in str(exc_info.value)
    assert "await" in str(exc_info.value)


@pytest.mark.asyncio
async def test_memory_entry_from_mem0():
    """Test MemoryEntry.from_mem0 parsing."""
    data = {
        "id": "mem-123",
        "memory": "User likes Python",
        "score": 0.95,
        "metadata": {"user_id": "u1"},
    }
    entry = MemoryEntry.from_mem0(data)

    assert entry.id == "mem-123"
    assert entry.content == "User likes Python"
    assert entry.relevance_score == 0.95
    assert entry.metadata == {"user_id": "u1"}


@pytest.mark.asyncio
async def test_memory_entry_from_mem0_with_content_field():
    """Test MemoryEntry.from_mem0 handles 'content' field as fallback."""
    data = {
        "id": "mem-456",
        "content": "Alternative field name",
        "relevance_score": 0.8,
    }
    entry = MemoryEntry.from_mem0(data)

    assert entry.id == "mem-456"
    assert entry.content == "Alternative field name"
    assert entry.relevance_score == 0.8
