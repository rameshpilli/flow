"""Test memory store service."""

import pytest


def test_memory_service_initialization(mock_memory_service):
    """Test memory service initialization."""
    service, mock_client = mock_memory_service
    assert service is not None
    assert service._memory_client is not None


def test_add_memory(mock_memory_service):
    """Test adding a memory."""
    service, mock_client = mock_memory_service
    
    # Mock the add method
    mock_client.add.return_value = {"id": "mem_123", "status": "success"}
    
    result = service.add_memory(
        agent_id="agent_001",
        messages="Test memory content",
        metadata={"category": "test"},
    )
    
    assert result["id"] == "mem_123"
    mock_client.add.assert_called_once()


def test_get_memories(mock_memory_service):
    """Test retrieving memories."""
    service, mock_client = mock_memory_service
    
    # Mock the search method
    mock_client.search.return_value = [
        {"id": "mem_1", "content": "Memory 1"},
        {"id": "mem_2", "content": "Memory 2"},
    ]
    
    memories = service.get_memories(
        agent_id="agent_001", query="test query", limit=10
    )
    
    assert len(memories) == 2
    assert memories[0]["id"] == "mem_1"
    mock_client.search.assert_called_once()


def test_delete_memory(mock_memory_service):
    """Test deleting a memory."""
    service, mock_client = mock_memory_service
    
    # Mock the delete method
    mock_client.delete.return_value = {"status": "deleted"}
    
    result = service.delete_memory(agent_id="agent_001", memory_id="mem_123")
    
    assert result["status"] == "deleted"
    mock_client.delete.assert_called_once_with(memory_id="mem_123")


@pytest.mark.asyncio
async def test_health_check(mock_memory_service):
    """Test health check."""
    service, _ = mock_memory_service
    
    health = await service.health_check()
    
    assert health["service"] == "memory_store"
    assert "components" in health
    assert "qdrant" in health["components"]
    assert "cohere" in health["components"]
