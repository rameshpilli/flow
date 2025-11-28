"""
FlowForge Timing Utilities

Decorators and utilities for timing operations.
"""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def timed(func: F) -> F:
    """
    Decorator to time function execution.

    Usage:
        @timed
        def my_function():
            ...
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(f"{func.__name__} executed in {elapsed:.2f}ms")
        return result

    return wrapper


def async_timed(func: F) -> F:
    """
    Decorator to time async function execution.

    Usage:
        @async_timed
        async def my_async_function():
            ...
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(f"{func.__name__} executed in {elapsed:.2f}ms")
        return result

    return wrapper


class Timer:
    """
    Context manager for timing code blocks.

    Usage:
        with Timer("my_operation") as t:
            do_something()
        print(f"Took {t.elapsed_ms}ms")
    """

    def __init__(self, name: str = "", log: bool = True):
        self.name = name
        self.log = log
        self.start_time: float = 0
        self.end_time: float = 0

    @property
    def elapsed_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.end_time = time.perf_counter()
        if self.log and self.name:
            logger.info(f"{self.name} took {self.elapsed_ms:.2f}ms")


class AsyncTimer:
    """
    Async context manager for timing code blocks.

    Usage:
        async with AsyncTimer("my_operation") as t:
            await do_something()
        print(f"Took {t.elapsed_ms}ms")
    """

    def __init__(self, name: str = "", log: bool = True):
        self.name = name
        self.log = log
        self.start_time: float = 0
        self.end_time: float = 0

    @property
    def elapsed_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self

    async def __aexit__(self, *args):
        self.end_time = time.perf_counter()
        if self.log and self.name:
            logger.info(f"{self.name} took {self.elapsed_ms:.2f}ms")
