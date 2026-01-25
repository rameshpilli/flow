"""
AgentOrchestrator Redis Service

Enterprise Redis connection service template for corporate environments.
Supports SSL/TLS connections with authentication.

Usage:
    from agentorchestrator.services import RedisService, get_redis_client

    # Option 1: Using configuration
    redis = RedisService(
        host="redis-18834.cl12.redisgcc12.abc.com",
        port=18834,
        username="your_service_id",
        password="your_service_password",
        ssl=True,
    )

    # Option 2: Using environment variables
    redis = RedisService.from_env()

    # Connect and use
    await redis.connect()
    await redis.set("key", "value", ttl=300)
    value = await redis.get("key")

    # Health check
    is_healthy = await redis.health_check()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

# Optional redis import - gracefully handle if not installed
try:
    import redis
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore
    aioredis = None  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
#                         CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RedisConfig:
    """
    Redis connection configuration.

    Supports both direct configuration and environment variable loading.

    Environment Variables:
        REDIS_HOST: Redis server hostname
        REDIS_PORT: Redis server port (default: 6379)
        REDIS_USERNAME: Service account username
        REDIS_PASSWORD: Service account password
        REDIS_SSL: Enable SSL/TLS (default: true for enterprise)
        REDIS_SSL_CERT_REQS: SSL certificate requirements (default: none)
        REDIS_DB: Database number (default: 0)
        REDIS_DECODE_RESPONSES: Decode responses to strings (default: true)
        REDIS_SOCKET_TIMEOUT: Socket timeout in seconds (default: 30)
        REDIS_CONNECTION_TIMEOUT: Connection timeout in seconds (default: 10)
        REDIS_RETRY_ON_TIMEOUT: Retry on timeout (default: true)
        REDIS_MAX_CONNECTIONS: Maximum pool connections (default: 10)
    """

    host: str = "localhost"
    port: int = 6379
    username: str | None = None
    password: str | None = None
    db: int = 0
    ssl: bool = False
    ssl_cert_reqs: str | None = None  # 'required', 'optional', 'none', or None
    decode_responses: bool = True
    socket_timeout: float = 30.0
    connection_timeout: float = 10.0
    retry_on_timeout: bool = True
    max_connections: int = 10
    health_check_interval: int = 30

    @classmethod
    def from_env(cls, prefix: str = "REDIS") -> "RedisConfig":
        """
        Load configuration from environment variables.

        Args:
            prefix: Environment variable prefix (default: REDIS)

        Returns:
            RedisConfig instance
        """

        def get_env(key: str, default: Any = None) -> str | None:
            return os.getenv(f"{prefix}_{key}", default)

        def get_bool(key: str, default: bool = False) -> bool:
            val = get_env(key)
            if val is None:
                return default
            return val.lower() in ("true", "1", "yes", "on")

        def get_int(key: str, default: int) -> int:
            val = get_env(key)
            return int(val) if val else default

        def get_float(key: str, default: float) -> float:
            val = get_env(key)
            return float(val) if val else default

        # Parse SSL cert reqs
        ssl_cert_reqs = get_env("SSL_CERT_REQS")
        if ssl_cert_reqs and ssl_cert_reqs.lower() == "none":
            ssl_cert_reqs = None

        return cls(
            host=get_env("HOST", "localhost") or "localhost",
            port=get_int("PORT", 6379),
            username=get_env("USERNAME"),
            password=get_env("PASSWORD"),
            db=get_int("DB", 0),
            ssl=get_bool("SSL", False),
            ssl_cert_reqs=ssl_cert_reqs,
            decode_responses=get_bool("DECODE_RESPONSES", True),
            socket_timeout=get_float("SOCKET_TIMEOUT", 30.0),
            connection_timeout=get_float("CONNECTION_TIMEOUT", 10.0),
            retry_on_timeout=get_bool("RETRY_ON_TIMEOUT", True),
            max_connections=get_int("MAX_CONNECTIONS", 10),
            health_check_interval=get_int("HEALTH_CHECK_INTERVAL", 30),
        )

    @classmethod
    def from_url(cls, url: str) -> "RedisConfig":
        """
        Parse configuration from Redis URL.

        Args:
            url: Redis URL (redis://user:pass@host:port/db or rediss:// for SSL)

        Returns:
            RedisConfig instance
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        ssl = parsed.scheme == "rediss"

        return cls(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            username=parsed.username,
            password=parsed.password,
            db=int(parsed.path.lstrip("/") or 0),
            ssl=ssl,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                         REDIS SERVICE
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RedisHealthStatus:
    """Redis health check result."""

    healthy: bool
    latency_ms: float
    redis_version: str | None = None
    uptime_days: float | None = None
    connected_clients: int | None = None
    used_memory_human: str | None = None
    error: str | None = None


class RedisService:
    """
    Enterprise Redis connection service.

    Provides a high-level interface for Redis operations with:
    - SSL/TLS support for secure connections
    - Service account authentication
    - Connection pooling
    - Health checks
    - Automatic reconnection
    - JSON serialization helpers

    Example:
        ```python
        # Corporate environment with SSL
        redis = RedisService(
            host="redis-18834.cl12.redisgcc12.abc.com",
            port=18834,
            username="my_service_id",
            password="my_service_password",
            ssl=True,
        )

        # Connect
        await redis.connect()

        # Basic operations
        await redis.set("key", "value", ttl=300)
        value = await redis.get("key")

        # JSON operations
        await redis.set_json("user:123", {"name": "John", "age": 30})
        user = await redis.get_json("user:123")

        # Health check
        status = await redis.health_check()
        print(f"Redis healthy: {status.healthy}")

        # Cleanup
        await redis.close()
        ```
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        username: str | None = None,
        password: str | None = None,
        db: int = 0,
        ssl: bool = False,
        ssl_cert_reqs: str | None = None,
        decode_responses: bool = True,
        socket_timeout: float = 30.0,
        connection_timeout: float = 10.0,
        retry_on_timeout: bool = True,
        max_connections: int = 10,
        health_check_interval: int = 30,
        config: RedisConfig | None = None,
    ):
        """
        Initialize Redis service.

        Args:
            host: Redis server hostname
            port: Redis server port
            username: Service account username (for ACL auth)
            password: Service account password
            db: Database number
            ssl: Enable SSL/TLS connection
            ssl_cert_reqs: SSL certificate requirements ('required', 'optional', None)
            decode_responses: Decode responses to strings
            socket_timeout: Socket timeout in seconds
            connection_timeout: Connection timeout in seconds
            retry_on_timeout: Retry operations on timeout
            max_connections: Maximum pool connections
            health_check_interval: Health check interval in seconds
            config: RedisConfig instance (overrides other params)
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package is required. Install with: pip install redis>=4.5.0"
            )

        if config:
            self.config = config
        else:
            self.config = RedisConfig(
                host=host,
                port=port,
                username=username,
                password=password,
                db=db,
                ssl=ssl,
                ssl_cert_reqs=ssl_cert_reqs,
                decode_responses=decode_responses,
                socket_timeout=socket_timeout,
                connection_timeout=connection_timeout,
                retry_on_timeout=retry_on_timeout,
                max_connections=max_connections,
                health_check_interval=health_check_interval,
            )

        self._client: aioredis.Redis | None = None
        self._sync_client: redis.Redis | None = None
        self._connected = False

    @classmethod
    def from_env(cls, prefix: str = "REDIS") -> "RedisService":
        """
        Create service from environment variables.

        Args:
            prefix: Environment variable prefix

        Returns:
            RedisService instance
        """
        config = RedisConfig.from_env(prefix)
        return cls(config=config)

    @classmethod
    def from_url(cls, url: str) -> "RedisService":
        """
        Create service from Redis URL.

        Args:
            url: Redis URL

        Returns:
            RedisService instance
        """
        config = RedisConfig.from_url(url)
        return cls(config=config)

    def _get_connection_kwargs(self) -> dict[str, Any]:
        """Get connection parameters for Redis client."""
        kwargs: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "db": self.config.db,
            "decode_responses": self.config.decode_responses,
            "socket_timeout": self.config.socket_timeout,
            "socket_connect_timeout": self.config.connection_timeout,
            "retry_on_timeout": self.config.retry_on_timeout,
            "health_check_interval": self.config.health_check_interval,
        }

        # Authentication
        if self.config.username:
            kwargs["username"] = self.config.username
        if self.config.password:
            kwargs["password"] = self.config.password

        # SSL/TLS configuration
        if self.config.ssl:
            kwargs["ssl"] = True
            kwargs["ssl_cert_reqs"] = self.config.ssl_cert_reqs

        return kwargs

    # ═══════════════════════════════════════════════════════════════════════════
    #                         CONNECTION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    async def connect(self) -> "RedisService":
        """
        Establish async connection to Redis.

        Returns:
            Self for chaining

        Raises:
            redis.ConnectionError: If connection fails
            redis.AuthenticationError: If authentication fails
        """
        if self._client and self._connected:
            return self

        connection_kwargs = self._get_connection_kwargs()

        try:
            self._client = aioredis.Redis(
                **connection_kwargs,
                max_connections=self.config.max_connections,
            )

            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info(
                f"Connected to Redis at {self.config.host}:{self.config.port}"
            )
            return self

        except redis.AuthenticationError as e:
            logger.error(f"Redis authentication failed: {e}")
            raise
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis: {e}")
            raise

    def connect_sync(self) -> "RedisService":
        """
        Establish synchronous connection to Redis.

        Returns:
            Self for chaining
        """
        if self._sync_client:
            return self

        connection_kwargs = self._get_connection_kwargs()

        try:
            self._sync_client = redis.Redis(
                **connection_kwargs,
                max_connections=self.config.max_connections,
            )

            # Test connection
            self._sync_client.ping()
            logger.info(
                f"Connected to Redis (sync) at {self.config.host}:{self.config.port}"
            )
            return self

        except redis.AuthenticationError as e:
            logger.error(f"Redis authentication failed: {e}")
            raise
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            raise

    @property
    def is_connected(self) -> bool:
        """Check if async client is connected."""
        return self._connected and self._client is not None

    async def ensure_connected(self) -> "RedisService":
        """
        Ensure Redis is connected, connecting if necessary.

        This is the preferred way to check/establish connection before operations.

        Returns:
            Self for chaining

        Example:
            await redis.ensure_connected()
            value = await redis.get("key")
        """
        if not self._connected:
            await self.connect()
        return self

    async def close(self) -> None:
        """Close Redis connections."""
        if self._client:
            await self._client.close()
            self._client = None
            self._connected = False
            logger.info("Redis async connection closed")

        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
            logger.info("Redis sync connection closed")

    @asynccontextmanager
    async def connection(self) -> AsyncIterator["RedisService"]:
        """
        Context manager for Redis connection.

        Example:
            async with redis.connection() as r:
                await r.set("key", "value")
        """
        await self.connect()
        try:
            yield self
        finally:
            await self.close()

    @property
    def client(self) -> aioredis.Redis:
        """Get the async Redis client."""
        if not self._client:
            raise RuntimeError(
                "Redis not connected. Call connect() first or use connection() context manager."
            )
        return self._client

    @property
    def sync_client(self) -> redis.Redis:
        """Get the sync Redis client."""
        if not self._sync_client:
            raise RuntimeError(
                "Redis not connected. Call connect_sync() first."
            )
        return self._sync_client

    # ═══════════════════════════════════════════════════════════════════════════
    #                         BASIC OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get(self, key: str) -> str | None:
        """Get a string value."""
        return await self.client.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        Set a string value.

        Args:
            key: Key name
            value: Value to set
            ttl: Time-to-live in seconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists

        Returns:
            True if set successfully
        """
        return await self.client.set(key, value, ex=ttl, nx=nx, xx=xx)

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys. Returns count of deleted keys."""
        return await self.client.delete(*keys)

    async def exists(self, *keys: str) -> int:
        """Check if keys exist. Returns count of existing keys."""
        return await self.client.exists(*keys)

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on a key."""
        return await self.client.expire(key, ttl)

    async def ttl(self, key: str) -> int:
        """Get TTL of a key. Returns -1 if no expiry, -2 if key doesn't exist."""
        return await self.client.ttl(key)

    async def keys(self, pattern: str = "*") -> list[str]:
        """
        Get keys matching pattern using SCAN (safe for production).

        Args:
            pattern: Glob pattern (e.g., "user:*")

        Returns:
            List of matching keys
        """
        keys = []
        cursor = 0
        while True:
            cursor, batch = await self.client.scan(cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        return keys

    # ═══════════════════════════════════════════════════════════════════════════
    #                         JSON OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_json(self, key: str) -> Any | None:
        """Get a JSON value."""
        value = await self.client.get(key)
        if value is None:
            return None
        return json.loads(value)

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        Set a JSON value.

        Args:
            key: Key name
            value: JSON-serializable value
            ttl: Time-to-live in seconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists

        Returns:
            True if set successfully
        """
        json_str = json.dumps(value, default=str)
        return await self.client.set(key, json_str, ex=ttl, nx=nx, xx=xx)

    # ═══════════════════════════════════════════════════════════════════════════
    #                         HASH OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def hget(self, name: str, key: str) -> str | None:
        """Get a hash field value."""
        return await self.client.hget(name, key)

    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> int:
        """
        Set hash field(s).

        Args:
            name: Hash name
            key: Field name (if setting single field)
            value: Field value (if setting single field)
            mapping: Dict of field:value pairs (for multiple fields)

        Returns:
            Number of fields added
        """
        return await self.client.hset(name, key, value, mapping)

    async def hgetall(self, name: str) -> dict[str, str]:
        """Get all fields and values from a hash."""
        return await self.client.hgetall(name)

    async def hdel(self, name: str, *keys: str) -> int:
        """Delete hash field(s). Returns count of deleted fields."""
        return await self.client.hdel(name, *keys)

    # ═══════════════════════════════════════════════════════════════════════════
    #                         LIST OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def lpush(self, name: str, *values: str) -> int:
        """Push values to the left of a list. Returns list length."""
        return await self.client.lpush(name, *values)

    async def rpush(self, name: str, *values: str) -> int:
        """Push values to the right of a list. Returns list length."""
        return await self.client.rpush(name, *values)

    async def lpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        """Pop value(s) from the left of a list."""
        return await self.client.lpop(name, count)

    async def rpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        """Pop value(s) from the right of a list."""
        return await self.client.rpop(name, count)

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        """Get a range of values from a list."""
        return await self.client.lrange(name, start, end)

    async def llen(self, name: str) -> int:
        """Get the length of a list."""
        return await self.client.llen(name)

    # ═══════════════════════════════════════════════════════════════════════════
    #                         SET OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def sadd(self, name: str, *values: str) -> int:
        """Add values to a set. Returns count of added values."""
        return await self.client.sadd(name, *values)

    async def srem(self, name: str, *values: str) -> int:
        """Remove values from a set. Returns count of removed values."""
        return await self.client.srem(name, *values)

    async def smembers(self, name: str) -> set[str]:
        """Get all members of a set."""
        return await self.client.smembers(name)

    async def sismember(self, name: str, value: str) -> bool:
        """Check if value is a member of a set."""
        return await self.client.sismember(name, value)

    async def scard(self, name: str) -> int:
        """Get the cardinality (size) of a set."""
        return await self.client.scard(name)

    # ═══════════════════════════════════════════════════════════════════════════
    #                         HEALTH CHECK
    # ═══════════════════════════════════════════════════════════════════════════

    async def health_check(self) -> RedisHealthStatus:
        """
        Perform a comprehensive health check.

        Returns:
            RedisHealthStatus with health information
        """
        import time

        start = time.perf_counter()

        try:
            # Ensure connected
            if not self._connected:
                await self.connect()

            # Ping test
            await self.client.ping()
            latency_ms = (time.perf_counter() - start) * 1000

            # Get server info
            info = await self.client.info("server")
            memory = await self.client.info("memory")
            clients = await self.client.info("clients")

            return RedisHealthStatus(
                healthy=True,
                latency_ms=latency_ms,
                redis_version=info.get("redis_version"),
                uptime_days=info.get("uptime_in_days"),
                connected_clients=clients.get("connected_clients"),
                used_memory_human=memory.get("used_memory_human"),
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return RedisHealthStatus(
                healthy=False,
                latency_ms=latency_ms,
                error=str(e),
            )

    async def ping(self) -> bool:
        """Simple ping check. Returns True if Redis responds."""
        try:
            return await self.client.ping()
        except Exception:
            return False

    # ═══════════════════════════════════════════════════════════════════════════
    #                         CACHE HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    async def cache_get_or_set(
        self,
        key: str,
        factory: Any,
        ttl: int = 300,
    ) -> Any:
        """
        Get cached value or compute and cache it.

        Args:
            key: Cache key
            factory: Async callable to compute value if not cached
            ttl: Time-to-live in seconds

        Returns:
            Cached or computed value
        """
        # Try to get from cache
        cached = await self.get_json(key)
        if cached is not None:
            return cached

        # Compute value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()

        # Cache and return
        await self.set_json(key, value, ttl=ttl)
        return value

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate (delete) all keys matching a pattern.

        Args:
            pattern: Glob pattern (e.g., "user:*", "cache:*")

        Returns:
            Number of deleted keys
        """
        keys = await self.keys(pattern)
        if keys:
            return await self.delete(*keys)
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
#                         MODULE-LEVEL SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_default_redis: RedisService | None = None


def get_redis_client() -> RedisService:
    """
    Get the default Redis service instance.

    Call init_redis_client() first to configure, or it will
    use environment variables.

    Returns:
        RedisService instance
    """
    global _default_redis
    if _default_redis is None:
        _default_redis = RedisService.from_env()
    return _default_redis


def init_redis_client(
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    ssl: bool = True,
    config: RedisConfig | None = None,
    **kwargs: Any,
) -> RedisService:
    """
    Initialize the default Redis service instance.

    Args:
        host: Redis server hostname
        port: Redis server port
        username: Service account username
        password: Service account password
        ssl: Enable SSL/TLS
        config: RedisConfig instance (overrides other params)
        **kwargs: Additional configuration options

    Returns:
        RedisService instance
    """
    global _default_redis

    if config:
        _default_redis = RedisService(config=config)
    else:
        _default_redis = RedisService(
            host=host or os.getenv("REDIS_HOST", "localhost"),
            port=port or int(os.getenv("REDIS_PORT", "6379")),
            username=username or os.getenv("REDIS_USERNAME"),
            password=password or os.getenv("REDIS_PASSWORD"),
            ssl=ssl,
            **kwargs,
        )

    return _default_redis


def set_redis_client(client: RedisService) -> None:
    """
    Set a custom Redis service instance as the default.

    Args:
        client: RedisService instance to use
    """
    global _default_redis
    _default_redis = client


__all__ = [
    "RedisService",
    "RedisConfig",
    "RedisHealthStatus",
    "get_redis_client",
    "init_redis_client",
    "set_redis_client",
    "REDIS_AVAILABLE",
]
