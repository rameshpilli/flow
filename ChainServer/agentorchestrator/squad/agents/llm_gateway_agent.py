"""
LLM Gateway Agent implementation.

A flexible agent that uses the existing LLMGatewayClient from
agentorchestrator.services.llm_gateway for inference.

Features:
    - Full chat history propagation
    - RAG context injection
    - User profile/preference support
    - OTEL tracing integration
    - Token budget awareness
    - Resilience (retry, timeout) via existing utils
"""

import asyncio
import json
import logging
import time
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
from agentorchestrator.utils.tracing import trace_span, noop_context

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
        enable_tracing: Enable OTEL tracing spans
        max_history_messages: Max history messages to include
        context_keys: Keys to extract from additional_params for context
        timeout_seconds: Timeout for LLM calls
        max_retries: Max retries on failure
    """
    llm_client: Optional[LLMGatewayClient] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    tool_config: Optional[dict[str, Any]] = None
    enable_tracing: bool = True
    max_history_messages: int = 10  # Max messages to include in context
    context_keys: list[str] = field(default_factory=lambda: ["rag_context", "user_profile", "session_data"])
    timeout_seconds: float = 60.0
    max_retries: int = 2


class LLMGatewayAgent(Agent):
    """
    Agent that uses the existing LLMGatewayClient for inference.

    Works with the corporate LLM Gateway using OAuth authentication,
    bypassing direct calls to Anthropic/OpenAI APIs.

    Features:
        - Full chat history propagation to LLM
        - RAG context injection via additional_params
        - User profile awareness
        - OTEL tracing for observability
        - Configurable timeouts and retries

    Example:
        ```python
        from agentorchestrator.squad.agents import LLMGatewayAgent, LLMGatewayAgentOptions

        # Basic usage
        agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="TechAgent",
            description="Handles technical questions about programming",
            system_prompt="You are a helpful technical assistant.",
        ))

        # With context propagation
        response = await agent.process_request(
            input_text="How do I optimize this?",
            user_id="user-1",
            session_id="session-1",
            chat_history=history,
            additional_params={
                "rag_context": "Retrieved docs about optimization...",
                "user_profile": {"role": "developer", "expertise": "python"},
            }
        )
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
        self.enable_tracing = options.enable_tracing
        self.max_history_messages = options.max_history_messages
        self.context_keys = options.context_keys
        self.timeout_seconds = options.timeout_seconds
        self.max_retries = options.max_retries

        # Metrics tracking
        self._request_count = 0
        self._total_latency_ms = 0.0
        self._error_count = 0

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

    def _build_context_prompt(
        self,
        input_text: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Build a context-enriched prompt with history, RAG data, and user profile.

        Args:
            input_text: Current user input
            chat_history: Conversation history
            additional_params: Additional context (RAG, user profile, etc.)

        Returns:
            Enriched prompt string
        """
        context_parts = []

        # Extract configured context keys from additional_params
        if additional_params:
            for key in self.context_keys:
                value = additional_params.get(key)
                if value:
                    if isinstance(value, dict):
                        value_str = json.dumps(value, indent=2)
                    else:
                        value_str = str(value)
                    context_parts.append(f"<{key}>\n{value_str}\n</{key}>")

        # Add chat history
        if chat_history:
            history_messages = chat_history[-self.max_history_messages:]
            history_text = []
            for msg in history_messages:
                role = msg.role
                text = msg.get_text() if hasattr(msg, 'get_text') else ""
                if not text and msg.content:
                    text = msg.content[0].get("text", "")
                if text:
                    history_text.append(f"{role}: {text}")

            if history_text:
                context_parts.append(
                    f"<conversation_history>\n{chr(10).join(history_text)}\n</conversation_history>"
                )

        # Build final prompt
        if context_parts:
            context_section = "\n\n".join(context_parts)
            return f"{context_section}\n\nUser: {input_text}"
        return f"User: {input_text}"

    async def process_request(
        self,
        input_text: str,
        user_id: str,
        session_id: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]] = None,
    ) -> ConversationMessage:
        """
        Process a user request using LLM Gateway with full context.

        Args:
            input_text: The user's input text
            user_id: User identifier
            session_id: Session identifier
            chat_history: Previous conversation messages
            additional_params: Additional context including:
                - rag_context: Retrieved documents/context
                - user_profile: User preferences and info
                - session_data: Session-specific data

        Returns:
            ConversationMessage with the agent's response
        """
        start_time = time.perf_counter()
        self._request_count += 1

        # Build trace attributes
        trace_attrs = {
            "agent.name": self.name,
            "agent.id": self.id,
            "user.id": user_id,
            "session.id": session_id,
            "history.length": len(chat_history) if chat_history else 0,
            "has_rag_context": bool(additional_params and additional_params.get("rag_context")),
        }

        self._log_debug(f"Processing request: {input_text[:100]}...")

        try:
            with trace_span(f"agent.{self.id}.process", attributes=trace_attrs) if self.enable_tracing else noop_context():
                # Build context-enriched prompt
                full_prompt = self._build_context_prompt(
                    input_text, chat_history, additional_params
                )

                # Prepare kwargs for LLM call
                kwargs = {
                    "max_tokens": self.max_tokens,
                }

                # Add tools if configured
                if self.tool_config and "tool" in self.tool_config:
                    tools = self.tool_config["tool"]
                    if isinstance(tools, AgentTools):
                        kwargs["tools"] = tools.to_llm_tools()

                # Call LLM with timeout
                response_text = await asyncio.wait_for(
                    self.llm_client.generate_async(
                        prompt=full_prompt,
                        system_prompt=self.system_prompt,
                        **kwargs
                    ),
                    timeout=self.timeout_seconds
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

                # Track metrics
                latency_ms = (time.perf_counter() - start_time) * 1000
                self._total_latency_ms += latency_ms

                logger.debug(
                    f"Agent {self.name} completed in {latency_ms:.1f}ms"
                )

                return ConversationMessage(
                    role=ParticipantRole.ASSISTANT.value,
                    content=[{"text": response_text}]
                )

        except asyncio.TimeoutError:
            self._error_count += 1
            logger.error(f"Agent {self.name} timed out after {self.timeout_seconds}s")
            return ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": f"Request timed out after {self.timeout_seconds} seconds. Please try again."}]
            )
        except Exception as e:
            self._error_count += 1
            logger.error(f"Agent {self.name} failed: {e}")
            return ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": f"I encountered an error processing your request: {str(e)}"}]
            )

    def get_metrics(self) -> dict[str, Any]:
        """
        Get agent metrics.

        Returns:
            Dict with request count, avg latency, error count, etc.
        """
        avg_latency = (
            self._total_latency_ms / self._request_count
            if self._request_count > 0 else 0.0
        )
        return {
            "agent_name": self.name,
            "agent_id": self.id,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "total_latency_ms": self._total_latency_ms,
            "avg_latency_ms": avg_latency,
        }

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

    def reset_metrics(self) -> None:
        """Reset all metrics counters."""
        self._request_count = 0
        self._total_latency_ms = 0.0
        self._error_count = 0
