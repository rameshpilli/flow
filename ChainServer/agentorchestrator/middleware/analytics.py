"""
AgentOrchestrator Usage Analytics Middleware

Provides usage tracking for billing, reporting, and observability.

Features:
- Track usage by user, chain, and step
- Token consumption tracking
- Duration and cost metrics
- Export to various backends (in-memory, file, external service)

Usage:
    from agentorchestrator.middleware import UsageAnalyticsMiddleware

    # Basic usage with in-memory storage
    analytics = UsageAnalyticsMiddleware()
    forge.use(analytics)

    # Get usage report
    report = analytics.get_usage_report(user_id="user123")

    # With file export
    analytics = UsageAnalyticsMiddleware(
        export_path="/var/log/ao_usage.jsonl",
        export_interval_seconds=60,
    )

    # With custom backend
    analytics = UsageAnalyticsMiddleware(
        backend=MyCustomBackend(),
    )
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware

logger = logging.getLogger(__name__)


@dataclass
class UsageRecord:
    """A single usage record."""

    timestamp: str
    request_id: str
    user_id: str | None
    chain_name: str
    step_name: str
    duration_ms: float
    tokens_used: int
    tokens_input: int
    tokens_output: int
    success: bool
    error_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "chain_name": self.chain_name,
            "step_name": self.step_name,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "success": self.success,
            "error_type": self.error_type,
            "metadata": self.metadata,
        }


@runtime_checkable
class UsageBackend(Protocol):
    """Protocol for usage analytics backends."""

    def record(self, usage: UsageRecord) -> None:
        """Record a usage event."""
        ...

    def query(
        self,
        user_id: str | None = None,
        chain_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[UsageRecord]:
        """Query usage records."""
        ...


class InMemoryUsageBackend:
    """
    In-memory usage backend for development and testing.

    Stores records in memory with optional size limit.
    """

    def __init__(self, max_records: int = 10000):
        self._records: list[UsageRecord] = []
        self._max_records = max_records
        self._lock = asyncio.Lock()

    def record(self, usage: UsageRecord) -> None:
        """Record a usage event."""
        self._records.append(usage)

        # Trim if exceeds max
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records :]

    def query(
        self,
        user_id: str | None = None,
        chain_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[UsageRecord]:
        """Query usage records with filters."""
        results = self._records

        if user_id:
            results = [r for r in results if r.user_id == user_id]

        if chain_name:
            results = [r for r in results if r.chain_name == chain_name]

        if start_time:
            start_iso = start_time.isoformat()
            results = [r for r in results if r.timestamp >= start_iso]

        if end_time:
            end_iso = end_time.isoformat()
            results = [r for r in results if r.timestamp <= end_iso]

        return results

    def clear(self) -> None:
        """Clear all records."""
        self._records.clear()


class FileUsageBackend:
    """
    File-based usage backend for persistent storage.

    Writes records to a JSONL file.
    """

    def __init__(self, path: str | Path, flush_interval: int = 10):
        self._path = Path(path)
        self._flush_interval = flush_interval
        self._buffer: list[UsageRecord] = []
        self._last_flush = time.time()

        # Ensure directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, usage: UsageRecord) -> None:
        """Record a usage event."""
        self._buffer.append(usage)

        # Flush if interval exceeded
        if time.time() - self._last_flush >= self._flush_interval:
            self._flush()

    def _flush(self) -> None:
        """Flush buffer to file."""
        if not self._buffer:
            return

        try:
            with open(self._path, "a") as f:
                for record in self._buffer:
                    f.write(json.dumps(record.to_dict()) + "\n")
            self._buffer.clear()
            self._last_flush = time.time()
        except Exception as e:
            logger.error(f"Failed to flush usage records: {e}")

    def query(
        self,
        user_id: str | None = None,
        chain_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[UsageRecord]:
        """Query usage records from file."""
        # Flush pending records first
        self._flush()

        results = []
        if not self._path.exists():
            return results

        try:
            with open(self._path) as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    record = UsageRecord(**data)

                    # Apply filters
                    if user_id and record.user_id != user_id:
                        continue
                    if chain_name and record.chain_name != chain_name:
                        continue
                    if start_time and record.timestamp < start_time.isoformat():
                        continue
                    if end_time and record.timestamp > end_time.isoformat():
                        continue

                    results.append(record)
        except Exception as e:
            logger.error(f"Failed to read usage records: {e}")

        return results

    def close(self) -> None:
        """Flush and close."""
        self._flush()


class UsageAnalyticsMiddleware(Middleware):
    """
    Middleware for tracking usage analytics.

    Collects:
    - User/chain/step usage
    - Token consumption
    - Execution duration
    - Success/failure rates

    Usage:
        analytics = UsageAnalyticsMiddleware()
        forge.use(analytics)

        # Run chains...
        await forge.run("my_chain", context={"user_id": "user123"})

        # Get report
        report = analytics.get_usage_report(user_id="user123")
        print(f"Total tokens: {report['total_tokens']}")

        # Get by chain
        chain_report = analytics.get_usage_report(chain_name="my_chain")
    """

    def __init__(
        self,
        backend: UsageBackend | None = None,
        priority: int = 1,  # Run very early to capture all data
        applies_to: list[str] | None = None,
        export_path: str | Path | None = None,
        track_tokens: bool = True,
        track_costs: bool = False,
        cost_per_1k_tokens: float = 0.0,
    ):
        """
        Initialize UsageAnalyticsMiddleware.

        Args:
            backend: Usage backend (default: InMemoryUsageBackend)
            priority: Middleware priority
            applies_to: List of step names to track (None = all)
            export_path: Path to export usage records (creates FileUsageBackend)
            track_tokens: Track token usage from results
            track_costs: Calculate costs based on tokens
            cost_per_1k_tokens: Cost per 1000 tokens (if track_costs=True)
        """
        super().__init__(priority=priority, applies_to=applies_to)

        if backend:
            self._backend = backend
        elif export_path:
            self._backend = FileUsageBackend(export_path)
        else:
            self._backend = InMemoryUsageBackend()

        self._track_tokens = track_tokens
        self._track_costs = track_costs
        self._cost_per_1k_tokens = cost_per_1k_tokens

        # Aggregated stats for quick access
        self._stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_requests": 0,
                "total_tokens": 0,
                "total_duration_ms": 0,
                "success_count": 0,
                "failure_count": 0,
            }
        )

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Record usage after step execution."""
        # Extract user ID from context
        user_id = ctx.metadata.get("user_id") or ctx.get("user_id")
        chain_name = ctx.metadata.get("chain_name", "unknown")

        # Extract token usage from result metadata
        tokens_used = 0
        tokens_input = 0
        tokens_output = 0

        if self._track_tokens and result.metadata:
            tokens_used = result.metadata.get("tokens_used", 0)
            tokens_input = result.metadata.get("tokens_input", 0)
            tokens_output = result.metadata.get("tokens_output", 0)

            # If only total is available
            if tokens_used == 0 and (tokens_input > 0 or tokens_output > 0):
                tokens_used = tokens_input + tokens_output

        # Create usage record
        record = UsageRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            request_id=ctx.request_id,
            user_id=user_id,
            chain_name=chain_name,
            step_name=step_name,
            duration_ms=result.duration_ms,
            tokens_used=tokens_used,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            success=result.success,
            error_type=result.error_type if result.failed else None,
            metadata={
                "retry_count": result.retry_count,
                "skipped": result.skipped,
            },
        )

        # Record to backend
        self._backend.record(record)

        # Update aggregated stats
        stat_key = f"{user_id or 'anonymous'}:{chain_name}"
        self._stats[stat_key]["total_requests"] += 1
        self._stats[stat_key]["total_tokens"] += tokens_used
        self._stats[stat_key]["total_duration_ms"] += result.duration_ms
        if result.success:
            self._stats[stat_key]["success_count"] += 1
        else:
            self._stats[stat_key]["failure_count"] += 1

    def get_usage_report(
        self,
        user_id: str | None = None,
        chain_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Get usage report with aggregated statistics.

        Args:
            user_id: Filter by user ID
            chain_name: Filter by chain name
            start_time: Filter by start time
            end_time: Filter by end time

        Returns:
            Dict with usage statistics
        """
        records = self._backend.query(
            user_id=user_id,
            chain_name=chain_name,
            start_time=start_time,
            end_time=end_time,
        )

        if not records:
            return {
                "total_requests": 0,
                "total_tokens": 0,
                "total_duration_ms": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0,
                "avg_duration_ms": 0,
                "total_cost": 0,
                "by_chain": {},
                "by_step": {},
            }

        # Aggregate
        total_tokens = sum(r.tokens_used for r in records)
        total_duration = sum(r.duration_ms for r in records)
        success_count = sum(1 for r in records if r.success)
        failure_count = len(records) - success_count

        # By chain
        by_chain: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"requests": 0, "tokens": 0, "duration_ms": 0}
        )
        for r in records:
            by_chain[r.chain_name]["requests"] += 1
            by_chain[r.chain_name]["tokens"] += r.tokens_used
            by_chain[r.chain_name]["duration_ms"] += r.duration_ms

        # By step
        by_step: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"requests": 0, "tokens": 0, "duration_ms": 0}
        )
        for r in records:
            by_step[r.step_name]["requests"] += 1
            by_step[r.step_name]["tokens"] += r.tokens_used
            by_step[r.step_name]["duration_ms"] += r.duration_ms

        # Calculate cost
        total_cost = 0
        if self._track_costs:
            total_cost = (total_tokens / 1000) * self._cost_per_1k_tokens

        return {
            "total_requests": len(records),
            "total_tokens": total_tokens,
            "total_duration_ms": total_duration,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_count / len(records) if records else 0,
            "avg_duration_ms": total_duration / len(records) if records else 0,
            "avg_tokens_per_request": total_tokens / len(records) if records else 0,
            "total_cost": round(total_cost, 4),
            "by_chain": dict(by_chain),
            "by_step": dict(by_step),
        }

    def get_user_usage(self, user_id: str) -> dict[str, Any]:
        """Get usage for a specific user."""
        return self.get_usage_report(user_id=user_id)

    def get_chain_usage(self, chain_name: str) -> dict[str, Any]:
        """Get usage for a specific chain."""
        return self.get_usage_report(chain_name=chain_name)

    def get_quick_stats(self) -> dict[str, Any]:
        """
        Get quick aggregated stats without querying backend.

        Returns in-memory aggregated statistics.
        """
        total_requests = sum(s["total_requests"] for s in self._stats.values())
        total_tokens = sum(s["total_tokens"] for s in self._stats.values())
        total_duration = sum(s["total_duration_ms"] for s in self._stats.values())
        success = sum(s["success_count"] for s in self._stats.values())
        failure = sum(s["failure_count"] for s in self._stats.values())

        return {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_duration_ms": total_duration,
            "success_count": success,
            "failure_count": failure,
            "success_rate": success / total_requests if total_requests > 0 else 0,
            "unique_users": len(set(k.split(":")[0] for k in self._stats.keys())),
            "unique_chains": len(set(k.split(":")[1] for k in self._stats.keys())),
        }

    def export_records(
        self,
        path: str | Path,
        user_id: str | None = None,
        chain_name: str | None = None,
    ) -> int:
        """
        Export usage records to a file.

        Args:
            path: Output file path
            user_id: Filter by user ID
            chain_name: Filter by chain name

        Returns:
            Number of records exported
        """
        records = self._backend.query(user_id=user_id, chain_name=chain_name)

        with open(path, "w") as f:
            for record in records:
                f.write(json.dumps(record.to_dict()) + "\n")

        return len(records)

    def clear(self) -> None:
        """Clear all usage data."""
        if isinstance(self._backend, InMemoryUsageBackend):
            self._backend.clear()
        self._stats.clear()
