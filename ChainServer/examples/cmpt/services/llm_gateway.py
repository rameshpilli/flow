"""
FlowForge LLM Gateway Client

OAuth-authenticated LLM gateway client for enterprise environments.
Supports both sync and async operations with:
- Connection pooling (shared httpx clients)
- Retry with exponential backoff
- Circuit breaker for resilience
- Optional streaming responses
"""

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

import httpx

from flowforge.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
)

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
#                           RETRY DECORATOR
# ═══════════════════════════════════════════════════════════════════════════════


def with_retry(
    max_attempts: int = 3,
    delay_ms: int = 1000,
    backoff_multiplier: float = 2.0,
    retryable_exceptions: tuple = (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException),
):
    """
    Decorator for adding retry logic with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delay_ms: Initial delay between retries in milliseconds
        backoff_multiplier: Multiplier for exponential backoff
        retryable_exceptions: Tuple of exception types to retry
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None
                delay = delay_ms

                for attempt in range(1, max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except retryable_exceptions as e:
                        last_exception = e
                        if attempt < max_attempts:
                            logger.warning(
                                f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                                f"Retrying in {delay}ms..."
                            )
                            await asyncio.sleep(delay / 1000)
                            delay = int(delay * backoff_multiplier)
                        else:
                            logger.error(f"{func.__name__} failed after {max_attempts} attempts")

                raise last_exception
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                import time
                last_exception = None
                delay = delay_ms

                for attempt in range(1, max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except retryable_exceptions as e:
                        last_exception = e
                        if attempt < max_attempts:
                            logger.warning(
                                f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                                f"Retrying in {delay}ms..."
                            )
                            time.sleep(delay / 1000)
                            delay = int(delay * backoff_multiplier)
                        else:
                            logger.error(f"{func.__name__} failed after {max_attempts} attempts")

                raise last_exception
            return sync_wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
#                           OAUTH TOKEN MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class OAuthTokenManager:
    """
    Manages OAuth token retrieval and caching.

    Thread-safe: Uses locks to prevent concurrent token fetches and race conditions.
    Caches tokens with TTL slightly less than actual expiry to prevent
    edge-case failures.
    """

    # Minimum buffer time before expiry (seconds) - never go below this
    MIN_EXPIRY_BUFFER = 10

    def __init__(
        self,
        oauth_endpoint: str,
        client_id: str,
        client_secret: str,
        grant_type: str = "client_credentials",
        scope: str = "read",
        token_ttl_seconds: int = 3500,  # ~1 hour, slightly less than typical 3600
        http_client: httpx.Client | None = None,
        async_http_client: httpx.AsyncClient | None = None,
    ):
        self.oauth_endpoint = oauth_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.grant_type = grant_type
        self.scope = scope
        self.token_ttl_seconds = token_ttl_seconds

        self._token: str | None = None
        self._token_expiry: datetime | None = None

        # Thread safety locks
        self._sync_lock = threading.Lock()
        self._async_lock: asyncio.Lock | None = None

        # Shared HTTP clients for connection pooling
        self._http_client = http_client
        self._async_http_client = async_http_client

    def _get_async_lock(self) -> asyncio.Lock:
        """Lazy initialization of async lock (must be created in async context)."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def _calculate_expiry(self, expires_in: int) -> datetime:
        """Calculate token expiry time safely."""
        buffer = 60 if expires_in > 60 else max(0, expires_in - self.MIN_EXPIRY_BUFFER)
        effective_ttl = min(expires_in - buffer, self.token_ttl_seconds)
        effective_ttl = max(effective_ttl, self.MIN_EXPIRY_BUFFER)
        return datetime.now() + timedelta(seconds=effective_ttl)

    def _is_token_valid(self) -> bool:
        """Check if current token is valid and not expired."""
        return bool(
            self._token
            and self._token_expiry
            and datetime.now() < self._token_expiry
        )

    @property
    def token(self) -> str:
        """Get a valid OAuth token, refreshing if needed (thread-safe)."""
        if self._is_token_valid():
            return self._token  # type: ignore

        with self._sync_lock:
            if self._is_token_valid():
                return self._token  # type: ignore
            return self._fetch_token()

    @with_retry(max_attempts=3, delay_ms=1000, backoff_multiplier=2.0)
    def _fetch_token(self) -> str:
        """Fetch a new OAuth token synchronously with retry."""
        if not all([self.client_id, self.client_secret, self.oauth_endpoint]):
            raise ValueError("OAuth credentials not configured (client_id, client_secret, oauth_endpoint)")

        # Use shared client or create temporary one
        client = self._http_client or httpx.Client(timeout=30.0)
        should_close = self._http_client is None

        try:
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

            expires_in = token_data.get("expires_in", self.token_ttl_seconds)
            self._token_expiry = self._calculate_expiry(expires_in)

            logger.info(f"OAuth token obtained, expires at {self._token_expiry}")
            return self._token

        finally:
            if should_close:
                client.close()

    async def get_token_async(self) -> str:
        """Get a valid OAuth token asynchronously (async-safe)."""
        if self._is_token_valid():
            return self._token  # type: ignore

        async with self._get_async_lock():
            if self._is_token_valid():
                return self._token  # type: ignore
            return await self._fetch_token_async()

    @with_retry(max_attempts=3, delay_ms=1000, backoff_multiplier=2.0)
    async def _fetch_token_async(self) -> str:
        """Fetch a new OAuth token asynchronously with retry."""
        if not all([self.client_id, self.client_secret, self.oauth_endpoint]):
            raise ValueError("OAuth credentials not configured")

        # Use shared client or create temporary one
        client = self._async_http_client
        should_close = client is None

        if client is None:
            client = httpx.AsyncClient(timeout=30.0)

        try:
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
            self._token_expiry = self._calculate_expiry(expires_in)

            logger.info(f"OAuth token obtained (async), expires at {self._token_expiry}")
            return self._token

        finally:
            if should_close:
                await client.aclose()

    def invalidate(self) -> None:
        """Manually invalidate the cached token (thread-safe)."""
        with self._sync_lock:
            self._token = None
            self._token_expiry = None
            logger.info("OAuth token invalidated")


# ═══════════════════════════════════════════════════════════════════════════════
#                           LLM GATEWAY CLIENT
# ═══════════════════════════════════════════════════════════════════════════════


class LLMGatewayClient:
    """
    Enterprise LLM Gateway client with OAuth authentication.

    Features:
    - Connection pooling via shared httpx clients
    - Retry with exponential backoff
    - Circuit breaker for resilience
    - Streaming responses support
    - Both sync and async methods
    - Context manager support (sync and async)

    Usage:
        # As context manager (recommended - ensures cleanup)
        async with LLMGatewayClient(server_url="...", model_name="gpt-4") as client:
            response = await client.generate_async("Tell me about Apple")

        # Sync context manager
        with LLMGatewayClient(server_url="...", model_name="gpt-4") as client:
            response = client.generate("Tell me about Apple")

        # Manual management (remember to call close())
        client = LLMGatewayClient(...)
        try:
            response = await client.generate_async("...")
        finally:
            await client.close()

        # With streaming
        async for chunk in client.stream_async("Tell me about Apple"):
            print(chunk, end="", flush=True)
    """

    def __init__(
        self,
        server_url: str,
        model_name: str,
        oauth_endpoint: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout: float = 60.0,
        # Retry configuration
        max_retries: int = 3,
        retry_delay_ms: int = 1000,
        # Circuit breaker configuration
        circuit_breaker_enabled: bool = True,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_recovery_timeout: float = 30.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms

        # Authentication
        self._api_key = api_key
        self._token_manager: OAuthTokenManager | None = None

        # Connection pooling - shared clients
        self._sync_client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None
        self._client_lock = threading.Lock()
        self._async_client_lock: asyncio.Lock | None = None  # Lazy init for async context

        if oauth_endpoint and client_id and client_secret:
            self._token_manager = OAuthTokenManager(
                oauth_endpoint=oauth_endpoint,
                client_id=client_id,
                client_secret=client_secret,
            )

        # Circuit breaker for resilience
        self._circuit_breaker: CircuitBreaker | None = None
        if circuit_breaker_enabled:
            self._circuit_breaker = CircuitBreaker(
                name=f"llm_gateway_{model_name}",
                config=CircuitBreakerConfig(
                    failure_threshold=circuit_breaker_threshold,
                    recovery_timeout=circuit_breaker_recovery_timeout,
                ),
            )

        # For LangChain integration
        self._langchain_llm: Any | None = None

    def _get_sync_client(self) -> httpx.Client:
        """Get or create shared sync HTTP client"""
        if self._sync_client is None:
            with self._client_lock:
                if self._sync_client is None:
                    self._sync_client = httpx.Client(
                        timeout=self.timeout,
                        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                    )
        return self._sync_client

    def _get_async_client_lock(self) -> asyncio.Lock:
        """Lazy initialization of async client lock (must be created in async context)."""
        if self._async_client_lock is None:
            self._async_client_lock = asyncio.Lock()
        return self._async_client_lock

    async def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create shared async HTTP client (thread-safe)."""
        if self._async_client is None:
            async with self._get_async_client_lock():
                # Double-check after acquiring lock
                if self._async_client is None:
                    self._async_client = httpx.AsyncClient(
                        timeout=self.timeout,
                        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                    )
        return self._async_client

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
        """Generate a response synchronously."""
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
        """Chat completion synchronously with retry and circuit breaker."""
        import time

        last_exception = None
        delay = self.retry_delay_ms

        for attempt in range(1, self.max_retries + 1):
            try:
                return self._chat_impl(messages, temperature, max_tokens)
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(
                        f"chat attempt {attempt}/{self.max_retries} failed: {e}. "
                        f"Retrying in {delay}ms..."
                    )
                    time.sleep(delay / 1000)
                    delay = int(delay * 2.0)  # Exponential backoff
                else:
                    logger.error(f"chat failed after {self.max_retries} attempts")

        raise last_exception  # type: ignore

    def _chat_impl(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Internal chat implementation (single attempt)."""
        # Check circuit breaker
        if self._circuit_breaker and self._circuit_breaker.is_open:
            raise CircuitBreakerError(
                f"Circuit breaker is open for {self.model_name}",
                self._circuit_breaker.name,
            )

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }

        try:
            client = self._get_sync_client()
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
            result = data["choices"][0]["message"]["content"]

            # Record success for circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker._record_success()

            return result

        except Exception as e:
            # Record failure for circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker._record_failure()
            logger.error(f"LLM request failed: {e}")
            raise

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
        """Generate a response asynchronously."""
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
        """Chat completion asynchronously with retry and circuit breaker."""
        last_exception = None
        delay = self.retry_delay_ms

        for attempt in range(1, self.max_retries + 1):
            try:
                return await self._chat_async_impl(messages, temperature, max_tokens)
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(
                        f"chat_async attempt {attempt}/{self.max_retries} failed: {e}. "
                        f"Retrying in {delay}ms..."
                    )
                    await asyncio.sleep(delay / 1000)
                    delay = int(delay * 2.0)  # Exponential backoff
                else:
                    logger.error(f"chat_async failed after {self.max_retries} attempts")

        raise last_exception  # type: ignore

    async def _chat_async_impl(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Internal async chat implementation (single attempt)."""
        # Check circuit breaker
        if self._circuit_breaker and self._circuit_breaker.is_open:
            raise CircuitBreakerError(
                f"Circuit breaker is open for {self.model_name}",
                self._circuit_breaker.name,
            )

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }

        try:
            client = await self._get_async_client()
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
            result = data["choices"][0]["message"]["content"]

            # Record success for circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker._record_success()

            return result

        except Exception as e:
            # Record failure for circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker._record_failure()
            logger.error(f"LLM request failed: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════════════════
    #                           STREAMING METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    async def stream_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a response asynchronously.

        Usage:
            async for chunk in client.stream_async("Tell me about Apple"):
                print(chunk, end="", flush=True)
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async for chunk in self.stream_chat_async(messages, temperature, max_tokens):
            yield chunk

    async def stream_chat_async(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat completion asynchronously."""
        # Check circuit breaker
        if self._circuit_breaker and self._circuit_breaker.is_open:
            raise CircuitBreakerError(
                f"Circuit breaker is open for {self.model_name}",
                self._circuit_breaker.name,
            )

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "stream": True,
        }

        try:
            client = await self._get_async_client()
            auth_header = await self._get_auth_header_async()

            async with client.stream(
                "POST",
                f"{self.server_url}/chat/completions",
                json=payload,
                headers={
                    **auth_header,
                    "Content-Type": "application/json",
                },
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break

                        import json
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

            # Record success for circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker._record_success()

        except Exception as e:
            # Record failure for circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker._record_failure()
            logger.error(f"LLM streaming request failed: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════════════════
    #                       LANGCHAIN INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════════

    def get_langchain_llm(self) -> Any:
        """Get a LangChain-compatible LLM instance."""
        if self._langchain_llm is not None:
            return self._langchain_llm

        try:
            from langchain_openai import ChatOpenAI

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

    # ═══════════════════════════════════════════════════════════════════════════
    #                           HEALTH & CLEANUP
    # ═══════════════════════════════════════════════════════════════════════════

    def health_check(self) -> dict[str, Any]:
        """Check client health status."""
        return {
            "server_url": self.server_url,
            "model": self.model_name,
            "circuit_breaker": {
                "enabled": self._circuit_breaker is not None,
                "state": self._circuit_breaker.state.value if self._circuit_breaker else None,
                "failures": self._circuit_breaker.stats.failures if self._circuit_breaker else 0,
            },
            "auth_configured": bool(self._token_manager or self._api_key),
        }

    async def close(self) -> None:
        """Close HTTP clients and cleanup resources (async version)."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

        logger.info("LLM Gateway client closed")

    def close_sync(self) -> None:
        """Close HTTP clients synchronously (for sync context manager)."""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

        # For async client, we can't await in sync context, but we can close transport
        if self._async_client:
            try:
                # Try to close without awaiting - works for cleanup
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in an async context, schedule the close
                    loop.create_task(self._async_client.aclose())
                except RuntimeError:
                    # No running loop - try to run in new loop
                    try:
                        asyncio.run(self._async_client.aclose())
                    except Exception:
                        pass
            except Exception:
                pass
            self._async_client = None

        logger.info("LLM Gateway client closed (sync)")

    # ═══════════════════════════════════════════════════════════════════════════
    #                       CONTEXT MANAGERS
    # ═══════════════════════════════════════════════════════════════════════════

    async def __aenter__(self) -> "LLMGatewayClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - ensures cleanup."""
        await self.close()

    def __enter__(self) -> "LLMGatewayClient":
        """Sync context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Sync context manager exit - ensures cleanup."""
        self.close_sync()

    def __del__(self):
        """Cleanup on deletion - best effort."""
        try:
            if self._sync_client:
                self._sync_client.close()
        except Exception:
            pass
        # Note: Can't reliably close async client in __del__
        # Users should use context managers or call close() explicitly


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


# ═══════════════════════════════════════════════════════════════════════════════
#                           CLIENT REGISTRY & CLEANUP
# ═══════════════════════════════════════════════════════════════════════════════

# Track all created clients for cleanup
_tracked_clients: list[LLMGatewayClient] = []
_default_client: LLMGatewayClient | None = None
_atexit_registered = False


def _register_client(client: LLMGatewayClient) -> None:
    """Register a client for atexit cleanup."""
    global _atexit_registered
    _tracked_clients.append(client)

    if not _atexit_registered:
        import atexit
        atexit.register(_cleanup_all_clients)
        _atexit_registered = True


def _cleanup_all_clients() -> None:
    """Cleanup all tracked clients on process exit."""
    global _tracked_clients, _default_client

    for client in _tracked_clients:
        try:
            client.close_sync()
        except Exception as e:
            logger.debug(f"Error closing client during cleanup: {e}")

    _tracked_clients.clear()
    _default_client = None
    logger.info("All LLM clients cleaned up")


def get_default_llm_client() -> LLMGatewayClient | None:
    """Get the default LLM client instance (singleton)."""
    global _default_client
    return _default_client


def set_default_llm_client(client: LLMGatewayClient) -> None:
    """Set the default LLM client instance."""
    global _default_client
    _default_client = client
    _register_client(client)
    logger.info(f"Default LLM client set: {client.model_name} @ {client.server_url}")


def init_default_llm_client(**kwargs) -> LLMGatewayClient:
    """Initialize and set the default LLM client from environment or kwargs."""
    client = get_llm_client(**kwargs)
    set_default_llm_client(client)
    return client


def create_managed_client(**kwargs) -> LLMGatewayClient:
    """
    Create a client that will be automatically cleaned up on process exit.

    Use this when you want automatic cleanup but don't want to use context managers.

    Usage:
        client = create_managed_client(server_url="...", model_name="gpt-4")
        # Client will be cleaned up when process exits
    """
    client = get_llm_client(**kwargs)
    _register_client(client)
    return client
