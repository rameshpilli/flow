"""
AgentOrchestrator Vector Store Service
======================================

This module provides a lightweight vector store service with both in-memory
and remote storage options for semantic search and similarity matching.

The VectorStoreService offers:
- In-memory vector storage for development and testing
- HTTP-based remote vector database integration
- Pluggable embedding functions
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

    # Remote vector database
    store = VectorStoreService(config=VectorStoreConfig(
        host="https://vector-db.corp.com/api",
        api_key="sk-xxx",
        namespace="my-app",
        provider="pinecone",
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
    vector databases (for production).

    Attributes:
        host (str | None): Base URL for remote vector service. Default: None.
            Example: "https://vector-db.corp.com/api"
        api_key (str | None): API key or token for authentication. Default: None.
        namespace (str): Namespace/collection name for isolation. Default: "default".
        timeout (float): HTTP timeout in seconds. Default: 30.0.
        provider (str): Storage provider. Default: "memory".
            Options: "memory" for in-memory, or remote provider ID.

    Environment Variables:
        VECTOR_HOST: Base URL for the vector service
        VECTOR_API_KEY: API key or token
        VECTOR_NAMESPACE: Namespace/collection name
        VECTOR_TIMEOUT: HTTP timeout seconds
        VECTOR_PROVIDER: Provider identifier ("memory" or remote)

    Methods:
        from_env(): Load configuration from environment variables.

    Example:
        >>> # In-memory configuration (default)
        >>> config = VectorStoreConfig()
        >>> print(config.provider)  # "memory"
        >>>
        >>> # Remote configuration
        >>> config = VectorStoreConfig(
        ...     host="https://vector-db.corp.com/api",
        ...     api_key="sk-xxx",
        ...     namespace="my-app-prod",
        ...     provider="pinecone",
        ... )
        >>>
        >>> # From environment
        >>> config = VectorStoreConfig.from_env()

    See Also:
        VectorStoreService: Service that uses this configuration.
    """

    host: str | None = None
    api_key: str | None = None
    namespace: str = "default"
    timeout: float = 30.0
    provider: str = "memory"  # "memory" or remote provider identifier

    @classmethod
    def from_env(cls, prefix: str = "VECTOR") -> "VectorStoreConfig":
        """
        Load configuration from environment variables.

        Reads environment variables with the specified prefix and creates
        a configuration instance.

        Args:
            prefix (str): Environment variable prefix. Default: "VECTOR".
                Variables are read as {prefix}_{KEY}, e.g., VECTOR_HOST.

        Returns:
            VectorStoreConfig: Configuration loaded from environment.

        Example:
            >>> import os
            >>> os.environ["VECTOR_HOST"] = "https://vector-db.corp.com"
            >>> os.environ["VECTOR_API_KEY"] = "sk-xxx"
            >>> os.environ["VECTOR_PROVIDER"] = "pinecone"
            >>>
            >>> config = VectorStoreConfig.from_env()
            >>> print(config.host)  # "https://vector-db.corp.com"
        """

        def getenv(key: str, default: Any = None) -> Any:
            return os.getenv(f"{prefix}_{key}", default)

        timeout_val = getenv("TIMEOUT")
        timeout = float(timeout_val) if timeout_val else 30.0

        return cls(
            host=getenv("HOST"),
            api_key=getenv("API_KEY"),
            namespace=getenv("NAMESPACE", "default"),
            timeout=timeout,
            provider=getenv("PROVIDER", "memory") or "memory",
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
    Simple in-memory vector store with pluggable embedder.

    Provides basic vector storage and similarity search for development
    and testing. Documents are embedded and stored in memory, with
    cosine similarity used for matching.

    Attributes:
        embedder (Callable): Function to convert text to embeddings.

    Methods:
        add_documents(): Add documents to the index.
        query(): Search for similar documents.
        clear(): Remove all documents.
        count(): Get number of indexed documents.

    Example:
        >>> # With default embedder
        >>> store = InMemoryVectorStore()
        >>>
        >>> # With custom embedder
        >>> async def my_embedder(text: str) -> list[float]:
        ...     return await openai.embed(text)
        >>> store = InMemoryVectorStore(embedder=my_embedder)
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

    def __init__(self, embedder: Callable[[str], Any] | None = None):
        """
        Initialize in-memory vector store.

        Args:
            embedder (Callable | None): Function to embed text into vectors.
                Can be sync or async. If None, uses a simple test embedder.
                Signature: (text: str) -> list[float]

        Example:
            >>> # Default embedder (testing only)
            >>> store = InMemoryVectorStore()
            >>>
            >>> # Custom sync embedder
            >>> store = InMemoryVectorStore(embedder=my_embed_function)
            >>>
            >>> # Custom async embedder
            >>> store = InMemoryVectorStore(embedder=async_embed_function)
        """
        self.embedder = embedder or _default_embedder
        self._index: dict[str, tuple[list[float], VectorDocument]] = {}

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
        Remove all documents from the index.

        Example:
            >>> await store.clear()
            >>> count = await store.count()  # 0
        """
        self._index.clear()

    async def count(self) -> int:
        """
        Get number of indexed documents.

        Returns:
            int: Number of documents in the index.

        Example:
            >>> await store.add_documents([...])
            >>> count = await store.count()
            >>> print(f"{count} documents indexed")
        """
        return len(self._index)


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
        ...     host="https://vector-api.corp.com",
        ...     api_key="sk-xxx",
        ...     namespace="production",
        ...     provider="pinecone",
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

        Example:
            >>> # In-memory with defaults
            >>> store = VectorStoreService()
            >>>
            >>> # In-memory with custom embedder
            >>> store = VectorStoreService(embedder=my_embedding_func)
            >>>
            >>> # Remote with config
            >>> config = VectorStoreConfig.from_env()
            >>> store = VectorStoreService(config=config)
        """
        self.config = config or VectorStoreConfig()
        self.embedder = embedder
        self._memory_store = InMemoryVectorStore(embedder) if self.config.provider == "memory" else None
        self._http_client = None

    async def connect(self) -> bool:
        """
        Initialize connection to vector store.

        For in-memory mode, this is a no-op. For remote providers,
        verifies that the HTTP client is available.

        Returns:
            bool: True if connection is ready.

        Raises:
            RuntimeError: If httpx is not installed for remote mode.

        Example:
            >>> store = VectorStoreService(config=remote_config)
            >>> await store.connect()
            >>> # Now ready for operations
        """
        if self._memory_store:
            return True
        try:
            import httpx  # noqa: F401
        except ImportError:
            raise RuntimeError("httpx is required for remote vector store usage") from None
        return True

    async def upsert(self, docs: Iterable[VectorDocument]) -> None:
        """
        Add or update documents in the store.

        Documents with existing IDs are updated; new IDs are added.
        In memory mode, documents are embedded locally. In remote mode,
        documents are sent to the vector service.

        Args:
            docs (Iterable[VectorDocument]): Documents to upsert.

        Raises:
            httpx.HTTPStatusError: If remote API returns error.

        Example:
            >>> docs = [
            ...     VectorDocument(id="1", text="First document"),
            ...     VectorDocument(id="2", text="Second document"),
            ... ]
            >>> await store.upsert(docs)
            >>>
            >>> # Update existing document
            >>> await store.upsert([
            ...     VectorDocument(id="1", text="Updated first document"),
            ... ])
        """
        if self._memory_store:
            await self._memory_store.add_documents(docs)
            return

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

    async def query(self, query_text: str, top_k: int = 5) -> list[VectorMatch]:
        """
        Search for similar documents.

        Finds documents most similar to the query text using
        vector similarity search.

        Args:
            query_text (str): Query text to search for.
            top_k (int): Maximum number of results. Default: 5.

        Returns:
            list[VectorMatch]: Matches sorted by similarity (highest first).

        Raises:
            httpx.HTTPStatusError: If remote API returns error.

        Example:
            >>> matches = await store.query("machine learning", top_k=3)
            >>> for match in matches:
            ...     print(f"ID: {match.id}")
            ...     print(f"Text: {match.text[:50]}...")
            ...     print(f"Score: {match.score:.3f}")
            ...     print()
        """
        if self._memory_store:
            return await self._memory_store.query(query_text, top_k=top_k)

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

        For in-memory mode, always returns True. For remote mode,
        pings the health endpoint.

        Returns:
            bool: True if service is healthy.

        Example:
            >>> if await store.health_check():
            ...     print("Vector store is ready")
            ... else:
            ...     print("Vector store is unavailable")
        """
        if self._memory_store:
            return True
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
        self._http_client = httpx.AsyncClient(timeout=self.config.timeout, verify=False)
        return self._http_client

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
