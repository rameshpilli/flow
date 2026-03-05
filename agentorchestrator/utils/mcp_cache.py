"""Thread-safe in-memory cache for MCP tool call results.

This module provides a production-ready caching layer for MCP tool calls with:
- Thread-safe operations using threading.Lock
- TTL-based expiration (default: 1 hour)
- LRU eviction when max entries reached (default: 500)
- Cache statistics tracking (hits, misses, evictions)
- JSON-based cache key generation from tool name + arguments

Example:
    from agentorchestrator.utils.mcp_cache import get_global_cache
    
    cache = get_global_cache()
    
    # Cache a tool result
    cache.set("search", {"query": "test"}, {"results": [...]})
    
    # Retrieve from cache
    result = cache.get("search", {"query": "test"})
    if result is not None:
        print("Cache hit!")
    
    # Get statistics
    stats = cache.get_stats()
    print(f"Hit rate: {stats['hit_rate']:.2%}")
"""

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Represents a single cache entry with metadata."""

    key: str
    value: Any
    created_at: float
    expires_at: float
    hit_count: int = 0
    last_accessed: float = field(default_factory=time.time)


@dataclass
class CacheStats:
    """Cache statistics for monitoring and observability."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_entries: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_entries": self.total_entries,
            "hit_rate": self.hit_rate,
        }


class MCPCache:
    """Thread-safe in-memory cache for MCP tool call results.
    
    This cache implements:
    - TTL-based expiration: Entries expire after a configurable time period
    - LRU eviction: When max entries reached, least recently used entries are removed
    - Thread safety: All operations are protected by a lock
    - Statistics tracking: Monitors hits, misses, and evictions
    
    Args:
        ttl_seconds: Time-to-live for cache entries in seconds (default: 3600 = 1 hour)
        max_entries: Maximum number of entries before LRU eviction (default: 500)
        enable_stats: Whether to track cache statistics (default: True)
    
    Example:
        cache = MCPCache(ttl_seconds=1800, max_entries=1000)
        
        # Cache a result
        cache.set("tool_name", {"arg": "value"}, {"result": "data"})
        
        # Retrieve from cache
        result = cache.get("tool_name", {"arg": "value"})
    """

    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_entries: int = 500,
        enable_stats: bool = True,
    ):
        """Initialize the MCP cache."""
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.enable_stats = enable_stats
        
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._stats = CacheStats()
        
        logger.info(
            f"Initialized MCPCache with ttl={ttl_seconds}s, max_entries={max_entries}"
        )

    def _generate_cache_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Generate a cache key from tool name and arguments.
        
        Args:
            tool_name: Name of the MCP tool
            arguments: Dictionary of tool arguments
        
        Returns:
            SHA256 hash of the tool name and sorted arguments
        """
        # Sort arguments to ensure consistent key generation
        sorted_args = json.dumps(arguments, sort_keys=True)
        key_string = f"{tool_name}:{sorted_args}"
        
        # Generate SHA256 hash
        return hashlib.sha256(key_string.encode()).hexdigest()

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if a cache entry has expired.
        
        Args:
            entry: Cache entry to check
        
        Returns:
            True if expired, False otherwise
        """
        return time.time() > entry.expires_at

    def _evict_lru(self) -> None:
        """Evict the least recently used entry.
        
        This method is called when the cache is full and a new entry needs to be added.
        It removes the entry with the oldest last_accessed timestamp.
        """
        if not self._cache:
            return
        
        # Find LRU entry
        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
        
        # Remove it
        del self._cache[lru_key]
        
        if self.enable_stats:
            self._stats.evictions += 1
        
        logger.debug(f"Evicted LRU cache entry: {lru_key[:16]}...")

    def _cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.
        
        Returns:
            Number of entries removed
        """
        expired_keys = [
            key for key, entry in self._cache.items() if self._is_expired(entry)
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)

    def get(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Any]:
        """Retrieve a value from the cache.
        
        Args:
            tool_name: Name of the MCP tool
            arguments: Dictionary of tool arguments
        
        Returns:
            Cached value if found and not expired, None otherwise
        """
        cache_key = self._generate_cache_key(tool_name, arguments)
        
        with self._lock:
            entry = self._cache.get(cache_key)
            
            if entry is None:
                if self.enable_stats:
                    self._stats.misses += 1
                return None
            
            # Check if expired
            if self._is_expired(entry):
                del self._cache[cache_key]
                if self.enable_stats:
                    self._stats.misses += 1
                logger.debug(f"Cache entry expired: {tool_name}")
                return None
            
            # Update access metadata
            entry.hit_count += 1
            entry.last_accessed = time.time()
            
            if self.enable_stats:
                self._stats.hits += 1
            
            logger.debug(f"Cache hit: {tool_name} (hits: {entry.hit_count})")
            return entry.value

    def set(self, tool_name: str, arguments: Dict[str, Any], value: Any) -> None:
        """Store a value in the cache.
        
        Args:
            tool_name: Name of the MCP tool
            arguments: Dictionary of tool arguments
            value: Value to cache
        """
        cache_key = self._generate_cache_key(tool_name, arguments)
        
        with self._lock:
            # Clean up expired entries periodically
            if len(self._cache) > 0 and len(self._cache) % 100 == 0:
                self._cleanup_expired()
            
            # Evict LRU if at capacity
            if len(self._cache) >= self.max_entries:
                self._evict_lru()
            
            # Create new entry
            now = time.time()
            entry = CacheEntry(
                key=cache_key,
                value=value,
                created_at=now,
                expires_at=now + self.ttl_seconds,
                last_accessed=now,
            )
            
            self._cache[cache_key] = entry
            
            if self.enable_stats:
                self._stats.total_entries = len(self._cache)
            
            logger.debug(f"Cached result for: {tool_name}")

    def invalidate(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Invalidate a specific cache entry.
        
        Args:
            tool_name: Name of the MCP tool
            arguments: Dictionary of tool arguments
        
        Returns:
            True if entry was found and removed, False otherwise
        """
        cache_key = self._generate_cache_key(tool_name, arguments)
        
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                if self.enable_stats:
                    self._stats.total_entries = len(self._cache)
                logger.debug(f"Invalidated cache entry: {tool_name}")
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            if self.enable_stats:
                self._stats.total_entries = 0
            logger.info(f"Cleared {count} cache entries")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary containing cache statistics including hits, misses, evictions,
            total entries, and hit rate.
        """
        with self._lock:
            # Update total entries count
            if self.enable_stats:
                self._stats.total_entries = len(self._cache)
            return self._stats.to_dict()

    def get_entry_info(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get detailed information about a cache entry.
        
        Args:
            tool_name: Name of the MCP tool
            arguments: Dictionary of tool arguments
        
        Returns:
            Dictionary with entry metadata or None if not found
        """
        cache_key = self._generate_cache_key(tool_name, arguments)
        
        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None
            
            return {
                "key": entry.key[:16] + "...",  # Truncate for readability
                "created_at": datetime.fromtimestamp(entry.created_at).isoformat(),
                "expires_at": datetime.fromtimestamp(entry.expires_at).isoformat(),
                "hit_count": entry.hit_count,
                "last_accessed": datetime.fromtimestamp(entry.last_accessed).isoformat(),
                "is_expired": self._is_expired(entry),
                "ttl_remaining": max(0, entry.expires_at - time.time()),
            }


# Global cache instance
_global_cache: Optional[MCPCache] = None
_global_cache_lock = threading.Lock()


def get_global_cache(
    ttl_seconds: int = 3600,
    max_entries: int = 500,
    enable_stats: bool = True,
) -> MCPCache:
    """Get or create the global MCP cache instance.
    
    This function implements a singleton pattern for the cache. The first call
    creates the cache with the provided parameters, and subsequent calls return
    the same instance (ignoring any new parameters).
    
    Args:
        ttl_seconds: Time-to-live for cache entries (only used on first call)
        max_entries: Maximum number of entries (only used on first call)
        enable_stats: Whether to track statistics (only used on first call)
    
    Returns:
        The global MCPCache instance
    
    Example:
        # First call creates the cache
        cache = get_global_cache(ttl_seconds=1800)
        
        # Subsequent calls return the same instance
        same_cache = get_global_cache()
        assert cache is same_cache
    """
    global _global_cache
    
    with _global_cache_lock:
        if _global_cache is None:
            _global_cache = MCPCache(
                ttl_seconds=ttl_seconds,
                max_entries=max_entries,
                enable_stats=enable_stats,
            )
            logger.info("Created global MCP cache instance")
        
        return _global_cache


def reset_global_cache() -> None:
    """Reset the global cache instance.
    
    This is primarily useful for testing. In production, you should use
    cache.clear() instead to clear entries without destroying the cache instance.
    """
    global _global_cache
    
    with _global_cache_lock:
        if _global_cache is not None:
            _global_cache.clear()
            _global_cache = None
            logger.info("Reset global MCP cache instance")