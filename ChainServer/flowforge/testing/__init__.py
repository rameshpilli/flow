"""
FlowForge Testing Utilities

Provides testing helpers for FlowForge chains, steps, and agents:
- MockAgent: Create mock agents with predefined responses
- mock_step: Decorator to mock step functions
- mock_chain: Context manager for mocking entire chains
- IsolatedForge: Pre-configured forge with test isolation
- Fixtures: Common pytest fixtures for FlowForge testing

Usage:
    from flowforge.testing import MockAgent, mock_step, IsolatedForge

    # Create mock agent
    mock_news = MockAgent(
        name="news_agent",
        responses={"Apple": {"articles": [...]}},
    )

    # Mock a step
    @mock_step("fetch_data", returns={"data": "mocked"})
    async def test_pipeline():
        result = await forge.launch("pipeline", {})
        assert result["success"]

    # Use isolated forge in tests
    async def test_with_isolation():
        async with IsolatedForge() as forge:
            @forge.step(name="my_step")
            async def my_step(ctx):
                return {"result": True}
            ...
"""

from flowforge.testing.assertions import (
    assert_chain_valid,
    assert_context_has,
    assert_step_completed,
    assert_step_failed,
)
from flowforge.testing.fixtures import (
    IsolatedForge,
    create_test_context,
    create_test_forge,
    sample_chain_request,
)
from flowforge.testing.mocks import (
    MockAgent,
    MockAgentResult,
    MockMiddleware,
    mock_chain,
    mock_step,
)

__all__ = [
    # Mocks
    "MockAgent",
    "MockAgentResult",
    "mock_step",
    "mock_chain",
    "MockMiddleware",
    # Fixtures
    "IsolatedForge",
    "create_test_context",
    "create_test_forge",
    "sample_chain_request",
    # Assertions
    "assert_step_completed",
    "assert_step_failed",
    "assert_context_has",
    "assert_chain_valid",
]
