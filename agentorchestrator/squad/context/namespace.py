"""
Agent Context Namespace - Isolated context for each sub-agent.

Each agent in a multi-agent system gets its own namespace that:
1. Isolates its working data from other agents
2. Controls what data it can see from the coordinator
3. Captures results for aggregation
4. Tracks metadata for tracing/debugging

This prevents "context pollution" where Agent A's intermediate data
accidentally influences Agent B's reasoning.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agentorchestrator.core.context import ChainContext

logger = logging.getLogger(__name__)

# Context variable to track current namespace
_current_namespace: ContextVar[str | None] = ContextVar("current_namespace", default=None)


class IsolationLevel(str, Enum):
    """How isolated the agent's context is from the coordinator."""

    FULL = "full"
    """Agent sees ONLY its own data + explicitly shared keys."""

    PARTIAL = "partial"
    """Agent sees own data + all coordinator CHAIN-scoped data (read-only)."""

    NONE = "none"
    """No isolation - agent shares context with coordinator (legacy mode)."""


@dataclass
class NamespaceSnapshot:
    """Point-in-time snapshot of namespace state for debugging."""

    agent_id: str
    timestamp: datetime
    local_store_keys: list[str]
    shared_keys: list[str]
    result_count: int
    metadata: dict[str, Any]


class AgentContextNamespace:
    """
    Isolated context namespace for a sub-agent.

    Each agent operates within its own namespace, preventing context leakage
    between agents while allowing controlled data sharing through the coordinator.

    Example:
        # Coordinator creates namespace for agent
        namespace = AgentContextNamespace(
            agent_id="research_agent",
            parent_context=coordinator_ctx,
            isolation_level=IsolationLevel.FULL,
        )

        # Agent operates within namespace
        async with namespace:
            namespace.set("findings", research_results)
            namespace.set_result(final_answer)

        # Coordinator retrieves result
        result = namespace.get_result()

    Attributes:
        agent_id: Unique identifier for this agent
        parent_context: Reference to coordinator's ChainContext
        isolation_level: How much parent context the agent can see
    """

    def __init__(
        self,
        agent_id: str,
        parent_context: "ChainContext | None" = None,
        isolation_level: IsolationLevel = IsolationLevel.FULL,
        max_local_items: int = 1000,
    ):
        """
        Initialize agent namespace.

        Args:
            agent_id: Unique identifier for this agent
            parent_context: Coordinator's ChainContext (for shared data access)
            isolation_level: How isolated this namespace is
            max_local_items: Maximum items in local store (prevents memory leaks)
        """
        self.agent_id = agent_id
        self.parent_context = parent_context
        self.isolation_level = isolation_level
        self.max_local_items = max_local_items

        # Agent's private storage (not visible to other agents)
        self._local_store: dict[str, Any] = {}

        # Keys from parent that this agent can see
        self._shared_keys: set[str] = set()

        # Keys this agent has published to be shared with others
        self._published_keys: set[str] = set()

        # Agent's results (for aggregation)
        self._results: list[Any] = []

        # Execution metadata
        self._metadata: dict[str, Any] = {
            "created_at": datetime.utcnow().isoformat(),
            "agent_id": agent_id,
            "isolation_level": isolation_level.value,
        }

        # Timing
        self._start_time: float | None = None
        self._end_time: float | None = None

        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "AgentContextNamespace":
        """Enter namespace scope (async context manager)."""
        self._start_time = time.perf_counter()
        _current_namespace.set(self.agent_id)
        logger.debug(f"Entered namespace: {self.agent_id}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit namespace scope."""
        self._end_time = time.perf_counter()
        self._metadata["duration_ms"] = (self._end_time - self._start_time) * 1000
        _current_namespace.set(None)
        logger.debug(f"Exited namespace: {self.agent_id} ({self._metadata['duration_ms']:.1f}ms)")

    def __enter__(self) -> "AgentContextNamespace":
        """Enter namespace scope (sync context manager)."""
        self._start_time = time.perf_counter()
        _current_namespace.set(self.agent_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit namespace scope."""
        self._end_time = time.perf_counter()
        self._metadata["duration_ms"] = (self._end_time - self._start_time) * 1000
        _current_namespace.set(None)

    # =========================================================================
    # Local Storage (Agent's Private Data)
    # =========================================================================

    def set(self, key: str, value: Any) -> None:
        """
        Store data in agent's local namespace.

        This data is NOT visible to other agents or the coordinator
        unless explicitly published.

        Args:
            key: Storage key
            value: Data to store
        """
        if len(self._local_store) >= self.max_local_items and key not in self._local_store:
            logger.warning(
                f"Namespace {self.agent_id} at capacity ({self.max_local_items} items). "
                f"Rejecting key: {key}"
            )
            return

        self._local_store[key] = value
        logger.debug(f"[{self.agent_id}] Set local: {key}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get data from namespace.

        Checks in order:
        1. Local store (agent's private data)
        2. Shared keys from parent (if isolation allows)

        Args:
            key: Key to retrieve
            default: Default if not found

        Returns:
            Value or default
        """
        # Check local first
        if key in self._local_store:
            return self._local_store[key]

        # Check shared keys from parent
        if self.isolation_level != IsolationLevel.NONE and key in self._shared_keys:
            if self.parent_context:
                return self.parent_context.get(key, default)

        # In PARTIAL mode, can see all parent CHAIN data
        if self.isolation_level == IsolationLevel.PARTIAL and self.parent_context:
            return self.parent_context.get(key, default)

        return default

    def has(self, key: str) -> bool:
        """Check if key exists in namespace."""
        if key in self._local_store:
            return True
        if key in self._shared_keys and self.parent_context:
            return self.parent_context.has(key)
        return False

    def delete(self, key: str) -> bool:
        """Delete key from local store."""
        if key in self._local_store:
            del self._local_store[key]
            return True
        return False

    def clear_local(self) -> None:
        """Clear all local data (keeps shared key access)."""
        self._local_store.clear()
        logger.debug(f"[{self.agent_id}] Cleared local store")

    def keys(self) -> list[str]:
        """Get all accessible keys."""
        local_keys = list(self._local_store.keys())
        shared = list(self._shared_keys)
        return local_keys + shared

    # =========================================================================
    # Shared Data (Coordinator-Mediated)
    # =========================================================================

    def grant_access(self, key: str) -> None:
        """
        Grant this namespace access to a parent context key.

        Called by ContextIsolationManager when coordinator shares data.

        Args:
            key: Parent context key to make visible
        """
        self._shared_keys.add(key)
        logger.debug(f"[{self.agent_id}] Granted access to: {key}")

    def revoke_access(self, key: str) -> None:
        """Revoke access to a shared key."""
        self._shared_keys.discard(key)

    def publish(self, key: str, value: Any) -> None:
        """
        Publish data to be shared with other agents (via coordinator).

        The coordinator decides if/how to share this with other agents.

        Args:
            key: Key to publish under
            value: Data to share
        """
        if self.parent_context:
            # Store in parent with agent prefix for tracing
            parent_key = f"{self.agent_id}:{key}"
            self.parent_context.set(parent_key, value)
            self._published_keys.add(key)
            logger.debug(f"[{self.agent_id}] Published: {key}")

    # =========================================================================
    # Results (For Aggregation)
    # =========================================================================

    def set_result(self, result: Any, metadata: dict[str, Any] | None = None) -> None:
        """
        Store agent's final result for aggregation.

        Args:
            result: The agent's output/answer
            metadata: Optional metadata about the result
        """
        self._results.append(result)
        if metadata:
            self._metadata.update(metadata)
        logger.debug(f"[{self.agent_id}] Set result #{len(self._results)}")

    def get_result(self) -> Any | None:
        """Get agent's most recent result."""
        return self._results[-1] if self._results else None

    def get_all_results(self) -> list[Any]:
        """Get all results (for multi-step agents)."""
        return self._results.copy()

    # =========================================================================
    # Metadata & Debugging
    # =========================================================================

    def get_metadata(self) -> dict[str, Any]:
        """
        Get execution metadata for tracing.

        Returns:
            Dict with agent_id, timing, result count, etc.
        """
        return {
            **self._metadata,
            "result_count": len(self._results),
            "local_store_size": len(self._local_store),
            "shared_keys_count": len(self._shared_keys),
            "published_keys": list(self._published_keys),
        }

    def snapshot(self) -> NamespaceSnapshot:
        """
        Take a snapshot of current namespace state.

        Useful for debugging and auditing.
        """
        return NamespaceSnapshot(
            agent_id=self.agent_id,
            timestamp=datetime.utcnow(),
            local_store_keys=list(self._local_store.keys()),
            shared_keys=list(self._shared_keys),
            result_count=len(self._results),
            metadata=self._metadata.copy(),
        )

    def __repr__(self) -> str:
        return (
            f"AgentContextNamespace("
            f"agent_id={self.agent_id!r}, "
            f"isolation={self.isolation_level.value}, "
            f"local_keys={len(self._local_store)}, "
            f"results={len(self._results)})"
        )


def get_current_namespace() -> str | None:
    """Get the current namespace ID (if within a namespace context)."""
    return _current_namespace.get()
