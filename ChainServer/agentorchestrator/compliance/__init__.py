"""
AgentOrchestrator Compliance Module
====================================

Provides MCP server compliance governance for regulated environments.
Integrates with the middleware pipeline to enforce pre-flight compliance
checks before MCP tool calls are allowed.

Components:
    - ComplianceStatus: Enum for server compliance states
    - ComplianceRecord: Pydantic model for compliance tracking
    - ComplianceConfig: Configuration for compliance behavior
    - ComplianceRegistry: In-memory registry of server compliance states
    - ComplianceMiddleware: Middleware that blocks unapproved MCP calls
    - ComplianceGatewayClient: HTTP client for MCPHub compliance API

Usage:
    from agentorchestrator.compliance import (
        ComplianceMiddleware,
        ComplianceConfig,
        ComplianceRegistry,
        ComplianceStatus,
    )

    # Option 1: Standalone (in-memory registry)
    config = ComplianceConfig(enforcement_mode="enforce")
    middleware = ComplianceMiddleware(config=config)
    ao.use(middleware)

    # Option 2: Connected to MCPHub compliance gateway
    config = ComplianceConfig(
        enforcement_mode="enforce",
        gateway_url="http://localhost:3000/api",
    )
    middleware = ComplianceMiddleware(config=config)
    ao.use(middleware)
"""

from agentorchestrator.compliance.models import (
    ComplianceAuditEntry,
    ComplianceRecord,
    ComplianceStatus,
)
from agentorchestrator.compliance.config import ComplianceConfig
from agentorchestrator.compliance.registry import ComplianceRegistry
from agentorchestrator.compliance.middleware import ComplianceMiddleware
from agentorchestrator.compliance.gateway_client import ComplianceGatewayClient

__all__ = [
    "ComplianceStatus",
    "ComplianceRecord",
    "ComplianceAuditEntry",
    "ComplianceConfig",
    "ComplianceRegistry",
    "ComplianceMiddleware",
    "ComplianceGatewayClient",
]
