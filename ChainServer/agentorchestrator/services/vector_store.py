"""
AgentOrchestrator Vector Store Service

Lightweight vector store helper with an in-memory implementation and hooks for
connecting to an external vector database. Designed to mirror the ergonomics of
RedisService: users can either supply a configured service client or fall back
to the in-memory store for local/dev.
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
    """Document to store in the vector index."""

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorMatch:
    """Query match result."""

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

    Environment variables (prefix VECTOR):
        VECTOR_HOST: Base URL for the vector service (e.g., https://vector/api)
        VECTOR_API_KEY: API key or token
        VECTOR_NAMESPACE: Namespace/collection name
        VECTOR_TIMEOUT: HTTP timeout seconds
    """

    host: str | None = None
    api_key: str | None = None
    namespace: str = "default"
    timeout: float = 30.0
    provider: str = "memory"  # "memory" or remote provider identifier

    @classmethod
    def from_env(cls, prefix: str = "VECTOR") -> "VectorStoreConfig":
        """Load configuration from environment variables."""

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
    Deterministic, lightweight embedding for dev/testing.

    Not suitable for production; intended for mock flows when no embedding model
    is configured. Produces a 16-dim vector based on character codes.
    """
    dims = 16
    vec = [0.0] * dims
    for i, ch in enumerate(text):
        vec[i % dims] += (ord(ch) % 53) / 100.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
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
    """Simple in-memory vector store with pluggable embedder."""

    def __init__(self, embedder: Callable[[str], Any] | None = None):
        self.embedder = embedder or _default_embedder
        self._index: dict[str, tuple[list[float], VectorDocument]] = {}

    async def add_documents(self, docs: Iterable[VectorDocument]) -> None:
        for doc in docs:
            embedding = await _maybe_await_embedder(self.embedder, doc.text)
            self._index[doc.id] = (embedding, doc)

    async def query(self, query_text: str, top_k: int = 5) -> list[VectorMatch]:
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
        self._index.clear()

    async def count(self) -> int:
        return len(self._index)


# ═══════════════════════════════════════════════════════════════════════════════
#                             SERVICE FACADE
# ═══════════════════════════════════════════════════════════════════════════════


class VectorStoreService:
    """
    Thin facade for vector store usage.

    - In-memory mode (default) for dev/testing
    - Remote mode (HTTP) when host/api_key are provided
    """

    def __init__(
        self,
        config: VectorStoreConfig | None = None,
        embedder: Callable[[str], Any] | None = None,
    ):
        self.config = config or VectorStoreConfig()
        self.embedder = embedder
        self._memory_store = InMemoryVectorStore(embedder) if self.config.provider == "memory" else None
        self._http_client = None

    async def connect(self) -> bool:
        """Initialize client if using remote provider."""
        if self._memory_store:
            return True
        try:
            import httpx  # noqa: F401
        except ImportError:
            raise RuntimeError("httpx is required for remote vector store usage") from None
        return True

    async def upsert(self, docs: Iterable[VectorDocument]) -> None:
        """Upsert documents into the store."""
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
        """Query for similar documents."""
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
        """Basic health check."""
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
        """Lazy-create HTTP client."""
        if self._http_client:
            return self._http_client
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for remote vector store usage") from exc
        self._http_client = httpx.AsyncClient(timeout=self.config.timeout, verify=False)
        return self._http_client

    def _auth_headers(self) -> dict[str, str]:
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
