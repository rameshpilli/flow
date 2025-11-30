"""AgentOrchestrator Utilities Module"""

# Circuit breaker
from agentorchestrator.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
    get_circuit_breaker,
    reset_all_circuit_breakers,
)

# Configuration
from agentorchestrator.utils.config import (
    AWSSecretsManagerBackend,
    # Config sub-types
    CacheConfig,
    ConfigError,
    EnvSecretBackend,
    AgentOrchestratorConfig,
    HealthStatus,
    RateLimitConfig,
    RetryPolicyConfig,
    # Secret backends
    SecretBackend,
    SecretString,
    VaultSecretBackend,
    get_config,
    get_health,
    get_secret,
    get_secret_backend,
    get_version,
    set_config,
    set_secret_backend,
)

# Health aggregator
from agentorchestrator.utils.health import (
    AggregatedHealth,
    ComponentHealth,
    HealthAggregator,
    check_agents_health,
    check_chains_health,
    # Built-in checks
    check_config_health,
    check_llm_health,
    check_redis_health,
    create_default_aggregator,
    is_live,
    is_ready,
    run_health_checks,
)
from agentorchestrator.utils.health import (
    HealthStatus as AggregatedHealthStatus,
)

# Structured logging
from agentorchestrator.utils.logging import (
    ChainLogger,
    LogContext,
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
)
from agentorchestrator.utils.retry import RetryPolicy, async_retry, retry
from agentorchestrator.utils.timing import async_timed, timed

# Tracing
from agentorchestrator.utils.tracing import (
    ChainTracer,
    configure_tracing,
    get_tracer,
    trace_function,
    trace_span,
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
    "AgentOrchestratorConfig",
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
