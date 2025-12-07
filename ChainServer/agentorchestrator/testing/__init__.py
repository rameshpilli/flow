"""
AgentOrchestrator Testing Utilities

Provides testing helpers for AgentOrchestrator chains, steps, and agents:
- MockAgent: Create mock agents with predefined responses
- mock_step: Decorator to mock step functions
- mock_chain: Context manager for mocking entire chains
- IsolatedOrchestrator: Pre-configured forge with test isolation
- Fixtures: Common pytest fixtures for AgentOrchestrator testing

Usage:
    from agentorchestrator.testing import MockAgent, mock_step, IsolatedOrchestrator

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
        async with IsolatedOrchestrator() as forge:
            @forge.step(name="my_step")
            async def my_step(ctx):
                return {"result": True}
            ...
"""

from agentorchestrator.testing.assertions import (
    assert_chain_valid,
    assert_context_has,
    assert_step_completed,
    assert_step_failed,
)
from agentorchestrator.testing.fixtures import (
    IsolatedOrchestrator,
    create_test_context,
    create_test_forge,
    sample_chain_request,
)
from agentorchestrator.testing.mocks import (
    MockAgent,
    MockAgentResult,
    MockMiddleware,
    mock_chain,
    mock_step,
)
from agentorchestrator.testing.agent_test_suite import (
    AgentTestSuite,
    TestConfig,
    TestResult,
    generate_test_suite,
    testable,
)

__all__ = [
    # Mocks
    "MockAgent",
    "MockAgentResult",
    "mock_step",
    "mock_chain",
    "MockMiddleware",
    # Fixtures
    "IsolatedOrchestrator",
    "create_test_context",
    "create_test_forge",
    "sample_chain_request",
    # Assertions
    "assert_step_completed",
    "assert_step_failed",
    "assert_context_has",
    "assert_chain_valid",
    # Agent Test Suite
    "AgentTestSuite",
    "TestConfig",
    "TestResult",
    "generate_test_suite",
    "testable",
]
