import asyncio
import os
from unittest import mock

import pytest

from agentorchestrator.core.exceptions import ConfigurationError
from agentorchestrator.services.vector_store import (
    InMemoryVectorStore,
    VectorDocument,
    VectorStoreConfig,
    VectorStoreService,
)


@pytest.mark.asyncio
async def test_inmemory_vector_store_add_and_query():
    store = InMemoryVectorStore()
    await store.add_documents([
        VectorDocument(id="a", text="Use async await for IO"),
        VectorDocument(id="b", text="Index tables for SQL performance"),
    ])

    results = await store.query("async IO", top_k=2)
    assert len(results) == 2
    assert results[0].id in {"a", "b"}


@pytest.mark.asyncio
async def test_vector_store_service_defaults_to_memory():
    service = VectorStoreService()
    await service.upsert([
        VectorDocument(id="x", text="Caching with Redis helps performance"),
    ])
    matches = await service.query("Redis", top_k=1)
    assert matches
    assert matches[0].id == "x"


# ============================================================================
# Tests for VectorStoreConfig.from_env
# ============================================================================


def test_vector_store_config_from_env_loads_values():
    """Test that from_env correctly loads configuration from environment variables."""
    env_vars = {
        "VECTOR_HOST": "https://vectordb.example.com",
        "VECTOR_API_KEY": "test-api-key-123",
        "VECTOR_NAMESPACE": "test-namespace",
        "VECTOR_TIMEOUT": "60.0",
        "VECTOR_PROVIDER": "cohere_compass",
        "VECTOR_VERIFY_SSL": "false",
    }
    with mock.patch.dict(os.environ, env_vars, clear=False):
        config = VectorStoreConfig.from_env()

    assert config.host == "https://vectordb.example.com"
    assert config.api_key == "test-api-key-123"
    assert config.namespace == "test-namespace"
    assert config.timeout == 60.0
    assert config.provider == "cohere_compass"
    assert config.verify_ssl is False


def test_vector_store_config_from_env_falls_back_to_cohere_vars():
    """Test that from_env falls back to COHERE_COMPASS_* environment variables."""
    env_vars = {
        "COHERE_COMPASS_URL": "https://compass.example.com",
        "COHERE_COMPASS_API_KEY": "compass-key-456",
        "COHERE_COMPASS_INDEX_NAME": "my-index",
    }
    with mock.patch.dict(os.environ, env_vars, clear=False):
        # Clear VECTOR_* vars to ensure fallback
        with mock.patch.dict(os.environ, {"VECTOR_HOST": "", "VECTOR_API_KEY": ""}, clear=False):
            config = VectorStoreConfig.from_env()

    assert config.host == "https://compass.example.com"
    assert config.api_key == "compass-key-456"
    assert config.compass_index_name == "my-index"


def test_vector_store_config_from_env_returns_defaults():
    """Test that from_env returns sensible defaults when no env vars set."""
    with mock.patch.dict(os.environ, {}, clear=True):
        config = VectorStoreConfig.from_env()

    assert config.host is None
    assert config.api_key is None
    assert config.namespace == "default"
    assert config.timeout == 30.0
    assert config.provider == "memory"
    assert config.verify_ssl is True


# ============================================================================
# Tests for remote config validation
# ============================================================================


def test_vector_store_service_raises_on_missing_host_for_remote():
    """Test that VectorStoreService raises ConfigurationError when host is missing for remote provider."""
    config = VectorStoreConfig(
        provider="cohere_compass",
        host=None,
        api_key="some-key",
    )
    with pytest.raises(ConfigurationError) as exc_info:
        VectorStoreService(config=config)

    assert "host" in str(exc_info.value)
    assert "cohere_compass" in str(exc_info.value)


def test_vector_store_service_raises_on_missing_api_key_for_remote():
    """Test that VectorStoreService raises ConfigurationError when api_key is missing for remote provider."""
    config = VectorStoreConfig(
        provider="cohere_compass",
        host="https://example.com",
        api_key=None,
    )
    with pytest.raises(ConfigurationError) as exc_info:
        VectorStoreService(config=config)

    assert "api_key" in str(exc_info.value)


def test_vector_store_service_raises_on_missing_both_for_remote():
    """Test that VectorStoreService lists all missing fields in error."""
    config = VectorStoreConfig(
        provider="some_remote_provider",
        host=None,
        api_key=None,
    )
    with pytest.raises(ConfigurationError) as exc_info:
        VectorStoreService(config=config)

    error_msg = str(exc_info.value)
    assert "host" in error_msg
    assert "api_key" in error_msg


def test_vector_store_service_memory_provider_no_validation():
    """Test that memory provider doesn't require host/api_key."""
    config = VectorStoreConfig(
        provider="memory",
        host=None,
        api_key=None,
    )
    # Should not raise
    service = VectorStoreService(config=config)
    assert service._memory_store is not None


# ============================================================================
# Tests for async context manager
# ============================================================================


@pytest.mark.asyncio
async def test_vector_store_service_async_context_manager():
    """Test that VectorStoreService works as async context manager."""
    async with VectorStoreService() as service:
        await service.upsert([
            VectorDocument(id="ctx-1", text="Context manager test"),
        ])
        matches = await service.query("context", top_k=1)
        assert len(matches) == 1
        assert matches[0].id == "ctx-1"
    # Service should be closed after exiting context


@pytest.mark.asyncio
async def test_vector_store_service_close_is_idempotent():
    """Test that calling close multiple times doesn't raise errors."""
    service = VectorStoreService()
    await service.close()
    await service.close()  # Should not raise

