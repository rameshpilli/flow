"""
Mem0 Memory Store integration for semantic memory.

Provides semantic search over conversation history using the corporate
mem0 service. Unlike ChatStorage (which stores raw messages), this
provides intelligent memory with semantic search capabilities.

Usage:
    from app import MemoryStoreClient
    from agentorchestrator.squad.storage.mem0 import Mem0Memory

    client = MemoryStoreClient(
        base_url="https://mem0.cfk.devfg.rbc.com",
        agent_id="my-agent-001"
    )

    memory = Mem0Memory(client=client)

    # Store memory
    await memory.add("User prefers technical explanations")

    # Search memories
    results = await memory.search("What are user's preferences?")

    # Use with agents
    agent = LLMGatewayAgent(memory=memory)
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class MemoryStoreClientProtocol(Protocol):
    """Protocol for mem0 client - matches your corporate MemoryStoreClient."""

    def add(self, memory: str, metadata: dict | None = None) -> dict: ...
    def search(self, query: str, limit: int = 10) -> list[dict]: ...
    def get_all(self) -> list[dict]: ...
    def delete(self, memory_id: str) -> bool: ...


@dataclass
class MemoryEntry:
    """A single memory entry."""

    id: str
    content: str
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    relevance_score: float = 0.0

    @classmethod
    def from_mem0(cls, data: dict) -> "MemoryEntry":
        """Create from mem0 response format."""
        return cls(
            id=data.get("id", ""),
            content=data.get("memory", data.get("content", "")),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
            relevance_score=data.get("score", data.get("relevance_score", 0.0)),
        )


class BaseMemory(ABC):
    """Abstract base for memory implementations."""

    @abstractmethod
    async def add(
        self,
        content: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> MemoryEntry:
        """Add a memory."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Search memories semantically."""
        pass

    @abstractmethod
    async def get_all(
        self,
        user_id: str | None = None,
    ) -> list[MemoryEntry]:
        """Get all memories."""
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        pass

    @abstractmethod
    async def clear(self, user_id: str | None = None) -> bool:
        """Clear all memories."""
        pass


class Mem0Memory(BaseMemory):
    """
    Mem0 semantic memory integration.

    Wraps the corporate MemoryStoreClient to provide async semantic
    memory for agents.

    Example:
        from app import MemoryStoreClient

        client = MemoryStoreClient(
            base_url="https://mem0.cfk.devfg.rbc.com",
            agent_id="trading-agent-001"
        )

        memory = Mem0Memory(client=client)

        # Add memories
        await memory.add("Execute buy order for 1000 shares of AAPL at $150")

        # Search memories
        results = await memory.search("What trades did I execute?")
        for mem in results:
            print(mem.content)
    """

    def __init__(
        self,
        client: MemoryStoreClientProtocol,
        default_user_id: str | None = None,
    ):
        """
        Initialize Mem0Memory.

        Args:
            client: Corporate MemoryStoreClient instance
            default_user_id: Default user ID for operations
        """
        self.client = client
        self.default_user_id = default_user_id
        self._loop = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop for sync-to-async bridging."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
            return self._loop

    async def _run_sync(self, func, *args, **kwargs) -> Any:
        """Run synchronous mem0 client methods in thread pool."""
        loop = self._get_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def add(
        self,
        content: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> MemoryEntry:
        """
        Add a memory to the store.

        Args:
            content: Memory content to store
            user_id: Optional user ID (uses default if not provided)
            session_id: Optional session ID for grouping
            metadata: Optional additional metadata

        Returns:
            Created MemoryEntry
        """
        meta = metadata or {}
        if user_id or self.default_user_id:
            meta["user_id"] = user_id or self.default_user_id
        if session_id:
            meta["session_id"] = session_id

        try:
            result = await self._run_sync(self.client.add, content, meta)
            logger.debug(f"Added memory: {content[:50]}...")
            return MemoryEntry(
                id=result.get("id", ""),
                content=content,
                metadata=meta,
            )
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            raise

    async def search(
        self,
        query: str,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """
        Search memories semantically.

        Args:
            query: Search query
            user_id: Optional user ID filter
            limit: Max results to return

        Returns:
            List of matching MemoryEntry objects sorted by relevance
        """
        try:
            results = await self._run_sync(self.client.search, query, limit)
            entries = [MemoryEntry.from_mem0(r) for r in results]

            # Filter by user_id if provided
            if user_id:
                entries = [e for e in entries if e.metadata.get("user_id") == user_id]

            logger.debug(f"Found {len(entries)} memories for query: {query[:50]}...")
            return entries
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []

    async def get_all(
        self,
        user_id: str | None = None,
    ) -> list[MemoryEntry]:
        """
        Get all memories.

        Args:
            user_id: Optional user ID filter

        Returns:
            List of all MemoryEntry objects
        """
        try:
            results = await self._run_sync(self.client.get_all)
            entries = [MemoryEntry.from_mem0(r) for r in results]

            if user_id:
                entries = [e for e in entries if e.metadata.get("user_id") == user_id]

            return entries
        except Exception as e:
            logger.error(f"Failed to get all memories: {e}")
            return []

    async def delete(self, memory_id: str) -> bool:
        """
        Delete a specific memory.

        Args:
            memory_id: ID of memory to delete

        Returns:
            True if deleted successfully
        """
        try:
            result = await self._run_sync(self.client.delete, memory_id)
            logger.debug(f"Deleted memory: {memory_id}")
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False

    async def clear(self, user_id: str | None = None) -> bool:
        """
        Clear all memories.

        Args:
            user_id: Optional user ID to clear only that user's memories

        Returns:
            True if cleared successfully
        """
        try:
            all_memories = await self.get_all(user_id=user_id)
            for mem in all_memories:
                await self.delete(mem.id)
            logger.info(f"Cleared {len(all_memories)} memories")
            return True
        except Exception as e:
            logger.error(f"Failed to clear memories: {e}")
            return False

    async def get_context_for_query(
        self,
        query: str,
        user_id: str | None = None,
        max_tokens: int = 2000,
        limit: int = 5,
    ) -> str:
        """
        Get relevant memory context for a query.

        Convenience method for agents to retrieve relevant memories
        formatted as context for LLM prompts.

        Args:
            query: The query to find relevant context for
            user_id: Optional user ID filter
            max_tokens: Approximate max tokens in context
            limit: Max memories to include

        Returns:
            Formatted context string
        """
        memories = await self.search(query, user_id=user_id, limit=limit)

        if not memories:
            return ""

        context_parts = ["Relevant memories:"]
        char_count = 0
        approx_chars_per_token = 4

        for mem in memories:
            mem_text = f"- {mem.content}"
            if char_count + len(mem_text) > max_tokens * approx_chars_per_token:
                break
            context_parts.append(mem_text)
            char_count += len(mem_text)

        return "\n".join(context_parts)


class CompositeMemory(BaseMemory):
    """
    Composite memory that combines multiple memory strategies.

    Example:
        memory = CompositeMemory([
            WindowMemory(window_size=5),
            EntityMemory(llm=llm_client),
            Mem0Memory(client=mem0_client),
        ])
    """

    def __init__(self, memories: list[BaseMemory]):
        """
        Initialize composite memory.

        Args:
            memories: List of memory implementations to use
        """
        self.memories = memories

    async def add(
        self,
        content: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> MemoryEntry:
        """Add to all memory stores."""
        results = await asyncio.gather(
            *[m.add(content, user_id, session_id, metadata) for m in self.memories],
            return_exceptions=True,
        )
        # Return first successful result
        for r in results:
            if isinstance(r, MemoryEntry):
                return r
        raise RuntimeError("All memory stores failed to add")

    async def search(
        self,
        query: str,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Search all memory stores and merge results."""
        all_results = await asyncio.gather(
            *[m.search(query, user_id, limit) for m in self.memories],
            return_exceptions=True,
        )

        # Merge and deduplicate
        seen_ids = set()
        merged = []
        for results in all_results:
            if isinstance(results, list):
                for entry in results:
                    if entry.id not in seen_ids:
                        seen_ids.add(entry.id)
                        merged.append(entry)

        # Sort by relevance and limit
        merged.sort(key=lambda x: x.relevance_score, reverse=True)
        return merged[:limit]

    async def get_all(self, user_id: str | None = None) -> list[MemoryEntry]:
        """Get all memories from all stores."""
        all_results = await asyncio.gather(
            *[m.get_all(user_id) for m in self.memories],
            return_exceptions=True,
        )

        merged = []
        for results in all_results:
            if isinstance(results, list):
                merged.extend(results)
        return merged

    async def delete(self, memory_id: str) -> bool:
        """Delete from all stores."""
        results = await asyncio.gather(
            *[m.delete(memory_id) for m in self.memories],
            return_exceptions=True,
        )
        return any(r is True for r in results)

    async def clear(self, user_id: str | None = None) -> bool:
        """Clear all stores."""
        results = await asyncio.gather(
            *[m.clear(user_id) for m in self.memories],
            return_exceptions=True,
        )
        return all(r is True for r in results if not isinstance(r, Exception))
