"""
Supervisor Agent for team coordination.

Implements the "agent-as-tools" architecture, allowing a lead agent
to coordinate a team of specialized agents in parallel.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Any, Union, AsyncIterable

from agentorchestrator.squad.agents.base import Agent, AgentOptions, AgentStreamResponse
from agentorchestrator.squad.agents.llm_gateway_agent import LLMGatewayAgent
from agentorchestrator.squad.storage.base import ChatStorage
from agentorchestrator.squad.storage.memory import InMemoryChatStorage
from agentorchestrator.squad.types import (
    ConversationMessage,
    ParticipantRole,
    TimestampedMessage,
    AgentTools,
    AgentTool,
)

logger = logging.getLogger(__name__)


@dataclass
class SupervisorAgentOptions(AgentOptions):
    """
    Configuration options for SupervisorAgent.

    Attributes:
        name: Display name (inherited from lead_agent if not set)
        description: Description (inherited from lead_agent if not set)
        lead_agent: The agent that coordinates the team (must be LLMGatewayAgent)
        team: List of specialist agents to coordinate
        storage: Chat storage for team memory (uses InMemory if None)
        trace: Enable detailed tracing/logging
        extra_tools: Additional tools for the lead agent
        tool_max_recursions: Max tool call recursions
    """
    lead_agent: Optional[LLMGatewayAgent] = None
    team: list[Agent] = field(default_factory=list)
    storage: Optional[ChatStorage] = None
    trace: bool = False
    extra_tools: Optional[Union[AgentTools, list[AgentTool]]] = None
    tool_max_recursions: int = 40


class SupervisorAgent(Agent):
    """
    Supervisor agent that coordinates a team of specialist agents.

    Implements the "agent-as-tools" pattern where the supervisor can
    delegate tasks to team members in parallel and aggregate responses.

    Features:
        - Parallel Processing: Execute multiple agent queries simultaneously
        - Smart Context Management: Team memory shared across agents
        - Dynamic Delegation: Route subtasks to appropriate specialists

    Example:
        ```python
        from agentorchestrator.squad.agents import (
            SupervisorAgent,
            SupervisorAgentOptions,
            LLMGatewayAgent,
            LLMGatewayAgentOptions,
        )

        # Create specialist agents
        tech_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="TechAgent",
            description="Handles technical programming questions",
        ))
        finance_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="FinanceAgent",
            description="Handles financial queries",
        ))

        # Create lead agent
        lead = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="Supervisor",
            description="Coordinates team to answer user questions",
        ))

        # Create supervisor
        supervisor = SupervisorAgent(SupervisorAgentOptions(
            name="Supervisor",
            description="Coordinates team to answer user questions",
            lead_agent=lead,
            team=[tech_agent, finance_agent],
            trace=True,
        ))

        # Process request
        response = await supervisor.process_request(
            "How do I optimize Python code for a trading algorithm?",
            user_id="user-1",
            session_id="session-1",
            chat_history=[],
        )
        ```
    """

    def __init__(self, options: SupervisorAgentOptions):
        """
        Initialize the supervisor agent.

        Args:
            options: Supervisor configuration options
        """
        # Validate options
        if not options.lead_agent:
            raise ValueError("SupervisorAgent requires a lead_agent")

        if not isinstance(options.lead_agent, LLMGatewayAgent):
            raise ValueError("lead_agent must be a LLMGatewayAgent")

        # Use lead agent's name/description if not provided
        options.name = options.name or options.lead_agent.name
        options.description = options.description or options.lead_agent.description

        super().__init__(options)

        self.lead_agent = options.lead_agent
        self.team = options.team or []
        self.storage = options.storage or InMemoryChatStorage()
        self.trace = options.trace
        self.tool_max_recursions = options.tool_max_recursions

        # Session context (set during process_request)
        self._user_id = ""
        self._session_id = ""
        self._additional_params: Optional[dict] = None

        # Configure supervisor tools
        self._configure_supervisor_tools(options.extra_tools)
        self._configure_prompt()

    def _configure_supervisor_tools(
        self,
        extra_tools: Optional[Union[AgentTools, list[AgentTool]]]
    ) -> None:
        """
        Configure tools available to the lead agent.

        The main tool is 'send_messages' which allows the supervisor
        to delegate tasks to team members.
        """
        # Create the send_messages tool
        send_messages_tool = AgentTool(
            name="send_messages",
            description="Send messages to multiple agents in parallel. Use this to delegate tasks to team members.",
            properties={
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "recipient": {
                                "type": "string",
                                "description": "Agent name to send message to."
                            },
                            "content": {
                                "type": "string",
                                "description": "Message content for the agent."
                            }
                        },
                        "required": ["recipient", "content"]
                    },
                    "description": "Array of messages for different agents.",
                    "minItems": 1
                }
            },
            required=["messages"],
            func=self._send_messages
        )

        # Build tools list
        tools_list = [send_messages_tool]

        # Add extra tools
        if extra_tools:
            if isinstance(extra_tools, AgentTools):
                tools_list.extend(extra_tools.tools)
            else:
                tools_list.extend(extra_tools)

        self.supervisor_tools = AgentTools(tools=tools_list)

        # Configure lead agent with tools
        self.lead_agent.tool_config = {
            "tool": self.supervisor_tools,
            "toolMaxRecursions": self.tool_max_recursions,
        }

    def _configure_prompt(self) -> None:
        """Configure the lead agent's system prompt."""
        # Build agent list string
        agent_list_str = "\n".join(
            f"- {agent.name}: {agent.description}"
            for agent in self.team
        )

        # Build tools string
        tools_str = "\n".join(
            f"- {tool.name}: {tool.description}"
            for tool in self.supervisor_tools.tools
        )

        self.prompt_template = f"""You are {self.name}, a supervisor agent that coordinates a team of specialists.

{self.description}

You can interact with the following team members:
<agents>
{agent_list_str}
</agents>

Available tools:
<tools>
{tools_str}
</tools>

Guidelines:
- Analyze the user's question and determine which agent(s) can help
- Use send_messages to delegate tasks to appropriate team members
- You can contact MULTIPLE agents at the same time for efficiency
- Provide a final answer to the user after receiving all agent responses
- Do not mention agent names to the user - synthesize their responses
- Keep communications with agents concise and focused
- Agents are not aware of each other - you are the intermediary
- If an agent asks for clarification, forward it to the user
- Never make up information - only use what agents provide

Team Memory (previous interactions):
<agents_memory>
{{AGENTS_MEMORY}}
</agents_memory>
"""
        self.lead_agent.set_system_prompt(self.prompt_template)

    async def _send_message_to_agent(
        self,
        agent: Agent,
        content: str,
    ) -> str:
        """
        Send a message to a specific agent.

        Args:
            agent: Target agent
            content: Message content

        Returns:
            Agent's response as string
        """
        try:
            if self.trace:
                logger.info(f"[Supervisor] → {agent.name}: {content[:100]}...")

            # Fetch agent's chat history
            agent_history = []
            if agent.save_chat:
                agent_history = await self.storage.fetch_chat(
                    self._user_id,
                    self._session_id,
                    agent.id
                )

            # Create user message
            user_message = TimestampedMessage(
                role=ParticipantRole.USER.value,
                content=[{"text": content}]
            )

            # Process request
            response = await agent.process_request(
                content,
                self._user_id,
                self._session_id,
                agent_history,
                self._additional_params
            )

            # Handle streaming response
            if agent.is_streaming_enabled() and isinstance(response, AsyncIterable):
                final_text = ""
                async for chunk in response:
                    if isinstance(chunk, AgentStreamResponse):
                        if chunk.final_message:
                            final_text = chunk.final_message.get_text()
                response_text = final_text
            else:
                response_text = response.get_text()

            # Save to storage
            if agent.save_chat:
                assistant_message = TimestampedMessage(
                    role=ParticipantRole.ASSISTANT.value,
                    content=[{"text": response_text}]
                )
                await self.storage.save_chat_messages(
                    self._user_id,
                    self._session_id,
                    agent.id,
                    [user_message, assistant_message]
                )

            if self.trace:
                logger.info(f"[Supervisor] ← {agent.name}: {response_text[:100]}...")

            return f"{agent.name}: {response_text}"

        except Exception as e:
            logger.error(f"Error sending to {agent.name}: {e}")
            return f"{agent.name}: Error - {str(e)}"

    async def _send_messages(self, messages: list[dict[str, str]]) -> str:
        """
        Send messages to multiple agents in parallel.

        This is the main tool used by the supervisor to delegate tasks.

        Args:
            messages: List of {recipient, content} dicts

        Returns:
            Combined responses from all agents
        """
        if self.trace:
            logger.info(f"[Supervisor] Sending to {len(messages)} agent(s)")

        # Create tasks for parallel execution
        tasks = []
        for message in messages:
            recipient = message.get("recipient", "")
            content = message.get("content", "")

            # Find matching agent
            for agent in self.team:
                if agent.name.lower() == recipient.lower():
                    task = asyncio.create_task(
                        self._send_message_to_agent(agent, content)
                    )
                    tasks.append(task)
                    break
            else:
                logger.warning(f"No agent found with name: {recipient}")

        if not tasks:
            return f"No matching agents found for: {[m.get('recipient') for m in messages]}"

        # Execute in parallel
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine responses
        results = []
        for resp in responses:
            if isinstance(resp, Exception):
                results.append(f"Error: {str(resp)}")
            else:
                results.append(str(resp))

        return "\n\n".join(results)

    def _format_agents_memory(
        self,
        agents_history: list[ConversationMessage]
    ) -> str:
        """
        Format agent conversation history for context.

        Args:
            agents_history: All agent messages

        Returns:
            Formatted memory string
        """
        if not agents_history:
            return "(No previous interactions)"

        formatted = []
        for i in range(0, len(agents_history) - 1, 2):
            user_msg = agents_history[i]
            if i + 1 < len(agents_history):
                asst_msg = agents_history[i + 1]
                # Skip messages from self
                asst_text = asst_msg.get_text() if hasattr(asst_msg, 'get_text') else ""
                if self.id not in asst_text:
                    user_text = user_msg.get_text() if hasattr(user_msg, 'get_text') else ""
                    formatted.append(f"User: {user_text}")
                    formatted.append(f"Agent: {asst_text}")

        return "\n".join(formatted) if formatted else "(No previous interactions)"

    def is_streaming_enabled(self) -> bool:
        """Check if lead agent supports streaming."""
        return self.lead_agent.is_streaming_enabled()

    async def process_request(
        self,
        input_text: str,
        user_id: str,
        session_id: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]] = None,
    ) -> Union[ConversationMessage, AsyncIterable[Any]]:
        """
        Process a user request through the supervisor.

        The supervisor will:
        1. Analyze the request
        2. Delegate to appropriate team members
        3. Aggregate responses
        4. Provide final answer

        Args:
            input_text: User's input
            user_id: User identifier
            session_id: Session identifier
            chat_history: Conversation history
            additional_params: Optional parameters

        Returns:
            Final response from supervisor
        """
        # Store session context for tool calls
        self._user_id = user_id
        self._session_id = session_id
        self._additional_params = additional_params

        try:
            # Fetch team memory
            agents_history = await self.storage.fetch_all_chats(user_id, session_id)
            agents_memory = self._format_agents_memory(agents_history)

            # Update prompt with memory
            current_prompt = self.prompt_template.replace(
                "{{AGENTS_MEMORY}}", agents_memory
            )
            self.lead_agent.set_system_prompt(current_prompt)

            if self.trace:
                logger.info(f"[Supervisor] Processing: {input_text[:100]}...")

            # Delegate to lead agent
            return await self.lead_agent.process_request(
                input_text,
                user_id,
                session_id,
                chat_history,
                additional_params
            )

        except Exception as e:
            logger.error(f"Supervisor error: {e}")
            return ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": f"I encountered an error coordinating the team: {str(e)}"}]
            )

    def add_agent(self, agent: Agent) -> None:
        """
        Add an agent to the team.

        Args:
            agent: Agent to add
        """
        self.team.append(agent)
        self._configure_prompt()

    def remove_agent(self, agent_name: str) -> bool:
        """
        Remove an agent from the team.

        Args:
            agent_name: Name of agent to remove

        Returns:
            True if agent was removed
        """
        for i, agent in enumerate(self.team):
            if agent.name.lower() == agent_name.lower():
                self.team.pop(i)
                self._configure_prompt()
                return True
        return False

    def get_team(self) -> list[Agent]:
        """Get list of team agents."""
        return self.team.copy()
