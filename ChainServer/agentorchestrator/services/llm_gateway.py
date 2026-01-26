"""
AgentOrchestrator LLM Gateway Client
====================================

This module provides a client for interacting with LLM APIs through corporate
gateways with OAuth token management and caching support.

The LLMGatewayClient handles authentication (OAuth or API key), request
formatting, and response parsing for OpenAI-compatible chat completion APIs.
Designed for corporate environments that require going through an LLM gateway
with OAuth authentication.

Classes:
    LLMGatewayConfig: Configuration dataclass for LLM gateway settings.
    OAuthTokenManager: Manages OAuth tokens with automatic refresh.
    LLMGatewayClient: Main client for LLM API calls with OAuth/API key support.

Functions:
    get_llm_client: Get or create an LLM client instance.
    get_default_llm_client: Get the default global LLM client.
    set_default_llm_client: Set the default global LLM client.
    init_default_llm_client: Initialize and set the default LLM client.
    create_llm_client_from_env: Create client from environment variables.
    create_managed_client: Create client with OAuth token management.

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

    # Generate text
    response = await client.generate_async("Hello, world!")

Example:
    >>> from agentorchestrator.services import LLMGatewayClient
    >>>
    >>> # Create client with OAuth
    >>> client = LLMGatewayClient(
    ...     server_url="https://llm-gateway/v1/chat/completions",
    ...     oauth_endpoint="https://auth/token",
    ...     client_id="my-app",
    ...     client_secret="secret",
    ...     model_name="gpt-4",
    ... )
    >>>
    >>> # Simple generation
    >>> response = await client.generate_async("What is 2+2?")
    >>> print(response)  # "4"
    >>>
    >>> # Structured generation
    >>> from pydantic import BaseModel
    >>> class Answer(BaseModel):
    ...     value: int
    ...     explanation: str
    >>>
    >>> result = await client.generate_structured_async(
    ...     prompt="What is 2+2?",
    ...     response_model=Answer,
    ... )
    >>> print(result.value)  # 4

See Also:
    - agentorchestrator.utils.caching: Caching utilities for LLM responses.
    - agentorchestrator.middleware: Middleware for rate limiting and offloading.
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
    Configuration for LLM Gateway client.

    This dataclass holds all configuration needed to connect to an LLM gateway,
    including server URL, model settings, and authentication credentials.
    Supports both direct configuration and environment variable loading.

    Attributes:
        server_url (str | None): LLM gateway endpoint URL.
            Example: "https://llm-gateway.corp.com/v1/chat/completions"
        model_name (str): Model to use for generation. Default: "gpt-4".
        temperature (float): Sampling temperature (0.0-2.0). Default: 0.2.
            Lower values = more deterministic, higher = more creative.
        max_tokens (int): Maximum output tokens. Default: 4096.
        timeout (float): Request timeout in seconds. Default: 120.0.
        api_key (str | None): API key for authentication. Default: None.
            Use this for simple API key auth, or OAuth credentials below.
        oauth_endpoint (str | None): OAuth token endpoint URL. Default: None.
        client_id (str | None): OAuth client ID. Default: None.
        client_secret (str | None): OAuth client secret. Default: None.

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

    Methods:
        from_env(): Load configuration from environment variables.
        is_valid(): Check if configuration has required fields.

    Example:
        >>> # Direct configuration
        >>> config = LLMGatewayConfig(
        ...     server_url="https://llm-gateway/v1/chat/completions",
        ...     model_name="gpt-4",
        ...     api_key="sk-xxx",
        ...     temperature=0.5,
        ... )
        >>>
        >>> # From environment variables
        >>> config = LLMGatewayConfig.from_env()
        >>> if config.is_valid():
        ...     client = LLMGatewayClient.from_config(config)

    See Also:
        LLMGatewayClient: Client that uses this configuration.
        OAuthTokenManager: OAuth token handling for corporate environments.
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
        """
        Load configuration from environment variables.

        Reads LLM_* environment variables and creates a configuration
        instance. This is the recommended way to configure the client
        in production environments.

        Returns:
            LLMGatewayConfig: Configuration loaded from environment.

        Example:
            >>> import os
            >>> os.environ["LLM_SERVER_URL"] = "https://llm-gateway/api"
            >>> os.environ["LLM_API_KEY"] = "sk-xxx"
            >>> config = LLMGatewayConfig.from_env()
            >>> print(config.server_url)  # "https://llm-gateway/api"
        """
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
        """
        Check if configuration has required fields.

        A valid configuration requires:
        - server_url to be set
        - Either api_key OR all OAuth credentials (endpoint, client_id, client_secret)

        Returns:
            bool: True if configuration is valid, False otherwise.

        Example:
            >>> config = LLMGatewayConfig(server_url="https://api", api_key="key")
            >>> config.is_valid()  # True
            >>>
            >>> config = LLMGatewayConfig()  # No URL or auth
            >>> config.is_valid()  # False
        """
        has_auth = bool(self.api_key) or all([
            self.oauth_endpoint,
            self.client_id,
            self.client_secret,
        ])
        return bool(self.server_url) and has_auth


class OAuthTokenManager:
    """
    Manages OAuth tokens with automatic refresh.

    This class handles OAuth 2.0 client credentials flow for corporate
    LLM gateways. It automatically refreshes tokens before expiry and
    caches them to minimize token endpoint calls.

    Attributes:
        oauth_endpoint (str | None): OAuth token endpoint URL.
        client_id (str | None): OAuth client ID.
        client_secret (str | None): OAuth client secret.
        grant_type (str): OAuth grant type. Default: "client_credentials".
        scope (str): OAuth scope. Default: "read".
        token_expiry_seconds (int): Token refresh threshold. Default: 3500.

    Methods:
        get_token(): Get a valid token, refreshing if necessary.
        set_token(): Manually set a token with expiry.

    Example:
        >>> manager = OAuthTokenManager(
        ...     oauth_endpoint="https://auth.corp.com/oauth/token",
        ...     client_id="my-app",
        ...     client_secret="secret",
        ... )
        >>>
        >>> # Get token (fetches automatically if needed)
        >>> token = await manager.get_token()
        >>> print(token)  # "eyJ..."
        >>>
        >>> # Token is cached and reused until near expiry
        >>> token2 = await manager.get_token()  # Returns cached token

    See Also:
        LLMGatewayClient: Uses this manager for OAuth authentication.
    """

    def __init__(
        self,
        oauth_endpoint: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        grant_type: str = "client_credentials",
        scope: str = "read",
        token_expiry_seconds: int = 3500,  # Refresh before actual expiry
    ):
        """
        Initialize OAuth token manager.

        Args:
            oauth_endpoint (str | None): OAuth token endpoint URL.
                Example: "https://auth.corp.com/oauth/token"
            client_id (str | None): OAuth client ID.
            client_secret (str | None): OAuth client secret.
            grant_type (str): OAuth grant type. Default: "client_credentials".
            scope (str): OAuth scope to request. Default: "read".
            token_expiry_seconds (int): Seconds before token refresh. Default: 3500.
                Set lower than actual expiry to refresh proactively.

        Example:
            >>> manager = OAuthTokenManager(
            ...     oauth_endpoint="https://auth/token",
            ...     client_id="app-id",
            ...     client_secret="app-secret",
            ...     token_expiry_seconds=3000,  # Refresh 10 min before expiry
            ... )
        """
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
        """
        Get a valid OAuth token, refreshing if necessary.

        This method is thread-safe and handles concurrent requests.
        It will return a cached token if still valid, or fetch a new
        one if expired or missing.

        Returns:
            str | None: Valid OAuth access token, or None if fetch fails.

        Raises:
            None: Errors are logged, None is returned on failure.

        Example:
            >>> token = await manager.get_token()
            >>> if token:
            ...     headers = {"Authorization": f"Bearer {token}"}
            ... else:
            ...     raise RuntimeError("Failed to get token")
        """
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

                # SSL verification - respect environment setting
                verify_ssl = os.getenv("LLM_VERIFY_SSL", "true").lower() != "false"
                async with httpx.AsyncClient(timeout=30.0, verify=verify_ssl) as client:
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
                    # Ensure we don't go negative - floor at 60 seconds minimum
                    # This prevents rapid refresh loops with short-lived tokens
                    buffer_seconds = min(60, expires_in // 2)  # Use half of expires_in if < 120s
                    effective_expiry = max(expires_in - buffer_seconds, 60)
                    self._expires_at = time.time() + min(effective_expiry, self.token_expiry_seconds)

                    logger.info(f"OAuth token refreshed, expires in {expires_in}s")
                    return self._token

            except ImportError:
                logger.error("httpx not installed, cannot fetch OAuth token")
                return None
            except Exception as e:
                logger.error(f"Failed to fetch OAuth token: {e}")
                return None

    def set_token(self, token: str, expires_in: int = 3600):
        """
        Manually set a token with expiry time.

        Use this to inject a pre-fetched token or for testing.

        Args:
            token (str): The OAuth access token.
            expires_in (int): Seconds until token expires. Default: 3600.

        Example:
            >>> manager.set_token("eyJ...", expires_in=7200)
        """
        self._token = token
        self._expires_at = time.time() + expires_in


class LLMGatewayClient:
    """
    Client for LLM API calls with OAuth support.

    This is the main client for interacting with LLM gateways. It handles:
    - OAuth token management for corporate environments
    - API key authentication as alternative
    - OpenAI-compatible chat completion API formatting
    - Automatic prompt truncation for large inputs
    - Structured output generation with JSON parsing

    Attributes:
        server_url (str | None): LLM gateway endpoint URL.
        model_name (str | None): Model name for generation.
        temperature (float): Sampling temperature.
        max_tokens (int): Maximum output tokens.
        timeout (float): Request timeout in seconds.
        api_key (str | None): API key if using key-based auth.

    Methods:
        from_env(): Create client from environment variables.
        from_config(): Create client from LLMGatewayConfig.
        generate_async(): Generate text from a prompt.
        generate_structured_async(): Generate structured JSON output.

    Example:
        >>> # With OAuth authentication
        >>> client = LLMGatewayClient(
        ...     server_url="https://llm-gateway/v1/chat/completions",
        ...     oauth_endpoint="https://auth/token",
        ...     client_id="my-app",
        ...     client_secret="secret",
        ...     model_name="gpt-4",
        ... )
        >>>
        >>> # Simple text generation
        >>> response = await client.generate_async(
        ...     prompt="Explain quantum computing",
        ...     system_prompt="You are a helpful assistant.",
        ... )
        >>> print(response)
        >>>
        >>> # With API key authentication
        >>> client = LLMGatewayClient(
        ...     server_url="https://api.openai.com/v1/chat/completions",
        ...     api_key="sk-xxx",
        ...     model_name="gpt-4",
        ... )

    Note:
        If neither OAuth nor API key is configured, the client operates
        in "stub mode" and returns placeholder responses. This is useful
        for testing without actual LLM calls.

    See Also:
        LLMGatewayConfig: Configuration class for this client.
        OAuthTokenManager: OAuth token handling.
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
        """
        Initialize LLM Gateway client.

        Args:
            server_url (str | None): LLM gateway endpoint URL.
                Example: "https://llm-gateway/v1/chat/completions"
            model_name (str | None): Model to use. Default: None.
                Common values: "gpt-4", "gpt-3.5-turbo", "claude-sonnet-4"
            temperature (float): Sampling temperature (0.0-2.0). Default: 0.2.
            max_tokens (int): Maximum output tokens. Default: 4096.
            timeout (float): Request timeout in seconds. Default: 120.0.
            oauth_endpoint (str | None): OAuth token endpoint. Default: None.
            client_id (str | None): OAuth client ID. Default: None.
            client_secret (str | None): OAuth client secret. Default: None.
            api_key (str | None): API key (alternative to OAuth). Default: None.

        Example:
            >>> # OAuth authentication
            >>> client = LLMGatewayClient(
            ...     server_url="https://llm-gateway/api",
            ...     oauth_endpoint="https://auth/token",
            ...     client_id="app",
            ...     client_secret="secret",
            ...     model_name="gpt-4",
            ... )
            >>>
            >>> # API key authentication
            >>> client = LLMGatewayClient(
            ...     server_url="https://api.openai.com/v1/chat/completions",
            ...     api_key="sk-xxx",
            ...     model_name="gpt-4",
            ... )
        """
        self.server_url = server_url
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.api_key = api_key
        
        # SSL verification - configurable via environment
        # WARNING: Disabling SSL verification is a security risk!
        # Only disable in development/testing with self-signed certs.
        self._verify_ssl = os.getenv("LLM_VERIFY_SSL", "true").lower() != "false"
        if not self._verify_ssl:
            logger.warning(
                "SSL verification disabled (LLM_VERIFY_SSL=false). "
                "This is insecure - only use for development/testing."
            )

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

        # Lock for async client initialization (connection pooling)
        self._async_client_lock = asyncio.Lock()
        self._async_client = None

    @classmethod
    def from_env(cls) -> "LLMGatewayClient":
        """
        Create client from environment variables.

        Loads LLM_* environment variables and creates a configured client.
        This is the recommended way to create the client in production.

        Returns:
            LLMGatewayClient: Client configured from environment.

        Example:
            >>> import os
            >>> os.environ["LLM_SERVER_URL"] = "https://llm-gateway/api"
            >>> os.environ["LLM_API_KEY"] = "sk-xxx"
            >>> os.environ["LLM_MODEL_NAME"] = "gpt-4"
            >>>
            >>> client = LLMGatewayClient.from_env()
            >>> response = await client.generate_async("Hello!")
        """
        config = LLMGatewayConfig.from_env()
        return cls.from_config(config)

    @classmethod
    def from_config(cls, config: LLMGatewayConfig) -> "LLMGatewayClient":
        """
        Create client from configuration object.

        Args:
            config (LLMGatewayConfig): Configuration instance.

        Returns:
            LLMGatewayClient: Client configured from config object.

        Example:
            >>> config = LLMGatewayConfig(
            ...     server_url="https://api/chat",
            ...     api_key="sk-xxx",
            ...     model_name="gpt-4",
            ...     temperature=0.7,
            ... )
            >>> client = LLMGatewayClient.from_config(config)
        """
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
        """
        Get or create async HTTP client (thread-safe).
        
        Connection pooling: Reuses a single httpx.AsyncClient instance
        to avoid creating new connections for each request. This significantly
        improves performance for high-throughput scenarios.
        """
        async with self._async_client_lock:
            if self._async_client is None:
                try:
                    import httpx
                    self._async_client = httpx.AsyncClient(
                        timeout=self.timeout,
                        verify=self._verify_ssl,
                        # Connection pooling settings
                        limits=httpx.Limits(
                            max_keepalive_connections=10,
                            max_connections=20,
                            keepalive_expiry=30.0,
                        ),
                    )
                except ImportError:
                    logger.warning("httpx not installed, using stub client")
            return self._async_client
    
    async def close(self) -> None:
        """
        Close the HTTP client and release resources.
        
        Call this when you're done using the client to properly
        close connection pools and free resources.
        """
        async with self._async_client_lock:
            if self._async_client is not None:
                await self._async_client.aclose()
                self._async_client = None
                logger.debug("LLMGatewayClient HTTP client closed")

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

        # Allow per-call overrides while keeping client defaults
        model = kwargs.pop("model", self.model_name)
        temperature = kwargs.pop("temperature", self.temperature)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        # Add temperature if supported
        if temperature is not None:
            payload["temperature"] = temperature

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

    _tiktoken_warning_logged: bool = False

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count using tiktoken (if available) or fallback to heuristic."""
        try:
            import tiktoken
            # Attempt to get encoding for the specific model
            try:
                encoding = tiktoken.encoding_for_model(self.model_name or "gpt-4")
            except KeyError:
                # Fallback to cl100k_base for newer/unknown models
                encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except ImportError:
            # Log warning once about inaccurate token counting
            if not LLMGatewayClient._tiktoken_warning_logged:
                logger.warning(
                    "tiktoken not installed - using character-based token estimation (~4 chars/token). "
                    "For accurate token counts, install tiktoken: pip install tiktoken"
                )
                LLMGatewayClient._tiktoken_warning_logged = True
            # Fallback to rough heuristic (~4 chars per token)
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
        """
        Generate text from a prompt.

        This is the main method for text generation. It handles:
        - Building the message array with optional system prompt
        - Truncating oversized prompts to prevent API errors
        - Parsing the response into plain text
        - Stub mode for unconfigured clients

        Args:
            prompt (str): The user prompt to send to the LLM.
            system_prompt (str | None): Optional system prompt for context.
                Sets the behavior/persona of the assistant.
            max_input_tokens (int): Max input tokens before truncation. Default: 100000.
                Prompts exceeding this are truncated with a warning.
            **kwargs: Additional parameters for the LLM API.
                Common kwargs: tools, tool_choice, response_format.

        Returns:
            str: Generated text response from the LLM.

        Raises:
            RuntimeError: If HTTP client or auth token unavailable.
            httpx.HTTPStatusError: If API returns error status.

        Example:
            >>> response = await client.generate_async(
            ...     prompt="What is the capital of France?",
            ...     system_prompt="Answer concisely.",
            ... )
            >>> print(response)  # "Paris"
            >>>
            >>> # With additional parameters
            >>> response = await client.generate_async(
            ...     prompt="List 3 colors",
            ...     max_input_tokens=50000,
            ... )

        Note:
            If client is not configured (no auth), returns a stub response
            like "[LLM Response for: What is...]" for testing purposes.
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

    def get_langchain_llm(self) -> Any:
        """
        Get a LangChain-compatible LLM wrapper for this client.

        This method returns a LangChain BaseChatModel that delegates to this
        LLMGatewayClient. Useful for integrating with LangChain chains,
        summarizers, and other LangChain components.

        Returns:
            BaseChatModel: A LangChain-compatible LLM wrapper.

        Raises:
            ImportError: If langchain-core is not installed.

        Example:
            >>> client = LLMGatewayClient.from_env()
            >>> llm = client.get_langchain_llm()
            >>>
            >>> # Use with LangChain
            >>> from langchain_core.prompts import ChatPromptTemplate
            >>> chain = ChatPromptTemplate.from_template("{text}") | llm
            >>> result = await chain.ainvoke({"text": "Hello"})
        """
        try:
            from langchain_core.language_models.chat_models import BaseChatModel
            from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
            from langchain_core.outputs import ChatResult, ChatGeneration
        except ImportError:
            raise ImportError(
                "langchain-core is required for LangChain integration. "
                "Install with: pip install langchain-core"
            )

        client = self

        class LLMGatewayLangChainWrapper(BaseChatModel):
            """LangChain wrapper for LLMGatewayClient."""

            @property
            def _llm_type(self) -> str:
                return "llm-gateway"

            @property
            def _identifying_params(self) -> dict[str, Any]:
                return {
                    "server_url": client.server_url,
                    "model_name": client.model_name,
                }

            def _generate(
                self,
                messages: list[BaseMessage],
                stop: list[str] | None = None,
                **kwargs: Any,
            ) -> ChatResult:
                """
                Sync generation helper.

                If an event loop is already running (common in notebooks or async
                frameworks), we fail fast with a clear error instead of attempting
                to nest event loops. Callers should use async LangChain interfaces
                (e.g., `.ainvoke`) in those environments.
                """
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    raise RuntimeError(
                        "LLMGatewayLangChainWrapper._generate cannot run while an event loop "
                        "is active. Use the async interface instead (e.g., .ainvoke())."
                    )

                if loop:
                    return loop.run_until_complete(self._agenerate(messages, stop, **kwargs))
                return asyncio.run(self._agenerate(messages, stop, **kwargs))

            async def _agenerate(
                self,
                messages: list[BaseMessage],
                stop: list[str] | None = None,
                **kwargs: Any,
            ) -> ChatResult:
                """Async generation using LLMGatewayClient."""
                # Convert LangChain messages to OpenAI format
                formatted_messages = []
                for msg in messages:
                    if isinstance(msg, SystemMessage):
                        formatted_messages.append({"role": "system", "content": msg.content})
                    elif isinstance(msg, HumanMessage):
                        formatted_messages.append({"role": "user", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        formatted_messages.append({"role": "assistant", "content": msg.content})
                    else:
                        formatted_messages.append({"role": "user", "content": str(msg.content)})

                # Call the gateway
                response = await client._call_llm_api(formatted_messages, **kwargs)

                # Parse response
                choice = response.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = message.get("content", "")

                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage(content=content))]
                )

        return LLMGatewayLangChainWrapper()

    async def generate_structured_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_model: type[T] | None = None,
        **kwargs,
    ) -> T | dict:
        """
        Generate structured JSON output from a prompt.

        This method asks the LLM to respond in JSON format and parses
        the response into a Pydantic model or dictionary. Useful for
        extracting structured data from LLM responses.

        Args:
            prompt (str): The user prompt to send to the LLM.
            system_prompt (str | None): Optional system prompt.
                "Respond with valid JSON only." is appended automatically.
            response_model (type[T] | None): Pydantic model class to parse into.
                If None, returns a plain dictionary.
            **kwargs: Additional parameters for the LLM API.

        Returns:
            T | dict: Parsed response as model instance or dictionary.
                On parse failure, returns {"raw_response": text} or empty model.

        Raises:
            RuntimeError: If HTTP client or auth token unavailable.
            httpx.HTTPStatusError: If API returns error status.

        Example:
            >>> from pydantic import BaseModel
            >>>
            >>> class Entity(BaseModel):
            ...     name: str
            ...     type: str
            ...     confidence: float
            >>>
            >>> result = await client.generate_structured_async(
            ...     prompt="Extract the company name: 'Apple announced new products'",
            ...     response_model=Entity,
            ... )
            >>> print(result.name)  # "Apple"
            >>> print(result.type)  # "company"
            >>>
            >>> # Without model (returns dict)
            >>> result = await client.generate_structured_async(
            ...     prompt="Return {name, age} for 'John is 30 years old'",
            ... )
            >>> print(result)  # {"name": "John", "age": 30}

        Note:
            Handles markdown code blocks in responses (```json...```).
            On JSON parse failure, attempts to return empty model instance.
        """
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
                    try:
                        return response_model(**data)
                    except Exception as validation_error:
                        logger.warning(
                            f"Failed to parse response into {response_model.__name__}: {validation_error}"
                        )
                        try:
                            return response_model()
                        except Exception:
                            return {"raw_response": response_text, "parsed": data}
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
    """
    Get the default global LLM client.

    Returns the client set via set_default_llm_client() or init_default_llm_client().
    Returns None if no default has been set.

    Returns:
        LLMGatewayClient | None: The default client, or None.

    Example:
        >>> client = get_default_llm_client()
        >>> if client:
        ...     response = await client.generate_async("Hello")
    """
    return _default_client


def set_default_llm_client(client: LLMGatewayClient):
    """
    Set the default global LLM client.

    Use this to set a pre-configured client as the default for
    the application.

    Args:
        client (LLMGatewayClient): Client instance to set as default.

    Example:
        >>> client = LLMGatewayClient(server_url="...", api_key="...")
        >>> set_default_llm_client(client)
        >>> # Now get_default_llm_client() returns this client
    """
    global _default_client
    _default_client = client


def init_default_llm_client(**kwargs) -> LLMGatewayClient:
    """
    Initialize and set the default LLM client.

    Creates a new LLMGatewayClient with the provided arguments
    and sets it as the global default.

    Args:
        **kwargs: Arguments passed to LLMGatewayClient constructor.

    Returns:
        LLMGatewayClient: The newly created and set default client.

    Example:
        >>> client = init_default_llm_client(
        ...     server_url="https://llm-gateway/api",
        ...     api_key="sk-xxx",
        ...     model_name="gpt-4",
        ... )
        >>> # client is now the global default
    """
    client = LLMGatewayClient(**kwargs)
    set_default_llm_client(client)
    return client


def get_llm_client(**kwargs) -> LLMGatewayClient:
    """
    Get or create an LLM client.

    If kwargs are provided, creates a new client with those settings.
    If no kwargs, returns the default client or creates a stub client.

    Args:
        **kwargs: Optional arguments for LLMGatewayClient constructor.

    Returns:
        LLMGatewayClient: Existing default or new client instance.

    Example:
        >>> # Get default client
        >>> client = get_llm_client()
        >>>
        >>> # Create new client with custom settings
        >>> client = get_llm_client(
        ...     server_url="https://api/chat",
        ...     api_key="key",
        ... )
    """
    if not kwargs:
        return get_default_llm_client() or LLMGatewayClient()
    return LLMGatewayClient(**kwargs)


def create_llm_client_from_env() -> LLMGatewayClient:
    """
    Create an LLM client from environment variables.

    Reads LLM_* environment variables to configure the client.
    This is a convenience function equivalent to LLMGatewayClient.from_env().

    Environment Variables:
        LLM_SERVER_URL: The LLM API endpoint (required)
        LLM_OAUTH_ENDPOINT: OAuth token endpoint
        LLM_CLIENT_ID: OAuth client ID
        LLM_CLIENT_SECRET: OAuth client secret
        LLM_API_KEY: API key (alternative to OAuth)
        LLM_MODEL_NAME: Model to use (default: gpt-4)
        LLM_MAX_TOKENS: Max tokens (default: 4096)
        LLM_TEMPERATURE: Temperature (default: 0.2)

    Returns:
        LLMGatewayClient: Client configured from environment.

    Example:
        >>> client = create_llm_client_from_env()
        >>> response = await client.generate_async("Hello!")
    """
    return LLMGatewayClient(
        server_url=os.getenv("LLM_SERVER_URL"),
        oauth_endpoint=os.getenv("LLM_OAUTH_ENDPOINT"),
        client_id=os.getenv("LLM_CLIENT_ID"),
        client_secret=os.getenv("LLM_CLIENT_SECRET"),
        api_key=os.getenv("LLM_API_KEY"),
        model_name=os.getenv("LLM_MODEL_NAME", "gpt-4"),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        timeout=float(os.getenv("LLM_TIMEOUT", "120.0")),
    )


def create_managed_client(
    token_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    **kwargs,
) -> LLMGatewayClient:
    """
    Create an LLM client with OAuth token management.

    Convenience function for creating OAuth-authenticated clients.

    Args:
        token_url (str | None): OAuth token endpoint URL.
        client_id (str | None): OAuth client ID.
        client_secret (str | None): OAuth client secret.
        **kwargs: Additional LLMGatewayClient arguments.

    Returns:
        LLMGatewayClient: Client with OAuth configuration.

    Example:
        >>> client = create_managed_client(
        ...     token_url="https://auth.corp.com/oauth/token",
        ...     client_id="my-app",
        ...     client_secret="secret",
        ...     server_url="https://llm-gateway/api",
        ...     model_name="gpt-4",
        ... )
    """
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
