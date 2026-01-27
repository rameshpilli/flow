"""
AgentOrchestrator Vector Store Service
======================================

This module provides a lightweight vector store service with in-memory
storage for development and Cohere Compass for enterprise RAG scenarios.
It acts as the single façade that callers import so they can switch between
local memory and Compass without changing code, centralizing config (env),
TLS/health handling, and future cross-backend behaviors.

The VectorStoreService offers:
- In-memory vector storage for development and testing
- Cohere Compass integration for managed enterprise deployments
- Pluggable embedding functions for in-memory mode
- Simple upsert and query API

Classes:
    VectorDocument: Document to store in the vector index.
    VectorMatch: Query match result with similarity score.
    VectorStoreConfig: Configuration for vector store connectivity.
    InMemoryVectorStore: Simple in-memory vector store implementation.
    VectorStoreService: Main facade for vector store operations.

Usage:
    from agentorchestrator.services import VectorStoreService, VectorDocument

    # In-memory (for development)
    store = VectorStoreService()
    await store.upsert([
        VectorDocument(id="doc1", text="Python is great", metadata={"lang": "en"}),
        VectorDocument(id="doc2", text="Machine learning basics", metadata={"topic": "ml"}),
    ])
    results = await store.query("programming languages", top_k=5)

    # Cohere Compass (enterprise RAG)
    store = VectorStoreService(config=VectorStoreConfig(
        host="https://compass.corp.com",
        api_key="sk-xxx",
        namespace="my-app",
        provider="cohere_compass",
    ))

Example:
    >>> from agentorchestrator.services import VectorStoreService, VectorDocument
    >>>
    >>> # Create service with in-memory store
    >>> store = VectorStoreService()
    >>>
    >>> # Add documents
    >>> docs = [
    ...     VectorDocument(id="1", text="Python programming guide"),
    ...     VectorDocument(id="2", text="JavaScript for beginners"),
    ...     VectorDocument(id="3", text="Data science with Python"),
    ... ]
    >>> await store.upsert(docs)
    >>>
    >>> # Query for similar documents
    >>> matches = await store.query("Python tutorials", top_k=2)
    >>> for match in matches:
    ...     print(f"{match.text} (score: {match.score:.2f})")

See Also:
    - agentorchestrator.services.mem0: Semantic memory for conversations.
    - agentorchestrator.services.redis: Key-value caching.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional

from agentorchestrator.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                             DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class VectorDocument:
    """
    Document to store in the vector index.

    Represents a text document with an ID, content, and optional metadata.
    The text will be embedded and stored for similarity search.

    Attributes:
        id (str): Unique identifier for the document.
        text (str): The text content to embed and index.
        metadata (dict[str, Any]): Additional metadata for filtering/retrieval.
            Common metadata: source, timestamp, category, author.

    Example:
        >>> doc = VectorDocument(
        ...     id="doc-123",
        ...     text="Python is a versatile programming language",
        ...     metadata={"category": "programming", "source": "tutorial"},
        ... )
        >>>
        >>> # Batch creation
        >>> docs = [
        ...     VectorDocument(id="1", text="First document"),
        ...     VectorDocument(id="2", text="Second document", metadata={"tag": "important"}),
        ... ]
    """

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorMatch:
    """
    Query match result from vector search.

    Contains the matched document information along with its
    similarity score to the query.

    Attributes:
        id (str): Document ID that matched.
        text (str): The text content of the matched document.
        score (float): Similarity score (0.0-1.0 for cosine similarity).
            Higher scores indicate more relevant matches.
        metadata (dict[str, Any]): Document metadata.

    Example:
        >>> # Typically returned from query operations
        >>> matches = await store.query("machine learning")
        >>> for match in matches:
        ...     print(f"ID: {match.id}")
        ...     print(f"Text: {match.text}")
        ...     print(f"Score: {match.score:.3f}")
        ...     print(f"Metadata: {match.metadata}")
    """

    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
#                             CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class VectorStoreConfig:
    """
    Configuration for vector store connectivity.

    Supports both in-memory storage (for development) and remote
    Cohere Compass deployments (for production).
    """

    host: str | None = None
    api_key: str | None = None
    namespace: str = "default"
    timeout: float = 30.0
    provider: str = "memory"  # "memory", "cohere_compass"
    verify_ssl: bool = True

    # Cohere Compass specific (overrides common settings if provider is cohere_compass)
    compass_index_name: str | None = None
    parser_url: str | None = None
    parser_api_key: str | None = None

    @classmethod
    def from_env(cls, prefix: str = "VECTOR") -> "VectorStoreConfig":
        """Load configuration from environment variables."""
        def getenv(key: str, default: Any = None) -> Any:
            return os.getenv(f"{prefix}_{key}", default)

        timeout_val = getenv("TIMEOUT")
        timeout = float(timeout_val) if timeout_val else 30.0

        return cls(
            host=getenv("HOST") or os.getenv("COHERE_COMPASS_URL"),
            api_key=getenv("API_KEY") or os.getenv("COHERE_COMPASS_API_KEY"),
            namespace=getenv("NAMESPACE", "default"),
            timeout=timeout,
            provider=getenv("PROVIDER", "memory") or "memory",
            compass_index_name=getenv("COMPASS_INDEX_NAME") or os.getenv("COHERE_COMPASS_INDEX_NAME"),
            parser_url=getenv("PARSER_URL") or os.getenv("COHERE_COMPASS_PARSER_URL"),
            parser_api_key=getenv("PARSER_API_KEY") or os.getenv("COHERE_COMPASS_PARSER_API_KEY"),
            verify_ssl=(getenv("VERIFY_SSL", "true").lower() != "false"),
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                             IN-MEMORY STORE
# ═══════════════════════════════════════════════════════════════════════════════


def _default_embedder(text: str) -> list[float]:
    """
    Deterministic, lightweight embedding for development/testing.

    This is a simple character-based embedding that produces consistent
    results. NOT suitable for production - use a real embedding model.

    Args:
        text (str): Text to embed.

    Returns:
        list[float]: 16-dimensional normalized embedding vector.

    Note:
        This embedder is only for testing. For production, provide a
        real embedding function (e.g., OpenAI embeddings, sentence-transformers).
    """
    dims = 16
    vec = [0.0] * dims
    for i, ch in enumerate(text):
        vec[i % dims] += (ord(ch) % 53) / 100.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    Args:
        a (list[float]): First vector.
        b (list[float]): Second vector.

    Returns:
        float: Cosine similarity (-1.0 to 1.0, typically 0.0 to 1.0 for normalized vectors).
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)


async def _maybe_await_embedder(embedder: Callable[[str], Any], text: str) -> list[float]:
    """Call embedder that may be sync or async."""
    result = embedder(text)
    if asyncio.iscoroutine(result):
        result = await result
    return list(result)


class InMemoryVectorStore:
    """
    Simple in-memory vector store with pluggable embedder and namespace isolation.

    Provides basic vector storage and similarity search for development
    and testing. Documents are embedded and stored in memory, with
    cosine similarity used for matching.

    Namespace Isolation:
        Each namespace has its own isolated index. Documents in one namespace
        are not visible to queries in another namespace. This prevents data
        leakage between different tenants, runs, or test cases.

    Attributes:
        embedder (Callable): Function to convert text to embeddings.
        namespace (str): Namespace for index isolation.

    Methods:
        add_documents(): Add documents to the index.
        query(): Search for similar documents.
        clear(): Remove all documents in this namespace.
        count(): Get number of indexed documents in this namespace.

    Example:
        >>> # With default embedder and namespace
        >>> store = InMemoryVectorStore(namespace="tenant-1")
        >>>
        >>> # With custom embedder
        >>> async def my_embedder(text: str) -> list[float]:
        ...     return await openai.embed(text)
        >>> store = InMemoryVectorStore(embedder=my_embedder, namespace="my-app")
        >>>
        >>> # Add and query
        >>> await store.add_documents([
        ...     VectorDocument(id="1", text="Hello world"),
        ... ])
        >>> matches = await store.query("greeting", top_k=1)

    Note:
        The default embedder is for testing only. For meaningful results,
        provide a real embedding model.

    See Also:
        VectorStoreService: Higher-level facade that wraps this store.
    """

    # Class-level registry for namespace isolation
    # Maps namespace -> {doc_id -> (embedding, document)}
    _namespace_indices: dict[str, dict[str, tuple[list[float], VectorDocument]]] = {}
    # Lock for thread-safe access to _namespace_indices in async contexts
    _lock: asyncio.Lock | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create the class-level lock (lazy initialization for async contexts)."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    def __init__(
        self,
        embedder: Callable[[str], Any] | None = None,
        namespace: str = "default",
    ):
        """
        Initialize in-memory vector store.

        Args:
            embedder (Callable | None): Function to embed text into vectors.
                Can be sync or async. If None, uses a simple test embedder.
                Signature: (text: str) -> list[float]
            namespace (str): Namespace for index isolation. Different namespaces
                have completely separate document storage. Default: "default".

        Example:
            >>> # Default embedder (testing only)
            >>> store = InMemoryVectorStore()
            >>>
            >>> # With namespace isolation
            >>> store1 = InMemoryVectorStore(namespace="tenant-a")
            >>> store2 = InMemoryVectorStore(namespace="tenant-b")
            >>> # store1 and store2 have separate indices
            >>>
            >>> # Custom sync embedder
            >>> store = InMemoryVectorStore(embedder=my_embed_function)
            >>>
            >>> # Custom async embedder
            >>> store = InMemoryVectorStore(embedder=async_embed_function)
        """
        self.embedder = embedder or _default_embedder
        self.namespace = namespace

        # Initialize namespace index if not exists (sync check, async init deferred)
        if namespace not in InMemoryVectorStore._namespace_indices:
            InMemoryVectorStore._namespace_indices[namespace] = {}
        # Store reference to namespace for this instance
        self._namespace_ref = namespace

    @property
    def _index(self) -> dict[str, tuple[list[float], VectorDocument]]:
        """Get the index for this namespace."""
        return InMemoryVectorStore._namespace_indices[self.namespace]

    async def add_documents(self, docs: Iterable[VectorDocument]) -> None:
        """
        Add documents to the index.

        Each document's text is embedded and stored with its ID.
        Documents with existing IDs are overwritten.

        Args:
            docs (Iterable[VectorDocument]): Documents to add.

        Example:
            >>> await store.add_documents([
            ...     VectorDocument(id="1", text="Python programming"),
            ...     VectorDocument(id="2", text="JavaScript basics"),
            ... ])
        """
        async with self._get_lock():
            for doc in docs:
                embedding = await _maybe_await_embedder(self.embedder, doc.text)
                self._index[doc.id] = (embedding, doc)

    async def query(self, query_text: str, top_k: int = 5) -> list[VectorMatch]:
        """
        Search for similar documents.

        Embeds the query text and finds the most similar documents
        using cosine similarity.

        Args:
            query_text (str): Query text to search for.
            top_k (int): Maximum number of results. Default: 5.

        Returns:
            list[VectorMatch]: Matches sorted by similarity (highest first).

        Example:
            >>> matches = await store.query("learn programming", top_k=3)
            >>> for match in matches:
            ...     print(f"{match.id}: {match.score:.3f}")
        """
        async with self._get_lock():
            if not self._index:
                return []
            query_vec = await _maybe_await_embedder(self.embedder, query_text)

            scored: list[tuple[float, VectorDocument]] = []
            for embedding, doc in self._index.values():
                score = _cosine_similarity(query_vec, embedding)
                scored.append((score, doc))

            scored.sort(key=lambda x: x[0], reverse=True)
            matches: list[VectorMatch] = []
            for score, doc in scored[:top_k]:
                matches.append(VectorMatch(
                    id=doc.id,
                    text=doc.text,
                    score=score,
                    metadata=doc.metadata,
                ))
            return matches

    async def clear(self) -> None:
        """
        Remove all documents from this namespace's index.

        Only clears documents in this store's namespace; other namespaces
        are not affected.

        Example:
            >>> await store.clear()
            >>> count = await store.count()  # 0
        """
        async with self._get_lock():
            self._index.clear()

    async def count(self) -> int:
        """
        Get number of indexed documents in this namespace.

        Returns:
            int: Number of documents in the index.

        Example:
            >>> await store.add_documents([...])
            >>> count = await store.count()
            >>> print(f"{count} documents indexed")
        """
        async with self._get_lock():
            return len(self._index)

    @classmethod
    async def clear_all_namespaces_async(cls) -> None:
        """
        Clear all namespaces asynchronously (thread-safe).

        Removes all documents from all namespaces. This is a class method
        that affects all InMemoryVectorStore instances.

        Example:
            >>> await InMemoryVectorStore.clear_all_namespaces_async()
        """
        async with cls._get_lock():
            cls._namespace_indices.clear()

    @classmethod
    def clear_all_namespaces(cls) -> None:
        """
        Clear all namespaces (useful for testing, not thread-safe).

        For async code, prefer clear_all_namespaces_async().

        Example:
            >>> InMemoryVectorStore.clear_all_namespaces()
        """
        cls._namespace_indices.clear()
        cls._lock = None  # Reset lock for clean state


# ═══════════════════════════════════════════════════════════════════════════════
#                             SERVICE FACADE
# ═══════════════════════════════════════════════════════════════════════════════


class VectorStoreService:
    """
    Facade for vector store operations.

    Provides a unified interface for vector storage that works with
    both in-memory storage (for development) and remote vector databases
    (for production).

    Attributes:
        config (VectorStoreConfig): Configuration for the service.
        embedder (Callable | None): Custom embedding function.

    Methods:
        connect(): Initialize connection (for remote providers).
        upsert(): Add or update documents in the store.
        query(): Search for similar documents.
        health_check(): Check if service is healthy.

    Example:
        >>> from agentorchestrator.services import VectorStoreService, VectorDocument
        >>>
        >>> # In-memory mode (default) for development
        >>> store = VectorStoreService()
        >>>
        >>> # Add documents
        >>> await store.upsert([
        ...     VectorDocument(id="doc1", text="Machine learning basics"),
        ...     VectorDocument(id="doc2", text="Deep learning tutorial"),
        ... ])
        >>>
        >>> # Search
        >>> matches = await store.query("AI and ML", top_k=5)
        >>> for match in matches:
        ...     print(f"{match.id}: {match.text} (score: {match.score:.2f})")

    Remote Mode Example:
        >>> from agentorchestrator.services import VectorStoreService, VectorStoreConfig
        >>>
        >>> config = VectorStoreConfig(
        ...     host="https://compass.corp.com",
        ...     api_key="sk-xxx",
        ...     namespace="production",
        ...     provider="cohere_compass",
        ... )
        >>> store = VectorStoreService(config=config)
        >>> await store.connect()
        >>>
        >>> # Operations work the same way
        >>> await store.upsert(documents)
        >>> matches = await store.query("search text")

    See Also:
        VectorStoreConfig: Configuration options.
        VectorDocument: Document format for upsert.
        VectorMatch: Result format from queries.
    """

    def __init__(
        self,
        config: VectorStoreConfig | None = None,
        embedder: Callable[[str], Any] | None = None,
    ):
        """
        Initialize vector store service.

        Args:
            config (VectorStoreConfig | None): Configuration for the service.
                If None, uses in-memory storage with default settings.
            embedder (Callable | None): Custom embedding function.
                Only used for in-memory mode. Signature: (text: str) -> list[float]

        Raises:
            ConfigurationError: If remote provider is configured without required host/api_key.
        """
        self.config = config or VectorStoreConfig()
        self.embedder = embedder
        self._memory_store = (
            InMemoryVectorStore(embedder=embedder, namespace=self.config.namespace)
            if self.config.provider == "memory"
            else None
        )
        self._cohere_compass = None
        self._http_client = None

        # Validate configuration for remote providers
        if self.config.provider != "memory":
            self._validate_remote_config()

        if self.config.provider == "cohere_compass":
            from agentorchestrator.services.cohere_compass import CohereCompassService
            self._cohere_compass = CohereCompassService(
                server_url=self.config.host,
                api_key=self.config.api_key,
                index_name=self.config.compass_index_name or self.config.namespace,
                timeout=self.config.timeout,
                verify_ssl=self.config.verify_ssl,
            )

    def _validate_remote_config(self) -> None:
        """Validate that required fields are set for remote providers."""
        missing_fields = []
        if not self.config.host:
            missing_fields.append("host")
        if not self.config.api_key:
            missing_fields.append("api_key")

        if missing_fields:
            raise ConfigurationError(
                f"Remote vector store provider '{self.config.provider}' requires: {', '.join(missing_fields)}. "
                f"Set these via VectorStoreConfig or environment variables (VECTOR_HOST, VECTOR_API_KEY).",
                {"provider": self.config.provider, "missing_fields": missing_fields},
            )

    async def connect(self) -> bool:
        """
        Initialize connection to vector store.
        """
        if self._memory_store:
            return True
        if self._cohere_compass:
            return await self._cohere_compass.health_check()
            
        try:
            import httpx  # noqa: F401
        except ImportError:
            raise RuntimeError("httpx is required for remote vector store usage") from None
        return True

    async def upsert(self, docs: Iterable[VectorDocument]) -> bool:
        """
        Add or update documents in the store.
        """
        if self._memory_store:
            await self._memory_store.add_documents(docs)
            return True

        if self._cohere_compass:
            compass_docs = [
                {"id": doc.id, "text": doc.text, "metadata": doc.metadata}
                for doc in docs
            ]
            await self._cohere_compass.upsert(compass_docs)
            return True

        client = await self._get_http_client()
        payload = {
            "namespace": self.config.namespace,
            "documents": [doc.__dict__ for doc in docs],
        }
        resp = await client.post(
            f"{self.config.host.rstrip('/')}/upsert",
            json=payload,
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return True

    async def query(self, query_text: str, top_k: int = 5) -> list[VectorMatch]:
        """
        Search for similar documents.
        """
        if self._memory_store:
            return await self._memory_store.query(query_text, top_k=top_k)

        if self._cohere_compass:
            results = await self._cohere_compass.query(query_text, top_k=top_k)
            matches = []
            for item in results:
                # Compass might return slightly different fields
                matches.append(VectorMatch(
                    id=item.get("id", item.get("doc_id", "")),
                    text=item.get("text", ""),
                    score=float(item.get("score", 0.0)),
                    metadata=item.get("metadata", {}) or {},
                ))
            return matches

        client = await self._get_http_client()
        payload = {
            "namespace": self.config.namespace,
            "query": query_text,
            "top_k": top_k,
        }
        resp = await client.post(
            f"{self.config.host.rstrip('/')}/query",
            json=payload,
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("matches", []):
            results.append(VectorMatch(
                id=item.get("id", ""),
                text=item.get("text", ""),
                score=float(item.get("score", 0.0)),
                metadata=item.get("metadata", {}) or {},
            ))
        return results

    async def health_check(self) -> bool:
        """
        Check if vector store is healthy.
        """
        if self._memory_store:
            return True
        if self._cohere_compass:
            return await self._cohere_compass.health_check()
            
        try:
            client = await self._get_http_client()
            resp = await client.get(
                f"{self.config.host.rstrip('/')}/health",
                headers=self._auth_headers(),
                timeout=self.config.timeout,
            )
            return resp.status_code < 300
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Vector store health check failed: {exc}")
            return False

    async def _get_http_client(self):
        """Lazy-create HTTP client for remote operations."""
        if self._http_client:
            return self._http_client
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for remote vector store usage") from exc
        self._http_client = httpx.AsyncClient(timeout=self.config.timeout, verify=self.config.verify_ssl)
        return self._http_client

    async def close(self):
        """Close any underlying HTTP clients."""
        if self._cohere_compass:
            await self._cohere_compass.close()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> "VectorStoreService":
        """Async context manager entry - connects to the store."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - closes connections."""
        await self.close()

    def _auth_headers(self) -> dict[str, str]:
        """Build authentication headers for remote API."""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers


__all__ = [
    "VectorStoreConfig",
    "VectorStoreService",
    "VectorDocument",
    "VectorMatch",
    "InMemoryVectorStore",
]
