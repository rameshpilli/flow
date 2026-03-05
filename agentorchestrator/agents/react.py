"""
ReAct (Reasoning + Acting) Agent Pattern
=========================================

Implements the industry-standard Thought→Action→Observation loop for AI agents.

The ReAct pattern enables agents to:
1. **Think** - Reason about the current situation and plan next steps
2. **Act** - Execute a tool or action based on reasoning
3. **Observe** - Process the result and update understanding

This creates a powerful feedback loop that allows agents to handle complex,
multi-step tasks with explicit reasoning traces.

References:
    - "ReAct: Synergizing Reasoning and Acting in Language Models" (Yao et al., 2022)
    - https://arxiv.org/abs/2210.03629

Usage:
    from agentorchestrator.agents.react import ReActAgent, ReActConfig
    from agentorchestrator.agents.tools import ToolRegistry

    # Create agent with tools
    tools = ToolRegistry()
    tools.register("search", search_func, description="Search the web")
    tools.register("calculate", calc_func, description="Perform calculations")

    agent = ReActAgent(
        llm_client=llm,
        tools=tools,
        config=ReActConfig(max_iterations=10),
    )

    # Run the agent
    result = await agent.run("What is the population of France divided by 3?")
    print(result.final_answer)
    print(result.thought_trace)  # Full reasoning trace

Example Trace:
    Thought: I need to find the population of France, then divide by 3.
    Action: search("population of France 2024")
    Observation: The population of France is approximately 68 million.
    Thought: Now I have the population. I need to divide 68 million by 3.
    Action: calculate("68000000 / 3")
    Observation: 22666666.67
    Thought: I now have the answer.
    Final Answer: The population of France (68 million) divided by 3 is approximately 22.67 million.
"""

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agentorchestrator.services.llm_gateway import LLMGatewayClient

logger = logging.getLogger(__name__)

__all__ = [
    "ReActAgent",
    "ReActConfig",
    "ReActResult",
    "ReActStep",
    "StepType",
    "Tool",
    "ToolResult",
]


class StepType(str, Enum):
    """Type of step in the ReAct loop."""
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"


@dataclass
class Tool:
    """
    Represents a tool that the ReAct agent can use.

    Attributes:
        name: Unique tool identifier (used in Action: tool_name(...))
        description: What the tool does (shown to LLM)
        func: The function to execute (sync or async)
        parameters: JSON schema for parameters (optional)
        required_params: List of required parameter names
    """
    name: str
    description: str
    func: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=dict)
    required_params: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate tool configuration."""
        if not self.name or not self.name.strip():
            raise ValueError("Tool name cannot be empty")
        if not callable(self.func):
            raise ValueError(f"Tool '{self.name}' func must be callable")


@dataclass
class ToolResult:
    """Result from executing a tool."""
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None
    duration_ms: float = 0.0

    def __str__(self) -> str:
        if self.success:
            return str(self.result)
        return f"Error: {self.error}"


@dataclass
class ReActStep:
    """
    A single step in the ReAct execution trace.

    Attributes:
        step_type: Type of step (thought, action, observation, final_answer)
        content: The content of this step
        tool_name: Tool name if this is an action
        tool_args: Tool arguments if this is an action
        duration_ms: Time taken for this step
    """
    step_type: StepType
    content: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict[str, Any]] = None
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": self.step_type.value,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class ReActResult:
    """
    Result from a ReAct agent execution.

    Attributes:
        success: Whether the agent completed successfully
        final_answer: The final answer (if successful)
        steps: Full trace of thought/action/observation steps
        total_iterations: Number of reasoning iterations
        total_duration_ms: Total execution time
        error: Error message if failed
    """
    success: bool
    final_answer: Optional[str] = None
    steps: list[ReActStep] = field(default_factory=list)
    total_iterations: int = 0
    total_duration_ms: float = 0.0
    error: Optional[str] = None
    run_id: str = field(default_factory=lambda: f"react_{uuid.uuid4().hex[:8]}")

    @property
    def thought_trace(self) -> str:
        """Get a formatted trace of the reasoning process."""
        lines = []
        for step in self.steps:
            prefix = step.step_type.value.capitalize()
            lines.append(f"{prefix}: {step.content}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "final_answer": self.final_answer,
            "steps": [s.to_dict() for s in self.steps],
            "total_iterations": self.total_iterations,
            "total_duration_ms": self.total_duration_ms,
            "error": self.error,
            "run_id": self.run_id,
        }


@dataclass
class ReActConfig:
    """
    Configuration for ReAct agent behavior.

    Attributes:
        max_iterations: Maximum number of thought-action-observation cycles
        max_tokens: Maximum tokens for LLM generation per step
        temperature: LLM sampling temperature
        stop_on_final_answer: Stop immediately when Final Answer is detected
        include_scratchpad: Include previous steps in prompts
        scratchpad_max_steps: Maximum previous steps to include
        timeout_per_action_ms: Timeout for tool execution
        retry_on_parse_error: Retry if LLM output can't be parsed
        max_parse_retries: Maximum parse retries per iteration
    """
    max_iterations: int = 10
    max_tokens: int = 1024
    temperature: float = 0.2
    stop_on_final_answer: bool = True
    include_scratchpad: bool = True
    scratchpad_max_steps: int = 20
    timeout_per_action_ms: int = 30000
    retry_on_parse_error: bool = True
    max_parse_retries: int = 2


# Default ReAct prompt template
REACT_SYSTEM_PROMPT = """You are an AI assistant that uses the ReAct (Reasoning and Acting) framework to solve problems step by step.

You have access to the following tools:
{tools_description}

Use the following format EXACTLY:

Thought: [Your reasoning about what to do next]
Action: tool_name(arg1, arg2, ...)
Observation: [Result from the tool - this will be provided to you]
... (repeat Thought/Action/Observation as needed)
Thought: [Your final reasoning]
Final Answer: [Your final answer to the original question]

Important rules:
1. Always start with a Thought
2. Only use one Action at a time
3. Wait for the Observation before continuing
4. When you have enough information, provide a Final Answer
5. Tool arguments should be valid Python literals (strings in quotes, numbers without)
6. If a tool fails, think about why and try a different approach

Begin!"""

REACT_USER_PROMPT = """Question: {question}

{scratchpad}"""


class ReActAgent:
    """
    ReAct Agent implementing Thought→Action→Observation loop.

    This agent uses an LLM to reason about tasks, select tools to use,
    and process results in a feedback loop until reaching a final answer.

    Example:
        >>> from agentorchestrator.agents.react import ReActAgent, ReActConfig, Tool
        >>> from agentorchestrator.services.llm_gateway import LLMGatewayClient
        >>>
        >>> # Define tools
        >>> def search(query: str) -> str:
        ...     return f"Results for '{query}': ..."
        >>>
        >>> def calculate(expression: str) -> str:
        ...     return str(eval(expression))
        >>>
        >>> # Create agent
        >>> agent = ReActAgent(
        ...     llm_client=LLMGatewayClient.from_env(),
        ...     tools=[
        ...         Tool("search", "Search the web", search),
        ...         Tool("calculate", "Evaluate math expressions", calculate),
        ...     ],
        ... )
        >>>
        >>> # Run
        >>> result = await agent.run("What is 42 * 17?")
        >>> print(result.final_answer)  # "714"
    """

    def __init__(
        self,
        llm_client: "LLMGatewayClient",
        tools: list[Tool] | None = None,
        config: ReActConfig | None = None,
        system_prompt: str | None = None,
        name: str = "ReActAgent",
    ):
        """
        Initialize the ReAct agent.

        Args:
            llm_client: LLM client for generating thoughts/actions
            tools: List of tools the agent can use
            config: Agent configuration
            system_prompt: Custom system prompt (uses default if None)
            name: Agent name for logging
        """
        self.llm_client = llm_client
        self.tools: dict[str, Tool] = {}
        self.config = config or ReActConfig()
        self.system_prompt = system_prompt or REACT_SYSTEM_PROMPT
        self.name = name

        # Register tools
        if tools:
            for tool in tools:
                self.register_tool(tool)

    def register_tool(self, tool: Tool) -> None:
        """
        Register a tool for the agent to use.

        Args:
            tool: Tool to register

        Raises:
            ValueError: If tool with same name already exists
        """
        if tool.name in self.tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self.tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def register_function(
        self,
        name: str,
        func: Callable[..., Any],
        description: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """
        Convenience method to register a function as a tool.

        Args:
            name: Tool name
            func: Function to execute
            description: Tool description
            parameters: Optional parameter schema
        """
        self.register_tool(Tool(
            name=name,
            description=description,
            func=func,
            parameters=parameters or {},
        ))

    def _build_tools_description(self) -> str:
        """Build the tools description for the system prompt."""
        if not self.tools:
            return "No tools available."

        lines = []
        for name, tool in self.tools.items():
            params = ""
            if tool.parameters:
                param_strs = []
                for pname, pinfo in tool.parameters.items():
                    ptype = pinfo.get("type", "any")
                    param_strs.append(f"{pname}: {ptype}")
                params = f"({', '.join(param_strs)})"
            else:
                params = "(...)"

            lines.append(f"- {name}{params}: {tool.description}")

        return "\n".join(lines)

    def _build_scratchpad(self, steps: list[ReActStep]) -> str:
        """Build the scratchpad from previous steps."""
        if not steps or not self.config.include_scratchpad:
            return ""

        # Limit to recent steps
        recent_steps = steps[-self.config.scratchpad_max_steps:]

        lines = []
        for step in recent_steps:
            if step.step_type == StepType.THOUGHT:
                lines.append(f"Thought: {step.content}")
            elif step.step_type == StepType.ACTION:
                lines.append(f"Action: {step.content}")
            elif step.step_type == StepType.OBSERVATION:
                lines.append(f"Observation: {step.content}")

        return "\n".join(lines)

    def _parse_action(self, text: str) -> tuple[str | None, dict[str, Any] | None, str | None]:
        """
        Parse an action from LLM output.

        Returns:
            Tuple of (tool_name, args_dict, raw_action_str) or (None, None, None)
        """
        # Look for Action: tool_name(args)
        action_pattern = r"Action:\s*(\w+)\s*\((.*?)\)"
        match = re.search(action_pattern, text, re.DOTALL)

        if not match:
            return None, None, None

        tool_name = match.group(1)
        args_str = match.group(2).strip()
        raw_action = match.group(0)

        # Parse arguments
        args = {}
        if args_str:
            try:
                # Try to parse as Python literals
                # Handle common cases: "string", 123, True, etc.
                import ast

                # If it looks like keyword args
                if "=" in args_str:
                    # Parse as dict
                    for part in args_str.split(","):
                        if "=" in part:
                            key, val = part.split("=", 1)
                            key = key.strip()
                            val = val.strip()
                            try:
                                args[key] = ast.literal_eval(val)
                            except (ValueError, SyntaxError):
                                args[key] = val.strip('"\'')
                else:
                    # Single positional arg
                    try:
                        args["query"] = ast.literal_eval(args_str)
                    except (ValueError, SyntaxError):
                        args["query"] = args_str.strip('"\'')
            except Exception as e:
                logger.warning(f"Failed to parse action args: {e}")
                args["query"] = args_str

        return tool_name, args, raw_action

    def _parse_final_answer(self, text: str) -> str | None:
        """Parse final answer from LLM output."""
        # Greedy match from "Final Answer:" to end-of-string so multi-line
        # JSON arrays are captured in full and not truncated at the first blank line.
        pattern = r"Final Answer:\s*(.+)$"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _parse_thought(self, text: str) -> str | None:
        """Parse thought from LLM output."""
        # Look for Thought: ... (up to Action: or Final Answer:)
        pattern = r"Thought:\s*(.+?)(?:Action:|Final Answer:|$)"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    async def _execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolResult:
        """Execute a tool and return the result."""
        start_time = time.perf_counter()

        if tool_name not in self.tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                result=None,
                error=f"Unknown tool: {tool_name}",
                duration_ms=0,
            )

        tool = self.tools[tool_name]

        try:
            # Execute with timeout
            timeout_s = self.config.timeout_per_action_ms / 1000

            if asyncio.iscoroutinefunction(tool.func):
                result = await asyncio.wait_for(
                    tool.func(**args),
                    timeout=timeout_s,
                )
            else:
                # Run sync function in executor
                # Use get_running_loop() (Python 3.10+) instead of deprecated get_event_loop()
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tool.func(**args)),
                    timeout=timeout_s,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000

            return ToolResult(
                tool_name=tool_name,
                success=True,
                result=result,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=False,
                result=None,
                error=f"Tool timed out after {timeout_s}s",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Tool {tool_name} failed: {e}")
            return ToolResult(
                tool_name=tool_name,
                success=False,
                result=None,
                error=str(e),
                duration_ms=duration_ms,
            )

    async def run(
        self,
        question: str,
        context: dict[str, Any] | None = None,
    ) -> ReActResult:
        """
        Run the ReAct agent on a question.

        Args:
            question: The question or task to solve
            context: Optional context to include in the prompt

        Returns:
            ReActResult with the answer and reasoning trace
        """
        start_time = time.perf_counter()
        steps: list[ReActStep] = []
        run_id = f"react_{uuid.uuid4().hex[:8]}"

        logger.info(f"[{run_id}] Starting ReAct agent: {question[:100]}...")

        # Build system prompt with tools
        system_prompt = self.system_prompt.format(
            tools_description=self._build_tools_description()
        )

        for iteration in range(self.config.max_iterations):
            logger.debug(f"[{run_id}] Iteration {iteration + 1}/{self.config.max_iterations}")

            # Build user prompt with scratchpad
            scratchpad = self._build_scratchpad(steps)
            user_prompt = REACT_USER_PROMPT.format(
                question=question,
                scratchpad=scratchpad if scratchpad else "Start your reasoning:",
            )

            # Get LLM response
            try:
                response = await self.llm_client.generate_async(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                )
            except Exception as e:
                logger.error(f"[{run_id}] LLM call failed: {e}")
                return ReActResult(
                    success=False,
                    error=f"LLM call failed: {e}",
                    steps=steps,
                    total_iterations=iteration + 1,
                    total_duration_ms=(time.perf_counter() - start_time) * 1000,
                    run_id=run_id,
                )

            # Parse LLM response
            thought = self._parse_thought(response)
            if thought:
                steps.append(ReActStep(
                    step_type=StepType.THOUGHT,
                    content=thought,
                ))
                logger.debug(f"[{run_id}] Thought: {thought[:100]}...")

            # Check for final answer
            final_answer = self._parse_final_answer(response)
            if final_answer and self.config.stop_on_final_answer:
                steps.append(ReActStep(
                    step_type=StepType.FINAL_ANSWER,
                    content=final_answer,
                ))
                logger.info(f"[{run_id}] Final answer reached after {iteration + 1} iterations")

                return ReActResult(
                    success=True,
                    final_answer=final_answer,
                    steps=steps,
                    total_iterations=iteration + 1,
                    total_duration_ms=(time.perf_counter() - start_time) * 1000,
                    run_id=run_id,
                )

            # Parse action
            tool_name, tool_args, raw_action = self._parse_action(response)

            if tool_name:
                steps.append(ReActStep(
                    step_type=StepType.ACTION,
                    content=raw_action or f"{tool_name}({tool_args})",
                    tool_name=tool_name,
                    tool_args=tool_args,
                ))
                logger.debug(f"[{run_id}] Action: {tool_name}({tool_args})")

                # Execute tool
                tool_result = await self._execute_tool(tool_name, tool_args or {})

                # Add observation
                observation = str(tool_result)
                steps.append(ReActStep(
                    step_type=StepType.OBSERVATION,
                    content=observation,
                    duration_ms=tool_result.duration_ms,
                ))
                logger.debug(f"[{run_id}] Observation: {observation[:100]}...")

            elif not final_answer:
                # No action and no final answer - LLM might be stuck
                logger.warning(f"[{run_id}] No action or final answer in response")
                if self.config.retry_on_parse_error:
                    # Add a hint for the LLM
                    steps.append(ReActStep(
                        step_type=StepType.ERROR,
                        content="Please provide either an Action or Final Answer.",
                    ))
                    continue
                else:
                    break

        # Max iterations reached
        logger.warning(f"[{run_id}] Max iterations ({self.config.max_iterations}) reached")

        # Try to extract any partial answer
        partial_answer = None
        for step in reversed(steps):
            if step.step_type == StepType.THOUGHT:
                partial_answer = step.content
                break

        return ReActResult(
            success=False,
            final_answer=partial_answer,
            steps=steps,
            total_iterations=self.config.max_iterations,
            total_duration_ms=(time.perf_counter() - start_time) * 1000,
            error=f"Max iterations ({self.config.max_iterations}) reached without final answer",
            run_id=run_id,
        )

    def run_sync(
        self,
        question: str,
        context: dict[str, Any] | None = None,
    ) -> ReActResult:
        """Synchronous wrapper for run()."""
        return asyncio.run(self.run(question, context))


# Convenience function to create a ReAct agent
def create_react_agent(
    llm_client: "LLMGatewayClient",
    tools: list[Tool] | None = None,
    **config_kwargs,
) -> ReActAgent:
    """
    Create a ReAct agent with configuration.

    Args:
        llm_client: LLM client
        tools: List of tools
        **config_kwargs: Arguments passed to ReActConfig

    Returns:
        Configured ReActAgent
    """
    config = ReActConfig(**config_kwargs)
    return ReActAgent(llm_client=llm_client, tools=tools, config=config)