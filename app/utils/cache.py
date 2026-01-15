# app/utils/cache.py
import json
import logging
import hashlib
from typing import Optional, Any, Callable
from functools import wraps
import redis
from app.config import config

logger = logging.getLogger("dbx_sql_mcp.cache")


class RedisCache:
    """Redis cache manager with TTL support"""
    
    def __init__(self):
        self.enabled = config.ENABLE_CACHING
        self._client: Optional[redis.Redis] = None
        
        if self.enabled:
            try:
                self._client = redis.Redis(
                    host=config.REDIS_HOST,
                    port=config.REDIS_PORT,
                    db=config.REDIS_DB,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                self._client.ping()
                logger.info(f"✓ Redis cache connected: {config.REDIS_HOST}:{config.REDIS_PORT}")
            except Exception as e:
                logger.warning(f"⚠ Redis connection failed: {e}. Caching disabled.")
                self.enabled = False
                self._client = None
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a cache key from prefix and arguments"""
        # Create a deterministic string from args and kwargs
        key_data = f"{prefix}:{str(args)}:{str(sorted(kwargs.items()))}"
        # Hash for consistent length
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"dbx_sql:{prefix}:{key_hash}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.enabled or not self._client:
            return None
        
        try:
            value = self._client.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            logger.debug(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int):
        """Set value in cache with TTL"""
        if not self.enabled or not self._client:
            return
        
        try:
            serialized = json.dumps(value)
            self._client.setex(key, ttl, serialized)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
    
    def delete(self, key: str):
        """Delete value from cache"""
        if not self.enabled or not self._client:
            return
        
        try:
            self._client.delete(key)
            logger.debug(f"Cache DELETE: {key}")
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
    
    def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern"""
        if not self.enabled or not self._client:
            return
        
        try:
            keys = self._client.keys(f"dbx_sql:{pattern}*")
            if keys:
                self._client.delete(*keys)
                logger.info(f"Cache cleared {len(keys)} keys matching: {pattern}")
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        if not self.enabled or not self._client:
            return {"enabled": False}
        
        try:
            info = self._client.info()
            return {
                "enabled": True,
                "connected": True,
                "keys": self._client.dbsize(),
                "memory_used": info.get("used_memory_human", "N/A"),
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
            }
        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return {"enabled": True, "connected": False, "error": str(e)}


# Global cache instance
cache = RedisCache()


def cached(ttl: int, prefix: str):
    """
    Decorator for caching function results
    
    Args:
        ttl: Time to live in seconds
        prefix: Cache key prefix
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = cache._generate_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Store in cache
            if result is not None:
                cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator
