"""
Compliance Configuration
========================

Configuration model for the compliance module.
Controls enforcement behavior, gateway connectivity, and audit settings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ComplianceConfig(BaseModel):
    """
    Configuration for the compliance middleware and registry.

    Attributes:
        enforcement_mode: How strictly to enforce compliance.
            - "monitor": Log violations but allow all calls (Phase 1).
            - "soft_enforce": Block rejected/suspended, allow pending (Phase 2).
            - "enforce": Block everything except approved/conditionally_approved (Phase 3).
        gateway_url: Base URL of the MCPHub compliance gateway API.
            If set, the registry will sync status from MCPHub.
            Example: "http://localhost:3000/api"
        sync_interval_seconds: How often to sync with the gateway (default 60s).
        default_status: Status assigned to servers not found in the registry.
        audit_enabled: Whether to emit audit events to the event bus.
        audit_blocked_calls: Whether to log each blocked tool call (can be noisy).
        allowed_statuses: Which statuses permit tool calls.
            Defaults to ["approved", "conditionally_approved"].
        bypass_servers: Server IDs that bypass compliance checks entirely.
            Useful for internal infrastructure servers.
    """

    enforcement_mode: Literal["monitor", "soft_enforce", "enforce"] = Field(
        default="monitor",
        description="Enforcement strictness level",
    )
    gateway_url: str | None = Field(
        default=None,
        description="MCPHub compliance API base URL (e.g., http://localhost:3000/api)",
    )
    sync_interval_seconds: int = Field(default=60, ge=5, le=3600)
    default_status: str = Field(
        default="pending_review",
        description="Status for servers not yet in the registry",
    )
    audit_enabled: bool = Field(default=True)
    audit_blocked_calls: bool = Field(default=True)
    allowed_statuses: list[str] = Field(
        default_factory=lambda: ["approved", "conditionally_approved"],
    )
    bypass_servers: list[str] = Field(
        default_factory=list,
        description="Server IDs that skip compliance checks",
    )
