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
    from app import MemoryStoreService
    service = MemoryStoreService()
    
    # As a client
    from app import MemoryStoreClient
    memory = MemoryStoreClient(
        base_url="http://memory-store-service:8000",
        agent_id="my_agent"
    )
"""

__version__ = "0.1.0"

from app.client import MemoryStoreClient, create_memory_client
from app.config import MemoryStoreConfig, get_config
from app.service import MemoryStoreService, create_memory_service

__all__ = [
    # Client
    "MemoryStoreClient",
    "create_memory_client",
    # Config
    "MemoryStoreConfig",
    "get_config",
    # Service
    "MemoryStoreService",
    "create_memory_service",
]
