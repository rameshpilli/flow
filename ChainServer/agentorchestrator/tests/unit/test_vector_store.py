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


# ============================================================================
# Tests for namespace isolation
# ============================================================================


@pytest.fixture(autouse=True)
def clear_namespaces():
    """Clear all namespaces before and after each test to ensure isolation."""
    InMemoryVectorStore.clear_all_namespaces()
    yield
    InMemoryVectorStore.clear_all_namespaces()


@pytest.mark.asyncio
async def test_inmemory_vector_store_namespace_isolation():
    """Test that different namespaces have isolated indices."""
    store_a = InMemoryVectorStore(namespace="tenant-a")
    store_b = InMemoryVectorStore(namespace="tenant-b")

    # Add documents to each namespace
    await store_a.add_documents([
        VectorDocument(id="doc1", text="Document in tenant A"),
    ])
    await store_b.add_documents([
        VectorDocument(id="doc2", text="Document in tenant B"),
    ])

    # Each namespace should only see its own documents
    assert await store_a.count() == 1
    assert await store_b.count() == 1

    # Query should only return documents from the same namespace
    results_a = await store_a.query("Document", top_k=10)
    results_b = await store_b.query("Document", top_k=10)

    assert len(results_a) == 1
    assert results_a[0].id == "doc1"

    assert len(results_b) == 1
    assert results_b[0].id == "doc2"


@pytest.mark.asyncio
async def test_inmemory_vector_store_clear_only_affects_namespace():
    """Test that clearing one namespace doesn't affect others."""
    store_a = InMemoryVectorStore(namespace="ns-a")
    store_b = InMemoryVectorStore(namespace="ns-b")

    await store_a.add_documents([VectorDocument(id="a1", text="A doc")])
    await store_b.add_documents([VectorDocument(id="b1", text="B doc")])

    # Clear namespace A
    await store_a.clear()

    # A should be empty, B should still have documents
    assert await store_a.count() == 0
    assert await store_b.count() == 1


@pytest.mark.asyncio
async def test_vector_store_service_uses_namespace_for_memory():
    """Test that VectorStoreService passes namespace to InMemoryVectorStore."""
    config_a = VectorStoreConfig(provider="memory", namespace="service-ns-a")
    config_b = VectorStoreConfig(provider="memory", namespace="service-ns-b")

    service_a = VectorStoreService(config=config_a)
    service_b = VectorStoreService(config=config_b)

    # Add documents through services
    await service_a.upsert([VectorDocument(id="sa1", text="Service A document")])
    await service_b.upsert([VectorDocument(id="sb1", text="Service B document")])

    # Each service should only see its own documents
    results_a = await service_a.query("document", top_k=10)
    results_b = await service_b.query("document", top_k=10)

    assert len(results_a) == 1
    assert results_a[0].id == "sa1"

    assert len(results_b) == 1
    assert results_b[0].id == "sb1"


@pytest.mark.asyncio
async def test_inmemory_vector_store_same_namespace_shares_data():
    """Test that stores with same namespace share the same index."""
    store1 = InMemoryVectorStore(namespace="shared")
    store2 = InMemoryVectorStore(namespace="shared")

    # Add via store1
    await store1.add_documents([VectorDocument(id="shared-doc", text="Shared data")])

    # Should be visible from store2
    assert await store2.count() == 1
    results = await store2.query("Shared", top_k=1)
    assert len(results) == 1
    assert results[0].id == "shared-doc"


def test_inmemory_vector_store_clear_all_namespaces():
    """Test that clear_all_namespaces removes all namespace indices."""
    # Create stores in different namespaces
    store_a = InMemoryVectorStore(namespace="clear-test-a")
    store_b = InMemoryVectorStore(namespace="clear-test-b")

    # Verify namespaces exist
    assert "clear-test-a" in InMemoryVectorStore._namespace_indices
    assert "clear-test-b" in InMemoryVectorStore._namespace_indices

    # Clear all
    InMemoryVectorStore.clear_all_namespaces()

    # All namespaces should be removed
    assert len(InMemoryVectorStore._namespace_indices) == 0

