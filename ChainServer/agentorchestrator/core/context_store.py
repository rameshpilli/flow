"""
AgentOrchestrator Context Store - External Storage for Large Payloads

Offloads large data to external storage (Redis, mem0, etc.),
keeping only lightweight references in chain context.

Key Principles:
1. NEVER lose data - full payloads preserved in storage
2. NEVER blind-truncate - always keep hashes, lengths, and retrieval links
3. Context stays lightweight - only refs in ChainContext
4. Pluggable backends - Redis, mem0, or custom stores

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                      Chain Context (in-memory, lightweight)      │
    │  ┌─────────────────────────────────────────────────────────────┐ │
    │  │  "large_data" → ContextRef(                                 │ │
    │  │      ref_id="ctx_abc", size=1.2MB, hash="a1b2c3",          │ │
    │  │      summary="Data summary...",                             │ │
    │  │      key_fields={key1: val1, key2: val2}                   │ │
    │  │  )                                                          │ │
    │  └─────────────────────────────────────────────────────────────┘ │
    └─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │              Context Store (Redis, mem0, etc.)                   │
    │  ctx_abc → <1.2MB of data - NEVER truncated>                   │
    │  ctx_xyz → <800KB of data - FULL data preserved>               │
    └─────────────────────────────────────────────────────────────────┘

Usage:
    from agentorchestrator.core.context_store import RedisContextStore, ContextRef

    # Initialize store
    store = RedisContextStore(host="localhost", port=6379)

    # Store large payload, get reference with summary
    ref = await store.store(
        key="my_data",
        data=large_data,
        summary="Description of the data",
        key_fields={"key1": "value1", "key2": "value2"},
    )

    # Store ref in context (lightweight - ~500 bytes instead of 1.2MB)
    ctx.set("data_ref", ref)

    # Later, retrieve full data (NEVER lost)
    data = await store.retrieve(ref)
"""

import hashlib
import json
import logging
import pickle
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextRef:
    """
    Lightweight reference to data stored in Redis.

    Contains enough metadata to understand what's stored without
    retrieving it, plus the ability to retrieve full data on demand.

    Key principle: NEVER lose information
    - size_bytes: Know exactly how big the data is
    - content_hash: Verify integrity, enable deduplication
    - summary: Human-readable summary of content
    - key_fields: Critical extracted fields (numbers, dates, entities)
    - item_count: For lists, how many items
    - omitted_count: If items were capped, how many were omitted
    """
    ref_id: str
    size_bytes: int
    content_hash: str  # SHA256 for integrity/dedup
    content_type: str = "application/json"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    ttl_seconds: int = 3600  # Default 1 hour

    # Summary info (NEVER blind-truncate - always keep these)
    summary: str = ""  # Human-readable summary
    key_fields: dict[str, Any] = field(default_factory=dict)  # Critical extracted fields

    # For list/collection data
    item_count: int = 0  # Total items in original data
    omitted_count: int = 0  # Items not included (if capped)

    # Source tracking
    source_step: str | None = None
    source_agent: str | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # For context serialization
    _is_context_ref: bool = field(default=True, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict (for logging/API responses)."""
        return {
            "_is_context_ref": True,
            "ref_id": self.ref_id,
            "size_bytes": self.size_bytes,
            "size_human": self._human_size(self.size_bytes),
            "content_hash": self.content_hash,
            "content_type": self.content_type,
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
            # Summary info - ALWAYS included
            "summary": self.summary,
            "key_fields": self.key_fields,
            "item_count": self.item_count,
            "omitted_count": self.omitted_count,
            # Source tracking
            "source_step": self.source_step,
            "source_agent": self.source_agent,
            "metadata": self.metadata,
            # Retrieval info
            "_retrieve_hint": f"Use store.retrieve(ref) to get full {self._human_size(self.size_bytes)} payload",
        }

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        """Convert bytes to human readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextRef":
        """Reconstruct from dict."""
        return cls(
            ref_id=data["ref_id"],
            size_bytes=data["size_bytes"],
            content_hash=data["content_hash"],
            content_type=data.get("content_type", "application/json"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            ttl_seconds=data.get("ttl_seconds", 3600),
            summary=data.get("summary", ""),
            key_fields=data.get("key_fields", {}),
            item_count=data.get("item_count", 0),
            omitted_count=data.get("omitted_count", 0),
            source_step=data.get("source_step"),
            source_agent=data.get("source_agent"),
            metadata=data.get("metadata", {}),
        )

    def __repr__(self) -> str:
        summary_preview = self.summary[:50] + "..." if len(self.summary) > 50 else self.summary
        return f"ContextRef({self.ref_id}, {self._human_size(self.size_bytes)}, '{summary_preview}')"


class ContextRefNotFoundError(Exception):
    """Raised when context ref is not found or has expired."""

    def __init__(self, ref_id: str):
        self.ref_id = ref_id
        super().__init__(f"Context ref not found (may have expired): {ref_id}")


class ContextStore(ABC):
    """
    Abstract base class for context storage backends.

    Implementations provide external storage for large payloads.
    """

    @abstractmethod
    async def store(
        self,
        key: str,
        data: Any,
        ttl_seconds: int = 3600,
        summary: str = "",
        key_fields: dict[str, Any] | None = None,
        source_step: str | None = None,
        source_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextRef:
        """
        Store data and return a lightweight reference.

        Args:
            key: Logical key for the data (will be prefixed with unique ID)
            data: The data to store (will be serialized)
            ttl_seconds: Time-to-live in seconds
            summary: Human-readable summary of the content
            key_fields: Critical fields to preserve in reference
            source_step: Step that produced this data
            source_agent: Agent that fetched this data
            metadata: Additional metadata

        Returns:
            ContextRef that can be stored in ChainContext
        """
        pass

    @abstractmethod
    async def retrieve(self, ref: ContextRef) -> Any:
        """
        Retrieve full data from a context reference.

        Args:
            ref: The context reference

        Returns:
            Original data (deserialized) - NEVER truncated

        Raises:
            ContextRefNotFoundError: If data has expired or doesn't exist
        """
        pass

    @abstractmethod
    async def delete(self, ref: ContextRef) -> bool:
        """Delete stored data."""
        pass

    @abstractmethod
    async def exists(self, ref: ContextRef) -> bool:
        """Check if data exists."""
        pass

    def _serialize(self, data: Any) -> bytes:
        """Serialize data for storage."""
        try:
            # Try JSON first (human readable, widely compatible)
            return json.dumps(data, default=str).encode("utf-8")
        except (TypeError, ValueError):
            # Fall back to pickle for complex objects
            return pickle.dumps(data)

    def _deserialize(self, data: bytes, content_type: str = "application/json") -> Any:
        """Deserialize data from storage."""
        if content_type == "application/json":
            try:
                return json.loads(data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        return pickle.loads(data)

    def _compute_hash(self, data: bytes) -> str:
        """Compute SHA256 hash of data."""
        return hashlib.sha256(data).hexdigest()[:16]

    def _generate_id(self, key: str) -> str:
        """Generate unique context ref ID."""
        return f"ctx_{key}_{uuid.uuid4().hex[:8]}"

    def _count_items(self, data: Any) -> int:
        """Count items in data (for lists/dicts)."""
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return len(data)
        return 1


class InMemoryContextStore(ContextStore):
    """
    In-memory context store for development and testing.

    Data is lost when process exits. Use RedisContextStore for production.
    """

    def __init__(self):
        self._store: dict[str, tuple[bytes, str, datetime]] = {}

    async def store(
        self,
        key: str,
        data: Any,
        ttl_seconds: int = 3600,
        summary: str = "",
        key_fields: dict[str, Any] | None = None,
        source_step: str | None = None,
        source_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextRef:
        serialized = self._serialize(data)
        ref_id = self._generate_id(key)
        content_hash = self._compute_hash(serialized)

        # Determine content type
        content_type = "application/json"
        try:
            json.dumps(data, default=str)
        except (TypeError, ValueError):
            content_type = "application/pickle"

        self._store[ref_id] = (serialized, content_type, datetime.utcnow())

        ref = ContextRef(
            ref_id=ref_id,
            size_bytes=len(serialized),
            content_hash=content_hash,
            content_type=content_type,
            ttl_seconds=ttl_seconds,
            summary=summary,
            key_fields=key_fields or {},
            item_count=self._count_items(data),
            source_step=source_step,
            source_agent=source_agent,
            metadata=metadata or {},
        )

        logger.debug(f"Stored in memory: {ref}")
        return ref

    async def retrieve(self, ref: ContextRef) -> Any:
        if ref.ref_id not in self._store:
            raise ContextRefNotFoundError(ref.ref_id)

        serialized, content_type, _ = self._store[ref.ref_id]
        return self._deserialize(serialized, content_type)

    async def delete(self, ref: ContextRef) -> bool:
        if ref.ref_id in self._store:
            del self._store[ref.ref_id]
            return True
        return False

    async def exists(self, ref: ContextRef) -> bool:
        return ref.ref_id in self._store


class RedisContextStore(ContextStore):
    """
    Redis-based context store for production use.

    Supports multiple deployment scenarios:
    - Same container: host="localhost" (your current Docker setup)
    - Kubernetes: host="redis-service.namespace"
    - AWS ElastiCache: host="xxx.cache.amazonaws.com", ssl=True
    - Azure Cache: host="xxx.redis.cache.windows.net", ssl=True

    Memory Configuration:
        The maxmemory setting controls how much memory Redis will use.
        When maxmemory is reached, Redis uses the eviction policy (default: allkeys-lru).

        Sizing guidelines:
        - Small workloads: 128MB-256MB (handles ~100-500 concurrent contexts)
        - Medium workloads: 512MB-1GB (handles ~1000-5000 concurrent contexts)
        - Large workloads: 2GB-4GB (handles ~10000+ concurrent contexts)

    Usage:
        # Local/same container
        store = RedisContextStore(host="localhost", port=6379)

        # Kubernetes
        store = RedisContextStore(host="redis-service.default.svc.cluster.local")

        # AWS ElastiCache (TLS)
        store = RedisContextStore(
            host="my-cluster.abc123.use1.cache.amazonaws.com",
            ssl=True,
        )

        ref = await store.store("large_data", data, summary="Data description")
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        key_prefix: str = "agentorchestrator:ctx:",
        max_connections: int = 10,
        maxmemory: str | None = None,
        maxmemory_policy: str = "allkeys-lru",
        ssl: bool = False,
        ssl_cert_reqs: str | None = None,
    ):
        """
        Initialize Redis context store.

        Args:
            host: Redis host (localhost, K8s service name, or cloud endpoint)
            port: Redis port (default 6379)
            db: Redis database number
            password: Redis password (required for most cloud Redis)
            key_prefix: Prefix for all context keys
            max_connections: Maximum connection pool size
            maxmemory: Memory limit for Redis (e.g., "128mb", "512mb", "1gb", "2gb").
                      If provided, will configure Redis server on first connection.
                      Note: May not work on managed Redis services.
            maxmemory_policy: Eviction policy when maxmemory is reached.
                             Options: "allkeys-lru" (default), "volatile-lru",
                             "allkeys-random", "volatile-random", "volatile-ttl", "noeviction"
            ssl: Enable SSL/TLS connection (required for ElastiCache, Azure, etc.)
            ssl_cert_reqs: SSL certificate requirements ("none", "optional", "required")
        """
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._key_prefix = key_prefix
        self._max_connections = max_connections
        self._maxmemory = maxmemory
        self._maxmemory_policy = maxmemory_policy
        self._ssl = ssl
        self._ssl_cert_reqs = ssl_cert_reqs
        self._redis = None
        self._memory_configured = False

    async def _get_redis(self):
        """Lazy initialization of Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as redis
            except ImportError:
                raise ImportError(
                    "redis package required for RedisContextStore. "
                    "Install with: pip install redis"
                )

            # Build connection kwargs
            conn_kwargs = {
                "host": self._host,
                "port": self._port,
                "db": self._db,
                "password": self._password,
                "max_connections": self._max_connections,
                "decode_responses": False,  # We handle bytes
            }

            # Add SSL config if enabled
            if self._ssl:
                import ssl as ssl_module
                conn_kwargs["ssl"] = True
                if self._ssl_cert_reqs:
                    cert_reqs_map = {
                        "none": ssl_module.CERT_NONE,
                        "optional": ssl_module.CERT_OPTIONAL,
                        "required": ssl_module.CERT_REQUIRED,
                    }
                    conn_kwargs["ssl_cert_reqs"] = cert_reqs_map.get(
                        self._ssl_cert_reqs.lower(), ssl_module.CERT_REQUIRED
                    )

            self._redis = redis.Redis(**conn_kwargs)

            # Configure memory limits if specified (may not work on managed services)
            if self._maxmemory and not self._memory_configured:
                await self._configure_memory()

        return self._redis

    async def _configure_memory(self) -> None:
        """Configure Redis memory settings."""
        if not self._redis or self._memory_configured:
            return

        try:
            # Set maxmemory
            await self._redis.config_set("maxmemory", self._maxmemory)
            await self._redis.config_set("maxmemory-policy", self._maxmemory_policy)
            self._memory_configured = True

            logger.info(
                f"Redis memory configured: maxmemory={self._maxmemory}, "
                f"policy={self._maxmemory_policy}"
            )
        except Exception as e:
            logger.warning(
                f"Could not configure Redis memory settings: {e}. "
                f"This may require Redis admin privileges. "
                f"Configure Redis directly with: redis-cli CONFIG SET maxmemory {self._maxmemory}"
            )

    def _redis_key(self, ref_id: str) -> str:
        """Get Redis key for ref ID."""
        return f"{self._key_prefix}{ref_id}"

    async def store(
        self,
        key: str,
        data: Any,
        ttl_seconds: int = 3600,
        summary: str = "",
        key_fields: dict[str, Any] | None = None,
        source_step: str | None = None,
        source_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextRef:
        redis = await self._get_redis()

        serialized = self._serialize(data)
        ref_id = self._generate_id(key)
        content_hash = self._compute_hash(serialized)

        # Determine content type
        content_type = "application/json"
        try:
            json.dumps(data, default=str)
        except (TypeError, ValueError):
            content_type = "application/pickle"

        # Store in Redis with TTL
        redis_key = self._redis_key(ref_id)
        await redis.setex(redis_key, ttl_seconds, serialized)

        # Store metadata separately (for inspection without loading data)
        meta_key = f"{redis_key}:meta"
        meta = {
            "content_type": content_type,
            "size_bytes": len(serialized),
            "content_hash": content_hash,
            "created_at": datetime.utcnow().isoformat(),
            "summary": summary,
            "key_fields": key_fields or {},
        }
        await redis.setex(meta_key, ttl_seconds, json.dumps(meta).encode())

        ref = ContextRef(
            ref_id=ref_id,
            size_bytes=len(serialized),
            content_hash=content_hash,
            content_type=content_type,
            ttl_seconds=ttl_seconds,
            summary=summary,
            key_fields=key_fields or {},
            item_count=self._count_items(data),
            source_step=source_step,
            source_agent=source_agent,
            metadata=metadata or {},
        )

        logger.debug(f"Stored in Redis: {ref}")
        return ref

    async def retrieve(self, ref: ContextRef) -> Any:
        redis = await self._get_redis()
        redis_key = self._redis_key(ref.ref_id)

        serialized = await redis.get(redis_key)
        if serialized is None:
            raise ContextRefNotFoundError(ref.ref_id)

        return self._deserialize(serialized, ref.content_type)

    async def delete(self, ref: ContextRef) -> bool:
        redis = await self._get_redis()
        redis_key = self._redis_key(ref.ref_id)
        meta_key = f"{redis_key}:meta"

        deleted = await redis.delete(redis_key, meta_key)
        return deleted > 0

    async def exists(self, ref: ContextRef) -> bool:
        redis = await self._get_redis()
        redis_key = self._redis_key(ref.ref_id)
        return await redis.exists(redis_key) > 0

    async def get_stats(self) -> dict[str, Any]:
        """Get context store statistics including memory usage."""
        redis = await self._get_redis()

        # Count refs
        pattern = f"{self._key_prefix}*"
        keys = []
        async for key in redis.scan_iter(match=pattern):
            if not key.decode().endswith(":meta"):
                keys.append(key)

        # Calculate total size
        total_size = 0
        for key in keys[:100]:  # Limit for performance
            size = await redis.strlen(key)
            total_size += size

        # Get memory info
        memory_info = {}
        try:
            info = await redis.info("memory")
            memory_info = {
                "used_memory": info.get("used_memory"),
                "used_memory_human": info.get("used_memory_human"),
                "used_memory_peak": info.get("used_memory_peak"),
                "used_memory_peak_human": info.get("used_memory_peak_human"),
                "maxmemory": info.get("maxmemory"),
                "maxmemory_human": info.get("maxmemory_human"),
                "maxmemory_policy": info.get("maxmemory_policy"),
            }
        except Exception as e:
            logger.debug(f"Could not get Redis memory info: {e}")

        return {
            "backend": "redis",
            "host": self._host,
            "port": self._port,
            "ref_count": len(keys),
            "sample_size_bytes": total_size,
            "memory": memory_info,
            "configured_maxmemory": self._maxmemory,
            "configured_policy": self._maxmemory_policy,
        }

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()


# ═══════════════════════════════════════════════════════════════════════════════
#                      MEM0 CONTEXT STORE (SEMANTIC MEMORY)
# ═══════════════════════════════════════════════════════════════════════════════


class Mem0ContextStore(ContextStore):
    """
    Mem0-based context store for semantic/long-term memory.

    Unlike Redis (key-value cache), mem0 provides:
    - Semantic search across stored memories
    - Automatic summarization and deduplication
    - User/session scoped memory
    - Cross-session persistence

    Use cases:
    - Remember user preferences across sessions
    - Store conversation history with semantic retrieval
    - Build up knowledge about entities over time

    Usage:
        # Cloud mem0
        store = Mem0ContextStore(api_key="m0-xxx")

        # Self-hosted mem0
        store = Mem0ContextStore(host="http://mem0.internal:8080")

        # Store with semantic indexing
        ref = await store.store(
            "user_preference",
            {"format": "json", "detail_level": "high"},
            summary="User prefers JSON output with high detail",
        )

        # Search semantically
        results = await store.search("what format does user prefer")
    """

    def __init__(
        self,
        api_key: str | None = None,
        host: str | None = None,
        user_id: str | None = None,
        org_id: str | None = None,
        agent_id: str | None = None,
    ):
        """
        Initialize mem0 context store.

        Args:
            api_key: mem0 cloud API key (for managed service)
            host: Self-hosted mem0 endpoint URL
            user_id: User ID for scoped memory (recommended)
            org_id: Organization ID for shared memory
            agent_id: Agent ID for agent-specific memory
        """
        self._api_key = api_key
        self._host = host
        self._user_id = user_id
        self._org_id = org_id
        self._agent_id = agent_id
        self._client = None
        self._ref_cache: dict[str, dict] = {}  # Local cache for ref metadata

    async def _get_client(self):
        """Lazy initialization of mem0 client."""
        if self._client is None:
            try:
                from mem0 import MemoryClient, Memory
            except ImportError:
                raise ImportError(
                    "mem0ai package required for Mem0ContextStore. "
                    "Install with: pip install mem0ai"
                )

            if self._api_key:
                # Cloud mem0
                self._client = MemoryClient(api_key=self._api_key)
                logger.info("Connected to mem0 cloud")
            elif self._host:
                # Self-hosted - use Memory with custom config
                config = {
                    "version": "v1.1",
                    "custom_endpoint": self._host,
                }
                self._client = Memory.from_config(config)
                logger.info(f"Connected to self-hosted mem0 at {self._host}")
            else:
                # Local memory (development)
                self._client = Memory()
                logger.info("Using local mem0 memory (development mode)")

        return self._client

    async def store(
        self,
        key: str,
        data: Any,
        ttl_seconds: int = 3600,
        summary: str = "",
        key_fields: dict[str, Any] | None = None,
        source_step: str | None = None,
        source_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextRef:
        client = await self._get_client()

        serialized = self._serialize(data)
        ref_id = self._generate_id(key)
        content_hash = self._compute_hash(serialized)

        # Prepare metadata for mem0
        mem0_metadata = {
            "ref_id": ref_id,
            "key": key,
            "content_hash": content_hash,
            "size_bytes": len(serialized),
            "source_step": source_step,
            "source_agent": source_agent,
            **(metadata or {}),
            **(key_fields or {}),
        }

        # Create memory content (summary + key data)
        memory_content = summary or _generate_summary(key, data, len(serialized))
        if key_fields:
            fields_str = ", ".join(f"{k}: {v}" for k, v in key_fields.items())
            memory_content = f"{memory_content}\nKey fields: {fields_str}"

        # Store in mem0
        add_kwargs = {"messages": [{"role": "user", "content": memory_content}]}
        if self._user_id:
            add_kwargs["user_id"] = self._user_id
        if self._agent_id:
            add_kwargs["agent_id"] = self._agent_id
        add_kwargs["metadata"] = mem0_metadata

        result = client.add(**add_kwargs)
        logger.debug(f"Stored in mem0: {result}")

        # Cache the full data locally (mem0 is for semantic search, not raw storage)
        self._ref_cache[ref_id] = {
            "data": serialized,
            "content_type": "application/json",
            "mem0_result": result,
        }

        ref = ContextRef(
            ref_id=ref_id,
            size_bytes=len(serialized),
            content_hash=content_hash,
            content_type="application/json",
            ttl_seconds=ttl_seconds,
            summary=summary,
            key_fields=key_fields or {},
            item_count=self._count_items(data),
            source_step=source_step,
            source_agent=source_agent,
            metadata={"mem0_result": result, **(metadata or {})},
        )

        return ref

    async def retrieve(self, ref: ContextRef) -> Any:
        # First check local cache
        if ref.ref_id in self._ref_cache:
            cached = self._ref_cache[ref.ref_id]
            return self._deserialize(cached["data"], cached.get("content_type", "application/json"))

        raise ContextRefNotFoundError(ref.ref_id)

    async def delete(self, ref: ContextRef) -> bool:
        if ref.ref_id in self._ref_cache:
            del self._ref_cache[ref.ref_id]
            return True
        return False

    async def exists(self, ref: ContextRef) -> bool:
        return ref.ref_id in self._ref_cache

    async def search(
        self,
        query: str,
        limit: int = 10,
        user_id: str | None = None,
    ) -> list[dict]:
        """
        Search memories semantically.

        Args:
            query: Natural language search query
            limit: Maximum results to return
            user_id: Override default user_id

        Returns:
            List of matching memories with scores
        """
        client = await self._get_client()

        search_kwargs = {"query": query, "limit": limit}
        if user_id or self._user_id:
            search_kwargs["user_id"] = user_id or self._user_id
        if self._agent_id:
            search_kwargs["agent_id"] = self._agent_id

        results = client.search(**search_kwargs)
        return results

    async def get_all_memories(
        self,
        user_id: str | None = None,
    ) -> list[dict]:
        """Get all memories for a user."""
        client = await self._get_client()

        get_kwargs = {}
        if user_id or self._user_id:
            get_kwargs["user_id"] = user_id or self._user_id
        if self._agent_id:
            get_kwargs["agent_id"] = self._agent_id

        return client.get_all(**get_kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
#                      CONTEXT INTEGRATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


async def offload_to_redis(
    ctx: "ChainContext",
    key: str,
    data: Any,
    store: ContextStore,
    threshold_bytes: int = 100_000,  # 100KB default
    ttl_seconds: int = 3600,
    summary: str = "",
    key_fields: dict[str, Any] | None = None,
    extract_key_fields: bool = True,
) -> ContextRef | Any:
    """
    Conditionally offload large data to Redis.

    If data is larger than threshold, stores in Redis and returns ref.
    Otherwise, returns data as-is.

    NEVER loses data - full payload preserved in Redis.

    Usage:
        from agentorchestrator.core.context_store import offload_to_redis

        @forge.step
        async def fetch_data(ctx):
            large_data = await fetch_large_payload()

            # Offload if large, keep ref in context
            result = await offload_to_redis(
                ctx, "my_data", large_data,
                store=ctx.get("_context_store"),
                threshold_bytes=100_000,
                summary="Large data payload",
                key_fields={"type": "report", "count": 100},
            )

            ctx.set("data_ref", result)  # ContextRef or raw data
            return {"data_ref": result}
    """
    # Estimate size
    try:
        serialized = json.dumps(data, default=str).encode()
        size = len(serialized)
    except (TypeError, ValueError):
        serialized = pickle.dumps(data)
        size = len(serialized)

    if size < threshold_bytes:
        logger.debug(f"Data '{key}' is small ({size} bytes), keeping in context")
        return data

    # Extract key fields automatically if requested
    extracted_fields = key_fields or {}
    if extract_key_fields and not key_fields:
        extracted_fields = _extract_key_fields(data)

    # Generate summary if not provided
    if not summary:
        summary = _generate_summary(key, data, size)

    # Get source info from context
    source_step = ctx.current_step
    source_agent = None
    if "agent" in key.lower():
        source_agent = key

    # Offload to Redis
    logger.info(f"Offloading '{key}' to Redis ({size} bytes)")
    ref = await store.store(
        key=key,
        data=data,
        ttl_seconds=ttl_seconds,
        summary=summary,
        key_fields=extracted_fields,
        source_step=source_step,
        source_agent=source_agent,
    )
    return ref


async def resolve_context_ref(
    data: Any,
    store: ContextStore,
) -> Any:
    """
    Resolve a ContextRef to its full data.

    If data is not a ContextRef, returns as-is.

    Usage:
        sec_data = ctx.get("sec_data")
        full_data = await resolve_context_ref(sec_data, store)
    """
    if isinstance(data, ContextRef):
        return await store.retrieve(data)
    if isinstance(data, dict) and data.get("_is_context_ref"):
        ref = ContextRef.from_dict(data)
        return await store.retrieve(ref)
    return data


def is_context_ref(data: Any) -> bool:
    """Check if data is a context reference."""
    if isinstance(data, ContextRef):
        return True
    if isinstance(data, dict) and data.get("_is_context_ref"):
        return True
    return False


def _extract_key_fields(data: Any) -> dict[str, Any]:
    """
    Auto-extract key fields from data.

    Extracts common fields that are typically important to preserve in references.
    Domain-specific extraction should be done at the application level.
    """
    key_fields = {}

    if isinstance(data, dict):
        # Common fields that are typically important
        for field in [
            "id", "name", "type", "status", "date", "created_at", "updated_at",
            "count", "total", "value", "result",
        ]:
            if field in data:
                key_fields[field] = data[field]

        # Record top-level keys for reference
        key_fields["keys"] = list(data.keys())[:10]

    elif isinstance(data, list) and len(data) > 0:
        # For lists, get count and sample of types
        key_fields["count"] = len(data)
        if isinstance(data[0], dict):
            key_fields["sample_keys"] = list(data[0].keys())[:5]

    return key_fields


def _generate_summary(key: str, data: Any, size: int) -> str:
    """Generate a human-readable summary of data."""
    size_str = ContextRef._human_size(size)

    if isinstance(data, list):
        return f"{len(data)} items ({size_str}), key: {key}"
    elif isinstance(data, dict):
        keys_preview = ", ".join(list(data.keys())[:5])
        return f"Dict with {len(data)} keys ({size_str}): {keys_preview}..."
    elif isinstance(data, str):
        preview = data[:100].replace("\n", " ")
        return f"Text ({size_str}): {preview}..."
    else:
        return f"{type(data).__name__} ({size_str}), key: {key}"


# ═══════════════════════════════════════════════════════════════════════════════
#                      FACTORY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════


def create_context_store(
    backend: str = "memory",
    **kwargs,
) -> ContextStore:
    """
    Factory function to create context store instances.

    Args:
        backend: "memory", "redis", or "mem0"
        **kwargs: Backend-specific configuration

    Backend-specific kwargs:

        redis:
            host: Redis host (default: localhost)
            port: Redis port (default: 6379)
            db: Database number (default: 0)
            password: Redis password
            key_prefix: Key prefix (default: agentorchestrator:ctx:)
            max_connections: Pool size (default: 10)
            maxmemory: Memory limit (e.g., "128mb")
            maxmemory_policy: Eviction policy (default: allkeys-lru)
            ssl: Enable SSL/TLS (default: False)
            ssl_cert_reqs: SSL cert requirements

        mem0:
            api_key: mem0 cloud API key
            host: Self-hosted mem0 URL
            user_id: User ID for scoped memory
            org_id: Organization ID
            agent_id: Agent ID

    Returns:
        ContextStore instance

    Usage:
        # Development (no dependencies)
        store = create_context_store(backend="memory")

        # Production Redis (same container)
        store = create_context_store(
            backend="redis",
            host="localhost",
            port=6379,
        )

        # Kubernetes Redis
        store = create_context_store(
            backend="redis",
            host="redis-service.default.svc.cluster.local",
        )

        # AWS ElastiCache
        store = create_context_store(
            backend="redis",
            host="my-cluster.abc123.use1.cache.amazonaws.com",
            ssl=True,
        )

        # mem0 cloud
        store = create_context_store(
            backend="mem0",
            api_key="m0-xxx",
            user_id="user-123",
        )
    """
    if backend == "memory":
        return InMemoryContextStore()

    elif backend == "redis":
        return RedisContextStore(**kwargs)

    elif backend == "mem0":
        return Mem0ContextStore(**kwargs)

    else:
        logger.warning(f"Unknown context store backend: {backend}, falling back to memory")
        return InMemoryContextStore()


# Type hint import for context
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentorchestrator.core.context import ChainContext