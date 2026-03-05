"""
HTTP Adapter Agent

A hardened HTTP client agent for making external API calls with:
- Authentication (API key, Bearer, Basic, OAuth)
- Retry with exponential backoff
- Circuit breaker
- Rate limiting
- Request/response logging
- Timeout handling

Usage:
    from agentorchestrator.plugins import HTTPAdapterAgent, HTTPAdapterConfig

    # Create adapter
    config = HTTPAdapterConfig(
        base_url="https://api.example.com",
        auth_type="bearer",
        auth_token="my-token",
        timeout_seconds=30.0,
        max_retries=3,
    )
    agent = HTTPAdapterAgent(config)

    # Make request
    result = await agent.fetch("/search", params={"q": "test"})

    # Or use factory
    agent = create_http_agent(
        name="my_api",
        base_url="https://api.example.com",
        auth_token="my-token",
    )
"""

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from agentorchestrator.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class HTTPAdapterConfig:
    """
    Configuration for HTTP adapter agent.

    Attributes:
        base_url: Base URL for API requests
        auth_type: Authentication type
        auth_token: Token for bearer/api_key auth
        auth_username: Username for basic auth
        auth_password: Password for basic auth
        api_key_header: Header name for API key
        timeout_seconds: Request timeout
        max_retries: Maximum retry attempts
        retry_delay_ms: Initial retry delay
        retry_backoff: Retry backoff multiplier
        retry_status_codes: Status codes to retry on
        circuit_breaker_enabled: Enable circuit breaker
        circuit_failure_threshold: Failures before opening circuit
        circuit_recovery_seconds: Recovery timeout
        rate_limit_enabled: Enable rate limiting
        rate_limit_rps: Requests per second
        rate_limit_burst: Burst size
        headers: Default headers
        verify_ssl: Verify SSL certificates
        log_requests: Log request/response details
    """

    base_url: str
    auth_type: Literal["none", "bearer", "api_key", "basic", "oauth"] = "none"
    auth_token: str | None = None
    auth_username: str | None = None
    auth_password: str | None = None
    api_key_header: str = "X-API-Key"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay_ms: int = 1000
    retry_backoff: float = 2.0
    retry_status_codes: list[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    circuit_breaker_enabled: bool = True
    circuit_failure_threshold: int = 5
    circuit_recovery_seconds: float = 30.0
    rate_limit_enabled: bool = False
    rate_limit_rps: float = 10.0
    rate_limit_burst: int = 20
    headers: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
    log_requests: bool = False


class HTTPAdapterAgent(BaseAgent):
    """
    Hardened HTTP client agent for external API calls.

    Features:
    - Multiple auth methods (bearer, API key, basic)
    - Retry with exponential backoff
    - Circuit breaker for failure protection
    - Rate limiting
    - Comprehensive logging
    """

    _ao_name = "http_adapter"
    _ao_version = "1.0.0"

    # Capability schema
    CAPABILITIES = {
        "get": {
            "description": "HTTP GET request",
            "parameters": {
                "endpoint": {"type": "string", "required": True},
                "params": {"type": "object", "default": {}},
            },
        },
        "post": {
            "description": "HTTP POST request",
            "parameters": {
                "endpoint": {"type": "string", "required": True},
                "data": {"type": "object", "default": {}},
                "json": {"type": "object", "default": None},
            },
        },
        "fetch": {
            "description": "Generic HTTP request",
            "parameters": {
                "endpoint": {"type": "string", "required": True},
                "method": {"type": "string", "default": "GET"},
                "params": {"type": "object", "default": {}},
                "data": {"type": "object", "default": None},
                "json": {"type": "object", "default": None},
            },
        },
    }

    def __init__(self, config: HTTPAdapterConfig | dict[str, Any] | None = None):
        super().__init__()

        if isinstance(config, dict):
            self._config = HTTPAdapterConfig(**config)
        elif config:
            self._config = config
        else:
            self._config = HTTPAdapterConfig(base_url="")

        self._client = None
        self._circuit = None
        self._rate_limiter = None
        self._last_request_time = 0.0
        self._request_count = 0

    async def initialize(self) -> None:
        """Initialize HTTP client and circuit breaker."""
        import httpx

        # Create async HTTP client
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=httpx.Timeout(self._config.timeout_seconds),
            verify=self._config.verify_ssl,
            headers=self._build_default_headers(),
        )

        # Create circuit breaker if enabled
        if self._config.circuit_breaker_enabled:
            from agentorchestrator.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

            self._circuit = CircuitBreaker(
                name=f"http_{self._ao_name}",
                config=CircuitBreakerConfig(
                    failure_threshold=self._config.circuit_failure_threshold,
                    recovery_timeout=self._config.circuit_recovery_seconds,
                ),
            )

        await super().initialize()
        logger.info(f"HTTPAdapterAgent initialized: {self._config.base_url}")

    async def cleanup(self) -> None:
        """Cleanup HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        await super().cleanup()

    def _build_default_headers(self) -> dict[str, str]:
        """Build default headers including auth."""
        headers = {
            "User-Agent": "AgentOrchestrator-HTTPAdapter/1.0",
            **self._config.headers,
        }

        # Add auth header
        if self._config.auth_type == "bearer" and self._config.auth_token:
            headers["Authorization"] = f"Bearer {self._config.auth_token}"
        elif self._config.auth_type == "api_key" and self._config.auth_token:
            headers[self._config.api_key_header] = self._config.auth_token
        elif self._config.auth_type == "basic":
            if self._config.auth_username and self._config.auth_password:
                credentials = f"{self._config.auth_username}:{self._config.auth_password}"
                encoded = base64.b64encode(credentials.encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"

        return headers

    async def _wait_for_rate_limit(self) -> None:
        """Wait if rate limit would be exceeded."""
        if not self._config.rate_limit_enabled:
            return

        now = time.time()
        elapsed = now - self._last_request_time

        # Simple token bucket rate limiting
        if elapsed < 1.0 / self._config.rate_limit_rps:
            wait_time = (1.0 / self._config.rate_limit_rps) - elapsed
            await asyncio.sleep(wait_time)

        self._last_request_time = time.time()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make HTTP request with retry and circuit breaker.

        Returns:
            Dict with response data and metadata
        """
        import httpx

        if self._client is None:
            await self.initialize()

        # Rate limiting
        await self._wait_for_rate_limit()

        last_error: Exception | None = None
        attempt = 0
        delay_ms = self._config.retry_delay_ms

        while attempt < self._config.max_retries:
            attempt += 1

            try:
                # Check circuit breaker
                if self._circuit and self._circuit.is_open:
                    raise Exception("Circuit breaker is open")

                # Log request
                if self._config.log_requests:
                    logger.info(
                        f"HTTP {method} {endpoint}",
                        extra={"params": params, "attempt": attempt},
                    )

                # Make request
                start_time = time.perf_counter()

                async with self._circuit if self._circuit else _noop_context():
                    response = await self._client.request(
                        method=method,
                        url=endpoint,
                        params=params,
                        data=data,
                        json=json_data,
                        headers=headers,
                    )

                duration_ms = (time.perf_counter() - start_time) * 1000

                # Log response
                if self._config.log_requests:
                    logger.info(
                        f"HTTP {response.status_code} in {duration_ms:.1f}ms",
                        extra={"status": response.status_code},
                    )

                # Check for retryable status codes
                if response.status_code in self._config.retry_status_codes:
                    if attempt < self._config.max_retries:
                        logger.warning(
                            f"Retrying {method} {endpoint} after {response.status_code}"
                        )
                        await asyncio.sleep(delay_ms / 1000)
                        delay_ms = int(delay_ms * self._config.retry_backoff)
                        continue

                # Parse response
                try:
                    response_data = response.json()
                except (json.JSONDecodeError, ValueError):
                    response_data = {"text": response.text}

                return {
                    "status_code": response.status_code,
                    "data": response_data,
                    "headers": dict(response.headers),
                    "duration_ms": duration_ms,
                    "attempts": attempt,
                    "success": 200 <= response.status_code < 300,
                }

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Request timeout on attempt {attempt}: {endpoint}")
            except httpx.ConnectError as e:
                last_error = e
                logger.warning(f"Connection error on attempt {attempt}: {e}")
            except Exception as e:
                last_error = e
                logger.warning(f"Request failed on attempt {attempt}: {e}")

            # Retry delay
            if attempt < self._config.max_retries:
                await asyncio.sleep(delay_ms / 1000)
                delay_ms = int(delay_ms * self._config.retry_backoff)

        # All retries exhausted
        return {
            "status_code": 0,
            "data": None,
            "error": str(last_error),
            "attempts": attempt,
            "success": False,
        }

    async def fetch(
        self,
        query: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> AgentResult:
        """
        Make HTTP request (implements BaseAgent.fetch).

        Args:
            query: Endpoint path (e.g., "/search")
            method: HTTP method
            params: Query parameters
            data: Form data
            json_data: JSON body
            headers: Additional headers

        Returns:
            AgentResult with response data
        """
        start = time.perf_counter()

        try:
            result = await self._make_request(
                method=method,
                endpoint=query,
                params=params,
                data=data,
                json_data=json_data,
                headers=headers,
            )

            duration = (time.perf_counter() - start) * 1000

            return AgentResult(
                data=result.get("data"),
                source=self._ao_name,
                query=query,
                duration_ms=duration,
                error=result.get("error") if not result.get("success") else None,
                metadata={
                    "method": method,
                    "status_code": result.get("status_code"),
                    "attempts": result.get("attempts"),
                    "base_url": self._config.base_url,
                },
            )

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=query,
                duration_ms=duration,
                error=str(e),
            )

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> AgentResult:
        """HTTP GET request."""
        return await self.fetch(endpoint, method="GET", params=params, **kwargs)

    async def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        **kwargs,
    ) -> AgentResult:
        """HTTP POST request."""
        return await self.fetch(
            endpoint, method="POST", data=data, json_data=json_data, **kwargs
        )

    async def health_check(self) -> bool:
        """Check if HTTP client is healthy."""
        if self._client is None:
            return False
        if self._circuit and self._circuit.is_open:
            return False
        return True

    @property
    def circuit_is_open(self) -> bool:
        """Check if circuit breaker is open."""
        return self._circuit.is_open if self._circuit else False


class _noop_context:
    """No-op context manager."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def create_http_agent(
    name: str,
    base_url: str,
    auth_token: str | None = None,
    auth_type: str = "bearer",
    **kwargs,
) -> HTTPAdapterAgent:
    """
    Factory function to create HTTP adapter agent.

    Args:
        name: Agent name
        base_url: API base URL
        auth_token: Authentication token
        auth_type: Authentication type
        **kwargs: Additional config options

    Returns:
        Configured HTTPAdapterAgent
    """
    config = HTTPAdapterConfig(
        base_url=base_url,
        auth_type=auth_type,
        auth_token=auth_token,
        **kwargs,
    )

    agent = HTTPAdapterAgent(config)
    agent._ao_name = name

    return agent