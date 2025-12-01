"""
LLM Gateway Client

Provides a thin wrapper around LLM providers (OpenAI, Anthropic, etc.)
with OAuth token management and caching support.
"""

import functools
import logging
import time
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def timed_lru_cache(seconds: int = 300, maxsize: int = 128):
    """LRU cache decorator with time-based expiration."""
    def decorator(func):
        cache = {}
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            if key in cache:
                result, timestamp = cache[key]
                if now - timestamp < seconds:
                    return result
            result = func(*args, **kwargs)
            cache[key] = (result, now)
            # Evict old entries if cache is too large
            if len(cache) > maxsize:
                oldest = min(cache.keys(), key=lambda k: cache[k][1])
                del cache[oldest]
            return result
        return wrapper
    return decorator


class OAuthTokenManager:
    """Manages OAuth tokens with automatic refresh."""

    def __init__(
        self,
        token_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        scope: str | None = None,
    ):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self._token: str | None = None
        self._expires_at: float = 0

    async def get_token(self) -> str | None:
        """Get a valid token, refreshing if necessary."""
        if self._token and time.time() < self._expires_at:
            return self._token
        # In production, implement actual OAuth flow
        return self._token

    def set_token(self, token: str, expires_in: int = 3600):
        """Manually set a token."""
        self._token = token
        self._expires_at = time.time() + expires_in


class LLMGatewayClient:
    """
    Client for LLM API calls with optional OAuth support.

    Usage:
        client = LLMGatewayClient(api_key="...", model="gpt-4")
        response = await client.generate_async("What is 2+2?")
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4",
        base_url: str | None = None,
        token_manager: OAuthTokenManager | None = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.token_manager = token_manager
        self.timeout = timeout

    async def generate_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs,
    ) -> str:
        """Generate text from a prompt."""
        # Stub implementation - in production, call actual LLM API
        logger.info(f"LLM generate (stub): {prompt[:50]}...")
        return f"[LLM Response for: {prompt[:30]}...]"

    async def generate_structured_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_model: type[T] | None = None,
        **kwargs,
    ) -> T | dict:
        """Generate structured output from a prompt."""
        # Stub implementation - in production, use instructor or similar
        logger.info(f"LLM structured generate (stub): {prompt[:50]}...")
        if response_model:
            # Return empty model instance
            try:
                return response_model()
            except Exception:
                return {}
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
#                       GLOBAL CLIENT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

_default_client: LLMGatewayClient | None = None


def get_default_llm_client() -> LLMGatewayClient | None:
    """Get the default LLM client."""
    return _default_client


def set_default_llm_client(client: LLMGatewayClient):
    """Set the default LLM client."""
    global _default_client
    _default_client = client


def init_default_llm_client(**kwargs) -> LLMGatewayClient:
    """Initialize and set the default LLM client."""
    client = LLMGatewayClient(**kwargs)
    set_default_llm_client(client)
    return client


def get_llm_client(**kwargs) -> LLMGatewayClient:
    """Get or create an LLM client."""
    if not kwargs:
        return get_default_llm_client() or LLMGatewayClient()
    return LLMGatewayClient(**kwargs)


def create_managed_client(
    token_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    **kwargs,
) -> LLMGatewayClient:
    """Create an LLM client with OAuth token management."""
    token_manager = OAuthTokenManager(
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret,
    )
    return LLMGatewayClient(token_manager=token_manager, **kwargs)


__all__ = [
    "LLMGatewayClient",
    "OAuthTokenManager",
    "timed_lru_cache",
    "get_llm_client",
    "get_default_llm_client",
    "set_default_llm_client",
    "init_default_llm_client",
    "create_managed_client",
]
