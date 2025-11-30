"""
FlowForge Rate Limiting & Circuit Breaker Middleware

Provides per-agent rate limiting, concurrency control, and circuit breaker
functionality to prevent overwhelming external APIs.

Features:
- Per-step/agent rate limiting (requests per second)
- Per-step/agent concurrency limits
- Circuit breaker with automatic recovery
- Configurable retry behavior when limits hit
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from flowforge.core.context import ChainContext, StepResult
from flowforge.middleware.base import Middleware

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class RateLimitConfig:
    """
    Rate limit configuration for a step/agent.

    Attributes:
        requests_per_second: Max requests per second (0 = unlimited)
        max_concurrent: Max concurrent requests (0 = unlimited)
        burst_size: Allow burst up to this size before rate limiting kicks in
        wait_on_limit: If True, wait when limit hit. If False, raise exception.
        max_wait_seconds: Maximum time to wait for rate limit (0 = wait forever)
    """
    requests_per_second: float = 0  # 0 = unlimited
    max_concurrent: int = 0  # 0 = unlimited
    burst_size: int = 1  # Allow small bursts
    wait_on_limit: bool = True  # Wait vs raise exception
    max_wait_seconds: float = 30.0  # Max wait time


@dataclass
class CircuitBreakerConfig:
    """
    Circuit breaker configuration.

    Attributes:
        failure_threshold: Number of consecutive failures to open circuit
        success_threshold: Number of consecutive successes to close circuit
        recovery_timeout_seconds: Time to wait before testing recovery
        half_open_max_requests: Max requests to allow in half-open state
    """
    failure_threshold: int = 5
    success_threshold: int = 2
    recovery_timeout_seconds: float = 60.0
    half_open_max_requests: int = 1


@dataclass
class StepRateLimitState:
    """
    Runtime state for rate limiting a single step/agent.

    Thread-safe via asyncio primitives.
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
        self.tokens = float(self.config.burst_size)
        if self.config.max_concurrent > 0:
            self.semaphore = asyncio.Semaphore(self.config.max_concurrent)


@dataclass
class CircuitBreakerState:
    """
    Runtime state for a circuit breaker.

    Thread-safe via asyncio primitives.
    """
    config: CircuitBreakerConfig
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
    """Raised when rate limit is exceeded and wait_on_limit is False"""

    def __init__(self, step_name: str, limit_type: str, message: str):
        self.step_name = step_name
        self.limit_type = limit_type
        super().__init__(message)


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open"""

    def __init__(self, step_name: str, recovery_time: datetime | None = None):
        self.step_name = step_name
        self.recovery_time = recovery_time
        message = f"Circuit breaker open for step '{step_name}'"
        if recovery_time:
            message += f", recovery at {recovery_time.isoformat()}"
        super().__init__(message)


class RateLimiterMiddleware(Middleware):
    """
    Rate limiting middleware with per-step configuration.

    Provides token bucket rate limiting and semaphore-based concurrency control.

    Usage:
        # Configure per-step limits
        rate_limiter = RateLimiterMiddleware({
            "fetch_news_data": RateLimitConfig(
                requests_per_second=5,
                max_concurrent=3,
            ),
            "fetch_sec_data": RateLimitConfig(
                requests_per_second=10,
                max_concurrent=5,
            ),
        })
        forge.use(rate_limiter)

        # Or with defaults for all data fetch steps
        rate_limiter = RateLimiterMiddleware(
            default_config=RateLimitConfig(requests_per_second=10),
            step_configs={
                "fetch_news_data": RateLimitConfig(requests_per_second=5),
            },
        )
    """

    def __init__(
        self,
        step_configs: dict[str, RateLimitConfig] | None = None,
        default_config: RateLimitConfig | None = None,
        priority: int = 10,  # Run early
    ):
        """
        Initialize rate limiter middleware.

        Args:
            step_configs: Per-step rate limit configurations
            default_config: Default config for steps not in step_configs
            priority: Middleware priority (lower = earlier)
        """
        super().__init__(priority=priority)
        self._step_configs = step_configs or {}
        self._default_config = default_config
        self._states: dict[str, StepRateLimitState] = {}
        self._lock = asyncio.Lock()

    async def _get_state(self, step_name: str) -> StepRateLimitState | None:
        """Get or create rate limit state for a step."""
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
        """Refill tokens based on elapsed time (token bucket algorithm)."""
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
        """Acquire a rate limit token, waiting if necessary."""
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
        """Apply rate limiting before step execution."""
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
        """Release concurrency semaphore after step completion."""
        state = await self._get_state(step_name)
        if state is None:
            return

        # Release semaphore if we acquired it
        if ctx.get(f"_rate_limit_semaphore_{step_name}"):
            if state.semaphore is not None:
                state.semaphore.release()
            ctx.delete(f"_rate_limit_semaphore_{step_name}")

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """Release semaphore on error."""
        await self.after(ctx, step_name, StepResult(step_name=step_name, output=None, duration_ms=0))

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Get rate limiting statistics for all steps."""
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
    Circuit breaker middleware for graceful degradation.

    Prevents overwhelming failing services by:
    1. CLOSED: Normal operation, tracking failures
    2. OPEN: Too many failures, reject requests immediately
    3. HALF_OPEN: Testing if service recovered

    Usage:
        circuit_breaker = CircuitBreakerMiddleware({
            "fetch_news_data": CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout_seconds=60,
            ),
        })
        forge.use(circuit_breaker)
    """

    def __init__(
        self,
        step_configs: dict[str, CircuitBreakerConfig] | None = None,
        default_config: CircuitBreakerConfig | None = None,
        priority: int = 5,  # Run very early
        on_circuit_open: Callable[[str], None] | None = None,
    ):
        """
        Initialize circuit breaker middleware.

        Args:
            step_configs: Per-step circuit breaker configurations
            default_config: Default config for steps not in step_configs
            priority: Middleware priority (lower = earlier)
            on_circuit_open: Callback when circuit opens (for alerting)
        """
        super().__init__(priority=priority)
        self._step_configs = step_configs or {}
        self._default_config = default_config
        self._states: dict[str, CircuitBreakerState] = {}
        self._lock = asyncio.Lock()
        self._on_circuit_open = on_circuit_open

    async def _get_state(self, step_name: str) -> CircuitBreakerState | None:
        """Get or create circuit breaker state for a step."""
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
        """Check if circuit allows request, transition states if needed."""
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
        """Record successful request."""
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
        """Record failed request."""
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
        """Check circuit state before step execution."""
        state = await self._get_state(step_name)
        if state is None:
            return

        await self._check_circuit(step_name, state)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Record success after step completion."""
        state = await self._get_state(step_name)
        if state is None:
            return

        if result.success:
            await self._record_success(step_name, state)

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """Record failure on step error."""
        state = await self._get_state(step_name)
        if state is None:
            return

        await self._record_failure(step_name, state)

    def get_circuit_states(self) -> dict[str, dict[str, Any]]:
        """Get circuit breaker states for all steps."""
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
        """Manually reset a circuit breaker to closed state."""
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

    Convenience class that combines both protections in one middleware.

    Usage:
        protection = RateLimitAndCircuitBreakerMiddleware(
            rate_limits={
                "fetch_news_data": RateLimitConfig(requests_per_second=5),
                "fetch_sec_data": RateLimitConfig(requests_per_second=10),
            },
            circuit_breakers={
                "fetch_news_data": CircuitBreakerConfig(failure_threshold=5),
            },
        )
        forge.use(protection)
    """

    def __init__(
        self,
        rate_limits: dict[str, RateLimitConfig] | None = None,
        circuit_breakers: dict[str, CircuitBreakerConfig] | None = None,
        default_rate_limit: RateLimitConfig | None = None,
        default_circuit_breaker: CircuitBreakerConfig | None = None,
        priority: int = 5,
    ):
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
        """Apply circuit breaker then rate limiting."""
        await self._circuit_breaker.before(ctx, step_name)
        await self._rate_limiter.before(ctx, step_name)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Record success/release resources."""
        await self._rate_limiter.after(ctx, step_name, result)
        await self._circuit_breaker.after(ctx, step_name, result)

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """Record failure/release resources."""
        await self._rate_limiter.on_error(ctx, step_name, error)
        await self._circuit_breaker.on_error(ctx, step_name, error)

    def get_stats(self) -> dict[str, Any]:
        """Get combined statistics."""
        return {
            "rate_limits": self._rate_limiter.get_stats(),
            "circuit_breakers": self._circuit_breaker.get_circuit_states(),
        }
