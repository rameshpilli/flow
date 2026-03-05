"""
AgentOrchestrator LLM Gateway Agent
====================================

This module provides an LLM-powered agent implementation using the corporate
LLM Gateway service for inference.

The LLMGatewayAgent is a fully-featured agent that handles chat history,
RAG context injection, tool calling, and observability through OTEL tracing.
It uses OAuth-authenticated access to the LLM Gateway, bypassing direct calls
to Anthropic/OpenAI APIs.

Classes:
    LLMGatewayAgentOptions: Configuration dataclass extending AgentOptions.
    LLMGatewayAgent: Full agent implementation using LLM Gateway.

Usage:
    from agentorchestrator.squad.agents import LLMGatewayAgent, LLMGatewayAgentOptions

    agent = LLMGatewayAgent(LLMGatewayAgentOptions(
        name="TechAgent",
        description="Handles technical questions",
        system_prompt="You are a helpful technical assistant.",
        temperature=0.7,
    ))

    response = await agent.process_request(
        input_text="How do I optimize this query?",
        user_id="user-1",
        session_id="session-1",
        chat_history=history,
    )

Example:
    >>> from agentorchestrator.squad.agents import LLMGatewayAgent, LLMGatewayAgentOptions
    >>> from agentorchestrator.services.llm_gateway import LLMGatewayClient
    >>>
    >>> # Create with custom LLM client
    >>> client = LLMGatewayClient(base_url="https://llm.company.com")
    >>> options = LLMGatewayAgentOptions(
    ...     name="Research Assistant",
    ...     description="Helps with research tasks",
    ...     llm_client=client,
    ...     system_prompt="You are a research assistant...",
    ...     max_tokens=8192,
    ...     temperature=0.3,
    ... )
    >>> agent = LLMGatewayAgent(options)
    >>>
    >>> # Process with RAG context
    >>> response = await agent.process_request(
    ...     input_text="Summarize the latest findings",
    ...     user_id="researcher-1",
    ...     session_id="research-session",
    ...     chat_history=[],
    ...     additional_params={
    ...         "rag_context": "Retrieved research papers...",
    ...         "user_profile": {"expertise": "ML"},
    ...     }
    ... )

See Also:
    - agentorchestrator.squad.agents.base: Base Agent class.
    - agentorchestrator.services.llm_gateway: LLM Gateway client.
    - agentorchestrator.utils.tracing: OTEL tracing utilities.
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
from agentorchestrator.core.event_bus import Event, get_event_bus
from agentorchestrator.core.event_bus import Event, get_event_bus

logger = logging.getLogger(__name__)


@dataclass
class LLMGatewayAgentOptions(AgentOptions):
    """
    Configuration options for LLMGatewayAgent.

    Extends AgentOptions with LLM-specific settings including model
    parameters, tool configuration, and context management.

    Attributes:
        name (str): Display name of the agent.
        description (str): Description of the agent's capabilities.
        llm_client (LLMGatewayClient | None): Pre-configured LLM client.
            If None, uses the default client from get_default_llm_client().
        system_prompt (str | None): System prompt for the LLM.
            If None, a default prompt is generated from name and description.
        temperature (float): LLM temperature for response randomness.
            Range: 0.0 (deterministic) to 1.0 (creative). Default: 0.7.
        max_tokens (int): Maximum tokens for LLM response. Default: 4096.
        tool_config (dict[str, Any] | None): Configuration for tool calling.
            Should contain "tool" key with AgentTools instance.
        save_chat (bool): Whether to persist chat history. Default: True.
        log_debug (bool): Enable debug logging. Default: False.
        enable_tracing (bool): Enable OTEL tracing spans. Default: True.
        max_history_messages (int): Maximum chat history messages to include
            in the LLM context. Default: 10.
        context_keys (list[str]): Keys to extract from additional_params for
            context injection. Default: ["rag_context", "user_profile", "session_data"].
        timeout_seconds (float): Timeout for LLM API calls. Default: 60.0.
        max_retries (int): Maximum retry attempts on failure. Default: 2.

    Example:
        >>> options = LLMGatewayAgentOptions(
        ...     name="Code Assistant",
        ...     description="Helps with coding tasks",
        ...     system_prompt="You are an expert programmer...",
        ...     temperature=0.2,  # More deterministic for code
        ...     max_tokens=8192,
        ...     max_history_messages=5,
        ...     timeout_seconds=120.0,
        ... )
        >>> agent = LLMGatewayAgent(options)

    See Also:
        AgentOptions: Base configuration options.
        LLMGatewayAgent: Agent that uses these options.
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
    event_bus: Any | None = None


class LLMGatewayAgent(Agent):
    """
    Agent that uses the LLM Gateway service for inference.

    A production-ready agent implementation that integrates with
    corporate LLM Gateway using OAuth authentication. Supports
    full chat history, RAG context injection, tool calling,
    and observability through OTEL tracing.

    Attributes:
        llm_client (LLMGatewayClient): The LLM Gateway client.
        system_prompt (str): System prompt sent to the LLM.
        temperature (float): LLM temperature setting.
        max_tokens (int): Maximum response tokens.
        tool_config (dict | None): Tool calling configuration.
        enable_tracing (bool): Whether OTEL tracing is enabled.
        max_history_messages (int): Max history messages in context.
        context_keys (list[str]): Keys for context extraction.
        timeout_seconds (float): LLM call timeout.
        max_retries (int): Maximum retry attempts.

    Methods:
        process_request(): Process user input with LLM.
        set_system_prompt(): Update the system prompt.
        get_metrics(): Get performance metrics.
        reset_metrics(): Reset all metrics counters.

    Example:
        >>> from agentorchestrator.squad.agents import LLMGatewayAgent, LLMGatewayAgentOptions
        >>>
        >>> # Basic usage
        >>> agent = LLMGatewayAgent(LLMGatewayAgentOptions(
        ...     name="Helper",
        ...     description="General purpose assistant",
        ... ))
        >>>
        >>> response = await agent.process_request(
        ...     input_text="What's the capital of France?",
        ...     user_id="user-1",
        ...     session_id="session-1",
        ...     chat_history=[],
        ... )
        >>> print(response.content[0]["text"])

    With RAG Context:
        >>> response = await agent.process_request(
        ...     input_text="Summarize this document",
        ...     user_id="user-1",
        ...     session_id="session-1",
        ...     chat_history=history,
        ...     additional_params={
        ...         "rag_context": "Document content here...",
        ...         "user_profile": {"role": "analyst"},
        ...     }
        ... )

    With Tools:
        >>> from agentorchestrator.squad.types import AgentTools, AgentTool
        >>>
        >>> def search_db(query: str) -> str:
        ...     return f"Results for: {query}"
        >>>
        >>> tools = AgentTools(tools=[
        ...     AgentTool(
        ...         name="search_db",
        ...         description="Search the database",
        ...         func=search_db,
        ...     )
        ... ])
        >>>
        >>> agent = LLMGatewayAgent(LLMGatewayAgentOptions(
        ...     name="DB Agent",
        ...     description="Database query agent",
        ...     tool_config={"tool": tools},
        ... ))

    See Also:
        Agent: Base class for all agents.
        LLMGatewayAgentOptions: Configuration options.
        LLMGatewayClient: The underlying LLM client.
    """

    def __init__(self, options: LLMGatewayAgentOptions):
        """
        Initialize the LLM Gateway agent.

        Args:
            options (LLMGatewayAgentOptions): Configuration options including
                LLM client, system prompt, model parameters, and behavior settings.

        Example:
            >>> options = LLMGatewayAgentOptions(
            ...     name="Assistant",
            ...     description="Helpful assistant",
            ...     temperature=0.7,
            ... )
            >>> agent = LLMGatewayAgent(options)
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
        self.event_bus = options.event_bus or get_event_bus(prefer_redis=True)
        self.event_bus = options.event_bus or get_event_bus(prefer_redis=True)

        # Metrics tracking
        self._request_count = 0
        self._total_latency_ms = 0.0
        self._error_count = 0

    def _default_system_prompt(self) -> str:
        """
        Generate a default system prompt from agent name and description.

        Returns:
            str: Default system prompt text.
        """
        return f"""You are {self.name}, an AI assistant.

{self.description}

Provide helpful, accurate, and concise responses.
If you don't know something, say so rather than making up information.
"""

    def set_system_prompt(self, prompt: str) -> None:
        """
        Update the system prompt for this agent.

        Args:
            prompt (str): The new system prompt to use for all
                subsequent LLM calls.

        Example:
            >>> agent.set_system_prompt(
            ...     "You are an expert Python developer. "
            ...     "Always provide code examples."
            ... )
        """
        self.system_prompt = prompt

    def _format_chat_history(
        self,
        chat_history: list[ConversationMessage]
    ) -> list[dict[str, str]]:
        """
        Format chat history for the LLM API.

        Args:
            chat_history (list[ConversationMessage]): Conversation messages.

        Returns:
            list[dict[str, str]]: Formatted messages with role and content keys.
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
        Build a context-enriched prompt with history and RAG data.

        Constructs a prompt that includes:
        - Context from additional_params (RAG, user profile, etc.)
        - Relevant chat history
        - The current user input

        Args:
            input_text (str): Current user input.
            chat_history (list[ConversationMessage]): Conversation history.
            additional_params (dict[str, Any] | None): Additional context including
                rag_context, user_profile, session_data, etc.

        Returns:
            str: Context-enriched prompt for the LLM.
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

        Sends the user's input to the LLM Gateway along with:
        - System prompt
        - Chat history (limited by max_history_messages)
        - RAG context and user profile from additional_params
        - Tool definitions if configured

        Args:
            input_text (str): The user's input text to process.
            user_id (str): Unique identifier for the user.
            session_id (str): Unique identifier for the session.
            chat_history (list[ConversationMessage]): Previous conversation messages.
            additional_params (dict[str, Any] | None): Additional context:
                - rag_context: Retrieved documents for RAG
                - user_profile: User preferences and metadata
                - session_data: Session-specific data

        Returns:
            ConversationMessage: The agent's response with role ASSISTANT.

        Raises:
            asyncio.TimeoutError: If LLM call exceeds timeout_seconds.
                Returns a timeout error message instead of raising.

        Example:
            >>> response = await agent.process_request(
            ...     input_text="Explain quantum computing",
            ...     user_id="user-123",
            ...     session_id="session-456",
            ...     chat_history=previous_messages,
            ...     additional_params={
            ...         "rag_context": "Quantum computing uses qubits...",
            ...         "user_profile": {"expertise": "beginner"},
            ...     }
            ... )
            >>> print(response.content[0]["text"])

        See Also:
            get_metrics(): Check performance after processing.
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
        Get performance metrics for this agent.

        Returns:
            dict[str, Any]: Metrics dictionary containing:
                - agent_name: Display name of the agent
                - agent_id: URL-safe identifier
                - request_count: Total requests processed
                - error_count: Number of failed requests
                - total_latency_ms: Cumulative latency in milliseconds
                - avg_latency_ms: Average latency per request

        Example:
            >>> metrics = agent.get_metrics()
            >>> print(f"Processed {metrics['request_count']} requests")
            >>> print(f"Average latency: {metrics['avg_latency_ms']:.1f}ms")
            >>> print(f"Error rate: {metrics['error_count']/metrics['request_count']*100:.1f}%")

        See Also:
            reset_metrics(): Reset all counters to zero.
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

    async def _emit_event(
        self,
        event_type: str,
        user_id: str | None,
        session_id: str | None,
        tool_name: str | None,
        payload: dict | None = None,
    ) -> None:
        """Publish tool/agent events (best-effort, no throw)."""
        if not self.event_bus:
            return
        try:
            await self.event_bus.publish(
                Event(
                    type=event_type,
                    payload=payload or {},
                    step=tool_name,
                    run_id=session_id,
                    metadata={
                        "agent_id": self.id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "tool": tool_name,
                    },
                )
            )
        except Exception:
            pass

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
        Handle tool calls in the LLM response.

        If the LLM response contains tool call JSON, executes the
        specified tools and continues the conversation with results.

        Args:
            response (str): LLM response (may contain tool calls as JSON).
            input_text (str): Original user input.
            user_id (str): User identifier.
            session_id (str): Session identifier.
            chat_history (list[ConversationMessage]): Chat history.
            additional_params (dict[str, Any] | None): Additional parameters.
            recursion_depth (int): Current recursion depth for tool chains.

        Returns:
            str: Final response text after tool execution.

        Note:
            Tool recursion is limited by toolMaxRecursions in tool_config
            (default: 10) to prevent infinite loops.
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
                        await self._emit_event(
                            "ToolCallStarted",
                            user_id,
                            session_id,
                            tool_name,
                            arguments,
                        )
                        if asyncio.iscoroutinefunction(tool.func):
                            result = await tool.func(**arguments)
                        else:
                            result = tool.func(**arguments)
                        tool_results.append(f"{tool_name}: {result}")
                        await self._emit_event(
                            "ToolCallResult",
                            user_id,
                            session_id,
                            tool_name,
                            {"success": True, "result": result},
                        )
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}")
                        tool_results.append(f"{tool_name}: Error - {str(e)}")
                        await self._emit_event(
                            "ToolCallResult",
                            user_id,
                            session_id,
                            tool_name,
                            {"success": False, "error": str(e)},
                        )
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
        """
        Reset all metrics counters to zero.

        Clears request_count, total_latency_ms, and error_count.
        Useful for starting fresh metrics collection after
        configuration changes or periodic reporting.

        Example:
            >>> # Report and reset hourly
            >>> metrics = agent.get_metrics()
            >>> send_to_monitoring(metrics)
            >>> agent.reset_metrics()

        See Also:
            get_metrics(): Retrieve current metrics.
        """
        self._request_count = 0
        self._total_latency_ms = 0.0
        self._error_count = 0