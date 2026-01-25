"""
Result Aggregator - Synthesizes outputs from isolated agent contexts.

After agents execute in isolation, the aggregator collects their results
and produces a unified output using various strategies.

Strategies:
1. SYNTHESIZE - Use LLM to create a narrative combining all results
2. MERGE - Deep merge structured data (JSON/dicts)
3. PRIORITIZE - Use ranking/confidence to select best result
4. VOTE - Majority voting for discrete answers
5. CHAIN - Sequential refinement (each result builds on previous)
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
    """Strategy for combining agent results."""

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
class AgentResult:
    """Result from a single agent."""

    agent_id: str
    data: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 1.0
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def is_valid(self) -> bool:
        """Check if result is valid (no error, has data)."""
        return self.error is None and self.data is not None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "priority": self.priority,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class ConflictInfo:
    """Information about a conflict between agent results."""

    key: str
    agents: list[str]
    values: list[Any]
    resolution: str | None = None
    resolved_value: Any = None


@dataclass
class AggregatedResult:
    """Final aggregated result from all agents."""

    data: Any
    strategy: AggregationStrategy
    agent_contributions: dict[str, Any]
    conflicts: list[ConflictInfo]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
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

    Example:
        aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)

        # Add results from each agent
        for agent in team:
            aggregator.add_result(
                agent_id=agent.id,
                data=agent.namespace.get_result(),
                confidence=agent.namespace.get_metadata().get("confidence", 1.0),
            )

        # Aggregate with LLM synthesis
        final = await aggregator.aggregate(llm=llm_client)
        print(final.data)

    Attributes:
        strategy: How to combine results
        conflict_resolver: Custom function to resolve conflicts
    """

    def __init__(
        self,
        strategy: AggregationStrategy = AggregationStrategy.SYNTHESIZE,
        conflict_resolver: Callable[[ConflictInfo], Any] | None = None,
    ):
        """
        Initialize aggregator.

        Args:
            strategy: How to combine results
            conflict_resolver: Custom function to resolve conflicts
        """
        self.strategy = strategy
        self.conflict_resolver = conflict_resolver

        self._results: dict[str, AgentResult] = {}
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

        Args:
            agent_id: Agent that produced this result
            data: The result data
            confidence: Confidence score (0-1)
            priority: Priority for PRIORITIZE strategy
            metadata: Additional metadata
            error: Error message if agent failed
        """
        self._results[agent_id] = AgentResult(
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
        Add result directly from agent namespace.

        Args:
            agent_id: Agent ID
            namespace: The agent's namespace
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

        Args:
            llm: LLM client (required for SYNTHESIZE strategy)
            prompt_template: Custom prompt for synthesis

        Returns:
            AggregatedResult with combined data
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
        results: dict[str, AgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> Any:
        """Synthesize results using LLM."""
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
        results: dict[str, AgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> dict[str, Any]:
        """Deep merge structured results."""
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
        results: dict[str, AgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> Any:
        """Select highest priority/confidence result."""
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
        results: dict[str, AgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> Any:
        """Majority voting for discrete answers."""
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
        results: dict[str, AgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> Any:
        """Chain results sequentially (order by priority)."""
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
        results: dict[str, AgentResult],
        llm: "LLMGatewayClient | None",
        prompt_template: str | None,
    ) -> str:
        """Simple concatenation of text results."""
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
        """Handle a conflict between agent values."""
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

    def _calculate_confidence(self, results: dict[str, AgentResult]) -> float:
        """Calculate overall confidence from agent results."""
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

    def get_results(self) -> dict[str, AgentResult]:
        """Get all agent results."""
        return self._results.copy()

    def get_conflicts(self) -> list[ConflictInfo]:
        """Get all detected conflicts."""
        return self._conflicts.copy()

    def clear(self) -> None:
        """Clear all results and conflicts."""
        self._results.clear()
        self._conflicts.clear()

    def __repr__(self) -> str:
        return (
            f"ResultAggregator("
            f"strategy={self.strategy.value}, "
            f"results={len(self._results)}, "
            f"conflicts={len(self._conflicts)})"
        )
