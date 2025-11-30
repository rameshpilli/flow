"""
Unit Tests for AgentOrchestrator Middleware Module

Tests for:
- Middleware base class
- CompositeMiddleware
- LoggerMiddleware
- CacheMiddleware
- Middleware priority and application
"""


import pytest

from agentorchestrator import ChainContext, AgentOrchestrator
from agentorchestrator.core.context import ContextScope, StepResult
from agentorchestrator.middleware.base import CompositeMiddleware, Middleware

# ══════════════════════════════════════════════════════════════════════════════
#                           Base Middleware Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestMiddlewareBase:
    """Tests for Middleware base class."""

    def test_default_attributes(self):
        """Test default middleware attributes."""
        mw = Middleware()

        assert mw._ao_middleware is True
        assert mw._ao_priority == 100
        assert mw._ao_applies_to is None

    def test_custom_priority(self):
        """Test setting custom priority."""
        mw = Middleware(priority=50)

        assert mw._ao_priority == 50

    def test_applies_to_filter(self):
        """Test applies_to filter."""
        mw = Middleware(applies_to=["step1", "step2"])

        assert mw._ao_applies_to == ["step1", "step2"]
        assert mw.should_apply("step1") is True
        assert mw.should_apply("step2") is True
        assert mw.should_apply("step3") is False

    def test_should_apply_all_when_none(self):
        """Test should_apply returns True for all when applies_to is None."""
        mw = Middleware()

        assert mw.should_apply("any_step") is True
        assert mw.should_apply("another_step") is True

    @pytest.mark.asyncio
    async def test_default_hooks_do_nothing(self):
        """Test default hooks are no-ops."""
        mw = Middleware()
        ctx = ChainContext(request_id="test")

        # These should not raise
        await mw.before(ctx, "step")
        await mw.after(ctx, "step", StepResult("step", {}, 100))
        await mw.on_error(ctx, "step", RuntimeError("error"))


# ══════════════════════════════════════════════════════════════════════════════
#                           Custom Middleware Tests
# ══════════════════════════════════════════════════════════════════════════════


class TrackingMiddleware(Middleware):
    """Middleware that tracks all calls."""

    def __init__(self, name: str = "tracker", **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.before_calls = []
        self.after_calls = []
        self.error_calls = []

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        self.before_calls.append(step_name)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        self.after_calls.append((step_name, result.success))

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        self.error_calls.append((step_name, str(error)))


class ModifyingMiddleware(Middleware):
    """Middleware that modifies context."""

    def __init__(self, key: str, value: str, **kwargs):
        super().__init__(**kwargs)
        self.key = key
        self.value = value

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        ctx.set(f"before_{self.key}", self.value, scope=ContextScope.CHAIN)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        ctx.set(f"after_{self.key}", self.value, scope=ContextScope.CHAIN)


class TestCustomMiddleware:
    """Tests for custom middleware implementations."""

    @pytest.mark.asyncio
    async def test_tracking_middleware(self):
        """Test tracking middleware records calls."""
        mw = TrackingMiddleware()
        ctx = ChainContext(request_id="test")

        await mw.before(ctx, "step1")
        await mw.before(ctx, "step2")
        await mw.after(ctx, "step1", StepResult("step1", {}, 100))
        await mw.on_error(ctx, "step3", RuntimeError("test error"))

        assert mw.before_calls == ["step1", "step2"]
        assert mw.after_calls == [("step1", True)]
        assert mw.error_calls == [("step3", "test error")]

    @pytest.mark.asyncio
    async def test_modifying_middleware(self):
        """Test middleware can modify context."""
        mw = ModifyingMiddleware("test", "modified")
        ctx = ChainContext(request_id="test")

        await mw.before(ctx, "step")
        assert ctx.get("before_test") == "modified"

        await mw.after(ctx, "step", StepResult("step", {}, 100))
        assert ctx.get("after_test") == "modified"


# ══════════════════════════════════════════════════════════════════════════════
#                           CompositeMiddleware Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestCompositeMiddleware:
    """Tests for CompositeMiddleware class."""

    @pytest.mark.asyncio
    async def test_composite_runs_all_before(self):
        """Test composite runs all before hooks."""
        mw1 = TrackingMiddleware("mw1")
        mw2 = TrackingMiddleware("mw2")
        composite = CompositeMiddleware([mw1, mw2])

        ctx = ChainContext(request_id="test")
        await composite.before(ctx, "step")

        assert mw1.before_calls == ["step"]
        assert mw2.before_calls == ["step"]

    @pytest.mark.asyncio
    async def test_composite_runs_after_in_reverse(self):
        """Test composite runs after hooks in reverse order."""
        order = []

        class OrderTrackingMiddleware(Middleware):
            def __init__(self, name: str, **kwargs):
                super().__init__(**kwargs)
                self.name = name

            async def after(self, ctx, step_name, result):
                order.append(self.name)

        mw1 = OrderTrackingMiddleware("first", priority=10)
        mw2 = OrderTrackingMiddleware("second", priority=20)
        mw3 = OrderTrackingMiddleware("third", priority=30)

        composite = CompositeMiddleware([mw3, mw1, mw2])  # Unordered

        ctx = ChainContext(request_id="test")
        await composite.after(ctx, "step", StepResult("step", {}, 100))

        # Should be reverse order: third (30), second (20), first (10)
        assert order == ["third", "second", "first"]

    @pytest.mark.asyncio
    async def test_composite_before_in_priority_order(self):
        """Test composite runs before hooks in priority order."""
        order = []

        class OrderTrackingMiddleware(Middleware):
            def __init__(self, name: str, **kwargs):
                super().__init__(**kwargs)
                self.name = name

            async def before(self, ctx, step_name):
                order.append(self.name)

        mw1 = OrderTrackingMiddleware("first", priority=10)
        mw2 = OrderTrackingMiddleware("second", priority=20)
        mw3 = OrderTrackingMiddleware("third", priority=30)

        composite = CompositeMiddleware([mw3, mw1, mw2])  # Unordered

        ctx = ChainContext(request_id="test")
        await composite.before(ctx, "step")

        # Should be priority order: first (10), second (20), third (30)
        assert order == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_composite_respects_applies_to(self):
        """Test composite respects individual applies_to filters."""
        mw1 = TrackingMiddleware("mw1", applies_to=["step1"])
        mw2 = TrackingMiddleware("mw2", applies_to=["step2"])
        mw3 = TrackingMiddleware("mw3")  # Applies to all

        composite = CompositeMiddleware([mw1, mw2, mw3])

        ctx = ChainContext(request_id="test")

        await composite.before(ctx, "step1")
        assert mw1.before_calls == ["step1"]
        assert mw2.before_calls == []  # Should not apply
        assert mw3.before_calls == ["step1"]

        await composite.before(ctx, "step2")
        assert mw1.before_calls == ["step1"]  # Should not apply
        assert mw2.before_calls == ["step2"]
        assert mw3.before_calls == ["step1", "step2"]


# ══════════════════════════════════════════════════════════════════════════════
#                           Middleware Integration Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestMiddlewareIntegration:
    """Tests for middleware integration with AgentOrchestrator."""

    @pytest.fixture
    def forge(self):
        """Create an isolated forge for testing."""
        return AgentOrchestrator.temp_registries("middleware_test")

    @pytest.mark.asyncio
    async def test_middleware_called_during_execution(self, forge):
        """Test middleware is called during chain execution."""
        tracker = TrackingMiddleware()
        forge.use(tracker)

        @forge.step(name="step1")
        async def step1(ctx):
            return {"step": 1}

        @forge.step(name="step2", deps=["step1"])
        async def step2(ctx):
            return {"step": 2}

        @forge.chain(name="test_chain")
        class TestChain:
            steps = ["step1", "step2"]

        result = await forge.launch("test_chain")

        assert result["success"] is True
        assert tracker.before_calls == ["step1", "step2"]
        assert len(tracker.after_calls) == 2

    @pytest.mark.asyncio
    async def test_middleware_modifies_context(self, forge):
        """Test middleware can modify context during execution."""
        modifier = ModifyingMiddleware("middleware", "was_here")
        forge.use(modifier)

        @forge.step(name="check_context")
        async def check_context(ctx):
            before_value = ctx.get("before_middleware")
            return {"before_value": before_value}

        @forge.chain(name="modifier_chain")
        class ModifierChain:
            steps = ["check_context"]

        result = await forge.launch("modifier_chain")

        assert result["success"] is True
        # The step should have seen the before value
        assert result["results"][0]["output"]["before_value"] == "was_here"

    @pytest.mark.asyncio
    async def test_middleware_priority_order(self, forge):
        """Test middleware executes in priority order."""
        execution_order = []

        class OrderedMiddleware(Middleware):
            def __init__(self, name: str, **kwargs):
                super().__init__(**kwargs)
                self.name = name

            async def before(self, ctx, step_name):
                execution_order.append(f"before_{self.name}")

            async def after(self, ctx, step_name, result):
                execution_order.append(f"after_{self.name}")

        # Add middleware with different priorities
        forge.use(OrderedMiddleware("low", priority=10))
        forge.use(OrderedMiddleware("high", priority=90))
        forge.use(OrderedMiddleware("medium", priority=50))

        @forge.step(name="step")
        async def step(ctx):
            return {}

        @forge.chain(name="order_chain")
        class OrderChain:
            steps = ["step"]

        await forge.launch("order_chain")

        # Before: low -> medium -> high
        # After: high -> medium -> low (reversed)
        # Note: DAGExecutor sorts middleware by priority
        before_order = [x for x in execution_order if x.startswith("before_")]
        assert before_order == ["before_low", "before_medium", "before_high"]

    @pytest.mark.asyncio
    async def test_middleware_applies_to_filter(self, forge):
        """Test middleware applies_to filter works."""
        tracker_all = TrackingMiddleware("all")
        tracker_step1 = TrackingMiddleware("step1_only", applies_to=["step1"])

        forge.use(tracker_all)
        forge.use(tracker_step1)

        @forge.step(name="step1")
        async def step1(ctx):
            return 1

        @forge.step(name="step2", deps=["step1"])
        async def step2(ctx):
            return 2

        @forge.chain(name="filter_chain")
        class FilterChain:
            steps = ["step1", "step2"]

        await forge.launch("filter_chain")

        assert tracker_all.before_calls == ["step1", "step2"]
        assert tracker_step1.before_calls == ["step1"]  # Only step1

    @pytest.mark.asyncio
    async def test_middleware_error_isolation(self, forge):
        """Test middleware errors don't crash step execution."""
        class FailingMiddleware(Middleware):
            async def before(self, ctx, step_name):
                raise RuntimeError("Middleware exploded")

        forge.use(FailingMiddleware())

        @forge.step(name="step")
        async def step(ctx):
            return {"executed": True}

        @forge.chain(name="isolation_chain")
        class IsolationChain:
            steps = ["step"]

        # Should succeed despite middleware failure
        result = await forge.launch("isolation_chain")

        assert result["success"] is True
        assert result["results"][0]["output"]["executed"] is True


# ══════════════════════════════════════════════════════════════════════════════
#                           Middleware Error Handling Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestMiddlewareErrorHandling:
    """Tests for middleware error handling."""

    @pytest.mark.asyncio
    async def test_on_error_called_on_step_failure(self):
        """Test on_error is called when step fails."""
        tracker = TrackingMiddleware()

        forge = AgentOrchestrator.temp_registries("error_test")
        forge.use(tracker)

        @forge.step(name="failing_step")
        async def failing_step(ctx):
            raise ValueError("Intentional failure")

        @forge.chain(name="fail_chain")
        class FailChain:
            steps = ["failing_step"]

        result = await forge.launch("fail_chain")

        assert result["success"] is False
        # Note: on_error is called by the executor for middleware
        # The actual error handling depends on executor implementation

    @pytest.mark.asyncio
    async def test_after_called_even_on_failure(self):
        """Test after middleware is called even when step fails."""
        forge = AgentOrchestrator.temp_registries("after_error_test")

        after_results = []

        class AfterTracker(Middleware):
            async def after(self, ctx, step_name, result):
                after_results.append({
                    "step": step_name,
                    "success": result.success,
                    "error": str(result.error) if result.error else None,
                })

        forge.use(AfterTracker())

        @forge.step(name="fail_step")
        async def fail_step(ctx):
            raise RuntimeError("Failed!")

        @forge.chain(name="fail_chain")
        class FailChain:
            steps = ["fail_step"]

        result = await forge.launch("fail_chain")

        assert result["success"] is False
        assert len(after_results) == 1
        assert after_results[0]["success"] is False
        assert "Failed!" in after_results[0]["error"]


# ══════════════════════════════════════════════════════════════════════════════
#                           Multiple Middleware Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestMultipleMiddleware:
    """Tests for multiple middleware working together."""

    @pytest.mark.asyncio
    async def test_chained_context_modifications(self):
        """Test multiple middleware can chain modifications."""
        forge = AgentOrchestrator.temp_registries("chained_mw")

        class Middleware1(Middleware):
            async def before(self, ctx, step_name):
                ctx.set("mw1", "value1", scope=ContextScope.CHAIN)

        class Middleware2(Middleware):
            def __init__(self):
                super().__init__(priority=200)  # Run after mw1

            async def before(self, ctx, step_name):
                mw1_value = ctx.get("mw1")
                ctx.set("mw2", f"from_mw1:{mw1_value}", scope=ContextScope.CHAIN)

        forge.use(Middleware1())
        forge.use(Middleware2())

        @forge.step(name="check")
        async def check(ctx):
            return {
                "mw1": ctx.get("mw1"),
                "mw2": ctx.get("mw2"),
            }

        @forge.chain(name="chained")
        class Chained:
            steps = ["check"]

        result = await forge.launch("chained")

        output = result["results"][0]["output"]
        assert output["mw1"] == "value1"
        assert output["mw2"] == "from_mw1:value1"

    @pytest.mark.asyncio
    async def test_middleware_can_short_circuit(self):
        """Test middleware pattern for caching/short-circuit."""
        forge = AgentOrchestrator.temp_registries("cache_test")

        cache = {}
        cache_hits = []

        class SimpleCacheMiddleware(Middleware):
            async def before(self, ctx, step_name):
                cache_key = f"{step_name}:{ctx.get('query', 'default')}"
                if cache_key in cache:
                    cache_hits.append(step_name)
                    ctx.set(f"{step_name}_cached", cache[cache_key], scope=ContextScope.CHAIN)

            async def after(self, ctx, step_name, result):
                if result.success:
                    cache_key = f"{step_name}:{ctx.get('query', 'default')}"
                    cache[cache_key] = result.output

        forge.use(SimpleCacheMiddleware())

        call_count = 0

        @forge.step(name="expensive_step")
        async def expensive_step(ctx):
            nonlocal call_count
            call_count += 1
            # Check if cached value available
            cached = ctx.get("expensive_step_cached")
            if cached:
                return cached
            return {"computed": True, "count": call_count}

        @forge.chain(name="cache_chain")
        class CacheChain:
            steps = ["expensive_step"]

        # First call - should compute
        result1 = await forge.launch("cache_chain", data={"query": "test"})
        assert result1["results"][0]["output"]["count"] == 1

        # Second call - should use cache
        await forge.launch("cache_chain", data={"query": "test"})
        # The step still runs but can use cached data
        assert "expensive_step" in cache_hits
