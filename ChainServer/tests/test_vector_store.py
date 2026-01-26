"""
Tests for Vector Store Service
==============================

Covers in-memory defaults, env loading, validation, namespace isolation,
context manager lifecycle, and Cohere Compass wiring at the facade level.
"""

import pytest
from unittest.mock import AsyncMock, patch

from agentorchestrator.services.vector_store import (
    VectorStoreService,
    VectorDocument,
    VectorStoreConfig,
)
from agentorchestrator.core.exceptions import ConfigurationError


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

    def test_from_env_loads_values(self, monkeypatch):
        """Environment variables should populate VectorStoreConfig."""
        monkeypatch.setenv("VECTOR_HOST", "https://vec.example.com")
        monkeypatch.setenv("VECTOR_API_KEY", "secret")
        monkeypatch.setenv("VECTOR_PROVIDER", "cohere_compass")
        monkeypatch.setenv("VECTOR_NAMESPACE", "tenant-x")

        cfg = VectorStoreConfig.from_env()

        assert cfg.host == "https://vec.example.com"
        assert cfg.api_key == "secret"
        assert cfg.provider == "cohere_compass"
        assert cfg.namespace == "tenant-x"

    def test_validate_remote_config_missing_fields_raises(self):
        """Remote provider without host/api_key should raise ConfigurationError."""
        cfg = VectorStoreConfig(provider="cohere_compass")
        with pytest.raises(ConfigurationError):
            VectorStoreService(config=cfg)

    @pytest.mark.asyncio
    async def test_namespace_isolation_between_memory_stores(self):
        """Memory backend must isolate documents by namespace."""
        svc_a = VectorStoreService(VectorStoreConfig(namespace="ns-a"))
        svc_b = VectorStoreService(VectorStoreConfig(namespace="ns-b"))

        await svc_a.upsert([VectorDocument(id="1", text="alpha")])

        matches_a = await svc_a.query("alpha", top_k=1)
        matches_b = await svc_b.query("alpha", top_k=1)

        assert matches_a and matches_a[0].id == "1"
        assert matches_b == []

    @pytest.mark.asyncio
    async def test_context_manager_closes_resources(self):
        """`async with` should call connect and close on remote client."""
        cfg = VectorStoreConfig(
            provider="cohere_compass",
            host="https://example",
            api_key="k",
            compass_index_name="idx",
        )
        service = VectorStoreService(config=cfg)

        # Patch compass client to avoid real IO
        service._cohere_compass.health_check = AsyncMock(return_value=True)
        service._cohere_compass.close = AsyncMock()

        async with service:
            assert service._cohere_compass.health_check.await_count == 1

        service._cohere_compass.close.assert_awaited_once()
