"""AgentOrchestrator Base Connector."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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
