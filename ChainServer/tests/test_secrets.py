"""
Tests for Secret Management Service
====================================

Tests Vault integration and environment fallback.
"""

import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

try:
    from agentorchestrator.services.secrets import (
        SecretService,
        SecretProvider,
        EnvSecretProvider,
        VaultSecretProvider,
        get_secret_service,
    )
    from agentorchestrator.config import SecretString
    SECRETS_AVAILABLE = True
except ImportError:
    SECRETS_AVAILABLE = False


pytestmark = pytest.mark.skipif(not SECRETS_AVAILABLE, reason="Secrets module not available")


class TestEnvSecretProvider:
    """Tests for environment variable secret provider."""

    @pytest.mark.asyncio
    async def test_get_existing_env_var(self):
        """Test getting an existing environment variable."""
        provider = EnvSecretProvider()
        
        with patch.dict(os.environ, {"TEST_SECRET": "secret-value"}):
            result = await provider.get_secret("TEST_SECRET")
            assert result == "secret-value"

    @pytest.mark.asyncio
    async def test_get_missing_env_var(self):
        """Test getting a missing environment variable."""
        provider = EnvSecretProvider()
        
        # Ensure it doesn't exist
        with patch.dict(os.environ, {}, clear=True):
            result = await provider.get_secret("NONEXISTENT_VAR")
            assert result is None


class TestVaultSecretProvider:
    """Tests for Vault secret provider."""

    def test_init(self):
        """Test Vault provider initialization."""
        provider = VaultSecretProvider(
            url="https://vault.example.com",
            token="test-token",
            mount_point="secret",
        )
        
        assert provider.url == "https://vault.example.com"
        assert provider.token == "test-token"
        assert provider.mount_point == "secret"

    @pytest.mark.asyncio
    async def test_get_secret_invalid_key_format(self):
        """Test that keys without : separator return None."""
        provider = VaultSecretProvider(
            url="https://vault.example.com",
            token="test-token",
        )
        
        with patch.object(provider, "_get_client"):
            result = await provider.get_secret("invalid-key-no-colon")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_secret_success(self):
        """Test successful secret retrieval from Vault."""
        provider = VaultSecretProvider(
            url="https://vault.example.com",
            token="test-token",
        )
        
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"api_key": "secret-api-key"}}
        }
        
        with patch.object(provider, "_get_client", return_value=mock_client):
            # Mock run_in_executor to run synchronously
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(
                    side_effect=lambda executor, func: func()
                )
                
                # Directly test the sync method
                result = provider._read_secret_sync("path/to/secret:api_key")
                assert result == "secret-api-key"

    @pytest.mark.asyncio
    async def test_get_secret_vault_error(self):
        """Test handling of Vault errors."""
        provider = VaultSecretProvider(
            url="https://vault.example.com",
            token="test-token",
        )
        
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = Exception("Vault error")
        
        with patch.object(provider, "_get_client", return_value=mock_client):
            result = provider._read_secret_sync("path:key")
            assert result is None


class TestSecretService:
    """Tests for the main SecretService facade."""

    @pytest.mark.asyncio
    async def test_get_from_env_fallback(self):
        """Test service falls back to environment when Vault not configured."""
        service = SecretService(vault_provider=None)
        
        with patch.dict(os.environ, {"MY_SECRET": "env-value"}):
            result = await service.get("MY_SECRET")
            assert str(result) != "env-value"  # SecretString masks value
            assert result.get_secret_value() == "env-value"

    @pytest.mark.asyncio
    async def test_get_returns_default(self):
        """Test service returns default when secret not found."""
        service = SecretService(vault_provider=None)
        
        with patch.dict(os.environ, {}, clear=True):
            result = await service.get("NONEXISTENT", default="default-value")
            assert result.get_secret_value() == "default-value"

    @pytest.mark.asyncio
    async def test_get_raw_returns_string(self):
        """Test get_raw returns plain string."""
        service = SecretService(vault_provider=None)
        
        with patch.dict(os.environ, {"MY_SECRET": "raw-value"}):
            result = await service.get_raw("MY_SECRET")
            assert result == "raw-value"

    @pytest.mark.asyncio
    async def test_vault_takes_precedence(self):
        """Test Vault provider is checked before environment."""
        mock_vault = MagicMock(spec=VaultSecretProvider)
        mock_vault.get_secret = AsyncMock(return_value="vault-value")
        
        service = SecretService(vault_provider=mock_vault)
        
        with patch.dict(os.environ, {"MY_SECRET": "env-value"}):
            result = await service.get_raw("MY_SECRET")
            assert result == "vault-value"
            mock_vault.get_secret.assert_called_once_with("MY_SECRET")


class TestGetSecretService:
    """Tests for the service factory function."""

    def test_creates_singleton(self):
        """Test that factory returns singleton."""
        import agentorchestrator.services.secrets as secrets_module
        
        # Reset singleton
        secrets_module._instance = None
        
        service1 = get_secret_service()
        service2 = get_secret_service()
        
        assert service1 is service2

    def test_configures_vault_from_env(self):
        """Test Vault is configured when env vars present."""
        import agentorchestrator.services.secrets as secrets_module
        
        # Reset singleton
        secrets_module._instance = None
        
        with patch.dict(os.environ, {
            "VAULT_URL": "https://vault.example.com",
            "VAULT_TOKEN": "test-token",
        }):
            service = get_secret_service()
            
            # Should have Vault provider
            assert any(
                isinstance(p, VaultSecretProvider) 
                for p in service.providers
            )
