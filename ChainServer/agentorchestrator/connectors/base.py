"""
AgentOrchestrator Base Connector
================================

This module provides the base class for external service connectors.

Connectors are responsible for handling low-level communication with external
APIs and services. They manage connection lifecycle, authentication, retries,
and request/response handling.

Classes:
    ConnectorConfig: Configuration dataclass for connector settings.
    BaseConnector: Abstract base class that all connectors must inherit from.

Usage:
    from agentorchestrator.connectors.base import BaseConnector, ConnectorConfig

    class MyAPIConnector(BaseConnector):
        async def connect(self) -> None:
            self._session = aiohttp.ClientSession()

        async def disconnect(self) -> None:
            await self._session.close()

        async def request(self, endpoint: str, method: str = "GET", **kwargs) -> dict:
            async with self._session.request(method, f"{self.config.base_url}/{endpoint}") as resp:
                return await resp.json()

    # Use as context manager
    async with MyAPIConnector(config) as connector:
        data = await connector.request("users/123")

Example:
    >>> config = ConnectorConfig(
    ...     name="my_api",
    ...     base_url="https://api.example.com",
    ...     api_key="secret-key",
    ...     timeout_ms=5000,
    ... )
    >>> connector = MyAPIConnector(config)
    >>> await connector.connect()
    >>> result = await connector.request("data", method="POST", json={"query": "test"})
    >>> await connector.disconnect()

See Also:
    - agentorchestrator.connectors.http: HTTP connector implementation
    - agentorchestrator.agents.base: Agents that use connectors
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectorConfig:
    """
    Configuration for a connector.

    This dataclass holds all configuration needed to establish and manage
    a connection to an external service.

    Attributes:
        name (str): Unique identifier for this connector instance.
            Used in logging and metrics.
        base_url (str): Base URL for the service API.
            Example: "https://api.example.com/v1"
        api_key (str | None): API key for authentication. Default: None.
            Pass None if using other auth methods (OAuth, etc.)
        timeout_ms (int): Request timeout in milliseconds. Default: 30000.
            Individual requests will fail if they exceed this duration.
        retry_count (int): Number of retry attempts on failure. Default: 3.
            Set to 0 to disable retries.
        retry_delay_ms (int): Initial delay between retries in ms. Default: 1000.
            May be increased with exponential backoff.
        headers (dict[str, str]): Additional HTTP headers to include. Default: {}.
            Common use: {"User-Agent": "MyApp/1.0"}
        extra (dict[str, Any]): Additional connector-specific config. Default: {}.
            Use for custom settings not covered by standard fields.

    Example:
        >>> config = ConnectorConfig(
        ...     name="sec_api",
        ...     base_url="https://sec-api.company.com",
        ...     api_key="sk-xxx",
        ...     timeout_ms=10000,
        ...     retry_count=2,
        ...     headers={"X-Custom-Header": "value"},
        ... )
    """

    name: str
    base_url: str
    api_key: str | None = None
    timeout_ms: int = 30000
    retry_count: int = 3
    retry_delay_ms: int = 1000
    headers: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class BaseConnector(ABC):
    """
    Abstract base class for external service connectors.

    Connectors handle the low-level communication with external APIs.
    They should be used by agents for data fetching. All connectors
    must implement connect(), disconnect(), and request() methods.

    Attributes:
        config (ConnectorConfig): Configuration for this connector.
        _session: Internal session object (implementation-specific).

    Methods:
        connect(): Establish connection to the external service.
        disconnect(): Close connection and cleanup resources.
        request(): Make a request to the service.
        health_check(): Check if connector is healthy.

    Example:
        >>> class MyAPIConnector(BaseConnector):
        ...     async def connect(self) -> None:
        ...         import aiohttp
        ...         self._session = aiohttp.ClientSession(
        ...             headers={"Authorization": f"Bearer {self.config.api_key}"}
        ...         )
        ...
        ...     async def disconnect(self) -> None:
        ...         if self._session:
        ...             await self._session.close()
        ...
        ...     async def request(self, endpoint: str, method: str = "GET", **kwargs) -> dict:
        ...         url = f"{self.config.base_url}/{endpoint}"
        ...         async with self._session.request(method, url, **kwargs) as resp:
        ...             return await resp.json()

    Context Manager Usage:
        >>> async with MyAPIConnector(config) as connector:
        ...     data = await connector.request("users")

    See Also:
        ConnectorConfig: Configuration options for connectors.
    """

    def __init__(self, config: ConnectorConfig):
        """
        Initialize the connector with configuration.

        Args:
            config (ConnectorConfig): Configuration containing connection
                details like base_url, api_key, timeouts, etc.

        Example:
            >>> config = ConnectorConfig(name="api", base_url="https://api.example.com")
            >>> connector = MyConnector(config)
        """
        self.config = config
        self._session = None

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection to the external service.

        This method should initialize any connection resources needed,
        such as HTTP sessions, database connections, or websockets.

        Raises:
            ConnectionError: If connection cannot be established.
            AuthenticationError: If credentials are invalid.

        Example:
            >>> await connector.connect()
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection and cleanup resources.

        This method should properly close any open connections and
        release resources. It should be safe to call multiple times.

        Example:
            >>> await connector.disconnect()
        """
        pass

    @abstractmethod
    async def request(self, endpoint: str, method: str = "GET", **kwargs) -> dict[str, Any]:
        """
        Make a request to the external service.

        Args:
            endpoint (str): The API endpoint to call (appended to base_url).
                Example: "users/123" or "data/query"
            method (str): HTTP method. Default: "GET".
                Options: "GET", "POST", "PUT", "DELETE", "PATCH"
            **kwargs: Additional arguments passed to the underlying client.
                Common kwargs:
                - json (dict): JSON body for POST/PUT requests
                - params (dict): Query parameters
                - headers (dict): Additional headers for this request
                - timeout (float): Override default timeout

        Returns:
            dict[str, Any]: Parsed JSON response from the service.

        Raises:
            RequestError: If request fails after retries.
            TimeoutError: If request exceeds timeout.
            ValueError: If response is not valid JSON.

        Example:
            >>> # GET request
            >>> users = await connector.request("users", params={"limit": 10})
            >>>
            >>> # POST request with JSON body
            >>> result = await connector.request(
            ...     "data/query",
            ...     method="POST",
            ...     json={"query": "SELECT * FROM items"}
            ... )
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if the connector is healthy and ready to make requests.

        Override this method for custom health checks (e.g., ping endpoint).

        Returns:
            bool: True if connector is healthy, False otherwise.

        Example:
            >>> if await connector.health_check():
            ...     data = await connector.request("data")
            ... else:
            ...     logger.warning("Connector unhealthy, skipping request")
        """
        return self._session is not None

    async def __aenter__(self):
        """
        Async context manager entry - establishes connection.

        Returns:
            BaseConnector: This connector instance.

        Example:
            >>> async with MyConnector(config) as conn:
            ...     data = await conn.request("endpoint")
        """
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit - closes connection.

        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception value if an error occurred.
            exc_tb: Exception traceback if an error occurred.
        """
        await self.disconnect()
