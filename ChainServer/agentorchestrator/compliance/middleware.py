"""
Compliance Middleware
====================

Middleware component that enforces MCP server compliance checks
in the AgentOrchestrator middleware pipeline.

Integrates with the existing ``Middleware`` base class, hooking into
``before()`` to perform pre-flight compliance checks before any step
that invokes an MCP tool call.

The middleware inspects the ChainContext to determine which MCP server
a step is targeting, then checks the ComplianceRegistry to decide
whether the call should proceed, be logged, or be blocked.

Enforcement Modes:
    - **monitor**: Log all calls but never block. Use during rollout.
    - **soft_enforce**: Block rejected/suspended servers; allow pending.
    - **enforce**: Only allow approved/conditionally_approved servers.

Usage:
    from agentorchestrator.compliance import ComplianceMiddleware, ComplianceConfig

    config = ComplianceConfig(
        enforcement_mode="enforce",
        gateway_url="http://localhost:3000/api",
    )
    compliance = ComplianceMiddleware(config=config)
    ao.use(compliance)

    # The middleware will now check compliance before every step that
    # has an mcp_server_id in context.
"""

from __future__ import annotations

import logging
from typing import Any

from agentorchestrator.compliance.config import ComplianceConfig
from agentorchestrator.compliance.models import ComplianceStatus
from agentorchestrator.compliance.registry import ComplianceRegistry
from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware, SkipStep

logger = logging.getLogger(__name__)


class ComplianceBlockedError(Exception):
    """Raised when a tool call is blocked by compliance policy."""

    def __init__(self, server_id: str, status: str, enforcement_mode: str) -> None:
        self.server_id = server_id
        self.status = status
        self.enforcement_mode = enforcement_mode
        super().__init__(
            f"Compliance blocked: server '{server_id}' has status '{status}' "
            f"(enforcement_mode={enforcement_mode})"
        )


class ComplianceMiddleware(Middleware):
    """
    Middleware that enforces MCP server compliance before step execution.

    Checks the compliance registry for the target MCP server and blocks
    the call if the server is not in an approved state.

    The middleware looks for these keys in ChainContext to identify
    the target server:
        - ``mcp_server_id``: Explicit server ID
        - ``mcp_server_name``: Server name (fallback)
        - ``agent_name``: Agent name that maps to a server

    Priority: 5 (runs very early, before caching/rate-limiting).

    Attributes:
        registry: The ComplianceRegistry instance.
        config: The ComplianceConfig.
    """

    def __init__(
        self,
        config: ComplianceConfig | None = None,
        registry: ComplianceRegistry | None = None,
        priority: int = 5,
    ) -> None:
        super().__init__(priority=priority)
        self._config = config or ComplianceConfig()
        self._registry = registry or ComplianceRegistry(self._config)

    @property
    def registry(self) -> ComplianceRegistry:
        return self._registry

    @property
    def config(self) -> ComplianceConfig:
        return self._config

    def _resolve_server_id(self, ctx: ChainContext, step_name: str) -> str | None:
        """
        Determine the MCP server ID from the context.

        Checks (in order):
            1. ctx["mcp_server_id"] — explicit server ID
            2. ctx["mcp_server_name"] — server name
            3. ctx["agent_name"] — agent name (for MCP adapter agents)
            4. Step name itself — if it matches a registered server
        """
        for key in ("mcp_server_id", "mcp_server_name", "agent_name"):
            value = ctx.get(key)
            if value and isinstance(value, str):
                return value

        # Check if step name maps to a known server
        if self._registry.get(step_name) is not None:
            return step_name

        return None

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Pre-flight compliance check.

        Called before every step in the chain. If the step targets an
        MCP server that is not in compliance, this method either logs
        a warning (monitor mode) or raises an error (enforce mode).
        """
        server_id = self._resolve_server_id(ctx, step_name)

        if server_id is None:
            # Not an MCP step — skip compliance check
            return

        allowed = self._registry.is_allowed(server_id)
        status = self._registry.get_status(server_id)
        mode = self._config.enforcement_mode

        # Log the check
        tool_name = ctx.get("tool_name", step_name)
        if self._config.audit_enabled and self._config.audit_blocked_calls:
            self._registry.log_tool_call(
                server_id=server_id,
                tool_name=tool_name,
                allowed=allowed,
                enforcement_mode=mode,
            )

        if allowed:
            logger.debug(
                f"[Compliance] ALLOWED: server={server_id} status={status.value} "
                f"step={step_name} mode={mode}"
            )
            # Store compliance metadata in context for downstream steps
            ctx.set("_compliance_server_id", server_id)
            ctx.set("_compliance_status", status.value)
            ctx.set("_compliance_allowed", True)
            return

        # Not allowed
        if mode == "monitor":
            # Monitor mode: log but don't block
            logger.warning(
                f"[Compliance] MONITOR: server={server_id} status={status.value} "
                f"step={step_name} — would be blocked in enforce mode"
            )
            ctx.set("_compliance_server_id", server_id)
            ctx.set("_compliance_status", status.value)
            ctx.set("_compliance_allowed", False)
            ctx.set("_compliance_mode", "monitor")
            return

        # Enforce or soft_enforce: block the call
        logger.warning(
            f"[Compliance] BLOCKED: server={server_id} status={status.value} "
            f"step={step_name} mode={mode}"
        )
        ctx.set("_compliance_server_id", server_id)
        ctx.set("_compliance_status", status.value)
        ctx.set("_compliance_allowed", False)
        ctx.set("_compliance_mode", mode)

        raise ComplianceBlockedError(
            server_id=server_id,
            status=status.value,
            enforcement_mode=mode,
        )

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Post-execution hook. Records successful compliance-checked calls.
        """
        server_id = ctx.get("_compliance_server_id")
        if server_id:
            logger.debug(
                f"[Compliance] Step {step_name} completed for server {server_id}"
            )

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """
        Error hook. Records compliance-related errors.
        """
        if isinstance(error, ComplianceBlockedError):
            logger.warning(
                f"[Compliance] Step {step_name} blocked: {error}"
            )

    async def initialize(self) -> None:
        """
        Initialize the middleware: start gateway sync if configured.
        Call this after creating the middleware to begin syncing.
        """
        if self._config.gateway_url:
            await self._registry.start_sync()
            # Do an immediate sync
            await self._registry.sync_now()

    async def shutdown(self) -> None:
        """Stop the sync loop."""
        await self._registry.stop_sync()
