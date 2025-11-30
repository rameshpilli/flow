"""
FlowForge Circuit Breaker

Simple circuit breaker pattern for resilience in external service calls.
Prevents cascading failures by failing fast when a service is unhealthy.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failing fast, requests are rejected
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 5          # Failures before opening circuit
    recovery_timeout: float = 30.0      # Seconds before trying again (half-open)
    half_open_max_calls: int = 3        # Calls allowed in half-open state
    success_threshold: int = 2          # Successes in half-open to close circuit


@dataclass
class CircuitStats:
    """Statistics for circuit breaker"""
    failures: int = 0
    successes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    half_open_calls: int = 0


class CircuitBreakerError(Exception):
    """Raised when circuit is open and call is rejected"""
    def __init__(self, message: str, circuit_name: str):
        super().__init__(message)
        self.circuit_name = circuit_name


class CircuitBreaker:
    """
    Circuit breaker for protecting external service calls.

    States:
    - CLOSED: Normal operation. Failures increment counter.
              Opens when failure_threshold is reached.
    - OPEN: Failing fast. All calls are rejected immediately.
            Transitions to HALF_OPEN after recovery_timeout.
    - HALF_OPEN: Testing recovery. Limited calls allowed.
                 Closes on success_threshold successes, opens on any failure.

    Usage:
        breaker = CircuitBreaker("llm_gateway")

        # As decorator
        @breaker
        async def call_llm(prompt: str) -> str:
            ...

        # As context manager
        async with breaker:
            result = await external_call()

        # Manual call
        result = await breaker.call(external_call, prompt)
    """

    def __init__(
        self,
        name: str = "default",
        config: CircuitBreakerConfig | None = None,
        on_state_change: Callable[[CircuitState, CircuitState], None] | None = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.on_state_change = on_state_change

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = asyncio.Lock()
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        """Current circuit state"""
        return self._state

    @property
    def stats(self) -> CircuitStats:
        """Current circuit statistics"""
        return self._stats

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN

    def _set_state(self, new_state: CircuitState) -> None:
        """Update state and notify listeners"""
        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            logger.info(f"Circuit '{self.name}' state: {old_state.value} -> {new_state.value}")
            if self.on_state_change:
                self.on_state_change(old_state, new_state)

    def _should_allow_request(self) -> bool:
        """Check if a request should be allowed through"""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self._opened_at and (time.monotonic() - self._opened_at) >= self.config.recovery_timeout:
                self._set_state(CircuitState.HALF_OPEN)
                self._stats.half_open_calls = 0
                return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            # Allow limited calls in half-open state
            return self._stats.half_open_calls < self.config.half_open_max_calls

        return False

    def _record_success(self) -> None:
        """Record a successful call"""
        self._stats.successes += 1
        self._stats.total_successes += 1
        self._stats.total_calls += 1
        self._stats.last_success_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            if self._stats.successes >= self.config.success_threshold:
                # Service recovered, close circuit
                self._set_state(CircuitState.CLOSED)
                self._stats.failures = 0
                self._stats.successes = 0

    def _record_failure(self) -> None:
        """Record a failed call"""
        self._stats.failures += 1
        self._stats.total_failures += 1
        self._stats.total_calls += 1
        self._stats.last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open reopens the circuit
            self._set_state(CircuitState.OPEN)
            self._opened_at = time.monotonic()
            self._stats.successes = 0
        elif self._state == CircuitState.CLOSED:
            if self._stats.failures >= self.config.failure_threshold:
                # Too many failures, open circuit
                self._set_state(CircuitState.OPEN)
                self._opened_at = time.monotonic()

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute a function through the circuit breaker.

        Args:
            func: Async or sync function to call
            *args, **kwargs: Arguments to pass to function

        Returns:
            Function result

        Raises:
            CircuitBreakerError: If circuit is open
        """
        async with self._lock:
            if not self._should_allow_request():
                raise CircuitBreakerError(
                    f"Circuit '{self.name}' is open. Failing fast.",
                    self.name
                )

            if self._state == CircuitState.HALF_OPEN:
                self._stats.half_open_calls += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            async with self._lock:
                self._record_success()

            return result

        except Exception:
            async with self._lock:
                self._record_failure()
            raise

    async def __aenter__(self) -> "CircuitBreaker":
        """Async context manager entry"""
        async with self._lock:
            if not self._should_allow_request():
                raise CircuitBreakerError(
                    f"Circuit '{self.name}' is open. Failing fast.",
                    self.name
                )
            if self._state == CircuitState.HALF_OPEN:
                self._stats.half_open_calls += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Async context manager exit"""
        async with self._lock:
            if exc_type is None:
                self._record_success()
            else:
                self._record_failure()
        return False  # Don't suppress exceptions

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Use as decorator"""
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs) -> T:
                return await self.call(func, *args, **kwargs)
            async_wrapper.__name__ = func.__name__
            async_wrapper.__doc__ = func.__doc__
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs) -> T:
                return asyncio.get_event_loop().run_until_complete(
                    self.call(func, *args, **kwargs)
                )
            sync_wrapper.__name__ = func.__name__
            sync_wrapper.__doc__ = func.__doc__
            return sync_wrapper

    def reset(self) -> None:
        """Reset circuit breaker to initial state"""
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._opened_at = None
        logger.info(f"Circuit '{self.name}' reset")

    def force_open(self) -> None:
        """Force circuit to open state (for testing/maintenance)"""
        self._set_state(CircuitState.OPEN)
        self._opened_at = time.monotonic()

    def force_close(self) -> None:
        """Force circuit to closed state (for testing)"""
        self._set_state(CircuitState.CLOSED)
        self._stats.failures = 0
        self._stats.successes = 0


# Registry for named circuit breakers
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None,
) -> CircuitBreaker:
    """
    Get or create a named circuit breaker.

    Usage:
        breaker = get_circuit_breaker("llm_gateway")
        result = await breaker.call(llm_call, prompt)
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers (for testing)"""
    for breaker in _circuit_breakers.values():
        breaker.reset()
