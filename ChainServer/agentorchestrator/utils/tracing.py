"""
AgentOrchestrator OpenTelemetry Tracing

Provides distributed tracing support using OpenTelemetry.
Falls back gracefully when OpenTelemetry is not installed.
"""

import logging
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Try to import OpenTelemetry
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Span, Status, StatusCode, Tracer
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    Span = None
    Status = None
    StatusCode = None
    Tracer = None
    TracerProvider = None
    BatchSpanProcessor = None
    ConsoleSpanExporter = None
    Resource = None


# Global tracer instance
_tracer: Any = None


def configure_tracing(
    service_name: str = "agentorchestrator",
    exporter: Any = None,
    enabled: bool = True,
) -> None:
    """
    Configure OpenTelemetry tracing.

    Args:
        service_name: Name of the service for tracing
        exporter: Custom span exporter (defaults to console)
        enabled: Whether tracing is enabled

    Usage:
        from agentorchestrator.utils.tracing import configure_tracing
        configure_tracing(service_name="my-app")

        # With OTLP exporter (requires opentelemetry-exporter-otlp)
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        configure_tracing(exporter=OTLPSpanExporter(endpoint="localhost:4317"))
    """
    global _tracer

    if not enabled or not OTEL_AVAILABLE:
        logger.info("Tracing disabled or OpenTelemetry not installed")
        _tracer = NoOpTracer()
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    # Use provided exporter or default to console
    if exporter is None:
        exporter = ConsoleSpanExporter()

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer(service_name)
    logger.info(f"Tracing configured for service: {service_name}")


def get_tracer() -> Any:
    """Get the configured tracer instance"""
    global _tracer
    if _tracer is None:
        if OTEL_AVAILABLE:
            _tracer = trace.get_tracer("agentorchestrator")
        else:
            _tracer = NoOpTracer()
    return _tracer


class NoOpSpan:
    """No-op span when tracing is disabled"""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "NoOpSpan":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


class NoOpTracer:
    """No-op tracer when OpenTelemetry is not installed"""

    def start_span(self, name: str, **kwargs) -> NoOpSpan:
        return NoOpSpan()

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs):
        yield NoOpSpan()


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    record_exception: bool = True,
):
    """
    Context manager for creating a traced span.

    Usage:
        with trace_span("fetch_data", attributes={"company": "Apple"}):
            result = await fetch_data()
    """
    tracer = get_tracer()

    with tracer.start_as_current_span(name) as span:
        if attributes and hasattr(span, "set_attribute"):
            for key, value in attributes.items():
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as e:
            if record_exception and hasattr(span, "record_exception"):
                span.record_exception(e)
            if OTEL_AVAILABLE and hasattr(span, "set_status"):
                span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


def trace_function(
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for tracing a function.

    Usage:
        @trace_function(attributes={"component": "data_fetcher"})
        async def fetch_data(query: str) -> dict:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        span_name = name or func.__name__

        if _is_async(func):
            async def async_wrapper(*args, **kwargs) -> T:
                with trace_span(span_name, attributes):
                    return await func(*args, **kwargs)
            async_wrapper.__name__ = func.__name__
            async_wrapper.__doc__ = func.__doc__
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs) -> T:
                with trace_span(span_name, attributes):
                    return func(*args, **kwargs)
            sync_wrapper.__name__ = func.__name__
            sync_wrapper.__doc__ = func.__doc__
            return sync_wrapper

    return decorator


def _is_async(func: Callable) -> bool:
    """Check if function is async"""
    import asyncio
    return asyncio.iscoroutinefunction(func)


# Chain-specific tracing utilities
class ChainTracer:
    """
    Specialized tracer for chain execution.

    Usage:
        tracer = ChainTracer("cmpt_chain", request_id="abc123")
        with tracer.chain_span():
            with tracer.step_span("fetch_data"):
                result = await fetch_data()
    """

    def __init__(self, chain_name: str, request_id: str | None = None):
        self.chain_name = chain_name
        self.request_id = request_id
        self._tracer = get_tracer()

    def _base_attributes(self) -> dict[str, Any]:
        """Base attributes for all spans"""
        attrs = {"chain.name": self.chain_name}
        if self.request_id:
            attrs["request.id"] = self.request_id
        return attrs

    @contextmanager
    def chain_span(self, total_steps: int | None = None):
        """Create a span for the entire chain execution"""
        attrs = self._base_attributes()
        if total_steps is not None:
            attrs["chain.total_steps"] = total_steps

        with trace_span(f"chain.{self.chain_name}", attributes=attrs) as span:
            yield span

    @contextmanager
    def step_span(self, step_name: str, **extra_attrs):
        """Create a span for a single step"""
        attrs = {
            **self._base_attributes(),
            "step.name": step_name,
            **extra_attrs,
        }
        with trace_span(f"step.{step_name}", attributes=attrs) as span:
            yield span

    @contextmanager
    def agent_span(self, agent_name: str, **extra_attrs):
        """Create a span for an agent call"""
        attrs = {
            **self._base_attributes(),
            "agent.name": agent_name,
            **extra_attrs,
        }
        with trace_span(f"agent.{agent_name}", attributes=attrs) as span:
            yield span
