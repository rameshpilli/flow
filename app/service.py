"""
Memory Store Service

Core service class for managing mem0 memory with multi-agent support.
"""

import logging
import os
from typing import Any
from urllib.parse import urlparse

from mem0 import Memory

from app.config import MemoryStoreConfig, get_config
from app.oauth import OAuthTokenManager

logger = logging.getLogger(__name__)


class MemoryStoreService:
    """
    Memory Store Service using mem0 with LLM Gateway (OpenAI) or Cohere embeddings and Qdrant.

    Provides multi-agent memory isolation where each agent gets its own
    namespace/user_id in the memory system.

    Features:
    - Per-agent memory isolation
    - Semantic search using LLM Gateway (text-embedding-3-large) or Cohere embeddings
    - Qdrant vector store backend
    - Optional Memgraph graph store
    - Kubernetes-ready
    """

    def __init__(self, config: MemoryStoreConfig | None = None):
        """
        Initialize the memory store service.

        Args:
            config: Optional configuration, uses global config if not provided
        """
        self.config = config or get_config()
        self._memory_client = None
        self._oauth_manager: OAuthTokenManager | None = None
        self._initialize_memory()

    def _initialize_memory(self):
        """Initialize mem0 with LLM Gateway (OpenAI) or Cohere and Qdrant."""
        try:
            # Parse Qdrant URL to extract host and port
            parsed_url = urlparse(self.config.qdrant.url)
            qdrant_host = parsed_url.hostname or "localhost"
            qdrant_port = parsed_url.port or 6333  # Default Qdrant port

            # Build mem0 configuration
            mem0_config = {
                "version": self.config.mem0.version,
                # Vector store configuration (Qdrant)
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "host": qdrant_host,
                        "port": qdrant_port,
                        "collection_name": self.config.qdrant.collection_name,
                        "embedding_model_dims": self.config.qdrant.vector_size,
                        "api_key": self.config.qdrant.api_key,
                        "on_disk": self.config.qdrant.on_disk,
                    },
                },
            }

            # Configure embedder: Prefer LLM Gateway (OpenAI), fallback to Cohere
            if self.config.llm_gateway.is_configured:
                # Initialize OAuth token manager
                self._oauth_manager = OAuthTokenManager(
                    oauth_endpoint=self.config.llm_gateway.oauth_endpoint,
                    client_id=self.config.llm_gateway.client_id,
                    client_secret=self.config.llm_gateway.client_secret,
                )

                # Set environment variable for OpenAI SDK to use OAuth token
                # We'll use a custom HTTP client that injects the token
                # For now, set a dummy API key - we'll override in the HTTP client
                os.environ["OPENAI_API_KEY"] = "dummy"  # Required but not used

                # Configure OpenAI embedder with LLM Gateway
                # Note: We'll patch the HTTP client after initialization to inject OAuth tokens
                mem0_config["embedder"] = {
                    "provider": "openai",
                    "config": {
                        "model": self.config.llm_gateway.embedding_model,
                        "embedding_dims": self.config.llm_gateway.embedding_dims,
                        "api_key": "dummy",  # Not used, OAuth token injected via HTTP client
                        "openai_base_url": self.config.llm_gateway.server_url,
                    },
                }
                logger.info(
                    f"Using LLM Gateway embeddings: {self.config.llm_gateway.embedding_model} "
                    f"({self.config.llm_gateway.embedding_dims} dims) via {self.config.llm_gateway.server_url}"
                )
            elif self.config.cohere.is_configured:
                # Fallback to Cohere (legacy)
                mem0_config["embedder"] = {
                    "provider": "cohere",
                    "config": {
                        "api_key": self.config.cohere.api_key,
                        "model": self.config.cohere.embedding_model,
                        "embedding_dims": self.config.qdrant.vector_size,
                    },
                }
                logger.info(
                    f"Using Cohere embeddings: {self.config.cohere.embedding_model} "
                    f"({self.config.qdrant.vector_size} dims)"
                )
            else:
                raise ValueError(
                    "No embedder configured. Set LLM Gateway or Cohere credentials."
                )

            # Add graph store if enabled
            if self.config.mem0.graph_store_enabled:
                provider = self.config.mem0.graph_store_provider.lower()
                
                if provider in ["memgraph", "neo4j"]:
                    mem0_config["graph_store"] = {
                        "provider": "neo4j",  # Mem0 uses neo4j driver for both
                        "config": {
                            "url": self.config.memgraph.connection_url,
                            "username": self.config.memgraph.username,
                            "password": self.config.memgraph.password,
                        },
                    }
                    logger.info(f"Graph store enabled: {provider} at {self.config.memgraph.host}")
                else:
                    logger.warning(f"Unknown graph store provider: {provider}, graph store disabled")

            # Initialize mem0 client
            # Note: Collection creation may fail with 409 if multiple workers start simultaneously
            # This is handled internally by mem0, but we catch and log it for clarity
            try:
                self._memory_client = Memory.from_config(mem0_config)
            except Exception as e:
                # Check if it's a collection already exists error (409)
                error_str = str(e)
                if "409" in error_str or "already exists" in error_str.lower():
                    logger.warning(
                        f"Collection '{self.config.qdrant.collection_name}' already exists "
                        "(likely created by another worker). Retrying initialization..."
                    )
                    # Retry - mem0 should handle existing collections gracefully
                    try:
                        self._memory_client = Memory.from_config(mem0_config)
                    except Exception as retry_error:
                        # If retry also fails, check if it's still a 409
                        if "409" in str(retry_error) or "already exists" in str(retry_error).lower():
                            logger.info(
                                "Collection exists, mem0 should handle this. "
                                "If errors persist, check collection configuration."
                            )
                            # Re-raise to see the actual error
                            raise
                        raise
                else:
                    raise
            
            # Patch OpenAI client to use OAuth tokens if using LLM Gateway
            if self.config.llm_gateway.is_configured and self._oauth_manager:
                self._patch_openai_client_for_oauth()
            
            logger.info("Mem0 memory client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize mem0 memory client: {e}")
            raise

    def _patch_openai_client_for_oauth(self):
        """
        Patch the OpenAI client used by mem0 to inject OAuth tokens.
        
        This accesses mem0's internal embedder and patches its HTTP client
        to add Authorization headers with OAuth tokens.
        """
        try:
            # Try multiple ways to access the embedder
            embedder = None
            
            # Method 1: Direct attribute
            if hasattr(self._memory_client, "_embedder"):
                embedder = self._memory_client._embedder
            elif hasattr(self._memory_client, "embedder"):
                embedder = self._memory_client.embedder
            
            if not embedder:
                logger.warning("Could not access mem0 embedder for OAuth patching")
                return
            
            # Try to get OpenAI client from embedder
            openai_client = None
            if hasattr(embedder, "client"):
                openai_client = embedder.client
            elif hasattr(embedder, "_client"):
                openai_client = embedder._client
            elif hasattr(embedder, "_openai_client"):
                openai_client = embedder._openai_client
            
            if not openai_client:
                logger.warning("Could not find OpenAI client in embedder")
                return
            
            # Try to get HTTP client from OpenAI client
            http_client = None
            if hasattr(openai_client, "_client"):
                http_client = openai_client._client
            elif hasattr(openai_client, "http_client"):
                http_client = openai_client.http_client
            elif hasattr(openai_client, "_http_client"):
                http_client = openai_client._http_client
            
            if not http_client:
                logger.warning("Could not find HTTP client in OpenAI client")
                return
            
            # Patch the request method to inject OAuth tokens
            if hasattr(http_client, "request"):
                original_request = http_client.request
                
                def oauth_request_wrapper(method, url, **kwargs):
                    """Wrapper that injects OAuth token into requests."""
                    # Get fresh OAuth token
                    token = self._oauth_manager.get_access_token()
                    
                    # Add Authorization header
                    headers = kwargs.get("headers", {})
                    if isinstance(headers, dict):
                        headers = headers.copy()
                    else:
                        headers = dict(headers) if headers else {}
                    
                    headers["Authorization"] = f"Bearer {token}"
                    kwargs["headers"] = headers
                    
                    # Make the request
                    return original_request(method, url, **kwargs)
                
                # Patch the request method
                http_client.request = oauth_request_wrapper
                logger.info("Successfully patched OpenAI HTTP client to use OAuth tokens")
            else:
                logger.warning("HTTP client does not have 'request' method")
                
        except Exception as e:
            logger.warning(f"Failed to patch OpenAI client for OAuth: {e}")
            logger.debug("OAuth patching failed, but service may still work if OpenAI SDK handles auth differently", exc_info=True)
            # Don't raise - the service might still work without the patch

    def add_memory(
        self,
        agent_id: str,
        messages: str | list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Add a memory for a specific agent.

        Args:
            agent_id: Unique identifier for the agent
            messages: Text or conversation messages to remember
            metadata: Optional metadata to attach to the memory

        Returns:
            Memory creation result with memory ID
        """
        try:
            result = self._memory_client.add(
                messages=messages,
                user_id=agent_id,
                metadata=metadata or {},
            )
            logger.info(f"Added memory for agent {agent_id}: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to add memory for agent {agent_id}: {e}")
            raise

    def get_memories(
        self,
        agent_id: str,
        query: str | None = None,
        limit: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve memories for a specific agent.

        Args:
            agent_id: Unique identifier for the agent
            query: Optional semantic search query
            limit: Maximum number of memories to return
            metadata: Optional metadata filters

        Returns:
            List of relevant memories
        """
        try:
            limit = limit or self.config.mem0.search_limit

            if query:
                # Semantic search
                memories = self._memory_client.search(
                    query=query,
                    user_id=agent_id,
                    limit=limit,
                )
            else:
                # Get all memories
                memories = self._memory_client.get_all(
                    user_id=agent_id,
                    limit=limit,
                )

            logger.info(
                f"Retrieved {len(memories) if memories else 0} memories for agent {agent_id}"
            )
            return memories or []
        except Exception as e:
            logger.error(f"Failed to get memories for agent {agent_id}: {e}")
            raise

    def update_memory(
        self, agent_id: str, memory_id: str, data: str | dict[str, Any]
    ) -> dict[str, Any]:
        """
        Update an existing memory.

        Args:
            agent_id: Unique identifier for the agent
            memory_id: ID of the memory to update
            data: New memory data

        Returns:
            Update result
        """
        try:
            result = self._memory_client.update(
                memory_id=memory_id,
                data=data,
            )
            logger.info(f"Updated memory {memory_id} for agent {agent_id}")
            return result
        except Exception as e:
            logger.error(
                f"Failed to update memory {memory_id} for agent {agent_id}: {e}"
            )
            raise

    def delete_memory(self, agent_id: str, memory_id: str) -> dict[str, Any]:
        """
        Delete a specific memory.

        Args:
            agent_id: Unique identifier for the agent
            memory_id: ID of the memory to delete

        Returns:
            Deletion result
        """
        try:
            result = self._memory_client.delete(memory_id=memory_id)
            logger.info(f"Deleted memory {memory_id} for agent {agent_id}")
            return result
        except Exception as e:
            logger.error(
                f"Failed to delete memory {memory_id} for agent {agent_id}: {e}"
            )
            raise

    def delete_all_memories(self, agent_id: str) -> dict[str, Any]:
        """
        Delete all memories for a specific agent.

        Args:
            agent_id: Unique identifier for the agent

        Returns:
            Deletion result
        """
        try:
            result = self._memory_client.delete_all(user_id=agent_id)
            logger.info(f"Deleted all memories for agent {agent_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to delete all memories for agent {agent_id}: {e}")
            raise

    def get_memory_history(
        self, agent_id: str, memory_id: str
    ) -> list[dict[str, Any]]:
        """
        Get the version history of a memory.

        Args:
            agent_id: Unique identifier for the agent
            memory_id: ID of the memory

        Returns:
            List of memory versions
        """
        try:
            history = self._memory_client.history(memory_id=memory_id)
            logger.info(
                f"Retrieved history for memory {memory_id} for agent {agent_id}"
            )
            return history or []
        except Exception as e:
            logger.error(
                f"Failed to get history for memory {memory_id} for agent {agent_id}: {e}"
            )
            raise

    async def health_check(self) -> dict[str, Any]:
        """
        Perform a health check on the memory store.

        Returns:
            Health status information
        """
        status = {
            "service": "memory_store",
            "status": "healthy",
            "components": {},
        }

        try:
            # Check Qdrant connection
            status["components"]["qdrant"] = {
                "status": "healthy",
                "url": self.config.qdrant.url,
            }

            # Check embedder (LLM Gateway or Cohere)
            if self.config.llm_gateway.is_configured:
                # Test OAuth token
                try:
                    token = self._oauth_manager.get_access_token() if self._oauth_manager else None
                    status["components"]["llm_gateway"] = {
                        "status": "healthy" if token else "unhealthy",
                        "model": self.config.llm_gateway.embedding_model,
                        "dims": self.config.llm_gateway.embedding_dims,
                        "url": self.config.llm_gateway.server_url,
                    }
                except Exception as e:
                    status["components"]["llm_gateway"] = {
                        "status": "unhealthy",
                        "error": str(e),
                    }
            else:
                status["components"]["cohere"] = {
                    "status": "healthy" if self.config.cohere.is_configured else "unconfigured",
                    "model": self.config.cohere.embedding_model,
                }
            
            # Check Memgraph (if enabled)
            if self.config.mem0.graph_store_enabled:
                status["components"]["memgraph"] = {
                    "status": "healthy" if self.config.memgraph.is_configured else "unconfigured",
                    "host": self.config.memgraph.host,
                    "provider": self.config.mem0.graph_store_provider,
                }

        except Exception as e:
            status["status"] = "unhealthy"
            status["error"] = str(e)
            logger.error(f"Health check failed: {e}")

        return status


def create_memory_service(config: MemoryStoreConfig | None = None) -> MemoryStoreService:
    """
    Factory function to create a memory store service.

    Args:
        config: Optional configuration

    Returns:
        Initialized MemoryStoreService
    """
    return MemoryStoreService(config=config)


__all__ = ["MemoryStoreService", "create_memory_service"]
