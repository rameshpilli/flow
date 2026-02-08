"""
Compliance Data Models
======================

Pydantic models for compliance records, audit entries, and status tracking.
These mirror the MCPHub compliance database schema so records can be
synced between the Python middleware and the Node.js compliance gateway.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ComplianceStatus(str, Enum):
    """
    Compliance status for an MCP server.

    Attributes:
        PENDING_REVIEW: Server registered, awaiting governance review.
        APPROVED: Server approved for production use.
        REJECTED: Server rejected — tool calls will be blocked.
        SUSPENDED: Previously approved server suspended (vulnerability, policy).
        CONDITIONALLY_APPROVED: Approved with conditions attached.
    """

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    CONDITIONALLY_APPROVED = "conditionally_approved"


class ComplianceRecord(BaseModel):
    """
    Tracks the compliance state of a single MCP server.

    Maps 1:1 with the MCPHub compliance_records table.
    """

    server_id: str = Field(..., description="Unique server identifier (matches MCPHub server name)")
    server_name: str = Field(..., description="Human-readable server name")
    mcp_url: str | None = Field(None, description="MCP endpoint URL")
    status: ComplianceStatus = Field(
        default=ComplianceStatus.PENDING_REVIEW,
        description="Current compliance status",
    )
    compliance_score: int | None = Field(None, ge=0, le=100, description="Automated compliance score 0-100")
    reviewed_at: datetime | None = Field(None, description="When last reviewed")
    reviewed_by: str | None = Field(None, description="Who performed the review")
    review_notes: str | None = Field(None, description="Reviewer notes")
    conditions: str | None = Field(None, description="Conditions for conditional approval")
    expires_at: datetime | None = Field(None, description="When the approval expires")
    rule_results: dict[str, Any] | None = Field(None, description="Automated rule evaluation results")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def is_allowed(self) -> bool:
        """Whether this server is allowed to serve tool calls."""
        return self.status in (
            ComplianceStatus.APPROVED,
            ComplianceStatus.CONDITIONALLY_APPROVED,
        )

    @property
    def is_expired(self) -> bool:
        """Whether the approval has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class ComplianceAuditEntry(BaseModel):
    """
    Immutable audit log entry for compliance events.

    Maps 1:1 with the MCPHub compliance_audit_logs table.
    """

    server_id: str
    event_type: str = Field(
        ...,
        description="Event type: registered, approved, rejected, suspended, "
        "connection_blocked, tool_call_blocked, tool_call_allowed",
    )
    actor: str | None = Field(None, description="Who performed the action")
    details: str | None = Field(None, description="Human-readable event description")
    previous_status: str | None = None
    new_status: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
