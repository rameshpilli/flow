"""AgentOrchestrator Middleware Module"""

from agentorchestrator.middleware.analytics import (
    FileUsageBackend,
    InMemoryUsageBackend,
    SourceCitation,
    UsageAnalyticsMiddleware,
    UsageBackend,
    UsageRecord,
)
from agentorchestrator.middleware.base import Middleware
from agentorchestrator.middleware.cache import CacheMiddleware
from agentorchestrator.middleware.citation import (
    CitationMiddleware,
    CitationReport,
    add_citation,
    add_source_content,
    cite,
    get_citation_report,
)
from agentorchestrator.middleware.idempotency import (
    IdempotencyBackend,
    IdempotencyConfig,
    IdempotencyHit,
    IdempotencyMiddleware,
    InMemoryIdempotencyBackend,
    create_redis_idempotency_middleware,
)
from agentorchestrator.middleware.logger import LoggerMiddleware
from agentorchestrator.middleware.metrics import (
    InMemoryMetricsBackend,
    MetricsBackend,
    MetricsMiddleware,
    OTelMetricsBackend,
    create_metrics_middleware,
)
from agentorchestrator.middleware.offload import (
    OffloadMiddleware,
    cap_items_with_metadata,
    cap_per_source,
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
    LangChainSummarizer,
    LLMSummarizer,  # Legacy alias
    SummarizationStrategy,
    SummarizerMiddleware,
    create_anthropic_summarizer,
    create_domain_aware_middleware,
    create_gateway_summarizer,
    create_openai_summarizer,
)
from agentorchestrator.middleware.token_manager import TokenManagerMiddleware

__all__ = [
    # Base
    "Middleware",
    # Citation Tracking
    "CitationMiddleware",
    "CitationReport",
    "cite",
    "add_citation",
    "add_source_content",
    "get_citation_report",
    # Usage Analytics
    "UsageAnalyticsMiddleware",
    "UsageBackend",
    "UsageRecord",
    "SourceCitation",
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
    # Idempotency (prevent duplicate execution)
    "IdempotencyMiddleware",
    "IdempotencyConfig",
    "IdempotencyBackend",
    "IdempotencyHit",
    "InMemoryIdempotencyBackend",
    "create_redis_idempotency_middleware",
    # Summarization (LangChain-powered)
    "SummarizerMiddleware",
    "LangChainSummarizer",
    "SummarizationStrategy",
    "create_openai_summarizer",
    "create_anthropic_summarizer",
    "create_gateway_summarizer",
    "create_domain_aware_middleware",
    "LLMSummarizer",  # Legacy alias
    # Offload Middleware (Auto-offload to Redis)
    "OffloadMiddleware",
    "cap_items_with_metadata",
    "cap_per_source",
    # Other middleware
    "CacheMiddleware",
    "LoggerMiddleware",
    "TokenManagerMiddleware",
]
