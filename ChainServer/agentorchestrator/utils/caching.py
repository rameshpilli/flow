"""
Caching Utilities

Provides time-based LRU cache decorators for both sync and async functions.

Usage:
    from agentorchestrator.utils.caching import timed_lru_cache, async_timed_lru_cache

    @timed_lru_cache(seconds=300, maxsize=128)
    def fetch_data(key: str) -> dict:
        return expensive_operation(key)

    @async_timed_lru_cache(seconds=300, maxsize=128)
    async def fetch_data_async(key: str) -> dict:
        return await async_expensive_operation(key)
"""

import asyncio
import functools
import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def timed_lru_cache(seconds: int = 300, maxsize: int = 128):
    """
    LRU cache decorator with time-based expiration (thread-safe).

    Caches function results for a specified duration. After expiration,
    the next call will re-execute the function and cache the new result.

    Args:
        seconds: Cache TTL in seconds (default: 300 = 5 minutes)
        maxsize: Maximum cache size (default: 128)

    Returns:
        Decorated function with caching

    Example:
        @timed_lru_cache(seconds=60, maxsize=100)
        def get_user(user_id: str) -> dict:
            return db.fetch_user(user_id)
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

        # Add cache management methods
        wrapper.cache_clear = lambda: cache.clear()
        wrapper.cache_info = lambda: {"size": len(cache), "maxsize": maxsize, "ttl": seconds}

        return wrapper
    return decorator


def async_timed_lru_cache(seconds: int = 300, maxsize: int = 128):
    """
    Async LRU cache decorator with time-based expiration.

    Thread-safe caching for async functions with automatic expiration.

    Args:
        seconds: Cache TTL in seconds (default: 300 = 5 minutes)
        maxsize: Maximum cache size (default: 128)

    Returns:
        Decorated async function with caching

    Example:
        @async_timed_lru_cache(seconds=60, maxsize=100)
        async def get_user(user_id: str) -> dict:
            return await db.fetch_user(user_id)
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

        # Add cache management methods
        wrapper.cache_clear = lambda: cache.clear()
        wrapper.cache_info = lambda: {"size": len(cache), "maxsize": maxsize, "ttl": seconds}

        return wrapper
    return decorator
