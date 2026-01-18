"""
Multi-Agent Squad Module for AgentOrchestrator.

Provides a native multi-agent orchestration system that works with
the corporate LLM Gateway (OAuth-enabled), bypassing direct API calls
to Anthropic/OpenAI.

This module follows the patterns of AWS Agent Squad but is built to work
behind corporate proxy with your existing LLMGatewayClient.

Key Components:
    - MultiAgentOrchestrator: Main orchestrator for managing agents and routing
    - LLMGatewayAgent: Agent that uses LLMGatewayClient for inference
    - SupervisorAgent: Coordinates a team of specialist agents
    - LLMGatewayClassifier: Intent classifier using LLMGatewayClient
    - ChatStorage: Conversation persistence (InMemory, Redis)

Example:
    ```python
    from agentorchestrator.squad import (
        MultiAgentOrchestrator,
        LLMGatewayAgent,
        LLMGatewayAgentOptions,
        SupervisorAgent,
        SupervisorAgentOptions,
        LLMGatewayClassifier,
    )
    from agentorchestrator.services.llm_gateway import init_default_llm_client

    # Initialize LLM client (uses your corporate gateway)
    init_default_llm_client(
        server_url="https://llm-gateway.corp.com/v1/chat/completions",
        oauth_endpoint="https://auth.corp.com/token",
        client_id="your_client_id",
        client_secret="your_client_secret",
        model_name="claude-sonnet-4",
    )

    # Create specialist agents
    tech_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
        name="TechAgent",
        description="Handles technical programming questions",
        system_prompt="You are a helpful technical assistant.",
    ))

    finance_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
        name="FinanceAgent",
        description="Handles financial and business queries",
        system_prompt="You are a helpful financial analyst.",
    ))

    # Create orchestrator with classifier
    orchestrator = MultiAgentOrchestrator(
        classifier=LLMGatewayClassifier(),
    )
    orchestrator.add_agent(tech_agent)
    orchestrator.add_agent(finance_agent)
    orchestrator.set_default_agent(tech_agent)

    # Route request - classifier picks the right agent
    response = await orchestrator.route_request(
        user_input="How do I optimize my Python code?",
        user_id="user-123",
        session_id="session-456",
    )
    print(response.output.get_text())
    ```

For team coordination with SupervisorAgent:
    ```python
    # Create supervisor that coordinates the team
    lead_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
        name="Supervisor",
        description="Coordinates team to answer complex questions",
    ))

    supervisor = SupervisorAgent(SupervisorAgentOptions(
        name="Supervisor",
        description="Coordinates team to answer complex questions",
        lead_agent=lead_agent,
        team=[tech_agent, finance_agent],
        trace=True,  # Enable logging
    ))

    # Use supervisor directly or add to orchestrator
    orchestrator.add_agent(supervisor)
    ```
"""

# Core orchestrator
from agentorchestrator.squad.orchestrator import MultiAgentOrchestrator

# Agents
from agentorchestrator.squad.agents import (
    Agent,
    AgentOptions,
    AgentStreamResponse,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
    SupervisorAgent,
    SupervisorAgentOptions,
)

# Classifiers
from agentorchestrator.squad.classifiers import (
    Classifier,
    LLMGatewayClassifier,
    LLMGatewayClassifierOptions,
)

# Storage
from agentorchestrator.squad.storage import (
    ChatStorage,
    InMemoryChatStorage,
    RedisChatStorage,
)

# Types
from agentorchestrator.squad.types import (
    ConversationMessage,
    TimestampedMessage,
    ClassifierResult,
    AgentResponse,
    AgentProcessingResult,
    SquadConfig,
    ParticipantRole,
    AgentTool,
    AgentTools,
)

__all__ = [
    # Orchestrator
    "MultiAgentOrchestrator",
    # Agents
    "Agent",
    "AgentOptions",
    "AgentStreamResponse",
    "LLMGatewayAgent",
    "LLMGatewayAgentOptions",
    "SupervisorAgent",
    "SupervisorAgentOptions",
    # Classifiers
    "Classifier",
    "LLMGatewayClassifier",
    "LLMGatewayClassifierOptions",
    # Storage
    "ChatStorage",
    "InMemoryChatStorage",
    "RedisChatStorage",
    # Types
    "ConversationMessage",
    "TimestampedMessage",
    "ClassifierResult",
    "AgentResponse",
    "AgentProcessingResult",
    "SquadConfig",
    "ParticipantRole",
    "AgentTool",
    "AgentTools",
]
