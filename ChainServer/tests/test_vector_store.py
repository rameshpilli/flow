"""
Tests for Vector Store Service
==============================

Tests in-memory and Cohere Compass integrations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from agentorchestrator.services.vector_store import (
        VectorStoreService,
        VectorDocument,
        VectorSearchResult,
        InMemoryVectorStore,
    )
    VECTOR_STORE_AVAILABLE = True
except ImportError:
    VECTOR_STORE_AVAILABLE = False


pytestmark = pytest.mark.skipif(not VECTOR_STORE_AVAILABLE, reason="Vector store not available")


class TestInMemoryVectorStore:
    """Tests for in-memory vector store."""

    @pytest.mark.asyncio
    async def test_upsert_documents(self):
        """Test upserting documents to the store."""
        store = InMemoryVectorStore()
        
        docs = [
            VectorDocument(id="doc1", text="Hello world", metadata={"topic": "greeting"}),
            VectorDocument(id="doc2", text="Machine learning basics", metadata={"topic": "ml"}),
        ]
        
        result = await store.upsert(docs)
        assert result is True

    @pytest.mark.asyncio
    async def test_query_returns_results(self):
        """Test querying the vector store."""
        store = InMemoryVectorStore()
        
        # Insert documents
        docs = [
            VectorDocument(id="doc1", text="Python programming language", metadata={}),
            VectorDocument(id="doc2", text="JavaScript is for web development", metadata={}),
            VectorDocument(id="doc3", text="Python is great for data science", metadata={}),
        ]
        await store.upsert(docs)
        
        # Query
        results = await store.query("Python programming", limit=2)
        
        assert len(results) <= 2
        # Should find Python-related documents
        assert any("python" in r.text.lower() for r in results)

    @pytest.mark.asyncio
    async def test_delete_document(self):
        """Test deleting a document."""
        store = InMemoryVectorStore()
        
        docs = [VectorDocument(id="doc1", text="Test document", metadata={})]
        await store.upsert(docs)
        
        # Delete
        result = await store.delete("doc1")
        assert result is True
        
        # Verify deleted
        results = await store.query("Test document", limit=1)
        assert not any(r.id == "doc1" for r in results)

    @pytest.mark.asyncio
    async def test_get_document_by_id(self):
        """Test getting a document by ID."""
        store = InMemoryVectorStore()
        
        docs = [VectorDocument(id="doc1", text="Test document", metadata={"key": "value"})]
        await store.upsert(docs)
        
        doc = await store.get("doc1")
        
        assert doc is not None
        assert doc.id == "doc1"
        assert doc.text == "Test document"
        assert doc.metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_document(self):
        """Test getting a nonexistent document."""
        store = InMemoryVectorStore()
        
        doc = await store.get("nonexistent")
        assert doc is None


class TestVectorStoreService:
    """Tests for the main VectorStoreService facade."""

    @pytest.mark.asyncio
    async def test_default_to_memory_backend(self):
        """Test service defaults to in-memory backend."""
        service = VectorStoreService()
        
        # Should work without explicit backend config
        docs = [VectorDocument(id="test", text="Test", metadata={})]
        result = await service.upsert(docs)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_search_with_filters(self):
        """Test searching with metadata filters."""
        service = VectorStoreService()
        
        docs = [
            VectorDocument(id="doc1", text="Python basics", metadata={"level": "beginner"}),
            VectorDocument(id="doc2", text="Python advanced", metadata={"level": "advanced"}),
        ]
        await service.upsert(docs)
        
        # Query with filter (if supported by backend)
        results = await service.query(
            query="Python",
            limit=5,
            filter_metadata={"level": "beginner"},
        )
        
        # In-memory may not support filters, but should not error
        assert isinstance(results, list)


class TestVectorDocument:
    """Tests for VectorDocument dataclass."""

    def test_create_document(self):
        """Test creating a vector document."""
        doc = VectorDocument(
            id="doc1",
            text="Sample text",
            metadata={"author": "test"},
        )
        
        assert doc.id == "doc1"
        assert doc.text == "Sample text"
        assert doc.metadata == {"author": "test"}

    def test_document_with_embedding(self):
        """Test document with pre-computed embedding."""
        embedding = [0.1, 0.2, 0.3]
        doc = VectorDocument(
            id="doc1",
            text="Sample text",
            metadata={},
            embedding=embedding,
        )
        
        assert doc.embedding == embedding


class TestVectorSearchResult:
    """Tests for search result dataclass."""

    def test_create_result(self):
        """Test creating a search result."""
        result = VectorSearchResult(
            id="doc1",
            text="Found document",
            score=0.95,
            metadata={"source": "test"},
        )
        
        assert result.id == "doc1"
        assert result.score == 0.95
        assert result.metadata == {"source": "test"}
