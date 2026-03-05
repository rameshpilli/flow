"""
AgentOrchestrator Rate Limiting & Circuit Breaker Middleware
============================================================

This module provides middleware for controlling request rates and implementing
circuit breaker patterns to protect external APIs and services from overload.

The middleware implements:
- Token bucket rate limiting (requests per second with burst support)
- Semaphore-based concurrency control (max parallel requests)
- Circuit breaker for graceful degradation (fail-fast on repeated failures)
- Configurable wait vs. reject behavior when limits are hit

Classes:
    RateLimitConfig: Configuration for per-step rate limiting.
    MiddlewareCircuitBreakerConfig: Configuration for circuit breaker behavior.
    StepRateLimitState: Runtime state for rate limiting a single step.
    CircuitBreakerState: Runtime state for a circuit breaker.
    RateLimitExceededError: Exception when rate limit is exceeded.
    CircuitOpenError: Exception when circuit breaker is open.
    RateLimiterMiddleware: Token bucket rate limiting middleware.
    CircuitBreakerMiddleware: Circuit breaker middleware for graceful degradation.
    RateLimitAndCircuitBreakerMiddleware: Combined rate limiting and circuit breaker.

Usage:
    from agentorchestrator.middleware import (
        RateLimiterMiddleware,
        RateLimitConfig,
        CircuitBreakerMiddleware,
        MiddlewareCircuitBreakerConfig,
    )

    # Configure rate limiting
    ao.use(RateLimiterMiddleware({
        "fetch_news_data": RateLimitConfig(requests_per_second=5, max_concurrent=3),
        "fetch_sec_data": RateLimitConfig(requests_per_second=10, max_concurrent=5),
    }))

    # Configure circuit breaker
    ao.use(CircuitBreakerMiddleware({
        "fetch_news_data": MiddlewareCircuitBreakerConfig(failure_threshold=5),
    }))

Example:
    >>> from agentorchestrator.middleware import (
    ...     RateLimitAndCircuitBreakerMiddleware,
    ...     RateLimitConfig,
    ...     MiddlewareCircuitBreakerConfig,
    ... )
    >>>
    >>> # Combined protection for data fetching steps
    >>> protection = RateLimitAndCircuitBreakerMiddleware(
    ...     rate_limits={
    ...         "fetch_news_data": RateLimitConfig(
    ...             requests_per_second=5,
    ...             max_concurrent=3,
    ...             wait_on_limit=True,
    ...         ),
    ...     },
    ...     circuit_breakers={
    ...         "fetch_news_data": MiddlewareCircuitBreakerConfig(
    ...             failure_threshold=5,
    ...             recovery_timeout_seconds=60,
    ...         ),
    ...     },
    ... )
    >>> ao.use(protection)
    >>>
    >>> # Check statistics
    >>> stats = protection.get_stats()
    >>> print(f"Rate limit stats: {stats['rate_limits']}")
    >>> print(f"Circuit states: {stats['circuit_breakers']}")

See Also:
    - agentorchestrator.middleware.base: Base middleware class.
    - agentorchestrator.utils.circuit_breaker: Standalone circuit breaker utility.
    - agentorchestrator.agents.base: ResilientAgent with built-in resilience.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware

# Import CircuitState from utils to avoid duplicate definitions
from agentorchestrator.utils.circuit_breaker import CircuitState

logger = logging.getLogger(__name__)

__all__ = [
    "RateLimitConfig",
    "MiddlewareCircuitBreakerConfig",
    "StepRateLimitState",
    "CircuitBreakerState",
    "RateLimitExceededError",
    "CircuitOpenError",
    "RateLimiterMiddleware",
    "CircuitBreakerMiddleware",
    "RateLimitAndCircuitBreakerMiddleware",
]


@dataclass
class RateLimitConfig:
    """
    Configuration for per-step rate limiting.

    Controls how requests to a step are throttled using a token bucket
    algorithm combined with semaphore-based concurrency control.

    Attributes:
        requests_per_second (float): Maximum requests per second. Set to 0
            for unlimited. Default: 0 (unlimited).
        max_concurrent (int): Maximum concurrent executions. Set to 0 for
            unlimited. Default: 0 (unlimited).
        burst_size (int): Allow burst of this many requests before rate
            limiting kicks in. Acts as the token bucket capacity.
            Default: 1.
        wait_on_limit (bool): If True, wait when limit is hit. If False,
            raise RateLimitExceededError immediately. Default: True.
        max_wait_seconds (float): Maximum time to wait for rate limit
            clearance. Set to 0 to wait indefinitely. Default: 30.0.

    Example:
        >>> # Strict API limits
        >>> config = RateLimitConfig(
        ...     requests_per_second=5,     # 5 requests per second
        ...     max_concurrent=3,          # Max 3 in parallel
        ...     burst_size=5,              # Allow burst of 5
        ...     wait_on_limit=True,        # Wait rather than fail
        ...     max_wait_seconds=10.0,     # Max 10s wait
        ... )
        >>>
        >>> # Fast API with high concurrency
        >>> fast_config = RateLimitConfig(
        ...     requests_per_second=100,
        ...     max_concurrent=20,
        ...     burst_size=50,
        ... )

    Note:
        The token bucket algorithm allows bursting up to `burst_size`
        requests, then refills at `requests_per_second` rate.

    See Also:
        RateLimiterMiddleware: Uses this configuration.
        StepRateLimitState: Runtime state using this config.
    """

    requests_per_second: float = 0  # 0 = unlimited
    max_concurrent: int = 0  # 0 = unlimited
    burst_size: int = 1  # Allow small bursts
    wait_on_limit: bool = True  # Wait vs raise exception
    max_wait_seconds: float = 30.0  # Max wait time


@dataclass
class MiddlewareCircuitBreakerConfig:
    """
    Configuration for middleware circuit breaker behavior.

    Controls when circuits open (fail-fast) and how they recover.
    This config is optimized for middleware use with different field
    names from the standalone CircuitBreaker utility.

    Attributes:
        failure_threshold (int): Number of consecutive failures before
            the circuit opens. Default: 5.
        success_threshold (int): Number of consecutive successes needed
            in half-open state to close the circuit. Default: 2.
        recovery_timeout_seconds (float): Time to wait in open state
            before transitioning to half-open for testing. Default: 60.0.
        half_open_max_requests (int): Maximum requests to allow through
            in half-open state for testing recovery. Default: 1.

    Example:
        >>> # Conservative circuit breaker
        >>> config = MiddlewareCircuitBreakerConfig(
        ...     failure_threshold=3,           # Open after 3 failures
        ...     success_threshold=3,           # Need 3 successes to close
        ...     recovery_timeout_seconds=120,  # Wait 2 min before testing
        ...     half_open_max_requests=1,      # Test with 1 request
        ... )
        >>>
        >>> # Aggressive circuit breaker (for flaky services)
        >>> aggressive = MiddlewareCircuitBreakerConfig(
        ...     failure_threshold=2,           # Open quickly
        ...     success_threshold=5,           # Require more proof of recovery
        ...     recovery_timeout_seconds=30,   # Test sooner
        ... )

    Circuit Breaker States:
        - CLOSED: Normal operation, tracking failures
        - OPEN: Too many failures, rejecting all requests immediately
        - HALF_OPEN: Testing if service recovered, allowing limited requests

    See Also:
        CircuitBreakerMiddleware: Uses this configuration.
        CircuitBreakerState: Runtime state using this config.
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    recovery_timeout_seconds: float = 60.0
    half_open_max_requests: int = 1




@dataclass
class StepRateLimitState:
    """
    Runtime state for rate limiting a single step.

    Maintains the token bucket state, concurrency semaphore, and statistics
    for a rate-limited step. Thread-safe via asyncio primitives.

    Attributes:
        config (RateLimitConfig): The configuration for this step.
        tokens (float): Current number of available tokens in the bucket.
        last_refill (float): Monotonic time of last token refill.
        semaphore (asyncio.Semaphore | None): Concurrency control semaphore.
        lock (asyncio.Lock): Lock for thread-safe token operations.
        total_requests (int): Total requests processed.
        requests_limited (int): Requests that had to wait for rate limit.
        requests_rejected (int): Requests rejected due to timeout/no-wait.

    Example:
        >>> config = RateLimitConfig(requests_per_second=5, max_concurrent=3)
        >>> state = StepRateLimitState(config=config)
        >>> print(f"Available tokens: {state.tokens}")
        >>> print(f"Semaphore permits: {state.config.max_concurrent}")

    Note:
        This is an internal class. Users should interact with
        RateLimiterMiddleware rather than this state directly.

    See Also:
        RateLimitConfig: Configuration that creates this state.
        RateLimiterMiddleware: Manages state for all steps.
    """

    config: RateLimitConfig
    # Rate limiting state
    tokens: float = field(init=False)
    last_refill: float = field(default_factory=time.monotonic)
    semaphore: asyncio.Semaphore | None = field(init=False, default=None)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Statistics
    total_requests: int = 0
    requests_limited: int = 0
    requests_rejected: int = 0

    def __post_init__(self):
        """Initialize tokens and semaphore based on config."""
        self.tokens = float(self.config.burst_size)
        if self.config.max_concurrent > 0:
            self.semaphore = asyncio.Semaphore(self.config.max_concurrent)


@dataclass
class CircuitBreakerState:
    """
    Runtime state for a circuit breaker.

    Maintains the circuit state, failure/success counts, and statistics
    for a circuit-breaker-protected step. Thread-safe via asyncio primitives.

    Attributes:
        config (MiddlewareCircuitBreakerConfig): The configuration for this step.
        state (CircuitState): Current circuit state (CLOSED, OPEN, HALF_OPEN).
        failure_count (int): Current consecutive failure count.
        success_count (int): Current consecutive success count (in half-open).
        last_failure_time (datetime | None): When the last failure occurred.
        last_state_change (datetime): When the circuit state last changed.
        half_open_requests (int): Requests allowed through in half-open state.
        lock (asyncio.Lock): Lock for thread-safe state transitions.
        total_failures (int): Lifetime failure count.
        total_circuit_opens (int): Number of times circuit has opened.

    Example:
        >>> config = MiddlewareCircuitBreakerConfig(failure_threshold=5)
        >>> state = CircuitBreakerState(config=config)
        >>> print(f"Circuit state: {state.state.value}")  # "closed"
        >>> print(f"Failures: {state.failure_count}/{config.failure_threshold}")

    Note:
        This is an internal class. Users should interact with
        CircuitBreakerMiddleware rather than this state directly.

    See Also:
        MiddlewareCircuitBreakerConfig: Configuration that creates this state.
        CircuitBreakerMiddleware: Manages state for all steps.
    """

    config: MiddlewareCircuitBreakerConfig
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: datetime | None = None
    last_state_change: datetime = field(default_factory=datetime.utcnow)
    half_open_requests: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Statistics
    total_failures: int = 0
    total_circuit_opens: int = 0


class RateLimitExceededError(Exception):
    """
    Exception raised when a rate limit is exceeded.

    This exception is raised when `wait_on_limit=False` and the rate limit
    is hit, or when `max_wait_seconds` is exceeded while waiting.

    Attributes:
        step_name (str): Name of the step that was rate-limited.
        limit_type (str): Type of limit exceeded: "rate", "concurrency",
            "timeout", or "concurrency_timeout".
        message (str): Human-readable error message.

    Example:
        >>> try:
        ...     await middleware.before(ctx, "fetch_data")
        ... except RateLimitExceededError as e:
        ...     print(f"Rate limited on {e.step_name}: {e.limit_type}")
        ...     # Handle gracefully - maybe use cached data or skip

    See Also:
        RateLimiterMiddleware: Raises this exception.
        RateLimitConfig.wait_on_limit: Controls whether to raise or wait.
    """

    def __init__(self, step_name: str, limit_type: str, message: str):
        """
        Initialize the rate limit exceeded error.

        Args:
            step_name (str): Name of the rate-limited step.
            limit_type (str): Type of limit that was exceeded.
            message (str): Descriptive error message.
        """
        self.step_name = step_name
        self.limit_type = limit_type
        super().__init__(message)


class CircuitOpenError(Exception):
    """
    Exception raised when a circuit breaker is open.

    This exception is raised when attempting to execute a step whose
    circuit breaker is in the OPEN state, rejecting requests immediately.

    Attributes:
        step_name (str): Name of the step with open circuit.
        recovery_time (datetime | None): Estimated time when circuit will
            transition to half-open state for testing.

    Example:
        >>> try:
        ...     await middleware.before(ctx, "fetch_data")
        ... except CircuitOpenError as e:
        ...     print(f"Circuit open for {e.step_name}")
        ...     if e.recovery_time:
        ...         print(f"Recovery at: {e.recovery_time}")
        ...     # Use fallback data or return cached response

    See Also:
        CircuitBreakerMiddleware: Raises this exception.
        MiddlewareCircuitBreakerConfig.recovery_timeout_seconds: Controls recovery time.
    """

    def __init__(self, step_name: str, recovery_time: datetime | None = None):
        """
        Initialize the circuit open error.

        Args:
            step_name (str): Name of the step with open circuit.
            recovery_time (datetime | None): When recovery testing begins.
        """
        self.step_name = step_name
        self.recovery_time = recovery_time
        message = f"Circuit breaker open for step '{step_name}'"
        if recovery_time:
            message += f", recovery at {recovery_time.isoformat()}"
        super().__init__(message)


class RateLimiterMiddleware(Middleware):
    """
    Middleware for per-step rate limiting and concurrency control.

    Implements a token bucket algorithm for rate limiting combined with
    semaphore-based concurrency control. Supports configurable wait vs.
    reject behavior when limits are exceeded.

    Attributes:
        _step_configs (dict[str, RateLimitConfig]): Per-step configurations.
        _default_config (RateLimitConfig | None): Default config for unlisted steps.
        _states (dict[str, StepRateLimitState]): Runtime state per step.

    Methods:
        before(): Apply rate limiting before step execution.
        after(): Release concurrency semaphore after completion.
        on_error(): Release semaphore on error.
        get_stats(): Get rate limiting statistics for all steps.

    Example:
        >>> from agentorchestrator.middleware import RateLimiterMiddleware, RateLimitConfig
        >>>
        >>> # Configure per-step limits
        >>> rate_limiter = RateLimiterMiddleware({
        ...     "fetch_news_data": RateLimitConfig(
        ...         requests_per_second=5,
        ...         max_concurrent=3,
        ...     ),
        ...     "fetch_sec_data": RateLimitConfig(
        ...         requests_per_second=10,
        ...         max_concurrent=5,
        ...     ),
        ... })
        >>> ao.use(rate_limiter)
        >>>
        >>> # Or with defaults for all data fetch steps
        >>> rate_limiter = RateLimiterMiddleware(
        ...     default_config=RateLimitConfig(requests_per_second=10),
        ...     step_configs={
        ...         "fetch_news_data": RateLimitConfig(requests_per_second=5),
        ...     },
        ... )
        >>>
        >>> # Check statistics
        >>> stats = rate_limiter.get_stats()
        >>> for step, data in stats.items():
        ...     print(f"{step}: {data['total_requests']} requests, "
        ...           f"{data['requests_limited']} limited")

    Token Bucket Algorithm:
        - Bucket starts with `burst_size` tokens
        - Each request consumes 1 token
        - Tokens refill at `requests_per_second` rate
        - When bucket is empty, requests wait or are rejected

    See Also:
        RateLimitConfig: Configuration options.
        RateLimitExceededError: Exception when limits exceeded.
        CircuitBreakerMiddleware: Complementary protection.
    """

    def __init__(
        self,
        step_configs: dict[str, RateLimitConfig] | None = None,
        default_config: RateLimitConfig | None = None,
        priority: int = 10,  # Run early
    ):
        """
        Initialize the rate limiter middleware.

        Args:
            step_configs (dict[str, RateLimitConfig] | None): Per-step rate
                limit configurations. Keys are step names, values are configs.
                Default: None (no per-step configs).
            default_config (RateLimitConfig | None): Default configuration
                applied to steps not in step_configs. If None, steps without
                explicit config are not rate-limited. Default: None.
            priority (int): Middleware priority (lower = earlier execution).
                Default: 10 (run early to limit before execution).

        Example:
            >>> # Per-step only
            >>> middleware = RateLimiterMiddleware({
            ...     "fetch_news": RateLimitConfig(requests_per_second=5),
            ... })
            >>>
            >>> # With defaults
            >>> middleware = RateLimiterMiddleware(
            ...     default_config=RateLimitConfig(requests_per_second=10),
            ...     step_configs={"slow_api": RateLimitConfig(requests_per_second=1)},
            ... )
        """
        super().__init__(priority=priority)
        self._step_configs = step_configs or {}
        self._default_config = default_config
        self._states: dict[str, StepRateLimitState] = {}
        self._lock = asyncio.Lock()

    async def _get_state(self, step_name: str) -> StepRateLimitState | None:
        """
        Get or create rate limit state for a step.

        Args:
            step_name (str): Name of the step.

        Returns:
            StepRateLimitState | None: State if step has config, None otherwise.
        """
        async with self._lock:
            if step_name in self._states:
                return self._states[step_name]

            # Check if we have config for this step
            config = self._step_configs.get(step_name, self._default_config)
            if config is None:
                return None

            state = StepRateLimitState(config=config)
            self._states[step_name] = state
            return state

    async def _refill_tokens(self, state: StepRateLimitState) -> None:
        """
        Refill tokens based on elapsed time (token bucket algorithm).

        Args:
            state (StepRateLimitState): State to refill tokens for.
        """
        if state.config.requests_per_second <= 0:
            return

        now = time.monotonic()
        elapsed = now - state.last_refill
        refill = elapsed * state.config.requests_per_second

        state.tokens = min(
            state.tokens + refill,
            float(state.config.burst_size),
        )
        state.last_refill = now

    async def _acquire_rate_limit(self, step_name: str, state: StepRateLimitState) -> None:
        """
        Acquire a rate limit token, waiting if necessary.

        Args:
            step_name (str): Name of the step acquiring the token.
            state (StepRateLimitState): Rate limit state for the step.

        Raises:
            RateLimitExceededError: If rate limit exceeded and cannot wait.
        """
        if state.config.requests_per_second <= 0:
            return

        start_time = time.monotonic()
        max_wait = state.config.max_wait_seconds

        async with state.lock:
            while True:
                await self._refill_tokens(state)

                if state.tokens >= 1.0:
                    state.tokens -= 1.0
                    state.total_requests += 1
                    return

                # Need to wait
                state.requests_limited += 1

                if not state.config.wait_on_limit:
                    state.requests_rejected += 1
                    raise RateLimitExceededError(
                        step_name=step_name,
                        limit_type="rate",
                        message=f"Rate limit exceeded for '{step_name}' "
                                f"({state.config.requests_per_second} req/s)",
                    )

                # Check max wait
                elapsed = time.monotonic() - start_time
                if max_wait > 0 and elapsed >= max_wait:
                    state.requests_rejected += 1
                    raise RateLimitExceededError(
                        step_name=step_name,
                        limit_type="timeout",
                        message=f"Rate limit wait timeout for '{step_name}' "
                                f"after {elapsed:.1f}s",
                    )

                # Calculate wait time until next token
                wait_time = (1.0 - state.tokens) / state.config.requests_per_second
                wait_time = min(wait_time, 0.1)  # Check frequently

                logger.debug(
                    f"Rate limit: waiting {wait_time:.3f}s for step '{step_name}'"
                )

                # Release lock while waiting
                state.lock.release()
                try:
                    await asyncio.sleep(wait_time)
                finally:
                    await state.lock.acquire()

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Apply rate limiting before step execution.

        Acquires a rate limit token and concurrency semaphore permit
        before allowing the step to execute.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step about to execute.

        Raises:
            RateLimitExceededError: If rate limit exceeded and wait_on_limit=False
                or if max_wait_seconds is exceeded.

        Example:
            >>> # Rate limiter automatically applied via middleware
            >>> @ao.step
            ... async def fetch_news(ctx):
            ...     # This will be rate-limited automatically
            ...     return await api.fetch()
        """
        state = await self._get_state(step_name)
        if state is None:
            return

        # Acquire rate limit token
        await self._acquire_rate_limit(step_name, state)

        # Acquire concurrency semaphore
        if state.semaphore is not None:
            try:
                if state.config.wait_on_limit:
                    await asyncio.wait_for(
                        state.semaphore.acquire(),
                        timeout=state.config.max_wait_seconds or None,
                    )
                else:
                    acquired = state.semaphore.locked()
                    if not acquired:
                        await state.semaphore.acquire()
                    else:
                        raise RateLimitExceededError(
                            step_name=step_name,
                            limit_type="concurrency",
                            message=f"Concurrency limit exceeded for '{step_name}' "
                                    f"({state.config.max_concurrent} concurrent)",
                        )
            except asyncio.TimeoutError:
                raise RateLimitExceededError(
                    step_name=step_name,
                    limit_type="concurrency_timeout",
                    message=f"Concurrency wait timeout for '{step_name}'",
                )

            # Store flag to release in after()
            ctx.set(f"_rate_limit_semaphore_{step_name}", True)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Release concurrency semaphore after step completion.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that executed.
            result (StepResult): The step's execution result.
        """
        state = await self._get_state(step_name)
        if state is None:
            return

        # Release semaphore if we acquired it
        if ctx.get(f"_rate_limit_semaphore_{step_name}"):
            if state.semaphore is not None:
                state.semaphore.release()
            ctx.delete(f"_rate_limit_semaphore_{step_name}")

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """
        Release semaphore on error to prevent deadlock.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that failed.
            error (Exception): The exception that was raised.
        """
        await self.after(ctx, step_name, StepResult(step_name=step_name, output=None, duration_ms=0))

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """
        Get rate limiting statistics for all steps.

        Returns:
            dict[str, dict[str, Any]]: Mapping of step names to statistics:
                - total_requests: Total requests processed
                - requests_limited: Requests that had to wait
                - requests_rejected: Requests rejected due to limits
                - current_tokens: Current available tokens

        Example:
            >>> stats = rate_limiter.get_stats()
            >>> for step, data in stats.items():
            ...     print(f"{step}:")
            ...     print(f"  Total: {data['total_requests']}")
            ...     print(f"  Limited: {data['requests_limited']}")
            ...     print(f"  Rejected: {data['requests_rejected']}")
        """
        return {
            step_name: {
                "total_requests": state.total_requests,
                "requests_limited": state.requests_limited,
                "requests_rejected": state.requests_rejected,
                "current_tokens": state.tokens,
            }
            for step_name, state in self._states.items()
        }


class CircuitBreakerMiddleware(Middleware):
    """
    Middleware for circuit breaker pattern implementation.

    Provides graceful degradation by failing fast when a step is
    experiencing repeated failures, preventing cascade failures and
    giving the underlying service time to recover.

    Attributes:
        _step_configs (dict[str, MiddlewareCircuitBreakerConfig]): Per-step configs.
        _default_config (MiddlewareCircuitBreakerConfig | None): Default config.
        _states (dict[str, CircuitBreakerState]): Runtime state per step.
        _on_circuit_open (Callable[[str], None] | None): Callback when circuit opens.

    Methods:
        before(): Check circuit state before step execution.
        after(): Record success after step completion.
        on_error(): Record failure on step error.
        get_circuit_states(): Get circuit breaker states for all steps.
        reset_circuit(): Manually reset a circuit breaker.

    Circuit States:
        - CLOSED: Normal operation, tracking failures
        - OPEN: Too many failures, rejecting requests immediately
        - HALF_OPEN: Testing if service recovered

    Example:
        >>> from agentorchestrator.middleware import (
        ...     CircuitBreakerMiddleware,
        ...     MiddlewareCircuitBreakerConfig,
        ... )
        >>>
        >>> def on_circuit_open(step_name: str):
        ...     alert_team(f"Circuit opened for {step_name}!")
        >>>
        >>> circuit_breaker = CircuitBreakerMiddleware(
        ...     step_configs={
        ...         "fetch_news_data": MiddlewareCircuitBreakerConfig(
        ...             failure_threshold=5,
        ...             recovery_timeout_seconds=60,
        ...         ),
        ...     },
        ...     on_circuit_open=on_circuit_open,
        ... )
        >>> ao.use(circuit_breaker)
        >>>
        >>> # Check circuit states
        >>> states = circuit_breaker.get_circuit_states()
        >>> for step, state in states.items():
        ...     print(f"{step}: {state['state']}")
        >>>
        >>> # Manual reset after fixing the issue
        >>> circuit_breaker.reset_circuit("fetch_news_data")

    State Transitions:
        CLOSED -> OPEN: After `failure_threshold` consecutive failures
        OPEN -> HALF_OPEN: After `recovery_timeout_seconds` elapsed
        HALF_OPEN -> CLOSED: After `success_threshold` consecutive successes
        HALF_OPEN -> OPEN: After any failure in half-open state

    See Also:
        MiddlewareCircuitBreakerConfig: Configuration options.
        CircuitOpenError: Exception when circuit is open.
        RateLimiterMiddleware: Complementary protection.
    """

    def __init__(
        self,
        step_configs: dict[str, MiddlewareCircuitBreakerConfig] | None = None,
        default_config: MiddlewareCircuitBreakerConfig | None = None,
        priority: int = 5,  # Run very early
        on_circuit_open: Callable[[str], None] | None = None,
    ):
        """
        Initialize the circuit breaker middleware.

        Args:
            step_configs (dict[str, MiddlewareCircuitBreakerConfig] | None):
                Per-step circuit breaker configurations. Keys are step names,
                values are configs. Default: None.
            default_config (MiddlewareCircuitBreakerConfig | None): Default
                configuration for steps not in step_configs. If None, steps
                without explicit config have no circuit breaker. Default: None.
            priority (int): Middleware priority (lower = earlier execution).
                Default: 5 (run very early to fail fast).
            on_circuit_open (Callable[[str], None] | None): Callback function
                called when a circuit opens. Receives step name as argument.
                Use for alerting/monitoring. Default: None.

        Example:
            >>> middleware = CircuitBreakerMiddleware(
            ...     step_configs={
            ...         "external_api": MiddlewareCircuitBreakerConfig(
            ...             failure_threshold=3,
            ...             recovery_timeout_seconds=30,
            ...         ),
            ...     },
            ...     on_circuit_open=lambda step: send_alert(step),
            ... )
        """
        super().__init__(priority=priority)
        self._step_configs = step_configs or {}
        self._default_config = default_config
        self._states: dict[str, CircuitBreakerState] = {}
        self._lock = asyncio.Lock()
        self._on_circuit_open = on_circuit_open

    async def _get_state(self, step_name: str) -> CircuitBreakerState | None:
        """
        Get or create circuit breaker state for a step.

        Args:
            step_name (str): Name of the step.

        Returns:
            CircuitBreakerState | None: State if step has config, None otherwise.
        """
        async with self._lock:
            if step_name in self._states:
                return self._states[step_name]

            config = self._step_configs.get(step_name, self._default_config)
            if config is None:
                return None

            state = CircuitBreakerState(config=config)
            self._states[step_name] = state
            return state

    async def _check_circuit(self, step_name: str, state: CircuitBreakerState) -> None:
        """
        Check if circuit allows request, transitioning states if needed.

        Args:
            step_name (str): Name of the step.
            state (CircuitBreakerState): Circuit breaker state.

        Raises:
            CircuitOpenError: If circuit is open and not ready for recovery.
        """
        async with state.lock:
            now = datetime.utcnow()

            if state.state == CircuitState.CLOSED:
                # Normal operation
                return

            if state.state == CircuitState.OPEN:
                # Check if recovery timeout elapsed
                if state.last_failure_time:
                    recovery_time = state.last_failure_time + timedelta(
                        seconds=state.config.recovery_timeout_seconds
                    )
                    if now >= recovery_time:
                        # Transition to half-open
                        logger.info(
                            f"Circuit breaker for '{step_name}' transitioning to HALF_OPEN"
                        )
                        state.state = CircuitState.HALF_OPEN
                        state.half_open_requests = 0
                        state.last_state_change = now
                    else:
                        # Still open
                        raise CircuitOpenError(step_name, recovery_time)
                else:
                    raise CircuitOpenError(step_name)

            if state.state == CircuitState.HALF_OPEN:
                # Allow limited requests
                if state.half_open_requests >= state.config.half_open_max_requests:
                    raise CircuitOpenError(step_name)
                state.half_open_requests += 1

    async def _record_success(self, step_name: str, state: CircuitBreakerState) -> None:
        """
        Record a successful request and potentially close the circuit.

        Args:
            step_name (str): Name of the step.
            state (CircuitBreakerState): Circuit breaker state.
        """
        async with state.lock:
            now = datetime.utcnow()

            if state.state == CircuitState.HALF_OPEN:
                state.success_count += 1
                if state.success_count >= state.config.success_threshold:
                    # Transition to closed
                    logger.info(f"Circuit breaker for '{step_name}' CLOSED (recovered)")
                    state.state = CircuitState.CLOSED
                    state.failure_count = 0
                    state.success_count = 0
                    state.last_state_change = now
            elif state.state == CircuitState.CLOSED:
                # Reset failure count on success
                state.failure_count = 0

    async def _record_failure(self, step_name: str, state: CircuitBreakerState) -> None:
        """
        Record a failed request and potentially open the circuit.

        Args:
            step_name (str): Name of the step.
            state (CircuitBreakerState): Circuit breaker state.
        """
        async with state.lock:
            now = datetime.utcnow()
            state.failure_count += 1
            state.success_count = 0
            state.last_failure_time = now
            state.total_failures += 1

            if state.state == CircuitState.HALF_OPEN:
                # Transition back to open
                logger.warning(f"Circuit breaker for '{step_name}' OPEN (failed in half-open)")
                state.state = CircuitState.OPEN
                state.last_state_change = now
                state.total_circuit_opens += 1
                if self._on_circuit_open:
                    self._on_circuit_open(step_name)

            elif state.state == CircuitState.CLOSED:
                if state.failure_count >= state.config.failure_threshold:
                    # Transition to open
                    logger.warning(
                        f"Circuit breaker for '{step_name}' OPEN "
                        f"(failures: {state.failure_count}/{state.config.failure_threshold})"
                    )
                    state.state = CircuitState.OPEN
                    state.last_state_change = now
                    state.total_circuit_opens += 1
                    if self._on_circuit_open:
                        self._on_circuit_open(step_name)

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Check circuit state before step execution.

        If the circuit is open, raises CircuitOpenError to fail fast.
        If the circuit is half-open, allows limited requests through.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step about to execute.

        Raises:
            CircuitOpenError: If circuit is open and rejecting requests.

        Example:
            >>> # Circuit breaker automatically applied via middleware
            >>> @ao.step
            ... async def fetch_external(ctx):
            ...     # If circuit is open, this won't execute
            ...     return await external_api.call()
        """
        state = await self._get_state(step_name)
        if state is None:
            return

        await self._check_circuit(step_name, state)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Record success after step completion.

        Updates circuit breaker statistics and potentially closes
        the circuit if in half-open state.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that executed.
            result (StepResult): The step's execution result.
        """
        state = await self._get_state(step_name)
        if state is None:
            return

        if result.success:
            await self._record_success(step_name, state)

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """
        Record failure on step error.

        Updates circuit breaker statistics and potentially opens
        the circuit if failure threshold is reached.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that failed.
            error (Exception): The exception that was raised.
        """
        state = await self._get_state(step_name)
        if state is None:
            return

        await self._record_failure(step_name, state)

    def get_circuit_states(self) -> dict[str, dict[str, Any]]:
        """
        Get circuit breaker states for all protected steps.

        Returns:
            dict[str, dict[str, Any]]: Mapping of step names to state info:
                - state: Current circuit state ("closed", "open", "half_open")
                - failure_count: Current consecutive failure count
                - success_count: Current consecutive success count
                - total_failures: Lifetime failure count
                - total_circuit_opens: Number of times circuit has opened
                - last_failure: ISO timestamp of last failure

        Example:
            >>> states = circuit_breaker.get_circuit_states()
            >>> for step, state in states.items():
            ...     if state['state'] == 'open':
            ...         print(f"WARNING: {step} circuit is open!")
            ...         print(f"  Last failure: {state['last_failure']}")
        """
        return {
            step_name: {
                "state": state.state.value,
                "failure_count": state.failure_count,
                "success_count": state.success_count,
                "total_failures": state.total_failures,
                "total_circuit_opens": state.total_circuit_opens,
                "last_failure": state.last_failure_time.isoformat() if state.last_failure_time else None,
            }
            for step_name, state in self._states.items()
        }

    def reset_circuit(self, step_name: str) -> bool:
        """
        Manually reset a circuit breaker to closed state.

        Use this after fixing the underlying issue to allow requests
        to flow through immediately rather than waiting for recovery.

        Args:
            step_name (str): Name of the step whose circuit to reset.

        Returns:
            bool: True if circuit was reset, False if step not found.

        Example:
            >>> # After fixing the external service
            >>> if circuit_breaker.reset_circuit("fetch_external_api"):
            ...     print("Circuit reset successfully")
            ... else:
            ...     print("Step not found")
        """
        if step_name not in self._states:
            return False

        state = self._states[step_name]
        state.state = CircuitState.CLOSED
        state.failure_count = 0
        state.success_count = 0
        state.last_state_change = datetime.utcnow()
        logger.info(f"Circuit breaker for '{step_name}' manually reset to CLOSED")
        return True


class RateLimitAndCircuitBreakerMiddleware(Middleware):
    """
    Combined rate limiting and circuit breaker middleware.

    A convenience class that combines both RateLimiterMiddleware and
    CircuitBreakerMiddleware into a single middleware, providing
    comprehensive protection for external API calls.

    Execution order: Circuit breaker checks first (fail fast), then rate limiting.

    Attributes:
        _circuit_breaker (CircuitBreakerMiddleware): Circuit breaker component.
        _rate_limiter (RateLimiterMiddleware): Rate limiter component.

    Methods:
        before(): Apply circuit breaker then rate limiting.
        after(): Release resources and record success.
        on_error(): Release resources and record failure.
        get_stats(): Get combined statistics from both components.

    Example:
        >>> from agentorchestrator.middleware import (
        ...     RateLimitAndCircuitBreakerMiddleware,
        ...     RateLimitConfig,
        ...     MiddlewareCircuitBreakerConfig,
        ... )
        >>>
        >>> protection = RateLimitAndCircuitBreakerMiddleware(
        ...     rate_limits={
        ...         "fetch_news_data": RateLimitConfig(
        ...             requests_per_second=5,
        ...             max_concurrent=3,
        ...         ),
        ...         "fetch_sec_data": RateLimitConfig(
        ...             requests_per_second=10,
        ...             max_concurrent=5,
        ...         ),
        ...     },
        ...     circuit_breakers={
        ...         "fetch_news_data": MiddlewareCircuitBreakerConfig(
        ...             failure_threshold=5,
        ...             recovery_timeout_seconds=60,
        ...         ),
        ...     },
        ...     default_rate_limit=RateLimitConfig(requests_per_second=20),
        ... )
        >>> ao.use(protection)
        >>>
        >>> # Get combined statistics
        >>> stats = protection.get_stats()
        >>> print(f"Rate limits: {stats['rate_limits']}")
        >>> print(f"Circuit breakers: {stats['circuit_breakers']}")

    See Also:
        RateLimiterMiddleware: Standalone rate limiting.
        CircuitBreakerMiddleware: Standalone circuit breaker.
        RateLimitConfig: Rate limit configuration.
        MiddlewareCircuitBreakerConfig: Circuit breaker configuration.
    """

    def __init__(
        self,
        rate_limits: dict[str, RateLimitConfig] | None = None,
        circuit_breakers: dict[str, MiddlewareCircuitBreakerConfig] | None = None,
        default_rate_limit: RateLimitConfig | None = None,
        default_circuit_breaker: MiddlewareCircuitBreakerConfig | None = None,
        priority: int = 5,
    ):
        """
        Initialize combined rate limiting and circuit breaker middleware.

        Args:
            rate_limits (dict[str, RateLimitConfig] | None): Per-step rate
                limit configurations. Default: None.
            circuit_breakers (dict[str, MiddlewareCircuitBreakerConfig] | None):
                Per-step circuit breaker configurations. Default: None.
            default_rate_limit (RateLimitConfig | None): Default rate limit
                for steps without explicit config. Default: None.
            default_circuit_breaker (MiddlewareCircuitBreakerConfig | None):
                Default circuit breaker config. Default: None.
            priority (int): Middleware priority. Default: 5.

        Example:
            >>> middleware = RateLimitAndCircuitBreakerMiddleware(
            ...     rate_limits={"api_call": RateLimitConfig(requests_per_second=5)},
            ...     circuit_breakers={"api_call": MiddlewareCircuitBreakerConfig()},
            ... )
        """
        super().__init__(priority=priority)
        self._circuit_breaker = CircuitBreakerMiddleware(
            step_configs=circuit_breakers,
            default_config=default_circuit_breaker,
            priority=priority,
        )
        self._rate_limiter = RateLimiterMiddleware(
            step_configs=rate_limits,
            default_config=default_rate_limit,
            priority=priority + 1,
        )

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Apply circuit breaker then rate limiting before step execution.

        Circuit breaker is checked first for fail-fast behavior,
        then rate limiting is applied.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step about to execute.

        Raises:
            CircuitOpenError: If circuit is open.
            RateLimitExceededError: If rate limit exceeded.
        """
        await self._circuit_breaker.before(ctx, step_name)
        await self._rate_limiter.before(ctx, step_name)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Release resources and record success after step completion.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that executed.
            result (StepResult): The step's execution result.
        """
        await self._rate_limiter.after(ctx, step_name, result)
        await self._circuit_breaker.after(ctx, step_name, result)

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """
        Release resources and record failure on step error.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that failed.
            error (Exception): The exception that was raised.
        """
        await self._rate_limiter.on_error(ctx, step_name, error)
        await self._circuit_breaker.on_error(ctx, step_name, error)

    def get_stats(self) -> dict[str, Any]:
        """
        Get combined statistics from both rate limiter and circuit breaker.

        Returns:
            dict[str, Any]: Combined statistics with two keys:
                - rate_limits: Statistics from RateLimiterMiddleware
                - circuit_breakers: States from CircuitBreakerMiddleware

        Example:
            >>> stats = protection.get_stats()
            >>> # Rate limit stats per step
            >>> for step, data in stats['rate_limits'].items():
            ...     print(f"{step}: {data['total_requests']} requests")
            >>> # Circuit breaker states
            >>> for step, state in stats['circuit_breakers'].items():
            ...     print(f"{step}: {state['state']}")
        """
        return {
            "rate_limits": self._rate_limiter.get_stats(),
            "circuit_breakers": self._circuit_breaker.get_circuit_states(),
        }