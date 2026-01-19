"""
AgentOrchestrator Services Module

Core services for LLM integration, gateway management, and external connections.

Usage:
    from agentorchestrator.services import LLMGatewayClient, get_llm_client
    from agentorchestrator.services import RedisService, get_redis_client
"""

# Core LLM services (always available)
from agentorchestrator.services.llm_gateway import (
    LLMGatewayClient,
    OAuthTokenManager,
    create_managed_client,
    get_default_llm_client,
    get_llm_client,
    init_default_llm_client,
    set_default_llm_client,
    timed_lru_cache,
)

# Redis service (optional - requires redis package)
try:
    from agentorchestrator.services.redis import (
        REDIS_AVAILABLE,
        RedisConfig,
        RedisHealthStatus,
        RedisService,
        get_redis_client,
        init_redis_client,
        set_redis_client,
    )
except ImportError:
    REDIS_AVAILABLE = False
    RedisService = None  # type: ignore
    RedisConfig = None  # type: ignore
    RedisHealthStatus = None  # type: ignore
    get_redis_client = None  # type: ignore
    init_redis_client = None  # type: ignore
    set_redis_client = None  # type: ignore

# Vector store (optional - httpx for remote, no deps for in-memory)
from agentorchestrator.services.vector_store import (
    InMemoryVectorStore,
    VectorDocument,
    VectorMatch,
    VectorStoreConfig,
    VectorStoreService,
)

__all__ = [
    # LLM Gateway
    "LLMGatewayClient",
    "OAuthTokenManager",
    "get_llm_client",
    "get_default_llm_client",
    "set_default_llm_client",
    "init_default_llm_client",
    "create_managed_client",
    "timed_lru_cache",
    # Redis Service
    "REDIS_AVAILABLE",
    "RedisService",
    "RedisConfig",
    "RedisHealthStatus",
    "get_redis_client",
    "init_redis_client",
    "set_redis_client",
    # Vector Store
    "VectorStoreConfig",
    "VectorStoreService",
    "VectorDocument",
    "VectorMatch",
    "InMemoryVectorStore",
]
