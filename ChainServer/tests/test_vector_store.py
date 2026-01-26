"""
Tests for Vector Store Service
==============================

Covers in-memory defaults and Cohere Compass wiring at the facade level.
"""

import pytest
from unittest.mock import AsyncMock, patch

from agentorchestrator.services.vector_store import (
    VectorStoreService,
    VectorDocument,
    VectorStoreConfig,
)


class TestVectorStoreService:
    """Tests for the main VectorStoreService facade."""

    @pytest.mark.asyncio
    async def test_default_to_memory_backend(self):
        """Service should default to in-memory and return True on upsert."""
        service = VectorStoreService()

        docs = [VectorDocument(id="test", text="Test", metadata={})]
        result = await service.upsert(docs)

        assert result is True

        matches = await service.query("Test", top_k=1)
        assert isinstance(matches, list)
        assert matches[0].id == "test"

    @pytest.mark.asyncio
    async def test_cohere_compass_upsert_and_query_calls_client(self):
        """Ensure Compass path is wired and uses provided client methods."""
        config = VectorStoreConfig(provider="cohere_compass", host="https://example", api_key="k", compass_index_name="idx")
        service = VectorStoreService(config=config)

        with patch.object(service._cohere_compass, "upsert", AsyncMock(return_value=True)) as mock_upsert, \
             patch.object(service._cohere_compass, "query", AsyncMock(return_value=[{"id": "1", "text": "t", "score": 0.9}])):

            docs = [VectorDocument(id="1", text="hello", metadata={})]
            result = await service.upsert(docs)
            assert result is True
            mock_upsert.assert_awaited_once()

            matches = await service.query("hello", top_k=1)
            assert len(matches) == 1
            assert matches[0].id == "1"

