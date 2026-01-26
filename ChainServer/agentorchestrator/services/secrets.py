"""
AgentOrchestrator Secret Management Service
===========================================

Provides a unified interface for retrieving secrets from multiple providers.
Supports HashiCorp Vault and falls back to environment variables.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
from agentorchestrator.config import SecretString

logger = logging.getLogger(__name__)

class SecretProvider(ABC):
    @abstractmethod
    async def get_secret(self, key: str) -> Optional[str]:
        pass

class EnvSecretProvider(SecretProvider):
    """Retrieves secrets from environment variables."""
    async def get_secret(self, key: str) -> Optional[str]:
        return os.getenv(key)

class VaultSecretProvider(SecretProvider):
    """Retrieves secrets from HashiCorp Vault."""
    
    def __init__(self, url: str, token: str, mount_point: str = "secret"):
        self.url = url
        self.token = token
        self.mount_point = mount_point
        self._client = None

    def _get_client(self):
        if not self._client:
            try:
                import hvac
                self._client = hvac.Client(url=self.url, token=self.token)
            except ImportError:
                logger.error("hvac package not installed. Run 'pip install hvac'")
                raise RuntimeError("hvac not installed")
        return self._client

    async def get_secret(self, key: str) -> Optional[str]:
        """
        Retrieves a secret from Vault. 
        Expects key in format 'path/to/secret:data_key'
        """
        try:
            client = self._get_client()
            if ":" not in key:
                logger.warning(f"Vault key {key} missing data_key suffix (path:key)")
                return None
                
            path, data_key = key.split(":", 1)
            read_response = client.secrets.kv.v2.read_secret_version(
                path=path, mount_point=self.mount_point
            )
            return read_response['data']['data'].get(data_key)
        except Exception as e:
            logger.error(f"Failed to retrieve secret {key} from Vault: {e}")
            return None

class SecretService:
    """
    Main service facade for secret management.
    Checks providers in order: Vault (if configured) -> Environment.
    """
    
    def __init__(self, vault_provider: Optional[VaultSecretProvider] = None):
        self.providers: list[SecretProvider] = []
        if vault_provider:
            self.providers.append(vault_provider)
        self.providers.append(EnvSecretProvider())

    async def get(self, key: str, default: Optional[str] = None) -> SecretString:
        """Get secret as a masked SecretString."""
        for provider in self.providers:
            val = await provider.get_secret(key)
            if val:
                return SecretString(val)
        return SecretString(default)

    async def get_raw(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get raw secret string value."""
        for provider in self.providers:
            val = await provider.get_secret(key)
            if val:
                return val
        return default

_instance: Optional[SecretService] = None

def get_secret_service() -> SecretService:
    global _instance
    if not _instance:
        # Auto-configure Vault if env vars present
        vault_url = os.getenv("VAULT_URL")
        vault_token = os.getenv("VAULT_TOKEN")
        vp = None
        if vault_url and vault_token:
            vp = VaultSecretProvider(vault_url, vault_token)
        _instance = SecretService(vault_provider=vp)
    return _instance
