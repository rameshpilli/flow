"""
Memory Store Service

A production-ready mem0-based memory store service with:
- Multi-agent memory isolation
- Cohere Compass vector store
- LLM Gateway integration
- Kubernetes-ready deployment
- RESTful API

Usage:
    # As a service
    from memory_store import MemoryStoreService
    service = MemoryStoreService()
    
    # As a client
    from memory_store import MemoryStoreClient
    memory = MemoryStoreClient(
        base_url="http://memory-store-service:8000",
        agent_id="my_agent"
    )
"""

__version__ = "0.1.0"

from memory_store.client import MemoryStoreClient, create_memory_client
from memory_store.config import MemoryStoreConfig, get_config
from memory_store.service import MemoryStoreService

__all__ = [
    # Client
    "MemoryStoreClient",
    "create_memory_client",
    # Config
    "MemoryStoreConfig",
    "get_config",
    # Service
    "MemoryStoreService",
]
