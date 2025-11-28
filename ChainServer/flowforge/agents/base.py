"""
FlowForge Base Agent

Provides the base class for data agents.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class AgentResult(Generic[T]):
    """Result from an agent operation"""

    data: T
    source: str
    query: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0

    @property
    def success(self) -> bool:
        return self.error is None


class BaseAgent(ABC):
    """
    Base class for FlowForge data agents.

    Agents are responsible for fetching data from external sources.
    They should be stateless and idempotent.

    Usage:
        @forge.agent(name="news_agent")
        class NewsAgent(BaseAgent):
            async def fetch(self, query: str, **kwargs) -> AgentResult:
                # Fetch news data
                ...
    """

    _flowforge_agent = True
    _flowforge_name: str = ""
    _flowforge_version: str = "1.0.0"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the agent (e.g., establish connections).
        Override this for setup logic.
        """
        self._initialized = True

    async def cleanup(self) -> None:
        """
        Cleanup agent resources.
        Override this for teardown logic.
        """
        self._initialized = False

    @abstractmethod
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch data based on a query.

        Args:
            query: The search/fetch query
            **kwargs: Additional parameters

        Returns:
            AgentResult with fetched data
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if the agent is healthy and can fetch data.
        Override for custom health checks.
        """
        return self._initialized

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self._flowforge_name})"


class CompositeAgent(BaseAgent):
    """
    Agent that combines multiple agents.

    Useful for aggregating data from multiple sources.

    Usage:
        composite = CompositeAgent([
            NewsAgent(),
            SECFilingAgent(),
        ])
        result = await composite.fetch("Apple Inc")
    """

    def __init__(self, agents: list[BaseAgent], config: dict[str, Any] | None = None):
        super().__init__(config)
        self.agents = agents

    async def initialize(self) -> None:
        for agent in self.agents:
            await agent.initialize()
        await super().initialize()

    async def cleanup(self) -> None:
        for agent in self.agents:
            await agent.cleanup()
        await super().cleanup()

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch from all agents and combine results"""
        import asyncio
        import time

        start = time.perf_counter()

        tasks = [agent.fetch(query, **kwargs) for agent in self.agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined_data = {}
        errors = []

        for agent, result in zip(self.agents, results):
            agent_name = getattr(agent, "_flowforge_name", agent.__class__.__name__)
            if isinstance(result, Exception):
                errors.append(f"{agent_name}: {result}")
            elif result.success:
                combined_data[agent_name] = result.data
            else:
                errors.append(f"{agent_name}: {result.error}")

        duration = (time.perf_counter() - start) * 1000

        return AgentResult(
            data=combined_data,
            source="composite",
            query=query,
            duration_ms=duration,
            error="; ".join(errors) if errors else None,
            metadata={"agent_count": len(self.agents)},
        )

    async def health_check(self) -> bool:
        checks = [await agent.health_check() for agent in self.agents]
        return all(checks)
