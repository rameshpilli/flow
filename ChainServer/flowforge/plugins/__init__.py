"""
FlowForge Plugin System

Provides plugin discovery, loading, and management for agents and connectors.

Features:
- Entry point discovery (pyproject.toml or setup.py)
- Capability schema validation
- Plugin lifecycle management
- HTTP adapter agent (hardened)
- MCP adapter agent

Usage:
    from flowforge.plugins import discover_plugins, load_plugin, PluginManager

    # Discover all plugins
    plugins = discover_plugins()

    # Load a specific plugin
    agent = load_plugin("my_agent")

    # Use plugin manager
    pm = PluginManager()
    pm.load_all()
    agent = pm.get("my_agent")
"""

from flowforge.plugins.discovery import (
    discover_plugins,
    load_plugin,
    PluginInfo,
    PluginManager,
)
from flowforge.plugins.capability import (
    AgentCapability,
    CapabilityParameter,
    CapabilitySchema,
    validate_capability_schema,
)
from flowforge.plugins.http_adapter import (
    HTTPAdapterAgent,
    HTTPAdapterConfig,
    create_http_agent,
)
from flowforge.plugins.mcp_adapter import (
    MCPAdapterAgent,
    MCPAdapterConfig,
    create_mcp_agent,
)

__all__ = [
    # Discovery
    "discover_plugins",
    "load_plugin",
    "PluginInfo",
    "PluginManager",
    # Capability
    "AgentCapability",
    "CapabilityParameter",
    "CapabilitySchema",
    "validate_capability_schema",
    # HTTP Adapter
    "HTTPAdapterAgent",
    "HTTPAdapterConfig",
    "create_http_agent",
    # MCP Adapter
    "MCPAdapterAgent",
    "MCPAdapterConfig",
    "create_mcp_agent",
]
