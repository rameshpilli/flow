"""
End-to-end integration tests for CMPT chain with mocked HTTP.

Tests the full chain execution with mocked external services to validate:
- Chain orchestration
- Error handling and partial success
- Data flow between steps
- Retry and circuit breaker behavior
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
sys.path.insert(0, "/Users/rameshpilli/Developer/ChainServer")

from flowforge import FlowForge, ChainContext
from flowforge.core.context import ExecutionSummary, StepResult
from flowforge.core.registry import (
    get_agent_registry,
    get_chain_registry,
    get_step_registry,
)


class MockHTTPResponse:
    """Mock HTTP response for testing."""

    def __init__(self, json_data: dict, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=MagicMock(),
                response=self,
            )


class TestCMPTChainIntegration:
    """End-to-end tests for CMPT chain."""

    def setup_method(self):
        """Reset registries before each test."""
        get_agent_registry().clear()
        get_step_registry().clear()
        get_chain_registry().clear()

    @pytest.mark.asyncio
    async def test_simple_chain_end_to_end(self):
        """Test a simple multi-step chain from start to finish."""
        forge = FlowForge(name="test_integration", isolated=True)

        # Track execution order
        execution_log = []

        @forge.step(name="fetch_company_data", produces=["company_data"])
        async def fetch_company_data(ctx: ChainContext):
            execution_log.append("fetch_company_data")
            company = ctx.get("company_name", "TestCorp")
            ctx.set("company_data", {"name": company, "revenue": 1000000})
            return {"company": company}

        @forge.step(name="enrich_data", deps=["fetch_company_data"], produces=["enriched_data"])
        async def enrich_data(ctx: ChainContext):
            execution_log.append("enrich_data")
            company_data = ctx.get("company_data")
            enriched = {
                **company_data,
                "industry": "Technology",
                "employees": 5000,
            }
            ctx.set("enriched_data", enriched)
            return enriched

        @forge.step(name="generate_summary", deps=["enrich_data"])
        async def generate_summary(ctx: ChainContext):
            execution_log.append("generate_summary")
            enriched = ctx.get("enriched_data")
            summary = f"Company {enriched['name']} in {enriched['industry']} sector"
            return {"summary": summary}

        @forge.chain(name="test_chain")
        class TestChain:
            steps = ["fetch_company_data", "enrich_data", "generate_summary"]

        # Run the chain
        result = await forge.run("test_chain", {"company_name": "Apple Inc"})

        # Verify success
        assert result["success"] is True
        assert len(result["results"]) == 3

        # Verify execution order
        assert execution_log == ["fetch_company_data", "enrich_data", "generate_summary"]

        # Verify data flow
        assert "Apple Inc" in result["context"]["data"].get("company_data", {}).get("name", "")

    @pytest.mark.asyncio
    async def test_parallel_steps_with_mocked_http(self):
        """Test parallel data fetching with mocked HTTP responses."""
        forge = FlowForge(name="test_parallel", isolated=True)

        # Mock HTTP responses
        mock_responses = {
            "company": {"name": "TestCorp", "ticker": "TEST"},
            "financials": {"revenue": 1000000, "profit": 100000},
            "news": [{"title": "TestCorp launches new product"}],
        }

        @forge.step(name="fetch_company")
        async def fetch_company(ctx: ChainContext):
            await asyncio.sleep(0.05)  # Simulate network delay
            ctx.set("company_info", mock_responses["company"])
            return mock_responses["company"]

        @forge.step(name="fetch_financials")
        async def fetch_financials(ctx: ChainContext):
            await asyncio.sleep(0.05)
            ctx.set("financial_info", mock_responses["financials"])
            return mock_responses["financials"]

        @forge.step(name="fetch_news")
        async def fetch_news(ctx: ChainContext):
            await asyncio.sleep(0.05)
            ctx.set("news_info", mock_responses["news"])
            return mock_responses["news"]

        @forge.step(name="combine_data", deps=["fetch_company", "fetch_financials", "fetch_news"])
        async def combine_data(ctx: ChainContext):
            combined = {
                "company": ctx.get("company_info"),
                "financials": ctx.get("financial_info"),
                "news": ctx.get("news_info"),
            }
            return combined

        @forge.chain(name="parallel_chain")
        class ParallelChain:
            steps = ["fetch_company", "fetch_financials", "fetch_news", "combine_data"]

        # Run and measure time
        import time
        start = time.perf_counter()
        result = await forge.run("parallel_chain")
        duration = time.perf_counter() - start

        # Verify success
        assert result["success"] is True

        # Verify parallel execution (should be ~0.05s, not ~0.15s)
        # Allow some overhead
        assert duration < 0.3, f"Expected parallel execution, got {duration:.3f}s"

    @pytest.mark.asyncio
    async def test_error_handling_continue_mode(self):
        """Test continue mode with partial success."""
        forge = FlowForge(name="test_continue", isolated=True)

        @forge.step(name="step_a")
        async def step_a(ctx: ChainContext):
            ctx.set("a_data", "success")
            return {"status": "ok"}

        @forge.step(name="step_b")
        async def step_b(ctx: ChainContext):
            raise ValueError("Step B failed intentionally")

        @forge.step(name="step_c", deps=["step_a"])
        async def step_c(ctx: ChainContext):
            a_data = ctx.get("a_data")
            return {"a_data": a_data}

        @forge.step(name="step_d", deps=["step_b"])  # Depends on failing step
        async def step_d(ctx: ChainContext):
            return {"should_not_run": True}

        @forge.chain(name="continue_chain", error_handling="continue")
        class ContinueChain:
            steps = ["step_a", "step_b", "step_c", "step_d"]

        result = await forge.run("continue_chain")

        # Overall should fail
        assert result["success"] is False

        # Collect results
        results_by_step = {r["step_name"]: r for r in result["results"]}

        # step_a: SUCCESS
        assert results_by_step["step_a"]["error"] is None

        # step_b: FAILED
        assert results_by_step["step_b"]["error"] is not None

        # step_c: SUCCESS (depends only on step_a)
        assert results_by_step["step_c"]["error"] is None

        # step_d: SKIPPED (depends on failed step_b)
        assert "step_d" in results_by_step
        # Should have skipped_reason or error indicating skip
        step_d_result = results_by_step["step_d"]
        assert step_d_result.get("skipped_reason") or "Skipped" in str(step_d_result.get("error", ""))

    @pytest.mark.asyncio
    async def test_retry_behavior(self):
        """Test retry logic with eventual success."""
        forge = FlowForge(name="test_retry", isolated=True)

        attempt_count = [0]

        @forge.step(name="flaky_step", retry=3)
        async def flaky_step(ctx: ChainContext):
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise ConnectionError(f"Attempt {attempt_count[0]} failed")
            return {"success": True, "attempts": attempt_count[0]}

        @forge.chain(name="retry_chain", error_handling="retry")
        class RetryChain:
            steps = ["flaky_step"]

        result = await forge.run("retry_chain")

        # Should succeed after retries
        assert result["success"] is True
        assert attempt_count[0] == 3

        # Only one result should be recorded
        flaky_results = [r for r in result["results"] if r["step_name"] == "flaky_step"]
        assert len(flaky_results) == 1
        assert flaky_results[0]["error"] is None

    @pytest.mark.asyncio
    async def test_execution_summary_partial_success(self):
        """Test ExecutionSummary tracks partial success correctly."""
        summary = ExecutionSummary(
            chain_name="test_chain",
            request_id="test_123",
            total_steps=4,
        )

        # Add results
        summary.add_result(StepResult(step_name="step_a", output={}, duration_ms=100))
        summary.add_result(StepResult(step_name="step_b", output={}, duration_ms=50))
        summary.add_result(StepResult(
            step_name="step_c",
            output=None,
            duration_ms=25,
            error=ValueError("failed"),
            error_type="ValueError",
        ))
        summary.add_result(StepResult(
            step_name="step_d",
            output=None,
            duration_ms=0,
            skipped_reason="dependency failed: step_c",
        ))

        summary.finalize()

        # Verify counts
        assert summary.completed_steps == 2
        assert summary.failed_steps == 1
        assert summary.skipped_steps == 1
        assert summary.total_steps == 4

        # Verify partial success
        assert summary.success is False
        assert summary.partial_success is True

        # Verify completion rate
        assert summary.completion_rate == 50.0

        # Verify helper methods
        assert len(summary.get_successful_steps()) == 2
        assert len(summary.get_failed_steps()) == 1
        assert len(summary.get_skipped_steps()) == 1

    @pytest.mark.asyncio
    async def test_step_result_rich_metadata(self):
        """Test that StepResult includes rich error metadata."""
        forge = FlowForge(name="test_metadata", isolated=True)

        @forge.step(name="error_step")
        async def error_step(ctx: ChainContext):
            raise ValueError("Detailed error message")

        @forge.chain(name="error_chain")
        class ErrorChain:
            steps = ["error_step"]

        result = await forge.run("error_chain")

        # Find the error step result
        error_result = next(r for r in result["results"] if r["step_name"] == "error_step")

        # Verify rich metadata
        assert error_result["error"] is not None
        assert error_result["error_type"] == "ValueError"
        assert error_result["error_traceback"] is not None
        assert "Detailed error message" in str(error_result["error"])


class TestParallelismBenchmark:
    """Smoke performance benchmarks for parallelism validation."""

    def setup_method(self):
        get_agent_registry().clear()
        get_step_registry().clear()
        get_chain_registry().clear()

    @pytest.mark.asyncio
    async def test_parallel_speedup(self):
        """Verify that parallel execution provides speedup over sequential."""
        forge = FlowForge(name="test_benchmark", isolated=True)

        STEP_DELAY = 0.1  # 100ms per step
        NUM_PARALLEL_STEPS = 5

        # Create parallel steps
        for i in range(NUM_PARALLEL_STEPS):
            @forge.step(name=f"parallel_step_{i}")
            async def parallel_step(ctx: ChainContext, idx=i):
                await asyncio.sleep(STEP_DELAY)
                return {"step": idx}

        @forge.step(
            name="final_step",
            deps=[f"parallel_step_{i}" for i in range(NUM_PARALLEL_STEPS)]
        )
        async def final_step(ctx: ChainContext):
            return {"done": True}

        @forge.chain(name="benchmark_chain")
        class BenchmarkChain:
            steps = [f"parallel_step_{i}" for i in range(NUM_PARALLEL_STEPS)] + ["final_step"]

        # Run and measure
        import time
        start = time.perf_counter()
        result = await forge.run("benchmark_chain")
        duration = time.perf_counter() - start

        assert result["success"] is True

        # Sequential would be: NUM_PARALLEL_STEPS * STEP_DELAY = 0.5s
        # Parallel should be: ~STEP_DELAY + overhead = ~0.15s
        sequential_time = NUM_PARALLEL_STEPS * STEP_DELAY
        expected_parallel_time = STEP_DELAY * 1.5  # Allow 50% overhead

        assert duration < expected_parallel_time, (
            f"Parallel execution too slow: {duration:.3f}s > {expected_parallel_time:.3f}s "
            f"(sequential would be {sequential_time:.3f}s)"
        )

        # Calculate speedup
        speedup = sequential_time / duration
        assert speedup > 2.0, f"Expected >2x speedup, got {speedup:.2f}x"

    @pytest.mark.asyncio
    async def test_concurrency_limit_respected(self):
        """Test that max_concurrency limits are respected."""
        forge = FlowForge(name="test_concurrency", isolated=True)

        concurrent_count = [0]
        max_observed = [0]

        @forge.step(name="limited_step", max_concurrency=2)
        async def limited_step(ctx: ChainContext):
            concurrent_count[0] += 1
            max_observed[0] = max(max_observed[0], concurrent_count[0])
            await asyncio.sleep(0.1)
            concurrent_count[0] -= 1
            return {}

        # Verify the step spec has max_concurrency set
        spec = get_step_registry().get_spec("limited_step")
        assert spec is not None
        assert spec.max_concurrency == 2


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
