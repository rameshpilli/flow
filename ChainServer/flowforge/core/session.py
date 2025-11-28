"""
FlowForge Session Management

Provides MCP session pooling and reuse for efficient agent communication.
Based on patterns from the existing ChainServer implementation.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    """Configuration for an MCP session"""

    name: str
    server_url: str
    bearer_token: str | None = None
    tool_name: str = "search"
    headers: dict[str, str] = field(default_factory=dict)
    timeout_ms: int = 30000


class MCPSessionPool:
    """
    Pool for reusing MCP sessions across multiple queries.

    This is critical for performance - creating a new session per query
    is expensive. Reuse sessions like the existing code does.

    Usage:
        pool = MCPSessionPool()

        async with pool.get_session(config) as session:
            result = await session.call_tool("search", {"query": "..."})
    """

    def __init__(self, max_sessions_per_agent: int = 5):
        self.max_sessions = max_sessions_per_agent
        self._sessions: dict[str, list[Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, agent_name: str) -> asyncio.Lock:
        if agent_name not in self._locks:
            self._locks[agent_name] = asyncio.Lock()
        return self._locks[agent_name]

    @asynccontextmanager
    async def get_session(self, config: SessionConfig):
        """Get or create a session for an agent"""
        # For now, create a new session each time
        # In production, implement actual pooling
        try:
            # Import MCP client (optional dependency)
            from mcp.client.session import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            headers = {**config.headers}
            if config.bearer_token:
                headers["Authorization"] = f"Bearer {config.bearer_token}"

            async with streamablehttp_client(config.server_url, headers=headers) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

        except ImportError:
            # MCP not installed - yield mock session
            logger.warning("MCP client not installed, using mock session")
            yield MockMCPSession()
        except Exception as e:
            logger.error(f"Failed to create MCP session for {config.name}: {e}")
            raise


class MockMCPSession:
    """Mock MCP session for testing without MCP dependency"""

    async def initialize(self):
        pass

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return {"content": [{"text": f"Mock response for {name}"}]}


class AgentSessionManager:
    """
    Manages sessions for multiple agents with parallel execution support.

    Pattern from existing code:
    - Reuse single MCP session per agent for all subqueries
    - Execute multiple agents in parallel
    - Collect errors per agent without failing fast
    """

    def __init__(self):
        self.pool = MCPSessionPool()
        self._agent_configs: dict[str, SessionConfig] = {}

    def register_agent_session(self, config: SessionConfig) -> None:
        """Register an agent's session configuration"""
        self._agent_configs[config.name] = config

    async def execute_parallel(
        self,
        queries_by_agent: dict[str, list[dict]],
        collect_errors: bool = True,
    ) -> tuple:
        """
        Execute queries across multiple agents in parallel.

        Args:
            queries_by_agent: Dict mapping agent names to list of queries
            collect_errors: If True, collect errors instead of failing fast

        Returns:
            (results_by_agent, errors_by_agent) tuple
        """
        results = {agent: [] for agent in queries_by_agent}
        errors = {agent: [] for agent in queries_by_agent}

        async def execute_agent_queries(agent_name: str, queries: list[dict]):
            config = self._agent_configs.get(agent_name)
            if not config:
                errors[agent_name].append(f"No session config for agent: {agent_name}")
                return

            try:
                async with self.pool.get_session(config) as session:
                    for query in queries:
                        try:
                            result = await session.call_tool(config.tool_name, query)
                            content = (
                                result.model_dump().get("content", [])
                                if hasattr(result, "model_dump")
                                else result.get("content", [])
                            )
                            results[agent_name].extend(content if content else [])
                        except Exception as e:
                            msg = f"Query failed for {agent_name}: {query} - {e}"
                            logger.error(msg)
                            if collect_errors:
                                errors[agent_name].append(msg)
                            else:
                                raise
            except Exception as e:
                msg = f"Session failed for {agent_name}: {e}"
                logger.error(msg)
                if collect_errors:
                    errors[agent_name].append(msg)
                else:
                    raise

        # Execute all agents in parallel
        tasks = [
            execute_agent_queries(agent, queries) for agent, queries in queries_by_agent.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=collect_errors)

        return results, errors


# Singleton for convenience
_session_manager: AgentSessionManager | None = None


def get_session_manager() -> AgentSessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = AgentSessionManager()
    return _session_manager
