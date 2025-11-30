"""
AgentOrchestrator Retry Utilities

Decorators and utilities for retry logic.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    delay_ms: int = 1000,
    backoff_multiplier: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[F], F]:
    """
    Decorator for synchronous retry logic.

    Usage:
        @retry(max_attempts=3, delay_ms=1000)
        def flaky_function():
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = delay_ms

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay}ms..."
                        )
                        if on_retry:
                            on_retry(e, attempt)
                        time.sleep(delay / 1000)
                        delay = int(delay * backoff_multiplier)

            raise last_exception

        return wrapper

    return decorator


def async_retry(
    max_attempts: int = 3,
    delay_ms: int = 1000,
    backoff_multiplier: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[F], F]:
    """
    Decorator for async retry logic.

    Usage:
        @async_retry(max_attempts=3, delay_ms=1000)
        async def flaky_async_function():
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            delay = delay_ms

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay}ms..."
                        )
                        if on_retry:
                            on_retry(e, attempt)
                        await asyncio.sleep(delay / 1000)
                        delay = int(delay * backoff_multiplier)

            raise last_exception

        return wrapper

    return decorator


class RetryPolicy:
    """
    Configurable retry policy for use with agents and connectors.

    Usage:
        policy = RetryPolicy(max_attempts=3, delay_ms=1000)

        @policy.wrap
        async def my_function():
            ...
    """

    def __init__(
        self,
        max_attempts: int = 3,
        delay_ms: int = 1000,
        backoff_multiplier: float = 2.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        self.max_attempts = max_attempts
        self.delay_ms = delay_ms
        self.backoff_multiplier = backoff_multiplier
        self.exceptions = exceptions

    def wrap(self, func: F) -> F:
        """Wrap a function with retry logic"""
        if asyncio.iscoroutinefunction(func):
            return async_retry(
                max_attempts=self.max_attempts,
                delay_ms=self.delay_ms,
                backoff_multiplier=self.backoff_multiplier,
                exceptions=self.exceptions,
            )(func)
        else:
            return retry(
                max_attempts=self.max_attempts,
                delay_ms=self.delay_ms,
                backoff_multiplier=self.backoff_multiplier,
                exceptions=self.exceptions,
            )(func)
