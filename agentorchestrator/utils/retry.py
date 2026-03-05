"""
AgentOrchestrator Retry Utilities
=================================

This module provides decorators and utilities for retry logic with exponential backoff.

Retrying failed operations is essential for handling transient failures in distributed
systems. This module provides both decorator-based and class-based approaches for
adding retry logic to your functions.

Functions:
    retry(): Decorator for synchronous retry logic with exponential backoff.
    async_retry(): Decorator for async retry logic with exponential backoff.

Classes:
    RetryPolicy: Configurable retry policy that works with both sync and async functions.

Usage:
    from agentorchestrator.utils.retry import retry, async_retry, RetryPolicy

    # Decorator for sync functions
    @retry(max_attempts=3, delay_ms=1000)
    def call_api():
        return requests.get(url)

    # Decorator for async functions
    @async_retry(max_attempts=3, delay_ms=1000)
    async def call_api_async():
        return await client.get(url)

    # Policy-based approach
    policy = RetryPolicy(max_attempts=3, delay_ms=1000)

    @policy.wrap
    async def my_function():
        return await external_call()

Example:
    >>> from agentorchestrator.utils.retry import async_retry
    >>>
    >>> @async_retry(
    ...     max_attempts=3,
    ...     delay_ms=1000,
    ...     backoff_multiplier=2.0,
    ...     exceptions=(ConnectionError, TimeoutError),
    ... )
    ... async def fetch_data(url: str) -> dict:
    ...     async with aiohttp.ClientSession() as session:
    ...         async with session.get(url) as response:
    ...             return await response.json()
    >>>
    >>> # Function will retry up to 3 times on ConnectionError or TimeoutError
    >>> # with delays of 1s, 2s, 4s between attempts
    >>> data = await fetch_data("https://api.example.com/data")

See Also:
    - agentorchestrator.utils.circuit_breaker: For failing fast on repeated failures.
    - agentorchestrator.agents.base.ResilientAgent: Combines retry with circuit breaker.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

__all__ = [
    "retry",
    "async_retry",
    "RetryPolicy",
]

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    delay_ms: int = 1000,
    backoff_multiplier: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[F], F]:
    """
    Decorator for synchronous retry logic with exponential backoff.

    Wraps a synchronous function to automatically retry on specified exceptions.
    Each retry waits longer than the previous, following exponential backoff.

    Args:
        max_attempts (int): Maximum number of attempts before giving up.
            Default: 3. Total attempts = max_attempts (not retries).
        delay_ms (int): Initial delay between retries in milliseconds.
            Default: 1000 (1 second).
        backoff_multiplier (float): Multiplier for delay after each attempt.
            Default: 2.0. With delay_ms=1000: 1s -> 2s -> 4s -> 8s.
        exceptions (tuple[type[Exception], ...]): Exception types to retry on.
            Default: (Exception,). Only these exceptions trigger retries.
        on_retry (Callable[[Exception, int], None] | None): Callback invoked
            before each retry. Receives (exception, attempt_number).
            Useful for logging or metrics. Default: None.

    Returns:
        Callable[[F], F]: Decorator that wraps the function with retry logic.

    Raises:
        Exception: The last exception encountered after all retries are exhausted.

    Example:
        >>> @retry(max_attempts=3, delay_ms=1000)
        ... def call_flaky_api():
        ...     response = requests.get("https://api.example.com")
        ...     response.raise_for_status()
        ...     return response.json()
        >>>
        >>> # Retry only on specific exceptions
        >>> @retry(
        ...     max_attempts=5,
        ...     exceptions=(ConnectionError, TimeoutError),
        ...     on_retry=lambda e, a: logger.warning(f"Attempt {a} failed: {e}"),
        ... )
        ... def connect_to_database():
        ...     return db.connect()
        >>>
        >>> # Custom backoff
        >>> @retry(max_attempts=4, delay_ms=500, backoff_multiplier=3.0)
        ... def send_request():
        ...     # Delays: 0.5s, 1.5s, 4.5s
        ...     return api.request()

    Note:
        The delay is applied BEFORE the retry, not after the initial attempt.
        With max_attempts=3 and delay_ms=1000, backoff_multiplier=2.0:
        - Attempt 1: Execute immediately
        - Attempt 2: Wait 1000ms, then execute
        - Attempt 3: Wait 2000ms, then execute

    See Also:
        async_retry(): Async version of this decorator.
        RetryPolicy: Class-based retry configuration.
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
    Decorator for async retry logic with exponential backoff.

    Wraps an async function to automatically retry on specified exceptions.
    Each retry waits longer than the previous, following exponential backoff.

    Args:
        max_attempts (int): Maximum number of attempts before giving up.
            Default: 3. Total attempts = max_attempts (not retries).
        delay_ms (int): Initial delay between retries in milliseconds.
            Default: 1000 (1 second).
        backoff_multiplier (float): Multiplier for delay after each attempt.
            Default: 2.0. With delay_ms=1000: 1s -> 2s -> 4s -> 8s.
        exceptions (tuple[type[Exception], ...]): Exception types to retry on.
            Default: (Exception,). Only these exceptions trigger retries.
        on_retry (Callable[[Exception, int], None] | None): Callback invoked
            before each retry. Receives (exception, attempt_number).
            Useful for logging or metrics. Default: None.

    Returns:
        Callable[[F], F]: Decorator that wraps the async function with retry logic.

    Raises:
        Exception: The last exception encountered after all retries are exhausted.

    Example:
        >>> @async_retry(max_attempts=3, delay_ms=1000)
        ... async def fetch_user(user_id: str) -> dict:
        ...     async with aiohttp.ClientSession() as session:
        ...         async with session.get(f"/users/{user_id}") as resp:
        ...             return await resp.json()
        >>>
        >>> # Retry only on specific exceptions
        >>> @async_retry(
        ...     max_attempts=5,
        ...     exceptions=(aiohttp.ClientError, asyncio.TimeoutError),
        ...     on_retry=lambda e, a: metrics.increment("api.retry"),
        ... )
        ... async def call_external_api(payload: dict) -> dict:
        ...     return await api_client.post(payload)
        >>>
        >>> # With callback for monitoring
        >>> def log_retry(exc: Exception, attempt: int):
        ...     logger.warning(f"Retry {attempt}: {exc}")
        ...     sentry.capture_exception(exc)
        >>>
        >>> @async_retry(max_attempts=3, on_retry=log_retry)
        ... async def critical_operation():
        ...     return await service.execute()

    Note:
        Uses asyncio.sleep() for non-blocking delays between retries.
        The delay is applied BEFORE the retry, not after the initial attempt.

    See Also:
        retry(): Synchronous version of this decorator.
        RetryPolicy: Class-based retry configuration.
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

    Provides a class-based approach to retry configuration that can be
    shared across multiple functions. Automatically detects whether a
    function is async and applies the appropriate retry logic.

    Attributes:
        max_attempts (int): Maximum number of attempts.
        delay_ms (int): Initial delay in milliseconds.
        backoff_multiplier (float): Backoff multiplier for delays.
        exceptions (tuple[type[Exception], ...]): Exceptions to retry on.

    Methods:
        wrap(): Decorator method to wrap a function with retry logic.

    Example:
        >>> from agentorchestrator.utils.retry import RetryPolicy
        >>>
        >>> # Create a shared policy
        >>> api_retry = RetryPolicy(
        ...     max_attempts=3,
        ...     delay_ms=1000,
        ...     backoff_multiplier=2.0,
        ...     exceptions=(ConnectionError, TimeoutError),
        ... )
        >>>
        >>> # Apply to multiple functions
        >>> @api_retry.wrap
        ... async def fetch_users():
        ...     return await api.get("/users")
        >>>
        >>> @api_retry.wrap
        ... async def fetch_orders():
        ...     return await api.get("/orders")
        >>>
        >>> # Works with sync functions too
        >>> @api_retry.wrap
        ... def parse_response(data: bytes) -> dict:
        ...     return json.loads(data)

    Use Cases:
        - Sharing retry configuration across multiple functions
        - Dynamically configuring retry behavior at runtime
        - Integrating with dependency injection frameworks

    See Also:
        retry(): Decorator for sync functions.
        async_retry(): Decorator for async functions.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        delay_ms: int = 1000,
        backoff_multiplier: float = 2.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        """
        Initialize a retry policy with specified parameters.

        Args:
            max_attempts (int): Maximum number of attempts before giving up.
                Default: 3. Total attempts = max_attempts (not retries).
            delay_ms (int): Initial delay between retries in milliseconds.
                Default: 1000 (1 second).
            backoff_multiplier (float): Multiplier for delay after each attempt.
                Default: 2.0. With delay_ms=1000: 1s -> 2s -> 4s -> 8s.
            exceptions (tuple[type[Exception], ...]): Exception types to retry on.
                Default: (Exception,). Only these exceptions trigger retries.

        Example:
            >>> # Default policy (3 attempts, 1s initial delay)
            >>> policy = RetryPolicy()
            >>>
            >>> # Aggressive retry (5 attempts, short delays)
            >>> aggressive = RetryPolicy(
            ...     max_attempts=5,
            ...     delay_ms=100,
            ...     backoff_multiplier=1.5,
            ... )
            >>>
            >>> # Conservative retry (few attempts, long delays)
            >>> conservative = RetryPolicy(
            ...     max_attempts=2,
            ...     delay_ms=5000,
            ...     backoff_multiplier=3.0,
            ... )
            >>>
            >>> # Specific exception handling
            >>> network_retry = RetryPolicy(
            ...     exceptions=(ConnectionError, TimeoutError, OSError),
            ... )
        """
        self.max_attempts = max_attempts
        self.delay_ms = delay_ms
        self.backoff_multiplier = backoff_multiplier
        self.exceptions = exceptions

    def wrap(self, func: F) -> F:
        """
        Wrap a function with retry logic using this policy.

        Automatically detects whether the function is async or sync
        and applies the appropriate retry decorator.

        Args:
            func (F): The function to wrap. Can be sync or async.

        Returns:
            F: Wrapped function with retry logic applied.

        Example:
            >>> policy = RetryPolicy(max_attempts=3)
            >>>
            >>> # Wrap async function
            >>> @policy.wrap
            ... async def async_operation():
            ...     return await external_call()
            >>>
            >>> # Wrap sync function
            >>> @policy.wrap
            ... def sync_operation():
            ...     return blocking_call()
            >>>
            >>> # Wrap at runtime
            >>> wrapped_func = policy.wrap(existing_function)

        Note:
            The function type is detected using asyncio.iscoroutinefunction().
            Async functions use async_retry(), sync functions use retry().

        See Also:
            retry(): Applied to sync functions.
            async_retry(): Applied to async functions.
        """
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
