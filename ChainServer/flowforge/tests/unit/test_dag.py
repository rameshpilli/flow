"""
Unit Tests for FlowForge DAG Module

Tests for:
- DAGBuilder: Building execution plans from chain definitions
- DAGExecutor: Executing steps with concurrency control
- DAGNode: Step state management
- ExecutionPlan: Compiled execution strategies
"""

import asyncio

import pytest

from flowforge import FlowForge
from flowforge.core.context import ContextScope, StepResult
from flowforge.core.dag import (
    DAGNode,
    ExecutionPlan,
    StepState,
)
from flowforge.core.registry import ComponentMetadata, StepSpec

# ══════════════════════════════════════════════════════════════════════════════
#                           DAGNode Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDAGNode:
    """Tests for DAGNode class."""

    def _create_spec(self, name: str = "test_step") -> StepSpec:
        """Helper to create a StepSpec."""
        async def handler(ctx):
            return {"result": "ok"}

        return StepSpec(
            metadata=ComponentMetadata(name=name),
            handler=handler,
            dependencies=[],
            produces=[],
        )

    def test_node_creation(self):
        """Test basic node creation."""
        spec = self._create_spec("my_step")
        node = DAGNode(name="my_step", spec=spec)

        assert node.name == "my_step"
        assert node.state == StepState.PENDING
        assert node.result is None
        assert node.started_at is None
        assert node.completed_at is None

    def test_node_is_ready_no_deps(self):
        """Test is_ready when no dependencies."""
        spec = self._create_spec()
        node = DAGNode(name="test", spec=spec)

        assert node.is_ready is True

    def test_node_is_ready_with_deps(self):
        """Test is_ready when dependencies exist."""
        spec = self._create_spec()
        node = DAGNode(name="test", spec=spec, dependencies={"dep1", "dep2"})

        assert node.is_ready is False

    def test_node_is_ready_after_state_change(self):
        """Test is_ready returns False when not PENDING."""
        spec = self._create_spec()
        node = DAGNode(name="test", spec=spec)
        node.state = StepState.RUNNING

        assert node.is_ready is False

    @pytest.mark.asyncio
    async def test_set_running(self):
        """Test thread-safe transition to RUNNING state."""
        spec = self._create_spec()
        node = DAGNode(name="test", spec=spec)

        await node.set_running()

        assert node.state == StepState.RUNNING
        assert node.started_at is not None

    @pytest.mark.asyncio
    async def test_set_completed(self):
        """Test thread-safe transition to COMPLETED state."""
        spec = self._create_spec()
        node = DAGNode(name="test", spec=spec)

        result = StepResult(step_name="test", output={"data": 1}, duration_ms=100)
        await node.set_completed(result)

        assert node.state == StepState.COMPLETED
        assert node.result == result
        assert node.completed_at is not None

    @pytest.mark.asyncio
    async def test_set_failed(self):
        """Test thread-safe transition to FAILED state."""
        spec = self._create_spec()
        node = DAGNode(name="test", spec=spec)

        error = RuntimeError("Test error")
        result = StepResult(
            step_name="test",
            output=None,
            duration_ms=50,
            error=error,
            error_type="RuntimeError",
        )
        await node.set_failed(result)

        assert node.state == StepState.FAILED
        assert node.result.error == error
        assert node.completed_at is not None

    @pytest.mark.asyncio
    async def test_set_skipped(self):
        """Test thread-safe transition to SKIPPED state."""
        spec = self._create_spec()
        node = DAGNode(name="test", spec=spec)

        await node.set_skipped("dependency failed: dep1")

        assert node.state == StepState.SKIPPED
        assert node.result.skipped_reason == "dependency failed: dep1"
        assert node.result.success is False
        assert node.completed_at is not None


# ══════════════════════════════════════════════════════════════════════════════
#                           DAGBuilder Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDAGBuilder:
    """Tests for DAGBuilder class."""

    @pytest.fixture
    def forge(self):
        """Create an isolated forge for testing."""
        return FlowForge.temp_registries("dag_builder_test")

    def test_build_simple_chain(self, forge):
        """Test building a simple linear chain."""
        @forge.step(name="step1")
        async def step1(ctx):
            return {"step": 1}

        @forge.step(name="step2", deps=["step1"])
        async def step2(ctx):
            return {"step": 2}

        @forge.step(name="step3", deps=["step2"])
        async def step3(ctx):
            return {"step": 3}

        @forge.chain(name="linear_chain")
        class LinearChain:
            steps = ["step1", "step2", "step3"]

        # Build execution plan
        builder = forge._executor.builder
        plan = builder.build("linear_chain")

        assert plan.chain_name == "linear_chain"
        assert plan.total_steps == 3
        assert len(plan.execution_order) == 3  # Each step in its own group (linear)
        assert plan.execution_order[0] == ["step1"]
        assert plan.execution_order[1] == ["step2"]
        assert plan.execution_order[2] == ["step3"]

    def test_build_parallel_chain(self, forge):
        """Test building a chain with parallel steps."""
        @forge.step(name="fetch_a")
        async def fetch_a(ctx):
            return {"source": "a"}

        @forge.step(name="fetch_b")
        async def fetch_b(ctx):
            return {"source": "b"}

        @forge.step(name="fetch_c")
        async def fetch_c(ctx):
            return {"source": "c"}

        @forge.step(name="combine", deps=["fetch_a", "fetch_b", "fetch_c"])
        async def combine(ctx):
            return {"combined": True}

        @forge.chain(name="parallel_chain")
        class ParallelChain:
            steps = ["fetch_a", "fetch_b", "fetch_c", "combine"]

        builder = forge._executor.builder
        plan = builder.build("parallel_chain")

        assert plan.total_steps == 4
        # First group should have all 3 parallel fetchers
        assert set(plan.execution_order[0]) == {"fetch_a", "fetch_b", "fetch_c"}
        # Second group should have combine
        assert plan.execution_order[1] == ["combine"]

    def test_build_with_explicit_parallel_groups(self, forge):
        """Test building with explicit parallel_groups."""
        @forge.step(name="s1")
        async def s1(ctx):
            return 1

        @forge.step(name="s2")
        async def s2(ctx):
            return 2

        @forge.step(name="s3", deps=["s1", "s2"])
        async def s3(ctx):
            return 3

        @forge.chain(name="explicit_groups")
        class ExplicitGroups:
            steps = ["s1", "s2", "s3"]
            parallel_groups = [["s1", "s2"], ["s3"]]

        builder = forge._executor.builder
        plan = builder.build("explicit_groups")

        assert plan.uses_explicit_groups is True
        assert plan.execution_order[0] == ["s1", "s2"]
        assert plan.execution_order[1] == ["s3"]

    def test_build_chain_not_found(self, forge):
        """Test error when chain doesn't exist."""
        builder = forge._executor.builder

        with pytest.raises(ValueError, match="Chain not found"):
            builder.build("nonexistent_chain")

    def test_build_step_not_found(self, forge):
        """Test error when step doesn't exist."""
        forge._chain_registry.register_chain(
            name="broken_chain",
            steps=["nonexistent_step"],
        )

        builder = forge._executor.builder

        with pytest.raises(ValueError, match="Step not found"):
            builder.build("broken_chain")

    def test_build_circular_dependency(self, forge):
        """Test detection of circular dependencies."""
        @forge.step(name="a", deps=["c"])
        async def a(ctx):
            return "a"

        @forge.step(name="b", deps=["a"])
        async def b(ctx):
            return "b"

        @forge.step(name="c", deps=["b"])
        async def c(ctx):
            return "c"

        @forge.chain(name="circular_chain")
        class CircularChain:
            steps = ["a", "b", "c"]

        builder = forge._executor.builder

        with pytest.raises(ValueError, match="Circular dependency"):
            builder.build("circular_chain")


# ══════════════════════════════════════════════════════════════════════════════
#                           DAGExecutor Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDAGExecutor:
    """Tests for DAGExecutor class."""

    @pytest.fixture
    def forge(self):
        """Create an isolated forge for testing."""
        return FlowForge.temp_registries("dag_executor_test")

    @pytest.mark.asyncio
    async def test_execute_simple_chain(self, forge):
        """Test executing a simple chain."""
        execution_order = []

        @forge.step(name="step1")
        async def step1(ctx):
            execution_order.append("step1")
            ctx.set("step1_data", "value1", scope=ContextScope.CHAIN)
            return {"step": 1}

        @forge.step(name="step2", deps=["step1"])
        async def step2(ctx):
            execution_order.append("step2")
            data = ctx.get("step1_data")
            return {"step": 2, "from_step1": data}

        @forge.chain(name="test_chain")
        class TestChain:
            steps = ["step1", "step2"]

        result = await forge.launch("test_chain")

        assert result["success"] is True
        assert execution_order == ["step1", "step2"]
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_execute_parallel_steps(self, forge):
        """Test that independent steps run in parallel."""
        start_times = {}
        end_times = {}

        @forge.step(name="slow1")
        async def slow1(ctx):
            start_times["slow1"] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            end_times["slow1"] = asyncio.get_event_loop().time()
            return 1

        @forge.step(name="slow2")
        async def slow2(ctx):
            start_times["slow2"] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            end_times["slow2"] = asyncio.get_event_loop().time()
            return 2

        @forge.step(name="slow3")
        async def slow3(ctx):
            start_times["slow3"] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            end_times["slow3"] = asyncio.get_event_loop().time()
            return 3

        @forge.chain(name="parallel_test")
        class ParallelTest:
            steps = ["slow1", "slow2", "slow3"]

        result = await forge.launch("parallel_test")

        assert result["success"] is True

        # All steps should start at roughly the same time (parallel)
        starts = list(start_times.values())
        max_start_diff = max(starts) - min(starts)
        assert max_start_diff < 0.05  # Should start within 50ms of each other

    @pytest.mark.asyncio
    async def test_execute_with_fail_fast(self, forge):
        """Test fail_fast error handling stops on first error."""
        executed = []

        @forge.step(name="ok1")
        async def ok1(ctx):
            executed.append("ok1")
            return 1

        @forge.step(name="fail", deps=["ok1"])
        async def fail(ctx):
            executed.append("fail")
            raise RuntimeError("Intentional failure")

        @forge.step(name="ok2", deps=["fail"])
        async def ok2(ctx):
            executed.append("ok2")
            return 2

        @forge.chain(name="fail_fast_chain")
        class FailFastChain:
            steps = ["ok1", "fail", "ok2"]
            error_handling = "fail_fast"

        result = await forge.launch("fail_fast_chain")

        assert result["success"] is False
        assert "ok1" in executed
        assert "fail" in executed
        assert "ok2" not in executed  # Should not execute after failure

    @pytest.mark.asyncio
    async def test_execute_with_continue(self, forge):
        """Test continue error handling executes all possible steps."""
        executed = []

        @forge.step(name="ok1")
        async def ok1(ctx):
            executed.append("ok1")
            return 1

        @forge.step(name="fail", deps=["ok1"])
        async def fail(ctx):
            executed.append("fail")
            raise RuntimeError("Intentional failure")

        @forge.step(name="independent")
        async def independent(ctx):
            executed.append("independent")
            return "independent result"

        @forge.chain(name="continue_chain")
        class ContinueChain:
            steps = ["ok1", "fail", "independent"]
            error_handling = "continue"

        result = await forge.launch("continue_chain")

        assert result["success"] is False
        assert "ok1" in executed
        assert "fail" in executed
        assert "independent" in executed  # Should still execute

    @pytest.mark.asyncio
    async def test_execute_with_retry(self, forge):
        """Test retry error handling retries failed steps."""
        attempt_count = 0

        @forge.step(name="flaky", retry=2)
        async def flaky(ctx):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise RuntimeError(f"Attempt {attempt_count} failed")
            return {"attempts": attempt_count}

        @forge.chain(name="retry_chain")
        class RetryChain:
            steps = ["flaky"]
            error_handling = "retry"

        result = await forge.launch("retry_chain")

        assert result["success"] is True
        assert attempt_count == 3  # Original + 2 retries

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, forge):
        """Test step timeout handling."""
        @forge.step(name="slow_step", timeout_ms=100)
        async def slow_step(ctx):
            await asyncio.sleep(1.0)  # Will timeout
            return "should not reach"

        @forge.chain(name="timeout_chain")
        class TimeoutChain:
            steps = ["slow_step"]

        result = await forge.launch("timeout_chain")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_with_initial_data(self, forge):
        """Test passing initial data to chain."""
        @forge.step(name="read_data")
        async def read_data(ctx):
            company = ctx.get("company")
            return {"company": company}

        @forge.chain(name="data_chain")
        class DataChain:
            steps = ["read_data"]

        result = await forge.launch("data_chain", data={"company": "Apple Inc"})

        assert result["success"] is True
        assert result["results"][0]["output"]["company"] == "Apple Inc"

    @pytest.mark.asyncio
    async def test_execute_with_max_concurrency(self, forge):
        """Test per-step concurrency limits."""
        concurrent_count = 0
        max_concurrent = 0

        @forge.step(name="limited", max_concurrency=2)
        async def limited(ctx):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return True

        @forge.chain(name="concurrency_chain")
        class ConcurrencyChain:
            steps = ["limited"]

        result = await forge.launch("concurrency_chain")

        assert result["success"] is True
        # With single step, max concurrent should be 1
        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_execute_with_debug_callback(self, forge):
        """Test debug callback is invoked after each step."""
        callbacks = []

        def debug_callback(ctx, step_name, result):
            callbacks.append({
                "step": step_name,
                "success": result["success"],
            })

        @forge.step(name="s1")
        async def s1(ctx):
            return 1

        @forge.step(name="s2", deps=["s1"])
        async def s2(ctx):
            return 2

        @forge.chain(name="debug_chain")
        class DebugChain:
            steps = ["s1", "s2"]

        result = await forge.launch("debug_chain", debug_callback=debug_callback)

        assert result["success"] is True
        assert len(callbacks) == 2
        assert callbacks[0]["step"] == "s1"
        assert callbacks[1]["step"] == "s2"


# ══════════════════════════════════════════════════════════════════════════════
#                           ExecutionPlan Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestExecutionPlan:
    """Tests for ExecutionPlan class."""

    def _create_node(self, name: str, state: StepState = StepState.PENDING) -> DAGNode:
        """Helper to create a DAGNode."""
        async def handler(ctx):
            return {}

        spec = StepSpec(
            metadata=ComponentMetadata(name=name),
            handler=handler,
        )
        node = DAGNode(name=name, spec=spec)
        node.state = state
        return node

    def test_get_ready_steps_all_pending(self):
        """Test getting ready steps when all are pending with no deps."""
        nodes = {
            "a": self._create_node("a"),
            "b": self._create_node("b"),
            "c": self._create_node("c"),
        }

        plan = ExecutionPlan(
            chain_name="test",
            nodes=nodes,
            execution_order=[["a", "b", "c"]],
            total_steps=3,
        )

        ready = plan.get_ready_steps()
        assert set(ready) == {"a", "b", "c"}

    def test_get_ready_steps_with_deps(self):
        """Test getting ready steps respects dependencies."""
        node_a = self._create_node("a")
        node_b = self._create_node("b")
        node_b.dependencies = {"a"}

        nodes = {"a": node_a, "b": node_b}

        plan = ExecutionPlan(
            chain_name="test",
            nodes=nodes,
            execution_order=[["a"], ["b"]],
            total_steps=2,
        )

        ready = plan.get_ready_steps()
        assert ready == ["a"]  # Only a is ready

    def test_get_ready_steps_none_ready(self):
        """Test when no steps are ready."""
        node_a = self._create_node("a", StepState.RUNNING)
        node_b = self._create_node("b")
        node_b.dependencies = {"a"}

        nodes = {"a": node_a, "b": node_b}

        plan = ExecutionPlan(
            chain_name="test",
            nodes=nodes,
            execution_order=[["a"], ["b"]],
            total_steps=2,
        )

        ready = plan.get_ready_steps()
        assert ready == []


# ══════════════════════════════════════════════════════════════════════════════
#                           Edge Cases & Error Handling
# ══════════════════════════════════════════════════════════════════════════════


class TestDAGEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def forge(self):
        return FlowForge.temp_registries("dag_edge_cases")

    @pytest.mark.asyncio
    async def test_empty_chain(self, forge):
        """Test executing a chain with no steps."""
        @forge.chain(name="empty_chain")
        class EmptyChain:
            steps = []

        result = await forge.launch("empty_chain")

        assert result["success"] is True
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_single_step_chain(self, forge):
        """Test executing a chain with single step."""
        @forge.step(name="only_step")
        async def only_step(ctx):
            return "only result"

        @forge.chain(name="single_chain")
        class SingleChain:
            steps = ["only_step"]

        result = await forge.launch("single_chain")

        assert result["success"] is True
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_diamond_dependency(self, forge):
        """Test diamond-shaped dependency graph (A -> B,C -> D)."""
        order = []

        @forge.step(name="top")
        async def top(ctx):
            order.append("top")
            return "top"

        @forge.step(name="left", deps=["top"])
        async def left(ctx):
            order.append("left")
            return "left"

        @forge.step(name="right", deps=["top"])
        async def right(ctx):
            order.append("right")
            return "right"

        @forge.step(name="bottom", deps=["left", "right"])
        async def bottom(ctx):
            order.append("bottom")
            return "bottom"

        @forge.chain(name="diamond_chain")
        class DiamondChain:
            steps = ["top", "left", "right", "bottom"]

        result = await forge.launch("diamond_chain")

        assert result["success"] is True
        assert order[0] == "top"
        assert set(order[1:3]) == {"left", "right"}
        assert order[3] == "bottom"

    @pytest.mark.asyncio
    async def test_step_output_preserved_on_error(self, forge):
        """Test that step outputs are preserved even when chain fails."""
        @forge.step(name="success_step")
        async def success_step(ctx):
            ctx.set("preserved", "data", scope=ContextScope.CHAIN)
            return {"status": "ok"}

        @forge.step(name="fail_step", deps=["success_step"])
        async def fail_step(ctx):
            raise RuntimeError("Intentional failure")

        @forge.chain(name="partial_chain")
        class PartialChain:
            steps = ["success_step", "fail_step"]

        result = await forge.launch("partial_chain")

        assert result["success"] is False
        # First step should have succeeded
        assert result["results"][0]["success"] is True
        assert result["results"][0]["output"] == {"status": "ok"}
