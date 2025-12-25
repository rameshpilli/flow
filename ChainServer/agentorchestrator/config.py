"""
AgentOrchestrator Configuration Module

Centralized configuration management using environment variables.
All settings are loaded once and distributed downstream.

Usage:
    from agentorchestrator.config import get_config, Config

    config = get_config()
    llm_client = config.get_llm_client()
    summarizer = config.get_summarizer()
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv

    # Try to load .env from multiple locations
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


def _get_env(key: str, default: str | None = None) -> str | None:
    """Get environment variable with optional default."""
    return os.getenv(key, default)


def _get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def _get_env_int(key: str, default: int) -> int:
    """Get integer environment variable."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _get_env_float(key: str, default: float) -> float:
    """Get float environment variable."""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


# ═══════════════════════════════════════════════════════════════════════════════
#                           CONFIGURATION DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class LLMConfig:
    """LLM Gateway configuration."""

    server_url: str = ""
    model_name: str = "gpt-4"
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout: float = 60.0

    # OAuth authentication
    oauth_endpoint: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    oauth_grant_type: str = "client_credentials"
    oauth_scope: str = "read"
    oauth_token_ttl: int = 3500

    # API Key authentication (alternative to OAuth)
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load LLM config from environment variables."""
        # Support both LLM_SERVER_URL and LLM_GATEWAY_URL for compatibility
        server_url = _get_env("LLM_SERVER_URL") or _get_env("LLM_GATEWAY_URL", "")
        return cls(
            server_url=server_url,
            model_name=_get_env("LLM_MODEL_NAME", "gpt-4"),
            temperature=_get_env_float("LLM_TEMPERATURE", 0.0),
            max_tokens=_get_env_int("LLM_MAX_TOKENS", 4096),
            timeout=_get_env_float("LLM_TIMEOUT", 60.0),
            oauth_endpoint=_get_env("LLM_OAUTH_ENDPOINT"),
            client_id=_get_env("LLM_CLIENT_ID"),
            client_secret=_get_env("LLM_CLIENT_SECRET"),
            oauth_grant_type=_get_env("LLM_OAUTH_GRANT_TYPE", "client_credentials"),
            oauth_scope=_get_env("LLM_OAUTH_SCOPE", "read"),
            oauth_token_ttl=_get_env_int("OAUTH_TOKEN_TTL", 3500),
            api_key=_get_env("LLM_API_KEY"),
        )

    @property
    def is_configured(self) -> bool:
        """Check if LLM is properly configured."""
        has_server = bool(self.server_url)
        has_auth = bool(self.api_key) or all([self.oauth_endpoint, self.client_id, self.client_secret])
        return has_server and has_auth


@dataclass
class FoundationConfig:
    """Foundation service configuration."""

    api_url: str = ""
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "FoundationConfig":
        """Load Foundation config from environment variables."""
        return cls(
            api_url=_get_env("FOUNDATION_API_URL", ""),
            api_key=_get_env("FOUNDATION_API_KEY"),
        )


@dataclass
class AgentConfig:
    """
    Configuration for a single data agent.

    This is a generic configuration that can be used for any agent type.
    Domain-specific agents should be configured at the application level,
    not in this base orchestrator package.
    """

    name: str = ""
    url: str = ""
    api_key: str | None = None
    timeout: float = 30.0
    retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentsConfig:
    """
    Dynamic agents configuration.

    Instead of hardcoded domain-specific agents (SEC, news, etc.),
    this provides a flexible registry that can be populated at runtime.

    Usage:
        # At application level, not in agentorchestrator
        config.agents.register("my_agent", AgentConfig(url="...", api_key="..."))
        agent_cfg = config.agents.get("my_agent")
    """

    _agents: dict[str, AgentConfig] = field(default_factory=dict)

    def register(self, name: str, config: AgentConfig) -> None:
        """Register an agent configuration."""
        config.name = name
        self._agents[name] = config

    def get(self, name: str) -> AgentConfig | None:
        """Get agent configuration by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        """List all registered agent names."""
        return list(self._agents.keys())

    @classmethod
    def from_env(cls) -> "AgentsConfig":
        """
        Load agents config from environment variables.

        Supports two formats:

        1. JSON array format (AGENT_CONFIG):
            AGENT_CONFIG='[
              {"name": "sec", "mcp_url": "https://...", "mcp_tool": "sec_tool", ...},
              {"name": "news", "mcp_url": "https://...", "mcp_tool": "news_tool", ...}
            ]'

        2. Individual env vars (AGENT_<NAME>_URL pattern):
            AGENT_DATA_URL=http://data-service/api
            AGENT_DATA_API_KEY=xxx
        """
        import json

        config = cls()

        # Try to load from AGENT_CONFIG JSON first
        agent_config_json = _get_env("AGENT_CONFIG")
        if agent_config_json:
            try:
                agents_list = json.loads(agent_config_json)
                if isinstance(agents_list, list):
                    for agent_data in agents_list:
                        if isinstance(agent_data, dict) and "name" in agent_data:
                            name = agent_data["name"]
                            # Map MCP-specific fields to generic AgentConfig
                            config.register(
                                name,
                                AgentConfig(
                                    name=name,
                                    url=agent_data.get("mcp_url", ""),
                                    api_key=agent_data.get("mcp_bearer_token"),
                                    timeout=float(agent_data.get("timeout", 30.0)),
                                    retries=int(agent_data.get("retries", 3)),
                                    metadata={
                                        "mcp_tool": agent_data.get("mcp_tool"),
                                        "cache_enabled": agent_data.get("cache_enabled", False),
                                        "cache_seconds": agent_data.get("cache_seconds", 3600),
                                        "cache_size": agent_data.get("cache_size", 128),
                                    },
                                ),
                            )
                    logger.info(f"Loaded {len(config._agents)} agents from AGENT_CONFIG")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse AGENT_CONFIG JSON: {e}")

        # Also scan for individual AGENT_<NAME>_URL env vars
        # These will override any agents with the same name from AGENT_CONFIG
        agent_urls = {
            k.replace("AGENT_", "").replace("_URL", "").lower(): v
            for k, v in os.environ.items()
            if k.startswith("AGENT_") and k.endswith("_URL") and k != "AGENT_CONFIG"
        }

        for agent_name, url in agent_urls.items():
            api_key_env = f"AGENT_{agent_name.upper()}_API_KEY"
            timeout_env = f"AGENT_{agent_name.upper()}_TIMEOUT"
            config.register(
                agent_name,
                AgentConfig(
                    url=url,
                    api_key=_get_env(api_key_env),
                    timeout=_get_env_float(timeout_env, 30.0),
                ),
            )

        return config


@dataclass
class ChainConfig:
    """Chain execution configuration."""

    max_parallel_steps: int = 5
    default_timeout_ms: int = 30000
    default_retries: int = 3
    error_handling: str = "fail_fast"  # "fail_fast", "continue", "retry"

    @classmethod
    def from_env(cls) -> "ChainConfig":
        """Load chain config from environment variables."""
        return cls(
            max_parallel_steps=_get_env_int("CHAIN_MAX_PARALLEL_STEPS", 5),
            default_timeout_ms=_get_env_int("CHAIN_DEFAULT_TIMEOUT_MS", 30000),
            default_retries=_get_env_int("CHAIN_DEFAULT_RETRIES", 3),
            error_handling=_get_env("CHAIN_ERROR_HANDLING", "fail_fast"),
        )


@dataclass
class SummarizerConfig:
    """Summarizer configuration."""

    max_tokens: int = 4000
    chunk_size: int = 2000
    chunk_overlap: int = 200
    strategy: str = "map_reduce"

    @classmethod
    def from_env(cls) -> "SummarizerConfig":
        """Load summarizer config from environment variables."""
        return cls(
            max_tokens=_get_env_int("SUMMARIZER_MAX_TOKENS", 4000),
            chunk_size=_get_env_int("SUMMARIZER_CHUNK_SIZE", 2000),
            chunk_overlap=_get_env_int("SUMMARIZER_CHUNK_OVERLAP", 200),
            strategy=_get_env("SUMMARIZER_STRATEGY", "map_reduce"),
        )


@dataclass
class CacheConfig:
    """Cache configuration."""

    ttl_seconds: int = 300

    @classmethod
    def from_env(cls) -> "CacheConfig":
        """Load cache config from environment variables."""
        return cls(
            ttl_seconds=_get_env_int("CACHE_TTL_SECONDS", 300),
        )


@dataclass
class ContextStoreConfig:
    """
    Context store configuration for pluggable storage backends.

    Supports multiple deployment scenarios:
    - Local development: backend="memory" (no external dependencies)
    - Same container: backend="redis", host="localhost" (your current setup)
    - Kubernetes: backend="redis", host="redis-service.namespace"
    - AWS ElastiCache: backend="redis", host="xxx.cache.amazonaws.com"
    - Long-term memory: backend="mem0" (semantic memory with embeddings)

    Environment Variables:
        CONTEXT_STORE_BACKEND: "memory", "redis", or "mem0"
        CONTEXT_STORE_REDIS_HOST: Redis host (default: localhost)
        CONTEXT_STORE_REDIS_PORT: Redis port (default: 6379)
        CONTEXT_STORE_REDIS_PASSWORD: Redis password (optional)
        CONTEXT_STORE_REDIS_DB: Redis database number (default: 0)
        CONTEXT_STORE_REDIS_MAXMEMORY: Memory limit (e.g., "128mb", "1gb")
        CONTEXT_STORE_TTL: Default TTL in seconds (default: 3600)
        CONTEXT_STORE_MEM0_API_KEY: mem0 API key (for cloud mem0)
        CONTEXT_STORE_MEM0_HOST: mem0 host (for self-hosted)
    """

    # Backend selection
    backend: str = "memory"  # "memory", "redis", or "mem0"

    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_db: int = 0
    redis_maxmemory: str | None = None
    redis_maxmemory_policy: str = "allkeys-lru"
    redis_max_connections: int = 10
    redis_key_prefix: str = "agentorchestrator:ctx:"
    redis_ssl: bool = False
    redis_ssl_cert_reqs: str | None = None  # For AWS ElastiCache TLS

    # Common settings
    default_ttl_seconds: int = 3600
    offload_threshold_bytes: int = 100_000  # 100KB

    # mem0 settings (for long-term semantic memory)
    mem0_api_key: str | None = None
    mem0_host: str | None = None  # For self-hosted mem0
    mem0_user_id: str | None = None  # For user-scoped memory
    mem0_org_id: str | None = None

    @classmethod
    def from_env(cls) -> "ContextStoreConfig":
        """Load context store config from environment variables."""
        return cls(
            backend=_get_env("CONTEXT_STORE_BACKEND", "memory"),
            # Redis
            redis_host=_get_env("CONTEXT_STORE_REDIS_HOST", "localhost"),
            redis_port=_get_env_int("CONTEXT_STORE_REDIS_PORT", 6379),
            redis_password=_get_env("CONTEXT_STORE_REDIS_PASSWORD"),
            redis_db=_get_env_int("CONTEXT_STORE_REDIS_DB", 0),
            redis_maxmemory=_get_env("CONTEXT_STORE_REDIS_MAXMEMORY"),
            redis_maxmemory_policy=_get_env("CONTEXT_STORE_REDIS_MAXMEMORY_POLICY", "allkeys-lru"),
            redis_max_connections=_get_env_int("CONTEXT_STORE_REDIS_MAX_CONNECTIONS", 10),
            redis_key_prefix=_get_env("CONTEXT_STORE_REDIS_KEY_PREFIX", "agentorchestrator:ctx:"),
            redis_ssl=_get_env_bool("CONTEXT_STORE_REDIS_SSL", False),
            redis_ssl_cert_reqs=_get_env("CONTEXT_STORE_REDIS_SSL_CERT_REQS"),
            # Common
            default_ttl_seconds=_get_env_int("CONTEXT_STORE_TTL", 3600),
            offload_threshold_bytes=_get_env_int("CONTEXT_STORE_OFFLOAD_THRESHOLD", 100_000),
            # mem0
            mem0_api_key=_get_env("CONTEXT_STORE_MEM0_API_KEY"),
            mem0_host=_get_env("CONTEXT_STORE_MEM0_HOST"),
            mem0_user_id=_get_env("CONTEXT_STORE_MEM0_USER_ID"),
            mem0_org_id=_get_env("CONTEXT_STORE_MEM0_ORG_ID"),
        )

    @property
    def is_redis_configured(self) -> bool:
        """Check if Redis is properly configured."""
        return self.backend == "redis" and bool(self.redis_host)

    @property
    def is_mem0_configured(self) -> bool:
        """Check if mem0 is properly configured."""
        return self.backend == "mem0" and (bool(self.mem0_api_key) or bool(self.mem0_host))

    def get_redis_url(self) -> str:
        """Get Redis connection URL."""
        scheme = "rediss" if self.redis_ssl else "redis"
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"{scheme}://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


# ═══════════════════════════════════════════════════════════════════════════════
#                           MAIN CONFIG CLASS
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Config:
    """
    Main AgentOrchestrator configuration.

    Holds all configuration sections and provides factory methods
    for creating configured service instances.
    """

    llm: LLMConfig = field(default_factory=LLMConfig)
    foundation: FoundationConfig = field(default_factory=FoundationConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    chain: ChainConfig = field(default_factory=ChainConfig)
    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    context_store: ContextStoreConfig = field(default_factory=ContextStoreConfig)

    # General settings
    log_level: str = "INFO"
    verbose: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        """Load all configuration from environment variables."""
        return cls(
            llm=LLMConfig.from_env(),
            foundation=FoundationConfig.from_env(),
            agents=AgentsConfig.from_env(),
            chain=ChainConfig.from_env(),
            summarizer=SummarizerConfig.from_env(),
            cache=CacheConfig.from_env(),
            context_store=ContextStoreConfig.from_env(),
            log_level=_get_env("LOG_LEVEL", "INFO"),
            verbose=_get_env_bool("VERBOSE", False),
        )

    # ═══════════════════════════════════════════════════════════════════════════
    #                           FACTORY METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def get_llm_client(self) -> Any | None:
        """
        Create and return an LLM Gateway client from config.

        Returns None if LLM is not configured.

        Usage:
            config = get_config()
            llm_client = config.get_llm_client()
            if llm_client:
                response = await llm_client.generate_async("Hello")
        """
        if not self.llm.is_configured:
            logger.warning("LLM not configured - missing server URL or credentials")
            return None

        from agentorchestrator.services.llm_gateway import LLMGatewayClient

        return LLMGatewayClient(
            server_url=self.llm.server_url,
            model_name=self.llm.model_name,
            temperature=self.llm.temperature,
            max_tokens=self.llm.max_tokens,
            timeout=self.llm.timeout,
            oauth_endpoint=self.llm.oauth_endpoint,
            client_id=self.llm.client_id,
            client_secret=self.llm.client_secret,
            api_key=self.llm.api_key,
        )

    def get_langchain_llm(self) -> Any | None:
        """
        Get a LangChain-compatible LLM from config.

        Returns None if LLM is not configured.

        Usage:
            config = get_config()
            llm = config.get_langchain_llm()
            if llm:
                result = await llm.ainvoke("Hello")
        """
        client = self.get_llm_client()
        if client:
            return client.get_langchain_llm()
        return None

    def get_summarizer(self) -> Any:
        """
        Create a LangChain summarizer from config.

        Usage:
            config = get_config()
            summarizer = config.get_summarizer()
            result = await summarizer.summarize(text, content_type="sec_filing")
        """
        from agentorchestrator.middleware.summarizer import LangChainSummarizer, SummarizationStrategy

        # Map strategy string to enum
        strategy_map = {
            "stuff": SummarizationStrategy.STUFF,
            "map_reduce": SummarizationStrategy.MAP_REDUCE,
            "refine": SummarizationStrategy.REFINE,
        }
        strategy = strategy_map.get(self.summarizer.strategy, SummarizationStrategy.MAP_REDUCE)

        llm = self.get_langchain_llm()

        return LangChainSummarizer(
            llm=llm,
            strategy=strategy,
            chunk_size=self.summarizer.chunk_size,
            chunk_overlap=self.summarizer.chunk_overlap,
        )

    def get_summarizer_middleware(self) -> Any:
        """
        Create a SummarizerMiddleware from config.

        Usage:
            config = get_config()
            middleware = config.get_summarizer_middleware()
            forge.use(middleware)
        """
        from agentorchestrator.middleware.summarizer import create_domain_aware_middleware

        llm = self.get_langchain_llm()
        return create_domain_aware_middleware(
            llm=llm,
            max_tokens=self.summarizer.max_tokens,
        )


    def get_cache_middleware(self) -> Any:
        """
        Create a CacheMiddleware from config.

        Usage:
            config = get_config()
            middleware = config.get_cache_middleware()
            forge.use(middleware)
        """
        from agentorchestrator.middleware.cache import CacheMiddleware

        return CacheMiddleware(ttl_seconds=self.cache.ttl_seconds)

    def get_context_store(self) -> Any:
        """
        Create a ContextStore from config.

        Automatically selects backend based on CONTEXT_STORE_BACKEND env var:
        - "memory": InMemoryContextStore (development, no dependencies)
        - "redis": RedisContextStore (production, requires redis)
        - "mem0": Mem0ContextStore (semantic memory, requires mem0)

        Usage:
            config = get_config()
            store = config.get_context_store()

            # Store large data
            ref = await store.store("sec_filing", large_data, summary="10-K for AAPL")

            # Retrieve later
            data = await store.retrieve(ref)

        Deployment Examples:

            # Local development (no Redis needed)
            CONTEXT_STORE_BACKEND=memory

            # Your current Docker setup (Redis in same container)
            CONTEXT_STORE_BACKEND=redis
            CONTEXT_STORE_REDIS_HOST=localhost
            CONTEXT_STORE_REDIS_PORT=6379

            # Kubernetes (Redis in separate pod)
            CONTEXT_STORE_BACKEND=redis
            CONTEXT_STORE_REDIS_HOST=redis-service.default.svc.cluster.local
            CONTEXT_STORE_REDIS_PORT=6379

            # AWS ElastiCache
            CONTEXT_STORE_BACKEND=redis
            CONTEXT_STORE_REDIS_HOST=my-cluster.abc123.use1.cache.amazonaws.com
            CONTEXT_STORE_REDIS_PORT=6379
            CONTEXT_STORE_REDIS_SSL=true

            # mem0 cloud (semantic memory)
            CONTEXT_STORE_BACKEND=mem0
            CONTEXT_STORE_MEM0_API_KEY=m0-xxx

            # mem0 self-hosted
            CONTEXT_STORE_BACKEND=mem0
            CONTEXT_STORE_MEM0_HOST=http://mem0.internal:8080
        """
        from agentorchestrator.core.context_store import create_context_store

        cfg = self.context_store

        if cfg.backend == "memory":
            logger.info("Using InMemoryContextStore (development mode)")
            return create_context_store(backend="memory")

        elif cfg.backend == "redis":
            logger.info(f"Using RedisContextStore at {cfg.redis_host}:{cfg.redis_port}")
            return create_context_store(
                backend="redis",
                host=cfg.redis_host,
                port=cfg.redis_port,
                db=cfg.redis_db,
                password=cfg.redis_password,
                key_prefix=cfg.redis_key_prefix,
                max_connections=cfg.redis_max_connections,
                maxmemory=cfg.redis_maxmemory,
                maxmemory_policy=cfg.redis_maxmemory_policy,
                ssl=cfg.redis_ssl,
                ssl_cert_reqs=cfg.redis_ssl_cert_reqs,
            )

        elif cfg.backend == "mem0":
            logger.info("Using Mem0ContextStore (semantic memory)")
            return create_context_store(
                backend="mem0",
                api_key=cfg.mem0_api_key,
                host=cfg.mem0_host,
                user_id=cfg.mem0_user_id,
                org_id=cfg.mem0_org_id,
            )

        else:
            logger.warning(f"Unknown context store backend: {cfg.backend}, falling back to memory")
            return create_context_store(backend="memory")

    def setup_logging(self) -> None:
        """
        Configure logging based on config settings.

        Usage:
            config = get_config()
            config.setup_logging()
        """
        level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        logger.info(f"Logging configured at level: {self.log_level}")

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary (for debugging, excludes secrets)."""
        return {
            "llm": {
                "server_url": self.llm.server_url,
                "model_name": self.llm.model_name,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "is_configured": self.llm.is_configured,
                "auth_method": "oauth" if self.llm.oauth_endpoint else ("api_key" if self.llm.api_key else "none"),
            },
            "chain": {
                "max_parallel_steps": self.chain.max_parallel_steps,
                "default_timeout_ms": self.chain.default_timeout_ms,
                "default_retries": self.chain.default_retries,
                "error_handling": self.chain.error_handling,
            },
            "agents": {
                "registered": self.agents.list_agents(),
            },
            "summarizer": {
                "max_tokens": self.summarizer.max_tokens,
                "chunk_size": self.summarizer.chunk_size,
                "strategy": self.summarizer.strategy,
            },
            "cache": {
                "ttl_seconds": self.cache.ttl_seconds,
            },
            "context_store": {
                "backend": self.context_store.backend,
                "redis_host": self.context_store.redis_host if self.context_store.backend == "redis" else None,
                "redis_port": self.context_store.redis_port if self.context_store.backend == "redis" else None,
                "redis_ssl": self.context_store.redis_ssl if self.context_store.backend == "redis" else None,
                "mem0_configured": self.context_store.is_mem0_configured if self.context_store.backend == "mem0" else None,
                "default_ttl_seconds": self.context_store.default_ttl_seconds,
                "offload_threshold_bytes": self.context_store.offload_threshold_bytes,
            },
            "log_level": self.log_level,
            "verbose": self.verbose,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#                           SINGLETON & FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

_config: Config | None = None


def get_config() -> Config:
    """
    Get the global configuration instance (singleton).

    Loads from environment variables on first call.

    Usage:
        from agentorchestrator.config import get_config

        config = get_config()
        llm_client = config.get_llm_client()
    """
    global _config
    if _config is None:
        _config = Config.from_env()
        logger.info("AgentOrchestrator configuration loaded from environment")
    return _config


def reload_config() -> Config:
    """
    Reload configuration from environment variables.

    Useful if environment variables have changed.
    """
    global _config
    _config = Config.from_env()
    logger.info("AgentOrchestrator configuration reloaded")
    return _config


def set_config(config: Config) -> None:
    """
    Set a custom configuration (for testing or programmatic config).

    Usage:
        from agentorchestrator.config import Config, set_config

        custom_config = Config(
            llm=LLMConfig(server_url="...", api_key="..."),
        )
        set_config(custom_config)
    """
    global _config
    _config = config
    logger.info("Custom AgentOrchestrator configuration set")


# ═══════════════════════════════════════════════════════════════════════════════
#                           CONVENIENCE EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Main config
    "Config",
    "get_config",
    "reload_config",
    "set_config",
    # Sub-configs
    "LLMConfig",
    "FoundationConfig",
    "AgentConfig",
    "AgentsConfig",
    "ChainConfig",
    "SummarizerConfig",
    "CacheConfig",
    "ContextStoreConfig",
]
