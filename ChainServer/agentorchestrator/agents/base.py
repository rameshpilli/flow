"""
AgentOrchestrator Base Agent

Provides the base class for data agents.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

__all__ = [
    "BaseAgent",
    "AgentResult",
    "CompositeAgent",
    "ResilientAgent",
    "ResilienceConfig",
]

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
    Base class for AgentOrchestrator data agents.

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


@dataclass
class ResilientAgentConfig:
    """Configuration for resilient agent wrapper."""

    timeout_seconds: float = 30.0  # Per-call timeout
    max_retries: int = 3           # Max retry attempts
    retry_delay_ms: int = 1000     # Initial retry delay
    retry_backoff: float = 2.0     # Backoff multiplier
    circuit_failure_threshold: int = 5   # Failures before opening circuit
    circuit_recovery_seconds: float = 30.0  # Seconds before half-open


class ResilientAgent(BaseAgent):
    """
    Wrapper that adds timeout, retry, and circuit-breaker to any agent.

    Provides external-call resilience with:
    - Per-call timeout (prevents hanging)
    - Retry with exponential backoff (handles transient failures)
    - Circuit breaker (prevents cascading failures)
    - Partial success tracking (surface per-agent errors)

    Usage:
        from agentorchestrator.agents import ResilientAgent, ResilientAgentConfig

        # Wrap an existing agent
        news_agent = NewsAgent()
        resilient_news = ResilientAgent(
            agent=news_agent,
            config=ResilientAgentConfig(
                timeout_seconds=10.0,
                max_retries=3,
            ),
        )

        # Use as normal
        result = await resilient_news.fetch("Apple Inc")

        # Check if circuit is open
        if resilient_news.circuit_is_open:
            logger.warning("News agent circuit is open!")

        # Get circuit stats
        stats = resilient_news.circuit_stats
    """

    def __init__(
        self,
        agent: BaseAgent,
        config: ResilientAgentConfig | None = None,
        name: str | None = None,
    ):
        super().__init__()
        self._wrapped_agent = agent
        self._config = config or ResilientAgentConfig()
        self._flowforge_name = name or f"resilient_{getattr(agent, '_flowforge_name', agent.__class__.__name__)}"

        # Import here to avoid circular imports
        from agentorchestrator.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

        # Create circuit breaker for this agent
        self._circuit = CircuitBreaker(
            name=self._flowforge_name,
            config=CircuitBreakerConfig(
                failure_threshold=self._config.circuit_failure_threshold,
                recovery_timeout=self._config.circuit_recovery_seconds,
            ),
        )

    @property
    def wrapped_agent(self) -> BaseAgent:
        """Get the wrapped agent."""
        return self._wrapped_agent

    @property
    def circuit_is_open(self) -> bool:
        """Check if circuit breaker is open."""
        return self._circuit.is_open

    @property
    def circuit_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        stats = self._circuit.stats
        return {
            "state": self._circuit.state.value,
            "failures": stats.failures,
            "successes": stats.successes,
            "total_calls": stats.total_calls,
            "total_failures": stats.total_failures,
        }

    async def initialize(self) -> None:
        """Initialize the wrapped agent."""
        await self._wrapped_agent.initialize()
        await super().initialize()

    async def cleanup(self) -> None:
        """Cleanup the wrapped agent."""
        await self._wrapped_agent.cleanup()
        await super().cleanup()

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch with resilience: timeout + retry + circuit breaker.

        Returns:
            AgentResult with data or error details
        """
        import asyncio
        import time

        start = time.perf_counter()
        last_error: Exception | None = None
        attempt = 0
        delay_ms = self._config.retry_delay_ms

        # Check circuit breaker first
        from agentorchestrator.utils.circuit_breaker import CircuitBreakerError

        if self._circuit.is_open:
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source=self._flowforge_name,
                query=query,
                duration_ms=duration,
                error=f"Circuit breaker open for {self._flowforge_name}",
                metadata={"circuit_state": "open", "attempt": 0},
            )

        # Retry loop
        while attempt < self._config.max_retries:
            attempt += 1
            try:
                # Execute with timeout and circuit breaker
                async with self._circuit:
                    result = await asyncio.wait_for(
                        self._wrapped_agent.fetch(query, **kwargs),
                        timeout=self._config.timeout_seconds,
                    )

                # Success!
                result.metadata["attempts"] = attempt
                result.metadata["circuit_state"] = self._circuit.state.value
                return result

            except asyncio.TimeoutError:
                last_error = asyncio.TimeoutError(
                    f"Agent {self._flowforge_name} timed out after {self._config.timeout_seconds}s"
                )
                logger.warning(
                    f"{self._flowforge_name} attempt {attempt}/{self._config.max_retries} "
                    f"timed out after {self._config.timeout_seconds}s"
                )
            except CircuitBreakerError as e:
                # Circuit opened mid-retry
                duration = (time.perf_counter() - start) * 1000
                return AgentResult(
                    data=None,
                    source=self._flowforge_name,
                    query=query,
                    duration_ms=duration,
                    error=str(e),
                    metadata={"circuit_state": "open", "attempt": attempt},
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"{self._flowforge_name} attempt {attempt}/{self._config.max_retries} "
                    f"failed: {e}"
                )

            # Retry delay with backoff (if not last attempt)
            if attempt < self._config.max_retries:
                await asyncio.sleep(delay_ms / 1000)
                delay_ms = int(delay_ms * self._config.retry_backoff)

        # All retries exhausted
        duration = (time.perf_counter() - start) * 1000
        return AgentResult(
            data=None,
            source=self._flowforge_name,
            query=query,
            duration_ms=duration,
            error=f"Failed after {attempt} attempts: {last_error}",
            metadata={
                "attempts": attempt,
                "circuit_state": self._circuit.state.value,
                "last_error_type": type(last_error).__name__ if last_error else None,
            },
        )

    async def health_check(self) -> bool:
        """
        Check health: agent health + circuit state.

        Returns False if circuit is open or agent is unhealthy.
        """
        if self._circuit.is_open:
            return False
        return await self._wrapped_agent.health_check()

    def reset_circuit(self) -> None:
        """Reset circuit breaker to closed state."""
        self._circuit.reset()


class ResilientCompositeAgent(BaseAgent):
    """
    Composite agent that runs multiple agents with resilience and partial success.

    Unlike CompositeAgent, this:
    - Wraps each agent with ResilientAgent automatically
    - Tracks per-agent success/failure separately
    - Returns partial results (successful agents) even if some fail
    - Surfaces clear per-agent errors instead of opaque failures

    Usage:
        composite = ResilientCompositeAgent(
            agents=[NewsAgent(), SECFilingAgent(), EarningsAgent()],
            config=ResilientAgentConfig(timeout_seconds=10.0),
        )

        result = await composite.fetch("Apple Inc")

        # result.data contains successful agent results
        # result.metadata contains per-agent status
        # result.error contains comma-separated failures (if any)
    """

    def __init__(
        self,
        agents: list[BaseAgent],
        config: ResilientAgentConfig | None = None,
        name: str = "resilient_composite",
    ):
        super().__init__()
        self._flowforge_name = name
        self._config = config or ResilientAgentConfig()

        # Wrap each agent with resilience
        self._resilient_agents: list[ResilientAgent] = []
        for agent in agents:
            if isinstance(agent, ResilientAgent):
                self._resilient_agents.append(agent)
            else:
                self._resilient_agents.append(
                    ResilientAgent(agent=agent, config=self._config)
                )

    @property
    def agents(self) -> list[ResilientAgent]:
        """Get wrapped resilient agents."""
        return self._resilient_agents

    async def initialize(self) -> None:
        """Initialize all agents."""
        for agent in self._resilient_agents:
            await agent.initialize()
        await super().initialize()

    async def cleanup(self) -> None:
        """Cleanup all agents."""
        for agent in self._resilient_agents:
            await agent.cleanup()
        await super().cleanup()

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch from all agents with partial success support.

        Even if some agents fail, returns results from successful agents.
        """
        import asyncio
        import time

        start = time.perf_counter()

        # Run all agents concurrently
        tasks = [agent.fetch(query, **kwargs) for agent in self._resilient_agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        combined_data = {}
        agent_status = {}
        errors = []
        success_count = 0
        failure_count = 0

        for agent, result in zip(self._resilient_agents, results):
            agent_name = agent._flowforge_name

            if isinstance(result, Exception):
                # Unexpected exception (should be caught by ResilientAgent)
                errors.append(f"{agent_name}: {type(result).__name__}: {result}")
                agent_status[agent_name] = {
                    "success": False,
                    "error": str(result),
                    "circuit_state": agent._circuit.state.value,
                }
                failure_count += 1
            elif result.success:
                combined_data[agent_name] = result.data
                agent_status[agent_name] = {
                    "success": True,
                    "duration_ms": result.duration_ms,
                    "circuit_state": agent._circuit.state.value,
                }
                success_count += 1
            else:
                # Agent returned error in result
                errors.append(f"{agent_name}: {result.error}")
                agent_status[agent_name] = {
                    "success": False,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                    "attempts": result.metadata.get("attempts", 1),
                    "circuit_state": agent._circuit.state.value,
                }
                failure_count += 1

        duration = (time.perf_counter() - start) * 1000

        # Build result with partial success info
        return AgentResult(
            data=combined_data,
            source=self._flowforge_name,
            query=query,
            duration_ms=duration,
            error="; ".join(errors) if errors else None,
            metadata={
                "agent_count": len(self._resilient_agents),
                "success_count": success_count,
                "failure_count": failure_count,
                "partial_success": success_count > 0 and failure_count > 0,
                "agent_status": agent_status,
            },
        )

    async def health_check(self) -> bool:
        """Check health of all agents."""
        import asyncio
        checks = await asyncio.gather(
            *[agent.health_check() for agent in self._resilient_agents]
        )
        return all(checks)

    def get_agent_health(self) -> dict[str, dict[str, Any]]:
        """Get detailed health status for each agent."""
        return {
            agent._flowforge_name: {
                "initialized": agent._initialized,
                "circuit_state": agent._circuit.state.value,
                "circuit_stats": agent.circuit_stats,
            }
            for agent in self._resilient_agents
        }


# Backward compatibility alias
ResilienceConfig = ResilientAgentConfig
