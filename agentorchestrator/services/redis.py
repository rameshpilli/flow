"""
AgentOrchestrator Redis Service
===============================

This module provides an enterprise Redis connection service with SSL/TLS support,
service account authentication, and high-level operations for key-value, JSON,
hash, list, and set data structures.

Designed for corporate environments that require secure Redis connections with
proper authentication and connection pooling.

Classes:
    RedisConfig: Configuration dataclass for Redis connection settings.
    RedisHealthStatus: Health check result dataclass.
    RedisService: Main Redis service class with async and sync operations.

Functions:
    get_redis_client: Get the default Redis service instance.
    init_redis_client: Initialize and set the default Redis service.
    set_redis_client: Set a custom Redis service as the default.

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

Example:
    >>> from agentorchestrator.services import RedisService
    >>>
    >>> # Create and connect
    >>> redis = RedisService(host="localhost", port=6379)
    >>> await redis.connect()
    >>>
    >>> # Basic operations
    >>> await redis.set("user:123:name", "John", ttl=3600)
    >>> name = await redis.get("user:123:name")
    >>> print(name)  # "John"
    >>>
    >>> # JSON operations
    >>> await redis.set_json("user:123", {"name": "John", "age": 30})
    >>> user = await redis.get_json("user:123")
    >>> print(user["age"])  # 30
    >>>
    >>> # Context manager
    >>> async with redis.connection() as r:
    ...     await r.set("temp", "value")

See Also:
    - agentorchestrator.services.mem0: Semantic memory integration.
    - agentorchestrator.squad.storage: Chat history storage using Redis.
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

    This dataclass holds all configuration needed to connect to a Redis server,
    including connection parameters, authentication credentials, SSL settings,
    and pool configuration.

    Attributes:
        host (str): Redis server hostname. Default: "localhost".
        port (int): Redis server port. Default: 6379.
        username (str | None): Service account username for ACL auth. Default: None.
        password (str | None): Service account password. Default: None.
        db (int): Database number (0-15). Default: 0.
        ssl (bool): Enable SSL/TLS connection. Default: False.
        ssl_cert_reqs (str | None): SSL certificate requirements. Default: None.
            Options: 'required', 'optional', 'none', or None.
        decode_responses (bool): Decode responses to strings. Default: True.
        socket_timeout (float): Socket timeout in seconds. Default: 30.0.
        connection_timeout (float): Connection timeout in seconds. Default: 10.0.
        retry_on_timeout (bool): Retry operations on timeout. Default: True.
        max_connections (int): Maximum pool connections. Default: 10.
        health_check_interval (int): Health check interval in seconds. Default: 30.

    Environment Variables:
        REDIS_HOST: Redis server hostname
        REDIS_PORT: Redis server port (default: 6379)
        REDIS_USERNAME: Service account username
        REDIS_PASSWORD: Service account password
        REDIS_SSL: Enable SSL/TLS (default: false)
        REDIS_SSL_CERT_REQS: SSL certificate requirements (default: none)
        REDIS_DB: Database number (default: 0)
        REDIS_DECODE_RESPONSES: Decode responses to strings (default: true)
        REDIS_SOCKET_TIMEOUT: Socket timeout in seconds (default: 30)
        REDIS_CONNECTION_TIMEOUT: Connection timeout in seconds (default: 10)
        REDIS_RETRY_ON_TIMEOUT: Retry on timeout (default: true)
        REDIS_MAX_CONNECTIONS: Maximum pool connections (default: 10)

    Methods:
        from_env(): Load configuration from environment variables.
        from_url(): Parse configuration from Redis URL.

    Example:
        >>> # Direct configuration
        >>> config = RedisConfig(
        ...     host="redis.corp.com",
        ...     port=6380,
        ...     username="svc_account",
        ...     password="secret",
        ...     ssl=True,
        ... )
        >>>
        >>> # From environment
        >>> config = RedisConfig.from_env()
        >>>
        >>> # From URL
        >>> config = RedisConfig.from_url("rediss://user:pass@host:6380/0")

    See Also:
        RedisService: Service class that uses this configuration.
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

        Reads environment variables with the specified prefix and creates
        a configuration instance. Boolean values accept: true, 1, yes, on.

        Args:
            prefix (str): Environment variable prefix. Default: "REDIS".
                Variables are read as {prefix}_{KEY}, e.g., REDIS_HOST.

        Returns:
            RedisConfig: Configuration loaded from environment.

        Example:
            >>> import os
            >>> os.environ["REDIS_HOST"] = "redis.corp.com"
            >>> os.environ["REDIS_PORT"] = "6380"
            >>> os.environ["REDIS_SSL"] = "true"
            >>>
            >>> config = RedisConfig.from_env()
            >>> print(config.host)  # "redis.corp.com"
            >>> print(config.ssl)   # True
            >>>
            >>> # With custom prefix
            >>> os.environ["CACHE_HOST"] = "cache.corp.com"
            >>> config = RedisConfig.from_env(prefix="CACHE")
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

        Supports standard Redis URL format with optional SSL scheme.

        Args:
            url (str): Redis URL in format:
                - redis://user:pass@host:port/db (standard)
                - rediss://user:pass@host:port/db (SSL)

        Returns:
            RedisConfig: Configuration parsed from URL.

        Example:
            >>> # Standard connection
            >>> config = RedisConfig.from_url("redis://localhost:6379/0")
            >>>
            >>> # With authentication
            >>> config = RedisConfig.from_url("redis://user:pass@redis.corp.com:6379/1")
            >>>
            >>> # SSL connection
            >>> config = RedisConfig.from_url("rediss://user:pass@redis.corp.com:6380/0")
            >>> print(config.ssl)  # True
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
    """
    Redis health check result.

    Contains detailed information about Redis server health and performance.

    Attributes:
        healthy (bool): Whether Redis is healthy and responding.
        latency_ms (float): Ping latency in milliseconds.
        redis_version (str | None): Redis server version.
        uptime_days (float | None): Server uptime in days.
        connected_clients (int | None): Number of connected clients.
        used_memory_human (str | None): Human-readable memory usage.
        error (str | None): Error message if unhealthy.

    Example:
        >>> status = await redis.health_check()
        >>> if status.healthy:
        ...     print(f"Redis {status.redis_version} - {status.latency_ms:.1f}ms")
        ... else:
        ...     print(f"Redis unhealthy: {status.error}")
    """

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
    - Service account authentication (ACL)
    - Connection pooling for performance
    - Comprehensive health checks
    - Automatic reconnection on failure
    - JSON serialization helpers
    - Both async and sync client support

    Attributes:
        config (RedisConfig): Redis connection configuration.
        is_connected (bool): Whether async client is connected.
        client (aioredis.Redis): Async Redis client (raises if not connected).
        sync_client (redis.Redis): Sync Redis client (raises if not connected).

    Methods:
        connect(): Establish async connection.
        connect_sync(): Establish sync connection.
        close(): Close all connections.
        ensure_connected(): Connect if not already connected.
        connection(): Async context manager for connection lifecycle.
        health_check(): Perform comprehensive health check.

    Basic Operations:
        get(), set(), delete(), exists(), expire(), ttl(), keys()

    JSON Operations:
        get_json(), set_json()

    Hash Operations:
        hget(), hset(), hgetall(), hdel()

    List Operations:
        lpush(), rpush(), lpop(), rpop(), lrange(), llen()

    Set Operations:
        sadd(), srem(), smembers(), sismember(), scard()

    Cache Helpers:
        cache_get_or_set(), invalidate_pattern()

    Example:
        >>> from agentorchestrator.services import RedisService
        >>>
        >>> # Corporate environment with SSL
        >>> redis = RedisService(
        ...     host="redis-18834.cl12.redisgcc12.abc.com",
        ...     port=18834,
        ...     username="my_service_id",
        ...     password="my_service_password",
        ...     ssl=True,
        ... )
        >>>
        >>> # Connect
        >>> await redis.connect()
        >>>
        >>> # Basic operations
        >>> await redis.set("key", "value", ttl=300)
        >>> value = await redis.get("key")
        >>>
        >>> # JSON operations
        >>> await redis.set_json("user:123", {"name": "John", "age": 30})
        >>> user = await redis.get_json("user:123")
        >>>
        >>> # Health check
        >>> status = await redis.health_check()
        >>> print(f"Redis healthy: {status.healthy}")
        >>>
        >>> # Cleanup
        >>> await redis.close()

    Context Manager Usage:
        >>> async with redis.connection() as r:
        ...     await r.set("temp", "value")
        ...     # Connection automatically closed

    See Also:
        RedisConfig: Configuration options.
        RedisHealthStatus: Health check result format.
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

        Can be initialized either with individual parameters or a
        RedisConfig instance. If config is provided, it overrides
        all other parameters.

        Args:
            host (str): Redis server hostname. Default: "localhost".
            port (int): Redis server port. Default: 6379.
            username (str | None): Service account username. Default: None.
            password (str | None): Service account password. Default: None.
            db (int): Database number (0-15). Default: 0.
            ssl (bool): Enable SSL/TLS connection. Default: False.
            ssl_cert_reqs (str | None): SSL certificate requirements. Default: None.
            decode_responses (bool): Decode responses to strings. Default: True.
            socket_timeout (float): Socket timeout in seconds. Default: 30.0.
            connection_timeout (float): Connection timeout in seconds. Default: 10.0.
            retry_on_timeout (bool): Retry operations on timeout. Default: True.
            max_connections (int): Maximum pool connections. Default: 10.
            health_check_interval (int): Health check interval in seconds. Default: 30.
            config (RedisConfig | None): Configuration instance. Default: None.
                If provided, overrides all other parameters.

        Raises:
            ImportError: If redis package is not installed.

        Example:
            >>> # Individual parameters
            >>> redis = RedisService(
            ...     host="redis.corp.com",
            ...     port=6380,
            ...     ssl=True,
            ... )
            >>>
            >>> # Using config
            >>> config = RedisConfig.from_env()
            >>> redis = RedisService(config=config)
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

        Convenience factory that loads RedisConfig from environment
        and creates a service instance.

        Args:
            prefix (str): Environment variable prefix. Default: "REDIS".

        Returns:
            RedisService: Service configured from environment.

        Example:
            >>> import os
            >>> os.environ["REDIS_HOST"] = "redis.corp.com"
            >>> os.environ["REDIS_PASSWORD"] = "secret"
            >>>
            >>> redis = RedisService.from_env()
            >>> await redis.connect()
        """
        config = RedisConfig.from_env(prefix)
        return cls(config=config)

    @classmethod
    def from_url(cls, url: str) -> "RedisService":
        """
        Create service from Redis URL.

        Convenience factory that parses a Redis URL and creates
        a service instance.

        Args:
            url (str): Redis URL (redis:// or rediss:// for SSL).

        Returns:
            RedisService: Service configured from URL.

        Example:
            >>> redis = RedisService.from_url("redis://localhost:6379/0")
            >>> await redis.connect()
            >>>
            >>> # SSL with auth
            >>> redis = RedisService.from_url("rediss://user:pass@redis.corp.com:6380/0")
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

        Creates an async Redis client with connection pooling and
        verifies the connection with a ping.

        Returns:
            RedisService: Self for method chaining.

        Raises:
            redis.ConnectionError: If connection fails.
            redis.AuthenticationError: If authentication fails.

        Example:
            >>> redis = RedisService(host="localhost")
            >>> await redis.connect()
            >>> # Now ready for operations
            >>> await redis.set("key", "value")
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

        Creates a sync Redis client for use in non-async contexts.

        Returns:
            RedisService: Self for method chaining.

        Raises:
            redis.ConnectionError: If connection fails.
            redis.AuthenticationError: If authentication fails.

        Example:
            >>> redis = RedisService(host="localhost")
            >>> redis.connect_sync()
            >>> value = redis.sync_client.get("key")
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
        """
        Check if async client is connected.

        Returns:
            bool: True if connected, False otherwise.

        Example:
            >>> if not redis.is_connected:
            ...     await redis.connect()
        """
        return self._connected and self._client is not None

    async def ensure_connected(self) -> "RedisService":
        """
        Ensure Redis is connected, connecting if necessary.

        This is the preferred way to check/establish connection before
        operations. Safe to call multiple times.

        Returns:
            RedisService: Self for method chaining.

        Example:
            >>> await redis.ensure_connected()
            >>> value = await redis.get("key")
        """
        if not self._connected:
            await self.connect()
        return self

    async def close(self) -> None:
        """
        Close Redis connections.

        Closes both async and sync clients if they exist.
        Safe to call multiple times.

        Example:
            >>> await redis.close()
            >>> # Connections are now closed
        """
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

        Automatically connects on enter and closes on exit.
        Useful for ensuring cleanup in scripts.

        Yields:
            RedisService: This service instance.

        Example:
            >>> async with redis.connection() as r:
            ...     await r.set("key", "value")
            ...     value = await r.get("key")
            >>> # Connection automatically closed
        """
        await self.connect()
        try:
            yield self
        finally:
            await self.close()

    @property
    def client(self) -> aioredis.Redis:
        """
        Get the async Redis client.

        Returns:
            aioredis.Redis: The async Redis client.

        Raises:
            RuntimeError: If not connected.

        Example:
            >>> await redis.connect()
            >>> # Direct client access for advanced operations
            >>> await redis.client.execute_command("INFO")
        """
        if not self._client:
            raise RuntimeError(
                "Redis not connected. Call connect() first or use connection() context manager."
            )
        return self._client

    @property
    def sync_client(self) -> redis.Redis:
        """
        Get the sync Redis client.

        Returns:
            redis.Redis: The sync Redis client.

        Raises:
            RuntimeError: If not connected.

        Example:
            >>> redis.connect_sync()
            >>> value = redis.sync_client.get("key")
        """
        if not self._sync_client:
            raise RuntimeError(
                "Redis not connected. Call connect_sync() first."
            )
        return self._sync_client

    # ═══════════════════════════════════════════════════════════════════════════
    #                         BASIC OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get(self, key: str) -> str | None:
        """
        Get a string value by key.

        Args:
            key (str): The key to retrieve.

        Returns:
            str | None: The value, or None if key doesn't exist.

        Example:
            >>> await redis.set("name", "John")
            >>> name = await redis.get("name")
            >>> print(name)  # "John"
        """
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
            key (str): Key name.
            value (str): Value to set.
            ttl (int | None): Time-to-live in seconds. Default: None (no expiry).
            nx (bool): Only set if key doesn't exist. Default: False.
            xx (bool): Only set if key exists. Default: False.

        Returns:
            bool: True if set successfully.

        Example:
            >>> # Basic set
            >>> await redis.set("key", "value")
            >>>
            >>> # With TTL
            >>> await redis.set("session", "data", ttl=3600)
            >>>
            >>> # Only if not exists (for locks)
            >>> acquired = await redis.set("lock:resource", "1", ttl=60, nx=True)
        """
        return await self.client.set(key, value, ex=ttl, nx=nx, xx=xx)

    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys.

        Args:
            *keys (str): Keys to delete.

        Returns:
            int: Number of keys that were deleted.

        Example:
            >>> await redis.set("a", "1")
            >>> await redis.set("b", "2")
            >>> deleted = await redis.delete("a", "b", "nonexistent")
            >>> print(deleted)  # 2
        """
        return await self.client.delete(*keys)

    async def exists(self, *keys: str) -> int:
        """
        Check if keys exist.

        Args:
            *keys (str): Keys to check.

        Returns:
            int: Number of keys that exist.

        Example:
            >>> await redis.set("a", "1")
            >>> count = await redis.exists("a", "b")
            >>> print(count)  # 1
        """
        return await self.client.exists(*keys)

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration on a key.

        Args:
            key (str): Key to set expiration on.
            ttl (int): Time-to-live in seconds.

        Returns:
            bool: True if timeout was set, False if key doesn't exist.

        Example:
            >>> await redis.set("session", "data")
            >>> await redis.expire("session", 3600)  # Expire in 1 hour
        """
        return await self.client.expire(key, ttl)

    async def ttl(self, key: str) -> int:
        """
        Get the TTL of a key.

        Args:
            key (str): Key to check.

        Returns:
            int: TTL in seconds, -1 if no expiry, -2 if key doesn't exist.

        Example:
            >>> await redis.set("session", "data", ttl=3600)
            >>> remaining = await redis.ttl("session")
            >>> print(f"{remaining} seconds remaining")
        """
        return await self.client.ttl(key)

    async def keys(self, pattern: str = "*") -> list[str]:
        """
        Get keys matching pattern using SCAN (production-safe).

        Uses SCAN iterator instead of KEYS command to avoid
        blocking the server on large datasets.

        Args:
            pattern (str): Glob pattern. Default: "*" (all keys).
                Examples: "user:*", "session:*:data", "*cache*"

        Returns:
            list[str]: List of matching keys.

        Example:
            >>> await redis.set("user:1", "data1")
            >>> await redis.set("user:2", "data2")
            >>> users = await redis.keys("user:*")
            >>> print(users)  # ["user:1", "user:2"]
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
        """
        Get a JSON value.

        Retrieves and deserializes a JSON-encoded value.

        Args:
            key (str): Key to retrieve.

        Returns:
            Any | None: Deserialized JSON value, or None if key doesn't exist.

        Example:
            >>> await redis.set_json("user:123", {"name": "John", "age": 30})
            >>> user = await redis.get_json("user:123")
            >>> print(user["name"])  # "John"
        """
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

        Serializes and stores a JSON-encodable value.

        Args:
            key (str): Key name.
            value (Any): JSON-serializable value (dict, list, etc.).
            ttl (int | None): Time-to-live in seconds. Default: None.
            nx (bool): Only set if key doesn't exist. Default: False.
            xx (bool): Only set if key exists. Default: False.

        Returns:
            bool: True if set successfully.

        Example:
            >>> user = {"name": "John", "age": 30, "roles": ["admin"]}
            >>> await redis.set_json("user:123", user, ttl=3600)
        """
        json_str = json.dumps(value, default=str)
        return await self.client.set(key, json_str, ex=ttl, nx=nx, xx=xx)

    # ═══════════════════════════════════════════════════════════════════════════
    #                         HASH OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def hget(self, name: str, key: str) -> str | None:
        """
        Get a hash field value.

        Args:
            name (str): Hash name.
            key (str): Field name.

        Returns:
            str | None: Field value, or None if not exists.

        Example:
            >>> await redis.hset("user:123", "name", "John")
            >>> name = await redis.hget("user:123", "name")
        """
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

        Can set a single field or multiple fields at once.

        Args:
            name (str): Hash name.
            key (str | None): Field name (for single field).
            value (str | None): Field value (for single field).
            mapping (dict[str, str] | None): Dict of field:value pairs.

        Returns:
            int: Number of fields added (not updated).

        Example:
            >>> # Single field
            >>> await redis.hset("user:123", "name", "John")
            >>>
            >>> # Multiple fields
            >>> await redis.hset("user:123", mapping={"age": "30", "city": "NYC"})
        """
        return await self.client.hset(name, key, value, mapping)

    async def hgetall(self, name: str) -> dict[str, str]:
        """
        Get all fields and values from a hash.

        Args:
            name (str): Hash name.

        Returns:
            dict[str, str]: All field:value pairs in the hash.

        Example:
            >>> await redis.hset("user:123", mapping={"name": "John", "age": "30"})
            >>> user = await redis.hgetall("user:123")
            >>> print(user)  # {"name": "John", "age": "30"}
        """
        return await self.client.hgetall(name)

    async def hdel(self, name: str, *keys: str) -> int:
        """
        Delete hash field(s).

        Args:
            name (str): Hash name.
            *keys (str): Fields to delete.

        Returns:
            int: Number of fields deleted.

        Example:
            >>> await redis.hdel("user:123", "age", "city")
        """
        return await self.client.hdel(name, *keys)

    # ═══════════════════════════════════════════════════════════════════════════
    #                         LIST OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def lpush(self, name: str, *values: str) -> int:
        """
        Push values to the left (head) of a list.

        Args:
            name (str): List name.
            *values (str): Values to push.

        Returns:
            int: Length of list after push.

        Example:
            >>> await redis.lpush("queue", "task1", "task2")
        """
        return await self.client.lpush(name, *values)

    async def rpush(self, name: str, *values: str) -> int:
        """
        Push values to the right (tail) of a list.

        Args:
            name (str): List name.
            *values (str): Values to push.

        Returns:
            int: Length of list after push.

        Example:
            >>> await redis.rpush("queue", "task1", "task2")
        """
        return await self.client.rpush(name, *values)

    async def lpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        """
        Pop value(s) from the left (head) of a list.

        Args:
            name (str): List name.
            count (int | None): Number of elements to pop. Default: 1.

        Returns:
            str | list[str] | None: Popped value(s), or None if empty.

        Example:
            >>> await redis.rpush("queue", "a", "b", "c")
            >>> item = await redis.lpop("queue")  # "a"
            >>> items = await redis.lpop("queue", 2)  # ["b", "c"]
        """
        return await self.client.lpop(name, count)

    async def rpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        """
        Pop value(s) from the right (tail) of a list.

        Args:
            name (str): List name.
            count (int | None): Number of elements to pop. Default: 1.

        Returns:
            str | list[str] | None: Popped value(s), or None if empty.

        Example:
            >>> await redis.rpush("queue", "a", "b", "c")
            >>> item = await redis.rpop("queue")  # "c"
        """
        return await self.client.rpop(name, count)

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        """
        Get a range of values from a list.

        Args:
            name (str): List name.
            start (int): Start index (0-based, inclusive).
            end (int): End index (inclusive, -1 for last element).

        Returns:
            list[str]: Values in the specified range.

        Example:
            >>> await redis.rpush("list", "a", "b", "c", "d")
            >>> items = await redis.lrange("list", 0, 2)  # ["a", "b", "c"]
            >>> all_items = await redis.lrange("list", 0, -1)  # ["a", "b", "c", "d"]
        """
        return await self.client.lrange(name, start, end)

    async def llen(self, name: str) -> int:
        """
        Get the length of a list.

        Args:
            name (str): List name.

        Returns:
            int: Length of the list (0 if doesn't exist).

        Example:
            >>> await redis.rpush("list", "a", "b", "c")
            >>> length = await redis.llen("list")  # 3
        """
        return await self.client.llen(name)

    # ═══════════════════════════════════════════════════════════════════════════
    #                         SET OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def sadd(self, name: str, *values: str) -> int:
        """
        Add values to a set.

        Args:
            name (str): Set name.
            *values (str): Values to add.

        Returns:
            int: Number of values added (excludes already existing).

        Example:
            >>> await redis.sadd("tags", "python", "redis", "async")
        """
        return await self.client.sadd(name, *values)

    async def srem(self, name: str, *values: str) -> int:
        """
        Remove values from a set.

        Args:
            name (str): Set name.
            *values (str): Values to remove.

        Returns:
            int: Number of values removed.

        Example:
            >>> await redis.srem("tags", "python")
        """
        return await self.client.srem(name, *values)

    async def smembers(self, name: str) -> set[str]:
        """
        Get all members of a set.

        Args:
            name (str): Set name.

        Returns:
            set[str]: All members of the set.

        Example:
            >>> await redis.sadd("tags", "a", "b", "c")
            >>> tags = await redis.smembers("tags")  # {"a", "b", "c"}
        """
        return await self.client.smembers(name)

    async def sismember(self, name: str, value: str) -> bool:
        """
        Check if value is a member of a set.

        Args:
            name (str): Set name.
            value (str): Value to check.

        Returns:
            bool: True if value is in set.

        Example:
            >>> await redis.sadd("tags", "python")
            >>> await redis.sismember("tags", "python")  # True
            >>> await redis.sismember("tags", "java")    # False
        """
        return await self.client.sismember(name, value)

    async def scard(self, name: str) -> int:
        """
        Get the cardinality (size) of a set.

        Args:
            name (str): Set name.

        Returns:
            int: Number of members in the set.

        Example:
            >>> await redis.sadd("tags", "a", "b", "c")
            >>> size = await redis.scard("tags")  # 3
        """
        return await self.client.scard(name)

    # ═══════════════════════════════════════════════════════════════════════════
    #                         HEALTH CHECK
    # ═══════════════════════════════════════════════════════════════════════════

    async def health_check(self) -> RedisHealthStatus:
        """
        Perform a comprehensive health check.

        Checks connection, measures latency, and retrieves server information
        including version, uptime, memory usage, and client count.

        Returns:
            RedisHealthStatus: Health status with detailed server info.

        Example:
            >>> status = await redis.health_check()
            >>> if status.healthy:
            ...     print(f"Redis {status.redis_version}")
            ...     print(f"Latency: {status.latency_ms:.1f}ms")
            ...     print(f"Memory: {status.used_memory_human}")
            ... else:
            ...     print(f"Unhealthy: {status.error}")
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
        """
        Simple ping check.

        Args:
            None

        Returns:
            bool: True if Redis responds, False otherwise.

        Example:
            >>> if await redis.ping():
            ...     print("Redis is responding")
        """
        try:
            return await self.client.ping()
        except Exception as e:
            logger.debug("Redis ping failed: %s", e)
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

        Classic cache-aside pattern: returns cached value if exists,
        otherwise calls factory to compute, caches, and returns the result.

        Args:
            key (str): Cache key.
            factory (Callable): Sync or async callable to compute value if not cached.
            ttl (int): Time-to-live in seconds. Default: 300 (5 minutes).

        Returns:
            Any: Cached or computed value.

        Example:
            >>> async def fetch_user(user_id):
            ...     return await db.get_user(user_id)
            >>>
            >>> # Will fetch from DB on first call, cache for subsequent calls
            >>> user = await redis.cache_get_or_set(
            ...     key="user:123",
            ...     factory=lambda: fetch_user("123"),
            ...     ttl=3600,
            ... )
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

        Useful for cache invalidation by prefix or pattern.

        Args:
            pattern (str): Glob pattern (e.g., "user:*", "cache:*").

        Returns:
            int: Number of keys deleted.

        Example:
            >>> # Invalidate all user caches
            >>> deleted = await redis.invalidate_pattern("user:*")
            >>> print(f"Invalidated {deleted} keys")
            >>>
            >>> # Invalidate specific user's caches
            >>> await redis.invalidate_pattern("cache:user:123:*")
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

    Returns the globally configured Redis service. If not initialized,
    creates one from environment variables.

    Returns:
        RedisService: The default Redis service instance.

    Example:
        >>> redis = get_redis_client()
        >>> await redis.connect()
        >>> await redis.set("key", "value")
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

    Creates and sets the global default Redis service. Use this at
    application startup to configure Redis.

    Args:
        host (str | None): Redis server hostname.
        port (int | None): Redis server port.
        username (str | None): Service account username.
        password (str | None): Service account password.
        ssl (bool): Enable SSL/TLS. Default: True.
        config (RedisConfig | None): Config instance (overrides other params).
        **kwargs: Additional RedisService arguments.

    Returns:
        RedisService: The initialized default service.

    Example:
        >>> # At application startup
        >>> redis = init_redis_client(
        ...     host="redis.corp.com",
        ...     port=6380,
        ...     username="svc_account",
        ...     password="secret",
        ...     ssl=True,
        ... )
        >>>
        >>> # Later in the application
        >>> redis = get_redis_client()
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

    Use this to inject a pre-configured or mock Redis service.

    Args:
        client (RedisService): Redis service instance to set as default.

    Example:
        >>> custom_redis = RedisService(host="custom.redis.com")
        >>> set_redis_client(custom_redis)
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
