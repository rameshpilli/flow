"""
FlowForge Test Fixtures

Shared fixtures for all FlowForge tests.
"""

import asyncio
from typing import Any, AsyncGenerator, Generator

import pytest

from flowforge import ChainContext, FlowForge
from flowforge.agents import AgentResult, BaseAgent
from flowforge.core.context import ContextScope, StepResult
from flowforge.core.registry import (
    AgentRegistry,
    ChainRegistry,
    StepRegistry,
    create_isolated_registries,
    reset_global_registries,
)
from flowforge.middleware.base import Middleware


# ══════════════════════════════════════════════════════════════════════════════
#                           CORE FIXTURES
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def isolated_registries() -> tuple[AgentRegistry, StepRegistry, ChainRegistry]:
    """Create isolated registries for test isolation."""
    return create_isolated_registries()


@pytest.fixture
def forge(isolated_registries) -> Generator[FlowForge, None, None]:
    """
    Create an isolated FlowForge instance for testing.

    Uses isolated registries to prevent cross-test contamination.
    """
    agent_reg, step_reg, chain_reg = isolated_registries
    fg = FlowForge(
        name="test_forge",
        version="1.0.0",
        agent_registry=agent_reg,
        step_registry=step_reg,
        chain_registry=chain_reg,
        isolated=True,
    )
    yield fg
    fg.clear()


@pytest.fixture
def context() -> ChainContext:
    """Create a fresh ChainContext for testing."""
    return ChainContext(request_id="test_request_123")


@pytest.fixture
def context_with_data() -> ChainContext:
    """Create a ChainContext with initial data."""
    return ChainContext(
        request_id="test_request_456",
        initial_data={
            "company": "Apple Inc",
            "ticker": "AAPL",
            "query": "Get company info",
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
#                           MOCK AGENTS
# ══════════════════════════════════════════════════════════════════════════════


class MockAgent(BaseAgent):
    """Mock agent for testing."""

    def __init__(self, name: str = "mock_agent", delay_ms: float = 0):
        self.name = name
        self.delay_ms = delay_ms
        self.fetch_count = 0

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        self.fetch_count += 1
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000)
        return AgentResult(
            data={"query": query, "result": f"mock_data_for_{query}"},
            source=self.name,
            query=query,
        )


class FailingAgent(BaseAgent):
    """Agent that always fails for testing error handling."""

    def __init__(self, error_message: str = "Intentional failure"):
        self.error_message = error_message

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        raise RuntimeError(self.error_message)


class SlowAgent(BaseAgent):
    """Agent with configurable delay for timeout testing."""

    def __init__(self, delay_seconds: float = 5.0):
        self.delay_seconds = delay_seconds

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        await asyncio.sleep(self.delay_seconds)
        return AgentResult(
            data={"query": query},
            source="slow_agent",
            query=query,
        )


@pytest.fixture
def mock_agent() -> MockAgent:
    """Create a mock agent instance."""
    return MockAgent()


@pytest.fixture
def failing_agent() -> FailingAgent:
    """Create a failing agent instance."""
    return FailingAgent()


# ══════════════════════════════════════════════════════════════════════════════
#                           MOCK MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════


class TrackingMiddleware(Middleware):
    """Middleware that tracks all calls for testing."""

    def __init__(self):
        super().__init__()
        self.before_calls: list[str] = []
        self.after_calls: list[tuple[str, bool]] = []
        self.error_calls: list[tuple[str, str]] = []

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        self.before_calls.append(step_name)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        self.after_calls.append((step_name, result.success))

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        self.error_calls.append((step_name, str(error)))

    def reset(self):
        """Reset tracking data."""
        self.before_calls.clear()
        self.after_calls.clear()
        self.error_calls.clear()


class ModifyingMiddleware(Middleware):
    """Middleware that modifies context for testing."""

    def __init__(self, key: str, value: Any):
        super().__init__()
        self.key = key
        self.value = value

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        ctx.set(f"{self.key}_before_{step_name}", self.value, scope=ContextScope.CHAIN)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        ctx.set(f"{self.key}_after_{step_name}", self.value, scope=ContextScope.CHAIN)


@pytest.fixture
def tracking_middleware() -> TrackingMiddleware:
    """Create a tracking middleware instance."""
    return TrackingMiddleware()


# ══════════════════════════════════════════════════════════════════════════════
#                           STEP FACTORIES
# ══════════════════════════════════════════════════════════════════════════════


def create_simple_step(name: str, output: Any = None, delay_ms: float = 0):
    """Factory to create simple test steps."""
    async def step_handler(ctx: ChainContext) -> Any:
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)
        ctx.set(f"{name}_output", output or {"step": name}, scope=ContextScope.CHAIN)
        return output or {"step": name}

    step_handler.__name__ = name
    return step_handler


def create_failing_step(name: str, error_message: str = "Step failed"):
    """Factory to create failing test steps."""
    async def step_handler(ctx: ChainContext) -> Any:
        raise RuntimeError(error_message)

    step_handler.__name__ = name
    return step_handler


def create_dependency_step(name: str, dependency_key: str):
    """Factory to create steps that read from dependencies."""
    async def step_handler(ctx: ChainContext) -> Any:
        dep_value = ctx.get(dependency_key)
        output = {"step": name, "dependency_value": dep_value}
        ctx.set(f"{name}_output", output, scope=ContextScope.CHAIN)
        return output

    step_handler.__name__ = name
    return step_handler


# ══════════════════════════════════════════════════════════════════════════════
#                           CLEANUP FIXTURES
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def reset_registries_after_test():
    """Reset global registries after each test to ensure isolation."""
    yield
    reset_global_registries()


# ══════════════════════════════════════════════════════════════════════════════
#                           ASYNC TEST HELPERS
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def run_async():
    """Helper to run async functions in sync tests."""
    def _run(coro):
        return asyncio.get_event_loop().run_until_complete(coro)
    return _run
