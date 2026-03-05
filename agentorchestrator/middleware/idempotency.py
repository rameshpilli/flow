"""
AgentOrchestrator Idempotency Middleware

Prevents duplicate execution of expensive steps by caching results based on
idempotency keys. Inspired by OpenAI's Airflow pattern of using idempotent
task keys to prevent unnecessary reruns.

Features:
- Automatic key generation from input hash
- Custom key functions per step
- TTL-based cache expiration
- Multiple storage backends (memory, Redis)

Usage:
    from agentorchestrator.middleware.idempotency import (
        IdempotencyMiddleware,
        IdempotencyConfig,
    )

    # Basic usage - auto-generate keys from input hash
    middleware = IdempotencyMiddleware()
    ao.add_middleware(middleware)

    # With custom key function
    @ao.step(
        name="expensive_computation",
        idempotency_key=lambda ctx: f"{ctx.get('company_id')}:{ctx.get('date')}",
    )
    async def expensive_computation(ctx):
        ...

    # With TTL
    middleware = IdempotencyMiddleware(
        config=IdempotencyConfig(ttl_seconds=3600)
    )
"""

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware

logger = logging.getLogger(__name__)

__all__ = [
    "IdempotencyMiddleware",
    "IdempotencyConfig",
    "IdempotencyBackend",
    "InMemoryIdempotencyBackend",
    "IdempotencyHit",
]


@dataclass
class IdempotencyHit:
    """Record of an idempotency cache hit"""

    key: str
    step_name: str
    cached_at: float
    expires_at: float | None
    result: Any


@dataclass
class IdempotencyConfig:
    """Configuration for idempotency middleware"""

    # TTL in seconds (None = no expiration)
    ttl_seconds: int | None = 3600

    # Whether to include step name in key generation
    include_step_name: bool = True

    # Whether to include request_id in key (False = cross-request dedup)
    include_request_id: bool = False

    # Fields to exclude from auto-generated keys
    exclude_fields: list[str] = field(default_factory=lambda: ["timestamp", "request_id"])

    # Whether to log cache hits
    log_hits: bool = True

    # Maximum cached entries (for memory backend)
    max_entries: int = 10000


class IdempotencyBackend(ABC):
    """Abstract backend for idempotency storage"""

    @abstractmethod
    async def get(self, key: str) -> IdempotencyHit | None:
        """Get cached result by key"""
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        step_name: str,
        result: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store result with key"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete cached result"""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cached results"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        pass


class InMemoryIdempotencyBackend(IdempotencyBackend):
    """In-memory idempotency storage (for single-process deployments)"""

    def __init__(self, max_entries: int = 10000):
        self._cache: dict[str, IdempotencyHit] = {}
        self._max_entries = max_entries

    async def get(self, key: str) -> IdempotencyHit | None:
        hit = self._cache.get(key)
        if hit is None:
            return None

        # Check expiration
        if hit.expires_at is not None and time.time() > hit.expires_at:
            del self._cache[key]
            return None

        return hit

    async def set(
        self,
        key: str,
        step_name: str,
        result: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        # Evict oldest entries if at capacity
        if len(self._cache) >= self._max_entries:
            # Remove ~10% of oldest entries
            entries_to_remove = max(1, self._max_entries // 10)
            sorted_keys = sorted(
                self._cache.keys(),
                key=lambda k: self._cache[k].cached_at,
            )
            for k in sorted_keys[:entries_to_remove]:
                del self._cache[k]

        now = time.time()
        expires_at = now + ttl_seconds if ttl_seconds else None

        self._cache[key] = IdempotencyHit(
            key=key,
            step_name=step_name,
            cached_at=now,
            expires_at=expires_at,
            result=result,
        )

    async def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def clear(self) -> None:
        self._cache.clear()

    async def exists(self, key: str) -> bool:
        hit = await self.get(key)  # This handles expiration
        return hit is not None

    def stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        now = time.time()
        expired = sum(
            1 for hit in self._cache.values()
            if hit.expires_at and hit.expires_at < now
        )
        return {
            "total_entries": len(self._cache),
            "expired_entries": expired,
            "max_entries": self._max_entries,
        }


class IdempotencyMiddleware(Middleware):
    """
    Middleware that prevents duplicate execution of steps.

    When a step is executed, this middleware:
    1. Generates an idempotency key from step inputs
    2. Checks if a result exists for that key
    3. If yes, returns cached result (skips execution)
    4. If no, allows execution and caches the result

    Usage:
        # Basic - auto-generated keys
        middleware = IdempotencyMiddleware()
        ao.add_middleware(middleware)

        # Custom key per step
        @ao.step(
            name="fetch_data",
            idempotency_key=lambda ctx: f"{ctx.get('ticker')}:{ctx.get('date')}",
        )
        async def fetch_data(ctx):
            ...

        # Disable for specific steps
        @ao.step(name="always_run", idempotent=False)
        async def always_run(ctx):
            ...
    """

    _ao_priority = 5  # Run early to skip execution if cache hit

    def __init__(
        self,
        config: IdempotencyConfig | None = None,
        backend: IdempotencyBackend | None = None,
        applies_to: list[str] | None = None,
        key_functions: dict[str, Callable[[ChainContext], str]] | None = None,
    ):
        """
        Initialize idempotency middleware.

        Args:
            config: Idempotency configuration
            backend: Storage backend (defaults to in-memory)
            applies_to: List of step names to apply to (None = all)
            key_functions: Dict mapping step names to custom key functions
        """
        self.config = config or IdempotencyConfig()
        self.backend = backend or InMemoryIdempotencyBackend(
            max_entries=self.config.max_entries
        )
        self._ao_applies_to = applies_to
        self._key_functions = key_functions or {}
        self._hits = 0
        self._misses = 0

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """Check for cached result before step execution"""
        # Check if step has idempotency disabled
        step_spec = self._get_step_spec(step_name)
        if step_spec and getattr(step_spec, "idempotent", None) is False:
            return

        # Generate idempotency key
        key = await self._generate_key(ctx, step_name, step_spec)

        # Check cache
        hit = await self.backend.get(key)
        if hit:
            self._hits += 1
            if self.config.log_hits:
                logger.info(
                    f"Idempotency hit for step '{step_name}' (key: {key[:16]}...)"
                )
            # Store hit info in context for after() to return cached result
            ctx.set(f"_idempotency_hit_{step_name}", hit, scope="step")
        else:
            self._misses += 1
            # Store key for caching in after()
            ctx.set(f"_idempotency_key_{step_name}", key, scope="step")

    async def after(
        self,
        ctx: ChainContext,
        step_name: str,
        result: StepResult,
    ) -> None:
        """Cache result after successful execution"""
        # Check if we had a cache hit (result was from cache)
        hit = ctx.get(f"_idempotency_hit_{step_name}")
        if hit:
            # Result came from cache, nothing to do
            return

        # Only cache successful results
        if not result.success:
            return

        # Get the key we generated in before()
        key = ctx.get(f"_idempotency_key_{step_name}")
        if not key:
            return

        # Cache the result
        await self.backend.set(
            key=key,
            step_name=step_name,
            result=result.output,
            ttl_seconds=self.config.ttl_seconds,
        )

        logger.debug(
            f"Cached result for step '{step_name}' (key: {key[:16]}..., "
            f"ttl: {self.config.ttl_seconds}s)"
        )

    async def _generate_key(
        self,
        ctx: ChainContext,
        step_name: str,
        step_spec: Any,
    ) -> str:
        """
        Generate idempotency key for a step execution.

        Priority:
        1. Custom key function registered with middleware
        2. Custom key function on step spec (idempotency_key attr)
        3. Auto-generated from context data hash
        """
        # Check for custom key function in middleware
        if step_name in self._key_functions:
            return self._key_functions[step_name](ctx)

        # Check for custom key function on step spec
        if step_spec:
            custom_fn = getattr(step_spec, "idempotency_key", None)
            if callable(custom_fn):
                return custom_fn(ctx)

        # Auto-generate from context
        return self._auto_generate_key(ctx, step_name)

    def _auto_generate_key(self, ctx: ChainContext, step_name: str) -> str:
        """Auto-generate idempotency key from context data"""
        key_parts = []

        if self.config.include_step_name:
            key_parts.append(f"step:{step_name}")

        if self.config.include_request_id:
            key_parts.append(f"req:{ctx.request_id}")

        # Hash the context data (excluding specified fields)
        data_to_hash = {}
        for key, value in (ctx.initial_data or {}).items():
            if key not in self.config.exclude_fields:
                data_to_hash[key] = value

        # Also include any step-specific inputs from context
        for key in ctx.keys():
            if not key.startswith("_") and key not in self.config.exclude_fields:
                val = ctx.get(key)
                if val is not None:
                    data_to_hash[key] = val

        # Create stable hash
        data_str = json.dumps(data_to_hash, sort_keys=True, default=str)
        data_hash = hashlib.sha256(data_str.encode()).hexdigest()[:16]
        key_parts.append(f"data:{data_hash}")

        return ":".join(key_parts)

    def _get_step_spec(self, step_name: str) -> Any:
        """Get step spec from registry"""
        try:
            from agentorchestrator.core.registry import get_step_registry
            return get_step_registry().get_spec(step_name)
        except Exception:
            return None

    def get_cached_result(self, ctx: ChainContext, step_name: str) -> Any | None:
        """
        Get cached result for a step if idempotency hit occurred.

        Call this in step handlers to get cached result instead of re-computing.

        Returns:
            Cached result if hit, None otherwise
        """
        hit = ctx.get(f"_idempotency_hit_{step_name}")
        if hit:
            return hit.result
        return None

    def stats(self) -> dict[str, Any]:
        """Get idempotency statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        stats = {
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate_percent": round(hit_rate, 2),
        }

        # Add backend stats if available
        if hasattr(self.backend, "stats"):
            stats["backend"] = self.backend.stats()

        return stats

    async def invalidate(self, key: str) -> bool:
        """Invalidate a cached result by key"""
        return await self.backend.delete(key)

    async def clear_cache(self) -> None:
        """Clear all cached results"""
        await self.backend.clear()
        self._hits = 0
        self._misses = 0


# Convenience function for creating middleware with Redis backend
def create_redis_idempotency_middleware(
    redis_url: str = "redis://localhost:6379",
    config: IdempotencyConfig | None = None,
    key_prefix: str = "ao:idempotency:",
    **kwargs,
) -> IdempotencyMiddleware:
    """
    Create idempotency middleware with Redis backend.

    Args:
        redis_url: Redis connection URL
        config: Idempotency configuration
        key_prefix: Prefix for Redis keys
        **kwargs: Additional args passed to IdempotencyMiddleware

    Returns:
        Configured IdempotencyMiddleware

    Note:
        Requires redis package: pip install redis
    """
    try:
        import redis.asyncio as redis
    except ImportError:
        raise ImportError(
            "Redis backend requires 'redis' package. "
            "Install with: pip install redis"
        )

    class RedisIdempotencyBackend(IdempotencyBackend):
        """Redis-based idempotency storage"""

        def __init__(self, redis_url: str, key_prefix: str):
            self._redis = redis.from_url(redis_url)
            self._prefix = key_prefix

        def _key(self, key: str) -> str:
            return f"{self._prefix}{key}"

        async def get(self, key: str) -> IdempotencyHit | None:
            data = await self._redis.get(self._key(key))
            if data is None:
                return None

            try:
                parsed = json.loads(data)
                return IdempotencyHit(
                    key=key,
                    step_name=parsed["step_name"],
                    cached_at=parsed["cached_at"],
                    expires_at=parsed.get("expires_at"),
                    result=parsed["result"],
                )
            except (json.JSONDecodeError, KeyError):
                return None

        async def set(
            self,
            key: str,
            step_name: str,
            result: Any,
            ttl_seconds: int | None = None,
        ) -> None:
            now = time.time()
            data = {
                "step_name": step_name,
                "cached_at": now,
                "expires_at": now + ttl_seconds if ttl_seconds else None,
                "result": result,
            }

            if ttl_seconds:
                await self._redis.setex(
                    self._key(key),
                    ttl_seconds,
                    json.dumps(data, default=str),
                )
            else:
                await self._redis.set(
                    self._key(key),
                    json.dumps(data, default=str),
                )

        async def delete(self, key: str) -> bool:
            result = await self._redis.delete(self._key(key))
            return result > 0

        async def clear(self) -> None:
            # Delete all keys with prefix
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=f"{self._prefix}*", count=100
                )
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break

        async def exists(self, key: str) -> bool:
            return await self._redis.exists(self._key(key)) > 0

    backend = RedisIdempotencyBackend(redis_url, key_prefix)
    return IdempotencyMiddleware(
        config=config,
        backend=backend,
        **kwargs,
    )
