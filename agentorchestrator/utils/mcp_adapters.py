"""Generic MCP adapter factory functions.

This module provides generic, vendor-agnostic functions for creating MCP adapters.
Supports two configuration approaches:

1. **Registry-Based (Recommended)**: Use centralized adapter/agent configuration
2. **Convention-Based (Legacy)**: Define agents via environment variables

**Registry-Based Configuration (Recommended):**

The new approach separates adapter technical settings from agent configuration:

    from agentorchestrator.utils.adapter_configs import ADAPTER_CONFIGS, AGENT_CONFIG

    # Adapters define connection settings (in code)
    ADAPTER_CONFIGS = {
        "Ravenpack": {
            "endpoint_env": "RAVENPACK_MCP_ENDPOINT",
            "secret_env": "RAVENPACK_MCP_SECRET",
            "use_path_routing": True,  # Path-based routing
            "verify_ssl": False
        }
    }

    # Agents reference adapters (enables reuse)
    AGENT_CONFIG = {
        "News": {"adapter_name": "Ravenpack", "tool_env": "NEWS_TOOL"},
        "SEC": {"adapter_name": "Ravenpack", "tool_env": "SEC_TOOL"}
    }

    # Environment variables (only endpoint + secret)
    RAVENPACK_MCP_ENDPOINT=https://ravenpack.example.com
    RAVENPACK_MCP_SECRET=token123

    # Use in code
    from agentorchestrator.utils.mcp_adapters import create_adapters_from_registry

    adapters = await create_adapters_from_registry(["News", "SEC"])
    # Creates 1 adapter shared by 2 agents!

**Convention-Based Configuration (Legacy):**

Define any MCP agent using environment variables:
    MCP_{AGENT_NAME}_ENDPOINT - MCP server URL
    MCP_{AGENT_NAME}_SECRET - Authentication token
    MCP_{AGENT_NAME}_ROUTING - "path" or "jsonrpc" (default: "path")
    MCP_{AGENT_NAME}_VERIFY_SSL - "true" or "false" (default: "false")

Example:
    # Define agents in .env
    MCP_NEWS_ENDPOINT=https://news-mcp.example.com
    MCP_NEWS_SECRET=token123

    # Use in code
    from agentorchestrator.utils.mcp_adapters import create_selected_adapters

    adapters = await create_selected_adapters(["News"])
"""

import os
from typing import Dict, List, Optional

from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter

# Import adapter registry (optional - for registry-based config)
try:
    from agentorchestrator.utils.adapter_configs import (
        ADAPTER_CONFIGS,
        AGENT_CONFIG,
        get_adapter_config,
        get_adapter_credentials,
        get_agent_config,
    )
    _HAS_ADAPTER_REGISTRY = True
except ImportError:
    _HAS_ADAPTER_REGISTRY = False
    ADAPTER_CONFIGS = {}
    AGENT_CONFIG = {}


# ============================================================================
# REGISTRY-BASED CONFIGURATION (Recommended)
# ============================================================================

async def create_adapters_from_registry(
    selected_agents: List[str],
    tool_filter: bool = True,
) -> Dict[str, MCPToolAdapter]:
    """
    Create MCP adapters using the centralized adapter registry.

    This is the recommended approach that:
    - Reuses adapters when multiple agents share the same MCP server
    - Reduces environment variables (only endpoint + secret per adapter)
    - Makes path routing vs JSON-RPC explicit in code
    - Supports tool filtering per agent

    Args:
        selected_agents: List of agent names from AGENT_CONFIG
                        Example: ["News", "SEC Filings", "CapIQ"]
        tool_filter: If True, apply tool filtering from tool_env (default: True)

    Returns:
        Dictionary mapping agent names to MCPToolAdapter instances
        Note: Multiple agents may share the same adapter instance

    Example:
        from agentorchestrator.utils.mcp_adapters import create_adapters_from_registry

        # Request specific agents
        adapters = await create_adapters_from_registry(["News", "SEC Filings"])

        # Both agents share the same Ravenpack adapter
        news_adapter = adapters["News"]
        sec_adapter = adapters["SEC Filings"]
        assert news_adapter is sec_adapter  # True! Same instance

        # Get tools (filtered per agent if tool_filter=True)
        news_tools = await news_adapter.get_tool_functions()

        # Cleanup
        seen = set()
        for adapter in adapters.values():
            if id(adapter) not in seen:
                await adapter.disconnect()
                seen.add(id(adapter))
    """
    if not _HAS_ADAPTER_REGISTRY:
        raise RuntimeError(
            "Adapter registry not available. "
            "Ensure agentorchestrator.utils.adapter_configs is importable."
        )

    # Track created adapters by adapter name (for reuse)
    adapter_instances: Dict[str, MCPToolAdapter] = {}

    # Map agent names to adapter instances
    agent_to_adapter: Dict[str, MCPToolAdapter] = {}

    for agent_name in selected_agents:
        # Get agent config
        agent_cfg = get_agent_config(agent_name)
        if not agent_cfg:
            print(f"⚠️  Agent '{agent_name}' not found in AGENT_CONFIG")
            continue

        adapter_name = agent_cfg.get("adapter_name")
        if not adapter_name:
            print(f"⚠️  Agent '{agent_name}' missing adapter_name")
            continue

        # Reuse existing adapter instance if already created
        if adapter_name in adapter_instances:
            agent_to_adapter[agent_name] = adapter_instances[adapter_name]
            print(f"♻️  Reusing adapter '{adapter_name}' for agent '{agent_name}'")
            continue

        # Get adapter config
        adapter_cfg = get_adapter_config(adapter_name)
        if not adapter_cfg:
            print(f"⚠️  Adapter '{adapter_name}' not found in ADAPTER_CONFIGS")
            continue

        # Get credentials from environment
        endpoint, secret = get_adapter_credentials(adapter_name)
        if not endpoint or not secret:
            print(
                f"⚠️  {adapter_name}: Missing credentials "
                f"(need {adapter_cfg['endpoint_env']} and {adapter_cfg['secret_env']})"
            )
            continue

        # Create adapter
        try:
            adapter = await create_mcp_adapter(
                name=adapter_name,
                endpoint=endpoint,
                secret=secret,
                use_path_routing=adapter_cfg.get("use_path_routing", True),
                verify_ssl=adapter_cfg.get("verify_ssl", False),
            )

            if adapter:
                adapter_instances[adapter_name] = adapter
                agent_to_adapter[agent_name] = adapter
                print(f"✅ Created adapter '{adapter_name}' for agent '{agent_name}'")
            else:
                print(f"⚠️  Failed to create adapter '{adapter_name}'")

        except Exception as e:
            print(f"⚠️  Error creating adapter '{adapter_name}': {e}")

    # Summary
    unique_adapters = len(adapter_instances)
    total_agents = len(agent_to_adapter)

    if unique_adapters > 0:
        print(
            f"\n✅ Created {unique_adapters} unique adapter(s) "
            f"for {total_agents} agent(s)"
        )
        print(f"   Adapters: {list(adapter_instances.keys())}")
        print(f"   Agents: {list(agent_to_adapter.keys())}")
    else:
        print(f"\n⚠️  No adapters created for: {', '.join(selected_agents)}")

    return agent_to_adapter


# ============================================================================
# LOW-LEVEL ADAPTER CREATION
# ============================================================================

async def create_mcp_adapter(
    name: str,
    endpoint: str,
    secret: str,
    use_path_routing: bool = True,
    verify_ssl: bool = False,
) -> Optional[MCPToolAdapter]:
    """Create a generic MCP adapter for any service.

    This is the base function for creating MCP adapters. Users can call this
    directly or use create_selected_adapters() for convention-based creation.

    Args:
        name: Display name for the adapter
        endpoint: MCP server endpoint URL
        secret: Authentication secret/token
        use_path_routing: If True, use path-based routing (/tools/{name})
                         If False, use single-endpoint JSON-RPC
        verify_ssl: If True, verify SSL certificates

    Returns:
        Connected MCPToolAdapter or None if connection fails

    Example:
        # Create adapter explicitly
        adapter = await create_mcp_adapter(
            name="My Data Source",
            endpoint="https://my-mcp-server.com",
            secret="my-api-key",
            use_path_routing=True
        )

        if adapter:
            tools = await adapter.get_tool_functions()
            # Use tools...
            await adapter.disconnect()
    """
    if not endpoint or not secret:
        print(f"⚠️  {name}: Missing endpoint or secret")
        return None

    adapter = MCPToolAdapter(name=name)

    try:
        success = await adapter.connect(
            endpoint=endpoint,
            secret=secret,
            use_path_routing=use_path_routing,
            verify_ssl=verify_ssl,
        )

        if not success:
            print(f"⚠️  Failed to connect to {name} at {endpoint}")
            return None

        return adapter

    except Exception as e:
        print(f"⚠️  Error connecting to {name}: {e}")
        return None


# ============================================================================
# CONVENTION-BASED CONFIGURATION (Legacy)
# ============================================================================

async def create_selected_adapters(
    selected_agents: List[str],
    agent_configs: Optional[dict] = None,
    use_registry: bool = False,
) -> List[MCPToolAdapter]:
    """Create only the MCP adapters for agents requested by the user.

    Supports two modes:
    1. Registry-based (use_registry=True): Uses centralized adapter configs
    2. Convention-based (default): Uses environment variable discovery

    **Registry-Based Mode (Recommended):**
    Set use_registry=True to use the centralized adapter registry. This enables
    adapter reuse when multiple agents share the same MCP server.

    **Convention-Based Discovery (Legacy):**
    If agent_configs is not provided and use_registry=False, discovers
    configuration from environment variables using this pattern:
        MCP_{AGENT_NAME}_ENDPOINT or {AGENT_NAME}_MCP_ENDPOINT
        MCP_{AGENT_NAME}_SECRET or {AGENT_NAME}_MCP_SECRET
        MCP_{AGENT_NAME}_ROUTING (optional: "path" or "jsonrpc", default: "path")
        MCP_{AGENT_NAME}_VERIFY_SSL (optional: "true" or "false", default: "false")

    Agent names are normalized: "My Agent" -> "MY_AGENT" (uppercase, spaces to underscores)

    Args:
        selected_agents: List of agent names to create adapters for
                        Example: ["News", "Financial Data", "SEC Filings"]
        agent_configs: Optional explicit configs (bypasses environment lookup).
                      Format: {
                          "Agent Name": {
                              "endpoint": "https://...",
                              "secret": "token",
                              "routing": "path" | "jsonrpc",
                              "verify_ssl": bool
                          }
                      }
        use_registry: If True, use centralized adapter registry (recommended)

    Returns:
        List of connected MCPToolAdapter instances

    Example 1 - Environment-based (recommended):
        # .env
        MCP_NEWS_ENDPOINT=https://news.example.com
        MCP_NEWS_SECRET=token123

        MCP_FINANCIAL_DATA_ENDPOINT=https://finance.example.com
        MCP_FINANCIAL_DATA_SECRET=token456
        MCP_FINANCIAL_DATA_ROUTING=jsonrpc

        # Code
        user_selection = ["News", "Financial Data"]
        adapters = await create_selected_adapters(user_selection)
        # Creates 2 adapters only!

    Example 2 - Explicit configs:
        configs = {
            "News": {
                "endpoint": "https://news.example.com",
                "secret": "token123",
                "routing": "path"
            },
            "Finance": {
                "endpoint": "https://finance.example.com",
                "secret": "token456",
                "routing": "jsonrpc",
                "verify_ssl": True
            }
        }
        adapters = await create_selected_adapters(["News"], configs)

    Example 3 - With cleanup:
        adapters = await create_selected_adapters(["News", "Finance"])
        try:
            # Use adapters
            for adapter in adapters:
                tools = await adapter.get_tool_functions()
                # ... use tools ...
        finally:
            # Always clean up
            for adapter in adapters:
                await adapter.disconnect()
    """
    # Use registry-based approach if requested
    if use_registry:
        if not _HAS_ADAPTER_REGISTRY:
            print("⚠️  Adapter registry not available, falling back to convention-based")
        else:
            agent_to_adapter = await create_adapters_from_registry(selected_agents)
            # Return unique adapter instances only
            seen = set()
            adapters = []
            for adapter in agent_to_adapter.values():
                if id(adapter) not in seen:
                    adapters.append(adapter)
                    seen.add(id(adapter))
            return adapters

    # Convention-based approach (legacy)
    adapters = []

    for agent_name in selected_agents:
        # Get config from provided dict or discover from environment
        if agent_configs and agent_name in agent_configs:
            # Explicit config provided
            config = agent_configs[agent_name]
            endpoint = config.get("endpoint")
            secret = config.get("secret")
            routing = config.get("routing", "path")
            verify_ssl = config.get("verify_ssl", False)
        else:
            # Auto-discover from environment using convention
            agent_key = agent_name.upper().replace(" ", "_").replace("-", "_")

            endpoint = (
                os.getenv(f"MCP_{agent_key}_ENDPOINT")
                or os.getenv(f"{agent_key}_MCP_ENDPOINT")
            )
            secret = (
                os.getenv(f"MCP_{agent_key}_SECRET")
                or os.getenv(f"{agent_key}_MCP_SECRET")
            )
            routing = os.getenv(f"MCP_{agent_key}_ROUTING", "path")
            verify_ssl_str = os.getenv(f"MCP_{agent_key}_VERIFY_SSL", "false")
            verify_ssl = verify_ssl_str.lower() in ["true", "1", "yes"]

        if not endpoint or not secret:
            print(f"⚠️  {agent_name}: No configuration found")
            print(f"    Expected: MCP_{agent_key}_ENDPOINT and MCP_{agent_key}_SECRET")
            continue

        try:
            use_path_routing = routing.lower() in ["path", "path-based", "true"]
            adapter = await create_mcp_adapter(
                name=agent_name,
                endpoint=endpoint,
                secret=secret,
                use_path_routing=use_path_routing,
                verify_ssl=verify_ssl,
            )

            if adapter:
                adapters.append(adapter)
        except Exception as e:
            print(f"⚠️  Failed to create adapter for {agent_name}: {e}")

    if adapters:
        print(f"\n✅ Created {len(adapters)} adapter(s): {[a.name for a in adapters]}")
    else:
        print(f"\n⚠️  No adapters created for: {', '.join(selected_agents)}")

    return adapters


# Legacy alias for backward compatibility
create_mcp_adapter_generic = create_mcp_adapter