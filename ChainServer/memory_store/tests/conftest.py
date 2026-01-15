"""Pytest configuration and fixtures."""

import pytest
from memory_store.config import MemoryStoreConfig, set_config


@pytest.fixture
def test_config():
    """Create a test configuration."""
    config = MemoryStoreConfig()
    
    # Override with test values
    config.cohere.api_key = "test_cohere_key"
    config.qdrant.url = "http://localhost:6333"
    config.qdrant.collection_name = "test_memory_store"
    config.service.port = 8001
    
    set_config(config)
    return config


@pytest.fixture
def mock_memory_service(test_config, mocker):
    """Create a mock memory service."""
    from memory_store.service import MemoryStoreService
    
    # Mock mem0 client
    mock_client = mocker.MagicMock()
    service = MemoryStoreService(test_config)
    service._memory_client = mock_client
    
    return service, mock_client


@pytest.fixture
async def test_client():
    """Create a test FastAPI client."""
    from fastapi.testclient import TestClient
    from memory_store.api import app
    
    with TestClient(app) as client:
        yield client
