"""
Tests for LLM Gateway Client
=============================

Tests OAuth token refresh logic, connection handling, and generation methods.
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Test imports (mocked if dependencies not available)
try:
    from agentorchestrator.services.llm_gateway import (
        LLMGatewayClient,
        LLMGatewayConfig,
        OAuthTokenManager,
    )
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    LLMGatewayClient = None
    LLMGatewayConfig = None
    OAuthTokenManager = None


pytestmark = pytest.mark.skipif(not LLM_AVAILABLE, reason="LLM gateway not available")


class TestOAuthTokenManager:
    """Tests for OAuth token refresh logic."""

    def test_init_with_credentials(self):
        """Test manager initialization with OAuth credentials."""
        manager = OAuthTokenManager(
            oauth_endpoint="https://auth.example.com/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        assert manager.oauth_endpoint == "https://auth.example.com/token"
        assert manager.client_id == "test-client"
        assert manager.client_secret == "test-secret"

    def test_set_token_manually(self):
        """Test setting token manually."""
        manager = OAuthTokenManager()
        manager.set_token("test-token", expires_in=3600)
        
        assert manager._token == "test-token"
        assert manager._expires_at > time.time()

    @pytest.mark.asyncio
    async def test_get_token_returns_cached_valid_token(self):
        """Test that valid cached tokens are returned."""
        manager = OAuthTokenManager()
        manager.set_token("cached-token", expires_in=3600)
        
        token = await manager.get_token()
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_get_token_returns_none_without_credentials(self):
        """Test that None is returned when credentials are missing."""
        manager = OAuthTokenManager()
        token = await manager.get_token()
        assert token is None

    @pytest.mark.asyncio
    async def test_get_token_refreshes_expired_token(self):
        """Test token refresh when expired."""
        manager = OAuthTokenManager(
            oauth_endpoint="https://auth.example.com/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        
        # Set expired token
        manager._token = "old-token"
        manager._expires_at = time.time() - 100  # Expired
        
        # Mock httpx
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "new-token",
                "expires_in": 3600,
            }
            mock_response.raise_for_status = MagicMock()
            
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_instance
            
            token = await manager.get_token()
            
            # Should have refreshed
            assert token == "new-token"
            mock_instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_refresh_is_thread_safe(self):
        """Test concurrent token refresh doesn't cause race conditions."""
        manager = OAuthTokenManager(
            oauth_endpoint="https://auth.example.com/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # Simulate network delay
            response = MagicMock()
            response.json.return_value = {
                "access_token": f"token-{call_count}",
                "expires_in": 3600,
            }
            response.raise_for_status = MagicMock()
            return response
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = mock_post
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_instance
            
            # Concurrent calls
            results = await asyncio.gather(*[manager.get_token() for _ in range(5)])
            
            # Lock should ensure only one refresh
            assert call_count == 1
            assert all(r == results[0] for r in results)


class TestLLMGatewayClient:
    """Tests for LLM Gateway Client."""

    def test_init_with_api_key(self):
        """Test client initialization with API key."""
        client = LLMGatewayClient(
            server_url="https://api.example.com/chat",
            api_key="test-api-key",
            model_name="gpt-4",
        )
        assert client.server_url == "https://api.example.com/chat"
        assert client.api_key == "test-api-key"
        assert client.model_name == "gpt-4"

    def test_init_with_oauth(self):
        """Test client initialization with OAuth."""
        client = LLMGatewayClient(
            server_url="https://api.example.com/chat",
            oauth_endpoint="https://auth.example.com/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        assert client._oauth_manager is not None

    def test_stub_mode_when_not_configured(self):
        """Test client operates in stub mode without credentials."""
        client = LLMGatewayClient()
        # Should be in stub mode
        assert client.server_url is None
        assert client.api_key is None

    def test_from_config(self):
        """Test creating client from config."""
        config = LLMGatewayConfig(
            server_url="https://api.example.com/chat",
            api_key="test-key",
            model_name="gpt-4",
            temperature=0.5,
        )
        client = LLMGatewayClient.from_config(config)
        
        assert client.server_url == config.server_url
        assert client.model_name == config.model_name
        assert client.temperature == 0.5

    @pytest.mark.asyncio
    async def test_generate_async_stub_mode(self):
        """Test generation in stub mode returns placeholder."""
        client = LLMGatewayClient()
        response = await client.generate_async("Test prompt")
        
        # Stub mode should return something
        assert response is not None

    @pytest.mark.asyncio
    async def test_generate_async_with_system_prompt(self):
        """Test generation with system prompt."""
        client = LLMGatewayClient(
            server_url="https://api.example.com/chat",
            api_key="test-key",
        )
        
        with patch.object(client, "_call_api_async") as mock_call:
            mock_call.return_value = {"content": "Response"}
            
            await client.generate_async(
                prompt="User message",
                system_prompt="You are helpful.",
            )
            
            # Check messages were formatted correctly
            call_args = mock_call.call_args
            messages = call_args[1].get("messages", call_args[0][0] if call_args[0] else [])
            
            assert any(m.get("role") == "system" for m in messages)
            assert any(m.get("role") == "user" for m in messages)


class TestLLMGatewayConfig:
    """Tests for LLM Gateway Configuration."""

    def test_from_env_with_api_key(self):
        """Test loading config from environment with API key."""
        with patch.dict("os.environ", {
            "LLM_SERVER_URL": "https://api.example.com/chat",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL_NAME": "gpt-4",
        }):
            config = LLMGatewayConfig.from_env()
            
            assert config.server_url == "https://api.example.com/chat"
            assert config.api_key == "test-key"
            assert config.model_name == "gpt-4"

    def test_from_env_with_oauth(self):
        """Test loading config from environment with OAuth."""
        with patch.dict("os.environ", {
            "LLM_SERVER_URL": "https://api.example.com/chat",
            "LLM_OAUTH_ENDPOINT": "https://auth.example.com/token",
            "LLM_CLIENT_ID": "test-client",
            "LLM_CLIENT_SECRET": "test-secret",
        }):
            config = LLMGatewayConfig.from_env()
            
            assert config.oauth_endpoint == "https://auth.example.com/token"
            assert config.client_id == "test-client"

    def test_default_values(self):
        """Test default configuration values."""
        config = LLMGatewayConfig()
        
        assert config.temperature == 0.2
        assert config.max_tokens == 4096
        assert config.timeout == 120.0
