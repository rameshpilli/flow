"""
Context Isolation Manager - Orchestrates isolated agent namespaces.

The manager sits between the coordinator (SupervisorAgent) and sub-agents,
creating isolated namespaces and mediating all data sharing.

Key responsibilities:
1. Create isolated namespaces for each agent
2. Control what data flows between agents
3. Enforce isolation boundaries
4. Track provenance of shared data
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, TYPE_CHECKING

from agentorchestrator.squad.context.namespace import (
    AgentContextNamespace,
    IsolationLevel,
)

if TYPE_CHECKING:
    from agentorchestrator.core.context import ChainContext

logger = logging.getLogger(__name__)


@dataclass
class SharedDataEntry:
    """Tracks shared data between agents."""

    key: str
    value: Any
    source_agent: str
    target_agents: list[str]
    shared_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IsolationConfig:
    """Configuration for isolation behavior."""

    default_isolation_level: IsolationLevel = IsolationLevel.FULL
    max_shared_keys_per_agent: int = 100
    enable_provenance_tracking: bool = True
    auto_share_request_data: bool = True
    request_data_keys: list[str] = field(default_factory=lambda: ["query", "user_id", "session_id"])


class ContextIsolationManager:
    """
    Manages context isolation for multi-agent execution.

    Creates and manages isolated namespaces for each sub-agent, mediates
    data sharing, and enforces isolation boundaries.

    Example:
        # Supervisor creates isolation manager
        isolation = ContextIsolationManager(coordinator_context=ctx)

        # Create namespaces for team
        for agent in team:
            namespace = isolation.create_namespace(agent.id)
            agent.namespace = namespace

        # Share request data with all agents
        isolation.share_with_all("query", user_query)

        # Execute agents with isolation
        async with isolation.execute_parallel(agents, process_fn) as results:
            for agent_id, result in results.items():
                print(f"{agent_id}: {result}")

        # Selective sharing between agents
        isolation.share_between(
            source_agent="researcher",
            key="findings",
            target_agents=["writer", "reviewer"],
        )
    """

    def __init__(
        self,
        coordinator_context: "ChainContext | None" = None,
        config: IsolationConfig | None = None,
    ):
        """
        Initialize isolation manager.

        Args:
            coordinator_context: The supervisor's ChainContext
            config: Isolation configuration
        """
        self.coordinator_context = coordinator_context
        self.config = config or IsolationConfig()

        # Agent namespaces
        self._namespaces: dict[str, AgentContextNamespace] = {}

        # Shared data tracking
        self._shared_data: dict[str, SharedDataEntry] = {}

        # Execution tracking
        self._execution_id: str | None = None
        self._started_at: datetime | None = None

    def create_namespace(
        self,
        agent_id: str,
        isolation_level: IsolationLevel | None = None,
    ) -> AgentContextNamespace:
        """
        Create an isolated namespace for an agent.

        Args:
            agent_id: Unique identifier for the agent
            isolation_level: Override default isolation level

        Returns:
            New AgentContextNamespace

        Raises:
            ValueError: If namespace already exists for agent_id
        """
        if agent_id in self._namespaces:
            raise ValueError(f"Namespace already exists for agent: {agent_id}")

        level = isolation_level or self.config.default_isolation_level

        namespace = AgentContextNamespace(
            agent_id=agent_id,
            parent_context=self.coordinator_context,
            isolation_level=level,
        )

        self._namespaces[agent_id] = namespace
        logger.info(f"Created namespace for {agent_id} (isolation={level.value})")

        # Auto-share request data if configured
        if self.config.auto_share_request_data and self.coordinator_context:
            for key in self.config.request_data_keys:
                if self.coordinator_context.has(key):
                    namespace.grant_access(key)

        return namespace

    def get_namespace(self, agent_id: str) -> AgentContextNamespace | None:
        """Get namespace for an agent."""
        return self._namespaces.get(agent_id)

    def has_namespace(self, agent_id: str) -> bool:
        """Check if agent has a namespace."""
        return agent_id in self._namespaces

    def list_namespaces(self) -> list[str]:
        """List all agent IDs with namespaces."""
        return list(self._namespaces.keys())

    # =========================================================================
    # Data Sharing
    # =========================================================================

    def share_with_all(
        self,
        key: str,
        value: Any | None = None,
        source_agent: str = "coordinator",
    ) -> None:
        """
        Share data with all agents.

        Args:
            key: Key to share
            value: Value to share (if None, shares existing coordinator value)
            source_agent: Who is sharing this data
        """
        # Store in coordinator context if value provided
        if value is not None and self.coordinator_context:
            self.coordinator_context.set(key, value)

        # Grant access to all namespaces
        target_agents = []
        for agent_id, namespace in self._namespaces.items():
            namespace.grant_access(key)
            target_agents.append(agent_id)

        # Track sharing
        if self.config.enable_provenance_tracking:
            self._shared_data[key] = SharedDataEntry(
                key=key,
                value=value,
                source_agent=source_agent,
                target_agents=target_agents,
            )

        logger.debug(f"Shared '{key}' with all agents ({len(target_agents)} agents)")

    def share_between(
        self,
        source_agent: str,
        key: str,
        target_agents: list[str],
        value: Any | None = None,
    ) -> None:
        """
        Share data from one agent to specific other agents.

        The coordinator mediates this - source agent publishes, coordinator
        decides who can see it.

        Args:
            source_agent: Agent that created the data
            key: Key to share
            target_agents: List of agent IDs that should see this
            value: Value to share (if None, pulls from source agent's namespace)
        """
        # Get value from source namespace if not provided
        if value is None:
            source_ns = self._namespaces.get(source_agent)
            if source_ns:
                value = source_ns.get(key)

        if value is None:
            logger.warning(f"Cannot share '{key}' - no value found")
            return

        # Store in coordinator with prefixed key
        shared_key = f"shared:{source_agent}:{key}"
        if self.coordinator_context:
            self.coordinator_context.set(shared_key, value)

        # Grant access to target namespaces
        for agent_id in target_agents:
            if agent_id in self._namespaces:
                self._namespaces[agent_id].grant_access(shared_key)

        # Track
        if self.config.enable_provenance_tracking:
            self._shared_data[shared_key] = SharedDataEntry(
                key=key,
                value=value,
                source_agent=source_agent,
                target_agents=target_agents,
            )

        logger.debug(f"Shared '{key}' from {source_agent} to {target_agents}")

    def revoke_sharing(self, key: str, agent_ids: list[str] | None = None) -> None:
        """
        Revoke access to shared data.

        Args:
            key: Key to revoke
            agent_ids: Specific agents to revoke from (None = all)
        """
        targets = agent_ids or list(self._namespaces.keys())
        for agent_id in targets:
            if agent_id in self._namespaces:
                self._namespaces[agent_id].revoke_access(key)

    # =========================================================================
    # Execution Helpers
    # =========================================================================

    @asynccontextmanager
    async def execute_parallel(
        self,
        agents: list[Any],
        process_fn: Callable,
        *args,
        **kwargs,
    ):
        """
        Execute agents in parallel with isolated contexts.

        Args:
            agents: List of agents (must have .id attribute)
            process_fn: Async function to call for each agent
            *args, **kwargs: Passed to process_fn

        Yields:
            Dict mapping agent_id to result

        Example:
            async def process_agent(agent, query, namespace):
                async with namespace:
                    return await agent.process(query)

            async with isolation.execute_parallel(team, process_agent, query) as results:
                for agent_id, result in results.items():
                    print(f"{agent_id}: {result}")
        """
        self._started_at = datetime.utcnow()

        # Ensure all agents have namespaces
        for agent in agents:
            if not self.has_namespace(agent.id):
                self.create_namespace(agent.id)

        # Execute in parallel
        async def _run_agent(agent):
            namespace = self._namespaces[agent.id]
            async with namespace:
                return await process_fn(agent, *args, namespace=namespace, **kwargs)

        tasks = [_run_agent(agent) for agent in agents]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Map results to agent IDs
        results = {}
        for agent, result in zip(agents, results_list):
            if isinstance(result, Exception):
                logger.error(f"Agent {agent.id} failed: {result}")
                results[agent.id] = None
                self._namespaces[agent.id]._metadata["error"] = str(result)
            else:
                results[agent.id] = result

        yield results

    def get_all_results(self) -> dict[str, Any]:
        """Get results from all namespaces."""
        return {
            agent_id: ns.get_result()
            for agent_id, ns in self._namespaces.items()
        }

    def get_all_metadata(self) -> dict[str, dict]:
        """Get metadata from all namespaces."""
        return {
            agent_id: ns.get_metadata()
            for agent_id, ns in self._namespaces.items()
        }

    # =========================================================================
    # Introspection
    # =========================================================================

    def get_sharing_graph(self) -> dict[str, list[str]]:
        """
        Get graph of data sharing between agents.

        Returns:
            Dict mapping source_agent -> [target_agents]
        """
        graph: dict[str, list[str]] = {}
        for entry in self._shared_data.values():
            if entry.source_agent not in graph:
                graph[entry.source_agent] = []
            graph[entry.source_agent].extend(entry.target_agents)
        return graph

    def get_shared_data_provenance(self) -> list[SharedDataEntry]:
        """Get all shared data entries for auditing."""
        return list(self._shared_data.values())

    def get_stats(self) -> dict[str, Any]:
        """Get isolation statistics."""
        return {
            "namespace_count": len(self._namespaces),
            "shared_keys_count": len(self._shared_data),
            "namespaces": {
                agent_id: {
                    "isolation_level": ns.isolation_level.value,
                    "local_store_size": len(ns._local_store),
                    "shared_keys": len(ns._shared_keys),
                    "result_count": len(ns._results),
                }
                for agent_id, ns in self._namespaces.items()
            },
            "started_at": self._started_at.isoformat() if self._started_at else None,
        }

    # =========================================================================
    # Cleanup
    # =========================================================================

    def clear_namespace(self, agent_id: str) -> None:
        """Clear an agent's namespace (keeps the namespace, clears data)."""
        if agent_id in self._namespaces:
            self._namespaces[agent_id].clear_local()

    def remove_namespace(self, agent_id: str) -> None:
        """Remove an agent's namespace entirely."""
        if agent_id in self._namespaces:
            del self._namespaces[agent_id]
            logger.debug(f"Removed namespace: {agent_id}")

    def clear_all(self) -> None:
        """Clear all namespaces and shared data."""
        self._namespaces.clear()
        self._shared_data.clear()
        logger.info("Cleared all namespaces")

    def __repr__(self) -> str:
        return (
            f"ContextIsolationManager("
            f"namespaces={len(self._namespaces)}, "
            f"shared_keys={len(self._shared_data)})"
        )