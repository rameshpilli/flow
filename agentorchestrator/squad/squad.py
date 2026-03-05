"""
Squad - High-level wrapper for supervisor + agents pattern.
===========================================================

Provides the simplest API for creating a coordinated team of agents.
Squad wraps SupervisorAgent to provide a clean, user-friendly interface.

This is the recommended entry point for multi-agent coordination when
you have a clear supervisor/specialist hierarchy.

Classes:
    SquadOptions: Configuration options for a Squad.
    Squad: High-level wrapper for team coordination.

Usage:
    from agentorchestrator.squad import Squad, SquadOptions, LLMGatewayAgent

    # Create specialist agents
    tech_agent = LLMGatewayAgent(...)
    finance_agent = LLMGatewayAgent(...)

    # Create supervisor (lead agent)
    supervisor = LLMGatewayAgent(name="Supervisor", ...)

    # Create squad
    squad = Squad(
        supervisor=supervisor,
        agents=[tech_agent, finance_agent],
    )

    # Run a query - supervisor coordinates the team
    result = await squad.run("Analyze tech stocks for Q1")
    print(result.content)

Example:
    >>> from agentorchestrator.squad import Squad, LLMGatewayAgent, LLMGatewayAgentOptions
    >>>
    >>> # Quick setup
    >>> tech = LLMGatewayAgent(LLMGatewayAgentOptions(
    ...     name="TechAgent",
    ...     description="Technical questions",
    ... ))
    >>> lead = LLMGatewayAgent(LLMGatewayAgentOptions(
    ...     name="Lead",
    ...     description="Team coordinator",
    ... ))
    >>> squad = Squad(supervisor=lead, agents=[tech])
    >>> result = await squad.run("How does async work in Python?")

See Also:
    SupervisorAgent: The underlying implementation.
    MultiAgentOrchestrator: For more complex routing scenarios.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from agentorchestrator.squad.agents.base import Agent
from agentorchestrator.squad.agents.llm_gateway_agent import LLMGatewayAgent
from agentorchestrator.squad.agents.supervisor import (
    SupervisorAgent,
    SupervisorAgentOptions,
)
from agentorchestrator.squad.storage.base import ChatStorage
from agentorchestrator.squad.storage.memory import InMemoryChatStorage
from agentorchestrator.squad.types import ConversationMessage


@dataclass
class SquadOptions:
    """
    Configuration options for a Squad.

    Controls how the squad coordinates agents and processes requests.

    Attributes:
        name (str): Display name for the squad. Default: "Squad".
        description (str): Description of what this squad does.
            Default: "A coordinated team of agents".
        storage (ChatStorage | None): Chat storage for team memory.
            If None, uses InMemoryChatStorage.
        trace (bool): Enable detailed tracing/logging. Default: False.
        enable_tracing (bool): Enable OTEL tracing spans. Default: True.
        max_concurrent_agents (int): Max agents to run in parallel.
            Default: 10. Set lower if agents are resource-intensive.
        agent_timeout_seconds (float): Timeout per agent call.
            Default: 60.0 seconds.
        enable_validation (bool): Enable response validation/judge.
            Default: False. Set True for quality control.
        guardrails (list[str]): Content guardrail checks to apply.
            Default: []. Options: "no_pii", "no_profanity", etc.

    Example:
        >>> options = SquadOptions(
        ...     name="ResearchSquad",
        ...     description="Coordinates research across multiple domains",
        ...     trace=True,
        ...     max_concurrent_agents=5,
        ... )
        >>> squad = Squad(supervisor=lead, agents=team, options=options)
    """

    name: str = "Squad"
    description: str = "A coordinated team of agents"
    storage: Optional[ChatStorage] = None
    trace: bool = False
    enable_tracing: bool = True
    max_concurrent_agents: int = 10
    agent_timeout_seconds: float = 60.0
    enable_validation: bool = False
    guardrails: list[str] = field(default_factory=list)


class Squad:
    """
    High-level wrapper for the supervisor + agents pattern.

    Squad provides the simplest API for creating a coordinated team
    of specialized agents with a supervisor that delegates tasks.

    The supervisor agent analyzes incoming requests, decides which
    team members to involve, delegates tasks in parallel, and
    synthesizes their responses into a final answer.

    Attributes:
        supervisor: The underlying SupervisorAgent instance.
        agents: List of team member agents.
        options: Configuration options.

    Methods:
        run: Execute a query with the squad.
        add_agent: Add an agent to the team.
        remove_agent: Remove an agent from the team.
        get_metrics: Get execution metrics.
        reset_metrics: Reset metrics counters.

    Example:
        ```python
        from agentorchestrator.squad import (
            Squad,
            SquadOptions,
            LLMGatewayAgent,
            LLMGatewayAgentOptions,
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

        # Create lead agent (supervisor)
        lead = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="Supervisor",
            description="Coordinates team to answer complex questions",
        ))

        # Create squad
        squad = Squad(
            supervisor=lead,
            agents=[tech_agent, finance_agent],
            options=SquadOptions(trace=True),
        )

        # Execute
        result = await squad.run("Analyze Tesla's EV technology and market cap")
        print(result.content)
        ```

    See Also:
        SupervisorAgent: The underlying implementation details.
        MultiAgentOrchestrator: For intent-based routing scenarios.
    """

    def __init__(
        self,
        supervisor: LLMGatewayAgent,
        agents: list[Agent],
        options: Optional[SquadOptions] = None,
    ):
        """
        Initialize a Squad.

        Args:
            supervisor: LLMGatewayAgent that coordinates the team.
                This agent will analyze requests and delegate to team members.
            agents: List of specialist agents to coordinate.
                Each should have a clear name and description.
            options: Optional squad configuration.
                If None, uses default SquadOptions.

        Raises:
            ValueError: If supervisor is not a LLMGatewayAgent.
            ValueError: If agents list is empty.

        Example:
            >>> squad = Squad(
            ...     supervisor=lead_agent,
            ...     agents=[tech_agent, finance_agent],
            ...     options=SquadOptions(trace=True),
            ... )
        """
        if not isinstance(supervisor, LLMGatewayAgent):
            raise ValueError("supervisor must be a LLMGatewayAgent")

        if not agents:
            raise ValueError("agents list cannot be empty")

        self.options = options or SquadOptions()
        self._lead = supervisor

        # Create the underlying SupervisorAgent
        self._supervisor = SupervisorAgent(
            SupervisorAgentOptions(
                name=self.options.name,
                description=self.options.description,
                lead_agent=supervisor,
                team=list(agents),
                storage=self.options.storage or InMemoryChatStorage(),
                trace=self.options.trace,
                enable_tracing=self.options.enable_tracing,
                max_concurrent_agents=self.options.max_concurrent_agents,
                agent_timeout_seconds=self.options.agent_timeout_seconds,
                enable_validation=self.options.enable_validation,
                guardrails=self.options.guardrails,
            )
        )

    @property
    def supervisor(self) -> SupervisorAgent:
        """
        Get the underlying SupervisorAgent.

        Returns:
            The SupervisorAgent instance managing the team.
        """
        return self._supervisor

    @property
    def agents(self) -> list[Agent]:
        """
        Get list of team member agents.

        Returns:
            List of agents in the team (excluding the supervisor).
        """
        return self._supervisor.team

    async def run(
        self,
        query: str,
        user_id: str = "default_user",
        session_id: str = "default_session",
        chat_history: Optional[list[ConversationMessage]] = None,
        additional_params: Optional[dict[str, Any]] = None,
    ) -> ConversationMessage:
        """
        Run the squad on a query.

        The supervisor will analyze the query, delegate to appropriate
        team members in parallel, and synthesize their responses.

        Args:
            query: User's input query to process.
            user_id: User identifier for history tracking. Default: "default_user".
            session_id: Session identifier for history tracking. Default: "default_session".
            chat_history: Optional conversation history for context.
            additional_params: Optional additional parameters (RAG context, etc.).

        Returns:
            ConversationMessage: The synthesized response from the squad.

        Example:
            >>> result = await squad.run(
            ...     "What are the best practices for async Python?",
            ...     user_id="user-123",
            ...     session_id="session-456",
            ... )
            >>> print(result.content)

        Note:
            The supervisor coordinates the team automatically. You don't need
            to specify which agents to use - the supervisor decides based on
            the query and agent descriptions.
        """
        return await self._supervisor.process_request(
            input_text=query,
            user_id=user_id,
            session_id=session_id,
            chat_history=chat_history or [],
            additional_params=additional_params,
        )

    def add_agent(self, agent: Agent) -> None:
        """
        Add an agent to the team.

        The new agent will be available for delegation on subsequent
        queries. The supervisor's prompt is automatically updated.

        Args:
            agent: Agent to add to the team.

        Example:
            >>> new_agent = LLMGatewayAgent(...)
            >>> squad.add_agent(new_agent)
        """
        self._supervisor.add_agent(agent)

    def remove_agent(self, agent_name: str) -> bool:
        """
        Remove an agent from the team by name.

        Args:
            agent_name: Name of the agent to remove.

        Returns:
            True if agent was found and removed, False otherwise.

        Example:
            >>> success = squad.remove_agent("TechAgent")
            >>> print(f"Removed: {success}")
        """
        return self._supervisor.remove_agent(agent_name)

    def get_metrics(self) -> dict[str, Any]:
        """
        Get squad execution metrics.

        Returns:
            Dict containing:
                - request_count: Total requests processed
                - total_latency_ms: Total processing time
                - avg_latency_ms: Average processing time
                - agent_metrics: Per-agent statistics
                - validation_failures: Failed validation count

        Example:
            >>> metrics = squad.get_metrics()
            >>> print(f"Processed {metrics['request_count']} requests")
            >>> print(f"Avg latency: {metrics['avg_latency_ms']:.1f}ms")
        """
        return self._supervisor.get_metrics()

    def reset_metrics(self) -> None:
        """
        Reset all metrics counters.

        Useful for starting fresh measurements after configuration changes.

        Example:
            >>> squad.reset_metrics()
            >>> # Run some queries
            >>> metrics = squad.get_metrics()  # Fresh metrics
        """
        self._supervisor.reset_metrics()

    def __repr__(self) -> str:
        """Return string representation of the Squad."""
        return (
            f"Squad("
            f"name={self.options.name!r}, "
            f"agents={len(self.agents)}, "
            f"supervisor={self._lead.name!r})"
        )