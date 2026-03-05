"""MCP Service Manager for application-level lifecycle management.

This module provides MCPServiceManager for managing MCP adapter lifecycle in
long-running applications (like FastAPI servers). It solves the problem of
async context management across different event loops and lifespan events.

Key features:
- Adapter registry for centralized management
- Startup/shutdown hooks for proper lifecycle
- Health checks for monitoring
- Auto-discovery from environment configuration
- FastAPI lifespan integration

Example with FastAPI:
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from agentorchestrator.services.mcp_service import MCPServiceManager

    mcp_service = MCPServiceManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: Initialize MCP adapters
        await mcp_service.startup()
        yield
        # Shutdown: Clean up MCP adapters
        await mcp_service.shutdown()

    app = FastAPI(lifespan=lifespan)

    @app.get("/health/mcp")
    async def mcp_health():
        return await mcp_service.health_check()

    @app.post("/analyze")
    async def analyze(query: str):
        # Get adapters from service
        adapters = mcp_service.get_all_adapters()
        # Use adapters...
"""

import logging
import os
from typing import Dict, List, Optional

from agentorchestrator.utils.mcp_adapters import create_selected_adapters
from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter

logger = logging.getLogger(__name__)


class MCPServiceManager:
    """Application-level MCP service manager for lifecycle management.

    Manages MCP adapter lifecycle in long-running applications. Handles:
    - Adapter creation and registration at startup
    - Proper cleanup at shutdown
    - Centralized adapter registry
    - Health checks for monitoring
    - Auto-discovery from environment config

    Solves async context issues by creating adapters once at startup and
    keeping them alive for the application lifetime, then cleaning up at
    shutdown.

    Attributes:
        adapters: Registry of adapter_name -> MCPToolAdapter
        _started: Flag indicating if service has been started

    Example:
        # Create service manager
        mcp_service = MCPServiceManager()

        # Startup (call once at app start)
        await mcp_service.startup()

        # Use adapters during app lifetime
        ravenpack = mcp_service.get_adapter("RavenPack News")
        if ravenpack:
            tools = await ravenpack.get_tool_functions()

        # Or get all adapters
        all_adapters = mcp_service.get_all_adapters()

        # Shutdown (call once at app shutdown)
        await mcp_service.shutdown()
    """

    def __init__(self):
        """Initialize the MCP service manager."""
        self.adapters: Dict[str, MCPToolAdapter] = {}
        self._started: bool = False
        logger.info("MCPServiceManager initialized")

    def _discover_agent_names_from_env(self) -> List[str]:
        """Discover agent names from environment variables.

        Scans environment for MCP_{AGENT_NAME}_ENDPOINT patterns and
        extracts agent names.

        Returns:
            List of discovered agent names (denormalized from env var names)
        """
        agent_names = []
        seen_keys = set()

        for key in os.environ.keys():
            # Look for MCP_{NAME}_ENDPOINT or {NAME}_MCP_ENDPOINT
            if key.startswith("MCP_") and key.endswith("_ENDPOINT"):
                # Extract: MCP_NEWS_SERVICE_ENDPOINT -> NEWS_SERVICE
                agent_key = key[4:-9]  # Remove "MCP_" prefix and "_ENDPOINT" suffix
                if agent_key and agent_key not in seen_keys:
                    # Denormalize: NEWS_SERVICE -> News Service
                    agent_name = agent_key.replace("_", " ").title()
                    agent_names.append(agent_name)
                    seen_keys.add(agent_key)

            elif key.endswith("_MCP_ENDPOINT"):
                # Extract: NEWS_SERVICE_MCP_ENDPOINT -> NEWS_SERVICE
                agent_key = key[:-13]  # Remove "_MCP_ENDPOINT" suffix
                if agent_key and agent_key not in seen_keys:
                    agent_name = agent_key.replace("_", " ").title()
                    agent_names.append(agent_name)
                    seen_keys.add(agent_key)

        if agent_names:
            logger.info(f"Auto-discovered {len(agent_names)} agent(s) from environment: {agent_names}")

        return agent_names

    async def startup(
        self,
        agent_names: Optional[List[str]] = None,
        agent_configs: Optional[dict] = None,
    ) -> None:
        """Start the MCP service and initialize adapters.

        Args:
            agent_names: Optional list of agent names to create adapters for.
                        If None, discovers all configured agents from environment.
                        Example: ["News", "Financial Data", "Analytics"]
            agent_configs: Optional explicit configs for agents (bypasses env lookup).
                          Format: {"Agent Name": {"endpoint": "...", "secret": "..."}}

        Example:
            # Create specific adapters
            await mcp_service.startup(agent_names=["News", "Finance"])

            # Discover all configured agents from environment
            await mcp_service.startup()  # Looks for MCP_*_ENDPOINT vars

            # Use explicit configs
            configs = {"News": {"endpoint": "...", "secret": "..."}}
            await mcp_service.startup(agent_configs=configs)

            # Manual registration (skip auto-creation)
            await mcp_service.startup(agent_names=[])
            # Then call mcp_service.register_adapter(adapter)
        """
        if self._started:
            logger.warning("MCPServiceManager already started, skipping startup")
            return

        logger.info("Starting MCPServiceManager...")

        # If agent_names is None, auto-discover from environment
        if agent_names is None:
            agent_names = self._discover_agent_names_from_env()
            if not agent_names:
                logger.warning(
                    "No MCP agents found in environment. "
                    "Set MCP_{AGENT_NAME}_ENDPOINT variables or pass agent_names explicitly."
                )

        # Create adapters for specified agents
        if agent_names:
            try:
                adapters = await create_selected_adapters(agent_names, agent_configs)
                for adapter in adapters:
                    self.register_adapter(adapter)

                logger.info(
                    f"MCPServiceManager started with {len(self.adapters)} adapter(s)"
                )
            except Exception as e:
                logger.error(f"Failed to create MCP adapters: {e}")
                raise
        else:
            logger.info("MCPServiceManager started (manual adapter registration)")

        self._started = True

    async def shutdown(self) -> None:
        """Shutdown the MCP service and clean up adapters.

        Disconnects all registered adapters and clears the registry.
        Safe to call multiple times.

        Example:
            await mcp_service.shutdown()
        """
        if not self._started:
            logger.warning("MCPServiceManager not started, skipping shutdown")
            return

        logger.info(f"Shutting down MCPServiceManager ({len(self.adapters)} adapters)...")

        # Disconnect all adapters
        for name, adapter in self.adapters.items():
            try:
                await adapter.disconnect()
                logger.info(f"Disconnected adapter: {name}")
            except Exception as e:
                logger.error(f"Error disconnecting adapter {name}: {e}")

        # Clear registry
        self.adapters.clear()
        self._started = False

        logger.info("MCPServiceManager shutdown complete")

    def register_adapter(self, adapter: MCPToolAdapter) -> None:
        """Register an MCP adapter with the service.

        Args:
            adapter: Connected MCPToolAdapter instance

        Example:
            adapter = await create_ravenpack_news_adapter()
            if adapter:
                mcp_service.register_adapter(adapter)
        """
        if adapter.name in self.adapters:
            logger.warning(f"Adapter {adapter.name} already registered, replacing")

        self.adapters[adapter.name] = adapter
        logger.info(f"Registered adapter: {adapter.name}")

    def unregister_adapter(self, adapter_name: str) -> Optional[MCPToolAdapter]:
        """Unregister an MCP adapter from the service.

        Args:
            adapter_name: Name of the adapter to unregister

        Returns:
            The unregistered adapter, or None if not found

        Note:
            This does NOT disconnect the adapter. Call adapter.disconnect()
            separately if needed.

        Example:
            adapter = mcp_service.unregister_adapter("RavenPack News")
            if adapter:
                await adapter.disconnect()
        """
        adapter = self.adapters.pop(adapter_name, None)
        if adapter:
            logger.info(f"Unregistered adapter: {adapter_name}")
        else:
            logger.warning(f"Adapter not found: {adapter_name}")

        return adapter

    def get_adapter(self, adapter_name: str) -> Optional[MCPToolAdapter]:
        """Get a registered adapter by name.

        Args:
            adapter_name: Name of the adapter to retrieve

        Returns:
            The adapter if found, None otherwise

        Example:
            ravenpack = mcp_service.get_adapter("RavenPack News")
            if ravenpack:
                tools = await ravenpack.get_tool_functions()
        """
        return self.adapters.get(adapter_name)

    def get_all_adapters(self) -> List[MCPToolAdapter]:
        """Get all registered adapters.

        Returns:
            List of all registered MCPToolAdapter instances

        Example:
            adapters = mcp_service.get_all_adapters()
            all_tools = []
            for adapter in adapters:
                tools = await adapter.get_tool_functions()
                all_tools.extend(tools)
        """
        return list(self.adapters.values())

    def list_adapter_names(self) -> List[str]:
        """Get names of all registered adapters.

        Returns:
            List of adapter names

        Example:
            names = mcp_service.list_adapter_names()
            print(f"Available adapters: {', '.join(names)}")
        """
        return list(self.adapters.keys())

    async def health_check(self) -> Dict[str, any]:
        """Check health status of MCP service and adapters.

        Returns:
            Dictionary with health status information:
            {
                "status": "healthy" | "degraded" | "unhealthy",
                "started": bool,
                "adapter_count": int,
                "adapters": {
                    "adapter_name": {
                        "connected": bool,
                        "tool_count": int
                    }
                }
            }

        Example:
            health = await mcp_service.health_check()
            if health["status"] != "healthy":
                logger.warning(f"MCP service health: {health['status']}")
        """
        health_data = {
            "status": "healthy",
            "started": self._started,
            "adapter_count": len(self.adapters),
            "adapters": {},
        }

        if not self._started:
            health_data["status"] = "unhealthy"
            return health_data

        # Check each adapter
        unhealthy_count = 0
        for name, adapter in self.adapters.items():
            adapter_health = {
                "connected": adapter.session is not None,
                "tool_count": len(adapter.tools_list),
            }

            if not adapter_health["connected"]:
                unhealthy_count += 1

            health_data["adapters"][name] = adapter_health

        # Determine overall status
        if unhealthy_count > 0:
            if unhealthy_count == len(self.adapters):
                health_data["status"] = "unhealthy"
            else:
                health_data["status"] = "degraded"

        return health_data

    def is_started(self) -> bool:
        """Check if the service has been started.

        Returns:
            True if started, False otherwise
        """
        return self._started

    def __repr__(self) -> str:
        """String representation of the service manager."""
        adapter_names = ", ".join(self.adapters.keys()) if self.adapters else "none"
        return (
            f"MCPServiceManager(started={self._started}, "
            f"adapters=[{adapter_names}])"
        )