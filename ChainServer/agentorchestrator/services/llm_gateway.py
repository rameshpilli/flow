"""
LLM Gateway Client

Provides a thin wrapper around LLM providers (OpenAI, Anthropic, etc.)
with OAuth token management and caching support.

For corporate environments that require going through an LLM gateway
with OAuth authentication.

Usage:
    from agentorchestrator.services import LLMGatewayClient, LLMGatewayConfig

    # Option 1: Direct configuration
    client = LLMGatewayClient(
        server_url="https://llm-gateway.corp.com/api/chat",
        api_key="your-api-key",
    )

    # Option 2: From environment variables
    client = LLMGatewayClient.from_env()

    # Option 3: Using config class
    config = LLMGatewayConfig.from_env()
    client = LLMGatewayClient.from_config(config)

    response = await client.generate_async("Hello, world!")
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from agentorchestrator.utils.caching import timed_lru_cache, async_timed_lru_cache

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ═══════════════════════════════════════════════════════════════════════════════
#                         CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class LLMGatewayConfig:
    """
    LLM Gateway configuration.

    Supports both direct configuration and environment variable loading.

    Environment Variables:
        LLM_SERVER_URL: LLM gateway endpoint URL
        LLM_MODEL_NAME: Model to use (default: gpt-4)
        LLM_API_KEY: API key (alternative to OAuth)
        LLM_OAUTH_ENDPOINT: OAuth token endpoint
        LLM_CLIENT_ID: OAuth client ID
        LLM_CLIENT_SECRET: OAuth client secret
        LLM_TEMPERATURE: Sampling temperature (default: 0.2)
        LLM_MAX_TOKENS: Max output tokens (default: 4096)
        LLM_TIMEOUT: Request timeout in seconds (default: 120)
    """

    server_url: str | None = None
    model_name: str = "gpt-4"
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: float = 120.0

    # Authentication - either OAuth or API key
    api_key: str | None = None
    oauth_endpoint: str | None = None
    client_id: str | None = None
    client_secret: str | None = None

    @classmethod
    def from_env(cls) -> "LLMGatewayConfig":
        """Load configuration from environment variables."""
        return cls(
            server_url=os.getenv("LLM_SERVER_URL"),
            model_name=os.getenv("LLM_MODEL_NAME", "gpt-4"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
            timeout=float(os.getenv("LLM_TIMEOUT", "120.0")),
            api_key=os.getenv("LLM_API_KEY"),
            oauth_endpoint=os.getenv("LLM_OAUTH_ENDPOINT"),
            client_id=os.getenv("LLM_CLIENT_ID"),
            client_secret=os.getenv("LLM_CLIENT_SECRET"),
        )

    def is_valid(self) -> bool:
        """Check if configuration has required fields."""
        has_auth = bool(self.api_key) or all([
            self.oauth_endpoint,
            self.client_id,
            self.client_secret,
        ])
        return bool(self.server_url) and has_auth


class OAuthTokenManager:
    """Manages OAuth tokens with automatic refresh."""

    def __init__(
        self,
        oauth_endpoint: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        grant_type: str = "client_credentials",
        scope: str = "read",
        token_expiry_seconds: int = 3500,  # Refresh before actual expiry
    ):
        self.oauth_endpoint = oauth_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.grant_type = grant_type
        self.scope = scope
        self.token_expiry_seconds = token_expiry_seconds
        self._token: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str | None:
        """Get a valid token, refreshing if necessary."""
        async with self._lock:
            if self._token and time.time() < self._expires_at:
                return self._token

            # Fetch new token
            if not all([self.oauth_endpoint, self.client_id, self.client_secret]):
                logger.warning("OAuth credentials not configured, cannot fetch token")
                return None

            try:
                import httpx

                data = {
                    "grant_type": self.grant_type,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": self.scope,
                }

                async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                    response = await client.post(
                        self.oauth_endpoint,
                        data=data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    response.raise_for_status()
                    result = response.json()

                    self._token = result.get("access_token")
                    # Use expires_in from response, or default
                    expires_in = result.get("expires_in", self.token_expiry_seconds)
                    self._expires_at = time.time() + min(expires_in - 60, self.token_expiry_seconds)

                    logger.info(f"OAuth token refreshed, expires in {expires_in}s")
                    return self._token

            except ImportError:
                logger.error("httpx not installed, cannot fetch OAuth token")
                return None
            except Exception as e:
                logger.error(f"Failed to fetch OAuth token: {e}")
                return None

    def set_token(self, token: str, expires_in: int = 3600):
        """Manually set a token."""
        self._token = token
        self._expires_at = time.time() + expires_in


class LLMGatewayClient:
    """
    Client for LLM API calls with OAuth support.

    Uses OAuth token management to authenticate with LLM gateway.
    Supports OpenAI-compatible chat completion API.

    Usage:
        client = LLMGatewayClient(
            server_url="https://llm-gateway/v1/chat/completions",
            oauth_endpoint="https://auth/token",
            client_id="...",
            client_secret="...",
            model_name="claude-sonnet-4",
        )
        response = await client.generate_async("What is 2+2?")
    """

    def __init__(
        self,
        server_url: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        oauth_endpoint: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_key: str | None = None,
    ):
        self.server_url = server_url
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.api_key = api_key

        # Set up OAuth token manager if OAuth credentials provided
        if oauth_endpoint and client_id and client_secret:
            self._token_manager = OAuthTokenManager(
                oauth_endpoint=oauth_endpoint,
                client_id=client_id,
                client_secret=client_secret,
            )
            logger.info(f"LLMGatewayClient configured with OAuth: {oauth_endpoint}")
        else:
            self._token_manager = None
            if api_key:
                logger.info("LLMGatewayClient configured with API key")
            else:
                logger.warning("LLMGatewayClient has no auth configured (will use stub mode)")

        # Lock for async client initialization
        self._async_client_lock = asyncio.Lock()
        self._async_client = None

    @classmethod
    def from_env(cls) -> "LLMGatewayClient":
        """Create client from environment variables."""
        config = LLMGatewayConfig.from_env()
        return cls.from_config(config)

    @classmethod
    def from_config(cls, config: LLMGatewayConfig) -> "LLMGatewayClient":
        """Create client from config object."""
        return cls(
            server_url=config.server_url,
            model_name=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            api_key=config.api_key,
            oauth_endpoint=config.oauth_endpoint,
            client_id=config.client_id,
            client_secret=config.client_secret,
        )

    def _is_configured(self) -> bool:
        """Check if client is properly configured for real API calls."""
        return bool(self.server_url and (self._token_manager or self.api_key))

    async def _get_async_client(self):
        """Get or create async HTTP client (thread-safe)."""
        async with self._async_client_lock:
            if self._async_client is None:
                try:
                    import httpx
                    self._async_client = httpx.AsyncClient(timeout=self.timeout, verify=False)
                except ImportError:
                    logger.warning("httpx not installed, using stub client")
            return self._async_client

    async def _get_auth_token(self) -> str | None:
        """Get authentication token (OAuth or API key)."""
        if self._token_manager:
            return await self._token_manager.get_token()
        return self.api_key

    async def _call_llm_api(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> dict[str, Any]:
        """Call the LLM API with proper authentication."""
        client = await self._get_async_client()
        if not client:
            raise RuntimeError("HTTP client not available")

        token = await self._get_auth_token()
        if not token:
            raise RuntimeError("No authentication token available")

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        # Add temperature if supported
        if self.temperature is not None:
            payload["temperature"] = self.temperature

        # Add any additional parameters
        for key in ["tools", "tool_choice", "response_format"]:
            if key in kwargs:
                payload[key] = kwargs[key]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        logger.debug(f"Calling LLM API: {self.server_url}, model={self.model_name}")

        response = await client.post(
            self.server_url,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (~4 chars per token for most models)."""
        return len(text) // 4

    def _truncate_if_needed(
        self,
        prompt: str,
        max_input_tokens: int = 100000,
    ) -> str:
        """Truncate prompt if it exceeds max input tokens.

        This is a safety measure to prevent 400 errors from the LLM API.
        The framework's OffloadMiddleware should handle large payloads properly,
        but this provides a fallback in case content is still too large.
        """
        estimated_tokens = self._estimate_tokens(prompt)
        if estimated_tokens <= max_input_tokens:
            return prompt

        # Truncate to fit, leaving room for response
        max_chars = max_input_tokens * 4
        logger.warning(
            f"Prompt too large ({estimated_tokens} tokens), truncating to {max_input_tokens} tokens. "
            "Consider using OffloadMiddleware or SummarizerMiddleware for better handling."
        )
        return prompt[:max_chars] + "\n\n... [CONTENT TRUNCATED - use SummarizerMiddleware for intelligent summarization]"

    async def generate_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_input_tokens: int = 100000,
        **kwargs,
    ) -> str:
        """Generate text from a prompt.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_input_tokens: Max input tokens before truncation (default 100K)
            **kwargs: Additional parameters for the LLM API
        """
        # Check if configured for real API calls
        if not self._is_configured():
            logger.info(f"LLM generate (stub): {prompt[:50]}...")
            return f"[LLM Response for: {prompt[:30]}...]"

        # Truncate if needed to prevent 400 errors
        prompt = self._truncate_if_needed(prompt, max_input_tokens)

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            data = await self._call_llm_api(messages, **kwargs)

            # Parse OpenAI-compatible response
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})

            if "content" in message:
                return message["content"]
            elif "tool_calls" in message:
                # Return tool calls as formatted string
                tool_calls = message["tool_calls"]
                return json.dumps(tool_calls, indent=2)
            else:
                logger.warning(f"Unexpected LLM response format: {data}")
                return str(data)

        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise

    async def generate_structured_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_model: type[T] | None = None,
        **kwargs,
    ) -> T | dict:
        """Generate structured output from a prompt."""
        # Check if configured for real API calls
        if not self._is_configured():
            logger.info(f"LLM structured generate (stub): {prompt[:50]}...")
            if response_model:
                try:
                    return response_model()
                except Exception:
                    return {}
            return {}

        # For structured output, we'll ask the LLM to respond in JSON
        # and then parse it into the response model
        if system_prompt:
            enhanced_system = f"{system_prompt}\n\nRespond with valid JSON only."
        else:
            enhanced_system = "Respond with valid JSON only."

        try:
            response_text = await self.generate_async(
                prompt=prompt,
                system_prompt=enhanced_system,
                **kwargs,
            )

            # Try to parse as JSON
            try:
                # Handle markdown code blocks
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]

                data = json.loads(response_text.strip())

                if response_model:
                    return response_model(**data)
                return data

            except json.JSONDecodeError:
                logger.warning(f"Failed to parse LLM response as JSON: {response_text[:200]}")
                if response_model:
                    try:
                        return response_model()
                    except Exception:
                        pass
                return {"raw_response": response_text}

        except Exception as e:
            logger.error(f"Structured generation failed: {e}")
            if response_model:
                try:
                    return response_model()
                except Exception:
                    pass
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


def create_llm_client_from_env() -> LLMGatewayClient:
    """Create an LLM client from environment variables.

    Required env vars:
        LLM_SERVER_URL: The LLM API endpoint
        LLM_OAUTH_ENDPOINT: OAuth token endpoint
        LLM_CLIENT_ID: OAuth client ID
        LLM_CLIENT_SECRET: OAuth client secret

    Optional env vars:
        LLM_MODEL_NAME: Model to use (default: gpt-4)
        LLM_MAX_TOKENS: Max tokens (default: 4096)
        LLM_TEMPERATURE: Temperature (default: 0.2)
    """
    return LLMGatewayClient(
        server_url=os.getenv("LLM_SERVER_URL"),
        oauth_endpoint=os.getenv("LLM_OAUTH_ENDPOINT"),
        client_id=os.getenv("LLM_CLIENT_ID"),
        client_secret=os.getenv("LLM_CLIENT_SECRET"),
        model_name=os.getenv("LLM_MODEL_NAME", "gpt-4"),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
    )


def create_managed_client(
    token_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    **kwargs,
) -> LLMGatewayClient:
    """Create an LLM client with OAuth token management."""
    return LLMGatewayClient(
        oauth_endpoint=token_url,
        client_id=client_id,
        client_secret=client_secret,
        **kwargs,
    )


__all__ = [
    # Config
    "LLMGatewayConfig",
    # Client
    "LLMGatewayClient",
    "OAuthTokenManager",
    # Factory functions
    "get_llm_client",
    "get_default_llm_client",
    "set_default_llm_client",
    "init_default_llm_client",
    "create_llm_client_from_env",
    "create_managed_client",
    # Caching utilities (re-exported for convenience)
    "timed_lru_cache",
    "async_timed_lru_cache",
]
