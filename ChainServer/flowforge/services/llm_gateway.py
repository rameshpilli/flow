"""
FlowForge LLM Gateway Client

OAuth-authenticated LLM gateway client for enterprise environments.
Supports both sync and async operations with timed caching.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                           TIMED LRU CACHE
# ═══════════════════════════════════════════════════════════════════════════════


def timed_lru_cache(seconds: int, maxsize: int = 128):
    """
    LRU cache with time-based expiration.

    Usage:
        @timed_lru_cache(seconds=3600)
        def get_config():
            return expensive_operation()
    """
    from functools import lru_cache

    def wrapped_cache(func):
        func = lru_cache(maxsize=maxsize)(func)
        func.lifetime = timedelta(seconds=seconds)
        func.expiration = datetime.now() + func.lifetime

        @wraps(func)
        def wrapped_func(*args, **kwargs):
            if datetime.now() > func.expiration:
                logger.info(
                    "Cache expired for function '%s'. Clearing cache. New expiration: %s",
                    func.__name__,
                    (datetime.now() + func.lifetime).strftime("%Y-%m-%d %H:%M:%S"),
                )
                func.cache_clear()
                func.expiration = datetime.now() + timedelta(seconds=seconds)
            return func(*args, **kwargs)

        wrapped_func.cache_clear = func.cache_clear
        wrapped_func.cache_info = func.cache_info
        return wrapped_func

    return wrapped_cache


# ═══════════════════════════════════════════════════════════════════════════════
#                           OAUTH TOKEN MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class OAuthTokenManager:
    """
    Manages OAuth token retrieval and caching.

    Caches tokens with TTL slightly less than actual expiry to prevent
    edge-case failures.
    """

    def __init__(
        self,
        oauth_endpoint: str,
        client_id: str,
        client_secret: str,
        grant_type: str = "client_credentials",
        scope: str = "read",
        token_ttl_seconds: int = 3500,  # ~1 hour, slightly less than typical 3600
    ):
        self.oauth_endpoint = oauth_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.grant_type = grant_type
        self.scope = scope
        self.token_ttl_seconds = token_ttl_seconds

        self._token: str | None = None
        self._token_expiry: datetime | None = None

    @property
    def token(self) -> str:
        """Get a valid OAuth token, refreshing if needed."""
        if self._token and self._token_expiry and datetime.now() < self._token_expiry:
            return self._token
        return self._fetch_token()

    def _fetch_token(self) -> str:
        """Fetch a new OAuth token synchronously."""
        if not all([self.client_id, self.client_secret, self.oauth_endpoint]):
            raise ValueError("OAuth credentials not configured (client_id, client_secret, oauth_endpoint)")

        try:
            with httpx.Client() as client:
                response = client.post(
                    self.oauth_endpoint,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": self.grant_type,
                        "scope": self.scope,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()

                token_data = response.json()
                self._token = token_data.get("access_token")

                if not self._token:
                    raise ValueError("No access_token in OAuth response")

                # Set expiry
                expires_in = token_data.get("expires_in", self.token_ttl_seconds)
                self._token_expiry = datetime.now() + timedelta(seconds=min(expires_in - 60, self.token_ttl_seconds))

                logger.info(f"OAuth token obtained, expires at {self._token_expiry}")
                return self._token

        except httpx.HTTPError as e:
            logger.error(f"OAuth token request failed: {e}")
            raise RuntimeError(f"Failed to get OAuth token: {e}") from e

    async def get_token_async(self) -> str:
        """Get a valid OAuth token asynchronously."""
        if self._token and self._token_expiry and datetime.now() < self._token_expiry:
            return self._token
        return await self._fetch_token_async()

    async def _fetch_token_async(self) -> str:
        """Fetch a new OAuth token asynchronously."""
        if not all([self.client_id, self.client_secret, self.oauth_endpoint]):
            raise ValueError("OAuth credentials not configured")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.oauth_endpoint,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": self.grant_type,
                        "scope": self.scope,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()

                token_data = response.json()
                self._token = token_data.get("access_token")

                if not self._token:
                    raise ValueError("No access_token in OAuth response")

                expires_in = token_data.get("expires_in", self.token_ttl_seconds)
                self._token_expiry = datetime.now() + timedelta(seconds=min(expires_in - 60, self.token_ttl_seconds))

                logger.info(f"OAuth token obtained (async), expires at {self._token_expiry}")
                return self._token

        except httpx.HTTPError as e:
            logger.error(f"OAuth token request failed: {e}")
            raise RuntimeError(f"Failed to get OAuth token: {e}") from e


# ═══════════════════════════════════════════════════════════════════════════════
#                           LLM GATEWAY CLIENT
# ═══════════════════════════════════════════════════════════════════════════════


class LLMGatewayClient:
    """
    Enterprise LLM Gateway client with OAuth authentication.

    Provides both sync and async methods for interacting with
    LLM gateway endpoints (OpenAI-compatible API).

    Usage:
        # Direct instantiation
        client = LLMGatewayClient(
            server_url="https://llm-gateway.company.com/v1",
            model_name="gpt-4",
            oauth_endpoint="https://auth.company.com/oauth/token",
            client_id="your-client-id",
            client_secret="your-client-secret",
        )
        response = await client.generate("Tell me about Apple Inc")

        # Or use factory function with environment variables
        client = get_llm_client()
    """

    def __init__(
        self,
        server_url: str,
        model_name: str,
        oauth_endpoint: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_key: str | None = None,  # Alternative to OAuth
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ):
        """
        Initialize the LLM Gateway client.

        Args:
            server_url: Base URL of the LLM gateway (e.g., https://llm.company.com/v1)
            model_name: Model to use (e.g., gpt-4, claude-3-sonnet)
            oauth_endpoint: OAuth token endpoint (for enterprise auth)
            client_id: OAuth client ID
            client_secret: OAuth client secret
            api_key: Direct API key (alternative to OAuth)
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
        """
        self.server_url = server_url.rstrip("/")
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        # Authentication
        self._api_key = api_key
        self._token_manager: OAuthTokenManager | None = None

        if oauth_endpoint and client_id and client_secret:
            self._token_manager = OAuthTokenManager(
                oauth_endpoint=oauth_endpoint,
                client_id=client_id,
                client_secret=client_secret,
            )

        # For LangChain integration
        self._langchain_llm: Any | None = None

    def _get_auth_header(self) -> dict[str, str]:
        """Get authorization header with token or API key."""
        if self._token_manager:
            token = self._token_manager.token
            return {"Authorization": f"Bearer {token}"}
        elif self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        else:
            raise ValueError("No authentication configured (OAuth or API key)")

    async def _get_auth_header_async(self) -> dict[str, str]:
        """Get authorization header asynchronously."""
        if self._token_manager:
            token = await self._token_manager.get_token_async()
            return {"Authorization": f"Bearer {token}"}
        elif self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        else:
            raise ValueError("No authentication configured (OAuth or API key)")

    # ═══════════════════════════════════════════════════════════════════════════
    #                           SYNC METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate a response synchronously.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            Generated text response
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return self.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Chat completion synchronously.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            Generated text response
        """
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.server_url}/chat/completions",
                    json=payload,
                    headers={
                        **self._get_auth_header(),
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()

                data = response.json()
                return data["choices"][0]["message"]["content"]

        except httpx.HTTPError as e:
            logger.error(f"LLM request failed: {e}")
            raise RuntimeError(f"LLM request failed: {e}") from e

    # ═══════════════════════════════════════════════════════════════════════════
    #                           ASYNC METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    async def generate_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate a response asynchronously.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            Generated text response
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.chat_async(messages, temperature=temperature, max_tokens=max_tokens)

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Chat completion asynchronously.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            Generated text response
        """
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                auth_header = await self._get_auth_header_async()
                response = await client.post(
                    f"{self.server_url}/chat/completions",
                    json=payload,
                    headers={
                        **auth_header,
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()

                data = response.json()
                return data["choices"][0]["message"]["content"]

        except httpx.HTTPError as e:
            logger.error(f"LLM request failed: {e}")
            raise RuntimeError(f"LLM request failed: {e}") from e

    # ═══════════════════════════════════════════════════════════════════════════
    #                       LANGCHAIN INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════════

    def get_langchain_llm(self) -> Any:
        """
        Get a LangChain-compatible LLM instance.

        Returns a ChatOpenAI instance configured to use this gateway.

        Usage:
            llm = client.get_langchain_llm()
            result = await llm.ainvoke("Hello")
        """
        if self._langchain_llm is not None:
            return self._langchain_llm

        try:
            from langchain_openai import ChatOpenAI

            # Get API key (OAuth token or direct key)
            if self._token_manager:
                api_key = self._token_manager.token
            elif self._api_key:
                api_key = self._api_key
            else:
                raise ValueError("No authentication configured")

            self._langchain_llm = ChatOpenAI(
                base_url=self.server_url,
                model=self.model_name,
                api_key=api_key,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            self._langchain_llm.model_rebuild()

            return self._langchain_llm

        except ImportError:
            raise ImportError(
                "langchain-openai is required for LangChain integration. "
                "Install with: pip install langchain-openai"
            )

    def refresh_langchain_token(self) -> None:
        """Refresh the OAuth token for LangChain LLM instance."""
        if self._token_manager and self._langchain_llm:
            self._langchain_llm.api_key = self._token_manager.token
            logger.info("LangChain LLM token refreshed")


# ═══════════════════════════════════════════════════════════════════════════════
#                           FACTORY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def get_llm_client(
    server_url: str | None = None,
    model_name: str | None = None,
    oauth_endpoint: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    api_key: str | None = None,
    **kwargs,
) -> LLMGatewayClient:
    """
    Factory function to create an LLM Gateway client.

    Reads from environment variables if not provided:
    - LLM_GATEWAY_URL: Server URL
    - LLM_MODEL_NAME: Model name (default: gpt-4)
    - LLM_OAUTH_ENDPOINT: OAuth token endpoint
    - LLM_CLIENT_ID: OAuth client ID
    - LLM_CLIENT_SECRET: OAuth client secret
    - LLM_API_KEY: Direct API key (alternative to OAuth)

    Usage:
        # Using environment variables
        client = get_llm_client()

        # With explicit config
        client = get_llm_client(
            server_url="https://llm.company.com/v1",
            model_name="gpt-4",
            api_key="sk-xxx",
        )
    """
    import os

    return LLMGatewayClient(
        server_url=server_url or os.getenv("LLM_GATEWAY_URL", ""),
        model_name=model_name or os.getenv("LLM_MODEL_NAME", "gpt-4"),
        oauth_endpoint=oauth_endpoint or os.getenv("LLM_OAUTH_ENDPOINT"),
        client_id=client_id or os.getenv("LLM_CLIENT_ID"),
        client_secret=client_secret or os.getenv("LLM_CLIENT_SECRET"),
        api_key=api_key or os.getenv("LLM_API_KEY"),
        **kwargs,
    )


# Singleton instance for shared usage
_default_client: LLMGatewayClient | None = None


def get_default_llm_client() -> LLMGatewayClient | None:
    """Get the default LLM client instance (singleton)."""
    global _default_client
    return _default_client


def set_default_llm_client(client: LLMGatewayClient) -> None:
    """Set the default LLM client instance."""
    global _default_client
    _default_client = client
    logger.info(f"Default LLM client set: {client.model_name} @ {client.server_url}")


def init_default_llm_client(**kwargs) -> LLMGatewayClient:
    """Initialize and set the default LLM client from environment or kwargs."""
    client = get_llm_client(**kwargs)
    set_default_llm_client(client)
    return client
