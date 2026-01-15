"""
Memory Store Client

Python client for connecting to the Memory Store service from your agents.

Usage:
    from app.client import MemoryStoreClient
    
    # Initialize
    memory = MemoryStoreClient(
        base_url="http://memory-store-service:8000",
        agent_id="my_agent"
    )
    
    # Add memory
    await memory.add_memory("User prefers dark mode")
    
    # Search
    results = await memory.search_memories("What does user prefer?")
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MemoryStoreClient:
    """
    Client for Memory Store service.
    
    Provides async methods for memory operations:
    - add_memory: Store new memories
    - search_memories: Semantic search
    - get_all_memories: Retrieve all memories
    - update_memory: Update existing memory
    - delete_memory: Delete specific memory
    - delete_all_memories: Clear all memories for agent
    - get_memory_history: Get version history
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        agent_id: str | None = None,
        timeout: float = 30.0,
        verify_ssl: bool = True,
    ):
        """
        Initialize Memory Store client.
        
        Args:
            base_url: Memory Store service URL
            agent_id: Default agent ID for operations
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout, verify=verify_ssl)
        logger.info(f"Memory Store client initialized: {base_url}")

    async def health_check(self) -> dict[str, Any]:
        """
        Check service health.
        
        Returns:
            Health status information
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise

    async def add_memory(
        self,
        messages: str | list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Add a memory for the agent.
        
        Args:
            messages: Text or conversation messages to remember
            metadata: Optional metadata (category, timestamp, etc.)
            agent_id: Agent ID (uses default if not provided)
        
        Returns:
            Memory creation result with memory ID
        
        Example:
            result = await memory.add_memory(
                "User prefers dark mode and likes Python",
                metadata={"category": "preferences", "topic": "ui"}
            )
        """
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("agent_id is required")

        try:
            response = await self.client.post(
                f"{self.base_url}/memories",
                json={
                    "agent_id": agent_id,
                    "messages": messages,
                    "metadata": metadata or {},
                },
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Added memory for agent {agent_id}: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to add memory for agent {agent_id}: {e}")
            raise

    async def search_memories(
        self,
        query: str,
        limit: int = 5,
        metadata: dict[str, Any] | None = None,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search memories using semantic similarity.
        
        Args:
            query: Search query (natural language)
            limit: Maximum number of results
            metadata: Optional metadata filters
            agent_id: Agent ID (uses default if not provided)
        
        Returns:
            List of relevant memories with similarity scores
        
        Example:
            memories = await memory.search_memories(
                query="What programming language does user like?",
                limit=5
            )
        """
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("agent_id is required")

        try:
            response = await self.client.post(
                f"{self.base_url}/memories/search",
                json={
                    "agent_id": agent_id,
                    "query": query,
                    "limit": limit,
                    "metadata": metadata,
                },
            )
            response.raise_for_status()
            result = response.json()
            memories = result.get("memories", [])
            logger.info(
                f"Found {len(memories)} memories for agent {agent_id}"
            )
            return memories
        except Exception as e:
            logger.error(f"Failed to search memories for agent {agent_id}: {e}")
            # Return empty list instead of raising to be more resilient
            return []

    async def get_all_memories(
        self,
        limit: int = 100,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all memories for the agent (no search).
        
        Args:
            limit: Maximum number of results
            agent_id: Agent ID (uses default if not provided)
        
        Returns:
            List of all memories
        """
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("agent_id is required")

        try:
            response = await self.client.post(
                f"{self.base_url}/memories/search",
                json={
                    "agent_id": agent_id,
                    "limit": limit,
                    # No query = get all
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("memories", [])
        except Exception as e:
            logger.error(f"Failed to get memories for agent {agent_id}: {e}")
            return []

    async def update_memory(
        self,
        memory_id: str,
        data: str | dict[str, Any],
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing memory.
        
        Args:
            memory_id: ID of memory to update
            data: New memory data
            agent_id: Agent ID (uses default if not provided)
        
        Returns:
            Update result
        """
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("agent_id is required")

        try:
            response = await self.client.put(
                f"{self.base_url}/memories",
                json={
                    "agent_id": agent_id,
                    "memory_id": memory_id,
                    "data": data,
                },
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Updated memory {memory_id} for agent {agent_id}")
            return result
        except Exception as e:
            logger.error(
                f"Failed to update memory {memory_id} for agent {agent_id}: {e}"
            )
            raise

    async def delete_memory(
        self,
        memory_id: str,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Delete a specific memory.
        
        Args:
            memory_id: ID of memory to delete
            agent_id: Agent ID (uses default if not provided)
        
        Returns:
            Deletion result
        """
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("agent_id is required")

        try:
            response = await self.client.delete(
                f"{self.base_url}/memories",
                json={
                    "agent_id": agent_id,
                    "memory_id": memory_id,
                },
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Deleted memory {memory_id} for agent {agent_id}")
            return result
        except Exception as e:
            logger.error(
                f"Failed to delete memory {memory_id} for agent {agent_id}: {e}"
            )
            raise

    async def delete_all_memories(
        self,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Delete all memories for the agent.
        
        Args:
            agent_id: Agent ID (uses default if not provided)
        
        Returns:
            Deletion result
        
        Warning:
            This is irreversible!
        """
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("agent_id is required")

        try:
            response = await self.client.delete(
                f"{self.base_url}/memories/all",
                json={"agent_id": agent_id},
            )
            response.raise_for_status()
            result = response.json()
            logger.warning(f"Deleted all memories for agent {agent_id}")
            return result
        except Exception as e:
            logger.error(
                f"Failed to delete all memories for agent {agent_id}: {e}"
            )
            raise

    async def get_memory_history(
        self,
        memory_id: str,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get version history of a memory.
        
        Args:
            memory_id: ID of memory
            agent_id: Agent ID (uses default if not provided)
        
        Returns:
            List of memory versions
        """
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("agent_id is required")

        try:
            response = await self.client.get(
                f"{self.base_url}/memories/{agent_id}/{memory_id}/history"
            )
            response.raise_for_status()
            result = response.json()
            return result.get("history", [])
        except Exception as e:
            logger.error(
                f"Failed to get history for memory {memory_id} for agent {agent_id}: {e}"
            )
            return []

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
        logger.info("Memory Store client closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Convenience function for creating clients
def create_memory_client(
    base_url: str = "http://localhost:8000",
    agent_id: str | None = None,
    **kwargs,
) -> MemoryStoreClient:
    """
    Create a Memory Store client.
    
    Args:
        base_url: Memory Store service URL
        agent_id: Default agent ID
        **kwargs: Additional arguments for client
    
    Returns:
        Configured MemoryStoreClient
    
    Example:
        memory = create_memory_client(
            base_url="http://memory-store-service:8000",
            agent_id="finance_agent"
        )
    """
    return MemoryStoreClient(base_url=base_url, agent_id=agent_id, **kwargs)


__all__ = ["MemoryStoreClient", "create_memory_client"]
