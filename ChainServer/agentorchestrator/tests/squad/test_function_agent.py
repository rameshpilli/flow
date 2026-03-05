"""Tests for FunctionAgent with handoffs."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agentorchestrator.squad import (
    FunctionAgent,
    FunctionAgentOptions,
    HandoffResult,
)


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate_async = AsyncMock(return_value="Mock response")
    client._is_configured = MagicMock(return_value=True)
    return client


class TestFunctionAgentInitialization:
    """Tests for FunctionAgent initialization."""

    def test_initialization_with_handoff_targets(self, mock_llm_client):
        """Test FunctionAgent initializes with handoff targets."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer", "Reviewer"],
        ))

        assert "Writer" in agent.can_handoff_to
        assert "Reviewer" in agent.can_handoff_to
        assert len(agent.can_handoff_to) == 2

    def test_initialization_with_empty_handoff_list(self, mock_llm_client):
        """Test FunctionAgent with no handoff targets."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=[],
        ))

        assert agent.can_handoff_to == []

    def test_initialization_without_handoff_list(self, mock_llm_client):
        """Test FunctionAgent without specifying handoff targets."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
        ))

        assert agent.can_handoff_to == []


class TestFunctionAgentHandoff:
    """Tests for FunctionAgent.handoff() method."""

    @pytest.mark.asyncio
    async def test_valid_handoff(self, mock_llm_client):
        """Test valid handoff to allowed agent."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer"],
        ))

        result = await agent.handoff(
            to_agent="Writer",
            context={"findings": ["item1", "item2"]},
            message="Please write a summary",
        )

        assert isinstance(result, HandoffResult)
        assert result.to_agent == "Writer"
        assert result.from_agent == "Researcher"
        assert result.context["findings"] == ["item1", "item2"]
        assert result.message == "Please write a summary"
        assert agent.has_pending_handoff()

    @pytest.mark.asyncio
    async def test_handoff_to_user_always_allowed(self, mock_llm_client):
        """Test handoff to 'User' is always allowed regardless of can_handoff_to."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=[],  # Empty list - but User should still work
        ))

        result = await agent.handoff(
            to_agent="User",
            context={"result": "done"},
            message="Task complete",
        )

        assert result.to_agent == "User"

    @pytest.mark.asyncio
    async def test_handoff_to_user_case_insensitive(self, mock_llm_client):
        """Test 'user', 'USER', 'User' all work."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=[],
        ))

        # All case variations should work
        for user_variant in ["user", "USER", "User"]:
            agent._pending_handoff = None  # Reset
            result = await agent.handoff(
                to_agent=user_variant,
                context={},
                message="",
            )
            assert result.to_agent == user_variant

    @pytest.mark.asyncio
    async def test_invalid_handoff_raises_error(self, mock_llm_client):
        """Test handoff to disallowed agent raises ValueError."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer"],
        ))

        with pytest.raises(ValueError, match="cannot hand off"):
            await agent.handoff(
                to_agent="UnauthorizedAgent",
                context={},
                message="",
            )

    @pytest.mark.asyncio
    async def test_handoff_callback(self, mock_llm_client):
        """Test on_handoff callback is called."""
        callback_called = []

        async def on_handoff(result: HandoffResult):
            callback_called.append(result)

        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer"],
            on_handoff=on_handoff,
        ))

        await agent.handoff(
            to_agent="Writer",
            context={"data": "test"},
            message="Test message",
        )

        assert len(callback_called) == 1
        assert callback_called[0].to_agent == "Writer"


class TestFunctionAgentPendingHandoff:
    """Tests for pending handoff management."""

    @pytest.mark.asyncio
    async def test_get_pending_handoff_returns_and_clears(self, mock_llm_client):
        """Test get_pending_handoff returns handoff and clears it."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer"],
        ))

        await agent.handoff(
            to_agent="Writer",
            context={},
            message="",
        )

        # First call returns the handoff
        result = agent.get_pending_handoff()
        assert result is not None
        assert result.to_agent == "Writer"

        # Second call returns None (cleared)
        result2 = agent.get_pending_handoff()
        assert result2 is None

    def test_has_pending_handoff_false_initially(self, mock_llm_client):
        """Test has_pending_handoff is False initially."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer"],
        ))

        assert agent.has_pending_handoff() is False

    @pytest.mark.asyncio
    async def test_has_pending_handoff_true_after_handoff(self, mock_llm_client):
        """Test has_pending_handoff is True after handoff."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer"],
        ))

        await agent.handoff(to_agent="Writer", context={}, message="")

        assert agent.has_pending_handoff() is True

    @pytest.mark.asyncio
    async def test_get_pending_clears_has_pending(self, mock_llm_client):
        """Test that get_pending_handoff clears has_pending_handoff."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer"],
        ))

        await agent.handoff(to_agent="Writer", context={}, message="")
        assert agent.has_pending_handoff() is True

        agent.get_pending_handoff()
        assert agent.has_pending_handoff() is False


class TestHandoffResult:
    """Tests for HandoffResult dataclass."""

    def test_handoff_result_repr(self):
        """Test HandoffResult string representation."""
        result = HandoffResult(
            to_agent="Writer",
            context={"findings": ["a", "b"]},
            message="Please write a summary of the research findings.",
            from_agent="Researcher",
        )

        repr_str = repr(result)
        assert "Researcher" in repr_str
        assert "Writer" in repr_str
        assert "findings" in repr_str

    def test_handoff_result_attributes(self):
        """Test HandoffResult has correct attributes."""
        result = HandoffResult(
            to_agent="Writer",
            context={"key": "value"},
            message="Test message",
            from_agent="Researcher",
        )

        assert result.to_agent == "Writer"
        assert result.from_agent == "Researcher"
        assert result.context == {"key": "value"}
        assert result.message == "Test message"


class TestFunctionAgentRepr:
    """Tests for FunctionAgent string representation."""

    def test_repr_without_pending(self, mock_llm_client):
        """Test repr without pending handoff."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer"],
        ))

        repr_str = repr(agent)
        assert "FunctionAgent" in repr_str
        assert "Researcher" in repr_str
        assert "Writer" in repr_str
        assert "pending=False" in repr_str

    @pytest.mark.asyncio
    async def test_repr_with_pending(self, mock_llm_client):
        """Test repr with pending handoff."""
        agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Research agent",
            llm_client=mock_llm_client,
            can_handoff_to=["Writer"],
        ))

        await agent.handoff(to_agent="Writer", context={}, message="")

        repr_str = repr(agent)
        assert "pending=True" in repr_str
