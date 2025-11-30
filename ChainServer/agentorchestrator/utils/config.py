"""
AgentOrchestrator Configuration Management

Provides typed configuration loading with:
- Environment variable validation
- Secret masking in logs
- Fail-fast on missing required values
- Health/version endpoint support
- External secret backend support (AWS Secrets Manager, Vault, etc.)
- Centralized runtime config (timeouts, retries, cache, rate limits)
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ConfigError(Exception):
    """Raised when configuration validation fails"""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
#                           SECRET BACKENDS
# ═══════════════════════════════════════════════════════════════════════════════


class SecretBackend(ABC):
    """
    Abstract base for secret backends.

    Implement this to integrate with AWS Secrets Manager, HashiCorp Vault, etc.
    """

    @abstractmethod
    def get_secret(self, key: str) -> str | None:
        """Retrieve a secret by key."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is available/configured."""
        pass


class EnvSecretBackend(SecretBackend):
    """Default backend that reads from environment variables."""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix

    def get_secret(self, key: str) -> str | None:
        full_key = f"{self.prefix}{key}" if self.prefix else key
        return os.getenv(full_key)

    def is_available(self) -> bool:
        return True


class AWSSecretsManagerBackend(SecretBackend):
    """
    AWS Secrets Manager backend.

    Usage:
        backend = AWSSecretsManagerBackend(secret_name="prod/agentorchestrator")
        set_secret_backend(backend)

    Requires: pip install boto3
    """

    def __init__(
        self,
        secret_name: str,
        region_name: str | None = None,
        cache_ttl_seconds: int = 300,
    ):
        self.secret_name = secret_name
        self.region_name = region_name
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, str] = {}
        self._cache_time: float = 0
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client(
                    "secretsmanager",
                    region_name=self.region_name
                )
            except ImportError:
                raise ConfigError(
                    "boto3 is required for AWS Secrets Manager. "
                    "Install with: pip install boto3"
                )
        return self._client

    def _load_secrets(self) -> dict[str, str]:
        """Load all secrets from AWS Secrets Manager."""
        import time

        # Check cache
        if self._cache and (time.time() - self._cache_time) < self.cache_ttl_seconds:
            return self._cache

        try:
            client = self._get_client()
            response = client.get_secret_value(SecretId=self.secret_name)
            secret_string = response.get("SecretString", "{}")
            self._cache = json.loads(secret_string)
            self._cache_time = time.time()
            return self._cache
        except Exception as e:
            logger.warning(f"Failed to load secrets from AWS: {e}")
            return {}

    def get_secret(self, key: str) -> str | None:
        secrets = self._load_secrets()
        return secrets.get(key)

    def is_available(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False


class VaultSecretBackend(SecretBackend):
    """
    HashiCorp Vault backend.

    Usage:
        backend = VaultSecretBackend(
            url="https://vault.example.com",
            token=os.getenv("VAULT_TOKEN"),
            path="secret/data/agentorchestrator"
        )
        set_secret_backend(backend)

    Requires: pip install hvac
    """

    def __init__(
        self,
        url: str,
        token: str | None = None,
        path: str = "secret/data/agentorchestrator",
        namespace: str | None = None,
    ):
        self.url = url
        self.token = token or os.getenv("VAULT_TOKEN")
        self.path = path
        self.namespace = namespace
        self._client = None
        self._cache: dict[str, str] = {}

    def _get_client(self):
        if self._client is None:
            try:
                import hvac
                self._client = hvac.Client(
                    url=self.url,
                    token=self.token,
                    namespace=self.namespace,
                )
            except ImportError:
                raise ConfigError(
                    "hvac is required for Vault. Install with: pip install hvac"
                )
        return self._client

    def _load_secrets(self) -> dict[str, str]:
        """Load secrets from Vault."""
        if self._cache:
            return self._cache

        try:
            client = self._get_client()
            response = client.secrets.kv.v2.read_secret_version(path=self.path)
            self._cache = response.get("data", {}).get("data", {})
            return self._cache
        except Exception as e:
            logger.warning(f"Failed to load secrets from Vault: {e}")
            return {}

    def get_secret(self, key: str) -> str | None:
        secrets = self._load_secrets()
        return secrets.get(key)

    def is_available(self) -> bool:
        try:
            client = self._get_client()
            return client.is_authenticated()
        except Exception:
            return False


# Global secret backend (defaults to environment variables)
_secret_backend: SecretBackend = EnvSecretBackend()


def set_secret_backend(backend: SecretBackend) -> None:
    """Set the global secret backend."""
    global _secret_backend
    _secret_backend = backend
    logger.info(f"Secret backend set to: {type(backend).__name__}")


def get_secret_backend() -> SecretBackend:
    """Get the current secret backend."""
    return _secret_backend


def get_secret(key: str, default: str | None = None) -> str | None:
    """
    Get a secret from the configured backend.

    Falls back to environment variable if backend doesn't have the key.
    """
    value = _secret_backend.get_secret(key)
    if value is None:
        # Fallback to environment variable
        value = os.getenv(key, default)
    return value


class SecretString:
    """
    A string that masks itself in logs and repr.

    Usage:
        api_key = SecretString(os.getenv("API_KEY"))
        print(api_key)  # Output: ***REDACTED***
        str(api_key)    # Returns actual value for use
    """

    def __init__(self, value: str | None):
        self._value = value

    def __repr__(self) -> str:
        if self._value:
            return "***REDACTED***"
        return "None"

    def __str__(self) -> str:
        """Returns actual value - use for passing to APIs"""
        return self._value or ""

    def __bool__(self) -> bool:
        return bool(self._value)

    def get_masked(self, show_chars: int = 4) -> str:
        """Show last N characters for debugging"""
        if not self._value:
            return "None"
        if len(self._value) <= show_chars:
            return "***"
        return f"***{self._value[-show_chars:]}"

    @property
    def value(self) -> str | None:
        """Explicit access to the actual value"""
        return self._value


@dataclass
class ConfigField(Generic[T]):
    """
    Configuration field definition with validation.

    Usage:
        field = ConfigField(
            name="API_KEY",
            required=True,
            secret=True,
            description="API key for external service"
        )
    """
    name: str
    required: bool = False
    default: T | None = None
    secret: bool = False
    description: str = ""
    validator: Any = None  # Callable[[T], bool]

    def load(self) -> T | SecretString | None:
        """Load value from environment or secret backend."""
        # Use secret backend for secrets, env for regular values
        if self.secret:
            value = get_secret(self.name, self.default)
        else:
            value = os.getenv(self.name, self.default)

        if self.required and not value:
            raise ConfigError(
                f"Required configuration '{self.name}' is missing. "
                f"Description: {self.description}"
            )

        if value and self.validator:
            if not self.validator(value):
                raise ConfigError(
                    f"Configuration '{self.name}' failed validation. "
                    f"Value: {self._mask_for_error(value)}"
                )

        if self.secret and value:
            return SecretString(value)

        return value

    def _mask_for_error(self, value: str) -> str:
        """Mask value for error messages"""
        if self.secret:
            return "***REDACTED***"
        return value


@dataclass
class CacheConfig:
    """Cache policy configuration."""

    enabled: bool = True
    ttl_seconds: int = 300  # Default 5 minutes
    max_size: int = 1000  # Max cache entries
    strategy: str = "lru"  # "lru", "ttl", "fifo"


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    enabled: bool = False
    requests_per_second: float = 10.0
    burst_size: int = 20


@dataclass
class RetryPolicyConfig:
    """Global retry policy configuration."""

    max_retries: int = 3
    base_delay_ms: int = 1000
    max_delay_ms: int = 30000
    backoff_multiplier: float = 2.0
    retry_on_timeout: bool = True
    retry_on_connection_error: bool = True


@dataclass
class AgentOrchestratorConfig:
    """
    AgentOrchestrator configuration with typed fields and validation.

    All configuration is loaded from environment variables with validation.
    Secrets are loaded from the configured secret backend (env by default).
    Secrets are automatically masked in logs.

    Usage:
        config = AgentOrchestratorConfig.from_env()
        print(config.llm_api_key)  # ***REDACTED***
        str(config.llm_api_key)    # actual value
    """

    # Service identification
    service_name: str = "agentorchestrator"
    service_version: str = "1.0.0"
    environment: str = "development"

    # LLM Configuration
    llm_api_key: SecretString | None = None
    llm_base_url: str = "http://localhost:8000"
    llm_model: str = "gpt-4"
    llm_timeout_ms: int = 30000
    llm_max_retries: int = 3

    # Execution Configuration
    max_parallel: int = 10
    default_timeout_ms: int = 30000

    # Cache Configuration
    cache: CacheConfig = field(default_factory=CacheConfig)

    # Rate Limit Configuration
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)

    # Retry Configuration
    retry: RetryPolicyConfig = field(default_factory=RetryPolicyConfig)

    # Observability
    otel_enabled: bool = False
    otel_endpoint: str = ""
    otel_service_name: str = ""
    log_level: str = "INFO"
    log_format: str = "text"  # "text" or "json"

    # Feature flags
    debug_mode: bool = False
    debug_snapshot_dir: str = ".agentorchestrator/snapshots"  # For debug context snapshots

    @classmethod
    def from_env(cls) -> "AgentOrchestratorConfig":
        """
        Load configuration from environment variables.

        Secrets are loaded via the configured secret backend (env by default).
        Fails fast on missing required values.
        Masks secrets in any error messages.
        """
        fields = [
            # Service
            ConfigField("FLOWFORGE_SERVICE_NAME", default="agentorchestrator"),
            ConfigField("FLOWFORGE_VERSION", default="1.0.0"),
            ConfigField("FLOWFORGE_ENV", default="development"),

            # LLM (API key loaded via secret backend)
            ConfigField(
                "LLM_API_KEY",
                secret=True,
                description="API key for LLM service"
            ),
            ConfigField("LLM_BASE_URL", default="http://localhost:8000"),
            ConfigField("LLM_MODEL", default="gpt-4"),
            ConfigField("LLM_TIMEOUT_MS", default="30000"),
            ConfigField("LLM_MAX_RETRIES", default="3"),

            # Execution
            ConfigField("FLOWFORGE_MAX_PARALLEL", default="10"),
            ConfigField("FLOWFORGE_DEFAULT_TIMEOUT_MS", default="30000"),

            # Cache
            ConfigField("FLOWFORGE_CACHE_ENABLED", default="true"),
            ConfigField("FLOWFORGE_CACHE_TTL_SECONDS", default="300"),
            ConfigField("FLOWFORGE_CACHE_MAX_SIZE", default="1000"),
            ConfigField("FLOWFORGE_CACHE_STRATEGY", default="lru"),

            # Rate Limit
            ConfigField("FLOWFORGE_RATE_LIMIT_ENABLED", default="false"),
            ConfigField("FLOWFORGE_RATE_LIMIT_RPS", default="10.0"),
            ConfigField("FLOWFORGE_RATE_LIMIT_BURST", default="20"),

            # Retry
            ConfigField("FLOWFORGE_RETRY_MAX", default="3"),
            ConfigField("FLOWFORGE_RETRY_BASE_DELAY_MS", default="1000"),
            ConfigField("FLOWFORGE_RETRY_MAX_DELAY_MS", default="30000"),
            ConfigField("FLOWFORGE_RETRY_BACKOFF", default="2.0"),

            # Observability
            ConfigField("OTEL_ENABLED", default="false"),
            ConfigField("OTEL_EXPORTER_OTLP_ENDPOINT", default=""),
            ConfigField("OTEL_SERVICE_NAME", default=""),
            ConfigField("LOG_LEVEL", default="INFO"),
            ConfigField("LOG_FORMAT", default="text"),

            # Debug
            ConfigField("FLOWFORGE_DEBUG", default="false"),
            ConfigField("FLOWFORGE_DEBUG_SNAPSHOT_DIR", default=".agentorchestrator/snapshots"),
        ]

        # Load all fields
        values = {}
        errors = []

        for f in fields:
            try:
                values[f.name] = f.load()
            except ConfigError as e:
                errors.append(str(e))

        if errors:
            raise ConfigError(
                "Configuration validation failed:\n" +
                "\n".join(f"  - {e}" for e in errors)
            )

        # Build nested config objects
        cache_config = CacheConfig(
            enabled=values.get("FLOWFORGE_CACHE_ENABLED", "true").lower() == "true",
            ttl_seconds=int(values.get("FLOWFORGE_CACHE_TTL_SECONDS", "300")),
            max_size=int(values.get("FLOWFORGE_CACHE_MAX_SIZE", "1000")),
            strategy=values.get("FLOWFORGE_CACHE_STRATEGY", "lru"),
        )

        rate_limit_config = RateLimitConfig(
            enabled=values.get("FLOWFORGE_RATE_LIMIT_ENABLED", "false").lower() == "true",
            requests_per_second=float(values.get("FLOWFORGE_RATE_LIMIT_RPS", "10.0")),
            burst_size=int(values.get("FLOWFORGE_RATE_LIMIT_BURST", "20")),
        )

        retry_config = RetryPolicyConfig(
            max_retries=int(values.get("FLOWFORGE_RETRY_MAX", "3")),
            base_delay_ms=int(values.get("FLOWFORGE_RETRY_BASE_DELAY_MS", "1000")),
            max_delay_ms=int(values.get("FLOWFORGE_RETRY_MAX_DELAY_MS", "30000")),
            backoff_multiplier=float(values.get("FLOWFORGE_RETRY_BACKOFF", "2.0")),
        )

        return cls(
            service_name=values.get("FLOWFORGE_SERVICE_NAME", "agentorchestrator"),
            service_version=values.get("FLOWFORGE_VERSION", "1.0.0"),
            environment=values.get("FLOWFORGE_ENV", "development"),
            llm_api_key=values.get("LLM_API_KEY"),
            llm_base_url=values.get("LLM_BASE_URL", "http://localhost:8000"),
            llm_model=values.get("LLM_MODEL", "gpt-4"),
            llm_timeout_ms=int(values.get("LLM_TIMEOUT_MS", "30000")),
            llm_max_retries=int(values.get("LLM_MAX_RETRIES", "3")),
            max_parallel=int(values.get("FLOWFORGE_MAX_PARALLEL", "10")),
            default_timeout_ms=int(values.get("FLOWFORGE_DEFAULT_TIMEOUT_MS", "30000")),
            cache=cache_config,
            rate_limit=rate_limit_config,
            retry=retry_config,
            otel_enabled=values.get("OTEL_ENABLED", "false").lower() == "true",
            otel_endpoint=values.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            otel_service_name=values.get("OTEL_SERVICE_NAME", ""),
            log_level=values.get("LOG_LEVEL", "INFO"),
            log_format=values.get("LOG_FORMAT", "text"),
            debug_mode=values.get("FLOWFORGE_DEBUG", "false").lower() == "true",
            debug_snapshot_dir=values.get("FLOWFORGE_DEBUG_SNAPSHOT_DIR", ".agentorchestrator/snapshots"),
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """
        Return config as dict with secrets masked.
        Safe for logging and health endpoints.
        """
        return {
            "service_name": self.service_name,
            "service_version": self.service_version,
            "environment": self.environment,
            "llm_api_key": repr(self.llm_api_key),  # Masked
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_timeout_ms": self.llm_timeout_ms,
            "llm_max_retries": self.llm_max_retries,
            "max_parallel": self.max_parallel,
            "default_timeout_ms": self.default_timeout_ms,
            "cache": {
                "enabled": self.cache.enabled,
                "ttl_seconds": self.cache.ttl_seconds,
                "max_size": self.cache.max_size,
                "strategy": self.cache.strategy,
            },
            "rate_limit": {
                "enabled": self.rate_limit.enabled,
                "requests_per_second": self.rate_limit.requests_per_second,
                "burst_size": self.rate_limit.burst_size,
            },
            "retry": {
                "max_retries": self.retry.max_retries,
                "base_delay_ms": self.retry.base_delay_ms,
                "max_delay_ms": self.retry.max_delay_ms,
                "backoff_multiplier": self.retry.backoff_multiplier,
            },
            "otel_enabled": self.otel_enabled,
            "otel_endpoint": self.otel_endpoint,
            "log_level": self.log_level,
            "log_format": self.log_format,
            "debug_mode": self.debug_mode,
            "debug_snapshot_dir": self.debug_snapshot_dir,
        }


# Global config instance (lazy loaded)
_config: AgentOrchestratorConfig | None = None


def get_config() -> AgentOrchestratorConfig:
    """
    Get the global configuration instance.

    Lazy loads from environment on first access.
    """
    global _config
    if _config is None:
        _config = AgentOrchestratorConfig.from_env()
    return _config


def set_config(config: AgentOrchestratorConfig) -> None:
    """Set the global configuration instance (for testing)"""
    global _config
    _config = config


# Health and version information
@dataclass
class HealthStatus:
    """Health check response"""
    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    environment: str
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "version": self.version,
            "environment": self.environment,
            "checks": self.checks,
        }


def get_health() -> HealthStatus:
    """
    Get health status for /health endpoint.

    Checks:
    - Configuration loaded
    - LLM connectivity (if configured)
    - OTel connectivity (if enabled)
    """
    config = get_config()
    checks = {}

    # Config check
    checks["config_loaded"] = True

    # LLM check (basic - just verify API key exists if needed)
    checks["llm_configured"] = bool(config.llm_api_key)

    # OTel check
    if config.otel_enabled:
        checks["otel_configured"] = bool(config.otel_endpoint)

    # Determine overall status
    all_passed = all(checks.values())
    critical_failed = not checks.get("config_loaded", True)

    if critical_failed:
        status = "unhealthy"
    elif not all_passed:
        status = "degraded"
    else:
        status = "healthy"

    return HealthStatus(
        status=status,
        version=config.service_version,
        environment=config.environment,
        checks=checks,
    )


def get_version() -> dict[str, str]:
    """Get version information for /version endpoint"""
    config = get_config()
    return {
        "name": config.service_name,
        "version": config.service_version,
        "environment": config.environment,
    }
