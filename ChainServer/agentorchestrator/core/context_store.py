"""
AgentOrchestrator Context Store - Redis-based External Storage for Large Payloads

Offloads heavy data (SEC filings, news transcripts, earnings data) to Redis,
keeping only lightweight references in chain context.

Key Principles:
1. NEVER lose data - full payloads preserved in Redis
2. NEVER blind-truncate - always keep hashes, lengths, and retrieval links
3. Context stays lightweight - only refs in ChainContext
4. Redis in same container (different port) = low latency, same network

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                      Chain Context (in-memory, lightweight)      │
    │  ┌─────────────────────────────────────────────────────────────┐ │
    │  │  "sec_data" → ContextRef(                                   │ │
    │  │      ref_id="ctx_abc", size=1.2MB, hash="a1b2c3",          │ │
    │  │      summary="10-K filing for AAPL, FY2024...",            │ │
    │  │      key_fields={revenue: 394B, net_income: 97B}           │ │
    │  │  )                                                          │ │
    │  └─────────────────────────────────────────────────────────────┘ │
    └─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │              Redis (same container, port 6380)                   │
    │  ctx_abc → <1.2MB of SEC filing data - NEVER truncated>        │
    │  ctx_xyz → <800KB of news articles - FULL data preserved>      │
    └─────────────────────────────────────────────────────────────────┘

Usage:
    from agentorchestrator.core.context_store import RedisContextStore, ContextRef

    # Initialize store (Redis in same container, different port)
    store = RedisContextStore(host="localhost", port=6380)

    # Store large payload, get reference with summary
    ref = await store.store(
        key="sec_filing_aapl",
        data=large_filing_data,
        summary="10-K Annual Report for Apple Inc., FY2024",
        key_fields={"revenue": "394.3B", "net_income": "97.0B"},
    )

    # Store ref in context (lightweight - ~500 bytes instead of 1.2MB)
    ctx.set("sec_data", ref)

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

    Designed to run Redis in the same container on a different port
    for low-latency access while keeping data external to Python memory.

    Memory Configuration:
        The maxmemory setting controls how much memory Redis will use.
        When maxmemory is reached, Redis uses the eviction policy (default: allkeys-lru).

        Sizing guidelines:
        - Small workloads: 128MB-256MB (handles ~100-500 concurrent contexts)
        - Medium workloads: 512MB-1GB (handles ~1000-5000 concurrent contexts)
        - Large workloads: 2GB-4GB (handles ~10000+ concurrent contexts)

    Setup with external Redis:
        # Start Redis in same container (e.g., supervisord or docker-compose)
        redis-server --port 6380 --maxmemory 512mb --maxmemory-policy allkeys-lru

    Usage:
        # Configure with memory limit (sets maxmemory on Redis server)
        store = RedisContextStore(
            host="localhost",
            port=6380,
            maxmemory="512mb",  # Options: "128mb", "256mb", "512mb", "1gb", "2gb"
        )

        ref = await store.store("sec_filing", large_data, summary="10-K for AAPL")
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6380,  # Different port for context store
        db: int = 0,
        password: str | None = None,
        key_prefix: str = "agentorchestrator:ctx:",
        max_connections: int = 10,
        maxmemory: str | None = None,
        maxmemory_policy: str = "allkeys-lru",
    ):
        """
        Initialize Redis context store.

        Args:
            host: Redis host
            port: Redis port (default 6380 to avoid conflicts with other Redis instances)
            db: Redis database number
            password: Redis password
            key_prefix: Prefix for all context keys
            max_connections: Maximum connection pool size
            maxmemory: Memory limit for Redis (e.g., "128mb", "512mb", "1gb", "2gb").
                      If provided, will configure Redis server on first connection.
            maxmemory_policy: Eviction policy when maxmemory is reached.
                             Options: "allkeys-lru" (default), "volatile-lru",
                             "allkeys-random", "volatile-random", "volatile-ttl", "noeviction"
        """
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._key_prefix = key_prefix
        self._max_connections = max_connections
        self._maxmemory = maxmemory
        self._maxmemory_policy = maxmemory_policy
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

            self._redis = redis.Redis(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password,
                max_connections=self._max_connections,
                decode_responses=False,  # We handle bytes
            )

            # Configure memory limits if specified
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
        async def fetch_sec_data(ctx):
            raw_filings = await fetch_large_filings()

            # Offload if large, keep ref in context
            result = await offload_to_redis(
                ctx, "sec_filings", raw_filings,
                store=ctx.get("_context_store"),
                threshold_bytes=100_000,
                summary="SEC 10-K filings for AAPL",
                key_fields={"ticker": "AAPL", "filing_type": "10-K"},
            )

            ctx.set("sec_data", result)  # ContextRef or raw data
            return {"sec_data": result}
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

    Looks for common financial/business fields to preserve in reference.
    """
    key_fields = {}

    if isinstance(data, dict):
        # Common financial fields
        for field in [
            "ticker", "symbol", "company_name", "cik",
            "revenue", "net_income", "ebitda", "market_cap",
            "fiscal_year", "fiscal_quarter", "filing_date",
            "event_date", "earnings_date",
        ]:
            if field in data:
                key_fields[field] = data[field]

        # Look for nested common fields
        if "company_info" in data and isinstance(data["company_info"], dict):
            for field in ["ticker", "name", "cik"]:
                if field in data["company_info"]:
                    key_fields[f"company_{field}"] = data["company_info"][field]

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
        backend: "memory" or "redis"
        **kwargs: Backend-specific configuration

    Returns:
        ContextStore instance
    """
    if backend == "memory":
        return InMemoryContextStore()
    elif backend == "redis":
        return RedisContextStore(**kwargs)
    else:
        raise ValueError(f"Unknown context store backend: {backend}")


# Type hint import for context
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentorchestrator.core.context import ChainContext