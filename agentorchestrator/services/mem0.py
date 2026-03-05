"""
AgentOrchestrator Mem0 Memory Service
=====================================

This module provides semantic memory integration using the Mem0 service for
intelligent, searchable conversation history and context retrieval.

Unlike simple chat storage (which stores raw messages), Mem0 provides:
- Semantic search over memories using embeddings
- Automatic memory consolidation and summarization
- User and session-scoped memory isolation
- Relevance-scored retrieval for context injection

Classes:
    MemoryEntry: Dataclass representing a single memory entry.
    BaseMemory: Abstract base class for memory implementations.
    Mem0Memory: Main Mem0 semantic memory integration class.
    CompositeMemory: Combines multiple memory strategies.

Protocols:
    MemoryStoreClientProtocol: Protocol for Mem0 client compatibility.

Usage:
    from app import MemoryStoreClient
    from agentorchestrator.services import Mem0Memory

    client = MemoryStoreClient(
        base_url="https://mem0.corp.com",
        agent_id="my-agent-001"
    )

    memory = Mem0Memory(client=client)

    # Store memory
    await memory.add("User prefers technical explanations")

    # Search memories
    results = await memory.search("What are user's preferences?")

    # Use with agents
    agent = LLMGatewayAgent(memory=memory)

Example:
    >>> from agentorchestrator.services import Mem0Memory
    >>>
    >>> # Assuming you have a MemoryStoreClient instance
    >>> memory = Mem0Memory(client=mem0_client, default_user_id="user-123")
    >>>
    >>> # Add memories
    >>> await memory.add("User is interested in machine learning")
    >>> await memory.add("User prefers Python over JavaScript")
    >>>
    >>> # Search semantically
    >>> results = await memory.search("What programming language does user like?")
    >>> for mem in results:
    ...     print(f"{mem.content} (score: {mem.relevance_score:.2f})")
    >>>
    >>> # Get context for LLM prompts
    >>> context = await memory.get_context_for_query("Help me with coding")
    >>> print(context)

See Also:
    - agentorchestrator.services.redis: Redis-based chat storage.
    - agentorchestrator.squad.storage: Chat history management.
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
    """
    Protocol for Mem0 client compatibility.

    Defines the interface that a Mem0 client must implement to work
    with the Mem0Memory class. Your corporate MemoryStoreClient should
    match this interface.

    Methods:
        add(): Add a memory to the store.
        search(): Search memories semantically.
        get_all(): Get all memories.
        delete(): Delete a specific memory.

    Example:
        >>> class MyMemoryClient:
        ...     def add(self, memory: str, metadata: dict | None = None) -> dict:
        ...         # Store memory and return {"id": "..."}
        ...         pass
        ...
        ...     def search(self, query: str, limit: int = 10) -> list[dict]:
        ...         # Return list of {"id": "...", "memory": "...", "score": 0.9}
        ...         pass
        ...
        ...     def get_all(self) -> list[dict]:
        ...         # Return all memories
        ...         pass
        ...
        ...     def delete(self, memory_id: str) -> bool:
        ...         # Delete and return success
        ...         pass
        >>>
        >>> # Verify protocol compatibility
        >>> isinstance(MyMemoryClient(), MemoryStoreClientProtocol)  # True
    """

    def add(self, memory: str, metadata: dict | None = None) -> dict: ...
    def search(self, query: str, limit: int = 10) -> list[dict]: ...
    def get_all(self) -> list[dict]: ...
    def delete(self, memory_id: str) -> bool: ...


@dataclass
class MemoryEntry:
    """
    A single memory entry.

    Represents a memory stored in the Mem0 system with content,
    metadata, timestamp, and relevance scoring.

    Attributes:
        id (str): Unique identifier for the memory.
        content (str): The memory content text.
        metadata (dict): Additional metadata (user_id, session_id, etc.).
        timestamp (datetime): When the memory was created.
        relevance_score (float): Relevance score from search (0.0-1.0).

    Methods:
        from_mem0(): Create from Mem0 response format.

    Example:
        >>> entry = MemoryEntry(
        ...     id="mem-123",
        ...     content="User prefers dark mode",
        ...     metadata={"user_id": "user-456"},
        ...     relevance_score=0.95,
        ... )
        >>> print(entry.content)
        >>>
        >>> # From Mem0 API response
        >>> entry = MemoryEntry.from_mem0({
        ...     "id": "mem-123",
        ...     "memory": "User prefers dark mode",
        ...     "score": 0.95,
        ... })
    """

    id: str
    content: str
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    relevance_score: float = 0.0

    @classmethod
    def from_mem0(cls, data: dict) -> "MemoryEntry":
        """
        Create from Mem0 response format.

        Parses the response format from Mem0 API into a MemoryEntry.
        Handles both "memory" and "content" field names for compatibility.

        Args:
            data (dict): Mem0 response dictionary with id, memory/content, etc.

        Returns:
            MemoryEntry: Parsed memory entry.

        Example:
            >>> data = {
            ...     "id": "abc123",
            ...     "memory": "User likes Python",
            ...     "score": 0.92,
            ...     "metadata": {"session": "sess-1"},
            ...     "timestamp": "2024-01-15T10:30:00",
            ... }
            >>> entry = MemoryEntry.from_mem0(data)
            >>> print(entry.content)  # "User likes Python"
            >>> print(entry.relevance_score)  # 0.92
        """
        return cls(
            id=data.get("id", ""),
            content=data.get("memory", data.get("content", "")),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
            relevance_score=data.get("score", data.get("relevance_score", 0.0)),
        )


class BaseMemory(ABC):
    """
    Abstract base class for memory implementations.

    Defines the interface that all memory implementations must follow.
    Subclasses implement different memory strategies (semantic, window,
    entity extraction, etc.).

    Methods:
        add(): Add a memory to the store.
        search(): Search memories semantically.
        get_all(): Get all memories for a user.
        delete(): Delete a specific memory.
        clear(): Clear all memories.

    Example:
        >>> class WindowMemory(BaseMemory):
        ...     def __init__(self, window_size: int = 10):
        ...         self.window_size = window_size
        ...         self._memories: list[MemoryEntry] = []
        ...
        ...     async def add(self, content: str, **kwargs) -> MemoryEntry:
        ...         entry = MemoryEntry(id=str(len(self._memories)), content=content)
        ...         self._memories.append(entry)
        ...         if len(self._memories) > self.window_size:
        ...             self._memories.pop(0)
        ...         return entry
        ...
        ...     # ... implement other methods

    See Also:
        Mem0Memory: Semantic memory implementation.
        CompositeMemory: Combines multiple memory strategies.
    """

    @abstractmethod
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
            content (str): Memory content to store.
            user_id (str | None): User ID for scoping.
            session_id (str | None): Session ID for grouping.
            metadata (dict | None): Additional metadata.

        Returns:
            MemoryEntry: The created memory entry.
        """
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """
        Search memories semantically.

        Args:
            query (str): Search query.
            user_id (str | None): Filter by user ID.
            limit (int): Maximum results to return.

        Returns:
            list[MemoryEntry]: Matching memories sorted by relevance.
        """
        pass

    @abstractmethod
    async def get_all(
        self,
        user_id: str | None = None,
    ) -> list[MemoryEntry]:
        """
        Get all memories for a user.

        Args:
            user_id (str | None): Filter by user ID.

        Returns:
            list[MemoryEntry]: All memories.
        """
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """
        Delete a specific memory.

        Args:
            memory_id (str): ID of memory to delete.

        Returns:
            bool: True if deleted successfully.
        """
        pass

    @abstractmethod
    async def clear(self, user_id: str | None = None) -> bool:
        """
        Clear all memories.

        Args:
            user_id (str | None): Clear only this user's memories.

        Returns:
            bool: True if cleared successfully.
        """
        pass


class Mem0Memory(BaseMemory):
    """
    Mem0 semantic memory integration.

    Wraps a Mem0 client (following MemoryStoreClientProtocol) to provide
    async semantic memory operations for agents. Handles sync-to-async
    bridging for synchronous Mem0 clients.

    Attributes:
        client (MemoryStoreClientProtocol): The Mem0 client instance.
        default_user_id (str | None): Default user ID for operations.

    Methods:
        add(): Add a memory to the store.
        search(): Search memories semantically.
        get_all(): Get all memories.
        delete(): Delete a specific memory.
        clear(): Clear all memories.
        get_context_for_query(): Get formatted context for LLM prompts.

    Example:
        >>> from app import MemoryStoreClient
        >>>
        >>> client = MemoryStoreClient(
        ...     base_url="https://mem0.corp.com",
        ...     agent_id="trading-agent-001"
        ... )
        >>>
        >>> memory = Mem0Memory(client=client, default_user_id="user-123")
        >>>
        >>> # Add memories
        >>> await memory.add("User executed buy order for AAPL")
        >>> await memory.add("User prefers limit orders over market orders")
        >>>
        >>> # Search memories
        >>> results = await memory.search("What are user's trading preferences?")
        >>> for mem in results:
        ...     print(f"- {mem.content} (relevance: {mem.relevance_score:.2f})")
        >>>
        >>> # Get context for LLM
        >>> context = await memory.get_context_for_query(
        ...     "Help me place an order",
        ...     max_tokens=1000,
        ... )
        >>> # Use context in LLM prompt

    Note:
        The Mem0 client is typically synchronous, so this class runs
        client methods in a thread pool executor for async compatibility.

    See Also:
        MemoryStoreClientProtocol: Required client interface.
        CompositeMemory: Combine with other memory strategies.
    """

    def __init__(
        self,
        client: MemoryStoreClientProtocol,
        default_user_id: str | None = None,
    ):
        """
        Initialize Mem0Memory.

        Args:
            client (MemoryStoreClientProtocol): Mem0 client instance.
                Must implement add(), search(), get_all(), delete() methods.
            default_user_id (str | None): Default user ID for operations.
                Used when user_id is not provided to individual methods.

        Example:
            >>> from app import MemoryStoreClient
            >>>
            >>> client = MemoryStoreClient(
            ...     base_url="https://mem0.corp.com",
            ...     agent_id="my-agent",
            ... )
            >>> memory = Mem0Memory(client=client, default_user_id="user-123")
        """
        self.client = client
        self.default_user_id = default_user_id

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """
        Get the running event loop for sync-to-async bridging.

        This class is designed for async-only usage. All public methods
        (add, search, get_all, delete, clear, get_context_for_query) are
        async and must be called from within a running event loop.

        Raises:
            RuntimeError: If called outside of an async context (no running event loop).
        """
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "Mem0Memory methods must be called from within an async context "
                "(e.g., inside an async function with a running event loop). "
                "Use 'await memory.add(...)' inside an async function."
            ) from None

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
        Add a memory to the Mem0 store.

        Stores content with optional user/session scoping and metadata.
        The memory becomes searchable via semantic search.

        Args:
            content (str): Memory content to store.
                Should be a complete, descriptive statement.
            user_id (str | None): User ID for scoping. Default: default_user_id.
            session_id (str | None): Session ID for grouping related memories.
            metadata (dict | None): Additional metadata to store with memory.

        Returns:
            MemoryEntry: The created memory entry with assigned ID.

        Raises:
            Exception: If Mem0 client fails to add memory.

        Example:
            >>> # Basic add
            >>> entry = await memory.add("User prefers dark mode")
            >>> print(entry.id)
            >>>
            >>> # With metadata
            >>> entry = await memory.add(
            ...     "User bought AAPL shares",
            ...     session_id="trading-session-123",
            ...     metadata={"symbol": "AAPL", "action": "buy"},
            ... )
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

        Performs semantic search using embeddings to find memories
        relevant to the query. Results are sorted by relevance score.

        Args:
            query (str): Search query in natural language.
            user_id (str | None): Filter results to this user's memories.
            limit (int): Maximum number of results. Default: 10.

        Returns:
            list[MemoryEntry]: Matching memories sorted by relevance (highest first).
                Each entry includes relevance_score (0.0-1.0).

        Example:
            >>> # Add some memories
            >>> await memory.add("User prefers Python programming")
            >>> await memory.add("User works on machine learning projects")
            >>> await memory.add("User enjoys hiking on weekends")
            >>>
            >>> # Search
            >>> results = await memory.search("What does user like to code?")
            >>> for mem in results:
            ...     print(f"{mem.content} (score: {mem.relevance_score:.2f})")
            >>> # "User prefers Python programming (score: 0.89)"
            >>> # "User works on machine learning projects (score: 0.75)"

        Note:
            Returns empty list on error instead of raising exception.
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

        Retrieves all stored memories, optionally filtered by user ID.

        Args:
            user_id (str | None): Filter to this user's memories only.

        Returns:
            list[MemoryEntry]: All matching memories.

        Example:
            >>> # Get all memories
            >>> all_memories = await memory.get_all()
            >>> print(f"Total memories: {len(all_memories)}")
            >>>
            >>> # Get specific user's memories
            >>> user_memories = await memory.get_all(user_id="user-123")

        Note:
            Returns empty list on error instead of raising exception.
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

        Permanently removes a memory from the store by its ID.

        Args:
            memory_id (str): ID of the memory to delete.

        Returns:
            bool: True if deleted successfully, False on failure.

        Example:
            >>> # Get memories
            >>> memories = await memory.search("outdated info")
            >>>
            >>> # Delete specific memory
            >>> if memories:
            ...     success = await memory.delete(memories[0].id)
            ...     if success:
            ...         print("Memory deleted")
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

        Deletes all memories, optionally scoped to a specific user.
        Use with caution as this operation cannot be undone.

        Args:
            user_id (str | None): Clear only this user's memories.
                If None, clears all memories in the store.

        Returns:
            bool: True if cleared successfully, False on failure.

        Example:
            >>> # Clear specific user's memories
            >>> success = await memory.clear(user_id="user-123")
            >>>
            >>> # Clear all memories (use with caution!)
            >>> success = await memory.clear()
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
        formatted as context for LLM prompts. Searches memories,
        formats them as bullet points, and respects token limits.

        Args:
            query (str): The query to find relevant context for.
            user_id (str | None): Filter to user's memories.
            max_tokens (int): Approximate max tokens in context. Default: 2000.
            limit (int): Max memories to include. Default: 5.

        Returns:
            str: Formatted context string ready for LLM prompt.
                Returns empty string if no relevant memories found.

        Example:
            >>> # Use with LLM prompt
            >>> context = await memory.get_context_for_query(
            ...     "Help me write Python code",
            ...     max_tokens=1000,
            ... )
            >>>
            >>> if context:
            ...     prompt = f'''
            ...     Context from previous conversations:
            ...     {context}
            ...
            ...     User: Help me write Python code
            ...     '''
            >>> else:
            ...     prompt = "User: Help me write Python code"

        Note:
            Uses approximate token counting (4 chars per token).
            Memories are included in order of relevance until token limit.
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

    Allows using multiple memory implementations together, routing
    operations to all of them and merging results. Useful for
    combining semantic memory with window memory, entity memory, etc.

    Attributes:
        memories (list[BaseMemory]): List of memory implementations.

    Methods:
        add(): Add to all memory stores.
        search(): Search all stores and merge results.
        get_all(): Get from all stores.
        delete(): Delete from all stores.
        clear(): Clear all stores.

    Example:
        >>> from agentorchestrator.services import Mem0Memory, CompositeMemory
        >>>
        >>> # Combine semantic and window memory
        >>> composite = CompositeMemory([
        ...     WindowMemory(window_size=5),   # Recent context
        ...     Mem0Memory(client=mem0_client),  # Semantic search
        ... ])
        >>>
        >>> # Operations go to all stores
        >>> await composite.add("User prefers Python")
        >>>
        >>> # Search merges and deduplicates results
        >>> results = await composite.search("programming preferences")

    Note:
        - add() returns first successful result
        - search() merges, deduplicates by ID, and sorts by relevance
        - delete() returns True if any store succeeded
        - clear() returns True only if all stores succeeded
    """

    def __init__(self, memories: list[BaseMemory]):
        """
        Initialize composite memory.

        Args:
            memories (list[BaseMemory]): List of memory implementations.
                All operations will be routed to each implementation.

        Example:
            >>> composite = CompositeMemory([
            ...     WindowMemory(window_size=10),
            ...     EntityMemory(llm=llm_client),
            ...     Mem0Memory(client=mem0_client),
            ... ])
        """
        self.memories = memories

    async def add(
        self,
        content: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> MemoryEntry:
        """
        Add memory to all stores.

        Adds the content to all memory implementations in parallel.
        Returns the first successful result.

        Args:
            content (str): Memory content.
            user_id (str | None): User ID for scoping.
            session_id (str | None): Session ID for grouping.
            metadata (dict | None): Additional metadata.

        Returns:
            MemoryEntry: First successful memory entry.

        Raises:
            RuntimeError: If all memory stores fail.

        Example:
            >>> entry = await composite.add("User prefers dark mode")
        """
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
        """
        Search all stores and merge results.

        Searches all memory implementations in parallel, merges results,
        removes duplicates by ID, and sorts by relevance score.

        Args:
            query (str): Search query.
            user_id (str | None): Filter by user ID.
            limit (int): Maximum results to return.

        Returns:
            list[MemoryEntry]: Merged, deduplicated, sorted results.

        Example:
            >>> results = await composite.search("user preferences", limit=5)
            >>> # Results from all memory stores, deduplicated and ranked
        """
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
        """
        Get all memories from all stores.

        Args:
            user_id (str | None): Filter by user ID.

        Returns:
            list[MemoryEntry]: All memories from all stores.

        Example:
            >>> all_memories = await composite.get_all()
        """
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
        """
        Delete from all stores.

        Attempts to delete the memory from all stores.
        Returns True if at least one store succeeded.

        Args:
            memory_id (str): ID of memory to delete.

        Returns:
            bool: True if any store deleted successfully.

        Example:
            >>> success = await composite.delete("mem-123")
        """
        results = await asyncio.gather(
            *[m.delete(memory_id) for m in self.memories],
            return_exceptions=True,
        )
        return any(r is True for r in results)

    async def clear(self, user_id: str | None = None) -> bool:
        """
        Clear all stores.

        Clears all memory implementations. Returns True only if
        all stores cleared successfully.

        Args:
            user_id (str | None): Clear only this user's memories.

        Returns:
            bool: True if all stores cleared successfully.

        Example:
            >>> success = await composite.clear(user_id="user-123")
        """
        results = await asyncio.gather(
            *[m.clear(user_id) for m in self.memories],
            return_exceptions=True,
        )
        return all(r is True for r in results if not isinstance(r, Exception))