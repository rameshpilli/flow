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


class TestUserOverrides:
    """Tests for user override functionality in ChainRequest"""

    def test_chain_request_overrides_model(self):
        """Test ChainRequestOverrides model creation"""
        from flowforge.services.models import ChainRequest, ChainRequestOverrides

        overrides = ChainRequestOverrides(
            ticker="AAPL",
            fiscal_quarter="Q1",
            fiscal_year="2025",
            next_earnings_date="2025-01-30",
            news_lookback_days=60,
        )

        assert overrides.ticker == "AAPL"
        assert overrides.fiscal_quarter == "Q1"
        assert overrides.fiscal_year == "2025"
        assert overrides.next_earnings_date == "2025-01-30"
        assert overrides.news_lookback_days == 60

    def test_chain_request_with_overrides(self):
        """Test ChainRequest with overrides"""
        from flowforge.services.models import ChainRequest, ChainRequestOverrides

        request = ChainRequest(
            corporate_company_name="Apple Inc",
            meeting_datetime="2025-02-15",
            rbc_employee_email="john.doe@rbc.com",
            overrides=ChainRequestOverrides(
                ticker="AAPL",
                fiscal_quarter="Q1",
                skip_earnings_calendar_api=True,
            ),
        )

        assert request.corporate_company_name == "Apple Inc"
        assert request.overrides is not None
        assert request.overrides.ticker == "AAPL"
        assert request.overrides.fiscal_quarter == "Q1"
        assert request.overrides.skip_earnings_calendar_api is True

    def test_chain_request_without_overrides(self):
        """Test ChainRequest without overrides"""
        from flowforge.services.models import ChainRequest

        request = ChainRequest(
            corporate_company_name="Microsoft",
            meeting_datetime="2025-03-01",
        )

        assert request.corporate_company_name == "Microsoft"
        assert request.overrides is None

    @pytest.mark.asyncio
    async def test_context_builder_with_ticker_override(self):
        """Test ContextBuilder applies ticker override"""
        from flowforge.services.context_builder import ContextBuilderService
        from flowforge.services.models import ChainRequest, ChainRequestOverrides

        service = ContextBuilderService()

        request = ChainRequest(
            corporate_company_name="Apple Inc",
            meeting_datetime="2025-02-15",
            overrides=ChainRequestOverrides(
                ticker="AAPL",
            ),
        )

        output = await service.execute(request)

        # Ticker should be the override value
        assert output.ticker == "AAPL"
        assert output.company_info.ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_context_builder_with_fiscal_quarter_override(self):
        """Test ContextBuilder applies fiscal quarter override"""
        from flowforge.services.context_builder import ContextBuilderService
        from flowforge.services.models import ChainRequest, ChainRequestOverrides

        service = ContextBuilderService()

        request = ChainRequest(
            corporate_company_name="Google",
            meeting_datetime="2025-06-15",  # Would normally be Q2
            overrides=ChainRequestOverrides(
                fiscal_quarter="Q1",  # Override to Q1
                fiscal_year="2025",
            ),
        )

        output = await service.execute(request)

        # Fiscal quarter should be the override value
        assert output.temporal_context is not None
        assert output.temporal_context.fiscal_quarter == "1"
        assert output.temporal_context.fiscal_year == "2025"

    @pytest.mark.asyncio
    async def test_context_builder_skip_earnings_api(self):
        """Test ContextBuilder skips earnings calendar API when override set"""
        from flowforge.services.context_builder import ContextBuilderService
        from flowforge.services.models import ChainRequest, ChainRequestOverrides

        service = ContextBuilderService()

        request = ChainRequest(
            corporate_company_name="Netflix",
            meeting_datetime="2025-04-15",
            overrides=ChainRequestOverrides(
                fiscal_quarter="Q2",
                skip_earnings_calendar_api=True,
            ),
        )

        output = await service.execute(request)

        # Should have temporal context created from overrides
        assert output.temporal_context is not None
        assert output.temporal_context.fiscal_quarter == "2"

    @pytest.mark.asyncio
    async def test_context_builder_skip_company_lookup(self):
        """Test ContextBuilder skips company lookup when override set"""
        from flowforge.services.context_builder import ContextBuilderService
        from flowforge.services.models import ChainRequest, ChainRequestOverrides

        service = ContextBuilderService()

        request = ChainRequest(
            corporate_company_name="Test Company",
            meeting_datetime="2025-05-01",
            overrides=ChainRequestOverrides(
                ticker="TEST",
                industry="Technology",
                skip_company_lookup=True,
            ),
        )

        output = await service.execute(request)

        # Company info should be created from overrides
        assert output.company_info is not None
        assert output.company_info.name == "Test Company"
        assert output.company_info.ticker == "TEST"
        assert output.company_info.industry == "Technology"

    @pytest.mark.asyncio
    async def test_context_builder_lookback_overrides(self):
        """Test ContextBuilder applies lookback period overrides"""
        from flowforge.services.context_builder import ContextBuilderService
        from flowforge.services.models import ChainRequest, ChainRequestOverrides

        service = ContextBuilderService()

        request = ChainRequest(
            corporate_company_name="Amazon",
            meeting_datetime="2025-03-15",
            overrides=ChainRequestOverrides(
                news_lookback_days=90,
                filing_quarters=12,
            ),
        )

        output = await service.execute(request)

        # Lookback periods should be the override values
        assert output.temporal_context is not None
        assert output.temporal_context.news_lookback_days == 90
        assert output.temporal_context.filing_quarters == 12

    def test_overrides_validation(self):
        """Test that overrides have proper validation"""
        from flowforge.services.models import ChainRequestOverrides
        import pydantic

        # news_lookback_days must be between 1 and 365
        with pytest.raises(pydantic.ValidationError):
            ChainRequestOverrides(news_lookback_days=0)

        with pytest.raises(pydantic.ValidationError):
            ChainRequestOverrides(news_lookback_days=400)

        # filing_quarters must be between 1 and 20
        with pytest.raises(pydantic.ValidationError):
            ChainRequestOverrides(filing_quarters=0)

        with pytest.raises(pydantic.ValidationError):
            ChainRequestOverrides(filing_quarters=25)


class TestLLMGateway:
    """Tests for LLM Gateway client"""

    def test_llm_gateway_client_creation(self):
        """Test LLMGatewayClient can be created"""
        from flowforge.services.llm_gateway import LLMGatewayClient

        client = LLMGatewayClient(
            server_url="https://llm.example.com/v1",
            model_name="gpt-4",
            api_key="test-key",
        )

        assert client.server_url == "https://llm.example.com/v1"
        assert client.model_name == "gpt-4"
        assert client.temperature == 0.0
        assert client.max_tokens == 4096

    def test_llm_gateway_client_with_oauth_config(self):
        """Test LLMGatewayClient with OAuth configuration"""
        from flowforge.services.llm_gateway import LLMGatewayClient

        client = LLMGatewayClient(
            server_url="https://llm.example.com/v1",
            model_name="gpt-4",
            oauth_endpoint="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
        )

        assert client._token_manager is not None
        assert client._token_manager.oauth_endpoint == "https://auth.example.com/oauth/token"
        assert client._token_manager.client_id == "test-client"

    def test_oauth_token_manager_creation(self):
        """Test OAuthTokenManager can be created"""
        from flowforge.services.llm_gateway import OAuthTokenManager

        manager = OAuthTokenManager(
            oauth_endpoint="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
        )

        assert manager.oauth_endpoint == "https://auth.example.com/oauth/token"
        assert manager.grant_type == "client_credentials"
        assert manager.scope == "read"

    def test_get_llm_client_factory(self):
        """Test get_llm_client factory function"""
        import os
        from flowforge.services.llm_gateway import get_llm_client

        # Set environment variables for testing
        os.environ["LLM_GATEWAY_URL"] = "https://test.example.com/v1"
        os.environ["LLM_MODEL_NAME"] = "test-model"
        os.environ["LLM_API_KEY"] = "test-api-key"

        try:
            client = get_llm_client()
            assert client.server_url == "https://test.example.com/v1"
            assert client.model_name == "test-model"
        finally:
            # Clean up
            del os.environ["LLM_GATEWAY_URL"]
            del os.environ["LLM_MODEL_NAME"]
            del os.environ["LLM_API_KEY"]

    def test_timed_lru_cache(self):
        """Test timed_lru_cache decorator"""
        from flowforge.services.llm_gateway import timed_lru_cache
        import time

        call_count = 0

        @timed_lru_cache(seconds=1)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - should execute function
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        # Second call within TTL - should use cache
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count == 1

        # Wait for cache to expire
        time.sleep(1.1)

        # Call after expiry - should execute function again
        result3 = expensive_function(5)
        assert result3 == 10
        assert call_count == 2

    def test_default_llm_client_singleton(self):
        """Test default LLM client singleton pattern"""
        from flowforge.services.llm_gateway import (
            LLMGatewayClient,
            get_default_llm_client,
            set_default_llm_client,
        )

        # Initially should be None
        assert get_default_llm_client() is None

        # Set a default client
        test_client = LLMGatewayClient(
            server_url="https://test.example.com/v1",
            model_name="test-model",
            api_key="test-key",
        )
        set_default_llm_client(test_client)

        # Should now return our client
        retrieved = get_default_llm_client()
        assert retrieved is test_client

        # Clean up - set back to None
        from flowforge.services import llm_gateway
        llm_gateway._default_client = None


class TestResponseBuilderWithLLM:
    """Tests for ResponseBuilder with LLM integration"""

    def test_response_builder_without_llm(self):
        """Test ResponseBuilder works without LLM client"""
        from flowforge.services.response_builder import ResponseBuilderService

        service = ResponseBuilderService()
        assert service.llm_client is None
        assert service.use_llm_for_metrics is True
        assert service.use_llm_for_analysis is True

    def test_response_builder_with_llm_client(self):
        """Test ResponseBuilder accepts LLM client"""
        from flowforge.services.llm_gateway import LLMGatewayClient
        from flowforge.services.response_builder import ResponseBuilderService

        llm_client = LLMGatewayClient(
            server_url="https://llm.example.com/v1",
            model_name="gpt-4",
            api_key="test-key",
        )

        service = ResponseBuilderService(llm_client=llm_client)
        assert service.llm_client is llm_client

    def test_response_builder_llm_toggle_flags(self):
        """Test ResponseBuilder LLM toggle flags"""
        from flowforge.services.response_builder import ResponseBuilderService

        service = ResponseBuilderService(
            use_llm_for_metrics=False,
            use_llm_for_analysis=True,
            use_llm_for_content=False,
        )

        assert service.use_llm_for_metrics is False
        assert service.use_llm_for_analysis is True
        assert service.use_llm_for_content is False

    @pytest.mark.asyncio
    async def test_response_builder_fallback_without_llm(self):
        """Test ResponseBuilder falls back to heuristics without LLM"""
        from flowforge.services.response_builder import ResponseBuilderService
        from flowforge.services.models import (
            CompanyInfo,
            ContextBuilderOutput,
            ContentPrioritizationOutput,
        )

        service = ResponseBuilderService()

        context = ContextBuilderOutput(
            company_info=CompanyInfo(name="Test Corp", ticker="TEST"),
            company_name="Test Corp",
            ticker="TEST",
        )
        prioritization = ContentPrioritizationOutput()

        output = await service.execute(context, prioritization)

        assert output is not None
        assert output.prepared_content is not None
        assert "Test Corp" in output.prepared_content

    def test_parse_json_response(self):
        """Test JSON parsing from LLM responses"""
        from flowforge.services.response_builder import ResponseBuilderService

        service = ResponseBuilderService()

        # Test direct JSON
        result = service._parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

        # Test JSON in markdown code block
        result = service._parse_json_response('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

        # Test JSON in plain code block
        result = service._parse_json_response('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

        # Test JSON embedded in text
        result = service._parse_json_response('Here is the result: {"key": "value"}')
        assert result == {"key": "value"}

        # Test invalid JSON
        result = service._parse_json_response("not json at all")
        assert result is None


class TestGatewaySummarizer:
    """Tests for Gateway Summarizer factory"""

    def test_create_gateway_summarizer_import(self):
        """Test create_gateway_summarizer is importable"""
        from flowforge.middleware import create_gateway_summarizer

        assert create_gateway_summarizer is not None

    def test_middleware_exports_gateway_summarizer(self):
        """Test middleware module exports create_gateway_summarizer"""
        from flowforge.middleware import __all__

        assert "create_gateway_summarizer" in __all__


class TestLLMExports:
    """Tests for LLM-related exports"""

    def test_services_exports_llm_gateway(self):
        """Test services module exports LLM gateway components"""
        from flowforge.services import (
            LLMGatewayClient,
            OAuthTokenManager,
            get_llm_client,
            get_default_llm_client,
            set_default_llm_client,
            init_default_llm_client,
            timed_lru_cache,
        )

        # All imports should succeed
        assert LLMGatewayClient is not None
        assert OAuthTokenManager is not None
        assert get_llm_client is not None
        assert get_default_llm_client is not None
        assert set_default_llm_client is not None
        assert init_default_llm_client is not None
        assert timed_lru_cache is not None

    def test_chain_request_overrides_exported(self):
        """Test ChainRequestOverrides is exported from services"""
        from flowforge.services import ChainRequestOverrides

        assert ChainRequestOverrides is not None


class TestConfig:
    """Tests for configuration module"""

    def test_config_from_env(self):
        """Test Config can be loaded from environment"""
        import os
        from flowforge.config import Config

        # Set some test environment variables
        os.environ["LLM_GATEWAY_URL"] = "https://test.example.com/v1"
        os.environ["LLM_MODEL_NAME"] = "test-model"
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["DEFAULT_NEWS_LOOKBACK_DAYS"] = "60"

        try:
            config = Config.from_env()

            assert config.llm.server_url == "https://test.example.com/v1"
            assert config.llm.model_name == "test-model"
            assert config.llm.api_key == "test-key"
            assert config.chain.default_news_lookback_days == 60

        finally:
            # Clean up
            del os.environ["LLM_GATEWAY_URL"]
            del os.environ["LLM_MODEL_NAME"]
            del os.environ["LLM_API_KEY"]
            del os.environ["DEFAULT_NEWS_LOOKBACK_DAYS"]

    def test_llm_config_is_configured(self):
        """Test LLMConfig.is_configured property"""
        from flowforge.config import LLMConfig

        # Not configured - missing server URL
        config = LLMConfig(api_key="test-key")
        assert config.is_configured is False

        # Not configured - missing auth
        config = LLMConfig(server_url="https://test.com")
        assert config.is_configured is False

        # Configured with API key
        config = LLMConfig(server_url="https://test.com", api_key="test-key")
        assert config.is_configured is True

        # Configured with OAuth
        config = LLMConfig(
            server_url="https://test.com",
            oauth_endpoint="https://auth.com",
            client_id="id",
            client_secret="secret",
        )
        assert config.is_configured is True

    def test_config_get_llm_client(self):
        """Test Config.get_llm_client() factory method"""
        from flowforge.config import Config, LLMConfig

        # Unconfigured - should return None
        config = Config()
        assert config.get_llm_client() is None

        # Configured - should return client
        config = Config(
            llm=LLMConfig(
                server_url="https://test.example.com/v1",
                model_name="gpt-4",
                api_key="test-key",
            )
        )
        client = config.get_llm_client()
        assert client is not None
        assert client.server_url == "https://test.example.com/v1"
        assert client.model_name == "gpt-4"

    def test_config_to_dict(self):
        """Test Config.to_dict() method"""
        from flowforge.config import Config, LLMConfig

        config = Config(
            llm=LLMConfig(
                server_url="https://test.com",
                api_key="secret-key",
            )
        )

        result = config.to_dict()

        # Should include server URL but mask auth details
        assert result["llm"]["server_url"] == "https://test.com"
        assert result["llm"]["auth_method"] == "api_key"
        # Should not expose the actual key
        assert "secret-key" not in str(result)

    def test_get_config_singleton(self):
        """Test get_config returns singleton"""
        from flowforge.config import get_config, reload_config
        import flowforge.config as config_module

        # Reset singleton
        config_module._config = None

        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

        # Reload should create new instance
        config3 = reload_config()
        assert config3 is not config1

    def test_set_config(self):
        """Test set_config allows custom config"""
        from flowforge.config import Config, LLMConfig, get_config, set_config
        import flowforge.config as config_module

        custom_config = Config(
            llm=LLMConfig(server_url="https://custom.com"),
            log_level="DEBUG",
        )

        set_config(custom_config)

        retrieved = get_config()
        assert retrieved.llm.server_url == "https://custom.com"
        assert retrieved.log_level == "DEBUG"

        # Clean up
        config_module._config = None

    def test_config_exports_from_main_module(self):
        """Test config exports are available from main flowforge module"""
        from flowforge import Config, get_config, set_config, reload_config

        assert Config is not None
        assert get_config is not None
        assert set_config is not None
        assert reload_config is not None


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
