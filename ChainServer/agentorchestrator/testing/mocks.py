"""
AgentOrchestrator Mock Objects for Testing

Provides mock implementations for agents, steps, and middleware.
"""

import asyncio
import functools
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class MockAgentResult:
    """
    Pre-configured result for MockAgent.

    Attributes:
        data: The data to return
        error: Optional error to simulate
        delay_seconds: Simulate latency
        call_count: Track how many times this result was used
    """
    data: Any = None
    error: Exception | None = None
    delay_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    # Internal tracking
    call_count: int = field(default=0, init=False)


class MockAgent(BaseAgent):
    """
    Mock agent for testing with configurable responses.

    Supports:
    - Static responses per query
    - Default response for unknown queries
    - Error simulation
    - Latency simulation
    - Call tracking

    Usage:
        # Simple mock with default response
        mock = MockAgent(
            name="news_agent",
            default_response={"articles": []},
        )

        # Mock with per-query responses
        mock = MockAgent(
            name="news_agent",
            responses={
                "Apple": {"articles": [{"title": "Apple News"}]},
                "Google": {"articles": [{"title": "Google News"}]},
            },
            default_response={"articles": []},
        )

        # Mock with error simulation
        mock = MockAgent(
            name="failing_agent",
            error=ConnectionError("API unavailable"),
        )

        # Register with forge
        forge.register_agent(mock)
    """

    def __init__(
        self,
        name: str,
        responses: dict[str, Any] | None = None,
        default_response: Any = None,
        error: Exception | None = None,
        delay_seconds: float = 0.0,
    ):
        """
        Initialize mock agent.

        Args:
            name: Agent name for registration
            responses: Dict mapping query -> response data
            default_response: Response for queries not in responses dict
            error: Exception to raise on fetch (simulates failure)
            delay_seconds: Simulate latency
        """
        self.name = name
        self._responses: dict[str, MockAgentResult] = {}
        self._default_response = default_response
        self._global_error = error
        self._global_delay = delay_seconds
        self._calls: list[dict[str, Any]] = []

        # Convert simple responses to MockAgentResult
        if responses:
            for query, data in responses.items():
                if isinstance(data, MockAgentResult):
                    self._responses[query] = data
                else:
                    self._responses[query] = MockAgentResult(data=data)

    def add_response(
        self,
        query: str,
        data: Any = None,
        error: Exception | None = None,
        delay_seconds: float = 0.0,
    ) -> "MockAgent":
        """
        Add or update a response for a specific query.

        Returns self for chaining.
        """
        self._responses[query] = MockAgentResult(
            data=data,
            error=error,
            delay_seconds=delay_seconds,
        )
        return self

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Return mock response for query.

        Args:
            query: The query string
            **kwargs: Additional arguments (captured for call tracking)

        Returns:
            AgentResult with mock data

        Raises:
            Configured error if set
        """
        # Record call
        call_info = {
            "query": query,
            "kwargs": kwargs,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._calls.append(call_info)

        # Check for global error first
        if self._global_error:
            raise self._global_error

        # Get response config
        response = self._responses.get(query)

        # Apply delay
        delay = response.delay_seconds if response else self._global_delay
        if delay > 0:
            await asyncio.sleep(delay)

        # Check for query-specific error
        if response and response.error:
            raise response.error

        # Get data
        if response:
            response.call_count += 1
            data = response.data
            metadata = response.metadata
        else:
            data = self._default_response
            metadata = {}

        return AgentResult(
            data=data,
            source=self.name,
            query=query,
            metadata=metadata,
        )

    async def initialize(self) -> None:
        """Mock initialization - no-op."""
        pass

    async def cleanup(self) -> None:
        """Mock cleanup - no-op."""
        pass

    async def health_check(self) -> bool:
        """Mock health check - returns True unless error configured."""
        return self._global_error is None

    @property
    def calls(self) -> list[dict[str, Any]]:
        """Get all recorded calls."""
        return self._calls

    @property
    def call_count(self) -> int:
        """Get total call count."""
        return len(self._calls)

    def reset(self) -> None:
        """Reset call tracking."""
        self._calls.clear()
        for response in self._responses.values():
            response.call_count = 0

    def assert_called(self, query: str | None = None) -> None:
        """Assert agent was called (optionally with specific query)."""
        if not self._calls:
            raise AssertionError(f"MockAgent '{self.name}' was never called")

        if query:
            queries = [c["query"] for c in self._calls]
            if query not in queries:
                raise AssertionError(
                    f"MockAgent '{self.name}' was not called with query '{query}'. "
                    f"Actual queries: {queries}"
                )

    def assert_not_called(self) -> None:
        """Assert agent was never called."""
        if self._calls:
            raise AssertionError(
                f"MockAgent '{self.name}' was called {len(self._calls)} time(s). "
                f"Queries: {[c['query'] for c in self._calls]}"
            )


def mock_step(
    step_name: str,
    returns: Any = None,
    raises: Exception | None = None,
    side_effect: Callable[..., Any] | None = None,
) -> Callable:
    """
    Decorator to mock a step function in tests.

    Patches the step registry to return mock results.

    Usage:
        @mock_step("fetch_news", returns={"articles": []})
        async def test_chain_with_mocked_step():
            result = await forge.launch("my_chain", {})
            assert result["success"]

        @mock_step("failing_step", raises=ValueError("oops"))
        async def test_error_handling():
            result = await forge.launch("my_chain", {})
            assert not result["success"]

    Args:
        step_name: Name of step to mock
        returns: Value to return from step
        raises: Exception to raise
        side_effect: Callable to invoke instead of step
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Create mock step function
            async def mock_fn(ctx: ChainContext) -> Any:
                if raises:
                    raise raises
                if side_effect:
                    return side_effect(ctx)
                return returns

            # Patch the step in registry
            from agentorchestrator import get_orchestrator
            forge = get_orchestrator()

            # Store original and patch
            original = None
            if step_name in forge._step_registry:
                original_spec = forge._step_registry.get_spec(step_name)
                if original_spec:
                    original = original_spec.func
                    # Replace with mock
                    original_spec.func = mock_fn

            try:
                return await func(*args, **kwargs)
            finally:
                # Restore original
                if original is not None:
                    spec = forge._step_registry.get_spec(step_name)
                    if spec:
                        spec.func = original

        return wrapper
    return decorator


@asynccontextmanager
async def mock_chain(
    chain_name: str,
    step_mocks: dict[str, Any] | None = None,
    agent_mocks: dict[str, MockAgent] | None = None,
):
    """
    Async context manager to mock multiple steps/agents in a chain.

    Usage:
        async with mock_chain(
            "my_chain",
            step_mocks={
                "fetch_data": {"data": "mocked"},
                "process": {"result": True},
            },
            agent_mocks={
                "news_agent": MockAgent(name="news_agent", default_response=[]),
            },
        ) as forge:
            result = await forge.launch("my_chain", {})
            assert result["success"]

    Args:
        chain_name: Name of chain to mock
        step_mocks: Dict of step_name -> return value
        agent_mocks: Dict of agent_name -> MockAgent
    """
    from agentorchestrator import get_orchestrator

    forge = get_orchestrator()
    originals: dict[str, Any] = {}
    original_agents: dict[str, Any] = {}

    try:
        # Mock steps
        if step_mocks:
            for step_name, return_value in step_mocks.items():
                if step_name in forge._step_registry:
                    spec = forge._step_registry.get_spec(step_name)
                    if spec:
                        originals[step_name] = spec.func

                        async def mock_fn(ctx, rv=return_value):
                            return rv

                        spec.func = mock_fn

        # Mock agents
        if agent_mocks:
            for agent_name, mock_agent in agent_mocks.items():
                if agent_name in forge._agent_registry:
                    original_agents[agent_name] = forge._agent_registry.get(agent_name)
                forge._agent_registry.register(agent_name, mock_agent)

        yield forge

    finally:
        # Restore steps
        for step_name, original_fn in originals.items():
            spec = forge._step_registry.get_spec(step_name)
            if spec:
                spec.func = original_fn

        # Restore agents
        for agent_name, original_agent in original_agents.items():
            if original_agent:
                forge._agent_registry.register(agent_name, original_agent)


class MockMiddleware(Middleware):
    """
    Mock middleware for testing middleware behavior.

    Tracks all calls and allows configuring behavior.

    Usage:
        mock_mw = MockMiddleware()
        forge.use_middleware(mock_mw)

        await forge.launch("chain", {})

        assert mock_mw.before_calls == ["step1", "step2", "step3"]
        assert mock_mw.after_calls == ["step1", "step2", "step3"]
    """

    def __init__(
        self,
        priority: int = 100,
        fail_on_step: str | None = None,
        block_step: str | None = None,
    ):
        """
        Initialize mock middleware.

        Args:
            priority: Middleware priority
            fail_on_step: Step name to fail on (raises in before())
            block_step: Step name to block (raises SkipStep)
        """
        super().__init__(priority=priority)
        self.before_calls: list[str] = []
        self.after_calls: list[str] = []
        self.error_calls: list[tuple[str, Exception]] = []
        self._fail_on_step = fail_on_step
        self._block_step = block_step

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """Record before call."""
        self.before_calls.append(step_name)

        if self._fail_on_step == step_name:
            raise RuntimeError(f"MockMiddleware configured to fail on {step_name}")

        if self._block_step == step_name:
            from agentorchestrator.middleware.base import SkipStep
            raise SkipStep(f"MockMiddleware blocking {step_name}")

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Record after call."""
        self.after_calls.append(step_name)

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """Record error call."""
        self.error_calls.append((step_name, error))

    def reset(self) -> None:
        """Reset all tracking."""
        self.before_calls.clear()
        self.after_calls.clear()
        self.error_calls.clear()

    def assert_step_executed(self, step_name: str) -> None:
        """Assert a step was executed (before + after called)."""
        if step_name not in self.before_calls:
            raise AssertionError(f"Step '{step_name}' before() was not called")
        if step_name not in self.after_calls:
            raise AssertionError(f"Step '{step_name}' after() was not called")

    def assert_step_failed(self, step_name: str) -> None:
        """Assert a step failed (on_error called)."""
        failed_steps = [s for s, _ in self.error_calls]
        if step_name not in failed_steps:
            raise AssertionError(
                f"Step '{step_name}' did not fail. "
                f"Failed steps: {failed_steps}"
            )
