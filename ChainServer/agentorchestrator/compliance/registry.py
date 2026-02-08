"""
Compliance Registry
===================

Thread-safe in-memory registry tracking compliance status for MCP servers.
Optionally syncs with the MCPHub compliance gateway via HTTP.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Any

from agentorchestrator.compliance.config import ComplianceConfig
from agentorchestrator.compliance.models import (
    ComplianceAuditEntry,
    ComplianceRecord,
    ComplianceStatus,
)

logger = logging.getLogger(__name__)


class ComplianceRegistry:
    """
    In-memory registry of MCP server compliance records.

    Thread-safe. Can optionally sync from the MCPHub compliance gateway
    when ``config.gateway_url`` is set.

    Usage:
        registry = ComplianceRegistry(config)

        # Check if a server is allowed
        if registry.is_allowed("sec-filing-server"):
            # proceed with tool call
            ...

        # Register a server
        registry.register("my-server", "My MCP Server", "http://...")

        # Get full record
        record = registry.get("my-server")
    """

    def __init__(self, config: ComplianceConfig | None = None) -> None:
        self._config = config or ComplianceConfig()
        self._records: dict[str, ComplianceRecord] = {}
        self._audit_log: list[ComplianceAuditEntry] = []
        self._lock = threading.Lock()
        self._sync_task: asyncio.Task | None = None
        self._last_sync: datetime | None = None

    @property
    def config(self) -> ComplianceConfig:
        return self._config

    # ── Query ──────────────────────────────────────────────────────────

    def get(self, server_id: str) -> ComplianceRecord | None:
        """Get the compliance record for a server."""
        with self._lock:
            return self._records.get(server_id)

    def get_status(self, server_id: str) -> ComplianceStatus:
        """Get the compliance status for a server (returns default if unknown)."""
        record = self.get(server_id)
        if record is None:
            return ComplianceStatus(self._config.default_status)
        return record.status

    def is_allowed(self, server_id: str) -> bool:
        """
        Check whether a server is allowed to handle tool calls.

        Takes into account: enforcement mode, bypass list, status, and expiry.
        """
        # Bypass list
        if server_id in self._config.bypass_servers:
            return True

        # Monitor mode — always allow
        if self._config.enforcement_mode == "monitor":
            return True

        record = self.get(server_id)

        # Unknown server
        if record is None:
            if self._config.enforcement_mode == "soft_enforce":
                return True  # Soft: allow unknown servers
            return False  # Strict: block unknown

        # Check expiry
        if record.is_expired:
            return False

        # Soft enforce: only block rejected/suspended
        if self._config.enforcement_mode == "soft_enforce":
            return record.status not in (
                ComplianceStatus.REJECTED,
                ComplianceStatus.SUSPENDED,
            )

        # Strict enforce: only allow approved statuses
        return record.status.value in self._config.allowed_statuses

    def list_all(self) -> list[ComplianceRecord]:
        """Return all compliance records."""
        with self._lock:
            return list(self._records.values())

    def get_audit_log(self, server_id: str | None = None, limit: int = 100) -> list[ComplianceAuditEntry]:
        """Get audit log entries, optionally filtered by server."""
        with self._lock:
            entries = self._audit_log
            if server_id:
                entries = [e for e in entries if e.server_id == server_id]
            return entries[-limit:]

    # ── Mutations ──────────────────────────────────────────────────────

    def register(
        self,
        server_id: str,
        server_name: str,
        mcp_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ComplianceRecord:
        """Register a new server for compliance review."""
        with self._lock:
            if server_id in self._records:
                return self._records[server_id]

            record = ComplianceRecord(
                server_id=server_id,
                server_name=server_name,
                mcp_url=mcp_url,
                status=ComplianceStatus.PENDING_REVIEW,
                metadata=metadata,
            )
            self._records[server_id] = record
            self._add_audit(
                server_id, "registered",
                details=f"Server {server_name} registered for compliance review",
                new_status="pending_review",
            )
            return record

    def update_status(
        self,
        server_id: str,
        new_status: ComplianceStatus,
        reviewer: str | None = None,
        notes: str | None = None,
    ) -> ComplianceRecord | None:
        """Update the compliance status of a server."""
        with self._lock:
            record = self._records.get(server_id)
            if record is None:
                return None

            old_status = record.status
            record.status = new_status
            record.reviewed_by = reviewer
            record.review_notes = notes
            record.reviewed_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()

            self._add_audit(
                server_id, new_status.value,
                actor=reviewer,
                details=f"Status changed to {new_status.value}" + (f": {notes}" if notes else ""),
                previous_status=old_status.value,
                new_status=new_status.value,
            )
            return record

    def bulk_load(self, records: list[dict[str, Any]]) -> int:
        """Load multiple records (e.g., from MCPHub gateway sync). Returns count loaded."""
        count = 0
        with self._lock:
            for data in records:
                try:
                    record = ComplianceRecord(
                        server_id=data.get("serverId", data.get("server_id", "")),
                        server_name=data.get("serverName", data.get("server_name", "")),
                        mcp_url=data.get("mcpUrl", data.get("mcp_url")),
                        status=ComplianceStatus(data.get("status", "pending_review")),
                        compliance_score=data.get("complianceScore", data.get("compliance_score")),
                        reviewed_by=data.get("reviewedBy", data.get("reviewed_by")),
                        review_notes=data.get("reviewNotes", data.get("review_notes")),
                        conditions=data.get("conditions"),
                        expires_at=data.get("expiresAt", data.get("expires_at")),
                    )
                    self._records[record.server_id] = record
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to load compliance record: {e}")
            self._last_sync = datetime.utcnow()
        logger.info(f"[Compliance] Loaded {count} records from gateway")
        return count

    # ── Audit ──────────────────────────────────────────────────────────

    def _add_audit(
        self,
        server_id: str,
        event_type: str,
        actor: str | None = None,
        details: str | None = None,
        previous_status: str | None = None,
        new_status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add an audit log entry (call inside _lock)."""
        entry = ComplianceAuditEntry(
            server_id=server_id,
            event_type=event_type,
            actor=actor,
            details=details,
            previous_status=previous_status,
            new_status=new_status,
            metadata=metadata,
        )
        self._audit_log.append(entry)

    def log_tool_call(
        self,
        server_id: str,
        tool_name: str,
        allowed: bool,
        enforcement_mode: str,
    ) -> None:
        """Log a tool call attempt (allowed or blocked)."""
        event_type = "tool_call_allowed" if allowed else "tool_call_blocked"
        with self._lock:
            self._add_audit(
                server_id,
                event_type,
                details=f"Tool '{tool_name}' call {'allowed' if allowed else 'blocked'} "
                f"(mode={enforcement_mode})",
                metadata={"tool_name": tool_name, "enforcement_mode": enforcement_mode},
            )

    # ── Sync ───────────────────────────────────────────────────────────

    async def start_sync(self) -> None:
        """Start periodic sync with MCPHub gateway (if configured)."""
        if not self._config.gateway_url:
            return
        if self._sync_task and not self._sync_task.done():
            return

        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info(
            f"[Compliance] Sync started with gateway: {self._config.gateway_url} "
            f"(every {self._config.sync_interval_seconds}s)"
        )

    async def stop_sync(self) -> None:
        """Stop the sync loop."""
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

    async def sync_now(self) -> int:
        """Manually trigger a sync from the gateway. Returns record count."""
        from agentorchestrator.compliance.gateway_client import ComplianceGatewayClient

        if not self._config.gateway_url:
            logger.warning("[Compliance] No gateway_url configured, skipping sync")
            return 0

        client = ComplianceGatewayClient(self._config.gateway_url)
        try:
            records = await client.fetch_all_records()
            return self.bulk_load(records)
        except Exception as e:
            logger.error(f"[Compliance] Sync failed: {e}")
            return 0

    async def _sync_loop(self) -> None:
        """Background sync loop."""
        while True:
            try:
                await self.sync_now()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Compliance] Sync error: {e}")
            await asyncio.sleep(self._config.sync_interval_seconds)
