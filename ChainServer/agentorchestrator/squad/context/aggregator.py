"""
AgentOrchestrator Result Aggregator
===================================

This module provides result aggregation for multi-agent systems.

After multiple agents execute in isolation, the ResultAggregator collects
their outputs and produces a unified result using configurable strategies.
This enables sophisticated multi-agent patterns like ensemble voting,
confidence-based selection, and LLM-powered synthesis.

Classes:
    AggregationStrategy: Enum of available aggregation strategies.
    ContextAgentResult: Result from a single agent with confidence/priority.
    ConflictInfo: Information about conflicting values between agents.
    AggregatedResult: Final aggregated output from all agents.
    ResultAggregator: Main class for aggregating agent results.

Strategies:
    SYNTHESIZE: Use LLM to create a narrative combining all results.
    MERGE: Deep merge structured data (JSON/dicts).
    PRIORITIZE: Select result with highest confidence/priority.
    VOTE: Majority voting for discrete answers.
    CHAIN: Sequential refinement (each result builds on previous).
    CONCAT: Simple concatenation (for text results).

Usage:
    from agentorchestrator.squad.context import ResultAggregator, AggregationStrategy

    aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)

    # Add results from each agent
    aggregator.add_result(agent_id="agent-1", data=result1, confidence=0.9)
    aggregator.add_result(agent_id="agent-2", data=result2, confidence=0.8)

    # Aggregate with LLM synthesis
    final = await aggregator.aggregate(llm=llm_client)
    print(final.data)

Example:
    >>> from agentorchestrator.squad.context import ResultAggregator, AggregationStrategy
    >>>
    >>> # Create aggregator with voting strategy
    >>> aggregator = ResultAggregator(strategy=AggregationStrategy.VOTE)
    >>>
    >>> # Multiple agents vote on an answer
    >>> aggregator.add_result("analyst-1", data="bullish", confidence=0.85)
    >>> aggregator.add_result("analyst-2", data="bullish", confidence=0.75)
    >>> aggregator.add_result("analyst-3", data="bearish", confidence=0.60)
    >>>
    >>> # Aggregate votes
    >>> result = await aggregator.aggregate()
    >>> print(result.data)  # "bullish" (2 votes vs 1)
    >>> print(result.confidence)  # ~0.73 (average of voters)

See Also:
    - agentorchestrator.squad.context.manager: Context management for agents.
    - agentorchestrator.services.llm_gateway: LLM client for synthesis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from agentorchestrator.services.llm_gateway import LLMGatewayClient

logger = logging.getLogger(__name__)


class AggregationStrategy(str, Enum):
    """
    Strategy for combining results from multiple agents.

    Each strategy is suited to different use cases:

    Attributes:
        SYNTHESIZE: Use LLM to create a narrative synthesis of all results.
            Best for: Open-ended questions, complex analysis, reports.
        MERGE: Deep merge structured data (dicts/lists).
            Best for: Combining complementary data from different sources.
        PRIORITIZE: Select the result with highest confidence/priority.
            Best for: When one expert answer is preferred over consensus.
        VOTE: Majority voting for discrete answers.
            Best for: Classification tasks, binary decisions.
        CHAIN: Sequential refinement where each result builds on previous.
            Best for: Iterative improvement, review chains.
        CONCAT: Simple concatenation of text results.
            Best for: Collecting multiple perspectives without synthesis.

    Example:
        >>> strategy = AggregationStrategy.VOTE
        >>> aggregator = ResultAggregator(strategy=strategy)

    See Also:
        ResultAggregator: Uses this enum to select aggregation behavior.
    """

    SYNTHESIZE = "synthesize"
    """Use LLM to create narrative synthesis of all results."""

    MERGE = "merge"
    """Deep merge structured data (dicts/lists)."""

    PRIORITIZE = "prioritize"
    """Select result with highest confidence/priority."""

    VOTE = "vote"
    """Majority voting for discrete answers."""

    CHAIN = "chain"
    """Sequential refinement - each result builds on previous."""

    CONCAT = "concat"
    """Simple concatenation (for text results)."""


@dataclass
class ContextAgentResult:
    """
    Result from a single agent in multi-agent aggregation context.

    Extends basic results with confidence and priority scores for
    aggregation strategies. This is distinct from agents.base.AgentResult
    which is for data fetching.

    Attributes:
        agent_id (str): Identifier of the agent that produced this result.
        data (Any): The result data (can be any type).
        timestamp (datetime): When the result was created. Default: now.
        confidence (float): Confidence score from 0.0 to 1.0. Default: 1.0.
            Used by PRIORITIZE and affects overall confidence calculation.
        priority (int): Priority ranking for this agent. Default: 0.
            Higher values = higher priority. Used by PRIORITIZE and CHAIN.
        metadata (dict[str, Any]): Additional metadata about the result.
        error (str | None): Error message if the agent failed. None on success.

    Methods:
        is_valid(): Check if result is usable (no error, has data).
        to_dict(): Convert to dictionary for serialization.

    Example:
        >>> result = ContextAgentResult(
        ...     agent_id="financial-analyst",
        ...     data={"recommendation": "buy", "target_price": 150.0},
        ...     confidence=0.85,
        ...     priority=2,
        ...     metadata={"model": "gpt-4", "reasoning": "Strong fundamentals"},
        ... )
        >>> result.is_valid()
        True
        >>> result.confidence
        0.85

    See Also:
        ResultAggregator.add_result(): Create results from parameters.
        AggregatedResult: Final output after aggregation.
    """

    agent_id: str
    data: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 1.0
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def is_valid(self) -> bool:
        """
        Check if the result is valid and usable for aggregation.

        A result is valid if it has no error and contains data.

        Returns:
            bool: True if no error and data is not None.

        Example:
            >>> result = ContextAgentResult(agent_id="a", data="answer")
            >>> result.is_valid()
            True
            >>> error_result = ContextAgentResult(agent_id="b", data=None, error="Failed")
            >>> error_result.is_valid()
            False
        """
        return self.error is None and self.data is not None

    def to_dict(self) -> dict:
        """
        Convert to a dictionary for serialization.

        Returns:
            dict: Dictionary representation with all fields.
                timestamp is converted to ISO format string.

        Example:
            >>> result = ContextAgentResult(agent_id="a", data="test")
            >>> d = result.to_dict()
            >>> d["agent_id"]
            'a'
        """
        return {
            "agent_id": self.agent_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "priority": self.priority,
            "metadata": self.metadata,
            "error": self.error,
        }


# Backward compatibility alias
AgentResult = ContextAgentResult


@dataclass
class ConflictInfo:
    """
    Information about a conflict between agent results.

    When multiple agents provide different values for the same key
    during MERGE strategy, a conflict is recorded.

    Attributes:
        key (str): The key/field where the conflict occurred.
        agents (list[str]): Agent IDs involved in the conflict.
        values (list[Any]): The conflicting values from each agent.
        resolution (str | None): How the conflict was resolved (if at all).
        resolved_value (Any): The final resolved value (if resolved).

    Example:
        >>> conflict = ConflictInfo(
        ...     key="recommendation",
        ...     agents=["analyst-1", "analyst-2"],
        ...     values=["buy", "hold"],
        ...     resolution="custom_resolver",
        ...     resolved_value="hold",
        ... )

    See Also:
        ResultAggregator: Creates conflicts during MERGE strategy.
        AggregatedResult.conflicts: Contains all detected conflicts.
    """

    key: str
    agents: list[str]
    values: list[Any]
    resolution: str | None = None
    resolved_value: Any = None


@dataclass
class AggregatedResult:
    """
    Final aggregated result from all agents.

    Contains the combined data, information about how it was produced,
    agent contributions, and any conflicts that were detected.

    Attributes:
        data (Any): The aggregated result data.
        strategy (AggregationStrategy): Strategy used for aggregation.
        agent_contributions (dict[str, Any]): Summary of each agent's contribution.
            Maps agent_id to {data_preview, confidence, error}.
        conflicts (list[ConflictInfo]): Any conflicts detected during aggregation.
        confidence (float): Overall confidence score for the aggregated result.
            Calculated as average of agent confidences minus conflict penalty.
        metadata (dict[str, Any]): Additional metadata including:
            - total_agents: Number of agents that provided results
            - valid_agents: Number of agents with valid results
            - failed_agents: Number of agents that failed

    Methods:
        to_dict(): Convert to dictionary for serialization.

    Example:
        >>> # After aggregation
        >>> result = await aggregator.aggregate()
        >>> print(result.data)
        >>> print(f"Strategy: {result.strategy.value}")
        >>> print(f"Confidence: {result.confidence:.0%}")
        >>> print(f"Conflicts: {len(result.conflicts)}")
        >>> for agent_id, contrib in result.agent_contributions.items():
        ...     print(f"  {agent_id}: {contrib['confidence']:.0%}")

    See Also:
        ResultAggregator.aggregate(): Produces this result.
        ContextAgentResult: Individual agent results.
    """

    data: Any
    strategy: AggregationStrategy
    agent_contributions: dict[str, Any]
    conflicts: list[ConflictInfo]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """
        Convert to a dictionary for serialization.

        Returns:
            dict: Dictionary representation with all fields.
                Strategy is converted to string value.
                Conflicts are converted to dicts.

        Example:
            >>> d = result.to_dict()
            >>> d["strategy"]
            'synthesize'
        """
        return {
            "data": self.data,
            "strategy": self.strategy.value,
            "agent_contributions": self.agent_contributions,
            "conflicts": [
                {
                    "key": c.key,
                    "agents": c.agents,
                    "values": c.values,
                    "resolution": c.resolution,
                }
                for c in self.conflicts
            ],
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


class ResultAggregator:
    """
    Aggregates results from multiple isolated agent contexts.

    The ResultAggregator collects outputs from multiple agents and
    combines them using a configurable strategy. It handles conflicts,
    tracks contributions, and calculates overall confidence.

    Attributes:
        strategy (AggregationStrategy): The aggregation strategy to use.
        conflict_resolver (Callable | None): Custom function to resolve conflicts.

    Methods:
        add_result(): Add a result from an agent.
        add_from_namespace(): Add result from agent namespace.
        aggregate(): Combine all results using the strategy.
        get_results(): Get all added results.
        get_conflicts(): Get all detected conflicts.
        clear(): Reset the aggregator.

    Example:
        >>> from agentorchestrator.squad.context import ResultAggregator, AggregationStrategy
        >>>
        >>> # Create with PRIORITIZE strategy
        >>> aggregator = ResultAggregator(strategy=AggregationStrategy.PRIORITIZE)
        >>>
        >>> # Add results with different priorities
        >>> aggregator.add_result(
        ...     agent_id="expert",
        ...     data={"answer": "42"},
        ...     confidence=0.95,
        ...     priority=10,  # High priority
        ... )
        >>> aggregator.add_result(
        ...     agent_id="novice",
        ...     data={"answer": "43"},
        ...     confidence=0.60,
        ...     priority=1,  # Low priority
        ... )
        >>>
        >>> # Expert's answer wins due to higher priority
        >>> result = await aggregator.aggregate()
        >>> print(result.data)  # {"answer": "42"}

    LLM Synthesis Example:
        >>> aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
        >>>
        >>> aggregator.add_result("research-agent", "Apple revenue grew 5%...")
        >>> aggregator.add_result("news-agent", "Apple announced new product...")
        >>> aggregator.add_result("analyst-agent", "Target price raised to $200...")
        >>>
        >>> # Synthesize with LLM
        >>> result = await aggregator.aggregate(llm=llm_client)
        >>> print(result.data)  # Coherent narrative combining all findings

    Custom Conflict Resolution:
        >>> def resolve_conflict(conflict: ConflictInfo) -> Any:
        ...     # Take the first value, or implement custom logic
        ...     return conflict.values[0]
        >>>
        >>> aggregator = ResultAggregator(
        ...     strategy=AggregationStrategy.MERGE,
        ...     conflict_resolver=resolve_conflict,
        ... )

    See Also:
        AggregationStrategy: Available strategies.
        AggregatedResult: Output from aggregate().
        ContextAgentResult: Individual agent results.
    """

    def __init__(
        self,
        strategy: AggregationStrategy = AggregationStrategy.SYNTHESIZE,
        conflict_resolver: Callable[[ConflictInfo], Any] | None = None,
    ):
        """
        Initialize the aggregator with a strategy.

        Args:
            strategy (AggregationStrategy): How to combine results.
                Default: SYNTHESIZE (requires LLM for aggregate()).
            conflict_resolver (Callable[[ConflictInfo], Any] | None): Custom
                function to resolve conflicts during MERGE. Receives a
                ConflictInfo and returns the resolved value.

        Example:
            >>> aggregator = ResultAggregator(
            ...     strategy=AggregationStrategy.VOTE,
            ... )
        """
        self.strategy = strategy
        self.conflict_resolver = conflict_resolver

        self._results: dict[str, ContextAgentResult] = {}
        self._conflicts: list[ConflictInfo] = []

    def add_result(
        self,
        agent_id: str,
        data: Any,
        confidence: float = 1.0,
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """
        Add a result from an agent.

        Creates a ContextAgentResult and stores it for later aggregation.
        If an agent_id is added multiple times, the latest result overwrites.

        Args:
            agent_id (str): Unique identifier for the agent.
            data (Any): The result data from the agent.
            confidence (float): Confidence score from 0.0 to 1.0. Default: 1.0.
                Used by PRIORITIZE strategy and overall confidence calculation.
            priority (int): Priority ranking (higher = more important). Default: 0.
                Used by PRIORITIZE and CHAIN strategies.
            metadata (dict[str, Any] | None): Additional metadata.
            error (str | None): Error message if agent failed.

        Example:
            >>> aggregator.add_result(
            ...     agent_id="weather-agent",
            ...     data={"temperature": 72, "conditions": "sunny"},
            ...     confidence=0.95,
            ...     priority=5,
            ...     metadata={"source": "weather-api"},
            ... )

        See Also:
            add_from_namespace(): Add from agent namespace directly.
        """
        self._results[agent_id] = ContextAgentResult(
            agent_id=agent_id,
            data=data,
            confidence=confidence,
            priority=priority,
            metadata=metadata or {},
            error=error,
        )
        logger.debug(f"Added result from {agent_id} (confidence={confidence:.2f})")

    def add_from_namespace(
        self,
        agent_id: str,
        namespace: "AgentContextNamespace",  # noqa: F821
    ) -> None:
        """
        Add result directly from an agent's namespace.

        Convenience method that extracts result, confidence, priority,
        and metadata from an AgentContextNamespace.

        Args:
            agent_id (str): Agent identifier.
            namespace (AgentContextNamespace): The agent's context namespace
                containing result and metadata.

        Example:
            >>> # After agent execution
            >>> aggregator.add_from_namespace(
            ...     agent_id="research-agent",
            ...     namespace=agent.namespace,
            ... )

        See Also:
            add_result(): Add with explicit parameters.
        """
        metadata = namespace.get_metadata()
        self.add_result(
            agent_id=agent_id,
            data=namespace.get_result(),
            confidence=metadata.get("confidence", 1.0),
            priority=metadata.get("priority", 0),
            metadata=metadata,
            error=metadata.get("error"),
        )

    async def aggregate(
        self,
        llm: "LLMGatewayClient | None" = None,
        prompt_template: str | None = None,
    ) -> AggregatedResult:
        """
        Aggregate all results using the configured strategy.

        Combines all added results into a single AggregatedResult.
        The method used depends on the strategy set during initialization.

        Args:
            llm (LLMGatewayClient | None): LLM client for SYNTHESIZE strategy.
                Required for SYNTHESIZE, optional for others.
            prompt_template (str | None): Custom prompt template for synthesis.
                Should contain {context} placeholder for agent outputs.

        Returns:
            AggregatedResult: Combined result with:
                - data: The aggregated output
                - strategy: Which strategy was used
                - agent_contributions: Summary of each agent's input
                - conflicts: Any conflicts detected
                - confidence: Overall confidence score
                - metadata: Counts and additional info

        Example:
            >>> result = await aggregator.aggregate()
            >>> if result.data is None:
            ...     print(f"Aggregation failed: {result.metadata.get('error')}")
            ... else:
            ...     print(f"Result: {result.data}")
            ...     print(f"Confidence: {result.confidence:.0%}")

        Strategy Behaviors:
            - SYNTHESIZE: Uses LLM to create narrative (requires llm parameter)
            - MERGE: Deep merges dicts, concatenates lists
            - PRIORITIZE: Returns highest priority/confidence result
            - VOTE: Returns most common value (majority wins)
            - CHAIN: Sequentially combines by priority order
            - CONCAT: Concatenates all text results

        See Also:
            AggregatedResult: The return type.
            AggregationStrategy: Available strategies.
        """
        valid_results = {
            aid: r for aid, r in self._results.items() if r.is_valid()
        }

        if not valid_results:
            return AggregatedResult(
                data=None,
                strategy=self.strategy,
                agent_contributions={},
                conflicts=[],
                confidence=0.0,
                metadata={"error": "No valid results to aggregate"},
            )

        # Route to strategy handler
        handlers = {
            AggregationStrategy.SYNTHESIZE: self._synthesize,
            AggregationStrategy.MERGE: self._merge,
            AggregationStrategy.PRIORITIZE: self._prioritize,
            AggregationStrategy.VOTE: self._vote,
            AggregationStrategy.CHAIN: self._chain,
            AggregationStrategy.CONCAT: self._concat,
        }

        handler = handlers.get(self.strategy, self._merge)
        data = await handler(valid_results, llm, prompt_template)

        # Build agent contributions summary
        contributions = {
            aid: {
                "data_preview": str(r.data)[:200] if r.data else None,
                "confidence": r.confidence,
                "error": r.error,
            }
            for aid, r in self._results.items()
        }

        # Calculate overall confidence
        confidence = self._calculate_confidence(valid_results)

        return AggregatedResult(
            data=data,
            strategy=self.strategy,
            agent_contributions=contributions,
            conflicts=self._conflicts,
            confidence=confidence,
            metadata={
                "total_agents": len(self._results),
                "valid_agents": len(valid_results),
                "failed_agents": len(self._results) - len(valid_results),
            },
        )

    # =========================================================================
    # Strategy Implementations
    # =========================================================================

    async def _synthesize(
        self,
        results: dict[str, ContextAgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> Any:
        """
        Synthesize results using LLM.

        Uses the LLM to create a coherent narrative that integrates
        findings from all agents.

        Args:
            results: Valid results to synthesize.
            llm: LLM client for generation.
            prompt_template: Custom prompt (optional).

        Returns:
            str: Synthesized narrative text.
        """
        if not llm:
            logger.warning("SYNTHESIZE strategy requires LLM, falling back to MERGE")
            return await self._merge(results, llm, prompt_template)

        # Build context from all results
        context_parts = []
        for agent_id, result in results.items():
            data_str = (
                json.dumps(result.data, indent=2, default=str)
                if isinstance(result.data, (dict, list))
                else str(result.data)
            )
            context_parts.append(
                f"### {agent_id} (confidence: {result.confidence:.0%})\n{data_str}"
            )

        context = "\n\n".join(context_parts)

        prompt = prompt_template or """You are synthesizing outputs from multiple specialized agents.

Each agent has analyzed part of a larger question. Create a unified, coherent response
that integrates all their findings.

AGENT OUTPUTS:
{context}

INSTRUCTIONS:
1. Identify common themes and findings
2. Note any disagreements between agents
3. Synthesize into a coherent narrative
4. Highlight key insights and conclusions
5. If agents conflict, explain both perspectives

SYNTHESIZED RESPONSE:"""

        try:
            response = await llm.generate_async(prompt.format(context=context))
            return response
        except Exception as e:
            logger.error(f"LLM synthesis failed: {e}")
            return await self._merge(results, llm, prompt_template)

    async def _merge(
        self,
        results: dict[str, ContextAgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> dict[str, Any]:
        """
        Deep merge structured results.

        Combines dict results by key. Conflicts are tracked and
        optionally resolved via conflict_resolver.

        Args:
            results: Valid results to merge.
            llm: Not used (for interface consistency).
            prompt_template: Not used (for interface consistency).

        Returns:
            dict: Merged data from all agents.
        """
        merged: dict[str, Any] = {}

        for agent_id, result in results.items():
            if isinstance(result.data, dict):
                for key, value in result.data.items():
                    if key not in merged:
                        merged[key] = value
                    elif merged[key] != value:
                        # Conflict detected
                        self._handle_conflict(key, agent_id, value, merged[key])
            elif isinstance(result.data, list):
                if "items" not in merged:
                    merged["items"] = []
                merged["items"].extend(result.data)
            else:
                # Non-dict results keyed by agent
                merged[agent_id] = result.data

        return merged

    async def _prioritize(
        self,
        results: dict[str, ContextAgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> Any:
        """
        Select the highest priority/confidence result.

        Sorts by priority first, then by confidence. Returns
        the top result's data.

        Args:
            results: Valid results to prioritize.
            llm: Not used (for interface consistency).
            prompt_template: Not used (for interface consistency).

        Returns:
            Any: Data from the highest priority agent.
        """
        # Sort by priority first, then confidence
        sorted_results = sorted(
            results.values(),
            key=lambda r: (r.priority, r.confidence),
            reverse=True,
        )
        winner = sorted_results[0]
        logger.info(f"Selected result from {winner.agent_id} (priority={winner.priority}, confidence={winner.confidence:.2f})")
        return winner.data

    async def _vote(
        self,
        results: dict[str, ContextAgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> Any:
        """
        Majority voting for discrete answers.

        Counts votes for each unique answer and returns the
        one with the most votes.

        Args:
            results: Valid results to vote on.
            llm: Not used (for interface consistency).
            prompt_template: Not used (for interface consistency).

        Returns:
            Any: The data value with the most votes.
        """
        # Count votes
        votes: dict[str, list[str]] = {}  # value -> [agent_ids]
        for agent_id, result in results.items():
            # Convert to string for comparison
            key = str(result.data)
            if key not in votes:
                votes[key] = []
            votes[key].append(agent_id)

        # Find majority
        sorted_votes = sorted(votes.items(), key=lambda x: len(x[1]), reverse=True)
        winner_key, winner_agents = sorted_votes[0]

        logger.info(f"Vote winner: {winner_key} ({len(winner_agents)}/{len(results)} votes)")

        # Return original data type
        for agent_id in winner_agents:
            return results[agent_id].data

    async def _chain(
        self,
        results: dict[str, ContextAgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> Any:
        """
        Chain results sequentially by priority.

        Lower priority results are applied first, then higher
        priority results refine/override.

        Args:
            results: Valid results to chain.
            llm: Not used (for interface consistency).
            prompt_template: Not used (for interface consistency).

        Returns:
            Any: Chained result after all refinements.
        """
        sorted_results = sorted(
            results.values(),
            key=lambda r: r.priority,
        )

        # Chain: each result refines the previous
        current = sorted_results[0].data

        for result in sorted_results[1:]:
            if isinstance(current, dict) and isinstance(result.data, dict):
                current.update(result.data)
            elif isinstance(current, str) and isinstance(result.data, str):
                current = f"{current}\n\n{result.data}"
            else:
                # Keep last
                current = result.data

        return current

    async def _concat(
        self,
        results: dict[str, ContextAgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> str:
        """
        Simple concatenation of text results.

        Combines all results with agent headers.

        Args:
            results: Valid results to concatenate.
            llm: Not used (for interface consistency).
            prompt_template: Not used (for interface consistency).

        Returns:
            str: Concatenated text with headers.
        """
        parts = []
        for agent_id, result in results.items():
            parts.append(f"## {agent_id}\n{result.data}")
        return "\n\n".join(parts)

    # =========================================================================
    # Conflict Handling
    # =========================================================================

    def _handle_conflict(
        self,
        key: str,
        new_agent: str,
        new_value: Any,
        existing_value: Any,
    ) -> None:
        """
        Handle a conflict between agent values.

        Records the conflict and optionally resolves it using
        the conflict_resolver callback.

        Args:
            key: The field/key where conflict occurred.
            new_agent: Agent ID providing the new value.
            new_value: The conflicting new value.
            existing_value: The existing value being overwritten.
        """
        # Find existing conflict or create new
        existing_conflict = None
        for c in self._conflicts:
            if c.key == key:
                existing_conflict = c
                break

        if existing_conflict:
            existing_conflict.agents.append(new_agent)
            existing_conflict.values.append(new_value)
        else:
            conflict = ConflictInfo(
                key=key,
                agents=["previous", new_agent],
                values=[existing_value, new_value],
            )
            self._conflicts.append(conflict)

        # Try to resolve
        if self.conflict_resolver:
            try:
                resolved = self.conflict_resolver(self._conflicts[-1])
                self._conflicts[-1].resolved_value = resolved
                self._conflicts[-1].resolution = "custom_resolver"
            except Exception as e:
                logger.warning(f"Conflict resolver failed: {e}")

    def _calculate_confidence(self, results: dict[str, ContextAgentResult]) -> float:
        """
        Calculate overall confidence from agent results.

        Computes average confidence with a penalty for conflicts.

        Args:
            results: Valid results to average.

        Returns:
            float: Overall confidence score (0.0 to 1.0).
        """
        if not results:
            return 0.0

        confidences = [r.confidence for r in results.values()]
        avg_confidence = sum(confidences) / len(confidences)

        # Reduce if there are conflicts
        conflict_penalty = len(self._conflicts) * 0.05
        return max(0.0, avg_confidence - conflict_penalty)

    # =========================================================================
    # Utilities
    # =========================================================================

    def get_results(self) -> dict[str, ContextAgentResult]:
        """
        Get all agent results added to this aggregator.

        Returns a copy to prevent external modification.

        Returns:
            dict[str, ContextAgentResult]: Map of agent_id to result.

        Example:
            >>> results = aggregator.get_results()
            >>> for agent_id, result in results.items():
            ...     print(f"{agent_id}: {result.confidence:.0%}")
        """
        return self._results.copy()

    def get_conflicts(self) -> list[ConflictInfo]:
        """
        Get all detected conflicts.

        Returns a copy to prevent external modification.
        Conflicts are detected during MERGE strategy when
        different agents provide different values for the same key.

        Returns:
            list[ConflictInfo]: List of all conflicts.

        Example:
            >>> conflicts = aggregator.get_conflicts()
            >>> for c in conflicts:
            ...     print(f"Conflict on '{c.key}': {c.values}")
        """
        return self._conflicts.copy()

    def clear(self) -> None:
        """
        Clear all results and conflicts.

        Resets the aggregator to its initial empty state.
        Useful for reusing the same aggregator instance.

        Example:
            >>> aggregator.clear()
            >>> len(aggregator.get_results())
            0
        """
        self._results.clear()
        self._conflicts.clear()

    def __repr__(self) -> str:
        """Return string representation of the aggregator."""
        return (
            f"ResultAggregator("
            f"strategy={self.strategy.value}, "
            f"results={len(self._results)}, "
            f"conflicts={len(self._conflicts)})"
        )
