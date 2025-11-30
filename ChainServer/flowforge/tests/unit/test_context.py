"""
Unit Tests for FlowForge Context Module

Tests for:
- ChainContext: Shared state management across chain steps
- ContextScope: Scoped data lifetime management
- StepResult: Step execution result tracking
- ExecutionSummary: Chain execution summary
- ContextManager: Global context management
"""

import asyncio
from datetime import datetime

import pytest

from flowforge.core.context import (
    ChainContext,
    ContextEntry,
    ContextManager,
    ContextScope,
    ExecutionSummary,
    StepResult,
)


# ══════════════════════════════════════════════════════════════════════════════
#                           ChainContext Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestChainContext:
    """Tests for ChainContext class."""

    def test_context_creation(self):
        """Test basic context creation."""
        ctx = ChainContext(request_id="req_123")

        assert ctx.request_id == "req_123"
        assert len(ctx.keys()) == 0
        assert ctx.total_tokens == 0
        assert ctx.created_at is not None

    def test_context_with_initial_data(self):
        """Test context creation with initial data."""
        ctx = ChainContext(
            request_id="req_456",
            initial_data={
                "company": "Apple",
                "ticker": "AAPL",
            },
        )

        assert ctx.get("company") == "Apple"
        assert ctx.get("ticker") == "AAPL"
        assert len(ctx.keys()) == 2

    def test_set_and_get(self):
        """Test basic set and get operations."""
        ctx = ChainContext(request_id="test")

        ctx.set("key1", "value1")
        ctx.set("key2", {"nested": "data"})
        ctx.set("key3", [1, 2, 3])

        assert ctx.get("key1") == "value1"
        assert ctx.get("key2") == {"nested": "data"}
        assert ctx.get("key3") == [1, 2, 3]

    def test_get_default_value(self):
        """Test get with default value for missing keys."""
        ctx = ChainContext(request_id="test")

        assert ctx.get("missing") is None
        assert ctx.get("missing", "default") == "default"
        assert ctx.get("missing", 42) == 42

    def test_has_key(self):
        """Test has() method for key existence."""
        ctx = ChainContext(request_id="test")

        ctx.set("exists", True)

        assert ctx.has("exists") is True
        assert ctx.has("missing") is False

    def test_delete_key(self):
        """Test delete() method."""
        ctx = ChainContext(request_id="test")

        ctx.set("to_delete", "value")
        assert ctx.has("to_delete") is True

        result = ctx.delete("to_delete")
        assert result is True
        assert ctx.has("to_delete") is False

        # Delete non-existent key
        result = ctx.delete("missing")
        assert result is False

    def test_keys_method(self):
        """Test keys() method returns all keys."""
        ctx = ChainContext(request_id="test")

        ctx.set("a", 1)
        ctx.set("b", 2)
        ctx.set("c", 3)

        keys = ctx.keys()
        assert set(keys) == {"a", "b", "c"}

    def test_update_existing_key(self):
        """Test updating an existing key preserves created_at."""
        ctx = ChainContext(request_id="test")

        ctx.set("key", "original")
        entry1 = ctx.get_entry("key")
        original_created = entry1.created_at

        # Small delay to ensure timestamps differ
        import time
        time.sleep(0.01)

        ctx.set("key", "updated")
        entry2 = ctx.get_entry("key")

        assert entry2.value == "updated"
        assert entry2.created_at == original_created  # Preserved
        assert entry2.updated_at > original_created  # Updated

    def test_token_tracking(self):
        """Test token count tracking."""
        ctx = ChainContext(request_id="test")

        ctx.set("small", "data", token_count=100)
        ctx.set("large", "lots of data", token_count=500)

        assert ctx.total_tokens == 600

    def test_metadata_storage(self):
        """Test storing metadata with entries."""
        ctx = ChainContext(request_id="test")

        ctx.set(
            "data",
            {"value": 1},
            metadata={"source": "api", "version": "1.0"},
        )

        entry = ctx.get_entry("data")
        assert entry.metadata["source"] == "api"
        assert entry.metadata["version"] == "1.0"


# ══════════════════════════════════════════════════════════════════════════════
#                           ContextScope Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestContextScope:
    """Tests for scoped data storage."""

    def test_chain_scope_persists(self):
        """Test CHAIN scope data persists across steps."""
        ctx = ChainContext(request_id="test")

        # Enter step and set chain-scoped data
        ctx.enter_step("step1")
        ctx.set("chain_data", "persists", scope=ContextScope.CHAIN)
        ctx.exit_step()

        # Data should still be accessible
        assert ctx.get("chain_data") == "persists"

    def test_step_scope_cleared_on_exit(self):
        """Test STEP scope data is cleared when exiting step."""
        ctx = ChainContext(request_id="test")

        ctx.enter_step("step1")
        ctx.set("step_data", "temporary", scope=ContextScope.STEP)
        assert ctx.get("step_data") == "temporary"

        ctx.exit_step()
        assert ctx.get("step_data") is None

    def test_step_scope_isolation(self):
        """Test STEP scope data is isolated between steps."""
        ctx = ChainContext(request_id="test")

        # Step 1 sets data
        ctx.enter_step("step1")
        ctx.set("step_data", "from_step1", scope=ContextScope.STEP)
        ctx.exit_step()

        # Step 2 cannot see step1's data
        ctx.enter_step("step2")
        assert ctx.get("step_data") is None
        ctx.exit_step()

    @pytest.mark.asyncio
    async def test_step_scope_async_context_manager(self):
        """Test step_scope async context manager."""
        ctx = ChainContext(request_id="test")

        async with ctx.step_scope("my_step"):
            ctx.set("temp", "value", scope=ContextScope.STEP)
            assert ctx.get("temp") == "value"
            assert ctx.current_step == "my_step"

        # Data should be cleaned up
        assert ctx.get("temp") is None
        assert ctx.current_step is None

    def test_step_scope_sync_context_manager(self):
        """Test step_scope_sync sync context manager."""
        ctx = ChainContext(request_id="test")

        with ctx.step_scope_sync("my_step"):
            ctx.set("temp", "value", scope=ContextScope.STEP)
            assert ctx.get("temp") == "value"

        assert ctx.get("temp") is None

    @pytest.mark.asyncio
    async def test_step_scope_cleanup_on_exception(self):
        """Test step-scoped data is cleaned up even on exception."""
        ctx = ChainContext(request_id="test")

        with pytest.raises(RuntimeError):
            async with ctx.step_scope("failing_step"):
                ctx.set("temp", "value", scope=ContextScope.STEP)
                raise RuntimeError("Intentional error")

        # Data should still be cleaned up
        assert ctx.get("temp") is None

    def test_keys_filtered_by_scope(self):
        """Test keys() can filter by scope."""
        ctx = ChainContext(request_id="test")

        ctx.set("chain_key", "value", scope=ContextScope.CHAIN)

        ctx.enter_step("step1")
        ctx.set("step_key", "value", scope=ContextScope.STEP)

        chain_keys = ctx.keys(scope=ContextScope.CHAIN)
        step_keys = ctx.keys(scope=ContextScope.STEP)

        assert "chain_key" in chain_keys
        assert "step_key" not in chain_keys
        assert "step_key" in step_keys

        ctx.exit_step()


# ══════════════════════════════════════════════════════════════════════════════
#                           StepResult Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestStepResult:
    """Tests for StepResult class."""

    def test_successful_result(self):
        """Test creating a successful step result."""
        result = StepResult(
            step_name="my_step",
            output={"data": "value"},
            duration_ms=150.5,
        )

        assert result.success is True
        assert result.failed is False
        assert result.skipped is False
        assert result.step_name == "my_step"
        assert result.output == {"data": "value"}
        assert result.duration_ms == 150.5

    def test_failed_result(self):
        """Test creating a failed step result."""
        error = RuntimeError("Something went wrong")
        result = StepResult(
            step_name="failing_step",
            output=None,
            duration_ms=50.0,
            error=error,
            error_type="RuntimeError",
            error_traceback="traceback here",
        )

        assert result.success is False
        assert result.failed is True
        assert result.skipped is False
        assert result.error == error
        assert result.error_type == "RuntimeError"

    def test_skipped_result(self):
        """Test creating a skipped step result."""
        result = StepResult(
            step_name="skipped_step",
            output=None,
            duration_ms=0,
            skipped_reason="dependency failed: dep1",
        )

        assert result.success is False
        assert result.failed is False
        assert result.skipped is True
        assert result.skipped_reason == "dependency failed: dep1"

    def test_result_with_retry_count(self):
        """Test result tracking retry count."""
        result = StepResult(
            step_name="flaky_step",
            output={"data": "finally"},
            duration_ms=300,
            retry_count=2,
        )

        assert result.retry_count == 2
        assert result.success is True

    def test_result_to_dict(self):
        """Test serializing result to dictionary."""
        error = ValueError("Bad value")
        result = StepResult(
            step_name="test_step",
            output={"key": "value"},
            duration_ms=100,
            token_count=50,
            metadata={"source": "test"},
            error=error,
            error_type="ValueError",
            error_traceback="traceback",
            retry_count=1,
            skipped_reason=None,
        )

        d = result.to_dict()

        assert d["step_name"] == "test_step"
        assert d["success"] is False
        assert d["output"] == {"key": "value"}
        assert d["duration_ms"] == 100
        assert d["token_count"] == 50
        assert d["error"] == "Bad value"
        assert d["error_type"] == "ValueError"
        assert d["retry_count"] == 1


# ══════════════════════════════════════════════════════════════════════════════
#                           ExecutionSummary Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestExecutionSummary:
    """Tests for ExecutionSummary class."""

    def test_summary_creation(self):
        """Test creating an execution summary."""
        summary = ExecutionSummary(
            chain_name="test_chain",
            request_id="req_123",
            total_steps=5,
        )

        assert summary.chain_name == "test_chain"
        assert summary.request_id == "req_123"
        assert summary.total_steps == 5
        assert summary.completed_steps == 0
        assert summary.failed_steps == 0
        assert summary.skipped_steps == 0

    def test_add_successful_result(self):
        """Test adding a successful result updates counters."""
        summary = ExecutionSummary(
            chain_name="test",
            request_id="req",
            total_steps=3,
        )

        result = StepResult(
            step_name="step1",
            output={"data": 1},
            duration_ms=100,
        )
        summary.add_result(result)

        assert summary.completed_steps == 1
        assert summary.failed_steps == 0
        assert summary.total_duration_ms == 100

    def test_add_failed_result(self):
        """Test adding a failed result updates counters."""
        summary = ExecutionSummary(
            chain_name="test",
            request_id="req",
            total_steps=3,
        )

        result = StepResult(
            step_name="fail",
            output=None,
            duration_ms=50,
            error=RuntimeError("error"),
        )
        summary.add_result(result)

        assert summary.completed_steps == 0
        assert summary.failed_steps == 1

    def test_add_skipped_result(self):
        """Test adding a skipped result updates counters."""
        summary = ExecutionSummary(
            chain_name="test",
            request_id="req",
            total_steps=3,
        )

        result = StepResult(
            step_name="skip",
            output=None,
            duration_ms=0,
            skipped_reason="dependency failed",
        )
        summary.add_result(result)

        assert summary.completed_steps == 0
        assert summary.skipped_steps == 1

    def test_completion_rate(self):
        """Test completion rate calculation."""
        summary = ExecutionSummary(
            chain_name="test",
            request_id="req",
            total_steps=4,
        )

        # Add 2 successful, 1 failed, 1 skipped
        summary.add_result(StepResult("s1", {"a": 1}, 100))
        summary.add_result(StepResult("s2", {"b": 2}, 100))
        summary.add_result(StepResult("s3", None, 50, error=RuntimeError()))
        summary.add_result(StepResult("s4", None, 0, skipped_reason="skipped"))

        assert summary.completion_rate == 50.0  # 2/4 = 50%

    def test_finalize_full_success(self):
        """Test finalize() when all steps succeed."""
        summary = ExecutionSummary(
            chain_name="test",
            request_id="req",
            total_steps=2,
        )

        summary.add_result(StepResult("s1", {}, 100))
        summary.add_result(StepResult("s2", {}, 100))
        summary.finalize()

        assert summary.success is True
        assert summary.partial_success is False

    def test_finalize_partial_success(self):
        """Test finalize() when some steps fail."""
        summary = ExecutionSummary(
            chain_name="test",
            request_id="req",
            total_steps=2,
        )

        summary.add_result(StepResult("s1", {}, 100))
        summary.add_result(StepResult("s2", None, 50, error=RuntimeError()))
        summary.finalize()

        assert summary.success is False
        assert summary.partial_success is True

    def test_get_result_categories(self):
        """Test getting results by category."""
        summary = ExecutionSummary(
            chain_name="test",
            request_id="req",
            total_steps=3,
        )

        summary.add_result(StepResult("ok", {}, 100))
        summary.add_result(StepResult("fail", None, 50, error=RuntimeError()))
        summary.add_result(StepResult("skip", None, 0, skipped_reason="skipped"))

        successful = summary.get_successful_steps()
        failed = summary.get_failed_steps()
        skipped = summary.get_skipped_steps()

        assert len(successful) == 1
        assert successful[0].step_name == "ok"
        assert len(failed) == 1
        assert failed[0].step_name == "fail"
        assert len(skipped) == 1
        assert skipped[0].step_name == "skip"

    def test_to_dict(self):
        """Test serializing summary to dictionary."""
        summary = ExecutionSummary(
            chain_name="test_chain",
            request_id="req_123",
            total_steps=2,
        )

        summary.add_result(StepResult("s1", {"data": 1}, 100))
        summary.finalize()

        d = summary.to_dict()

        assert d["chain_name"] == "test_chain"
        assert d["request_id"] == "req_123"
        assert d["total_steps"] == 2
        assert d["completed_steps"] == 1
        assert "step_results" in d


# ══════════════════════════════════════════════════════════════════════════════
#                           Context Results Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestContextResults:
    """Tests for result management in ChainContext."""

    def test_add_result(self):
        """Test adding results to context."""
        ctx = ChainContext(request_id="test")

        result = StepResult("step1", {"output": 1}, 100)
        ctx.add_result(result)

        assert len(ctx.results) == 1
        assert ctx.results[0].step_name == "step1"

    def test_results_preserved(self):
        """Test results are preserved in order."""
        ctx = ChainContext(request_id="test")

        ctx.add_result(StepResult("s1", {}, 100))
        ctx.add_result(StepResult("s2", {}, 200))
        ctx.add_result(StepResult("s3", {}, 150))

        names = [r.step_name for r in ctx.results]
        assert names == ["s1", "s2", "s3"]

    def test_last_result(self):
        """Test getting the last result."""
        ctx = ChainContext(request_id="test")

        assert ctx.last_result is None

        ctx.add_result(StepResult("s1", {}, 100))
        ctx.add_result(StepResult("s2", {}, 200))

        assert ctx.last_result.step_name == "s2"

    def test_get_result_by_name(self):
        """Test getting result by step name."""
        ctx = ChainContext(request_id="test")

        ctx.add_result(StepResult("step1", {"a": 1}, 100))
        ctx.add_result(StepResult("step2", {"b": 2}, 200))

        result = ctx.get_result("step1")
        assert result.output == {"a": 1}

        result = ctx.get_result("step2")
        assert result.output == {"b": 2}

        result = ctx.get_result("missing")
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
#                           Context Serialization Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestContextSerialization:
    """Tests for context serialization."""

    def test_to_dict_basic(self):
        """Test basic context serialization."""
        ctx = ChainContext(request_id="req_123")
        ctx.set("key1", "value1")
        ctx.set("key2", {"nested": "data"})

        d = ctx.to_dict()

        assert d["request_id"] == "req_123"
        assert "created_at" in d
        assert d["data"]["key1"] == "value1"
        assert d["data"]["key2"] == {"nested": "data"}

    def test_to_dict_without_data(self):
        """Test serialization without data (lightweight summary)."""
        ctx = ChainContext(request_id="req_123")
        ctx.set("large_data", "x" * 10000)

        d = ctx.to_dict(include_data=False)

        assert d["request_id"] == "req_123"
        assert "data" not in d

    def test_to_dict_with_results(self):
        """Test serialization includes results."""
        ctx = ChainContext(request_id="test")
        ctx.add_result(StepResult("s1", {}, 100))
        ctx.add_result(StepResult("s2", {}, 200))

        d = ctx.to_dict()

        assert len(d["results"]) == 2
        assert d["results"][0]["step"] == "s1"
        assert d["results"][1]["step"] == "s2"


# ══════════════════════════════════════════════════════════════════════════════
#                           Context Clone Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestContextClone:
    """Tests for context cloning."""

    def test_clone_basic(self):
        """Test basic context cloning."""
        ctx = ChainContext(request_id="original")
        ctx.set("key", "value")

        clone = ctx.clone()

        assert clone.request_id == "original"
        assert clone.get("key") == "value"

    def test_clone_independence(self):
        """Test cloned context is independent."""
        ctx = ChainContext(request_id="test")
        ctx.set("key", "original")

        clone = ctx.clone()
        clone.set("key", "modified")
        clone.set("new_key", "new_value")

        assert ctx.get("key") == "original"
        assert ctx.get("new_key") is None

    def test_clone_results_independence(self):
        """Test cloned results are independent."""
        ctx = ChainContext(request_id="test")
        ctx.add_result(StepResult("s1", {}, 100))

        clone = ctx.clone()
        clone.add_result(StepResult("s2", {}, 200))

        assert len(ctx.results) == 1
        assert len(clone.results) == 2


# ══════════════════════════════════════════════════════════════════════════════
#                           ContextManager Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestContextManager:
    """Tests for global ContextManager."""

    def test_singleton_pattern(self):
        """Test ContextManager is a singleton."""
        cm1 = ContextManager()
        cm2 = ContextManager()

        assert cm1 is cm2

    def test_create_and_get_context(self):
        """Test creating and retrieving contexts."""
        cm = ContextManager()

        ctx = cm.create_context("req_123", {"data": "value"})

        assert ctx.request_id == "req_123"
        assert ctx.get("data") == "value"

        retrieved = cm.get_context("req_123")
        assert retrieved is ctx

    def test_remove_context(self):
        """Test removing contexts."""
        cm = ContextManager()

        cm.create_context("to_remove")
        assert cm.get_context("to_remove") is not None

        result = cm.remove_context("to_remove")
        assert result is True
        assert cm.get_context("to_remove") is None

        # Remove non-existent
        result = cm.remove_context("missing")
        assert result is False

    def test_global_storage(self):
        """Test global key-value storage."""
        cm = ContextManager()

        cm.set_global("config", {"debug": True})

        assert cm.get_global("config") == {"debug": True}
        assert cm.get_global("missing") is None
        assert cm.get_global("missing", "default") == "default"


# ══════════════════════════════════════════════════════════════════════════════
#                           Thread Safety Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestContextThreadSafety:
    """Tests for context thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_set_get(self):
        """Test concurrent set/get operations are safe."""
        ctx = ChainContext(request_id="concurrent")

        async def writer(key: str, value: str):
            for i in range(100):
                ctx.set(f"{key}_{i}", f"{value}_{i}")
                await asyncio.sleep(0)

        async def reader(key: str):
            for i in range(100):
                ctx.get(f"{key}_{i}")
                await asyncio.sleep(0)

        # Run concurrent writers and readers
        await asyncio.gather(
            writer("a", "value_a"),
            writer("b", "value_b"),
            reader("a"),
            reader("b"),
        )

        # Verify data integrity
        for i in range(100):
            assert ctx.get(f"a_{i}") == f"value_a_{i}"
            assert ctx.get(f"b_{i}") == f"value_b_{i}"

    @pytest.mark.asyncio
    async def test_concurrent_step_scopes(self):
        """Test concurrent step scopes are isolated via contextvars."""
        ctx = ChainContext(request_id="parallel_steps")
        results = {}

        async def step_worker(step_name: str):
            async with ctx.step_scope(step_name):
                # Set step-scoped data
                ctx.set("my_data", step_name, scope=ContextScope.STEP)
                # Small delay to allow interleaving
                await asyncio.sleep(0.01)
                # Read back - should see our own data
                results[step_name] = ctx.get("my_data")

        # Run multiple "steps" concurrently
        await asyncio.gather(
            step_worker("step_a"),
            step_worker("step_b"),
            step_worker("step_c"),
        )

        # Each step should have seen its own data
        assert results["step_a"] == "step_a"
        assert results["step_b"] == "step_b"
        assert results["step_c"] == "step_c"

    @pytest.mark.asyncio
    async def test_concurrent_results(self):
        """Test concurrent result additions are safe."""
        ctx = ChainContext(request_id="concurrent_results")

        async def add_results(prefix: str):
            for i in range(50):
                result = StepResult(f"{prefix}_{i}", {}, float(i))
                ctx.add_result(result)
                await asyncio.sleep(0)

        await asyncio.gather(
            add_results("a"),
            add_results("b"),
        )

        # Should have all 100 results
        assert len(ctx.results) == 100
