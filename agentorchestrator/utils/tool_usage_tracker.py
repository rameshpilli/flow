"""Thread-safe tool usage tracking system for MCP tool calls.

This module provides production-ready tracking for MCP tool invocations with:
- Thread-safe operations using threading.Lock
- Per-call metrics (duration, timestamp, arguments, result/error)
- Aggregated statistics (by tool, by source, error rates)
- JSON export for logging and observability
- OpenTelemetry-ready backend abstraction

Example:
    from agentorchestrator.utils.tool_usage_tracker import get_global_tracker

    tracker = get_global_tracker()

    # Record successful tool call
    tracker.record_call(
        tool_name="search",
        arguments={"query": "test"},
        result={"items": [...]},
        duration_ms=123.45
    )

    # Record failed tool call
    tracker.record_call(
        tool_name="search",
        arguments={"query": "test"},
        error="Connection timeout",
        duration_ms=5000.0
    )

    # Get statistics
    stats = tracker.get_stats()
    print(f"Total calls: {stats['total_calls']}")
    print(f"Error rate: {stats['error_rate']:.2%}")

    # Export to JSON
    export_data = tracker.export_json()
"""

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """Represents a single tool call with all associated metrics.

    Attributes:
        tool_name: Name of the MCP tool that was called
        arguments: Dictionary of arguments passed to the tool
        timestamp: Unix timestamp when the call was made
        duration_ms: Duration of the call in milliseconds
        result: Result returned by the tool (None if error)
        error: Error message if call failed (None if success)
        mcp_source: Source MCP server (e.g., "ravenpack", "capiq")
        cached: Whether the result was served from cache
        session_id: Optional session identifier
        user_id: Optional user identifier
    """

    tool_name: str
    arguments: Dict[str, Any]
    timestamp: float
    duration_ms: float
    result: Optional[Any] = None
    error: Optional[str] = None
    mcp_source: Optional[str] = None
    cached: bool = False
    session_id: Optional[str] = None
    user_id: Optional[str] = None

    def __post_init__(self):
        """Validate that either result or error is set, but not both."""
        if self.result is not None and self.error is not None:
            raise ValueError("ToolCallRecord cannot have both result and error set")
        if self.result is None and self.error is None:
            raise ValueError("ToolCallRecord must have either result or error set")

    @property
    def success(self) -> bool:
        """Returns True if the call succeeded (no error)."""
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for serialization."""
        return asdict(self)


class ObservabilityBackend(ABC):
    """Abstract base class for observability backends.

    This abstraction allows plugging in different backends like:
    - OpenTelemetry
    - Prometheus
    - DataDog
    - Custom logging systems
    """

    @abstractmethod
    def record_tool_call(self, record: ToolCallRecord) -> None:
        """Record a tool call to the observability backend.

        Args:
            record: The tool call record to record
        """
        pass

    @abstractmethod
    def flush(self) -> None:
        """Flush any buffered metrics to the backend."""
        pass


class LoggingBackend(ObservabilityBackend):
    """Simple logging-based observability backend.

    Logs tool calls at INFO level (success) or WARNING level (errors).
    """

    def __init__(self, logger_name: str = __name__):
        self.logger = logging.getLogger(logger_name)

    def record_tool_call(self, record: ToolCallRecord) -> None:
        """Log the tool call."""
        if record.success:
            self.logger.info(
                f"Tool call: {record.tool_name} "
                f"(source={record.mcp_source}, duration={record.duration_ms:.2f}ms, "
                f"cached={record.cached})"
            )
        else:
            self.logger.warning(
                f"Tool call failed: {record.tool_name} "
                f"(source={record.mcp_source}, duration={record.duration_ms:.2f}ms, "
                f"error={record.error})"
            )

    def flush(self) -> None:
        """No-op for logging backend."""
        pass


class ToolUsageTracker:
    """Thread-safe tracker for MCP tool usage.

    Records all tool calls with detailed metrics and provides aggregated statistics.
    Designed to be used as a singleton via get_global_tracker().

    Attributes:
        max_records: Maximum number of records to keep in memory (LRU eviction)
        backend: Optional observability backend for real-time metrics
    """

    def __init__(
        self,
        max_records: int = 10000,
        backend: Optional[ObservabilityBackend] = None
    ):
        """Initialize the tracker.

        Args:
            max_records: Maximum records to keep (default: 10000)
            backend: Optional observability backend (default: LoggingBackend)
        """
        self.max_records = max_records
        self.backend = backend or LoggingBackend()

        # Thread-safe record storage
        self._lock = threading.Lock()
        self._records: List[ToolCallRecord] = []

        # Pre-computed statistics (updated on each record)
        self._total_calls = 0
        self._error_count = 0
        self._cache_hit_count = 0
        self._by_tool: Dict[str, int] = defaultdict(int)
        self._by_source: Dict[str, int] = defaultdict(int)
        self._errors_by_tool: Dict[str, int] = defaultdict(int)

    def record_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        duration_ms: float,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        mcp_source: Optional[str] = None,
        cached: bool = False,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """Record a tool call.

        Args:
            tool_name: Name of the MCP tool
            arguments: Arguments passed to the tool
            duration_ms: Duration in milliseconds
            result: Result from the tool (if successful)
            error: Error message (if failed)
            mcp_source: Source MCP server (e.g., "ravenpack")
            cached: Whether result was from cache
            session_id: Optional session identifier
            user_id: Optional user identifier

        Raises:
            ValueError: If both result and error are provided or neither is provided
        """
        # Create record
        record = ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            timestamp=time.time(),
            duration_ms=duration_ms,
            result=result,
            error=error,
            mcp_source=mcp_source,
            cached=cached,
            session_id=session_id,
            user_id=user_id
        )

        # Record to backend (outside lock for performance)
        try:
            self.backend.record_tool_call(record)
        except Exception as e:
            logger.error(f"Failed to record tool call to backend: {e}")

        # Update internal storage and statistics
        with self._lock:
            # Add to records list
            self._records.append(record)

            # Apply LRU eviction if needed
            if len(self._records) > self.max_records:
                self._records.pop(0)

            # Update statistics
            self._total_calls += 1
            self._by_tool[tool_name] += 1

            if mcp_source:
                self._by_source[mcp_source] += 1

            if error:
                self._error_count += 1
                self._errors_by_tool[tool_name] += 1

            if cached:
                self._cache_hit_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics.

        Returns:
            Dictionary containing:
                - total_calls: Total number of tool calls
                - error_count: Number of failed calls
                - error_rate: Percentage of calls that failed (0.0-1.0)
                - cache_hit_count: Number of calls served from cache
                - cache_hit_rate: Percentage of calls from cache (0.0-1.0)
                - by_tool: Call counts by tool name
                - by_source: Call counts by MCP source
                - errors_by_tool: Error counts by tool name
                - avg_duration_ms: Average call duration
                - total_duration_ms: Total time spent in tool calls
        """
        with self._lock:
            # Calculate duration stats
            total_duration = sum(r.duration_ms for r in self._records)
            avg_duration = total_duration / len(self._records) if self._records else 0.0

            return {
                "total_calls": self._total_calls,
                "error_count": self._error_count,
                "error_rate": self._error_count / self._total_calls if self._total_calls > 0 else 0.0,
                "cache_hit_count": self._cache_hit_count,
                "cache_hit_rate": self._cache_hit_count / self._total_calls if self._total_calls > 0 else 0.0,
                "by_tool": dict(self._by_tool),
                "by_source": dict(self._by_source),
                "errors_by_tool": dict(self._errors_by_tool),
                "avg_duration_ms": avg_duration,
                "total_duration_ms": total_duration,
                "records_in_memory": len(self._records),
                "max_records": self.max_records
            }

    def get_records(
        self,
        tool_name: Optional[str] = None,
        mcp_source: Optional[str] = None,
        errors_only: bool = False,
        limit: Optional[int] = None
    ) -> List[ToolCallRecord]:
        """Get tool call records with optional filtering.

        Args:
            tool_name: Filter by tool name
            mcp_source: Filter by MCP source
            errors_only: Only return failed calls
            limit: Maximum number of records to return (most recent first)

        Returns:
            List of matching ToolCallRecords (most recent first)
        """
        with self._lock:
            records = list(reversed(self._records))  # Most recent first

            # Apply filters
            if tool_name:
                records = [r for r in records if r.tool_name == tool_name]

            if mcp_source:
                records = [r for r in records if r.mcp_source == mcp_source]

            if errors_only:
                records = [r for r in records if r.error is not None]

            # Apply limit
            if limit:
                records = records[:limit]

            return records

    def export_json(
        self,
        tool_name: Optional[str] = None,
        mcp_source: Optional[str] = None,
        errors_only: bool = False,
        limit: Optional[int] = None,
        include_stats: bool = True
    ) -> str:
        """Export records as JSON string.

        Args:
            tool_name: Filter by tool name
            mcp_source: Filter by MCP source
            errors_only: Only return failed calls
            limit: Maximum number of records to return
            include_stats: Include aggregated statistics in export

        Returns:
            JSON string with records and optional statistics
        """
        records = self.get_records(
            tool_name=tool_name,
            mcp_source=mcp_source,
            errors_only=errors_only,
            limit=limit
        )

        export_data = {
            "records": [r.to_dict() for r in records],
            "record_count": len(records)
        }

        if include_stats:
            export_data["statistics"] = self.get_stats()

        return json.dumps(export_data, indent=2, default=str)

    def clear(self) -> None:
        """Clear all records and reset statistics.

        Warning: This operation cannot be undone.
        """
        with self._lock:
            self._records.clear()
            self._total_calls = 0
            self._error_count = 0
            self._cache_hit_count = 0
            self._by_tool.clear()
            self._by_source.clear()
            self._errors_by_tool.clear()

        logger.info("Tool usage tracker cleared")

    def flush(self) -> None:
        """Flush any buffered metrics to the observability backend."""
        try:
            self.backend.flush()
        except Exception as e:
            logger.error(f"Failed to flush observability backend: {e}")


# Global singleton instance
_global_tracker: Optional[ToolUsageTracker] = None
_global_tracker_lock = threading.Lock()


def get_global_tracker(
    max_records: int = 10000,
    backend: Optional[ObservabilityBackend] = None
) -> ToolUsageTracker:
    """Get or create the global ToolUsageTracker singleton.

    Args:
        max_records: Maximum records to keep (only used on first call)
        backend: Optional observability backend (only used on first call)

    Returns:
        The global ToolUsageTracker instance
    """
    global _global_tracker

    if _global_tracker is None:
        with _global_tracker_lock:
            if _global_tracker is None:
                _global_tracker = ToolUsageTracker(
                    max_records=max_records,
                    backend=backend
                )
                logger.info(
                    f"Initialized global tool usage tracker "
                    f"(max_records={max_records})"
                )

    return _global_tracker


def reset_global_tracker() -> None:
    """Reset the global tracker singleton.

    Useful for testing. Not recommended for production use.
    """
    global _global_tracker

    with _global_tracker_lock:
        if _global_tracker:
            _global_tracker.clear()
        _global_tracker = None
        logger.info("Global tool usage tracker reset")