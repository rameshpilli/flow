"""AgentOrchestrator Middleware Module"""

from agentorchestrator.middleware.analytics import (
    FileUsageBackend,
    InMemoryUsageBackend,
    UsageAnalyticsMiddleware,
    UsageBackend,
    UsageRecord,
)
from agentorchestrator.middleware.base import Middleware
from agentorchestrator.middleware.cache import CacheMiddleware
from agentorchestrator.middleware.logger import LoggerMiddleware
from agentorchestrator.middleware.metrics import (
    InMemoryMetricsBackend,
    MetricsBackend,
    MetricsMiddleware,
    OTelMetricsBackend,
    create_metrics_middleware,
)
from agentorchestrator.middleware.offload import (
    KEY_FIELD_EXTRACTORS,
    SUMMARY_GENERATORS,
    OffloadMiddleware,
    cap_items_with_metadata,
    cap_per_source,
    get_key_field_extractor,
    get_summary_generator,
)
from agentorchestrator.middleware.rate_limiter import (
    CircuitBreakerConfig,
    CircuitBreakerMiddleware,
    CircuitOpenError,
    CircuitState,
    RateLimitAndCircuitBreakerMiddleware,
    RateLimitConfig,
    RateLimiterMiddleware,
    RateLimitExceededError,
)
from agentorchestrator.middleware.summarizer import (
    DOMAIN_PROMPTS,
    LangChainSummarizer,
    LLMSummarizer,  # Legacy alias
    SummarizationStrategy,
    SummarizerMiddleware,
    create_anthropic_summarizer,
    create_domain_aware_middleware,
    create_gateway_summarizer,
    create_openai_summarizer,
    get_domain_prompts,
)
from agentorchestrator.middleware.token_manager import TokenManagerMiddleware

__all__ = [
    # Base
    "Middleware",
    # Usage Analytics
    "UsageAnalyticsMiddleware",
    "UsageBackend",
    "UsageRecord",
    "InMemoryUsageBackend",
    "FileUsageBackend",
    # Metrics/Instrumentation
    "MetricsMiddleware",
    "MetricsBackend",
    "InMemoryMetricsBackend",
    "OTelMetricsBackend",
    "create_metrics_middleware",
    # Rate Limiting & Circuit Breaker
    "RateLimiterMiddleware",
    "RateLimitConfig",
    "RateLimitExceededError",
    "CircuitBreakerMiddleware",
    "CircuitBreakerConfig",
    "CircuitOpenError",
    "CircuitState",
    "RateLimitAndCircuitBreakerMiddleware",
    # Summarization (LangChain-powered)
    "SummarizerMiddleware",
    "LangChainSummarizer",
    "SummarizationStrategy",
    "create_openai_summarizer",
    "create_anthropic_summarizer",
    "create_gateway_summarizer",
    "create_domain_aware_middleware",
    "DOMAIN_PROMPTS",
    "get_domain_prompts",
    "LLMSummarizer",  # Legacy alias
    # Offload Middleware (Auto-offload to Redis)
    "OffloadMiddleware",
    "cap_items_with_metadata",
    "cap_per_source",
    "get_key_field_extractor",
    "get_summary_generator",
    "KEY_FIELD_EXTRACTORS",
    "SUMMARY_GENERATORS",
    # Other middleware
    "CacheMiddleware",
    "LoggerMiddleware",
    "TokenManagerMiddleware",
]
