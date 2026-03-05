"""
Tests for the Multi-Agent Squad module.

These tests verify the core functionality of the squad module
without requiring actual LLM API calls.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agentorchestrator.squad import (
    MultiAgentOrchestrator,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
    SupervisorAgent,
    SupervisorAgentOptions,
    LLMGatewayClassifier,
    LLMGatewayClassifierOptions,
    InMemoryChatStorage,
    ConversationMessage,
    ParticipantRole,
    ClassifierResult,
    SquadConfig,
)


# ═══════════════════════════════════════════════════════════════════════════════
#                         FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate_async = AsyncMock(return_value="Mock LLM response")
    return client


@pytest.fixture
def storage():
    """Create in-memory storage."""
    return InMemoryChatStorage()


@pytest.fixture
def tech_agent(mock_llm_client):
    """Create a tech agent with mock LLM."""
    agent = LLMGatewayAgent(LLMGatewayAgentOptions(
        name="TechAgent",
        description="Handles technical programming questions",
        llm_client=mock_llm_client,
    ))
    return agent


@pytest.fixture
def finance_agent(mock_llm_client):
    """Create a finance agent with mock LLM."""
    agent = LLMGatewayAgent(LLMGatewayAgentOptions(
        name="FinanceAgent",
        description="Handles financial queries",
        llm_client=mock_llm_client,
    ))
    return agent


@pytest.fixture
def classifier(mock_llm_client):
    """Create a classifier with mock LLM."""
    classifier = LLMGatewayClassifier(
        LLMGatewayClassifierOptions(llm_client=mock_llm_client)
    )
    return classifier


# ═══════════════════════════════════════════════════════════════════════════════
#                         STORAGE TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestInMemoryChatStorage:
    """Tests for InMemoryChatStorage."""

    @pytest.mark.asyncio
    async def test_save_and_fetch_message(self, storage):
        """Test saving and fetching a message."""
        message = ConversationMessage(
            role=ParticipantRole.USER.value,
            content=[{"text": "Hello"}]
        )

        # Save
        result = await storage.save_chat_message(
            "user-1", "session-1", "agent-1", message
        )
        assert result is True

        # Fetch
        messages = await storage.fetch_chat("user-1", "session-1", "agent-1")
        assert len(messages) == 1
        assert messages[0].get_text() == "Hello"

    @pytest.mark.asyncio
    async def test_save_multiple_messages(self, storage):
        """Test saving multiple messages."""
        msg1 = ConversationMessage(
            role=ParticipantRole.USER.value,
            content=[{"text": "Hello"}]
        )
        msg2 = ConversationMessage(
            role=ParticipantRole.ASSISTANT.value,
            content=[{"text": "Hi there!"}]
        )

        await storage.save_chat_messages(
            "user-1", "session-1", "agent-1", [msg1, msg2]
        )

        messages = await storage.fetch_chat("user-1", "session-1", "agent-1")
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_fetch_all_chats(self, storage):
        """Test fetching all chats across agents."""
        msg1 = ConversationMessage(
            role=ParticipantRole.USER.value,
            content=[{"text": "Tech question"}]
        )
        msg2 = ConversationMessage(
            role=ParticipantRole.USER.value,
            content=[{"text": "Finance question"}]
        )

        await storage.save_chat_message("user-1", "session-1", "tech-agent", msg1)
        await storage.save_chat_message("user-1", "session-1", "finance-agent", msg2)

        all_messages = await storage.fetch_all_chats("user-1", "session-1")
        assert len(all_messages) == 2

    @pytest.mark.asyncio
    async def test_clear_chat(self, storage):
        """Test clearing chat history."""
        msg = ConversationMessage(
            role=ParticipantRole.USER.value,
            content=[{"text": "Hello"}]
        )

        await storage.save_chat_message("user-1", "session-1", "agent-1", msg)
        await storage.clear_chat("user-1", "session-1", "agent-1")

        messages = await storage.fetch_chat("user-1", "session-1", "agent-1")
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_trim_conversation(self, storage):
        """Test conversation trimming."""
        for i in range(10):
            msg = ConversationMessage(
                role=ParticipantRole.USER.value if i % 2 == 0 else ParticipantRole.ASSISTANT.value,
                content=[{"text": f"Message {i}"}]
            )
            await storage.save_chat_message(
                "user-1", "session-1", "agent-1", msg, max_history_size=4
            )

        messages = await storage.fetch_chat("user-1", "session-1", "agent-1")
        assert len(messages) <= 4


# ═══════════════════════════════════════════════════════════════════════════════
#                         AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestLLMGatewayAgent:
    """Tests for LLMGatewayAgent."""

    def test_agent_initialization(self, tech_agent):
        """Test agent initializes correctly."""
        assert tech_agent.name == "TechAgent"
        assert tech_agent.id == "techagent"
        assert "technical" in tech_agent.description.lower()

    def test_agent_id_generation(self):
        """Test agent ID generation from name."""
        from agentorchestrator.squad.agents.base import Agent

        assert Agent.generate_key_from_name("Tech Agent") == "tech-agent"
        assert Agent.generate_key_from_name("Finance & Trading") == "finance-trading"  # & is removed, spaces collapse to single hyphen
        assert Agent.generate_key_from_name("AI Assistant 2.0") == "ai-assistant-20"

    @pytest.mark.asyncio
    async def test_agent_process_request(self, tech_agent, mock_llm_client):
        """Test agent processes request correctly."""
        mock_llm_client.generate_async.return_value = "Here's how to optimize Python code..."

        response = await tech_agent.process_request(
            input_text="How do I optimize Python?",
            user_id="user-1",
            session_id="session-1",
            chat_history=[],
        )

        assert response.role == ParticipantRole.ASSISTANT.value
        assert "optimize" in response.get_text().lower()
        mock_llm_client.generate_async.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
#                         CLASSIFIER TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestLLMGatewayClassifier:
    """Tests for LLMGatewayClassifier."""

    def test_classifier_initialization(self, classifier):
        """Test classifier initializes correctly."""
        assert classifier.llm_client is not None

    def test_set_agents(self, classifier, tech_agent, finance_agent):
        """Test setting agents for classification."""
        classifier.set_agents({
            tech_agent.id: tech_agent,
            finance_agent.id: finance_agent,
        })

        assert "techagent" in classifier.agent_descriptions
        assert "financeagent" in classifier.agent_descriptions

    @pytest.mark.asyncio
    async def test_classify_request(self, classifier, tech_agent, mock_llm_client):
        """Test classification of user input."""
        classifier.set_agents({tech_agent.id: tech_agent})

        # Mock LLM response
        mock_llm_client.generate_async.return_value = """
selected_agent: techagent
confidence: 0.95
"""

        result = await classifier.classify(
            input_text="How do I optimize Python?",
            chat_history=[]
        )

        assert result.selected_agent == tech_agent
        assert result.confidence == 0.95

    def test_parse_classification_response(self, classifier, tech_agent):
        """Test parsing of classification response."""
        classifier.set_agents({tech_agent.id: tech_agent})

        response = """
selected_agent: techagent
confidence: 0.85
"""
        result = classifier.parse_classification_response(response)

        assert result.selected_agent == tech_agent
        assert result.confidence == 0.85

    def test_parse_unknown_agent(self, classifier):
        """Test parsing when agent is unknown."""
        response = """
selected_agent: unknown
confidence: 0.3
"""
        result = classifier.parse_classification_response(response)

        assert result.selected_agent is None
        assert result.confidence == 0.3


# ═══════════════════════════════════════════════════════════════════════════════
#                         ORCHESTRATOR TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultiAgentOrchestrator:
    """Tests for MultiAgentOrchestrator."""

    def test_orchestrator_initialization(self, classifier, storage):
        """Test orchestrator initializes correctly."""
        orchestrator = MultiAgentOrchestrator(
            classifier=classifier,
            storage=storage,
        )

        assert orchestrator.classifier == classifier
        assert orchestrator.storage == storage
        assert len(orchestrator.agents) == 0

    def test_add_agent(self, classifier, storage, tech_agent):
        """Test adding an agent."""
        orchestrator = MultiAgentOrchestrator(
            classifier=classifier,
            storage=storage,
        )

        orchestrator.add_agent(tech_agent)

        assert tech_agent.id in orchestrator.agents
        assert orchestrator.get_agent(tech_agent.id) == tech_agent

    def test_add_duplicate_agent_raises(self, classifier, storage, tech_agent):
        """Test adding duplicate agent raises error."""
        orchestrator = MultiAgentOrchestrator(
            classifier=classifier,
            storage=storage,
        )

        orchestrator.add_agent(tech_agent)

        with pytest.raises(ValueError, match="already exists"):
            orchestrator.add_agent(tech_agent)

    def test_set_default_agent(self, classifier, storage, tech_agent):
        """Test setting default agent."""
        orchestrator = MultiAgentOrchestrator(
            classifier=classifier,
            storage=storage,
        )

        orchestrator.set_default_agent(tech_agent)
        assert orchestrator.default_agent == tech_agent

    def test_get_all_agents(self, classifier, storage, tech_agent, finance_agent):
        """Test getting all agents info."""
        orchestrator = MultiAgentOrchestrator(
            classifier=classifier,
            storage=storage,
        )

        orchestrator.add_agent(tech_agent)
        orchestrator.add_agent(finance_agent)

        agents_info = orchestrator.get_all_agents()

        assert len(agents_info) == 2
        assert tech_agent.id in agents_info
        assert finance_agent.id in agents_info

    @pytest.mark.asyncio
    async def test_route_request(self, classifier, storage, tech_agent, mock_llm_client):
        """Test routing a request to an agent."""
        orchestrator = MultiAgentOrchestrator(
            classifier=classifier,
            storage=storage,
        )
        orchestrator.add_agent(tech_agent)
        orchestrator.set_default_agent(tech_agent)

        # Mock classifier response
        mock_llm_client.generate_async.side_effect = [
            # Classifier call
            "selected_agent: techagent\nconfidence: 0.9",
            # Agent call
            "Here's how to optimize Python code...",
        ]

        response = await orchestrator.route_request(
            user_input="How do I optimize Python?",
            user_id="user-1",
            session_id="session-1",
        )

        assert response.metadata.agent_id == tech_agent.id
        assert response.streaming is False


# ═══════════════════════════════════════════════════════════════════════════════
#                         SUPERVISOR TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSupervisorAgent:
    """Tests for SupervisorAgent."""

    def test_supervisor_initialization(self, mock_llm_client, tech_agent, finance_agent):
        """Test supervisor initializes correctly."""
        lead_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="Supervisor",
            description="Coordinates team",
            llm_client=mock_llm_client,
        ))

        supervisor = SupervisorAgent(SupervisorAgentOptions(
            name="Supervisor",
            description="Coordinates team",
            lead_agent=lead_agent,
            team=[tech_agent, finance_agent],
        ))

        assert supervisor.name == "Supervisor"
        assert len(supervisor.team) == 2
        assert supervisor.lead_agent == lead_agent

    def test_supervisor_requires_lead_agent(self, tech_agent):
        """Test supervisor requires a lead agent."""
        with pytest.raises(ValueError, match="requires a lead_agent"):
            SupervisorAgent(SupervisorAgentOptions(
                name="Supervisor",
                description="Coordinates team",
                lead_agent=None,
                team=[tech_agent],
            ))

    def test_supervisor_add_agent(self, mock_llm_client, tech_agent, finance_agent):
        """Test adding agent to supervisor team."""
        lead_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="Supervisor",
            description="Coordinates team",
            llm_client=mock_llm_client,
        ))

        supervisor = SupervisorAgent(SupervisorAgentOptions(
            name="Supervisor",
            description="Coordinates team",
            lead_agent=lead_agent,
            team=[tech_agent],
        ))

        supervisor.add_agent(finance_agent)
        assert len(supervisor.team) == 2

    def test_supervisor_remove_agent(self, mock_llm_client, tech_agent, finance_agent):
        """Test removing agent from supervisor team."""
        lead_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="Supervisor",
            description="Coordinates team",
            llm_client=mock_llm_client,
        ))

        supervisor = SupervisorAgent(SupervisorAgentOptions(
            name="Supervisor",
            description="Coordinates team",
            lead_agent=lead_agent,
            team=[tech_agent, finance_agent],
        ))

        result = supervisor.remove_agent("TechAgent")
        assert result is True
        assert len(supervisor.team) == 1


# ═══════════════════════════════════════════════════════════════════════════════
#                         INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSquadIntegration:
    """Integration tests for the full squad workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, mock_llm_client):
        """Test complete workflow from request to response."""
        # Create agents
        tech_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="TechAgent",
            description="Handles technical questions",
            llm_client=mock_llm_client,
        ))

        # Create classifier
        classifier = LLMGatewayClassifier(
            LLMGatewayClassifierOptions(llm_client=mock_llm_client)
        )

        # Create orchestrator
        storage = InMemoryChatStorage()
        orchestrator = MultiAgentOrchestrator(
            classifier=classifier,
            storage=storage,
        )
        orchestrator.add_agent(tech_agent)
        orchestrator.set_default_agent(tech_agent)

        # Mock responses
        mock_llm_client.generate_async.side_effect = [
            "selected_agent: techagent\nconfidence: 0.95",
            "To optimize Python code, you should use list comprehensions...",
        ]

        # Route request
        response = await orchestrator.route_request(
            user_input="How do I optimize Python?",
            user_id="user-1",
            session_id="session-1",
        )

        # Verify response
        assert response.metadata.agent_id == "techagent"
        assert "optimize" in response.output.get_text().lower()

        # Verify chat was saved
        history = await storage.fetch_chat("user-1", "session-1", "techagent")
        assert len(history) == 2  # User message + assistant response
