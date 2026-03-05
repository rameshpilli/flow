"""
AgentOrchestrator Base Agent
============================

This module provides the base classes for data agents in AgentOrchestrator.

Agents are responsible for fetching data from external sources (APIs, databases,
files, etc.). They should be stateless, idempotent, and return structured results
with optional citation tracking for provenance.

Classes:
    AgentResult: Dataclass for agent operation results with citation support.
    BaseAgent: Abstract base class that all data agents must inherit from.
    CompositeAgent: Agent that combines results from multiple agents.
    ResilientAgent: Wrapper adding timeout, retry, and circuit-breaker resilience.
    ResilientAgentConfig: Configuration for resilience settings.
    ResilientCompositeAgent: Composite agent with per-agent resilience.

Usage:
    from agentorchestrator.agents import BaseAgent, AgentResult

    @ao.agent(name="news_agent")
    class NewsAgent(BaseAgent):
        async def fetch(self, query: str, **kwargs) -> AgentResult:
            # Fetch news data from API
            data = await self._fetch_news(query)
            return AgentResult(
                data=data,
                source="news_agent",
                query=query,
            )

Example:
    >>> from agentorchestrator.agents import ResilientAgent, ResilientAgentConfig
    >>>
    >>> # Wrap agent with resilience
    >>> news = NewsAgent()
    >>> resilient_news = ResilientAgent(
    ...     agent=news,
    ...     config=ResilientAgentConfig(timeout_seconds=10.0, max_retries=3),
    ... )
    >>>
    >>> result = await resilient_news.fetch("Apple earnings")
    >>> if result.success:
    ...     print(result.data)

See Also:
    - agentorchestrator.connectors: Low-level API connectors used by agents.
    - agentorchestrator.models.citation: Citation model for source tracking.
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
    "ResilientAgentConfig",
    "ResilientCompositeAgent",
    "ResilienceConfig",
]

T = TypeVar("T")


@dataclass
class AgentResult(Generic[T]):
    """
    Result from an agent operation.

    This dataclass encapsulates the output from an agent fetch operation,
    including the data, metadata, timing information, and optional citations
    for source verification and provenance tracking.

    Attributes:
        data (T): The fetched data. Can be any type (dict, list, str, etc.).
        source (str): Name of the agent that produced this result.
        query (str): The query/request that was executed.
        timestamp (datetime): When the result was created. Default: now.
        metadata (dict[str, Any]): Additional metadata about the fetch.
        error (str | None): Error message if fetch failed. None on success.
        duration_ms (float): Time taken to fetch in milliseconds.
        citations (list[Any]): List of Citation objects for source tracking.
        raw_content (str | None): Raw content for citation verification.

    Properties:
        success (bool): True if no error occurred.
        has_citations (bool): True if citations are attached.

    Methods:
        add_citation(): Add a citation to this result.

    Example:
        >>> from agentorchestrator.models import Citation
        >>>
        >>> result = AgentResult(
        ...     data={"revenue": 394.3, "unit": "billion"},
        ...     source="sec_filing_agent",
        ...     query="AAPL revenue 2024",
        ...     duration_ms=250.5,
        ...     citations=[
        ...         Citation(
        ...             source_type="document",
        ...             source_name="sec_filing_agent",
        ...             content="Total net sales were $394,328 million",
        ...             document_id="AAPL-10K-2024",
        ...         )
        ...     ],
        ... )
        >>>
        >>> print(result.success)  # True
        >>> print(result.has_citations)  # True

    See Also:
        Citation: Model for source citations.
        BaseAgent.fetch(): Method that returns AgentResult.
    """

    data: T
    source: str
    query: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0
    citations: list[Any] = field(default_factory=list)
    raw_content: str | None = None

    @property
    def success(self) -> bool:
        """
        Check if the operation was successful.

        Returns:
            bool: True if no error occurred, False otherwise.

        Example:
            >>> if result.success:
            ...     process_data(result.data)
            ... else:
            ...     log_error(result.error)
        """
        return self.error is None

    @property
    def has_citations(self) -> bool:
        """
        Check if result has citations attached.

        Returns:
            bool: True if one or more citations exist.

        Example:
            >>> if result.has_citations:
            ...     for citation in result.citations:
            ...         print(f"Source: {citation.source_name}")
        """
        return len(self.citations) > 0

    def add_citation(
        self,
        content: str,
        reasoning: str | None = None,
        document_id: str | None = None,
        **kwargs: Any,
    ) -> "AgentResult[T]":
        """
        Add a citation to this result for source tracking.

        This method creates a Citation object and appends it to the
        result's citations list. Use citations to track data provenance
        and enable source verification.

        Args:
            content (str): Verbatim quote or excerpt from the source.
                Should be the exact text that supports the data.
            reasoning (str | None): Explanation of why this citation
                supports the data. Optional but recommended.
            document_id (str | None): Unique identifier for the source
                document (e.g., "AAPL-10K-2024", "news-article-123").
            **kwargs: Additional fields to pass to the Citation constructor.
                Common kwargs: page_number, section, confidence_score.

        Returns:
            AgentResult[T]: Self, for method chaining.

        Example:
            >>> result = AgentResult(data={"revenue": 100}, source="agent", query="q")
            >>> result.add_citation(
            ...     content="Revenue was $100 million in Q4",
            ...     reasoning="Direct revenue figure from earnings report",
            ...     document_id="earnings-q4-2024",
            ...     page_number=5,
            ... )
            >>>
            >>> # Chain multiple citations
            >>> result.add_citation(...).add_citation(...)

        See Also:
            Citation: The citation model with all available fields.
        """
        from agentorchestrator.models.citation import Citation

        citation = Citation(
            source_type="agent",
            source_name=self.source,
            content=content,
            reasoning=reasoning,
            document_id=document_id,
            **kwargs,
        )
        self.citations.append(citation)
        return self


class BaseAgent(ABC):
    """
    Abstract base class for AgentOrchestrator data agents.

    Agents are responsible for fetching data from external sources.
    They should be stateless and idempotent - the same query should
    always produce the same result (or an error).

    Attributes:
        config (dict[str, Any]): Agent configuration dictionary.
        _initialized (bool): Whether the agent has been initialized.
        _ao_agent (bool): Marker for AgentOrchestrator registration.
        _ao_name (str): Registered name of this agent.
        _ao_version (str): Version string for this agent.

    Methods:
        initialize(): Setup agent (connections, resources).
        cleanup(): Teardown agent resources.
        fetch(): Fetch data based on query (abstract - must implement).
        health_check(): Check if agent is healthy.

    Example:
        >>> from agentorchestrator.agents import BaseAgent, AgentResult
        >>>
        >>> class MyDataAgent(BaseAgent):
        ...     async def initialize(self) -> None:
        ...         self._client = await create_client()
        ...         await super().initialize()
        ...
        ...     async def fetch(self, query: str, **kwargs) -> AgentResult:
        ...         data = await self._client.search(query)
        ...         return AgentResult(
        ...             data=data,
        ...             source=self._ao_name,
        ...             query=query,
        ...         )
        ...
        ...     async def cleanup(self) -> None:
        ...         await self._client.close()
        ...         await super().cleanup()

    Registration with @ao.agent:
        >>> @ao.agent(name="news_agent", version="1.0.0")
        ... class NewsAgent(BaseAgent):
        ...     async def fetch(self, query: str, **kwargs) -> AgentResult:
        ...         ...

    See Also:
        AgentResult: Return type for fetch() method.
        ResilientAgent: Wrapper for adding resilience.
    """

    _ao_agent = True
    _ao_name: str = ""
    _ao_version: str = "1.0.0"

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the agent with optional configuration.

        Args:
            config (dict[str, Any] | None): Configuration dictionary.
                Contents depend on the specific agent implementation.
                Default: Empty dict {}.

        Example:
            >>> agent = MyAgent(config={"api_key": "xxx", "timeout": 30})
        """
        self.config = config or {}
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the agent (e.g., establish connections, load resources).

        Override this method to add custom initialization logic.
        Always call super().initialize() at the end.

        Raises:
            ConnectionError: If required connections cannot be established.
            ConfigurationError: If required config is missing.

        Example:
            >>> async def initialize(self) -> None:
            ...     self._session = aiohttp.ClientSession()
            ...     await super().initialize()
        """
        self._initialized = True

    async def cleanup(self) -> None:
        """
        Cleanup agent resources (e.g., close connections).

        Override this method to add custom cleanup logic.
        Always call super().cleanup() at the end.

        Example:
            >>> async def cleanup(self) -> None:
            ...     await self._session.close()
            ...     await super().cleanup()
        """
        self._initialized = False

    @abstractmethod
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch data based on a query.

        This is the main method that agents must implement. It should
        fetch data from the external source and return an AgentResult.

        Args:
            query (str): The search/fetch query. Interpretation depends
                on the agent (could be a search term, ticker, ID, etc.).
            **kwargs: Additional parameters for the fetch.
                Common kwargs:
                - limit (int): Max results to return
                - start_date (str): Filter by date
                - filters (dict): Additional filters

        Returns:
            AgentResult: Result containing the fetched data, or error info.

        Raises:
            NotImplementedError: If not overridden by subclass.

        Example:
            >>> async def fetch(self, query: str, **kwargs) -> AgentResult:
            ...     limit = kwargs.get("limit", 10)
            ...     data = await self._api.search(query, limit=limit)
            ...     return AgentResult(
            ...         data=data,
            ...         source=self._ao_name,
            ...         query=query,
            ...     )
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if the agent is healthy and can fetch data.

        Override this method for custom health checks (e.g., verify
        API connectivity, check credentials, etc.).

        Returns:
            bool: True if agent is healthy, False otherwise.

        Example:
            >>> async def health_check(self) -> bool:
            ...     try:
            ...         await self._api.ping()
            ...         return True
            ...     except Exception:
            ...         return False
        """
        return self._initialized

    def __repr__(self) -> str:
        """Return string representation of the agent."""
        return f"{self.__class__.__name__}(name={self._ao_name})"


class CompositeAgent(BaseAgent):
    """
    Agent that combines results from multiple agents.

    Useful for aggregating data from multiple sources in parallel.
    All agents are queried with the same query, and results are
    combined into a single AgentResult.

    Attributes:
        agents (list[BaseAgent]): List of agents to combine.

    Example:
        >>> from agentorchestrator.agents import CompositeAgent
        >>>
        >>> composite = CompositeAgent([
        ...     NewsAgent(),
        ...     SECFilingAgent(),
        ...     EarningsAgent(),
        ... ])
        >>>
        >>> result = await composite.fetch("Apple Inc")
        >>> # result.data = {
        >>> #     "NewsAgent": {...},
        >>> #     "SECFilingAgent": {...},
        >>> #     "EarningsAgent": {...},
        >>> # }

    Note:
        If you need resilience (timeout, retry, circuit-breaker),
        use ResilientCompositeAgent instead.

    See Also:
        ResilientCompositeAgent: With per-agent resilience.
    """

    def __init__(self, agents: list[BaseAgent], config: dict[str, Any] | None = None):
        """
        Initialize composite agent with a list of agents.

        Args:
            agents (list[BaseAgent]): Agents to combine. All will be
                queried in parallel when fetch() is called.
            config (dict[str, Any] | None): Optional configuration.

        Example:
            >>> composite = CompositeAgent([NewsAgent(), SECAgent()])
        """
        super().__init__(config)
        self.agents = agents

    async def initialize(self) -> None:
        """Initialize all component agents."""
        for agent in self.agents:
            await agent.initialize()
        await super().initialize()

    async def cleanup(self) -> None:
        """Cleanup all component agents."""
        for agent in self.agents:
            await agent.cleanup()
        await super().cleanup()

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch from all agents in parallel and combine results.

        Args:
            query (str): Query to send to all agents.
            **kwargs: Additional parameters passed to each agent.

        Returns:
            AgentResult: Combined result with data from each agent.
                - data: Dict mapping agent_name -> agent_data
                - error: Combined errors from any failed agents
                - metadata.agent_count: Number of agents queried

        Example:
            >>> result = await composite.fetch("Apple Inc", limit=10)
            >>> for agent_name, data in result.data.items():
            ...     print(f"{agent_name}: {len(data)} results")
        """
        import asyncio
        import time

        start = time.perf_counter()

        tasks = [agent.fetch(query, **kwargs) for agent in self.agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined_data = {}
        errors = []

        for agent, result in zip(self.agents, results):
            agent_name = getattr(agent, "_ao_name", agent.__class__.__name__)
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
        """Check health of all component agents."""
        checks = [await agent.health_check() for agent in self.agents]
        return all(checks)


@dataclass
class ResilientAgentConfig:
    """
    Configuration for ResilientAgent wrapper.

    Controls timeout, retry, and circuit-breaker behavior for
    resilient agent wrappers.

    Attributes:
        timeout_seconds (float): Max time for each fetch call. Default: 30.0.
            Calls exceeding this are cancelled and retried.
        max_retries (int): Number of retry attempts. Default: 3.
            Total attempts = max_retries (first attempt + retries).
        retry_delay_ms (int): Initial delay between retries. Default: 1000.
            Increases with exponential backoff.
        retry_backoff (float): Backoff multiplier. Default: 2.0.
            Delay doubles after each retry: 1s -> 2s -> 4s.
        circuit_failure_threshold (int): Failures before opening circuit. Default: 5.
            Once open, calls fail immediately until recovery.
        circuit_recovery_seconds (float): Time before half-open state. Default: 30.0.
            After this, one test call is allowed through.

    Example:
        >>> config = ResilientAgentConfig(
        ...     timeout_seconds=10.0,      # 10s timeout per call
        ...     max_retries=2,             # Try up to 2 times
        ...     circuit_failure_threshold=3,  # Open after 3 failures
        ... )
        >>> resilient = ResilientAgent(my_agent, config)

    See Also:
        ResilientAgent: Agent wrapper using this config.
        CircuitBreaker: Circuit breaker implementation.
    """

    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay_ms: int = 1000
    retry_backoff: float = 2.0
    circuit_failure_threshold: int = 5
    circuit_recovery_seconds: float = 30.0


class ResilientAgent(BaseAgent):
    """
    Wrapper that adds timeout, retry, and circuit-breaker to any agent.

    Provides production-ready resilience with:
    - Per-call timeout (prevents hanging)
    - Retry with exponential backoff (handles transient failures)
    - Circuit breaker (prevents cascading failures)
    - Detailed error tracking in result metadata

    Attributes:
        wrapped_agent (BaseAgent): The wrapped agent.
        circuit_is_open (bool): Whether circuit breaker is open.
        circuit_stats (dict): Circuit breaker statistics.

    Methods:
        fetch(): Fetch with resilience wrapping.
        reset_circuit(): Reset circuit to closed state.

    Example:
        >>> from agentorchestrator.agents import ResilientAgent, ResilientAgentConfig
        >>>
        >>> # Wrap an existing agent
        >>> news_agent = NewsAgent()
        >>> resilient_news = ResilientAgent(
        ...     agent=news_agent,
        ...     config=ResilientAgentConfig(
        ...         timeout_seconds=10.0,
        ...         max_retries=3,
        ...         circuit_failure_threshold=5,
        ...     ),
        ... )
        >>>
        >>> # Use as normal
        >>> result = await resilient_news.fetch("Apple Inc")
        >>>
        >>> # Check circuit state
        >>> if resilient_news.circuit_is_open:
        ...     logger.warning("Circuit open - agent is failing!")
        >>>
        >>> # View stats
        >>> print(resilient_news.circuit_stats)
        >>> # {"state": "closed", "failures": 0, "successes": 10, ...}

    Circuit Breaker States:
        - CLOSED: Normal operation, calls go through.
        - OPEN: Too many failures, calls rejected immediately.
        - HALF_OPEN: Testing if service recovered.

    See Also:
        ResilientAgentConfig: Configuration options.
        ResilientCompositeAgent: Multiple agents with resilience.
    """

    def __init__(
        self,
        agent: BaseAgent,
        config: ResilientAgentConfig | None = None,
        name: str | None = None,
    ):
        """
        Initialize resilient wrapper around an agent.

        Args:
            agent (BaseAgent): The agent to wrap with resilience.
            config (ResilientAgentConfig | None): Resilience configuration.
                If None, uses default values.
            name (str | None): Name for this wrapper. Default: "resilient_{agent_name}".

        Example:
            >>> resilient = ResilientAgent(
            ...     agent=MyAgent(),
            ...     config=ResilientAgentConfig(timeout_seconds=5.0),
            ...     name="my_resilient_agent",
            ... )
        """
        super().__init__()
        self._wrapped_agent = agent
        self._config = config or ResilientAgentConfig()
        self._ao_name = name or f"resilient_{getattr(agent, '_ao_name', agent.__class__.__name__)}"

        from agentorchestrator.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

        self._circuit = CircuitBreaker(
            name=self._ao_name,
            config=CircuitBreakerConfig(
                failure_threshold=self._config.circuit_failure_threshold,
                recovery_timeout=self._config.circuit_recovery_seconds,
            ),
        )

    @property
    def wrapped_agent(self) -> BaseAgent:
        """
        Get the wrapped agent.

        Returns:
            BaseAgent: The original agent wrapped by this resilient wrapper.
        """
        return self._wrapped_agent

    @property
    def circuit_is_open(self) -> bool:
        """
        Check if circuit breaker is open (rejecting calls).

        Returns:
            bool: True if circuit is open, False otherwise.

        Example:
            >>> if resilient.circuit_is_open:
            ...     logger.warning("Skipping call - circuit open")
        """
        return self._circuit.is_open

    @property
    def circuit_stats(self) -> dict[str, Any]:
        """
        Get circuit breaker statistics.

        Returns:
            dict: Statistics including state, failures, successes, etc.
                - state: "closed", "open", or "half_open"
                - failures: Current failure count
                - successes: Current success count
                - total_calls: Lifetime call count
                - total_failures: Lifetime failure count

        Example:
            >>> stats = resilient.circuit_stats
            >>> print(f"State: {stats['state']}, Failures: {stats['failures']}")
        """
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

        Wraps the underlying agent's fetch() with:
        1. Circuit breaker check (fail fast if open)
        2. Timeout enforcement
        3. Retry with exponential backoff
        4. Detailed error metadata

        Args:
            query (str): Query to pass to the wrapped agent.
            **kwargs: Additional parameters for the wrapped agent.

        Returns:
            AgentResult: Result from wrapped agent, or error result.
                On error, metadata includes:
                - attempts: Number of attempts made
                - circuit_state: Current circuit state
                - last_error_type: Type of last error (if failed)

        Example:
            >>> result = await resilient.fetch("AAPL")
            >>> if not result.success:
            ...     print(f"Failed after {result.metadata['attempts']} attempts")
            ...     print(f"Circuit state: {result.metadata['circuit_state']}")
        """
        import asyncio
        import time

        start = time.perf_counter()
        last_error: Exception | None = None
        attempt = 0
        delay_ms = self._config.retry_delay_ms

        from agentorchestrator.utils.circuit_breaker import CircuitBreakerError

        if self._circuit.is_open:
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=query,
                duration_ms=duration,
                error=f"Circuit breaker open for {self._ao_name}",
                metadata={"circuit_state": "open", "attempt": 0},
            )

        while attempt < self._config.max_retries:
            attempt += 1
            try:
                async with self._circuit:
                    result = await asyncio.wait_for(
                        self._wrapped_agent.fetch(query, **kwargs),
                        timeout=self._config.timeout_seconds,
                    )

                result.metadata["attempts"] = attempt
                result.metadata["circuit_state"] = self._circuit.state.value
                return result

            except asyncio.TimeoutError:
                last_error = asyncio.TimeoutError(
                    f"Agent {self._ao_name} timed out after {self._config.timeout_seconds}s"
                )
                logger.warning(
                    f"{self._ao_name} attempt {attempt}/{self._config.max_retries} "
                    f"timed out after {self._config.timeout_seconds}s"
                )
            except CircuitBreakerError as e:
                duration = (time.perf_counter() - start) * 1000
                return AgentResult(
                    data=None,
                    source=self._ao_name,
                    query=query,
                    duration_ms=duration,
                    error=str(e),
                    metadata={"circuit_state": "open", "attempt": attempt},
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"{self._ao_name} attempt {attempt}/{self._config.max_retries} "
                    f"failed: {e}"
                )

            if attempt < self._config.max_retries:
                await asyncio.sleep(delay_ms / 1000)
                delay_ms = int(delay_ms * self._config.retry_backoff)

        duration = (time.perf_counter() - start) * 1000
        return AgentResult(
            data=None,
            source=self._ao_name,
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

        Returns:
            bool: False if circuit is open or agent is unhealthy.

        Example:
            >>> if await resilient.health_check():
            ...     result = await resilient.fetch(query)
        """
        if self._circuit.is_open:
            return False
        return await self._wrapped_agent.health_check()

    def reset_circuit(self) -> None:
        """
        Reset circuit breaker to closed state.

        Use this to manually reset after fixing the underlying issue.

        Example:
            >>> resilient.reset_circuit()
            >>> # Circuit is now closed, calls will go through
        """
        self._circuit.reset()


class ResilientCompositeAgent(BaseAgent):
    """
    Composite agent with per-agent resilience and partial success support.

    Unlike CompositeAgent, this:
    - Wraps each agent with ResilientAgent automatically
    - Tracks per-agent success/failure separately
    - Returns partial results (successful agents) even if some fail
    - Surfaces clear per-agent errors in metadata

    Attributes:
        agents (list[ResilientAgent]): Wrapped resilient agents.

    Methods:
        fetch(): Fetch from all agents with partial success.
        get_agent_health(): Get detailed health for each agent.

    Example:
        >>> composite = ResilientCompositeAgent(
        ...     agents=[NewsAgent(), SECFilingAgent(), EarningsAgent()],
        ...     config=ResilientAgentConfig(timeout_seconds=10.0),
        ... )
        >>>
        >>> result = await composite.fetch("Apple Inc")
        >>>
        >>> # Check partial success
        >>> if result.metadata["partial_success"]:
        ...     print("Some agents failed, but got partial data")
        >>>
        >>> # Per-agent status
        >>> for name, status in result.metadata["agent_status"].items():
        ...     print(f"{name}: {'OK' if status['success'] else status['error']}")

    See Also:
        ResilientAgent: Per-agent resilience wrapper.
        ResilientAgentConfig: Resilience configuration.
    """

    def __init__(
        self,
        agents: list[BaseAgent],
        config: ResilientAgentConfig | None = None,
        name: str = "resilient_composite",
    ):
        """
        Initialize resilient composite with list of agents.

        Args:
            agents (list[BaseAgent]): Agents to combine. Each will be
                wrapped with ResilientAgent if not already.
            config (ResilientAgentConfig | None): Resilience config
                applied to all non-resilient agents.
            name (str): Name for this composite. Default: "resilient_composite".

        Example:
            >>> composite = ResilientCompositeAgent(
            ...     agents=[NewsAgent(), SECAgent()],
            ...     config=ResilientAgentConfig(timeout_seconds=5.0),
            ... )
        """
        super().__init__()
        self._ao_name = name
        self._config = config or ResilientAgentConfig()

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
        """
        Get wrapped resilient agents.

        Returns:
            list[ResilientAgent]: All resilient-wrapped agents.
        """
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
        This enables graceful degradation - you get what's available.

        Args:
            query (str): Query for all agents.
            **kwargs: Additional parameters for agents.

        Returns:
            AgentResult: Combined result with:
                - data: Dict mapping agent_name -> agent_data (successes only)
                - error: Combined error messages (if any failures)
                - metadata.success_count: Number of successful agents
                - metadata.failure_count: Number of failed agents
                - metadata.partial_success: True if some succeeded and some failed
                - metadata.agent_status: Per-agent status details

        Example:
            >>> result = await composite.fetch("AAPL")
            >>> print(f"Got data from {result.metadata['success_count']} agents")
            >>> if result.metadata.get("partial_success"):
            ...     print("Warning: Some agents failed")
        """
        import asyncio
        import time

        start = time.perf_counter()

        tasks = [agent.fetch(query, **kwargs) for agent in self._resilient_agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined_data = {}
        agent_status = {}
        errors = []
        success_count = 0
        failure_count = 0

        for agent, result in zip(self._resilient_agents, results):
            agent_name = agent._ao_name

            if isinstance(result, Exception):
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

        return AgentResult(
            data=combined_data,
            source=self._ao_name,
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
        """
        Get detailed health status for each agent.

        Returns:
            dict: Mapping of agent_name -> health details.
                Each entry contains:
                - initialized: Whether agent is initialized
                - circuit_state: Current circuit breaker state
                - circuit_stats: Circuit breaker statistics

        Example:
            >>> health = composite.get_agent_health()
            >>> for name, status in health.items():
            ...     print(f"{name}: {status['circuit_state']}")
        """
        return {
            agent._ao_name: {
                "initialized": agent._initialized,
                "circuit_state": agent._circuit.state.value,
                "circuit_stats": agent.circuit_stats,
            }
            for agent in self._resilient_agents
        }


# Backward compatibility alias
ResilienceConfig = ResilientAgentConfig
