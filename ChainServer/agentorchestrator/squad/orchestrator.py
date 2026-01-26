"""
Multi-Agent Orchestrator for the Squad module.

Provides the main orchestration layer that manages multiple agents,
routes requests via classification, and maintains conversation context.
"""

import logging
import time
from dataclasses import asdict, fields, replace
from typing import Optional, Any, AsyncIterable

from agentorchestrator.squad.agents.base import Agent, AgentStreamResponse
from agentorchestrator.squad.classifiers.base import Classifier
from agentorchestrator.squad.classifiers.llm_gateway import LLMGatewayClassifier
from agentorchestrator.squad.storage.base import ChatStorage
from agentorchestrator.squad.storage.memory import InMemoryChatStorage
from agentorchestrator.core.event_bus import Event, get_event_bus
from agentorchestrator.squad.types import (
    ConversationMessage,
    ParticipantRole,
    ClassifierResult,
    AgentResponse,
    AgentProcessingResult,
    SquadConfig,
)

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """
    Multi-Agent Orchestrator that manages agents and routes requests.

    This is the main entry point for the Squad module. It:
    - Registers and manages multiple agents
    - Classifies user intents to select appropriate agents
    - Routes requests to selected agents
    - Maintains conversation history
    - Supports streaming and non-streaming responses

    Example:
        ```python
        from agentorchestrator.squad import MultiAgentOrchestrator
        from agentorchestrator.squad.agents import LLMGatewayAgent, LLMGatewayAgentOptions
        from agentorchestrator.squad.classifiers import LLMGatewayClassifier
        from agentorchestrator.services.llm_gateway import init_default_llm_client

        # Initialize LLM client
        init_default_llm_client(
            server_url="https://llm-gateway/v1/chat/completions",
            oauth_endpoint="https://auth/token",
            client_id="...",
            client_secret="...",
        )

        # Create agents
        tech_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="TechAgent",
            description="Handles technical programming questions",
        ))
        general_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="GeneralAgent",
            description="Handles general questions",
        ))

        # Create orchestrator
        orchestrator = MultiAgentOrchestrator(
            classifier=LLMGatewayClassifier(),
        )
        orchestrator.add_agent(tech_agent)
        orchestrator.add_agent(general_agent)
        orchestrator.set_default_agent(general_agent)

        # Route request
        response = await orchestrator.route_request(
            user_input="How do I optimize Python code?",
            user_id="user-123",
            session_id="session-456",
        )
        print(response.output.get_text())
        ```
    """

    def __init__(
        self,
        config: Optional[SquadConfig] = None,
        storage: Optional[ChatStorage] = None,
        classifier: Optional[Classifier] = None,
        default_agent: Optional[Agent] = None,
        event_bus=None,
    ):
        """
        Initialize the orchestrator.

        Args:
            config: Orchestrator configuration
            storage: Chat storage backend (uses InMemory if None)
            classifier: Intent classifier (uses LLMGatewayClassifier if None)
            default_agent: Fallback agent when classification fails
        """
        # Configuration
        self.config = config or SquadConfig()

        # Storage
        self.storage = storage or InMemoryChatStorage()

        # Classifier
        self.classifier = classifier or LLMGatewayClassifier()

        # Agents
        self.agents: dict[str, Agent] = {}
        self.default_agent = default_agent

        # Execution tracking
        self.execution_times: dict[str, float] = {}

        # Event bus (shared with core) for streaming telemetry
        self.event_bus = event_bus or get_event_bus(prefer_redis=True)

    def add_agent(self, agent: Agent) -> None:
        """
        Register an agent with the orchestrator.

        Args:
            agent: Agent to register

        Raises:
            ValueError: If agent with same ID already exists
        """
        if agent.id in self.agents:
            raise ValueError(f"Agent with ID '{agent.id}' already exists")

        self.agents[agent.id] = agent
        self.classifier.set_agents(self.agents)
        logger.info(f"Registered agent: {agent.name} (id={agent.id})")

    def remove_agent(self, agent_id: str) -> bool:
        """
        Remove an agent from the orchestrator.

        Args:
            agent_id: ID of agent to remove

        Returns:
            True if agent was removed
        """
        if agent_id in self.agents:
            del self.agents[agent_id]
            self.classifier.set_agents(self.agents)
            logger.info(f"Removed agent: {agent_id}")
            return True
        return False

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """
        Get an agent by ID.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent or None if not found
        """
        return self.agents.get(agent_id)

    def get_all_agents(self) -> dict[str, dict[str, str]]:
        """
        Get info about all registered agents.

        Returns:
            Dict mapping agent IDs to their name/description
        """
        return {
            agent_id: {
                "name": agent.name,
                "description": agent.description
            }
            for agent_id, agent in self.agents.items()
        }

    def set_default_agent(self, agent: Agent) -> None:
        """
        Set the default fallback agent.

        Args:
            agent: Agent to use when classification fails
        """
        self.default_agent = agent

    async def classify_request(
        self,
        user_input: str,
        user_id: str,
        session_id: str,
    ) -> ClassifierResult:
        """
        Classify user input to determine appropriate agent.

        Args:
            user_input: User's input text
            user_id: User identifier
            session_id: Session identifier

        Returns:
            ClassifierResult with selected agent and confidence
        """
        try:
            # Fetch conversation history for context
            chat_history = await self.storage.fetch_all_chats(user_id, session_id) or []

            # Classify
            result = await self._measure_execution_time(
                "Classification",
                lambda: self.classifier.classify(user_input, chat_history)
            )

            if self.config.LOG_CLASSIFIER_OUTPUT:
                self._log_classification(user_input, result)

            # Fall back to default if needed
            if not result.selected_agent:
                if self.config.USE_DEFAULT_AGENT_IF_NONE_IDENTIFIED and self.default_agent:
                    result = ClassifierResult(
                        selected_agent=self.default_agent,
                        confidence=0.0
                    )
                    logger.info("Using default agent (classification returned None)")

            return result

        except Exception as e:
            logger.error(f"Classification error: {e}")
            # Return default agent on error
            if self.default_agent:
                return ClassifierResult(
                    selected_agent=self.default_agent,
                    confidence=0.0
                )
            return ClassifierResult(selected_agent=None, confidence=0.0)

    async def dispatch_to_agent(
        self,
        user_input: str,
        user_id: str,
        session_id: str,
        classifier_result: ClassifierResult,
        additional_params: Optional[dict[str, Any]] = None,
    ) -> ConversationMessage:
        """
        Dispatch request to the selected agent.

        Args:
            user_input: User's input
            user_id: User identifier
            session_id: Session identifier
            classifier_result: Classification result
            additional_params: Optional parameters

        Returns:
            Agent's response message
        """
        if not classifier_result.selected_agent:
            return ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": self.config.NO_SELECTED_AGENT_MESSAGE}]
            )

        agent = classifier_result.selected_agent

        # Fetch agent's chat history
        agent_history = await self.storage.fetch_chat(
            user_id, session_id, agent.id
        )

        if self.config.LOG_AGENT_CHAT:
            logger.debug(f"Agent {agent.name} history: {len(agent_history)} messages")

        # Process request
        response = await self._measure_execution_time(
            f"Agent: {agent.name}",
            lambda: agent.process_request(
                user_input,
                user_id,
                session_id,
                agent_history,
                additional_params
            )
        )

        return response

    async def route_request(
        self,
        user_input: str,
        user_id: str,
        session_id: str,
        additional_params: Optional[dict[str, Any]] = None,
        stream_response: bool = False,
    ) -> AgentResponse:
        """
        Route a user request to the appropriate agent.

        This is the main entry point for processing user requests.
        It classifies the intent, routes to the right agent,
        and manages conversation storage.

        Args:
            user_input: User's input text
            user_id: User identifier
            session_id: Session identifier
            additional_params: Optional parameters
            stream_response: Whether to stream the response

        Returns:
            AgentResponse with metadata and output
        """
        self.execution_times.clear()

        try:
            # Step 1: Classify
            classifier_result = await self.classify_request(
                user_input, user_id, session_id
            )

            # Step 2: Check if we have an agent
            if not classifier_result.selected_agent:
                return AgentResponse(
                    metadata=self._create_metadata(
                        None, user_input, user_id, session_id, additional_params
                    ),
                    output=ConversationMessage(
                        role=ParticipantRole.ASSISTANT.value,
                        content=[{"text": self.config.NO_SELECTED_AGENT_MESSAGE}]
                    ),
                    streaming=False
                )

            # Step 3: Dispatch to agent
            agent = classifier_result.selected_agent
            agent_response = await self.dispatch_to_agent(
                user_input, user_id, session_id,
                classifier_result, additional_params
            )

            # Step 4: Save conversation
            # Save user message
            await self._save_message(
                ConversationMessage(
                    role=ParticipantRole.USER.value,
                    content=[{"text": user_input}]
                ),
                user_id, session_id, agent
            )

            # Handle streaming vs non-streaming
            if agent.is_streaming_enabled() and stream_response:
                # Return streaming response
                final_response = await self._process_streaming_response(
                    agent_response, user_id, session_id, agent
                )
            else:
                # Non-streaming
                if isinstance(agent_response, AsyncIterable):
                    # Consume stream to get final message
                    final_response = await self._consume_stream(agent_response)
                else:
                    final_response = agent_response

                # Save assistant message
                await self._save_message(final_response, user_id, session_id, agent)

            # Step 5: Log execution times
            if self.config.LOG_EXECUTION_TIMES:
                self._log_execution_times()

            return AgentResponse(
                metadata=self._create_metadata(
                    classifier_result, user_input, user_id, session_id, additional_params
                ),
                output=final_response,
                streaming=agent.is_streaming_enabled() and stream_response
            )

        except Exception as e:
            logger.error(f"Routing error: {e}")
            return AgentResponse(
                metadata=self._create_metadata(
                    None, user_input, user_id, session_id, additional_params
                ),
                output=ConversationMessage(
                    role=ParticipantRole.ASSISTANT.value,
                    content=[{"text": self.config.GENERAL_ROUTING_ERROR_MSG_MESSAGE}]
                ),
                streaming=False
            )

    async def _process_streaming_response(
        self,
        response: AsyncIterable,
        user_id: str,
        session_id: str,
        agent: Agent,
    ) -> ConversationMessage:
        """Process a streaming response and save the final message."""
        final_message = None
        accumulated_chunks: list[str] = []
        async for chunk in response:
            if isinstance(chunk, AgentStreamResponse):
                if chunk.text:
                    accumulated_chunks.append(chunk.text)
                    await self._emit_event(
                        "AgentTokenChunk",
                        agent.id,
                        user_id,
                        session_id,
                        payload={"text": chunk.text},
                    )
                if chunk.final_message:
                    final_message = chunk.final_message

        if not final_message and accumulated_chunks:
            final_message = ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": "".join(accumulated_chunks)}]
            )

        if final_message:
            await self._save_message(final_message, user_id, session_id, agent)
            await self._emit_event(
                "AgentStreamCompleted",
                agent.id,
                user_id,
                session_id,
                payload={"text": final_message.content[0].get("text", "") if final_message.content else ""},
            )
            return final_message

        return ConversationMessage(
            role=ParticipantRole.ASSISTANT.value,
            content=[{"text": ""}]
        )

    async def _consume_stream(
        self,
        response: AsyncIterable
    ) -> ConversationMessage:
        """Consume a stream to get the final message."""
        final_message = None
        accumulated_chunks: list[str] = []
        async for chunk in response:
            if isinstance(chunk, AgentStreamResponse):
                if chunk.text:
                    accumulated_chunks.append(chunk.text)
                    await self._emit_event(
                        "AgentTokenChunk",
                        None,
                        None,
                        None,
                        payload={"text": chunk.text},
                    )
                if chunk.final_message:
                    final_message = chunk.final_message

        if final_message:
            return final_message

        if accumulated_chunks:
            msg = ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": "".join(accumulated_chunks)}]
            )
            await self._emit_event(
                "AgentStreamCompleted",
                agent_id=None,
                user_id=None,
                session_id=None,
                payload={"text": msg.content[0].get("text", "")},
            )
            return msg

        return ConversationMessage(
            role=ParticipantRole.ASSISTANT.value,
            content=[{"text": ""}]
        )

    async def _save_message(
        self,
        message: ConversationMessage,
        user_id: str,
        session_id: str,
        agent: Agent
    ) -> None:
        """Save a message to storage if agent allows it."""
        if agent and agent.save_chat:
            await self.storage.save_chat_message(
                user_id, session_id, agent.id, message,
                self.config.MAX_MESSAGE_PAIRS_PER_AGENT
            )

    def _create_metadata(
        self,
        classifier_result: Optional[ClassifierResult],
        user_input: str,
        user_id: str,
        session_id: str,
        additional_params: Optional[dict]
    ) -> AgentProcessingResult:
        """Create processing metadata."""
        metadata = AgentProcessingResult(
            user_input=user_input,
            agent_id="no_agent_selected",
            agent_name="No Agent",
            user_id=user_id,
            session_id=session_id,
            additional_params=additional_params or {}
        )

        if classifier_result and classifier_result.selected_agent:
            metadata.agent_id = classifier_result.selected_agent.id
            metadata.agent_name = classifier_result.selected_agent.name
        else:
            metadata.additional_params["error_type"] = "classification_failed"

        return metadata

    async def _emit_event(
        self,
        event_type: str,
        agent_id: str | None,
        user_id: str | None,
        session_id: str | None,
        payload: dict | None = None,
    ) -> None:
        """Publish agent streaming/telemetry events."""
        if not self.event_bus:
            return
        try:
            await self.event_bus.publish(
                Event(
                    type=event_type,
                    payload=payload or {},
                    step=agent_id,
                    run_id=session_id,
                    metadata={
                        "agent_id": agent_id,
                        "user_id": user_id,
                        "session_id": session_id,
                    },
                )
            )
        except Exception:
            # Best effort; do not break the flow
            pass

    async def _measure_execution_time(
        self,
        name: str,
        fn
    ) -> Any:
        """Measure and record execution time."""
        if not self.config.LOG_EXECUTION_TIMES:
            return await fn()

        start = time.time()
        try:
            result = await fn()
            duration = time.time() - start
            self.execution_times[name] = duration
            return result
        except Exception as e:
            self.execution_times[name] = time.time() - start
            raise

    def _log_classification(
        self,
        user_input: str,
        result: ClassifierResult
    ) -> None:
        """Log classification result."""
        agent_name = result.selected_agent.name if result.selected_agent else "None"
        logger.info(
            f"Classification: input='{user_input[:50]}...' "
            f"agent={agent_name} confidence={result.confidence:.2f}"
        )

    def _log_execution_times(self) -> None:
        """Log all execution times."""
        for name, duration in self.execution_times.items():
            logger.info(f"Execution time - {name}: {duration:.3f}s")

    async def get_chat_history(
        self,
        user_id: str,
        session_id: str,
        agent_id: Optional[str] = None
    ) -> list[ConversationMessage]:
        """
        Get chat history.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Optional agent ID (returns all if None)

        Returns:
            List of conversation messages
        """
        if agent_id:
            return await self.storage.fetch_chat(user_id, session_id, agent_id)
        return await self.storage.fetch_all_chats(user_id, session_id)

    async def clear_chat_history(
        self,
        user_id: str,
        session_id: str,
        agent_id: Optional[str] = None
    ) -> bool:
        """
        Clear chat history.

        Args:
            user_id: User identifier
            session_id: Session identifier
            agent_id: Optional agent ID (clears all if None)

        Returns:
            True if cleared successfully
        """
        return await self.storage.clear_chat(user_id, session_id, agent_id)
