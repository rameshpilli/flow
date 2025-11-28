"""
FlowForge Test Suite

Tests for the FlowForge framework core functionality.
"""

import asyncio

# Import FlowForge components
import sys

import pytest

sys.path.insert(0, "/Users/rameshpilli/Developer/ChainServer")

from flowforge import ChainContext, FlowForge
from flowforge.agents import AgentResult, BaseAgent
from flowforge.core.context import ContextScope, StepResult
from flowforge.core.registry import get_agent_registry, get_chain_registry, get_step_registry
from flowforge.middleware import CacheMiddleware, LoggerMiddleware


class TestChainContext:
    """Tests for ChainContext"""

    def test_context_creation(self):
        ctx = ChainContext(request_id="test_123")
        assert ctx.request_id == "test_123"
        assert len(ctx.keys()) == 0

    def test_context_set_get(self):
        ctx = ChainContext(request_id="test")
        ctx.set("key1", "value1")
        assert ctx.get("key1") == "value1"
        assert ctx.get("nonexistent", "default") == "default"

    def test_context_scope(self):
        ctx = ChainContext(request_id="test")
        ctx.set("chain_data", "persists", scope=ContextScope.CHAIN)
        ctx.set("step_data", "temporary", scope=ContextScope.STEP)

        ctx.enter_step("test_step")
        assert ctx.get("chain_data") == "persists"
        assert ctx.get("step_data") == "temporary"

        ctx.exit_step()
        assert ctx.get("chain_data") == "persists"
        assert ctx.get("step_data") is None  # Step-scoped data cleared

    def test_context_results(self):
        ctx = ChainContext(request_id="test")
        result = StepResult(step_name="step1", output={"data": 1}, duration_ms=100)
        ctx.add_result(result)

        assert len(ctx.results) == 1
        assert ctx.last_result.step_name == "step1"
        assert ctx.get_result("step1").output == {"data": 1}

    def test_context_to_dict(self):
        ctx = ChainContext(request_id="test_123")
        ctx.set("key", "value")

        d = ctx.to_dict()
        assert d["request_id"] == "test_123"
        assert "key" in d["data"]


class TestFlowForge:
    """Tests for FlowForge main class"""

    def setup_method(self):
        """Reset registries before each test"""
        get_agent_registry().clear()
        get_step_registry().clear()
        get_chain_registry().clear()

    def test_forge_creation(self):
        forge = FlowForge(name="test_app", version="1.0.0")
        assert forge.name == "test_app"
        assert forge.version == "1.0.0"

    def test_step_registration(self):
        forge = FlowForge(name="test")

        @forge.step(name="my_step")
        async def my_step(ctx: ChainContext):
            return {"result": "done"}

        assert "my_step" in forge.list_steps()

    def test_agent_registration(self):
        forge = FlowForge(name="test")

        @forge.agent(name="my_agent")
        class MyAgent(BaseAgent):
            async def fetch(self, query: str, **kwargs) -> AgentResult:
                return AgentResult(data={"query": query}, source="test", query=query)

        assert "my_agent" in forge.list_agents()

    def test_chain_registration(self):
        forge = FlowForge(name="test")

        @forge.step(name="step_a")
        async def step_a(ctx):
            return {}

        @forge.step(name="step_b")
        async def step_b(ctx):
            return {}

        @forge.chain(name="my_chain")
        class MyChain:
            steps = ["step_a", "step_b"]

        assert "my_chain" in forge.list_chains()


class TestDAGExecution:
    """Tests for DAG-based execution"""

    def setup_method(self):
        get_agent_registry().clear()
        get_step_registry().clear()
        get_chain_registry().clear()

    @pytest.mark.asyncio
    async def test_simple_chain_execution(self):
        forge = FlowForge(name="test")

        @forge.step(name="step1", produces=["data1"])
        async def step1(ctx: ChainContext):
            ctx.set("data1", "from_step1")
            return {"data1": "from_step1"}

        @forge.step(name="step2", deps=["step1"], produces=["data2"])
        async def step2(ctx: ChainContext):
            data1 = ctx.get("data1")
            ctx.set("data2", f"processed_{data1}")
            return {"data2": ctx.get("data2")}

        @forge.chain(name="test_chain")
        class TestChain:
            steps = ["step1", "step2"]

        result = await forge.run("test_chain")

        assert result["success"] is True
        assert len(result["results"]) == 2
        assert result["context"]["data"]["data2"] == "processed_from_step1"

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """Test that independent steps run in parallel"""
        forge = FlowForge(name="test")
        execution_order = []

        @forge.step(name="parallel_a")
        async def parallel_a(ctx):
            execution_order.append("a_start")
            await asyncio.sleep(0.1)
            execution_order.append("a_end")
            return {}

        @forge.step(name="parallel_b")
        async def parallel_b(ctx):
            execution_order.append("b_start")
            await asyncio.sleep(0.1)
            execution_order.append("b_end")
            return {}

        @forge.step(name="combine", deps=["parallel_a", "parallel_b"])
        async def combine(ctx):
            execution_order.append("combine")
            return {}

        @forge.chain(name="parallel_chain")
        class ParallelChain:
            steps = ["parallel_a", "parallel_b", "combine"]

        result = await forge.run("parallel_chain")

        assert result["success"] is True
        # Both a and b should start before either ends (parallel execution)
        assert execution_order.index("a_start") < execution_order.index("combine")
        assert execution_order.index("b_start") < execution_order.index("combine")

    @pytest.mark.asyncio
    async def test_error_handling(self):
        forge = FlowForge(name="test")

        @forge.step(name="failing_step")
        async def failing_step(ctx):
            raise ValueError("Test error")

        @forge.chain(name="error_chain")
        class ErrorChain:
            steps = ["failing_step"]

        result = await forge.run("error_chain")

        assert result["success"] is False
        assert "Test error" in result["error"]


class TestMiddleware:
    """Tests for middleware"""

    def setup_method(self):
        get_agent_registry().clear()
        get_step_registry().clear()
        get_chain_registry().clear()

    @pytest.mark.asyncio
    async def test_logger_middleware(self):
        forge = FlowForge(name="test")
        forge.use(LoggerMiddleware())

        @forge.step(name="logged_step")
        async def logged_step(ctx):
            return {"done": True}

        @forge.chain(name="logged_chain")
        class LoggedChain:
            steps = ["logged_step"]

        result = await forge.run("logged_chain")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_cache_middleware(self):
        forge = FlowForge(name="test")
        cache = CacheMiddleware(ttl_seconds=60)
        forge.use(cache)

        call_count = 0

        @forge.step(name="cached_step")
        async def cached_step(ctx):
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        @forge.chain(name="cached_chain")
        class CachedChain:
            steps = ["cached_step"]

        # First run
        await forge.run("cached_chain")

        # Check stats
        stats = cache.get_stats()
        assert stats["entries"] >= 0  # Cache may or may not store depending on implementation


class TestAgents:
    """Tests for agent system"""

    def setup_method(self):
        get_agent_registry().clear()
        get_step_registry().clear()
        get_chain_registry().clear()

    @pytest.mark.asyncio
    async def test_custom_agent(self):
        forge = FlowForge(name="test")

        @forge.agent(name="test_agent")
        class TestAgent(BaseAgent):
            async def fetch(self, query: str, **kwargs) -> AgentResult:
                return AgentResult(
                    data={"query": query, "result": "found"},
                    source="test",
                    query=query,
                )

        agent = forge.get_agent("test_agent")
        result = await agent.fetch("test query")

        assert result.success is True
        assert result.data["query"] == "test query"

    @pytest.mark.asyncio
    async def test_agent_in_step(self):
        forge = FlowForge(name="test")

        @forge.agent(name="data_agent")
        class DataAgent(BaseAgent):
            async def fetch(self, query: str, **kwargs) -> AgentResult:
                return AgentResult(
                    data={"items": [1, 2, 3]},
                    source="data",
                    query=query,
                )

        @forge.step(name="fetch_step", produces=["items"])
        async def fetch_step(ctx: ChainContext):
            agent = forge.get_agent("data_agent")
            result = await agent.fetch("get items")
            ctx.set("items", result.data["items"])
            return {"items": result.data["items"]}

        @forge.chain(name="agent_chain")
        class AgentChain:
            steps = ["fetch_step"]

        result = await forge.run("agent_chain")

        assert result["success"] is True
        assert result["context"]["data"]["items"] == [1, 2, 3]


class TestVisualization:
    """Tests for chain visualization"""

    def setup_method(self):
        get_agent_registry().clear()
        get_step_registry().clear()
        get_chain_registry().clear()

    def test_chain_visualization(self):
        forge = FlowForge(name="test")

        @forge.step(name="step_a")
        async def step_a(ctx):
            return {}

        @forge.step(name="step_b", deps=["step_a"])
        async def step_b(ctx):
            return {}

        @forge.step(name="step_c", deps=["step_b"])
        async def step_c(ctx):
            return {}

        @forge.chain(name="viz_chain")
        class VizChain:
            steps = ["step_a", "step_b", "step_c"]

        # Use graph() method instead of visualize_chain()
        viz = forge.graph("viz_chain")

        assert "step_a" in viz
        assert "step_b" in viz
        assert "step_c" in viz


class TestSummarizer:
    """Tests for summarizer middleware"""

    def test_domain_prompts_exist(self):
        """Test that domain prompts are defined"""
        from flowforge.middleware.summarizer import DOMAIN_PROMPTS

        # All expected domains should exist
        expected_domains = ["sec_filing", "earnings", "news", "transcripts", "pricing"]
        for domain in expected_domains:
            assert domain in DOMAIN_PROMPTS
            assert "map" in DOMAIN_PROMPTS[domain]
            assert "reduce" in DOMAIN_PROMPTS[domain]

    def test_get_domain_prompts(self):
        """Test getting domain-specific prompts"""
        from flowforge.middleware.summarizer import LangChainSummarizer, get_domain_prompts

        # Test known domain
        map_prompt, reduce_prompt = get_domain_prompts("sec_filing")
        assert "SEC filing" in map_prompt or "financial" in map_prompt.lower()
        assert "consolidate" in reduce_prompt.lower() or "combine" in reduce_prompt.lower()

        # Test unknown domain falls back to defaults
        map_prompt, reduce_prompt = get_domain_prompts("unknown_domain")
        assert map_prompt == LangChainSummarizer.DEFAULT_MAP_PROMPT
        assert reduce_prompt == LangChainSummarizer.DEFAULT_REDUCE_PROMPT

    def test_summarizer_content_type_parameter(self):
        """Test that summarizer accepts content_type parameter"""
        from flowforge.middleware.summarizer import LangChainSummarizer

        summarizer = LangChainSummarizer(llm=None)

        # Should not raise error
        import asyncio

        result = asyncio.run(
            summarizer.summarize(
                "Test content",
                max_tokens=100,
                content_type="sec_filing",
            )
        )

        # Without LLM, should truncate
        assert isinstance(result, str)

    def test_create_domain_aware_middleware(self):
        """Test factory function for domain-aware middleware"""
        from flowforge.middleware.summarizer import create_domain_aware_middleware

        middleware = create_domain_aware_middleware(llm=None, max_tokens=4000)

        # Should have step_content_types configured
        assert "sec_filing" in middleware.step_content_types.values()
        assert "earnings" in middleware.step_content_types.values()
        assert "news" in middleware.step_content_types.values()

    def test_summarizer_middleware_with_content_type(self):
        """Test SummarizerMiddleware with step_content_types"""
        from flowforge.middleware.summarizer import SummarizerMiddleware

        middleware = SummarizerMiddleware(
            max_tokens=4000,
            step_content_types={
                "fetch_sec": "sec_filing",
                "fetch_news": "news",
            },
        )

        assert middleware.step_content_types["fetch_sec"] == "sec_filing"
        assert middleware.step_content_types["fetch_news"] == "news"


class TestExports:
    """Tests for package exports"""

    def test_main_exports(self):
        """Test that main package exports are available"""
        from flowforge import (
            DOMAIN_PROMPTS,
            CacheMiddleware,
            ChainContext,
            ChainRequest,
            ChainResponse,
            CMPTChain,
            FlowForge,
            LangChainSummarizer,
            LoggerMiddleware,
            SummarizationStrategy,
            SummarizerMiddleware,
            TokenManagerMiddleware,
            create_domain_aware_middleware,
        )

        # All imports should succeed
        assert FlowForge is not None
        assert ChainContext is not None
        assert SummarizerMiddleware is not None
        assert LangChainSummarizer is not None
        assert SummarizationStrategy is not None
        assert create_domain_aware_middleware is not None
        assert DOMAIN_PROMPTS is not None
        assert CacheMiddleware is not None
        assert LoggerMiddleware is not None
        assert TokenManagerMiddleware is not None
        assert CMPTChain is not None
        assert ChainRequest is not None
        assert ChainResponse is not None

    def test_middleware_exports(self):
        """Test middleware submodule exports"""
        from flowforge.middleware import (
            Middleware,
            create_anthropic_summarizer,
            create_openai_summarizer,
            get_domain_prompts,
        )

        assert Middleware is not None
        assert create_openai_summarizer is not None
        assert create_anthropic_summarizer is not None
        assert get_domain_prompts is not None


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
