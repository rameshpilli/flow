"""
AgentOrchestrator Circuit Breaker
=================================

This module provides the circuit breaker pattern for resilience in external service calls.
Prevents cascading failures by failing fast when a service is unhealthy.

The circuit breaker monitors calls and tracks failures. When failures exceed a threshold,
the circuit "opens" and subsequent calls fail immediately without attempting the operation.
After a recovery timeout, the circuit enters a "half-open" state to test if the service
has recovered.

Classes:
    CircuitState: Enum of circuit breaker states (CLOSED, OPEN, HALF_OPEN).
    CircuitBreakerConfig: Configuration dataclass for circuit breaker behavior.
    CircuitStats: Statistics dataclass tracking circuit breaker metrics.
    CircuitBreakerError: Exception raised when circuit is open.
    CircuitBreaker: Main circuit breaker implementation.

Functions:
    get_circuit_breaker(): Get or create a named circuit breaker from registry.
    reset_all_circuit_breakers(): Reset all circuit breakers (for testing).

Usage:
    from agentorchestrator.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

    # Create a circuit breaker
    breaker = CircuitBreaker(
        name="api_gateway",
        config=CircuitBreakerConfig(failure_threshold=5, recovery_timeout=30.0),
    )

    # Use as async context manager
    async with breaker:
        result = await external_api_call()

    # Use as decorator
    @breaker
    async def call_external_service():
        return await api.fetch()

Example:
    >>> from agentorchestrator.utils.circuit_breaker import CircuitBreaker
    >>>
    >>> breaker = CircuitBreaker("llm_gateway")
    >>>
    >>> # Check state before calling
    >>> if not breaker.is_open:
    ...     async with breaker:
    ...         result = await llm.generate(prompt)
    >>>
    >>> # View statistics
    >>> print(breaker.stats)
    >>> # CircuitStats(failures=0, successes=5, total_calls=5, ...)

See Also:
    - agentorchestrator.agents.base.ResilientAgent: Uses CircuitBreaker internally.
    - agentorchestrator.utils.retry: Retry utilities for transient failures.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

logger = logging.getLogger(__name__)

__all__ = [
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitStats",
    "CircuitBreakerError",
    "CircuitBreaker",
    "get_circuit_breaker",
    "reset_all_circuit_breakers",
]

T = TypeVar("T")


class CircuitState(Enum):
    """
    Circuit breaker states.

    The circuit breaker transitions between these states based on
    success/failure patterns of the protected calls.

    Attributes:
        CLOSED: Normal operation. Requests pass through. Failures are counted.
            When failures reach threshold, transitions to OPEN.
        OPEN: Failing fast. All requests are rejected immediately with
            CircuitBreakerError. After recovery_timeout, transitions to HALF_OPEN.
        HALF_OPEN: Testing recovery. Limited requests are allowed through.
            On success_threshold successes, transitions to CLOSED.
            On any failure, transitions back to OPEN.

    Example:
        >>> breaker = CircuitBreaker("api")
        >>> print(breaker.state)
        CircuitState.CLOSED
        >>>
        >>> # After many failures
        >>> print(breaker.state)
        CircuitState.OPEN

    See Also:
        CircuitBreaker: Uses these states for flow control.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """
    Configuration for circuit breaker behavior.

    Controls when the circuit opens, how long to wait before testing
    recovery, and how many successes are needed to close the circuit.

    Attributes:
        failure_threshold (int): Number of failures before opening circuit.
            Default: 5. Lower values make the circuit more sensitive.
        recovery_timeout (float): Seconds to wait in OPEN state before
            transitioning to HALF_OPEN. Default: 30.0.
        half_open_max_calls (int): Maximum calls allowed in HALF_OPEN state.
            Default: 3. Limits exposure while testing recovery.
        success_threshold (int): Successes needed in HALF_OPEN to close circuit.
            Default: 2. Higher values require more proof of recovery.

    Example:
        >>> config = CircuitBreakerConfig(
        ...     failure_threshold=3,      # Open after 3 failures
        ...     recovery_timeout=60.0,    # Wait 60s before testing
        ...     half_open_max_calls=2,    # Allow 2 test calls
        ...     success_threshold=2,      # Need 2 successes to close
        ... )
        >>> breaker = CircuitBreaker("api", config=config)

    See Also:
        CircuitBreaker: Uses this configuration.
        ResilientAgentConfig: Higher-level config including circuit breaker.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    success_threshold: int = 2


@dataclass
class CircuitStats:
    """
    Statistics for circuit breaker monitoring.

    Tracks current window metrics and lifetime totals for monitoring
    circuit breaker health and behavior.

    Attributes:
        failures (int): Current window failure count. Reset on state change.
        successes (int): Current window success count. Reset on state change.
        last_failure_time (float | None): Monotonic timestamp of last failure.
        last_success_time (float | None): Monotonic timestamp of last success.
        total_calls (int): Lifetime total calls through the circuit.
        total_failures (int): Lifetime total failures.
        total_successes (int): Lifetime total successes.
        half_open_calls (int): Calls made in current HALF_OPEN window.

    Example:
        >>> stats = breaker.stats
        >>> print(f"Total calls: {stats.total_calls}")
        >>> print(f"Failure rate: {stats.total_failures / stats.total_calls:.2%}")
        >>>
        >>> # Check recent activity
        >>> if stats.last_failure_time:
        ...     print(f"Last failure: {time.monotonic() - stats.last_failure_time:.1f}s ago")

    See Also:
        CircuitBreaker.stats: Property that returns CircuitStats.
    """

    failures: int = 0
    successes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    half_open_calls: int = 0


class CircuitBreakerError(Exception):
    """
    Exception raised when circuit is open and call is rejected.

    This exception is raised immediately when attempting to make a call
    through an open circuit breaker, implementing the "fail fast" pattern.

    Attributes:
        message (str): Error message describing the rejection.
        circuit_name (str): Name of the circuit breaker that rejected the call.

    Example:
        >>> try:
        ...     async with breaker:
        ...         result = await api_call()
        ... except CircuitBreakerError as e:
        ...     logger.warning(f"Circuit {e.circuit_name} is open, using fallback")
        ...     result = get_cached_fallback()

    See Also:
        CircuitBreaker: Raises this when circuit is open.
    """

    def __init__(self, message: str, circuit_name: str):
        """
        Initialize CircuitBreakerError.

        Args:
            message (str): Error message describing why the call was rejected.
            circuit_name (str): Name of the circuit breaker that rejected the call.

        Example:
            >>> raise CircuitBreakerError(
            ...     "Circuit 'api' is open. Failing fast.",
            ...     circuit_name="api"
            ... )
        """
        super().__init__(message)
        self.circuit_name = circuit_name


class CircuitBreaker:
    """
    Circuit breaker for protecting external service calls.

    Implements the circuit breaker pattern to prevent cascading failures.
    When a service starts failing, the circuit opens and subsequent calls
    fail immediately without attempting the operation, giving the service
    time to recover.

    Attributes:
        name (str): Identifier for this circuit breaker.
        config (CircuitBreakerConfig): Configuration settings.
        state (CircuitState): Current circuit state (read-only property).
        stats (CircuitStats): Current statistics (read-only property).
        is_closed (bool): True if circuit is in CLOSED state.
        is_open (bool): True if circuit is in OPEN state.
        is_half_open (bool): True if circuit is in HALF_OPEN state.

    Methods:
        call(): Execute a function through the circuit breaker.
        reset(): Reset circuit to initial CLOSED state.
        force_open(): Force circuit to OPEN state (for maintenance).
        force_close(): Force circuit to CLOSED state (for testing).

    Example:
        >>> from agentorchestrator.utils.circuit_breaker import CircuitBreaker
        >>>
        >>> # Create circuit breaker
        >>> breaker = CircuitBreaker(
        ...     name="llm_gateway",
        ...     config=CircuitBreakerConfig(failure_threshold=5),
        ... )
        >>>
        >>> # Use as async context manager
        >>> async with breaker:
        ...     result = await llm.generate(prompt)
        >>>
        >>> # Use as decorator
        >>> @breaker
        ... async def call_llm(prompt: str) -> str:
        ...     return await llm.generate(prompt)
        >>>
        >>> # Manual call
        >>> result = await breaker.call(llm.generate, prompt)
        >>>
        >>> # Check state
        >>> if breaker.is_open:
        ...     logger.warning("LLM gateway is failing!")

    State Transitions:
        CLOSED -> OPEN: When failures >= failure_threshold
        OPEN -> HALF_OPEN: After recovery_timeout seconds
        HALF_OPEN -> CLOSED: After success_threshold successes
        HALF_OPEN -> OPEN: On any failure

    See Also:
        CircuitBreakerConfig: Configuration options.
        CircuitBreakerError: Exception raised when circuit is open.
        get_circuit_breaker(): Get named circuit breaker from registry.
    """

    def __init__(
        self,
        name: str = "default",
        config: CircuitBreakerConfig | None = None,
        on_state_change: Callable[[CircuitState, CircuitState], None] | None = None,
    ):
        """
        Initialize a circuit breaker.

        Args:
            name (str): Identifier for this circuit breaker. Used in logs
                and error messages. Default: "default".
            config (CircuitBreakerConfig | None): Configuration settings.
                If None, uses default CircuitBreakerConfig values.
            on_state_change (Callable | None): Callback function invoked when
                state changes. Receives (old_state, new_state) as arguments.
                Useful for logging or alerting. Default: None.

        Example:
            >>> # Simple circuit breaker
            >>> breaker = CircuitBreaker("api_gateway")
            >>>
            >>> # With custom config
            >>> breaker = CircuitBreaker(
            ...     name="llm_service",
            ...     config=CircuitBreakerConfig(
            ...         failure_threshold=3,
            ...         recovery_timeout=60.0,
            ...     ),
            ... )
            >>>
            >>> # With state change callback
            >>> def on_change(old, new):
            ...     logger.info(f"Circuit changed: {old} -> {new}")
            ...     if new == CircuitState.OPEN:
            ...         alert_ops_team()
            >>>
            >>> breaker = CircuitBreaker("critical_api", on_state_change=on_change)
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.on_state_change = on_state_change

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = asyncio.Lock()
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        """
        Get the current circuit state.

        Returns:
            CircuitState: Current state (CLOSED, OPEN, or HALF_OPEN).

        Example:
            >>> if breaker.state == CircuitState.OPEN:
            ...     logger.warning("Circuit is open!")
        """
        return self._state

    @property
    def stats(self) -> CircuitStats:
        """
        Get current circuit statistics.

        Returns:
            CircuitStats: Statistics including failures, successes, and totals.

        Example:
            >>> stats = breaker.stats
            >>> print(f"Failures: {stats.failures}/{breaker.config.failure_threshold}")
        """
        return self._stats

    @property
    def is_closed(self) -> bool:
        """
        Check if circuit is in CLOSED (normal) state.

        Returns:
            bool: True if circuit is closed and accepting requests.

        Example:
            >>> if breaker.is_closed:
            ...     result = await breaker.call(api_func)
        """
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """
        Check if circuit is in OPEN (failing fast) state.

        Returns:
            bool: True if circuit is open and rejecting requests.

        Example:
            >>> if breaker.is_open:
            ...     return get_fallback_response()
        """
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """
        Check if circuit is in HALF_OPEN (testing recovery) state.

        Returns:
            bool: True if circuit is testing for service recovery.

        Example:
            >>> if breaker.is_half_open:
            ...     logger.info("Testing if service has recovered...")
        """
        return self._state == CircuitState.HALF_OPEN

    def _set_state(self, new_state: CircuitState) -> None:
        """
        Update state and notify listeners.

        Internal method that handles state transitions and invokes
        the on_state_change callback if configured.

        Args:
            new_state (CircuitState): The new state to transition to.
        """
        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            logger.info(f"Circuit '{self.name}' state: {old_state.value} -> {new_state.value}")
            if self.on_state_change:
                self.on_state_change(old_state, new_state)

    def _should_allow_request(self) -> bool:
        """
        Check if a request should be allowed through.

        Internal method that implements the circuit breaker logic for
        determining whether to allow a request based on current state.

        Returns:
            bool: True if request should proceed, False if it should be rejected.
        """
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
        """
        Record a successful call.

        Internal method that updates statistics and potentially
        transitions from HALF_OPEN to CLOSED on sufficient successes.
        """
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
        """
        Record a failed call.

        Internal method that updates statistics and potentially
        transitions to OPEN state based on failure threshold.
        """
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

        This is the primary method for protecting function calls.
        The function is only executed if the circuit allows it.

        Args:
            func (Callable): Async or sync function to call.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.

        Returns:
            T: The return value from the function.

        Raises:
            CircuitBreakerError: If circuit is open and rejecting calls.
            Exception: Any exception raised by the wrapped function.

        Example:
            >>> # Call async function
            >>> result = await breaker.call(api.fetch_data, user_id=123)
            >>>
            >>> # Call sync function
            >>> result = await breaker.call(parse_response, response)
            >>>
            >>> # Handle circuit open
            >>> try:
            ...     result = await breaker.call(external_api)
            ... except CircuitBreakerError:
            ...     result = get_cached_fallback()
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
        """
        Async context manager entry.

        Checks if the circuit allows requests and raises CircuitBreakerError
        if the circuit is open.

        Returns:
            CircuitBreaker: Self for use in async with block.

        Raises:
            CircuitBreakerError: If circuit is open.

        Example:
            >>> async with breaker:
            ...     result = await external_call()
        """
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
        """
        Async context manager exit.

        Records success or failure based on whether an exception occurred.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.

        Returns:
            bool: False (does not suppress exceptions).

        Example:
            >>> async with breaker:
            ...     # Success is recorded if no exception
            ...     result = await api_call()
            ...     # Failure is recorded if exception raised
        """
        async with self._lock:
            if exc_type is None:
                self._record_success()
            else:
                self._record_failure()
        return False  # Don't suppress exceptions

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """
        Use circuit breaker as a decorator.

        Wraps a function so all calls go through the circuit breaker.
        Works with both sync and async functions.

        Args:
            func (Callable): Function to wrap with circuit breaker protection.

        Returns:
            Callable: Wrapped function with circuit breaker protection.

        Example:
            >>> @breaker
            ... async def fetch_user(user_id: str) -> dict:
            ...     return await api.get_user(user_id)
            >>>
            >>> # Calls are now protected
            >>> user = await fetch_user("123")
            >>>
            >>> @breaker
            ... def parse_data(raw: str) -> dict:
            ...     return json.loads(raw)
        """
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
        """
        Reset circuit breaker to initial CLOSED state.

        Clears all statistics and resets the circuit to its initial state.
        Use this after fixing the underlying issue or for testing.

        Example:
            >>> # After fixing the failing service
            >>> breaker.reset()
            >>> print(breaker.state)
            CircuitState.CLOSED
            >>>
            >>> # Statistics are cleared
            >>> print(breaker.stats.failures)
            0
        """
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._opened_at = None
        logger.info(f"Circuit '{self.name}' reset")

    def force_open(self) -> None:
        """
        Force circuit to OPEN state.

        Use this for maintenance windows or when you know the service
        is unavailable and want to fail fast immediately.

        Example:
            >>> # Before maintenance
            >>> breaker.force_open()
            >>> # All calls will now fail immediately
            >>>
            >>> # After maintenance
            >>> breaker.reset()
        """
        self._set_state(CircuitState.OPEN)
        self._opened_at = time.monotonic()

    def force_close(self) -> None:
        """
        Force circuit to CLOSED state.

        Use this for testing or when you're certain the service
        has recovered and want to skip the half-open testing phase.

        Example:
            >>> # After confirming service is healthy
            >>> breaker.force_close()
            >>> # Calls will now go through
        """
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
    Get or create a named circuit breaker from the registry.

    This function provides a singleton pattern for circuit breakers.
    The first call with a given name creates the circuit breaker;
    subsequent calls return the same instance.

    Args:
        name (str): Unique identifier for the circuit breaker.
        config (CircuitBreakerConfig | None): Configuration for new circuit
            breakers. Ignored if circuit breaker already exists.

    Returns:
        CircuitBreaker: The named circuit breaker instance.

    Example:
        >>> # Get or create a circuit breaker
        >>> breaker = get_circuit_breaker("llm_gateway")
        >>>
        >>> # Same instance is returned
        >>> breaker2 = get_circuit_breaker("llm_gateway")
        >>> assert breaker is breaker2
        >>>
        >>> # Create with custom config
        >>> breaker = get_circuit_breaker(
        ...     "api_v2",
        ...     config=CircuitBreakerConfig(failure_threshold=3),
        ... )

    Note:
        Config is only used when creating a new circuit breaker.
        If the breaker already exists, the config parameter is ignored.

    See Also:
        CircuitBreaker: The circuit breaker class.
        reset_all_circuit_breakers(): Reset all registered breakers.
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def reset_all_circuit_breakers() -> None:
    """
    Reset all circuit breakers in the registry.

    Resets every circuit breaker to its initial CLOSED state with
    cleared statistics. Primarily useful for testing.

    Example:
        >>> # In test setup/teardown
        >>> reset_all_circuit_breakers()
        >>>
        >>> # All breakers are now in initial state
        >>> breaker = get_circuit_breaker("api")
        >>> assert breaker.is_closed
        >>> assert breaker.stats.total_calls == 0

    See Also:
        CircuitBreaker.reset(): Reset a single circuit breaker.
        get_circuit_breaker(): Get named circuit breaker.
    """
    for breaker in _circuit_breakers.values():
        breaker.reset()