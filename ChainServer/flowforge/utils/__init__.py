"""FlowForge Utilities Module"""

from flowforge.utils.retry import async_retry, retry, RetryPolicy
from flowforge.utils.timing import async_timed, timed

# Circuit breaker
from flowforge.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
    get_circuit_breaker,
    reset_all_circuit_breakers,
)

# Structured logging
from flowforge.utils.logging import (
    configure_logging,
    get_logger,
    LogContext,
    bind_context,
    clear_context,
    ChainLogger,
)

# Tracing
from flowforge.utils.tracing import (
    configure_tracing,
    get_tracer,
    trace_span,
    trace_function,
    ChainTracer,
)

# Configuration
from flowforge.utils.config import (
    FlowForgeConfig,
    ConfigError,
    SecretString,
    get_config,
    set_config,
    get_health,
    get_version,
    HealthStatus,
    # Secret backends
    SecretBackend,
    EnvSecretBackend,
    AWSSecretsManagerBackend,
    VaultSecretBackend,
    set_secret_backend,
    get_secret_backend,
    get_secret,
    # Config sub-types
    CacheConfig,
    RateLimitConfig,
    RetryPolicyConfig,
)

# Health aggregator
from flowforge.utils.health import (
    HealthAggregator,
    ComponentHealth,
    AggregatedHealth,
    HealthStatus as AggregatedHealthStatus,
    run_health_checks,
    create_default_aggregator,
    is_ready,
    is_live,
    # Built-in checks
    check_config_health,
    check_redis_health,
    check_llm_health,
    check_agents_health,
    check_chains_health,
)

__all__ = [
    # Timing
    "timed",
    "async_timed",
    # Retry
    "retry",
    "async_retry",
    "RetryPolicy",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "CircuitState",
    "get_circuit_breaker",
    "reset_all_circuit_breakers",
    # Logging
    "configure_logging",
    "get_logger",
    "LogContext",
    "bind_context",
    "clear_context",
    "ChainLogger",
    # Tracing
    "configure_tracing",
    "get_tracer",
    "trace_span",
    "trace_function",
    "ChainTracer",
    # Configuration
    "FlowForgeConfig",
    "ConfigError",
    "SecretString",
    "get_config",
    "set_config",
    "get_health",
    "get_version",
    "HealthStatus",
    # Secret backends
    "SecretBackend",
    "EnvSecretBackend",
    "AWSSecretsManagerBackend",
    "VaultSecretBackend",
    "set_secret_backend",
    "get_secret_backend",
    "get_secret",
    # Config sub-types
    "CacheConfig",
    "RateLimitConfig",
    "RetryPolicyConfig",
    # Health aggregator
    "HealthAggregator",
    "ComponentHealth",
    "AggregatedHealth",
    "AggregatedHealthStatus",
    "run_health_checks",
    "create_default_aggregator",
    "is_ready",
    "is_live",
    "check_config_health",
    "check_redis_health",
    "check_llm_health",
    "check_agents_health",
    "check_chains_health",
]
