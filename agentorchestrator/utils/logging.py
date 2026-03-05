"""
AgentOrchestrator Structured Logging

Provides structured logging using structlog for better observability.
Falls back to standard logging if structlog is not installed.
"""

import logging
import sys
from typing import Any

# Try to import structlog, fall back to standard logging
try:
    import structlog
    from structlog.contextvars import bind_contextvars, clear_contextvars, unbind_contextvars
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    bind_contextvars = None
    clear_contextvars = None
    unbind_contextvars = None


def configure_logging(
    level: str = "INFO",
    json_output: bool = False,
    include_timestamp: bool = True,
) -> None:
    """
    Configure AgentOrchestrator logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_output: If True, output JSON logs (for production)
        include_timestamp: Include timestamp in logs

    Usage:
        from agentorchestrator.utils.logging import configure_logging
        configure_logging(level="DEBUG", json_output=True)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    if STRUCTLOG_AVAILABLE:
        _configure_structlog(log_level, json_output, include_timestamp)
    else:
        _configure_standard_logging(log_level, include_timestamp)


def _configure_structlog(
    level: int,
    json_output: bool,
    include_timestamp: bool,
) -> None:
    """Configure structlog for structured logging"""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if include_timestamp:
        processors.insert(0, structlog.processors.TimeStamper(fmt="iso"))

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to work with structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )


def _configure_standard_logging(level: int, include_timestamp: bool) -> None:
    """Configure standard logging as fallback"""
    fmt = "%(levelname)s | %(name)s | %(message)s"
    if include_timestamp:
        fmt = "%(asctime)s | " + fmt

    logging.basicConfig(
        format=fmt,
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        level=level,
    )


def get_logger(name: str) -> Any:
    """
    Get a logger instance.

    Returns structlog logger if available, otherwise standard logger.

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing request", request_id="abc123", step="fetch")
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    return logging.getLogger(name)


class LogContext:
    """
    Context manager for adding structured context to logs.

    Usage:
        with LogContext(request_id="abc123", chain="my_chain"):
            logger.info("Starting chain")  # Includes request_id and chain
    """

    def __init__(self, **context: Any):
        self.context = context
        self._token = None

    def __enter__(self) -> "LogContext":
        if STRUCTLOG_AVAILABLE and bind_contextvars:
            bind_contextvars(**self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if STRUCTLOG_AVAILABLE and unbind_contextvars:
            unbind_contextvars(*self.context.keys())

    async def __aenter__(self) -> "LogContext":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return self.__exit__(exc_type, exc_val, exc_tb)


def bind_context(**context: Any) -> None:
    """
    Bind context variables to all subsequent logs in the current context.

    Usage:
        bind_context(request_id="abc123")
        logger.info("Processing")  # Includes request_id
    """
    if STRUCTLOG_AVAILABLE and bind_contextvars:
        bind_contextvars(**context)


def clear_context() -> None:
    """Clear all bound context variables"""
    if STRUCTLOG_AVAILABLE and clear_contextvars:
        clear_contextvars()


# Convenience class for chain/step logging
class ChainLogger:
    """
    Specialized logger for chain execution with automatic context.

    Usage:
        logger = ChainLogger("my_chain", request_id="abc123")
        logger.step_start("fetch_data")
        logger.step_complete("fetch_data", duration_ms=150)
    """

    def __init__(self, chain_name: str, request_id: str | None = None):
        self.chain_name = chain_name
        self.request_id = request_id
        self._logger = get_logger(f"agentorchestrator.chain.{chain_name}")

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Log with chain context"""
        kwargs["chain"] = self.chain_name
        if self.request_id:
            kwargs["request_id"] = self.request_id

        log_method = getattr(self._logger, level, self._logger.info)
        log_method(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log("info", message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log("debug", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log("warning", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log("error", message, **kwargs)

    def chain_start(self, total_steps: int) -> None:
        self.info("Chain started", total_steps=total_steps)

    def chain_complete(self, duration_ms: float, success: bool = True) -> None:
        self.info("Chain completed", duration_ms=round(duration_ms, 2), success=success)

    def step_start(self, step_name: str) -> None:
        self.info("Step started", step=step_name)

    def step_complete(self, step_name: str, duration_ms: float) -> None:
        self.info("Step completed", step=step_name, duration_ms=round(duration_ms, 2))

    def step_failed(self, step_name: str, error: str, duration_ms: float) -> None:
        self.error("Step failed", step=step_name, error=error, duration_ms=round(duration_ms, 2))
