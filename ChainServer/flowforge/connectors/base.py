"""
FlowForge Base Connector

Provides base classes for external service connectors.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConnectorConfig:
    """Configuration for a connector"""

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
    Base class for external service connectors.

    Connectors handle the low-level communication with external APIs.
    They should be used by agents for data fetching.

    Usage:
        class MyAPIConnector(BaseConnector):
            async def request(self, endpoint: str, **kwargs) -> Dict:
                ...
    """

    def __init__(self, config: ConnectorConfig):
        self.config = config
        self._session = None

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the service"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the service"""
        pass

    @abstractmethod
    async def request(self, endpoint: str, method: str = "GET", **kwargs) -> dict[str, Any]:
        """Make a request to the service"""
        pass

    async def health_check(self) -> bool:
        """Check if the connector is healthy"""
        return self._session is not None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


class HTTPConnector(BaseConnector):
    """
    HTTP-based connector using aiohttp.

    Usage:
        config = ConnectorConfig(
            name="ravenpack",
            base_url="https://api.ravenpack.com",
            api_key="...",
        )
        connector = HTTPConnector(config)
        async with connector:
            data = await connector.request("/v1/news", params={"q": "Apple"})
    """

    async def connect(self) -> None:
        try:
            import aiohttp

            self._session = aiohttp.ClientSession(
                base_url=self.config.base_url,
                headers={
                    **self.config.headers,
                    "Authorization": f"Bearer {self.config.api_key}" if self.config.api_key else "",
                },
            )
            logger.info(f"Connected to {self.config.name}")
        except ImportError:
            logger.warning("aiohttp not installed, using mock session")
            self._session = MockSession()

    async def disconnect(self) -> None:
        if self._session and hasattr(self._session, "close"):
            await self._session.close()
        self._session = None
        logger.info(f"Disconnected from {self.config.name}")

    async def request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict | None = None,
        data: dict | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        if not self._session:
            raise RuntimeError("Connector not connected")

        try:
            timeout_seconds = self.config.timeout_ms / 1000

            async with self._session.request(
                method,
                endpoint,
                params=params,
                json=data,
                timeout=timeout_seconds,
                **kwargs,
            ) as response:
                response.raise_for_status()
                return await response.json()

        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise


class MockSession:
    """Mock session for testing without aiohttp"""

    async def close(self):
        pass

    def request(self, *args, **kwargs):
        return MockResponse()


class MockResponse:
    """Mock response for testing"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    async def json(self):
        return {"_mock": True}
