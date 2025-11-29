"""
FlowForge Metrics Middleware

Provides instrumentation and metrics collection for step execution.
Supports multiple metrics backends including:
- In-memory (default, for development)
- OpenTelemetry metrics
- Custom backends via MetricsBackend protocol

Usage:
    # Basic usage with in-memory backend
    forge.use(MetricsMiddleware())

    # With OpenTelemetry
    from opentelemetry import metrics
    meter = metrics.get_meter("flowforge")
    forge.use(MetricsMiddleware(backend=OTelMetricsBackend(meter)))

    # Get metrics
    middleware = MetricsMiddleware()
    forge.use(middleware)
    # ... run chains ...
    stats = middleware.get_stats()
"""

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from flowforge.core.context import ChainContext, StepResult
from flowforge.middleware.base import Middleware

logger = logging.getLogger(__name__)


@runtime_checkable
class MetricsBackend(Protocol):
    """Protocol for metrics backends."""

    def record_histogram(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram/distribution value."""
        ...

    def record_counter(
        self,
        name: str,
        value: int = 1,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter."""
        ...

    def record_gauge(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge value."""
        ...


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    tags: dict[str, str]
    timestamp: float = field(default_factory=time.time)


class InMemoryMetricsBackend:
    """
    In-memory metrics backend for development and testing.

    Stores all metrics in memory for later analysis.
    """

    def __init__(self):
        self._histograms: dict[str, list[MetricPoint]] = defaultdict(list)
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._counter_tags: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record_histogram(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram value."""
        point = MetricPoint(name=name, value=value, tags=tags or {})
        self._histograms[name].append(point)

    def record_counter(
        self,
        name: str,
        value: int = 1,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter."""
        self._counters[name] += value
        if tags:
            tag_key = str(sorted(tags.items()))
            self._counter_tags[name][tag_key] += value

    def record_gauge(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge value."""
        self._gauges[name] = value

    def get_histogram_stats(self, name: str) -> dict[str, float]:
        """Get statistics for a histogram."""
        values = [p.value for p in self._histograms.get(name, [])]
        if not values:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}

        sorted_values = sorted(values)
        count = len(values)

        def percentile(p: float) -> float:
            idx = int(count * p / 100)
            return sorted_values[min(idx, count - 1)]

        return {
            "count": count,
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / count,
            "sum": sum(values),
            "p50": percentile(50),
            "p95": percentile(95),
            "p99": percentile(99),
        }

    def get_counter(self, name: str) -> int:
        """Get counter value."""
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> float:
        """Get gauge value."""
        return self._gauges.get(name, 0.0)

    def get_all_stats(self) -> dict[str, Any]:
        """Get all metrics stats."""
        return {
            "histograms": {
                name: self.get_histogram_stats(name)
                for name in self._histograms
            },
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
        }

    def clear(self) -> None:
        """Clear all metrics."""
        self._histograms.clear()
        self._counters.clear()
        self._gauges.clear()
        self._counter_tags.clear()


class OTelMetricsBackend:
    """
    OpenTelemetry metrics backend.

    Requires opentelemetry-api to be installed.

    Usage:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider

        # Setup meter provider (usually done once at app startup)
        metrics.set_meter_provider(MeterProvider())

        # Create backend
        meter = metrics.get_meter("flowforge")
        backend = OTelMetricsBackend(meter)
    """

    def __init__(self, meter: Any):
        """
        Initialize with OpenTelemetry Meter.

        Args:
            meter: OpenTelemetry Meter instance
        """
        self._meter = meter
        self._histograms: dict[str, Any] = {}
        self._counters: dict[str, Any] = {}
        self._gauges: dict[str, Any] = {}

    def _get_histogram(self, name: str) -> Any:
        """Get or create histogram instrument."""
        if name not in self._histograms:
            self._histograms[name] = self._meter.create_histogram(
                name,
                unit="ms" if "duration" in name else "1",
                description=f"FlowForge {name}",
            )
        return self._histograms[name]

    def _get_counter(self, name: str) -> Any:
        """Get or create counter instrument."""
        if name not in self._counters:
            self._counters[name] = self._meter.create_counter(
                name,
                unit="1",
                description=f"FlowForge {name}",
            )
        return self._counters[name]

    def _get_gauge(self, name: str) -> Any:
        """Get or create gauge instrument."""
        if name not in self._gauges:
            self._gauges[name] = self._meter.create_up_down_counter(
                name,
                unit="1",
                description=f"FlowForge {name}",
            )
        return self._gauges[name]

    def record_histogram(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram value."""
        histogram = self._get_histogram(name)
        histogram.record(value, tags or {})

    def record_counter(
        self,
        name: str,
        value: int = 1,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter."""
        counter = self._get_counter(name)
        counter.add(value, tags or {})

    def record_gauge(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge value (using up_down_counter as approximation)."""
        gauge = self._get_gauge(name)
        gauge.add(value, tags or {})


class MetricsMiddleware(Middleware):
    """
    Middleware for collecting step execution metrics.

    Collects:
    - step_duration_ms: Histogram of step execution times
    - step_executions_total: Counter of step executions (success/failure)
    - step_errors_total: Counter of step errors by type
    - chain_steps_in_progress: Gauge of currently executing steps

    Usage:
        # Basic usage
        metrics = MetricsMiddleware()
        forge.use(metrics)

        # Run chains...
        result = await forge.run("my_chain")

        # Get stats
        stats = metrics.get_stats()
        print(f"Step durations: {stats['histograms']['step_duration_ms']}")

        # With custom backend
        from opentelemetry import metrics as otel_metrics
        meter = otel_metrics.get_meter("my-app")
        forge.use(MetricsMiddleware(backend=OTelMetricsBackend(meter)))
    """

    # Metric names
    STEP_DURATION = "flowforge.step.duration_ms"
    STEP_EXECUTIONS = "flowforge.step.executions_total"
    STEP_ERRORS = "flowforge.step.errors_total"
    STEP_RETRIES = "flowforge.step.retries_total"
    STEPS_IN_PROGRESS = "flowforge.step.in_progress"

    def __init__(
        self,
        backend: MetricsBackend | None = None,
        priority: int = 5,  # Run early to capture accurate timing
        applies_to: list[str] | None = None,
        include_chain_name: bool = True,
        include_error_type: bool = True,
    ):
        """
        Initialize MetricsMiddleware.

        Args:
            backend: Metrics backend (default: InMemoryMetricsBackend)
            priority: Middleware priority (lower = earlier)
            applies_to: List of step names to apply to (None = all)
            include_chain_name: Include chain name in metric tags
            include_error_type: Include error type in error metrics
        """
        super().__init__(priority=priority, applies_to=applies_to)
        self._backend = backend or InMemoryMetricsBackend()
        self._include_chain_name = include_chain_name
        self._include_error_type = include_error_type
        self._step_start_times: dict[str, float] = {}

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """Record step start."""
        # Track start time for this step
        key = f"{ctx.request_id}:{step_name}"
        self._step_start_times[key] = time.perf_counter()

        # Increment in-progress gauge
        tags = {"step": step_name}
        if self._include_chain_name:
            tags["chain"] = ctx.metadata.get("chain_name", "unknown")

        self._backend.record_gauge(self.STEPS_IN_PROGRESS, 1, tags)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Record step completion metrics."""
        key = f"{ctx.request_id}:{step_name}"
        start_time = self._step_start_times.pop(key, None)

        # Build tags
        tags = {"step": step_name}
        if self._include_chain_name:
            tags["chain"] = ctx.metadata.get("chain_name", "unknown")

        # Record duration
        if start_time is not None:
            duration_ms = (time.perf_counter() - start_time) * 1000
        else:
            duration_ms = result.duration_ms

        self._backend.record_histogram(self.STEP_DURATION, duration_ms, tags)

        # Record execution count with status
        status = "success" if result.success else ("skipped" if result.skipped else "failed")
        self._backend.record_counter(
            self.STEP_EXECUTIONS,
            1,
            {**tags, "status": status},
        )

        # Record error if failed
        if result.failed:
            error_tags = {**tags}
            if self._include_error_type and result.error_type:
                error_tags["error_type"] = result.error_type
            self._backend.record_counter(self.STEP_ERRORS, 1, error_tags)

        # Record retry count if any
        if result.retry_count > 0:
            self._backend.record_counter(
                self.STEP_RETRIES,
                result.retry_count,
                tags,
            )

        # Decrement in-progress gauge
        self._backend.record_gauge(self.STEPS_IN_PROGRESS, -1, tags)

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """Record error metrics (called if step throws)."""
        key = f"{ctx.request_id}:{step_name}"
        self._step_start_times.pop(key, None)

        tags = {"step": step_name}
        if self._include_chain_name:
            tags["chain"] = ctx.metadata.get("chain_name", "unknown")

        # Record error
        if self._include_error_type:
            tags["error_type"] = type(error).__name__

        self._backend.record_counter(self.STEP_ERRORS, 1, tags)
        self._backend.record_gauge(self.STEPS_IN_PROGRESS, -1, {"step": step_name})

    def get_stats(self) -> dict[str, Any]:
        """
        Get metrics statistics.

        Only available for InMemoryMetricsBackend.

        Returns:
            Dict with histogram stats, counters, and gauges
        """
        if isinstance(self._backend, InMemoryMetricsBackend):
            return self._backend.get_all_stats()
        return {"error": "Stats only available with InMemoryMetricsBackend"}

    def get_step_stats(self, step_name: str) -> dict[str, Any]:
        """
        Get metrics for a specific step.

        Args:
            step_name: Name of the step

        Returns:
            Dict with duration stats and execution counts
        """
        if not isinstance(self._backend, InMemoryMetricsBackend):
            return {"error": "Stats only available with InMemoryMetricsBackend"}

        # Filter histogram points for this step
        duration_points = [
            p for p in self._backend._histograms.get(self.STEP_DURATION, [])
            if p.tags.get("step") == step_name
        ]

        if not duration_points:
            return {"step": step_name, "executions": 0}

        durations = [p.value for p in duration_points]
        sorted_durations = sorted(durations)
        count = len(durations)

        def percentile(p: float) -> float:
            idx = int(count * p / 100)
            return sorted_durations[min(idx, count - 1)]

        return {
            "step": step_name,
            "executions": count,
            "duration_ms": {
                "min": min(durations),
                "max": max(durations),
                "avg": sum(durations) / count,
                "p50": percentile(50),
                "p95": percentile(95),
                "p99": percentile(99),
            },
        }

    def clear(self) -> None:
        """Clear all collected metrics."""
        if isinstance(self._backend, InMemoryMetricsBackend):
            self._backend.clear()
        self._step_start_times.clear()


# Convenience functions for creating configured middleware
def create_metrics_middleware(
    *,
    otel_meter: Any = None,
    priority: int = 5,
    applies_to: list[str] | None = None,
) -> MetricsMiddleware:
    """
    Create a configured MetricsMiddleware.

    Args:
        otel_meter: Optional OpenTelemetry Meter for OTel integration
        priority: Middleware priority
        applies_to: List of step names to apply to

    Returns:
        Configured MetricsMiddleware instance
    """
    if otel_meter is not None:
        backend = OTelMetricsBackend(otel_meter)
    else:
        backend = InMemoryMetricsBackend()

    return MetricsMiddleware(
        backend=backend,
        priority=priority,
        applies_to=applies_to,
    )
