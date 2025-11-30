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
        return cls(
            server_url=_get_env("LLM_GATEWAY_URL", ""),
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
    """Data agent configuration."""

    url: str = ""
    api_key: str | None = None


@dataclass
class AgentsConfig:
    """All data agents configuration."""

    sec: AgentConfig = field(default_factory=AgentConfig)
    news: AgentConfig = field(default_factory=AgentConfig)
    earnings: AgentConfig = field(default_factory=AgentConfig)
    transcripts: AgentConfig = field(default_factory=AgentConfig)

    @classmethod
    def from_env(cls) -> "AgentsConfig":
        """Load agents config from environment variables."""
        return cls(
            sec=AgentConfig(
                url=_get_env("SEC_AGENT_URL", ""),
                api_key=_get_env("SEC_AGENT_API_KEY"),
            ),
            news=AgentConfig(
                url=_get_env("NEWS_AGENT_URL", ""),
                api_key=_get_env("NEWS_AGENT_API_KEY"),
            ),
            earnings=AgentConfig(
                url=_get_env("EARNINGS_AGENT_URL", ""),
                api_key=_get_env("EARNINGS_AGENT_API_KEY"),
            ),
            transcripts=AgentConfig(
                url=_get_env("TRANSCRIPTS_AGENT_URL", ""),
                api_key=_get_env("TRANSCRIPTS_AGENT_API_KEY"),
            ),
        )


@dataclass
class ChainConfig:
    """Chain execution configuration."""

    default_news_lookback_days: int = 30
    default_filing_quarters: int = 8
    max_parallel_agents: int = 5
    default_timeout_ms: int = 30000

    @classmethod
    def from_env(cls) -> "ChainConfig":
        """Load chain config from environment variables."""
        return cls(
            default_news_lookback_days=_get_env_int("DEFAULT_NEWS_LOOKBACK_DAYS", 30),
            default_filing_quarters=_get_env_int("DEFAULT_FILING_QUARTERS", 8),
            max_parallel_agents=_get_env_int("MAX_PARALLEL_AGENTS", 5),
            default_timeout_ms=_get_env_int("DEFAULT_TIMEOUT_MS", 30000),
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

    def get_context_builder_service(self) -> Any:
        """
        Create a ContextBuilderService from config.

        Usage:
            config = get_config()
            service = config.get_context_builder_service()
            output = await service.execute(request)
        """
        from agentorchestrator.services.context_builder import ContextBuilderService

        return ContextBuilderService(
            news_lookback_days=self.chain.default_news_lookback_days,
            filing_quarters=self.chain.default_filing_quarters,
        )

    def get_response_builder_service(self) -> Any:
        """
        Create a ResponseBuilderService from config.

        Usage:
            config = get_config()
            service = config.get_response_builder_service()
            output = await service.execute(context, prioritization)
        """
        from agentorchestrator.services.response_builder import ResponseBuilderService

        llm_client = self.get_llm_client()

        return ResponseBuilderService(
            max_parallel_agents=self.chain.max_parallel_agents,
            llm_client=llm_client,
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
                "default_news_lookback_days": self.chain.default_news_lookback_days,
                "default_filing_quarters": self.chain.default_filing_quarters,
                "max_parallel_agents": self.chain.max_parallel_agents,
            },
            "summarizer": {
                "max_tokens": self.summarizer.max_tokens,
                "chunk_size": self.summarizer.chunk_size,
                "strategy": self.summarizer.strategy,
            },
            "cache": {
                "ttl_seconds": self.cache.ttl_seconds,
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
]
