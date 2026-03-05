"""
Tests for Middleware - Rate Limiter and Circuit Breaker
========================================================

Tests resilience patterns in middleware.
"""

import asyncio
import pytest
import time
from unittest.mock import MagicMock, AsyncMock

try:
    from agentorchestrator.middleware.rate_limiter import (
        RateLimiterMiddleware,
        RateLimitConfig,
    )
    from agentorchestrator.middleware.circuit_breaker import (
        CircuitBreakerMiddleware,
        MiddlewareCircuitBreakerConfig,
    )
    from agentorchestrator.core.context import ChainContext, StepResult
    MIDDLEWARE_AVAILABLE = True
except ImportError:
    MIDDLEWARE_AVAILABLE = False


pytestmark = pytest.mark.skipif(not MIDDLEWARE_AVAILABLE, reason="Middleware not available")


class TestRateLimiterMiddleware:
    """Tests for rate limiting middleware."""

    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self):
        """Test requests within rate limit are allowed."""
        middleware = RateLimiterMiddleware({
            "test_step": {"requests_per_second": 10},
        })
        
        ctx = ChainContext(request_id="test")
        
        # Should allow 10 requests quickly
        for _ in range(10):
            await middleware.before(ctx, "test_step")

    @pytest.mark.asyncio
    async def test_throttles_requests_over_limit(self):
        """Test requests over rate limit are delayed."""
        middleware = RateLimiterMiddleware({
            "test_step": {"requests_per_second": 5},
        })
        
        ctx = ChainContext(request_id="test")
        
        start = time.time()
        
        # Make 10 requests (should throttle after 5)
        for _ in range(6):
            await middleware.before(ctx, "test_step")
        
        elapsed = time.time() - start
        
        # Should have been delayed (at least some time)
        # With 5 RPS, 6th request needs to wait ~0.2s
        assert elapsed >= 0.1

    @pytest.mark.asyncio
    async def test_no_limit_for_unconfigured_step(self):
        """Test steps without config are not rate limited."""
        middleware = RateLimiterMiddleware({
            "other_step": {"requests_per_second": 1},
        })
        
        ctx = ChainContext(request_id="test")
        
        # Should not throttle unconfigured step
        start = time.time()
        for _ in range(100):
            await middleware.before(ctx, "unconfigured_step")
        elapsed = time.time() - start
        
        # Should be very fast (no throttling)
        assert elapsed < 0.5


class TestCircuitBreakerMiddleware:
    """Tests for circuit breaker middleware."""

    @pytest.mark.asyncio
    async def test_closed_state_allows_requests(self):
        """Test closed circuit allows requests."""
        middleware = CircuitBreakerMiddleware({
            "test_step": MiddlewareCircuitBreakerConfig(
                failure_threshold=3,
                reset_timeout=10,
            ),
        })
        
        ctx = ChainContext(request_id="test")
        result = StepResult(step_name="test_step", output={}, duration_ms=100)
        
        # Should allow request
        await middleware.before(ctx, "test_step")
        await middleware.after(ctx, "test_step", result)

    @pytest.mark.asyncio
    async def test_opens_after_failures(self):
        """Test circuit opens after threshold failures."""
        middleware = CircuitBreakerMiddleware({
            "test_step": MiddlewareCircuitBreakerConfig(
                failure_threshold=3,
                reset_timeout=60,
            ),
        })
        
        ctx = ChainContext(request_id="test")
        
        # Simulate failures
        for _ in range(3):
            await middleware.before(ctx, "test_step")
            await middleware.on_error(ctx, "test_step", Exception("fail"))
        
        # Circuit should be open now
        with pytest.raises(Exception):  # Should raise circuit open error
            await middleware.before(ctx, "test_step")

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """Test circuit becomes half-open after reset timeout."""
        middleware = CircuitBreakerMiddleware({
            "test_step": MiddlewareCircuitBreakerConfig(
                failure_threshold=2,
                reset_timeout=0.1,  # Very short for testing
            ),
        })
        
        ctx = ChainContext(request_id="test")
        
        # Open the circuit
        for _ in range(2):
            await middleware.before(ctx, "test_step")
            await middleware.on_error(ctx, "test_step", Exception("fail"))
        
        # Wait for reset timeout
        await asyncio.sleep(0.2)
        
        # Should allow one test request (half-open)
        await middleware.before(ctx, "test_step")

    @pytest.mark.asyncio
    async def test_unconfigured_step_not_protected(self):
        """Test steps without config are not circuit-protected."""
        middleware = CircuitBreakerMiddleware({
            "protected_step": MiddlewareCircuitBreakerConfig(failure_threshold=1),
        })
        
        ctx = ChainContext(request_id="test")
        
        # Simulate many failures on unprotected step
        for _ in range(10):
            await middleware.on_error(ctx, "unprotected_step", Exception("fail"))
        
        # Should still allow requests
        await middleware.before(ctx, "unprotected_step")


class TestCircuitBreakerConfig:
    """Tests for circuit breaker configuration."""

    def test_default_values(self):
        """Test default configuration values."""
        config = MiddlewareCircuitBreakerConfig()
        
        assert config.failure_threshold == 5
        assert config.reset_timeout == 30

    def test_custom_values(self):
        """Test custom configuration values."""
        config = MiddlewareCircuitBreakerConfig(
            failure_threshold=10,
            reset_timeout=60,
        )
        
        assert config.failure_threshold == 10
        assert config.reset_timeout == 60
