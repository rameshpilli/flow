"""
Memory Store Configuration Module

Centralized configuration management using environment variables.
"""

import logging
import os
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv

    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    pass

logger = logging.getLogger(__name__)


class CohereConfig(BaseSettings):
    """Cohere configuration for embeddings (deprecated - use LLM Gateway instead)."""

    model_config = SettingsConfigDict(env_prefix="COHERE_", case_sensitive=False)

    api_key: str = Field(default="", description="Cohere API key")
    embedding_model: str = Field(
        default="embed-english-v3.0", description="Cohere embedding model"
    )

    @property
    def is_configured(self) -> bool:
        """Check if Cohere is properly configured."""
        return bool(self.api_key)


class LLMGatewayConfig(BaseSettings):
    """LLM Gateway configuration for embeddings via OpenAI-compatible API."""

    model_config = SettingsConfigDict(env_prefix="LLM_", case_sensitive=False)

    # Gateway URL
    server_url: str = Field(default="", description="LLM Gateway base URL")
    
    # OAuth configuration
    oauth_endpoint: str = Field(default="", description="OAuth token endpoint URL")
    client_id: str = Field(default="", description="OAuth client ID")
    client_secret: str = Field(default="", description="OAuth client secret")
    
    # Embedding model configuration
    embedding_model: str = Field(
        default="text-embedding-3-large", description="OpenAI embedding model"
    )
    embedding_dims: int = Field(
        default=3072, description="Embedding dimensions (3072 for text-embedding-3-large)"
    )

    @property
    def is_configured(self) -> bool:
        """Check if LLM Gateway is properly configured."""
        return bool(
            self.server_url
            and self.oauth_endpoint
            and self.client_id
            and self.client_secret
        )
    
    @property
    def embeddings_url(self) -> str:
        """Get the embeddings endpoint URL."""
        base = self.server_url.rstrip("/")
        return f"{base}/embeddings"


class QdrantConfig(BaseSettings):
    """Qdrant vector store configuration."""

    model_config = SettingsConfigDict(env_prefix="QDRANT_", case_sensitive=False)

    # Connection settings
    url: str = Field(default="http://localhost:6333", description="Qdrant server URL")
    api_key: str | None = Field(default=None, description="Qdrant API key (for cloud)")
    collection_name: str = Field(default="memory_store", description="Collection name")

    # Vector settings
    vector_size: int = Field(default=3072, description="Embedding dimensions (3072 for text-embedding-3-large)")
    distance_metric: str = Field(default="cosine", description="Distance metric")

    # Performance settings
    on_disk: bool = Field(default=False, description="Store vectors on disk")
    shard_number: int = Field(default=1, description="Number of shards")
    replication_factor: int = Field(default=1, description="Replication factor")

    @property
    def is_configured(self) -> bool:
        """Check if Qdrant is properly configured."""
        return bool(self.url)


class MemgraphConfig(BaseSettings):
    """Memgraph graph store configuration (optional)."""

    model_config = SettingsConfigDict(env_prefix="MEMGRAPH_", case_sensitive=False)

    # Connection settings
    host: str = Field(default="localhost", description="Memgraph host")
    port: int = Field(default=7687, description="Memgraph Bolt port")
    username: str = Field(default="", description="Memgraph username (optional)")
    password: str = Field(default="", description="Memgraph password (optional)")

    # Connection string alternative
    url: str | None = Field(
        default=None, description="Full connection URL (overrides host/port)"
    )

    @property
    def is_configured(self) -> bool:
        """Check if Memgraph is properly configured."""
        return bool(self.url or self.host)

    @property
    def connection_url(self) -> str:
        """Get connection URL."""
        if self.url:
            return self.url
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"bolt://{auth}{self.host}:{self.port}"


class Mem0Config(BaseSettings):
    """Mem0 configuration."""

    model_config = SettingsConfigDict(env_prefix="MEM0_", case_sensitive=False)

    # Version and organization
    version: str = Field(default="v1.1", description="Mem0 version")
    org_id: str | None = Field(default=None, description="Organization ID")

    # Storage settings
    graph_store_enabled: bool = Field(
        default=False, description="Enable graph store for relationships"
    )
    graph_store_provider: str = Field(
        default="memgraph", description="Graph store provider (memgraph or neo4j)"
    )

    # Search settings
    search_limit: int = Field(default=10, description="Default search limit")
    search_threshold: float = Field(default=0.7, description="Search similarity threshold")


class ServiceConfig(BaseSettings):
    """Service configuration."""

    model_config = SettingsConfigDict(env_prefix="SERVICE_", case_sensitive=False)

    host: str = Field(default="0.0.0.0", description="Service host")
    port: int = Field(default=8000, description="Service port")
    workers: int = Field(default=4, description="Number of workers")
    log_level: str = Field(default="INFO", description="Log level")
    cors_enabled: bool = Field(default=True, description="Enable CORS")
    cors_origins: str = Field(default="*", description="CORS origins (comma-separated)")

    # Health check settings
    health_check_interval: int = Field(
        default=30, description="Health check interval in seconds"
    )

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_per_minute: int = Field(
        default=60, description="Rate limit per minute per agent"
    )


class MemoryStoreConfig(BaseSettings):
    """Main Memory Store configuration."""

    model_config = SettingsConfigDict(case_sensitive=False)

    # Sub-configurations
    cohere: CohereConfig = Field(default_factory=CohereConfig)
    llm_gateway: LLMGatewayConfig = Field(default_factory=LLMGatewayConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    memgraph: MemgraphConfig = Field(default_factory=MemgraphConfig)
    mem0: Mem0Config = Field(default_factory=Mem0Config)
    service: ServiceConfig = Field(default_factory=ServiceConfig)

    def __init__(self, **kwargs):
        """Initialize with nested configs from environment."""
        super().__init__(**kwargs)
        # Load nested configs from environment
        self.cohere = CohereConfig()
        self.llm_gateway = LLMGatewayConfig()
        self.qdrant = QdrantConfig()
        self.memgraph = MemgraphConfig()
        self.mem0 = Mem0Config()
        self.service = ServiceConfig()

    def validate_config(self) -> tuple[bool, list[str]]:
        """
        Validate configuration and return (is_valid, error_messages).

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Require either LLM Gateway (preferred) or Cohere (legacy)
        if not self.llm_gateway.is_configured and not self.cohere.is_configured:
            errors.append(
                "Either LLM Gateway (LLM_SERVER_URL, LLM_OAUTH_ENDPOINT, LLM_CLIENT_ID, LLM_CLIENT_SECRET) "
                "or Cohere (COHERE_API_KEY) is required"
            )

        if not self.qdrant.is_configured:
            errors.append("Qdrant URL is required (QDRANT_URL)")

        return len(errors) == 0, errors

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary (for debugging, excludes secrets)."""
        return {
            "cohere": {
                "embedding_model": self.cohere.embedding_model,
                "is_configured": self.cohere.is_configured,
            },
            "llm_gateway": {
                "server_url": self.llm_gateway.server_url,
                "embedding_model": self.llm_gateway.embedding_model,
                "embedding_dims": self.llm_gateway.embedding_dims,
                "is_configured": self.llm_gateway.is_configured,
            },
            "qdrant": {
                "url": self.qdrant.url,
                "collection_name": self.qdrant.collection_name,
                "vector_size": self.qdrant.vector_size,
                "is_configured": self.qdrant.is_configured,
            },
            "memgraph": {
                "host": self.memgraph.host,
                "port": self.memgraph.port,
                "is_configured": self.memgraph.is_configured,
            },
            "mem0": {
                "version": self.mem0.version,
                "search_limit": self.mem0.search_limit,
                "graph_store_enabled": self.mem0.graph_store_enabled,
                "graph_store_provider": self.mem0.graph_store_provider,
            },
            "service": {
                "host": self.service.host,
                "port": self.service.port,
                "workers": self.service.workers,
                "log_level": self.service.log_level,
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
#                           SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_config: MemoryStoreConfig | None = None


def get_config() -> MemoryStoreConfig:
    """
    Get the global configuration instance (singleton).

    Loads from environment variables on first call.
    """
    global _config
    if _config is None:
        _config = MemoryStoreConfig()
        logger.info("Memory Store configuration loaded from environment")

        # Validate config
        is_valid, errors = _config.validate_config()
        if not is_valid:
            logger.error(f"Configuration validation failed: {errors}")
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")

    return _config


def reload_config() -> MemoryStoreConfig:
    """Reload configuration from environment variables."""
    global _config
    _config = MemoryStoreConfig()
    logger.info("Memory Store configuration reloaded")
    return _config


def set_config(config: MemoryStoreConfig) -> None:
    """Set a custom configuration (for testing)."""
    global _config
    _config = config
    logger.info("Custom Memory Store configuration set")


__all__ = [
    "MemoryStoreConfig",
    "CohereConfig",
    "LLMGatewayConfig",
    "QdrantConfig",
    "MemgraphConfig",
    "Mem0Config",
    "ServiceConfig",
    "get_config",
    "reload_config",
    "set_config",
]
