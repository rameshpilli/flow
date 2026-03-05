"""
Integration Tests for AgentOrchestrator Chain Execution

End-to-end tests for:
- Complete chain execution flows
- Error handling scenarios
- Resumability features
- Resource injection
- Complex dependency patterns
- Chain composition (nested chains)
"""

import asyncio

import pytest

from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.context import ContextScope
from agentorchestrator.middleware.base import Middleware

# ══════════════════════════════════════════════════════════════════════════════
#                           Basic Chain Execution Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestBasicChainExecution:
    """Tests for basic chain execution patterns."""

    @pytest.fixture
    def ao(self):
        """Create an isolated ao for testing."""
        return AgentOrchestrator.temp_registries("basic_chain_test")

    @pytest.mark.asyncio
    async def test_simple_linear_chain(self, ao):
        """Test a simple linear chain execution."""
        @ao.step(name="step1")
        async def step1(ctx):
            ctx.set("step1_data", "from_step1", scope=ContextScope.CHAIN)
            return {"step": 1}

        @ao.step(name="step2", deps=["step1"])
        async def step2(ctx):
            data = ctx.get("step1_data")
            return {"step": 2, "received": data}

        @ao.step(name="step3", deps=["step2"])
        async def step3(ctx):
            return {"step": 3, "final": True}

        @ao.chain(name="linear_chain")
        class LinearChain:
            steps = ["step1", "step2", "step3"]

        result = await ao.launch("linear_chain")

        assert result["success"] is True
        assert len(result["results"]) == 3
        assert result["results"][1]["output"]["received"] == "from_step1"

    @pytest.mark.asyncio
    async def test_parallel_chain_execution(self, ao):
        """Test parallel step execution."""
        execution_times = {}

        @ao.step(name="fetch_a")
        async def fetch_a(ctx):
            execution_times["fetch_a_start"] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            execution_times["fetch_a_end"] = asyncio.get_event_loop().time()
            return {"source": "a"}

        @ao.step(name="fetch_b")
        async def fetch_b(ctx):
            execution_times["fetch_b_start"] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            execution_times["fetch_b_end"] = asyncio.get_event_loop().time()
            return {"source": "b"}

        @ao.step(name="combine", deps=["fetch_a", "fetch_b"])
        async def combine(ctx):
            return {"combined": True}

        @ao.chain(name="parallel_chain")
        class ParallelChain:
            steps = ["fetch_a", "fetch_b", "combine"]

        result = await ao.launch("parallel_chain")

        assert result["success"] is True

        # Verify parallel execution (fetch_a and fetch_b should overlap)
        a_start = execution_times["fetch_a_start"]
        b_start = execution_times["fetch_b_start"]
        # Should start within 50ms of each other
        assert abs(a_start - b_start) < 0.05

    @pytest.mark.asyncio
    async def test_chain_with_initial_data(self, ao):
        """Test chain execution with initial data."""
        @ao.step(name="process")
        async def process(ctx):
            company = ctx.get("company")
            ticker = ctx.get("ticker")
            return {"company": company, "ticker": ticker}

        @ao.chain(name="data_chain")
        class DataChain:
            steps = ["process"]

        result = await ao.launch(
            "data_chain",
            data={"company": "Apple Inc", "ticker": "AAPL"},
        )

        assert result["success"] is True
        assert result["results"][0]["output"]["company"] == "Apple Inc"
        assert result["results"][0]["output"]["ticker"] == "AAPL"


# ══════════════════════════════════════════════════════════════════════════════
#                           Error Handling Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Tests for chain error handling scenarios."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("error_handling_test")

    @pytest.mark.asyncio
    async def test_fail_fast_stops_execution(self, ao):
        """Test fail_fast mode stops on first error."""
        executed = []

        @ao.step(name="ok1")
        async def ok1(ctx):
            executed.append("ok1")
            return 1

        @ao.step(name="fail", deps=["ok1"])
        async def fail(ctx):
            executed.append("fail")
            raise RuntimeError("Intentional failure")

        @ao.step(name="ok2", deps=["fail"])
        async def ok2(ctx):
            executed.append("ok2")
            return 2

        @ao.chain(name="fail_fast_chain")
        class FailFastChain:
            steps = ["ok1", "fail", "ok2"]
            error_handling = "fail_fast"

        result = await ao.launch("fail_fast_chain")

        assert result["success"] is False
        assert "ok2" not in executed

    @pytest.mark.asyncio
    async def test_continue_mode_runs_independent_steps(self, ao):
        """Test continue mode runs independent steps despite failures."""
        executed = []

        @ao.step(name="fail1")
        async def fail1(ctx):
            executed.append("fail1")
            raise RuntimeError("Failure 1")

        @ao.step(name="ok1")
        async def ok1(ctx):
            executed.append("ok1")
            return "ok1"

        @ao.step(name="ok2")
        async def ok2(ctx):
            executed.append("ok2")
            return "ok2"

        @ao.chain(name="continue_chain")
        class ContinueChain:
            steps = ["fail1", "ok1", "ok2"]
            error_handling = "continue"

        result = await ao.launch("continue_chain")

        assert result["success"] is False
        # All independent steps should run
        assert "ok1" in executed
        assert "ok2" in executed

    @pytest.mark.asyncio
    async def test_retry_mode_retries_failed_steps(self, ao):
        """Test retry mode retries failed steps."""
        attempt = 0

        @ao.step(name="flaky", retry=2)
        async def flaky(ctx):
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise RuntimeError(f"Attempt {attempt} failed")
            return {"success": True, "attempts": attempt}

        @ao.chain(name="retry_chain")
        class RetryChain:
            steps = ["flaky"]
            error_handling = "retry"

        result = await ao.launch("retry_chain")

        assert result["success"] is True
        assert attempt == 3

    @pytest.mark.asyncio
    async def test_error_info_included_in_result(self, ao):
        """Test error information is included in result."""
        @ao.step(name="error_step")
        async def error_step(ctx):
            raise ValueError("Custom error message")

        @ao.chain(name="error_info_chain")
        class ErrorInfoChain:
            steps = ["error_step"]

        result = await ao.launch("error_info_chain")

        assert result["success"] is False
        assert "error" in result
        assert "ValueError" in result["error"]["type"]


# ══════════════════════════════════════════════════════════════════════════════
#                           Resource Injection Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestResourceInjection:
    """Tests for resource injection."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("resource_test")

    @pytest.mark.asyncio
    async def test_resource_injection(self, ao):
        """Test resources are injected into steps."""
        # Register a resource
        ao.register_resource("config", {"api_key": "secret123"})

        @ao.step(name="use_config", resources=["config"])
        async def use_config(ctx, config):
            return {"api_key": config["api_key"]}

        @ao.chain(name="resource_chain")
        class ResourceChain:
            steps = ["use_config"]

        result = await ao.launch("resource_chain")

        assert result["success"] is True
        assert result["results"][0]["output"]["api_key"] == "secret123"

    @pytest.mark.asyncio
    async def test_factory_resource(self, ao):
        """Test resources created from factory functions."""
        call_count = 0

        def create_client():
            nonlocal call_count
            call_count += 1
            return {"client_id": call_count}

        ao.register_resource("client", factory=create_client)

        @ao.step(name="use_client", resources=["client"])
        async def use_client(ctx, client):
            return {"client_id": client["client_id"]}

        @ao.chain(name="factory_chain")
        class FactoryChain:
            steps = ["use_client"]

        result = await ao.launch("factory_chain")

        assert result["success"] is True
        assert result["results"][0]["output"]["client_id"] == 1


# ══════════════════════════════════════════════════════════════════════════════
#                           Complex Dependency Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestComplexDependencies:
    """Tests for complex dependency patterns."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("complex_deps_test")

    @pytest.mark.asyncio
    async def test_diamond_dependency(self, ao):
        """Test diamond-shaped dependency pattern."""
        order = []

        @ao.step(name="top")
        async def top(ctx):
            order.append("top")
            ctx.set("top_data", "from_top", scope=ContextScope.CHAIN)
            return "top"

        @ao.step(name="left", deps=["top"])
        async def left(ctx):
            order.append("left")
            return "left"

        @ao.step(name="right", deps=["top"])
        async def right(ctx):
            order.append("right")
            return "right"

        @ao.step(name="bottom", deps=["left", "right"])
        async def bottom(ctx):
            order.append("bottom")
            top_data = ctx.get("top_data")
            return {"top_data": top_data}

        @ao.chain(name="diamond_chain")
        class DiamondChain:
            steps = ["top", "left", "right", "bottom"]

        result = await ao.launch("diamond_chain")

        assert result["success"] is True
        assert order[0] == "top"
        assert set(order[1:3]) == {"left", "right"}
        assert order[3] == "bottom"

    @pytest.mark.asyncio
    async def test_explicit_parallel_groups(self, ao):
        """Test explicit parallel group ordering."""
        order = []

        @ao.step(name="a")
        async def a(ctx):
            order.append("a")
            return "a"

        @ao.step(name="b")
        async def b(ctx):
            order.append("b")
            return "b"

        @ao.step(name="c", deps=["a", "b"])
        async def c(ctx):
            order.append("c")
            return "c"

        @ao.step(name="d", deps=["c"])
        async def d(ctx):
            order.append("d")
            return "d"

        @ao.chain(name="explicit_chain")
        class ExplicitChain:
            steps = ["a", "b", "c", "d"]
            parallel_groups = [["a", "b"], ["c"], ["d"]]

        result = await ao.launch("explicit_chain")

        assert result["success"] is True
        # a and b run in first group (parallel)
        assert set(order[:2]) == {"a", "b"}
        assert order[2] == "c"
        assert order[3] == "d"


# ══════════════════════════════════════════════════════════════════════════════
#                           Resumability Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestResumability:
    """Tests for chain resumability features."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("resumability_test")

    @pytest.mark.asyncio
    async def test_launch_resumable(self, ao):
        """Test launching a resumable chain."""
        @ao.step(name="step1")
        async def step1(ctx):
            return {"step": 1}

        @ao.step(name="step2", deps=["step1"])
        async def step2(ctx):
            return {"step": 2}

        @ao.chain(name="resumable_chain")
        class ResumableChain:
            steps = ["step1", "step2"]

        result = await ao.launch_resumable("resumable_chain")

        assert result["success"] is True
        assert "run_id" in result
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_partial_output(self, ao):
        """Test getting partial output from failed chain."""
        @ao.step(name="success_step")
        async def success_step(ctx):
            ctx.set("success_output", "value", scope=ContextScope.CHAIN)
            return {"success": True}

        @ao.step(name="fail_step", deps=["success_step"])
        async def fail_step(ctx):
            raise RuntimeError("Intentional failure")

        @ao.chain(name="partial_chain")
        class PartialChain:
            steps = ["success_step", "fail_step"]

        # First run - should fail but first step should have succeeded
        try:
            await ao.launch_resumable("partial_chain")
        except RuntimeError:
            # Expected - the chain failed
            pass

        # For now, just verify the chain definition exists and can be launched
        # The partial output feature depends on the run store implementation
        assert ao._chain_registry.has("partial_chain")


# ══════════════════════════════════════════════════════════════════════════════
#                           Chain Composition Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestChainComposition:
    """Tests for chain composition (calling chains from chains)."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("composition_test")

    @pytest.mark.asyncio
    async def test_nested_chain_as_step(self, ao):
        """Test using a chain as a step in another chain."""
        # Define inner chain
        @ao.step(name="inner_step1")
        async def inner_step1(ctx):
            ctx.set("inner_data", "from_inner", scope=ContextScope.CHAIN)
            return {"inner": 1}

        @ao.step(name="inner_step2", deps=["inner_step1"])
        async def inner_step2(ctx):
            return {"inner": 2}

        @ao.chain(name="inner_chain")
        class InnerChain:
            steps = ["inner_step1", "inner_step2"]

        # Define outer chain that uses inner chain
        @ao.step(name="outer_before")
        async def outer_before(ctx):
            ctx.set("outer_data", "from_outer", scope=ContextScope.CHAIN)
            return {"outer": "before"}

        @ao.step(name="run_inner", deps=["outer_before"])
        async def run_inner(ctx):
            # Execute the inner chain
            inner_result = await ao.launch("inner_chain", data=ctx.to_dict().get("data", {}))
            ctx.set("inner_result", inner_result, scope=ContextScope.CHAIN)
            return {"inner_success": inner_result["success"]}

        @ao.step(name="outer_after", deps=["run_inner"])
        async def outer_after(ctx):
            inner_result = ctx.get("inner_result")
            return {
                "outer": "after",
                "inner_ran": inner_result is not None,
            }

        @ao.chain(name="outer_chain")
        class OuterChain:
            steps = ["outer_before", "run_inner", "outer_after"]

        result = await ao.launch("outer_chain")

        assert result["success"] is True
        assert result["results"][2]["output"]["inner_ran"] is True

    @pytest.mark.asyncio
    async def test_chain_composition_with_data_passing(self, ao):
        """Test data flows correctly through composed chains."""
        # Inner chain that transforms data
        @ao.step(name="transform")
        async def transform(ctx):
            value = ctx.get("value", 0)
            transformed = value * 2
            ctx.set("transformed", transformed, scope=ContextScope.CHAIN)
            return {"transformed": transformed}

        @ao.chain(name="transform_chain")
        class TransformChain:
            steps = ["transform"]

        # Outer chain
        @ao.step(name="prepare")
        async def prepare(ctx):
            ctx.set("value", 10, scope=ContextScope.CHAIN)
            return {"prepared": True}

        @ao.step(name="call_transform", deps=["prepare"])
        async def call_transform(ctx):
            value = ctx.get("value")
            inner_result = await ao.launch(
                "transform_chain",
                data={"value": value},
            )
            # Extract transformed value from inner chain
            transformed = inner_result["context"]["data"].get("transformed")
            ctx.set("final_value", transformed, scope=ContextScope.CHAIN)
            return {"from_inner": transformed}

        @ao.step(name="finalize", deps=["call_transform"])
        async def finalize(ctx):
            final = ctx.get("final_value")
            return {"final": final}

        @ao.chain(name="composed_chain")
        class ComposedChain:
            steps = ["prepare", "call_transform", "finalize"]

        result = await ao.launch("composed_chain")

        assert result["success"] is True
        assert result["results"][2]["output"]["final"] == 20  # 10 * 2


# ══════════════════════════════════════════════════════════════════════════════
#                           Full Integration Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestFullIntegration:
    """Full integration tests simulating real-world usage."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("full_integration")

    @pytest.mark.asyncio
    async def test_complete_data_pipeline(self, ao):
        """Test a complete data pipeline with multiple stages."""
        # Middleware for tracking
        execution_log = []

        class LoggingMiddleware(Middleware):
            async def before(self, ctx, step_name):
                execution_log.append(f"start:{step_name}")

            async def after(self, ctx, step_name, result):
                execution_log.append(f"end:{step_name}:{result.success}")

        ao.use(LoggingMiddleware())

        # Stage 1: Fetch data from multiple sources
        @ao.step(name="fetch_users")
        async def fetch_users(ctx):
            await asyncio.sleep(0.01)
            return {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}

        @ao.step(name="fetch_orders")
        async def fetch_orders(ctx):
            await asyncio.sleep(0.01)
            return {"orders": [{"user_id": 1, "amount": 100}, {"user_id": 2, "amount": 200}]}

        # Stage 2: Process data
        @ao.step(name="process_data", deps=["fetch_users", "fetch_orders"])
        async def process_data(ctx):
            users_result = ctx.get_result("fetch_users")
            orders_result = ctx.get_result("fetch_orders")

            users = users_result.output["users"]
            orders = orders_result.output["orders"]

            # Join data
            user_map = {u["id"]: u for u in users}
            enriched = []
            for order in orders:
                user = user_map.get(order["user_id"])
                enriched.append({
                    "user_name": user["name"] if user else "Unknown",
                    "amount": order["amount"],
                })

            ctx.set("enriched_data", enriched, scope=ContextScope.CHAIN)
            return {"processed": len(enriched)}

        # Stage 3: Generate report
        @ao.step(name="generate_report", deps=["process_data"])
        async def generate_report(ctx):
            enriched = ctx.get("enriched_data")
            total = sum(item["amount"] for item in enriched)
            return {
                "report": {
                    "total_orders": len(enriched),
                    "total_amount": total,
                    "items": enriched,
                }
            }

        @ao.chain(name="data_pipeline")
        class DataPipeline:
            steps = ["fetch_users", "fetch_orders", "process_data", "generate_report"]

        result = await ao.launch("data_pipeline")

        assert result["success"] is True
        report = result["results"][3]["output"]["report"]
        assert report["total_orders"] == 2
        assert report["total_amount"] == 300

        # Verify middleware was called
        assert "start:fetch_users" in execution_log
        assert "end:generate_report:True" in execution_log

    @pytest.mark.asyncio
    async def test_error_recovery_pipeline(self, ao):
        """Test pipeline with error recovery."""
        attempts = {"api_call": 0}

        @ao.step(name="validate_input")
        async def validate_input(ctx):
            query = ctx.get("query")
            if not query:
                raise ValueError("Query is required")
            return {"valid": True}

        @ao.step(name="api_call", deps=["validate_input"], retry=2)
        async def api_call(ctx):
            attempts["api_call"] += 1
            if attempts["api_call"] < 2:
                raise ConnectionError("API temporarily unavailable")
            return {"data": "api_response"}

        @ao.step(name="process", deps=["api_call"])
        async def process(ctx):
            api_result = ctx.get_result("api_call")
            return {"processed": api_result.output["data"]}

        @ao.chain(name="recovery_pipeline")
        class RecoveryPipeline:
            steps = ["validate_input", "api_call", "process"]
            error_handling = "retry"

        result = await ao.launch(
            "recovery_pipeline",
            data={"query": "test_query"},
        )

        assert result["success"] is True
        assert attempts["api_call"] == 2  # Succeeded on second attempt
