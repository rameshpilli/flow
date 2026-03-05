"""
FunctionAgent - Agent with explicit handoff capabilities.
=========================================================

Extends LLMGatewayAgent with the ability to explicitly delegate tasks
to other agents with context transfer. This enables agent-to-agent
workflows where agents can hand off execution to each other.

The handoff pattern is useful when:
- Different agents have specialized expertise
- A task needs to be passed through a pipeline (research → write → review)
- You want explicit control over agent delegation

Classes:
    HandoffResult: Result of a handoff to another agent.
    FunctionAgentOptions: Configuration extending LLMGatewayAgentOptions.
    FunctionAgent: Agent with handoff capabilities.

Usage:
    from agentorchestrator.squad import FunctionAgent, FunctionAgentOptions

    # Create agent with handoff targets
    research_agent = FunctionAgent(FunctionAgentOptions(
        name="Researcher",
        description="Searches for information",
        can_handoff_to=["Writer", "Reviewer"],
    ))

    # During processing, agent can delegate
    result = await research_agent.handoff(
        to_agent="Writer",
        context={"findings": findings},
        message="Research complete. Please write a summary.",
    )

Example:
    >>> from agentorchestrator.squad import FunctionAgent, FunctionAgentOptions
    >>>
    >>> # Create pipeline agents
    >>> researcher = FunctionAgent(FunctionAgentOptions(
    ...     name="Researcher",
    ...     description="Gathers information",
    ...     can_handoff_to=["Writer"],
    ... ))
    >>> writer = FunctionAgent(FunctionAgentOptions(
    ...     name="Writer",
    ...     description="Writes reports",
    ...     can_handoff_to=["User"],  # Terminal - returns to user
    ... ))
    >>>
    >>> # Handoff creates a result that orchestrator can use
    >>> handoff = await researcher.handoff(
    ...     to_agent="Writer",
    ...     context={"findings": ["insight1", "insight2"]},
    ...     message="Please write this up",
    ... )
    >>> print(handoff.to_agent)  # "Writer"

See Also:
    LLMGatewayAgent: Base class providing LLM capabilities.
    Squad: High-level wrapper for team coordination.
    SupervisorAgent: Alternative pattern with central coordinator.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from agentorchestrator.squad.agents.llm_gateway_agent import (
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)

logger = logging.getLogger(__name__)


@dataclass
class HandoffResult:
    """
    Result of a handoff to another agent.

    Captures the handoff specification so that an orchestrator or workflow
    can route execution to the target agent with proper context.

    Attributes:
        to_agent (str): Name of the target agent to hand off to.
            "User" is a special value meaning return control to the user.
        context (dict[str, Any]): Context data to pass to the target agent.
            Should contain everything the next agent needs to continue.
        message (str): Message for the target agent explaining what to do.
        from_agent (str): Name of the agent initiating the handoff.

    Example:
        >>> handoff = HandoffResult(
        ...     to_agent="Writer",
        ...     context={"findings": ["insight1"], "sources": ["doc1.pdf"]},
        ...     message="Research complete. Please write a summary.",
        ...     from_agent="Researcher",
        ... )
        >>> print(f"{handoff.from_agent} → {handoff.to_agent}")
        Researcher → Writer
    """

    to_agent: str
    context: dict[str, Any]
    message: str
    from_agent: str

    def __repr__(self) -> str:
        return (
            f"HandoffResult("
            f"from={self.from_agent!r} → to={self.to_agent!r}, "
            f"context_keys={list(self.context.keys())}, "
            f"message={self.message[:50]!r}...)"
        )


# Type alias for handoff callback
OnHandoffCallback = Callable[[HandoffResult], Awaitable[None]]


@dataclass
class FunctionAgentOptions(LLMGatewayAgentOptions):
    """
    Configuration options for FunctionAgent.

    Extends LLMGatewayAgentOptions with handoff-specific settings.

    Attributes:
        can_handoff_to (list[str]): List of agent names this agent can
            hand off to. "User" is always implicitly allowed as a target.
            Default: [].
        on_handoff (Callable[[HandoffResult], Awaitable[None]] | None):
            Optional async callback invoked when a handoff occurs.
            Useful for logging, metrics, or workflow orchestration.

    Example:
        >>> options = FunctionAgentOptions(
        ...     name="Researcher",
        ...     description="Gathers and analyzes information",
        ...     can_handoff_to=["Writer", "Analyst"],
        ...     on_handoff=my_handoff_logger,
        ... )
        >>> agent = FunctionAgent(options)
        >>> "Writer" in agent.can_handoff_to  # True

    Note:
        "User" is always a valid handoff target, even if not in the list.
        This allows any agent to return control to the user.

    See Also:
        LLMGatewayAgentOptions: Base options inherited by this class.
        FunctionAgent: Agent that uses these options.
    """

    can_handoff_to: list[str] = field(default_factory=list)
    on_handoff: Optional[OnHandoffCallback] = None


class FunctionAgent(LLMGatewayAgent):
    """
    Agent with explicit handoff capabilities.

    Extends LLMGatewayAgent with the ability to explicitly delegate
    tasks to other agents with context transfer. This enables
    agent-to-agent workflows and explicit coordination patterns.

    Attributes:
        can_handoff_to (list[str]): Allowed handoff targets.

    Methods:
        handoff: Create a handoff to another agent.
        get_pending_handoff: Get and clear pending handoff.
        has_pending_handoff: Check if there's a pending handoff.

    Example:
        ```python
        from agentorchestrator.squad import FunctionAgent, FunctionAgentOptions

        # Create agents with handoff permissions
        research_agent = FunctionAgent(FunctionAgentOptions(
            name="Researcher",
            description="Searches for information",
            can_handoff_to=["Writer", "User"],
        ))

        writer_agent = FunctionAgent(FunctionAgentOptions(
            name="Writer",
            description="Writes reports from research",
            can_handoff_to=["Reviewer", "User"],
        ))

        reviewer_agent = FunctionAgent(FunctionAgentOptions(
            name="Reviewer",
            description="Reviews and improves content",
            can_handoff_to=["User"],  # Terminal - returns to user
        ))

        # Researcher hands off to Writer
        handoff = await research_agent.handoff(
            to_agent="Writer",
            context={
                "findings": findings,
                "sources": sources,
            },
            message="Research complete. Please write a summary.",
        )

        # Orchestrator uses handoff.to_agent to route to Writer
        # Writer then processes with the provided context
        ```

    Pipeline Pattern:
        FunctionAgent enables explicit pipelines like:
        ```
        Researcher → Writer → Reviewer → User
        ```
        Each agent does its part and hands off to the next.

    See Also:
        LLMGatewayAgent: Base class providing LLM capabilities.
        HandoffResult: Result returned by handoff().
        Squad: Alternative pattern using supervisor coordination.
    """

    def __init__(self, options: FunctionAgentOptions):
        """
        Initialize the FunctionAgent.

        Args:
            options: Configuration options including handoff targets.

        Example:
            >>> agent = FunctionAgent(FunctionAgentOptions(
            ...     name="Researcher",
            ...     description="Gathers information",
            ...     can_handoff_to=["Writer", "Analyst"],
            ... ))
        """
        super().__init__(options)

        self.can_handoff_to = list(options.can_handoff_to or [])
        self._on_handoff = options.on_handoff
        self._pending_handoff: Optional[HandoffResult] = None

    async def handoff(
        self,
        to_agent: str,
        context: dict[str, Any],
        message: str = "",
    ) -> HandoffResult:
        """
        Hand off execution to another agent.

        Creates a HandoffResult that can be consumed by a workflow
        orchestrator to continue execution with the target agent.

        Args:
            to_agent: Name of the agent to hand off to.
                "User" (case-insensitive) is always allowed as a target,
                meaning return control to the user.
            context: Context data to pass to the target agent.
                Should contain everything the next agent needs.
            message: Optional message to the target agent explaining
                what to do. Default: "".

        Returns:
            HandoffResult containing the handoff specification.

        Raises:
            ValueError: If to_agent is not in can_handoff_to list
                (and is not "User").

        Example:
            >>> handoff = await agent.handoff(
            ...     to_agent="Writer",
            ...     context={"findings": findings, "sources": sources},
            ...     message="Research complete. Please write a summary.",
            ... )
            >>> print(handoff.to_agent)  # "Writer"

        Note:
            The handoff is stored as pending until get_pending_handoff()
            is called. This allows the orchestrator to check for handoffs
            after processing.
        """
        # "User" is always a valid handoff target (return to user)
        if to_agent.lower() != "user" and to_agent not in self.can_handoff_to:
            raise ValueError(
                f"Agent {self.name!r} cannot hand off to {to_agent!r}. "
                f"Allowed targets: {self.can_handoff_to + ['User']}"
            )

        result = HandoffResult(
            to_agent=to_agent,
            context=context,
            message=message,
            from_agent=self.name,
        )

        self._pending_handoff = result
        logger.info(f"Agent {self.name!r} handing off to {to_agent!r}")

        if self._on_handoff:
            await self._on_handoff(result)

        return result

    def get_pending_handoff(self) -> Optional[HandoffResult]:
        """
        Get and clear any pending handoff.

        Returns the pending handoff result (if any) and clears it.
        This is typically called by an orchestrator after processing
        to check if the agent wants to hand off to another agent.

        Returns:
            HandoffResult if there's a pending handoff, None otherwise.
            The handoff is cleared after being retrieved.

        Example:
            >>> # After agent processing
            >>> handoff = agent.get_pending_handoff()
            >>> if handoff:
            ...     # Route to handoff.to_agent
            ...     next_agent = get_agent(handoff.to_agent)
            ...     await next_agent.process(handoff.context)
        """
        handoff = self._pending_handoff
        self._pending_handoff = None
        return handoff

    def has_pending_handoff(self) -> bool:
        """
        Check if there's a pending handoff.

        Returns:
            True if the agent has a pending handoff, False otherwise.

        Example:
            >>> if agent.has_pending_handoff():
            ...     handoff = agent.get_pending_handoff()
            ...     # Handle the handoff
        """
        return self._pending_handoff is not None

    def __repr__(self) -> str:
        """Return string representation of the FunctionAgent."""
        return (
            f"FunctionAgent("
            f"name={self.name!r}, "
            f"can_handoff_to={self.can_handoff_to}, "
            f"pending={self.has_pending_handoff()})"
        )