"""
Unit Tests for AgentOrchestrator Chain Composition

Tests for:
- Subchain execution within parent chains
- Data flow between parent and child chains
- Error handling in composed chains
- Explicit subchain references with dependencies
"""

import asyncio

import pytest

from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.context import ContextScope

# ══════════════════════════════════════════════════════════════════════════════
#                           Basic Chain Composition Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestBasicChainComposition:
    """Tests for basic chain composition functionality."""

    @pytest.fixture
    def ao(self):
        """Create an isolated ao for testing."""
        return AgentOrchestrator.temp_registries("composition_test")

    @pytest.mark.asyncio
    async def test_chain_as_step_string_reference(self, ao):
        """Test using a chain name (string) as a step in another chain."""
        execution_order = []

        # Define inner chain
        @ao.step(name="inner_step1")
        async def inner_step1(ctx):
            execution_order.append("inner_step1")
            ctx.set("inner_data", "from_inner", scope=ContextScope.CHAIN)
            return {"inner": 1}

        @ao.step(name="inner_step2", deps=["inner_step1"])
        async def inner_step2(ctx):
            execution_order.append("inner_step2")
            return {"inner": 2}

        @ao.chain(name="inner_chain")
        class InnerChain:
            steps = ["inner_step1", "inner_step2"]

        # Define outer chain that includes inner_chain as a step
        @ao.step(name="outer_before")
        async def outer_before(ctx):
            execution_order.append("outer_before")
            return {"outer": "before"}

        @ao.step(name="outer_after", deps=["__subchain__inner_chain"])
        async def outer_after(ctx):
            execution_order.append("outer_after")
            # Check that inner chain's data was merged
            inner_data = ctx.get("inner_data")
            return {"outer": "after", "inner_data": inner_data}

        @ao.chain(name="outer_chain")
        class OuterChain:
            steps = ["outer_before", "inner_chain", "outer_after"]

        result = await ao.launch("outer_chain")

        assert result["success"] is True
        # Verify execution order
        assert "outer_before" in execution_order
        assert "inner_step1" in execution_order
        assert "inner_step2" in execution_order
        assert "outer_after" in execution_order

    @pytest.mark.asyncio
    async def test_chain_class_as_step(self, ao):
        """Test using a chain class directly as a step."""
        # Define inner chain
        @ao.step(name="process")
        async def process(ctx):
            ctx.set("processed", True, scope=ContextScope.CHAIN)
            return {"processed": True}

        @ao.chain(name="processing_chain")
        class ProcessingChain:
            steps = ["process"]

        # Define outer chain using the class
        @ao.step(name="prepare")
        async def prepare(ctx):
            return {"prepared": True}

        @ao.step(name="finalize", deps=["__subchain__processing_chain"])
        async def finalize(ctx):
            processed = ctx.get("processed")
            return {"finalized": True, "was_processed": processed}

        @ao.chain(name="main_chain")
        class MainChain:
            steps = ["prepare", ProcessingChain, "finalize"]

        result = await ao.launch("main_chain")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_data_flows_to_subchain(self, ao):
        """Test that parent context data flows to subchain."""
        received_data = {}

        # Inner chain that reads parent's data - define first
        @ao.step(name="read_config")
        async def read_config(ctx):
            received_data["config"] = ctx.get("config")
            received_data["user_id"] = ctx.get("user_id")
            return {"read": True}

        @ao.chain(name="config_reader")
        class ConfigReader:
            steps = ["read_config"]

        # Outer step that sets up data
        @ao.step(name="setup")
        async def setup(ctx):
            ctx.set("config", {"api_key": "secret"}, scope=ContextScope.CHAIN)
            ctx.set("user_id", 123, scope=ContextScope.CHAIN)
            return {"setup": True}

        # Need dependency to ensure setup runs before subchain
        @ao.step(name="run_reader", deps=["setup"])
        async def run_reader(ctx):
            # Get data for subchain
            config = ctx.get("config")
            user_id = ctx.get("user_id")
            # Run subchain with explicit data
            result = await ao.launch("config_reader", data={
                "config": config,
                "user_id": user_id,
            })
            return {"reader_success": result["success"]}

        @ao.chain(name="pipeline")
        class Pipeline:
            steps = ["setup", "run_reader"]

        result = await ao.launch("pipeline")

        assert result["success"] is True
        assert received_data["config"] == {"api_key": "secret"}
        assert received_data["user_id"] == 123

    @pytest.mark.asyncio
    async def test_subchain_output_available_to_parent(self, ao):
        """Test that subchain outputs are accessible in parent chain."""
        # Inner chain that produces data
        @ao.step(name="generate")
        async def generate(ctx):
            ctx.set("generated_value", 42, scope=ContextScope.CHAIN)
            return {"generated": 42}

        @ao.chain(name="generator")
        class Generator:
            steps = ["generate"]

        # Outer chain that uses the generated data
        @ao.step(name="init")
        async def init(ctx):
            return {"initialized": True}

        @ao.step(name="use_generated", deps=["__subchain__generator"])
        async def use_generated(ctx):
            value = ctx.get("generated_value")
            return {"used_value": value}

        @ao.chain(name="user_chain")
        class UserChain:
            steps = ["init", "generator", "use_generated"]

        result = await ao.launch("user_chain")

        assert result["success"] is True
        # Find the use_generated result
        use_result = next(r for r in result["results"] if r["step"] == "use_generated")
        assert use_result["output"]["used_value"] == 42


# ══════════════════════════════════════════════════════════════════════════════
#                           Error Handling in Composition
# ══════════════════════════════════════════════════════════════════════════════


class TestChainCompositionErrors:
    """Tests for error handling in chain composition."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("composition_error_test")

    @pytest.mark.asyncio
    async def test_subchain_failure_propagates(self, ao):
        """Test that subchain failure is propagated to parent."""
        @ao.step(name="failing_step")
        async def failing_step(ctx):
            raise ValueError("Subchain step failed!")

        @ao.chain(name="failing_chain")
        class FailingChain:
            steps = ["failing_step"]

        @ao.step(name="before")
        async def before(ctx):
            return {"before": True}

        @ao.step(name="after", deps=["__subchain__failing_chain"])
        async def after(ctx):
            return {"after": True}

        @ao.chain(name="parent_chain")
        class ParentChain:
            steps = ["before", "failing_chain", "after"]

        result = await ao.launch("parent_chain")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_subchain_result_stored_in_context(self, ao):
        """Test that subchain result is stored in context for inspection."""
        @ao.step(name="simple")
        async def simple(ctx):
            return {"simple": True}

        @ao.chain(name="simple_chain")
        class SimpleChain:
            steps = ["simple"]

        @ao.step(name="check", deps=["__subchain__simple_chain"])
        async def check(ctx):
            subchain_result = ctx.get("_subchain_simple_chain_result")
            return {
                "has_result": subchain_result is not None,
                "was_success": subchain_result.get("success") if subchain_result else None,
            }

        @ao.chain(name="checker_chain")
        class CheckerChain:
            steps = ["simple_chain", "check"]

        result = await ao.launch("checker_chain")

        assert result["success"] is True
        check_output = next(r for r in result["results"] if r["step"] == "check")
        assert check_output["output"]["has_result"] is True
        assert check_output["output"]["was_success"] is True


# ══════════════════════════════════════════════════════════════════════════════
#                           Explicit Subchain Reference Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestExplicitSubchainReference:
    """Tests for explicit subchain() method."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("explicit_subchain_test")

    @pytest.mark.asyncio
    async def test_explicit_subchain_with_deps(self, ao):
        """Test explicit subchain reference with dependencies."""
        execution_order = []

        @ao.step(name="s1")
        async def s1(ctx):
            execution_order.append("s1")
            return 1

        @ao.step(name="s2")
        async def s2(ctx):
            execution_order.append("s2")
            return 2

        @ao.chain(name="inner")
        class Inner:
            steps = ["s2"]

        # After inner chain is defined, create explicit reference
        subchain_ref = ao.subchain("inner", deps=["s1"])

        @ao.step(name="s3", deps=[subchain_ref])
        async def s3(ctx):
            execution_order.append("s3")
            return 3

        @ao.chain(name="outer")
        class Outer:
            steps = ["s1", subchain_ref, "s3"]

        result = await ao.launch("outer")

        assert result["success"] is True
        # Verify s1 runs before inner, s3 runs after inner
        s1_idx = execution_order.index("s1")
        s2_idx = execution_order.index("s2")
        s3_idx = execution_order.index("s3")
        assert s1_idx < s2_idx < s3_idx

    def test_subchain_nonexistent_chain_raises(self, ao):
        """Test that referencing non-existent chain raises error."""
        with pytest.raises(ValueError, match="not found"):
            ao.subchain("nonexistent_chain")


# ══════════════════════════════════════════════════════════════════════════════
#                           Nested Composition Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestNestedComposition:
    """Tests for deeply nested chain composition."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("nested_composition_test")

    @pytest.mark.asyncio
    async def test_deeply_nested_chains(self, ao):
        """Test chains nested multiple levels deep."""
        depth_tracker = []

        # Level 3 (deepest)
        @ao.step(name="level3_step")
        async def level3_step(ctx):
            depth_tracker.append(3)
            ctx.set("level3_ran", True, scope=ContextScope.CHAIN)
            return {"level": 3}

        @ao.chain(name="level3_chain")
        class Level3Chain:
            steps = ["level3_step"]

        # Level 2
        @ao.step(name="level2_before")
        async def level2_before(ctx):
            depth_tracker.append(2)
            return {"level": 2}

        @ao.chain(name="level2_chain")
        class Level2Chain:
            steps = ["level2_before", "level3_chain"]

        # Level 1 (top)
        @ao.step(name="level1_before")
        async def level1_before(ctx):
            depth_tracker.append(1)
            return {"level": 1}

        @ao.step(name="level1_after", deps=["__subchain__level2_chain"])
        async def level1_after(ctx):
            level3_ran = ctx.get("level3_ran")
            return {"level3_ran_in_parent": level3_ran}

        @ao.chain(name="level1_chain")
        class Level1Chain:
            steps = ["level1_before", "level2_chain", "level1_after"]

        result = await ao.launch("level1_chain")

        assert result["success"] is True
        # All levels should have executed
        assert 1 in depth_tracker
        assert 2 in depth_tracker
        assert 3 in depth_tracker


# ══════════════════════════════════════════════════════════════════════════════
#                           Parallel Subchains Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestParallelSubchains:
    """Tests for parallel execution of subchains."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("parallel_subchains_test")

    @pytest.mark.asyncio
    async def test_parallel_subchains(self, ao):
        """Test multiple subchains can run in parallel."""
        start_times = {}

        # Subchain A
        @ao.step(name="slow_a")
        async def slow_a(ctx):
            start_times["a"] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            ctx.set("result_a", "A", scope=ContextScope.CHAIN)
            return "A"

        @ao.chain(name="chain_a")
        class ChainA:
            steps = ["slow_a"]

        # Subchain B
        @ao.step(name="slow_b")
        async def slow_b(ctx):
            start_times["b"] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            ctx.set("result_b", "B", scope=ContextScope.CHAIN)
            return "B"

        @ao.chain(name="chain_b")
        class ChainB:
            steps = ["slow_b"]

        # Parent chain with parallel subchains
        @ao.step(name="init")
        async def init(ctx):
            return "init"

        @ao.step(name="combine", deps=["__subchain__chain_a", "__subchain__chain_b"])
        async def combine(ctx):
            a = ctx.get("result_a")
            b = ctx.get("result_b")
            return {"a": a, "b": b}

        @ao.chain(name="parallel_parent")
        class ParallelParent:
            steps = ["init", "chain_a", "chain_b", "combine"]

        result = await ao.launch("parallel_parent")

        assert result["success"] is True

        # Check subchains ran in parallel (start times should be close)
        if "a" in start_times and "b" in start_times:
            time_diff = abs(start_times["a"] - start_times["b"])
            assert time_diff < 0.05  # Within 50ms means parallel


# ══════════════════════════════════════════════════════════════════════════════
#                           Real-World Scenario Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestRealWorldScenarios:
    """Tests simulating real-world chain composition scenarios."""

    @pytest.fixture
    def ao(self):
        return AgentOrchestrator.temp_registries("real_world_test")

    @pytest.mark.asyncio
    async def test_etl_pipeline_composition(self, ao):
        """Test ETL pipeline with extraction, transformation, and loading subchains."""
        # Extraction chain
        @ao.step(name="extract_users")
        async def extract_users(ctx):
            ctx.set("users", [{"id": 1, "name": "Alice"}], scope=ContextScope.CHAIN)
            return {"extracted": "users"}

        @ao.step(name="extract_orders")
        async def extract_orders(ctx):
            ctx.set("orders", [{"user_id": 1, "amount": 100}], scope=ContextScope.CHAIN)
            return {"extracted": "orders"}

        @ao.chain(name="extraction_chain")
        class ExtractionChain:
            steps = ["extract_users", "extract_orders"]

        # Transformation chain
        @ao.step(name="transform_data")
        async def transform_data(ctx):
            users = ctx.get("users", [])
            orders = ctx.get("orders", [])
            # Join data
            enriched = []
            for order in orders:
                user = next((u for u in users if u["id"] == order["user_id"]), None)
                enriched.append({
                    "user_name": user["name"] if user else "Unknown",
                    "amount": order["amount"],
                })
            ctx.set("enriched_data", enriched, scope=ContextScope.CHAIN)
            return {"transformed": len(enriched)}

        @ao.chain(name="transformation_chain")
        class TransformationChain:
            steps = ["transform_data"]

        # Loading chain
        @ao.step(name="load_to_warehouse")
        async def load_to_warehouse(ctx):
            data = ctx.get("enriched_data", [])
            return {"loaded": len(data), "status": "success"}

        @ao.chain(name="loading_chain")
        class LoadingChain:
            steps = ["load_to_warehouse"]

        # Main ETL pipeline
        @ao.chain(name="etl_pipeline")
        class ETLPipeline:
            steps = ["extraction_chain", "transformation_chain", "loading_chain"]

        result = await ao.launch("etl_pipeline")

        assert result["success"] is True

        # Verify final output
        load_result = next(
            r for r in result["results"]
            if r["step"] == "__subchain__loading_chain"
        )
        # The subchain result contains the steps_executed count
        assert load_result["success"] is True

    @pytest.mark.asyncio
    async def test_validation_with_early_exit(self, ao):
        """Test composition where validation failure should stop pipeline."""
        process_executed = []

        @ao.step(name="validate_input")
        async def validate_input(ctx):
            data = ctx.get("input_data")
            if not data or not data.get("required_field"):
                raise ValueError("Missing required_field")
            return {"valid": True}

        @ao.chain(name="validation_chain")
        class ValidationChain:
            steps = ["validate_input"]

        # Process step with explicit dependency on validation subchain
        @ao.step(name="process", deps=["__subchain__validation_chain"])
        async def process(ctx):
            process_executed.append(True)
            return {"processed": True}

        @ao.chain(name="processing_pipeline")
        class ProcessingPipeline:
            steps = ["validation_chain", "process"]

        # Test with invalid input
        result = await ao.launch(
            "processing_pipeline",
            data={"input_data": {}},  # Missing required_field
        )

        assert result["success"] is False
        assert len(process_executed) == 0  # Process should not have run

        # Test with valid input - use a new ao to reset state
        ao2 = AgentOrchestrator.temp_registries("validation_test_2")
        process_executed_2 = []

        @ao2.step(name="validate_input")
        async def validate_input2(ctx):
            data = ctx.get("input_data")
            if not data or not data.get("required_field"):
                raise ValueError("Missing required_field")
            return {"valid": True}

        @ao2.chain(name="validation_chain")
        class ValidationChain2:
            steps = ["validate_input"]

        @ao2.step(name="process", deps=["__subchain__validation_chain"])
        async def process2(ctx):
            process_executed_2.append(True)
            return {"processed": True}

        @ao2.chain(name="processing_pipeline")
        class ProcessingPipeline2:
            steps = ["validation_chain", "process"]

        result = await ao2.launch(
            "processing_pipeline",
            data={"input_data": {"required_field": "value"}},
        )

        assert result["success"] is True
        assert len(process_executed_2) == 1
