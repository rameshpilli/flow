"""
Compliance Gateway Client
=========================

HTTP client for communicating with the MCPHub compliance gateway API.
Used by ComplianceRegistry.sync_now() to pull compliance records,
and by ComplianceMiddleware to report blocked calls.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ComplianceGatewayClient:
    """
    HTTP client for the MCPHub compliance gateway REST API.

    Endpoints consumed:
        GET  /compliance/servers          - Fetch all compliance records
        GET  /compliance/servers-with-tools - Fetch records with tool data
        GET  /compliance/status/{id}      - Fetch single server status
        GET  /compliance/dashboard        - Fetch dashboard stats
        POST /compliance/check            - Register a server
        GET  /compliance/audit/{id}       - Fetch audit trail

    Usage:
        client = ComplianceGatewayClient("http://localhost:3000/api")
        records = await client.fetch_all_records()
        status = await client.get_server_status("sec-filing-server")
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def fetch_all_records(self) -> list[dict[str, Any]]:
        """Fetch all compliance records from the gateway."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/compliance/servers")
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data) if isinstance(data, dict) else data

    async def fetch_records_with_tools(self) -> list[dict[str, Any]]:
        """Fetch compliance records enriched with tool data."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/compliance/servers-with-tools")
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data) if isinstance(data, dict) else data

    async def get_server_status(self, server_id: str) -> dict[str, Any] | None:
        """Get compliance status for a single server."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/compliance/status/{server_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data) if isinstance(data, dict) else data

    async def get_dashboard(self) -> dict[str, Any]:
        """Fetch compliance dashboard stats."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/compliance/dashboard")
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data) if isinstance(data, dict) else data

    async def register_server(
        self,
        server_id: str,
        server_name: str,
        mcp_url: str | None = None,
    ) -> dict[str, Any]:
        """Register a server for compliance review via the gateway."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/compliance/check",
                json={
                    "serverId": server_id,
                    "serverName": server_name,
                    "mcpUrl": mcp_url,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data) if isinstance(data, dict) else data

    async def get_audit_log(self, server_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch audit log for a server."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/compliance/audit/{server_id}",
                params={"limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data) if isinstance(data, dict) else data
