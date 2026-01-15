"""Test configuration management."""

import os
import pytest
from memory_store.config import (
    MemoryStoreConfig,
    LLMGatewayConfig,
    CohereConfig,
    QdrantConfig,
)


def test_cohere_config():
    """Test Cohere configuration."""
    config = CohereConfig(api_key="test_key")
    assert config.api_key == "test_key"
    assert config.is_configured


def test_cohere_config_unconfigured():
    """Test Cohere configuration when not set."""
    config = CohereConfig(api_key="")
    assert not config.is_configured


def test_qdrant_config():
    """Test Qdrant configuration."""
    config = QdrantConfig(url="http://localhost:6333")
    assert config.url == "http://localhost:6333"
    assert config.collection_name == "memory_store"
    assert config.vector_size == 1024
    assert config.is_configured


def test_llm_gateway_config():
    """Test LLM Gateway configuration."""
    config = LLMGatewayConfig(
        server_url="http://llm-gateway:8080",
        api_key="test_key",
    )
    assert config.server_url == "http://llm-gateway:8080"
    assert config.is_configured


def test_memory_store_config():
    """Test main memory store configuration."""
    config = MemoryStoreConfig()
    config.cohere.api_key = "test_key"
    config.qdrant.url = "http://localhost:6333"
    
    is_valid, errors = config.validate_config()
    assert is_valid
    assert len(errors) == 0


def test_memory_store_config_invalid():
    """Test configuration validation with missing required fields."""
    config = MemoryStoreConfig()
    config.cohere.api_key = ""  # Missing required field
    
    is_valid, errors = config.validate_config()
    assert not is_valid
    assert len(errors) > 0


def test_config_to_dict():
    """Test configuration serialization."""
    config = MemoryStoreConfig()
    config.cohere.api_key = "test_key"
    config.qdrant.url = "http://localhost:6333"
    
    config_dict = config.to_dict()
    assert "cohere" in config_dict
    assert "qdrant" in config_dict
    assert "mem0" in config_dict
    assert config_dict["cohere"]["is_configured"]
