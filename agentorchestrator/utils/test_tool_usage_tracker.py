"""Unit tests for tool usage tracker."""

import json
import threading
import time

import pytest

from agentorchestrator.utils.tool_usage_tracker import (
    LoggingBackend,
    ToolCallRecord,
    ToolUsageTracker,
    get_global_tracker,
    reset_global_tracker,
)


class TestToolCallRecord:
    """Tests for ToolCallRecord dataclass."""

    def test_successful_call_record(self):
        """Test creating a successful call record."""
        record = ToolCallRecord(
            tool_name="search",
            arguments={"query": "test"},
            timestamp=time.time(),
            duration_ms=100.0,
            result={"items": [1, 2, 3]},
            mcp_source="ravenpack",
        )

        assert record.tool_name == "search"
        assert record.success is True
        assert record.error is None
        assert record.mcp_source == "ravenpack"

    def test_error_call_record(self):
        """Test creating an error call record."""
        record = ToolCallRecord(
            tool_name="search",
            arguments={"query": "test"},
            timestamp=time.time(),
            duration_ms=5000.0,
            error="Connection timeout",
            mcp_source="capiq",
        )

        assert record.tool_name == "search"
        assert record.success is False
        assert record.error == "Connection timeout"
        assert record.result is None

    def test_validation_both_result_and_error(self):
        """Test that record cannot have both result and error."""
        with pytest.raises(ValueError, match="cannot have both result and error"):
            ToolCallRecord(
                tool_name="test",
                arguments={},
                timestamp=time.time(),
                duration_ms=100.0,
                result={"data": "test"},
                error="Some error",
            )

    def test_validation_neither_result_nor_error(self):
        """Test that record must have either result or error."""
        with pytest.raises(ValueError, match="must have either result or error"):
            ToolCallRecord(
                tool_name="test",
                arguments={},
                timestamp=time.time(),
                duration_ms=100.0,
            )

    def test_to_dict(self):
        """Test conversion to dictionary."""
        record = ToolCallRecord(
            tool_name="test",
            arguments={"key": "value"},
            timestamp=123.456,
            duration_ms=100.0,
            result={"data": "test"},
        )

        record_dict = record.to_dict()

        assert record_dict["tool_name"] == "test"
        assert record_dict["arguments"] == {"key": "value"}
        assert record_dict["timestamp"] == 123.456
        assert record_dict["duration_ms"] == 100.0


class TestToolUsageTracker:
    """Tests for ToolUsageTracker class."""

    def test_record_successful_call(self):
        """Test recording a successful tool call."""
        tracker = ToolUsageTracker()

        tracker.record_call(
            tool_name="search",
            arguments={"query": "test"},
            duration_ms=100.0,
            result={"items": [1, 2, 3]},
            mcp_source="ravenpack",
        )

        stats = tracker.get_stats()
        assert stats["total_calls"] == 1
        assert stats["error_count"] == 0
        assert stats["error_rate"] == 0.0

    def test_record_error_call(self):
        """Test recording a failed tool call."""
        tracker = ToolUsageTracker()

        tracker.record_call(
            tool_name="search",
            arguments={"query": "test"},
            duration_ms=5000.0,
            error="Timeout",
            mcp_source="capiq",
        )

        stats = tracker.get_stats()
        assert stats["total_calls"] == 1
        assert stats["error_count"] == 1
        assert stats["error_rate"] == 1.0

    def test_cache_hit_tracking(self):
        """Test tracking of cache hits."""
        tracker = ToolUsageTracker()

        tracker.record_call(
            tool_name="search",
            arguments={"query": "test"},
            duration_ms=50.0,
            result={"items": []},
            cached=True,
        )

        stats = tracker.get_stats()
        assert stats["cache_hit_count"] == 1
        assert stats["cache_hit_rate"] == 1.0

    def test_statistics_aggregation(self):
        """Test aggregated statistics calculation."""
        tracker = ToolUsageTracker()

        # Record multiple calls
        tracker.record_call("tool1", {}, 100.0, result={"ok": True})
        tracker.record_call("tool2", {}, 200.0, result={"ok": True}, mcp_source="ravenpack")
        tracker.record_call("tool1", {}, 300.0, error="Failed")
        tracker.record_call("tool3", {}, 400.0, result={"ok": True}, mcp_source="capiq")

        stats = tracker.get_stats()

        assert stats["total_calls"] == 4
        assert stats["error_count"] == 1
        assert stats["error_rate"] == 0.25
        assert stats["by_tool"] == {"tool1": 2, "tool2": 1, "tool3": 1}
        assert stats["by_source"] == {"ravenpack": 1, "capiq": 1}
        assert stats["errors_by_tool"] == {"tool1": 1}
        assert stats["avg_duration_ms"] == 250.0
        assert stats["total_duration_ms"] == 1000.0

    def test_get_records_all(self):
        """Test retrieving all records."""
        tracker = ToolUsageTracker()

        tracker.record_call("tool1", {}, 100.0, result={"ok": True})
        tracker.record_call("tool2", {}, 200.0, result={"ok": True})

        records = tracker.get_records()
        assert len(records) == 2
        # Most recent first
        assert records[0].tool_name == "tool2"
        assert records[1].tool_name == "tool1"

    def test_get_records_filter_by_tool(self):
        """Test filtering records by tool name."""
        tracker = ToolUsageTracker()

        tracker.record_call("tool1", {}, 100.0, result={"ok": True})
        tracker.record_call("tool2", {}, 200.0, result={"ok": True})
        tracker.record_call("tool1", {}, 300.0, result={"ok": True})

        records = tracker.get_records(tool_name="tool1")
        assert len(records) == 2
        assert all(r.tool_name == "tool1" for r in records)

    def test_get_records_filter_by_source(self):
        """Test filtering records by MCP source."""
        tracker = ToolUsageTracker()

        tracker.record_call("tool1", {}, 100.0, result={"ok": True}, mcp_source="ravenpack")
        tracker.record_call("tool2", {}, 200.0, result={"ok": True}, mcp_source="capiq")
        tracker.record_call("tool3", {}, 300.0, result={"ok": True}, mcp_source="ravenpack")

        records = tracker.get_records(mcp_source="ravenpack")
        assert len(records) == 2
        assert all(r.mcp_source == "ravenpack" for r in records)

    def test_get_records_errors_only(self):
        """Test filtering to get only errors."""
        tracker = ToolUsageTracker()

        tracker.record_call("tool1", {}, 100.0, result={"ok": True})
        tracker.record_call("tool2", {}, 200.0, error="Failed")
        tracker.record_call("tool3", {}, 300.0, error="Timeout")

        records = tracker.get_records(errors_only=True)
        assert len(records) == 2
        assert all(r.error is not None for r in records)

    def test_get_records_with_limit(self):
        """Test limiting number of records returned."""
        tracker = ToolUsageTracker()

        for i in range(10):
            tracker.record_call(f"tool{i}", {}, 100.0, result={"ok": True})

        records = tracker.get_records(limit=3)
        assert len(records) == 3

    def test_export_json(self):
        """Test JSON export."""
        tracker = ToolUsageTracker()

        tracker.record_call("tool1", {"key": "value"}, 100.0, result={"ok": True})

        export_str = tracker.export_json()
        export_data = json.loads(export_str)

        assert "records" in export_data
        assert "statistics" in export_data
        assert export_data["record_count"] == 1

    def test_export_json_without_stats(self):
        """Test JSON export without statistics."""
        tracker = ToolUsageTracker()

        tracker.record_call("tool1", {}, 100.0, result={"ok": True})

        export_str = tracker.export_json(include_stats=False)
        export_data = json.loads(export_str)

        assert "records" in export_data
        assert "statistics" not in export_data

    def test_clear(self):
        """Test clearing all records."""
        tracker = ToolUsageTracker()

        tracker.record_call("tool1", {}, 100.0, result={"ok": True})
        tracker.record_call("tool2", {}, 200.0, result={"ok": True})

        tracker.clear()

        stats = tracker.get_stats()
        assert stats["total_calls"] == 0
        assert stats["records_in_memory"] == 0
        assert len(tracker.get_records()) == 0

    def test_lru_eviction(self):
        """Test LRU eviction when max_records is exceeded."""
        tracker = ToolUsageTracker(max_records=5)

        # Add 10 records
        for i in range(10):
            tracker.record_call(f"tool{i}", {"i": i}, 100.0, result={"ok": True})

        stats = tracker.get_stats()
        assert stats["total_calls"] == 10  # All calls tracked in stats
        assert stats["records_in_memory"] == 5  # Only 5 kept in memory

        records = tracker.get_records()
        assert len(records) == 5
        # Most recent should be kept (tool9, tool8, tool7, tool6, tool5)
        assert records[0].tool_name == "tool9"
        assert records[-1].tool_name == "tool5"

    def test_thread_safety(self):
        """Test thread-safe recording."""
        tracker = ToolUsageTracker()

        def record_calls(count):
            for i in range(count):
                tracker.record_call(f"tool{i}", {}, 100.0, result={"ok": True})

        threads = []
        for _ in range(5):
            t = threading.Thread(target=record_calls, args=(20,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        stats = tracker.get_stats()
        assert stats["total_calls"] == 100


class TestGlobalTracker:
    """Tests for global tracker singleton."""

    def test_get_global_tracker_singleton(self):
        """Test that get_global_tracker returns singleton."""
        reset_global_tracker()

        tracker1 = get_global_tracker()
        tracker2 = get_global_tracker()

        assert tracker1 is tracker2

    def test_global_tracker_shares_state(self):
        """Test that global tracker shares state across references."""
        reset_global_tracker()

        tracker1 = get_global_tracker()
        tracker1.record_call("test", {}, 100.0, result={"ok": True})

        tracker2 = get_global_tracker()
        stats = tracker2.get_stats()

        assert stats["total_calls"] == 1

    def test_reset_global_tracker(self):
        """Test resetting the global tracker."""
        reset_global_tracker()

        tracker1 = get_global_tracker()
        tracker1.record_call("test", {}, 100.0, result={"ok": True})

        reset_global_tracker()

        tracker2 = get_global_tracker()
        stats = tracker2.get_stats()

        assert stats["total_calls"] == 0