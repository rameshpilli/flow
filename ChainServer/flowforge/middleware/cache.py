"""
FlowForge Cache Middleware

Provides caching for step outputs to avoid redundant computation.
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flowforge.core.context import ChainContext, StepResult
from flowforge.middleware.base import Middleware

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached step result"""

    key: str
    value: Any
    created_at: float
    expires_at: float
    hit_count: int = 0


class CacheMiddleware(Middleware):
    """
    Middleware that caches step outputs.

    Features:
    - TTL-based expiration
    - Custom cache key generation
    - In-memory or external cache support
    - Cache statistics

    Usage:
        forge.use_middleware(CacheMiddleware(
            ttl_seconds=300,
            cache_key_fn=lambda ctx, step: f"{step}:{ctx.get('company_id')}",
        ))
    """

    def __init__(
        self,
        priority: int = 20,
        applies_to: list[str] | None = None,
        ttl_seconds: int = 300,
        max_entries: int = 1000,
        cache_key_fn: Callable[[ChainContext, str], str] | None = None,
        enabled: bool = True,
    ):
        super().__init__(priority=priority, applies_to=applies_to)
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.cache_key_fn = cache_key_fn or self._default_cache_key
        self.enabled = enabled

        self._cache: dict[str, CacheEntry] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }

    def _default_cache_key(self, ctx: ChainContext, step_name: str) -> str:
        """Generate a default cache key based on context data"""
        # Create a hash of relevant context data
        context_data = ctx.to_dict().get("data", {})
        data_str = json.dumps(context_data, sort_keys=True, default=str)
        data_hash = hashlib.md5(data_str.encode()).hexdigest()[:16]
        return f"{step_name}:{data_hash}"

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        if not self.enabled:
            return

        cache_key = self.cache_key_fn(ctx, step_name)
        entry = self._get_entry(cache_key)

        if entry:
            # Cache hit - store result to skip execution
            ctx.set(f"_cache_hit_{step_name}", True)
            ctx.set(f"_cache_result_{step_name}", entry.value)
            entry.hit_count += 1
            self._stats["hits"] += 1
            logger.debug(f"Cache hit for step {step_name}: {cache_key}")
        else:
            self._stats["misses"] += 1
            logger.debug(f"Cache miss for step {step_name}: {cache_key}")

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        if not self.enabled:
            return

        # Don't cache failed results
        if not result.success:
            return

        # Check if this was a cache hit (no need to re-cache)
        if ctx.get(f"_cache_hit_{step_name}"):
            ctx.delete(f"_cache_hit_{step_name}")
            ctx.delete(f"_cache_result_{step_name}")
            return

        cache_key = self.cache_key_fn(ctx, step_name)
        self._set_entry(cache_key, result.output)
        logger.debug(f"Cached result for step {step_name}: {cache_key}")

    def _get_entry(self, key: str) -> CacheEntry | None:
        """Get a cache entry if it exists and is valid"""
        entry = self._cache.get(key)
        if entry is None:
            return None

        # Check expiration
        if time.time() > entry.expires_at:
            del self._cache[key]
            return None

        return entry

    def _set_entry(self, key: str, value: Any) -> None:
        """Set a cache entry"""
        # Evict if at capacity
        if len(self._cache) >= self.max_entries:
            self._evict_oldest()

        now = time.time()
        self._cache[key] = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )

    def _evict_oldest(self) -> None:
        """Evict the oldest cache entry"""
        if not self._cache:
            return

        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
        del self._cache[oldest_key]
        self._stats["evictions"] += 1

    def invalidate(self, key: str | None = None, step_name: str | None = None) -> int:
        """
        Invalidate cache entries.

        Args:
            key: Specific cache key to invalidate
            step_name: Invalidate all entries for a step

        Returns:
            Number of entries invalidated
        """
        if key:
            if key in self._cache:
                del self._cache[key]
                return 1
            return 0

        if step_name:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(f"{step_name}:")]
            for k in keys_to_delete:
                del self._cache[k]
            return len(keys_to_delete)

        # Invalidate all
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        total = self._stats["hits"] + self._stats["misses"]
        return {
            "entries": len(self._cache),
            "max_entries": self.max_entries,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
            "hit_rate": self._stats["hits"] / total if total > 0 else 0,
        }

    def clear(self) -> None:
        """Clear all cache entries and reset stats"""
        self._cache.clear()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}
