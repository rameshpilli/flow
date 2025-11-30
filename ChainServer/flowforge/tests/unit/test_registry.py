"""
Unit Tests for FlowForge Registry Module

Tests for:
- BaseRegistry: Common registration functionality
- AgentRegistry: Agent registration and discovery
- StepRegistry: Step registration and dependencies
- ChainRegistry: Chain registration
- Isolated registries for test isolation
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from flowforge.core.registry import (
    AgentRegistry,
    AgentSpec,
    BaseRegistry,
    ChainRegistry,
    ChainSpec,
    ComponentMetadata,
    ComponentStatus,
    RetryConfig,
    StepRegistry,
    StepSpec,
    create_isolated_registries,
    get_agent_registry,
    get_chain_registry,
    get_step_registry,
    reset_global_registries,
)


# ══════════════════════════════════════════════════════════════════════════════
#                           BaseRegistry Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestBaseRegistry:
    """Tests for BaseRegistry class."""

    def test_register_and_get(self):
        """Test basic registration and retrieval."""
        registry = BaseRegistry()

        registry.register("my_component", {"data": "value"})

        result = registry.get("my_component")
        assert result == {"data": "value"}

    def test_name_normalization(self):
        """Test component name normalization."""
        registry = BaseRegistry()

        registry.register("My-Component", {"data": 1})

        # All forms should resolve to the same component
        assert registry.get("My-Component") == {"data": 1}
        assert registry.get("my_component") == {"data": 1}
        assert registry.get("MY_COMPONENT") == {"data": 1}

    def test_aliases(self):
        """Test component aliases."""
        registry = BaseRegistry()

        registry.register(
            "primary_name",
            {"data": "value"},
            aliases=["alias1", "alias2"],
        )

        assert registry.get("primary_name") == {"data": "value"}
        assert registry.get("alias1") == {"data": "value"}
        assert registry.get("alias2") == {"data": "value"}

    def test_has(self):
        """Test checking if component exists."""
        registry = BaseRegistry()

        registry.register("exists", {})

        assert registry.has("exists") is True
        assert registry.has("missing") is False

    def test_list(self):
        """Test listing all components."""
        registry = BaseRegistry()

        registry.register("a", {})
        registry.register("b", {})
        registry.register("c", {})

        components = registry.list()
        assert set(components) == {"a", "b", "c"}

    def test_remove(self):
        """Test removing a component."""
        registry = BaseRegistry()

        registry.register("to_remove", {})
        assert registry.has("to_remove") is True

        result = registry.remove("to_remove")
        assert result is True
        assert registry.has("to_remove") is False

        # Remove non-existent
        result = registry.remove("missing")
        assert result is False

    def test_remove_clears_aliases(self):
        """Test removing a component also removes its aliases."""
        registry = BaseRegistry()

        registry.register("main", {}, aliases=["alias"])
        assert registry.has("alias") is True

        registry.remove("main")
        assert registry.has("alias") is False

    def test_clear(self):
        """Test clearing all registrations."""
        registry = BaseRegistry()

        registry.register("a", {})
        registry.register("b", {})
        registry.register("c", {}, aliases=["c_alias"])

        registry.clear()

        assert registry.list() == []
        assert registry.has("a") is False
        assert registry.has("c_alias") is False

    def test_strict_registration(self):
        """Test strict registration prevents overwrite."""
        registry = BaseRegistry()

        registry.register("component", {"v": 1}, strict=True)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("component", {"v": 2}, strict=True)

    def test_overwrite_without_strict(self):
        """Test registration overwrites without strict mode."""
        registry = BaseRegistry()

        registry.register("component", {"v": 1})
        registry.register("component", {"v": 2})

        assert registry.get("component") == {"v": 2}


# ══════════════════════════════════════════════════════════════════════════════
#                           AgentRegistry Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestAgentRegistry:
    """Tests for AgentRegistry class."""

    def test_register_agent(self):
        """Test agent registration."""
        registry = AgentRegistry()

        class MyAgent:
            pass

        registry.register_agent(
            name="my_agent",
            agent_class=MyAgent,
            version="1.0.0",
            description="Test agent",
            capabilities=["search", "fetch"],
        )

        spec = registry.get_spec("my_agent")
        assert spec is not None
        assert spec.metadata.name == "my_agent"
        assert spec.metadata.version == "1.0.0"
        assert spec.metadata.description == "Test agent"
        assert spec.capabilities == ["search", "fetch"]

    def test_get_agent_instance(self):
        """Test getting agent instance."""
        registry = AgentRegistry()

        class Counter:
            def __init__(self):
                self.count = 0

        registry.register_agent("counter", Counter)

        # Get instance
        instance1 = registry.get_agent("counter")
        instance1.count = 5

        # Same instance returned (singleton behavior)
        instance2 = registry.get_agent("counter")
        assert instance2.count == 5
        assert instance1 is instance2

    def test_get_agent_with_kwargs(self):
        """Test getting agent instance with init kwargs."""
        registry = AgentRegistry()

        class Configurable:
            def __init__(self, config_value: str = "default"):
                self.config_value = config_value

        registry.register_agent("configurable", Configurable)

        instance = registry.get_agent("configurable", config_value="custom")
        assert instance.config_value == "custom"

    def test_get_missing_agent(self):
        """Test getting non-existent agent returns None."""
        registry = AgentRegistry()

        assert registry.get_agent("missing") is None
        assert registry.get_spec("missing") is None

    def test_agent_with_group(self):
        """Test agent registration with group."""
        registry = AgentRegistry()

        class DataAgent:
            pass

        registry.register_agent(
            "data_agent",
            DataAgent,
            group="financial",
        )

        spec = registry.get_spec("data_agent")
        assert spec.metadata.group == "financial"


# ══════════════════════════════════════════════════════════════════════════════
#                           StepRegistry Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestStepRegistry:
    """Tests for StepRegistry class."""

    def test_register_step(self):
        """Test step registration."""
        registry = StepRegistry()

        async def my_step(ctx):
            return {"result": "ok"}

        registry.register_step(
            name="my_step",
            handler=my_step,
            description="Test step",
            timeout_ms=5000,
        )

        spec = registry.get_spec("my_step")
        assert spec is not None
        assert spec.metadata.name == "my_step"
        assert spec.handler is my_step
        assert spec.timeout_ms == 5000
        assert spec.is_async is True

    def test_register_sync_step(self):
        """Test registering a sync step handler."""
        registry = StepRegistry()

        def sync_step(ctx):
            return {"sync": True}

        registry.register_step("sync_step", sync_step)

        spec = registry.get_spec("sync_step")
        assert spec.is_async is False

    def test_step_dependencies(self):
        """Test step with dependencies."""
        registry = StepRegistry()

        async def dependent_step(ctx):
            return {}

        registry.register_step(
            "dependent",
            dependent_step,
            dependencies=["dep1", "dep2", "dep3"],
        )

        spec = registry.get_spec("dependent")
        assert spec.dependencies == ["dep1", "dep2", "dep3"]

        deps = registry.get_dependencies("dependent")
        assert deps == ["dep1", "dep2", "dep3"]

    def test_step_produces(self):
        """Test step with produces declaration."""
        registry = StepRegistry()

        async def producer(ctx):
            return {}

        registry.register_step(
            "producer",
            producer,
            produces=["output_a", "output_b"],
        )

        spec = registry.get_spec("producer")
        assert spec.produces == ["output_a", "output_b"]

    def test_step_resources(self):
        """Test step with resource dependencies."""
        registry = StepRegistry()

        async def step_with_resources(ctx, db, cache):
            return {}

        registry.register_step(
            "resource_step",
            step_with_resources,
            resources=["db", "cache"],
        )

        spec = registry.get_spec("resource_step")
        assert spec.resources == ["db", "cache"]

    def test_step_retry_config(self):
        """Test step with retry configuration."""
        registry = StepRegistry()

        async def flaky_step(ctx):
            return {}

        registry.register_step(
            "flaky",
            flaky_step,
            retry_count=3,
            retry_delay_ms=500,
            retry_backoff=2.0,
            retry_max_delay_ms=10000,
        )

        spec = registry.get_spec("flaky")
        assert spec.retry_config.count == 3
        assert spec.retry_config.delay_ms == 500
        assert spec.retry_config.backoff_multiplier == 2.0
        assert spec.retry_config.max_delay_ms == 10000

    def test_step_retry_config_object(self):
        """Test step with RetryConfig object."""
        registry = StepRegistry()

        async def step(ctx):
            return {}

        config = RetryConfig(
            count=5,
            delay_ms=1000,
            backoff_multiplier=1.5,
        )

        registry.register_step("step", step, retry_config=config)

        spec = registry.get_spec("step")
        assert spec.retry_config.count == 5

    def test_step_max_concurrency(self):
        """Test step with max_concurrency limit."""
        registry = StepRegistry()

        async def limited_step(ctx):
            return {}

        registry.register_step(
            "limited",
            limited_step,
            max_concurrency=2,
        )

        spec = registry.get_spec("limited")
        assert spec.max_concurrency == 2

    def test_step_input_output_models(self):
        """Test step with input/output validation models."""
        registry = StepRegistry()

        from pydantic import BaseModel

        class InputModel(BaseModel):
            query: str

        class OutputModel(BaseModel):
            result: str

        async def validated_step(ctx):
            return OutputModel(result="ok")

        registry.register_step(
            "validated",
            validated_step,
            input_model=InputModel,
            output_model=OutputModel,
            input_key="request",
            validate_output=True,
        )

        spec = registry.get_spec("validated")
        assert spec.input_model is InputModel
        assert spec.output_model is OutputModel
        assert spec.input_key == "request"
        assert spec.validate_output is True

    def test_get_handler(self):
        """Test getting step handler."""
        registry = StepRegistry()

        async def my_handler(ctx):
            return "result"

        registry.register_step("step", my_handler)

        handler = registry.get_handler("step")
        assert handler is my_handler

        assert registry.get_handler("missing") is None


# ══════════════════════════════════════════════════════════════════════════════
#                           ChainRegistry Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestChainRegistry:
    """Tests for ChainRegistry class."""

    def test_register_chain(self):
        """Test chain registration."""
        registry = ChainRegistry()

        registry.register_chain(
            name="my_chain",
            steps=["step1", "step2", "step3"],
            description="Test chain",
        )

        spec = registry.get_spec("my_chain")
        assert spec is not None
        assert spec.metadata.name == "my_chain"
        assert spec.steps == ["step1", "step2", "step3"]

    def test_chain_with_class(self):
        """Test chain registration with class reference."""
        registry = ChainRegistry()

        class MyChain:
            steps = ["a", "b", "c"]

        registry.register_chain(
            name="class_chain",
            steps=["a", "b", "c"],
            chain_class=MyChain,
        )

        spec = registry.get_spec("class_chain")
        assert spec.chain_class is MyChain

    def test_chain_parallel_groups(self):
        """Test chain with explicit parallel groups."""
        registry = ChainRegistry()

        registry.register_chain(
            name="parallel_chain",
            steps=["a", "b", "c", "d"],
            parallel_groups=[["a", "b"], ["c"], ["d"]],
        )

        spec = registry.get_spec("parallel_chain")
        assert spec.parallel_groups == [["a", "b"], ["c"], ["d"]]

    def test_chain_error_handling(self):
        """Test chain with error handling mode."""
        registry = ChainRegistry()

        registry.register_chain(
            name="continue_chain",
            steps=["a", "b"],
            error_handling="continue",
        )

        spec = registry.get_spec("continue_chain")
        assert spec.error_handling == "continue"

    def test_get_steps(self):
        """Test getting chain steps."""
        registry = ChainRegistry()

        registry.register_chain("chain", ["s1", "s2", "s3"])

        steps = registry.get_steps("chain")
        assert steps == ["s1", "s2", "s3"]

        assert registry.get_steps("missing") == []


# ══════════════════════════════════════════════════════════════════════════════
#                           ComponentMetadata Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestComponentMetadata:
    """Tests for ComponentMetadata dataclass."""

    def test_default_values(self):
        """Test default metadata values."""
        meta = ComponentMetadata(name="test")

        assert meta.name == "test"
        assert meta.version == "1.0.0"
        assert meta.description == ""
        assert meta.author == ""
        assert meta.group == ""
        assert meta.tags == []
        assert meta.status == ComponentStatus.ACTIVE
        assert meta.config == {}
        assert meta.registered_at is not None

    def test_custom_values(self):
        """Test custom metadata values."""
        meta = ComponentMetadata(
            name="custom",
            version="2.0.0",
            description="Custom component",
            author="Test Author",
            group="test_group",
            tags=["tag1", "tag2"],
            status=ComponentStatus.DEPRECATED,
            config={"key": "value"},
        )

        assert meta.version == "2.0.0"
        assert meta.description == "Custom component"
        assert meta.tags == ["tag1", "tag2"]
        assert meta.status == ComponentStatus.DEPRECATED


# ══════════════════════════════════════════════════════════════════════════════
#                           RetryConfig Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self):
        """Test default retry configuration."""
        config = RetryConfig()

        assert config.count == 0
        assert config.delay_ms == 1000
        assert config.backoff_multiplier == 1.0
        assert config.max_delay_ms == 30000

    def test_custom_values(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            count=5,
            delay_ms=500,
            backoff_multiplier=2.0,
            max_delay_ms=60000,
        )

        assert config.count == 5
        assert config.delay_ms == 500
        assert config.backoff_multiplier == 2.0
        assert config.max_delay_ms == 60000


# ══════════════════════════════════════════════════════════════════════════════
#                           Isolated Registries Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestIsolatedRegistries:
    """Tests for isolated registry functionality."""

    def test_create_isolated_registries(self):
        """Test creating isolated registries."""
        agent_reg, step_reg, chain_reg = create_isolated_registries()

        # Should be new instances
        assert agent_reg is not get_agent_registry()
        assert step_reg is not get_step_registry()
        assert chain_reg is not get_chain_registry()

    def test_isolated_registries_are_independent(self):
        """Test isolated registries don't affect global."""
        agent_reg, step_reg, chain_reg = create_isolated_registries()

        # Register in isolated registry
        async def isolated_step(ctx):
            return {}

        step_reg.register_step("isolated_step", isolated_step)

        # Should not be in global registry
        assert get_step_registry().get_spec("isolated_step") is None

    def test_reset_global_registries(self):
        """Test resetting global registries."""
        # Register something in global
        async def global_step(ctx):
            return {}

        get_step_registry().register_step("global_step", global_step)
        assert get_step_registry().has("global_step")

        # Reset
        reset_global_registries()

        # Should be cleared
        assert not get_step_registry().has("global_step")


# ══════════════════════════════════════════════════════════════════════════════
#                           Thread Safety Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestRegistryThreadSafety:
    """Tests for registry thread safety."""

    def test_concurrent_registration(self):
        """Test concurrent registration is safe."""
        registry = StepRegistry()
        errors = []

        def register_steps(prefix: str, count: int):
            try:
                for i in range(count):
                    async def handler(ctx):
                        return {}

                    registry.register_step(f"{prefix}_{i}", handler)
            except Exception as e:
                errors.append(e)

        # Run concurrent registrations
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(register_steps, f"thread_{t}", 50)
                for t in range(4)
            ]
            for f in futures:
                f.result()

        # Should have all registrations
        assert len(errors) == 0
        assert len(registry.list()) == 200  # 4 threads x 50 each

    def test_concurrent_get(self):
        """Test concurrent get operations are safe."""
        registry = StepRegistry()

        # Pre-populate
        for i in range(100):
            async def handler(ctx):
                return {}

            registry.register_step(f"step_{i}", handler)

        results = []
        errors = []

        def get_steps(count: int):
            try:
                for i in range(count):
                    spec = registry.get_spec(f"step_{i % 100}")
                    if spec:
                        results.append(spec.metadata.name)
            except Exception as e:
                errors.append(e)

        # Run concurrent gets
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(get_steps, 100)
                for _ in range(4)
            ]
            for f in futures:
                f.result()

        assert len(errors) == 0
        assert len(results) == 400  # 4 threads x 100 each


# ══════════════════════════════════════════════════════════════════════════════
#                           Component Status Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestComponentStatus:
    """Tests for component status filtering."""

    def test_list_by_status(self):
        """Test listing components by status."""
        registry = AgentRegistry()

        class Agent1:
            pass

        class Agent2:
            pass

        class Agent3:
            pass

        registry.register_agent("active_agent", Agent1)
        registry.register_agent("deprecated_agent", Agent2)
        registry.register_agent("disabled_agent", Agent3)

        # Update statuses
        registry.get_spec("deprecated_agent").metadata.status = ComponentStatus.DEPRECATED
        registry.get_spec("disabled_agent").metadata.status = ComponentStatus.DISABLED

        active = registry.list(status=ComponentStatus.ACTIVE)
        deprecated = registry.list(status=ComponentStatus.DEPRECATED)
        disabled = registry.list(status=ComponentStatus.DISABLED)

        assert "active_agent" in active
        assert "deprecated_agent" in deprecated
        assert "disabled_agent" in disabled
