# Create New Middleware

Create a new AgentOrchestrator middleware for cross-cutting concerns.

## Usage
```
/new-middleware <middleware_name> <description>
```

Example: `/new-middleware audit_logger "Logs all step executions for compliance"`

---

## Middleware Pattern

Middleware intercepts step execution at three points:
1. `before()` - Before step execution
2. `after()` - After step execution (with result)
3. `on_error()` - When a step fails

```
Step Execution Flow:
┌─────────────────────────────────────────────────────────┐
│                      Middleware Stack                    │
├─────────────────────────────────────────────────────────┤
│  ┌─────────┐                              ┌─────────┐   │
│  │ before  │ ─► Step Execution ─────────► │  after  │   │
│  └─────────┘           │                  └─────────┘   │
│                        │                                 │
│                        ▼                                 │
│                  ┌──────────┐                           │
│                  │ on_error │ (if step fails)           │
│                  └──────────┘                           │
└─────────────────────────────────────────────────────────┘
```

---

## Middleware Template

```python
"""
{MiddlewareName} Middleware

{MiddlewareDescription}
"""

import logging
from typing import Any

from agentorchestrator.middleware.base import Middleware, SkipStep
from agentorchestrator.core.context import ChainContext, StepResult

logger = logging.getLogger(__name__)


class {MiddlewareName}Middleware(Middleware):
    """
    {MiddlewareDescription}

    Usage:
        middleware = {MiddlewareName}Middleware(config=...)
        ao.add_middleware(middleware)

    Or with decorator:
        @ao.middleware(priority=50)
        class {MiddlewareName}Middleware(Middleware):
            ...
    """

    _ao_middleware = True
    _ao_priority = 100  # Lower = earlier execution

    def __init__(
        self,
        priority: int = 100,
        applies_to: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ):
        """
        Initialize middleware.

        Args:
            priority: Execution priority (lower = earlier)
            applies_to: List of step names to apply to (None = all)
            config: Additional configuration
        """
        super().__init__(priority=priority, applies_to=applies_to)
        self.config = config or {}

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Called before step execution.

        Args:
            ctx: The chain context
            step_name: Name of the step about to execute

        Raises:
            SkipStep: To skip this step entirely
        """
        logger.debug(f"[{self.__class__.__name__}] Before: {step_name}")

        # Example: Check preconditions
        if self._should_skip(ctx, step_name):
            logger.info(f"Skipping step: {step_name}")
            raise SkipStep(f"Step {step_name} skipped by {self.__class__.__name__}")

        # Example: Set context values
        ctx.set(f"_{step_name}_start_time", self._get_timestamp())

    async def after(
        self,
        ctx: ChainContext,
        step_name: str,
        result: StepResult,
    ) -> None:
        """
        Called after step execution.

        Args:
            ctx: The chain context
            step_name: Name of the step that executed
            result: The step execution result
        """
        logger.debug(f"[{self.__class__.__name__}] After: {step_name}")

        # Example: Log timing
        start_time = ctx.get(f"_{step_name}_start_time")
        if start_time:
            duration = self._get_timestamp() - start_time
            logger.info(f"Step {step_name} completed in {duration:.2f}ms")

        # Example: Process result
        if result.success:
            self._on_success(ctx, step_name, result)
        else:
            self._on_failure(ctx, step_name, result)

    async def on_error(
        self,
        ctx: ChainContext,
        step_name: str,
        error: Exception,
    ) -> None:
        """
        Called when a step fails.

        Args:
            ctx: The chain context
            step_name: Name of the step that failed
            error: The exception that occurred
        """
        logger.error(f"[{self.__class__.__name__}] Error in {step_name}: {error}")

        # Example: Record error for reporting
        errors = ctx.get("_middleware_errors", [])
        errors.append({
            "step": step_name,
            "error": str(error),
            "type": type(error).__name__,
        })
        ctx.set("_middleware_errors", errors)

    def should_apply(self, step_name: str) -> bool:
        """Check if this middleware should apply to a step."""
        if self._ao_applies_to is None:
            return True
        return step_name in self._ao_applies_to

    # ═══════════════════════════════════════════════════════════════════════════
    #                           PRIVATE METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def _should_skip(self, ctx: ChainContext, step_name: str) -> bool:
        """Determine if step should be skipped."""
        # Your skip logic here
        return False

    def _on_success(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Handle successful step execution."""
        pass

    def _on_failure(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Handle failed step execution."""
        pass

    @staticmethod
    def _get_timestamp() -> float:
        """Get current timestamp in milliseconds."""
        import time
        return time.perf_counter() * 1000
```

---

## Available Middleware

### 1. OffloadMiddleware
Automatically offloads large payloads to Redis/storage.

```python
from agentorchestrator.middleware.offload import OffloadMiddleware

middleware = OffloadMiddleware(
    default_threshold_bytes=100_000,  # 100KB
    step_thresholds={
        "response_builder": 50_000,    # Lower for specific step
    },
)
ao.add_middleware(middleware)
```

### 2. CacheMiddleware
Caches step results for repeated calls.

```python
from agentorchestrator.middleware.cache import CacheMiddleware

middleware = CacheMiddleware(
    ttl_seconds=300,
    cache_backend="redis",  # or "memory"
)
ao.add_middleware(middleware)
```

### 3. LoggerMiddleware
Logs step execution with timing.

```python
from agentorchestrator.middleware.logger import LoggerMiddleware

middleware = LoggerMiddleware(
    log_level="INFO",
    include_context=False,  # Don't log full context
)
ao.add_middleware(middleware)
```

### 4. MetricsMiddleware
Collects metrics for monitoring.

```python
from agentorchestrator.middleware.metrics import MetricsMiddleware, create_metrics_middleware

# With OpenTelemetry
middleware = create_metrics_middleware(backend="otel")

# With in-memory backend
middleware = MetricsMiddleware(backend=InMemoryMetricsBackend())

ao.add_middleware(middleware)
```

### 5. RateLimiterMiddleware
Rate limits step execution.

```python
from agentorchestrator.middleware.rate_limiter import (
    RateLimiterMiddleware,
    RateLimitConfig,
)

middleware = RateLimiterMiddleware(
    config=RateLimitConfig(
        requests_per_minute=60,
        burst_size=10,
    ),
)
ao.add_middleware(middleware)
```

### 6. CircuitBreakerMiddleware
Implements circuit breaker pattern.

```python
from agentorchestrator.middleware.rate_limiter import (
    CircuitBreakerMiddleware,
    CircuitBreakerConfig,
)

middleware = CircuitBreakerMiddleware(
    config=CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout=30.0,
    ),
)
ao.add_middleware(middleware)
```

### 7. IdempotencyMiddleware
Prevents duplicate step execution.

```python
from agentorchestrator.middleware.idempotency import (
    IdempotencyMiddleware,
    IdempotencyConfig,
)

middleware = IdempotencyMiddleware(
    config=IdempotencyConfig(
        ttl_seconds=3600,
        key_fields=["request_id", "company_name"],
    ),
)
ao.add_middleware(middleware)
```

### 8. SummarizerMiddleware
Summarizes large context for LLM.

```python
from agentorchestrator.middleware.summarizer import (
    SummarizerMiddleware,
    create_openai_summarizer,
)

summarizer = create_openai_summarizer(model="gpt-4o-mini")
middleware = SummarizerMiddleware(
    summarizer=summarizer,
    threshold_tokens=4000,
)
ao.add_middleware(middleware)
```

### 9. CitationMiddleware
Tracks citations for source attribution.

```python
from agentorchestrator.middleware.citation import CitationMiddleware

middleware = CitationMiddleware(
    track_sources=True,
    require_citations=True,
)
ao.add_middleware(middleware)
```

### 10. UsageAnalyticsMiddleware
Tracks usage for analytics.

```python
from agentorchestrator.middleware.analytics import UsageAnalyticsMiddleware

middleware = UsageAnalyticsMiddleware(
    backend=FileUsageBackend("usage.jsonl"),
)
ao.add_middleware(middleware)
```

---

## Middleware Priority

Middleware executes in priority order (lower = earlier):

```python
@ao.middleware(priority=10)   # Runs first
class EarlyMiddleware: ...

@ao.middleware(priority=50)   # Runs second
class MiddleMiddleware: ...

@ao.middleware(priority=100)  # Runs last (default)
class LateMiddleware: ...
```

For `after()` hooks, the order is reversed (last-in-first-out).

---

## SkipStep Exception

Raise `SkipStep` in `before()` to skip a step:

```python
from agentorchestrator.middleware.base import SkipStep

async def before(self, ctx: ChainContext, step_name: str) -> None:
    # Check cache
    cached = await self.cache.get(self._cache_key(ctx, step_name))
    if cached:
        ctx.set(f"{step_name}_output", cached)
        raise SkipStep("Using cached result")
```

---

## CompositeMiddleware

Combine multiple middleware into one:

```python
from agentorchestrator.middleware.base import CompositeMiddleware

composite = CompositeMiddleware([
    LoggerMiddleware(),
    CacheMiddleware(),
    MetricsMiddleware(),
])
ao.add_middleware(composite)
```

---

## Adding Middleware to Chain

```python
def register_{chain_name}_chain(ao: AgentOrchestrator) -> None:
    """Register chain with middleware."""

    # Add middleware before registering steps
    from agentorchestrator.middleware import (
        OffloadMiddleware,
        LoggerMiddleware,
        MetricsMiddleware,
    )

    ao.add_middleware(OffloadMiddleware(default_threshold_bytes=100_000))
    ao.add_middleware(LoggerMiddleware())
    ao.add_middleware(MetricsMiddleware())

    # Now register steps and chain...
    @ao.step(name="my_step")
    async def my_step(ctx): ...
```

---

## Reference Files

- **Base Middleware**: [agentorchestrator/middleware/base.py](agentorchestrator/middleware/base.py)
- **Offload Middleware**: [agentorchestrator/middleware/offload.py](agentorchestrator/middleware/offload.py)
- **Cache Middleware**: [agentorchestrator/middleware/cache.py](agentorchestrator/middleware/cache.py)
- **Metrics Middleware**: [agentorchestrator/middleware/metrics.py](agentorchestrator/middleware/metrics.py)
- **All Middleware**: [agentorchestrator/middleware/__init__.py](agentorchestrator/middleware/__init__.py)
