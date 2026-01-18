"""
LLM Gateway Agent implementation.

A flexible agent that uses the existing LLMGatewayClient from
agentorchestrator.services.llm_gateway for inference.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Any, Union, AsyncIterable, Callable, Awaitable

from agentorchestrator.squad.agents.base import Agent, AgentOptions, AgentStreamResponse
from agentorchestrator.squad.types import (
    ConversationMessage,
    ParticipantRole,
    AgentTools,
    AgentTool,
)
from agentorchestrator.services.llm_gateway import (
    LLMGatewayClient,
    get_default_llm_client,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMGatewayAgentOptions(AgentOptions):
    """
    Configuration options for LLMGatewayAgent.

    Attributes:
        name: Display name of the agent
        description: Description of the agent's capabilities
        llm_client: Pre-configured LLMGatewayClient (uses default if None)
        system_prompt: System prompt for the agent
        temperature: LLM temperature (0.0-1.0)
        max_tokens: Maximum tokens for response
        tool_config: Optional tool configuration
        save_chat: Whether to save chat history
        log_debug: Enable debug logging
    """
    llm_client: Optional[LLMGatewayClient] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    tool_config: Optional[dict[str, Any]] = None


class LLMGatewayAgent(Agent):
    """
    Agent that uses the existing LLMGatewayClient for inference.

    Works with the corporate LLM Gateway using OAuth authentication,
    bypassing direct calls to Anthropic/OpenAI APIs.

    Example:
        ```python
        from agentorchestrator.squad.agents import LLMGatewayAgent, LLMGatewayAgentOptions
        from agentorchestrator.services.llm_gateway import LLMGatewayClient

        # Using default client
        agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="TechAgent",
            description="Handles technical questions about programming",
            system_prompt="You are a helpful technical assistant.",
        ))

        # Using custom client
        client = LLMGatewayClient(
            server_url="https://llm-gateway/v1/chat/completions",
            oauth_endpoint="https://auth/token",
            client_id="...",
            client_secret="...",
        )
        agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="FinanceAgent",
            description="Handles financial queries",
            llm_client=client,
        ))
        ```
    """

    def __init__(self, options: LLMGatewayAgentOptions):
        """
        Initialize the agent.

        Args:
            options: Agent configuration options
        """
        super().__init__(options)

        # Use provided client or fall back to default from services/llm_gateway.py
        self.llm_client = options.llm_client or get_default_llm_client()
        if not self.llm_client:
            logger.warning(
                f"No LLMGatewayClient provided for {self.name}. "
                "Agent will run in stub mode."
            )
            self.llm_client = LLMGatewayClient()

        self.system_prompt = options.system_prompt or self._default_system_prompt()
        self.temperature = options.temperature
        self.max_tokens = options.max_tokens
        self.tool_config = options.tool_config

    def _default_system_prompt(self) -> str:
        """Generate default system prompt based on agent name and description."""
        return f"""You are {self.name}, an AI assistant.

{self.description}

Provide helpful, accurate, and concise responses.
If you don't know something, say so rather than making up information.
"""

    def set_system_prompt(self, prompt: str) -> None:
        """
        Set the system prompt.

        Args:
            prompt: New system prompt
        """
        self.system_prompt = prompt

    def _format_chat_history(
        self,
        chat_history: list[ConversationMessage]
    ) -> list[dict[str, str]]:
        """
        Format chat history for LLM API.

        Args:
            chat_history: List of conversation messages

        Returns:
            List of message dicts for LLM API
        """
        messages = []
        for msg in chat_history:
            text = msg.get_text() if hasattr(msg, 'get_text') else ""
            if not text and msg.content:
                text = msg.content[0].get("text", "")
            messages.append({
                "role": msg.role,
                "content": text
            })
        return messages

    async def process_request(
        self,
        input_text: str,
        user_id: str,
        session_id: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]] = None,
    ) -> ConversationMessage:
        """
        Process a user request using LLM Gateway.

        Args:
            input_text: The user's input text
            user_id: User identifier
            session_id: Session identifier
            chat_history: Previous conversation messages
            additional_params: Optional additional parameters

        Returns:
            ConversationMessage with the agent's response
        """
        self._log_debug(f"Processing request: {input_text[:100]}...")

        try:
            # Build the prompt with chat history context
            context = ""
            if chat_history:
                history_text = "\n".join([
                    f"{msg.role}: {msg.get_text() if hasattr(msg, 'get_text') else msg.content[0].get('text', '')}"
                    for msg in chat_history[-10:]  # Last 10 messages for context
                ])
                context = f"\nPrevious conversation:\n{history_text}\n\n"

            full_prompt = f"{context}User: {input_text}"

            # Prepare kwargs for LLM call
            kwargs = {
                "max_tokens": self.max_tokens,
            }

            # Add tools if configured
            if self.tool_config and "tool" in self.tool_config:
                tools = self.tool_config["tool"]
                if isinstance(tools, AgentTools):
                    kwargs["tools"] = tools.to_llm_tools()

            # Call LLM using existing LLMGatewayClient
            response_text = await self.llm_client.generate_async(
                prompt=full_prompt,
                system_prompt=self.system_prompt,
                **kwargs
            )

            self._log_debug(f"Response: {response_text[:200]}...")

            # Handle tool calls if present
            if self.tool_config and "tool" in self.tool_config:
                response_text = await self._handle_tool_calls(
                    response_text,
                    input_text,
                    user_id,
                    session_id,
                    chat_history,
                    additional_params,
                )

            return ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": response_text}]
            )

        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            return ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": f"I encountered an error processing your request: {str(e)}"}]
            )

    async def _handle_tool_calls(
        self,
        response: str,
        input_text: str,
        user_id: str,
        session_id: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]],
        recursion_depth: int = 0,
    ) -> str:
        """
        Handle tool calls in the response.

        Args:
            response: LLM response (may contain tool calls)
            input_text: Original user input
            user_id: User identifier
            session_id: Session identifier
            chat_history: Chat history
            additional_params: Additional parameters
            recursion_depth: Current recursion depth

        Returns:
            Final response text after tool execution
        """
        max_recursions = self.tool_config.get("toolMaxRecursions", 10)

        if recursion_depth >= max_recursions:
            logger.warning(f"Max tool recursions ({max_recursions}) reached")
            return response

        # Try to parse tool calls from response
        try:
            # Check if response looks like tool calls JSON
            if response.strip().startswith("["):
                tool_calls = json.loads(response)
            else:
                # No tool calls, return as-is
                return response
        except json.JSONDecodeError:
            # Not JSON, return as-is
            return response

        # Execute tool calls
        tools = self.tool_config.get("tool")
        if not isinstance(tools, AgentTools):
            return response

        tool_results = []
        for call in tool_calls:
            if not isinstance(call, dict):
                continue

            func_info = call.get("function", {})
            tool_name = func_info.get("name")
            arguments = func_info.get("arguments", {})

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            # Find and execute the tool
            for tool in tools.tools:
                if tool.name == tool_name and tool.func:
                    try:
                        self._log_debug(f"Executing tool: {tool_name}", arguments)
                        if asyncio.iscoroutinefunction(tool.func):
                            result = await tool.func(**arguments)
                        else:
                            result = tool.func(**arguments)
                        tool_results.append(f"{tool_name}: {result}")
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}")
                        tool_results.append(f"{tool_name}: Error - {str(e)}")
                    break

        if tool_results:
            # Continue conversation with tool results
            tool_context = "\n".join(tool_results)
            follow_up_prompt = f"Tool results:\n{tool_context}\n\nOriginal question: {input_text}\n\nPlease provide a response based on the tool results."

            follow_up_response = await self.llm_client.generate_async(
                prompt=follow_up_prompt,
                system_prompt=self.system_prompt,
                max_tokens=self.max_tokens,
            )

            return await self._handle_tool_calls(
                follow_up_response,
                input_text,
                user_id,
                session_id,
                chat_history,
                additional_params,
                recursion_depth + 1,
            )

        return response


# Import asyncio for tool handling
import asyncio
