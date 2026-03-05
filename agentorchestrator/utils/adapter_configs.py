"""
MCP Adapter Configuration Registry

This module provides a centralized registry for MCP adapter configurations.
Adapters define technical connection settings (endpoint, routing, SSL) while
agents reference adapters by name. This separation enables:

1. Adapter Reuse: Multiple agents can share one MCP server connection
2. Reduced Env Vars: Only endpoint + secret per adapter (not per agent)
3. Explicit Configuration: Path routing vs JSON-RPC is defined in code
4. Maintainability: Technical settings in one place

Usage:
    from agentorchestrator.utils.adapter_configs import ADAPTER_CONFIGS, AGENT_CONFIG

    # Adapters define connection details
    adapter_def = ADAPTER_CONFIGS["Ravenpack"]
    endpoint = os.getenv(adapter_def["endpoint_env"])

    # Agents reference adapters
    agent_def = AGENT_CONFIG["News"]
    adapter_name = agent_def["adapter_name"]  # "Ravenpack"
"""

import os
from typing import Any, Dict, List, Optional, TypedDict


class AdapterConfig(TypedDict, total=False):
    """Adapter configuration schema."""
    endpoint_env: str  # Environment variable for endpoint URL
    secret_env: str  # Environment variable for secret/token
    use_path_routing: bool  # True for path-based (/tools/list), False for JSON-RPC
    verify_ssl: bool  # SSL certificate verification
    timeout_seconds: float  # Request timeout


class AgentConfig(TypedDict, total=False):
    """Agent configuration schema."""
    adapter_name: str  # Reference to adapter in ADAPTER_CONFIGS
    tool_env: Optional[str]  # Env var for specific tool filter (None = all tools)
    description: Optional[str]  # Agent description


# ============================================================================
# ADAPTER REGISTRY
# Defines connection settings for each MCP server
# ============================================================================

ADAPTER_CONFIGS: Dict[str, AdapterConfig] = {
    "Ravenpack": {
        "endpoint_env": "RAVENPACK_MCP_ENDPOINT",
        "secret_env": "RAVENPACK_MCP_SECRET",
        "use_path_routing": True,  # Uses /initialize, /tools/list, /tools/call
        "verify_ssl": False,
        "timeout_seconds": 30.0,
    },
    "CapIQ": {
        "endpoint_env": "CAPIQ_MCP_ENDPOINT",
        "secret_env": "CAPIQ_MCP_SECRET",
        "use_path_routing": False,  # Uses single-endpoint JSON-RPC
        "verify_ssl": False,
        "timeout_seconds": 30.0,
    },
    "RBC Insights": {
        "endpoint_env": "RBC_INSIGHTS_MCP_ENDPOINT",
        "secret_env": "RBC_INSIGHTS_MCP_SECRET",
        "use_path_routing": False,  # Uses single-endpoint JSON-RPC
        "verify_ssl": False,
        "timeout_seconds": 30.0,
    },
    "FactSet Earnings": {
        "endpoint_env": "FACTSET_EARNINGS_MCP_ENDPOINT",
        "secret_env": "FACTSET_EARNINGS_MCP_SECRET",
        "use_path_routing": True,  # Uses /initialize, /tools/list, /tools/call
        "verify_ssl": False,
        "timeout_seconds": 30.0,
    },
}


# ============================================================================
# AGENT CONFIGURATION
# Maps agents to adapters with optional tool filtering
# ============================================================================

AGENT_CONFIG: Dict[str, AgentConfig] = {
    "News": {
        "adapter_name": "Ravenpack",
        "tool_env": "RAVENPACK_MCP_NEWS_TOOL",  # Filter to specific tool
        "description": "Ravenpack news data agent",
    },
    "SEC Filings": {
        "adapter_name": "Ravenpack",
        "tool_env": "RAVENPACK_MCP_SEC_FILING_TOOL",  # Filter to specific tool
        "description": "SEC filings data agent",
    },
    "CapIQ": {
        "adapter_name": "CapIQ",
        "tool_env": None,  # Use all tools from endpoint
        "description": "S&P Capital IQ financial data agent",
    },
    "RBC Insights": {
        "adapter_name": "RBC Insights",
        "tool_env": None,  # Use all tools from endpoint
        "description": "RBC Insights market data agent",
    },
    "FactSet Earnings": {
        "adapter_name": "FactSet Earnings",
        "tool_env": None,  # Use all tools from endpoint
        "description": "FactSet earnings data agent",
    },
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_adapter_config(adapter_name: str) -> Optional[AdapterConfig]:
    """
    Get adapter configuration by name.

    Args:
        adapter_name: Adapter name (e.g., "Ravenpack", "CapIQ")

    Returns:
        Adapter configuration dict or None if not found
    """
    return ADAPTER_CONFIGS.get(adapter_name)


def get_agent_config(agent_name: str) -> Optional[AgentConfig]:
    """
    Get agent configuration by name.

    Args:
        agent_name: Agent name (e.g., "News", "SEC Filings")

    Returns:
        Agent configuration dict or None if not found
    """
    return AGENT_CONFIG.get(agent_name)


def get_adapter_credentials(adapter_name: str) -> tuple[Optional[str], Optional[str]]:
    """
    Get endpoint and secret for an adapter from environment.

    Args:
        adapter_name: Adapter name

    Returns:
        Tuple of (endpoint, secret) or (None, None) if not configured
    """
    adapter_cfg = get_adapter_config(adapter_name)
    if not adapter_cfg:
        return None, None

    endpoint = os.getenv(adapter_cfg["endpoint_env"])
    secret = os.getenv(adapter_cfg["secret_env"])

    return endpoint, secret


def list_adapters() -> List[str]:
    """
    List all registered adapter names.

    Returns:
        List of adapter names
    """
    return list(ADAPTER_CONFIGS.keys())


def list_agents() -> List[str]:
    """
    List all registered agent names.

    Returns:
        List of agent names
    """
    return list(AGENT_CONFIG.keys())


def get_agents_for_adapter(adapter_name: str) -> List[str]:
    """
    Find all agents that use a specific adapter.

    Args:
        adapter_name: Adapter name

    Returns:
        List of agent names using this adapter
    """
    return [
        agent_name
        for agent_name, agent_cfg in AGENT_CONFIG.items()
        if agent_cfg.get("adapter_name") == adapter_name
    ]


def validate_configuration() -> Dict[str, Any]:
    """
    Validate adapter and agent configurations.

    Returns:
        Dictionary with validation results:
        {
            "valid": bool,
            "errors": List[str],
            "warnings": List[str],
            "stats": dict
        }
    """
    errors = []
    warnings = []

    # Check all agents reference valid adapters
    for agent_name, agent_cfg in AGENT_CONFIG.items():
        adapter_name = agent_cfg.get("adapter_name")
        if not adapter_name:
            errors.append(f"Agent '{agent_name}' missing adapter_name")
        elif adapter_name not in ADAPTER_CONFIGS:
            errors.append(
                f"Agent '{agent_name}' references unknown adapter '{adapter_name}'"
            )

    # Check adapter credentials
    for adapter_name in ADAPTER_CONFIGS:
        endpoint, secret = get_adapter_credentials(adapter_name)
        if not endpoint:
            warnings.append(
                f"Adapter '{adapter_name}' missing endpoint "
                f"(env: {ADAPTER_CONFIGS[adapter_name]['endpoint_env']})"
            )
        if not secret:
            warnings.append(
                f"Adapter '{adapter_name}' missing secret "
                f"(env: {ADAPTER_CONFIGS[adapter_name]['secret_env']})"
            )

    # Count adapter usage
    adapter_usage = {}
    for adapter_name in ADAPTER_CONFIGS:
        agents = get_agents_for_adapter(adapter_name)
        adapter_usage[adapter_name] = len(agents)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "total_adapters": len(ADAPTER_CONFIGS),
            "total_agents": len(AGENT_CONFIG),
            "adapter_usage": adapter_usage,
        },
    }