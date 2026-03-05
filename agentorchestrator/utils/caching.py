"""
AgentOrchestrator Caching Utilities
===================================

This module provides time-based LRU cache decorators for both sync and async functions.

Caching is essential for reducing latency and load on external services. These decorators
combine the benefits of LRU (Least Recently Used) eviction with time-based expiration,
ensuring cached data stays fresh while limiting memory usage.

Functions:
    timed_lru_cache(): Thread-safe LRU cache with TTL for sync functions.
    async_timed_lru_cache(): Async-safe LRU cache with TTL for async functions.

Usage:
    from agentorchestrator.utils.caching import timed_lru_cache, async_timed_lru_cache

    # Cache sync function results for 5 minutes
    @timed_lru_cache(seconds=300, maxsize=128)
    def fetch_config(key: str) -> dict:
        return database.get_config(key)

    # Cache async function results for 1 minute
    @async_timed_lru_cache(seconds=60, maxsize=100)
    async def fetch_user(user_id: str) -> dict:
        return await api.get_user(user_id)

Example:
    >>> from agentorchestrator.utils.caching import async_timed_lru_cache
    >>>
    >>> @async_timed_lru_cache(seconds=300, maxsize=1000)
    ... async def get_stock_price(symbol: str) -> float:
    ...     return await market_api.get_price(symbol)
    >>>
    >>> # First call fetches from API
    >>> price = await get_stock_price("AAPL")  # ~100ms
    >>>
    >>> # Second call returns cached value
    >>> price = await get_stock_price("AAPL")  # ~0ms
    >>>
    >>> # After 5 minutes, cache expires
    >>> price = await get_stock_price("AAPL")  # ~100ms (re-fetches)
    >>>
    >>> # View cache info
    >>> print(get_stock_price.cache_info())
    >>> # {"size": 1, "maxsize": 1000, "ttl": 300}
    >>>
    >>> # Clear cache manually
    >>> get_stock_price.cache_clear()

See Also:
    - functools.lru_cache: Standard library LRU cache (no TTL).
    - agentorchestrator.utils.retry: For retrying failed operations.
"""

import asyncio
import functools
import threading
import time
from typing import Callable, TypeVar

__all__ = [
    "timed_lru_cache",
    "async_timed_lru_cache",
]

T = TypeVar("T")


def timed_lru_cache(seconds: int = 300, maxsize: int = 128):
    """
    LRU cache decorator with time-based expiration (thread-safe).

    Caches function results for a specified duration. After expiration,
    the next call will re-execute the function and cache the new result.
    Uses threading.Lock for thread-safety in multi-threaded applications.

    Args:
        seconds (int): Cache TTL (Time To Live) in seconds. Cached values
            older than this are considered stale and will be refreshed.
            Default: 300 (5 minutes).
        maxsize (int): Maximum number of entries in the cache. When exceeded,
            the oldest entry (by timestamp) is evicted. Default: 128.

    Returns:
        Callable: Decorator that wraps the function with caching.

    Attributes (on wrapped function):
        cache_clear (Callable[[], None]): Clear all cached entries.
        cache_info (Callable[[], dict]): Get cache statistics.

    Example:
        >>> @timed_lru_cache(seconds=60, maxsize=100)
        ... def get_user(user_id: str) -> dict:
        ...     return db.fetch_user(user_id)
        >>>
        >>> # First call hits database
        >>> user = get_user("123")
        >>>
        >>> # Second call returns cached result
        >>> user = get_user("123")
        >>>
        >>> # Check cache status
        >>> info = get_user.cache_info()
        >>> print(f"Cached entries: {info['size']}/{info['maxsize']}")
        >>>
        >>> # Clear cache (e.g., after data update)
        >>> get_user.cache_clear()

    Cache Key:
        The cache key is generated from (args, sorted(kwargs.items())).
        Arguments must be hashable. For unhashable arguments, consider:
        - Converting dicts to frozensets: frozenset(d.items())
        - Converting lists to tuples: tuple(lst)
        - Using string representations: str(obj)

    Thread Safety:
        Uses threading.Lock to ensure thread-safe cache access.
        The function execution happens outside the lock to avoid blocking.

    Example with complex keys:
        >>> @timed_lru_cache(seconds=300)
        ... def query_data(query: str, filters: tuple = ()) -> list:
        ...     # filters must be tuple (hashable), not list
        ...     return db.query(query, list(filters))
        >>>
        >>> data = query_data("SELECT *", filters=("active", "verified"))

    See Also:
        async_timed_lru_cache(): Async version of this decorator.
        functools.lru_cache: Standard library LRU cache without TTL.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache: dict = {}
        lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()

            with lock:
                if key in cache:
                    result, timestamp = cache[key]
                    if now - timestamp < seconds:
                        return result

            # Execute function outside lock to avoid blocking
            result = func(*args, **kwargs)

            with lock:
                cache[key] = (result, now)
                # Evict oldest entry if cache is too large
                if len(cache) > maxsize:
                    oldest = min(cache.keys(), key=lambda k: cache[k][1])
                    del cache[oldest]

            return result

        def cache_clear() -> None:
            """
            Clear all cached entries.

            Removes all entries from the cache, forcing subsequent calls
            to re-execute the function.

            Example:
                >>> get_user.cache_clear()
                >>> # Next call will fetch fresh data
                >>> user = get_user("123")
            """
            with lock:
                cache.clear()

        def cache_info() -> dict:
            """
            Get cache statistics.

            Returns:
                dict: Cache information including:
                    - size (int): Current number of cached entries.
                    - maxsize (int): Maximum cache size.
                    - ttl (int): TTL in seconds.

            Example:
                >>> info = get_user.cache_info()
                >>> print(f"Cache utilization: {info['size']}/{info['maxsize']}")
            """
            with lock:
                return {"size": len(cache), "maxsize": maxsize, "ttl": seconds}

        wrapper.cache_clear = cache_clear
        wrapper.cache_info = cache_info

        return wrapper
    return decorator


def async_timed_lru_cache(seconds: int = 300, maxsize: int = 128):
    """
    Async LRU cache decorator with time-based expiration.

    Caches async function results for a specified duration. After expiration,
    the next call will re-execute the function and cache the new result.
    Uses asyncio.Lock for safe concurrent access in async applications.

    Args:
        seconds (int): Cache TTL (Time To Live) in seconds. Cached values
            older than this are considered stale and will be refreshed.
            Default: 300 (5 minutes).
        maxsize (int): Maximum number of entries in the cache. When exceeded,
            the oldest entry (by timestamp) is evicted. Default: 128.

    Returns:
        Callable: Decorator that wraps the async function with caching.

    Attributes (on wrapped function):
        cache_clear (Callable[[], None]): Clear all cached entries.
        cache_info (Callable[[], dict]): Get cache statistics.

    Example:
        >>> @async_timed_lru_cache(seconds=60, maxsize=100)
        ... async def get_user(user_id: str) -> dict:
        ...     return await db.fetch_user(user_id)
        >>>
        >>> # First call hits database
        >>> user = await get_user("123")
        >>>
        >>> # Second call returns cached result (instant)
        >>> user = await get_user("123")
        >>>
        >>> # Check cache status
        >>> info = get_user.cache_info()
        >>> print(f"Cached entries: {info['size']}/{info['maxsize']}")
        >>>
        >>> # Clear cache (e.g., after data update)
        >>> get_user.cache_clear()

    Cache Key:
        The cache key is generated from (args, sorted(kwargs.items())).
        Arguments must be hashable. For unhashable arguments, consider:
        - Converting dicts to frozensets: frozenset(d.items())
        - Converting lists to tuples: tuple(lst)
        - Using string representations: str(obj)

    Concurrency:
        Uses asyncio.Lock to ensure safe concurrent access.
        Note: The lock is held during cache lookup but NOT during
        function execution, allowing concurrent calls to different keys.

    Example with API caching:
        >>> @async_timed_lru_cache(seconds=300, maxsize=1000)
        ... async def fetch_stock_data(symbol: str, period: str = "1d") -> dict:
        ...     async with aiohttp.ClientSession() as session:
        ...         async with session.get(f"/stocks/{symbol}?period={period}") as resp:
        ...             return await resp.json()
        >>>
        >>> # Cache different combinations
        >>> aapl_daily = await fetch_stock_data("AAPL", period="1d")
        >>> aapl_weekly = await fetch_stock_data("AAPL", period="1w")
        >>> msft_daily = await fetch_stock_data("MSFT", period="1d")

    Note:
        The cache is NOT shared across event loops. If you create multiple
        event loops, each will have its own cache instance.

    See Also:
        timed_lru_cache(): Sync version of this decorator.
        asyncio.Lock: The locking mechanism used.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache: dict = {}
        lock = asyncio.Lock()

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()

            async with lock:
                if key in cache:
                    result, timestamp = cache[key]
                    if now - timestamp < seconds:
                        return result

            result = await func(*args, **kwargs)

            async with lock:
                cache[key] = (result, now)
                # Evict oldest entry if cache is too large
                if len(cache) > maxsize:
                    oldest = min(cache.keys(), key=lambda k: cache[k][1])
                    del cache[oldest]

            return result

        def cache_clear() -> None:
            """
            Clear all cached entries.

            Removes all entries from the cache, forcing subsequent calls
            to re-execute the function. This is a synchronous operation
            and can be called from outside an async context.

            Example:
                >>> get_user.cache_clear()
                >>> # Next call will fetch fresh data
                >>> user = await get_user("123")
            """
            cache.clear()

        def cache_info() -> dict:
            """
            Get cache statistics.

            Returns:
                dict: Cache information including:
                    - size (int): Current number of cached entries.
                    - maxsize (int): Maximum cache size.
                    - ttl (int): TTL in seconds.

            Example:
                >>> info = get_user.cache_info()
                >>> print(f"Cache utilization: {info['size']}/{info['maxsize']}")
            """
            return {"size": len(cache), "maxsize": maxsize, "ttl": seconds}

        wrapper.cache_clear = cache_clear
        wrapper.cache_info = cache_info

        return wrapper
    return decorator