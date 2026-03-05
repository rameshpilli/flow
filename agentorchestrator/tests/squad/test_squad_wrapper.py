"""Tests for Squad wrapper class."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agentorchestrator.squad import (
    Squad,
    SquadOptions,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)
from agentorchestrator.squad.types import ConversationMessage, ParticipantRole


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate_async = AsyncMock(return_value="Mock response")
    client._is_configured = MagicMock(return_value=True)
    return client


@pytest.fixture
def tech_agent(mock_llm_client):
    """Create a tech specialist agent."""
    return LLMGatewayAgent(LLMGatewayAgentOptions(
        name="TechAgent",
        description="Handles technical questions",
        llm_client=mock_llm_client,
    ))


@pytest.fixture
def finance_agent(mock_llm_client):
    """Create a finance specialist agent."""
    return LLMGatewayAgent(LLMGatewayAgentOptions(
        name="FinanceAgent",
        description="Handles financial questions",
        llm_client=mock_llm_client,
    ))


@pytest.fixture
def supervisor_agent(mock_llm_client):
    """Create a supervisor agent."""
    return LLMGatewayAgent(LLMGatewayAgentOptions(
        name="Supervisor",
        description="Coordinates the team",
        llm_client=mock_llm_client,
    ))


class TestSquadInitialization:
    """Tests for Squad initialization."""

    def test_squad_basic_initialization(self, supervisor_agent, tech_agent, finance_agent):
        """Test basic Squad initialization."""
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent, finance_agent],
        )

        assert squad is not None
        assert squad.options.name == "Squad"
        assert len(squad.agents) == 2

    def test_squad_with_options(self, supervisor_agent, tech_agent):
        """Test Squad with custom options."""
        options = SquadOptions(
            name="ResearchSquad",
            description="Research team",
            trace=True,
            max_concurrent_agents=5,
        )

        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent],
            options=options,
        )

        assert squad.options.name == "ResearchSquad"
        assert squad.options.trace is True
        assert squad.options.max_concurrent_agents == 5

    def test_squad_requires_llm_gateway_agent_supervisor(self, tech_agent):
        """Test that supervisor must be LLMGatewayAgent."""
        # Create a non-LLMGatewayAgent mock
        mock_agent = MagicMock()
        mock_agent.name = "MockAgent"

        with pytest.raises(ValueError, match="supervisor must be a LLMGatewayAgent"):
            Squad(
                supervisor=mock_agent,
                agents=[tech_agent],
            )

    def test_squad_requires_non_empty_agents(self, supervisor_agent):
        """Test that agents list cannot be empty."""
        with pytest.raises(ValueError, match="agents list cannot be empty"):
            Squad(
                supervisor=supervisor_agent,
                agents=[],
            )


class TestSquadOperations:
    """Tests for Squad operations."""

    def test_squad_agents_property(self, supervisor_agent, tech_agent, finance_agent):
        """Test agents property returns team members."""
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent, finance_agent],
        )

        agents = squad.agents
        assert len(agents) == 2
        assert any(a.name == "TechAgent" for a in agents)
        assert any(a.name == "FinanceAgent" for a in agents)

    def test_squad_supervisor_property(self, supervisor_agent, tech_agent):
        """Test supervisor property returns SupervisorAgent."""
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent],
        )

        assert squad.supervisor is not None
        # The internal supervisor is a SupervisorAgent wrapping the lead

    def test_squad_add_agent(self, supervisor_agent, tech_agent, finance_agent):
        """Test adding agent to squad."""
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent],
        )

        initial_count = len(squad.agents)
        squad.add_agent(finance_agent)
        assert len(squad.agents) == initial_count + 1

    def test_squad_remove_agent(self, supervisor_agent, tech_agent, finance_agent):
        """Test removing agent from squad."""
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent, finance_agent],
        )

        result = squad.remove_agent("TechAgent")
        assert result is True
        assert len(squad.agents) == 1

    def test_squad_remove_nonexistent_agent(self, supervisor_agent, tech_agent):
        """Test removing non-existent agent returns False."""
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent],
        )

        result = squad.remove_agent("NonexistentAgent")
        assert result is False

    def test_squad_repr(self, supervisor_agent, tech_agent, finance_agent):
        """Test Squad string representation."""
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent, finance_agent],
        )

        repr_str = repr(squad)
        assert "Squad" in repr_str
        assert "agents=2" in repr_str


class TestSquadRun:
    """Tests for Squad.run() method."""

    @pytest.mark.asyncio
    async def test_squad_run_delegates_to_supervisor(
        self, supervisor_agent, tech_agent, mock_llm_client
    ):
        """Test that run() delegates to supervisor.process_request()."""
        # Create the squad
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent],
        )

        # Mock the internal supervisor's process_request
        mock_response = ConversationMessage(
            role=ParticipantRole.ASSISTANT,
            content=[{"text": "Coordinated response"}],
        )
        squad._supervisor.process_request = AsyncMock(return_value=mock_response)

        result = await squad.run(
            "Test query",
            user_id="user-1",
            session_id="session-1",
        )

        assert result is not None
        squad._supervisor.process_request.assert_called_once()


class TestSquadMetrics:
    """Tests for Squad metrics."""

    def test_squad_get_metrics(self, supervisor_agent, tech_agent):
        """Test get_metrics returns dict."""
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent],
        )

        metrics = squad.get_metrics()
        assert isinstance(metrics, dict)

    def test_squad_reset_metrics(self, supervisor_agent, tech_agent):
        """Test reset_metrics doesn't raise."""
        squad = Squad(
            supervisor=supervisor_agent,
            agents=[tech_agent],
        )

        # Should not raise
        squad.reset_metrics()
