"""
FlowForge Main Class

A DAG-based Chain Orchestration Framework inspired by Dagster patterns.
Provides decorator-driven registration, dependency resolution, and execution.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from flowforge.core.context import ChainContext, ContextManager, ContextScope
from flowforge.core.dag import ChainRunner, DAGExecutor, DebugCallback
from flowforge.core.run_store import (
    FileRunStore,
    InMemoryRunStore,
    ResumableChainRunner,
    RunCheckpoint,
    RunStore,
)
from flowforge.core.registry import (
    AgentRegistry,
    ChainRegistry,
    StepRegistry,
    create_isolated_registries,
    get_agent_registry,
    get_chain_registry,
    get_step_registry,
)
from flowforge.core.resources import (
    Resource,
    ResourceManager,
    ResourceScope,
    get_resource_manager,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FlowForge",
    "Definitions",
    "Context",
    "get_forge",
    "set_forge",
]

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class Definitions:
    """
    Container for FlowForge definitions (similar to Dagster's Definitions).

    Holds all registered agents, steps, chains, and resources.
    """

    def __init__(
        self,
        agents: list[Any] | None = None,
        steps: list[Any] | None = None,
        chains: list[Any] | None = None,
        resources: dict[str, Any] | None = None,
    ):
        self.agents = agents or []
        self.steps = steps or []
        self.chains = chains or []
        self.resources = resources or {}


class FlowForge:
    """
    FlowForge: A DAG-based Chain Orchestration Framework

    Inspired by Dagster's clean API patterns. Provides:
    - @fg.step() - Define processing steps (like @asset)
    - @fg.agent() - Define data agents (like resources)
    - @fg.chain() - Define execution chains (like @job)

    Usage:
        import flowforge as fg

        # Define an agent
        @fg.agent
        class NewsAgent:
            async def fetch(self, query: str) -> dict: ...

        # Define steps with dependencies via 'deps' parameter
        @fg.step
        def extract_company(ctx: fg.Context) -> dict: ...

        @fg.step(deps=[extract_company])
        def fetch_data(ctx: fg.Context) -> dict: ...

        # Define a chain
        @fg.chain
        class MeetingPrepChain:
            steps = [extract_company, fetch_data]

        # Validate & Run
        fg.check()                    # Validate definitions
        fg.list_defs()                # List all definitions
        await fg.launch("my_chain")   # Execute chain
    """

    def __init__(
        self,
        name: str = "flowforge",
        version: str = "1.0.0",
        max_parallel: int = 10,
        default_timeout_ms: int = 30000,
        *,
        isolated: bool = True,  # Default to isolated to prevent state bleed
        agent_registry: AgentRegistry | None = None,
        step_registry: StepRegistry | None = None,
        chain_registry: ChainRegistry | None = None,
        # Resumability support
        run_store: RunStore | None = None,
        checkpoint_dir: str | None = None,
    ):
        """
        Initialize a FlowForge instance.

        Args:
            name: Name of this FlowForge instance
            version: Version string
            max_parallel: Maximum concurrent steps (enforced via semaphore)
            default_timeout_ms: Default timeout for steps in milliseconds
            isolated: If True (default), create isolated registries (prevents state bleed)
            agent_registry: Custom agent registry (overrides isolated flag)
            step_registry: Custom step registry (overrides isolated flag)
            chain_registry: Custom chain registry (overrides isolated flag)
            run_store: Custom run store for checkpointing (overrides checkpoint_dir)
            checkpoint_dir: Directory for file-based checkpoints (default: in-memory)

        Example:
            # Use isolated registries (default, prevents state bleed)
            forge = FlowForge()

            # Use global shared registries (for backward compatibility)
            forge = FlowForge(isolated=False)

            # Use custom registries
            from flowforge.core.registry import create_isolated_registries
            a, s, c = create_isolated_registries()
            forge = FlowForge(agent_registry=a, step_registry=s, chain_registry=c)

            # Context manager for temporary registries
            with FlowForge.temp_registries() as forge:
                @forge.step
                def temp_step(ctx): ...
        """
        self.name = name
        self.version = version
        self._isolated = isolated

        # Registries - support isolated mode for testing
        if agent_registry or step_registry or chain_registry:
            # Custom registries provided
            self._agent_registry = agent_registry or AgentRegistry()
            self._step_registry = step_registry or StepRegistry()
            self._chain_registry = chain_registry or ChainRegistry()
        elif isolated:
            # Create isolated registries
            self._agent_registry, self._step_registry, self._chain_registry = (
                create_isolated_registries()
            )
        else:
            # Use global shared registries (default)
            self._agent_registry = get_agent_registry()
            self._step_registry = get_step_registry()
            self._chain_registry = get_chain_registry()

        # Executor & Runner
        self._executor = DAGExecutor(
            max_parallel=max_parallel,
            default_timeout_ms=default_timeout_ms,
        )
        # Pass registries to executor for proper isolation
        self._executor.builder.step_registry = self._step_registry
        self._executor.builder.chain_registry = self._chain_registry

        self._runner = ChainRunner(executor=self._executor)

        # Middleware & Resources
        self._middleware: list[Any] = []
        self._resource_manager = ResourceManager() if isolated else get_resource_manager()
        self._context_manager = ContextManager()

        # Run Store for Resumability
        if run_store:
            self._run_store = run_store
        elif checkpoint_dir:
            self._run_store = FileRunStore(checkpoint_dir)
        else:
            self._run_store = InMemoryRunStore()

        # Create resumable runner using our executor
        self._resumable_runner = ResumableChainRunner(
            store=self._run_store,
            executor=self._executor,
            auto_checkpoint=True,
        )

        logger.info(f"FlowForge initialized: {name} v{version} (isolated={isolated})")

    # ══════════════════════════════════════════════════════════════════
    #                    CONTEXT MANAGERS
    # ══════════════════════════════════════════════════════════════════

    @classmethod
    def temp_registries(cls, name: str = "temp", **kwargs) -> "FlowForge":
        """
        Create a FlowForge instance with temporary isolated registries.

        Use as a context manager for temporary definitions that are
        automatically cleaned up.

        Usage:
            with FlowForge.temp_registries() as forge:
                @forge.step
                def my_step(ctx): ...

                result = await forge.launch("my_chain")
            # Registries automatically cleared after block
        """
        return cls(name=name, isolated=True, **kwargs)

    def __enter__(self) -> "FlowForge":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Exit context manager with resource cleanup.

        Note: For sync context manager, we attempt to run async cleanup
        in a new event loop. For better cleanup guarantees, use the
        async context manager (async with).
        """
        try:
            self._cleanup_resources_sync()
        except Exception as e:
            logger.warning(f"Error during resource cleanup: {e}")
        finally:
            if self._isolated:
                self.clear()

    def _cleanup_resources_sync(self, timeout_seconds: float = 30.0) -> None:
        """
        Synchronously cleanup resources with timeout.

        Args:
            timeout_seconds: Maximum time to wait for cleanup (default 30s)
        """
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - use ensure_future for safer scheduling
            asyncio.ensure_future(self.cleanup_resources(timeout_seconds))
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            try:
                asyncio.run(self.cleanup_resources(timeout_seconds))
            except Exception as e:
                logger.warning(f"Failed to cleanup resources: {e}")

    async def __aenter__(self) -> "FlowForge":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Async context manager exit with proper resource cleanup.

        This ensures all managed resources (DB connections, HTTP clients, etc.)
        are properly cleaned up when exiting the context, preventing:
        - Memory leaks from unclosed connections
        - Connection pool exhaustion
        - File handle leaks
        """
        try:
            await self.cleanup_resources(timeout_seconds=30.0)
        except asyncio.TimeoutError:
            logger.warning("Resource cleanup timed out, some resources may not be cleaned")
        except Exception as e:
            logger.warning(f"Error during resource cleanup: {e}")
        finally:
            if self._isolated:
                self.clear()

    # ══════════════════════════════════════════════════════════════════
    #                         DECORATORS
    # ══════════════════════════════════════════════════════════════════

    def agent(
        self,
        cls: type[T] | None = None,
        *,
        name: str | None = None,
        description: str = "",
        group: str | None = None,
    ) -> type[T] | Callable[[type[T]], type[T]]:
        """
        Register a data agent (similar to Dagster's resource).

        Usage:
            @fg.agent
            class NewsAgent:
                async def fetch(self, query: str) -> dict: ...

            @fg.agent(name="sec_agent", group="financial")
            class SECFilingAgent:
                async def fetch(self, query: str) -> dict: ...
        """

        def decorator(cls: type[T]) -> type[T]:
            agent_name = name or cls.__name__
            self._agent_registry.register_agent(
                name=agent_name,
                agent_class=cls,
                description=description,
                group=group,
            )
            cls._fg_name = agent_name
            cls._fg_type = "agent"
            return cls

        if cls is not None:
            return decorator(cls)
        return decorator

    def step(
        self,
        func: F | None = None,
        *,
        name: str | None = None,
        deps: list[Any] | None = None,
        dependencies: list[Any] | None = None,  # Alias for deps
        produces: list[str] | None = None,
        resources: list[str] | None = None,
        description: str = "",
        group: str | None = None,
        timeout_ms: int = 30000,
        retry: int = 0,
        max_concurrency: int | None = None,
        input_model: type | None = None,
        output_model: type | None = None,
        input_key: str | None = None,
        validate_output: bool = True,
    ) -> F | Callable[[F], F]:
        """
        Register a chain step (similar to Dagster's @asset).

        Dependencies can be specified via:
        1. deps parameter (list of step functions or names)
        2. Function parameters (automatic resolution)

        Resources can be injected via the 'resources' parameter.

        Input/Output Contracts:
        - input_model: Pydantic model to validate input data (fail-fast on bad payloads)
        - output_model: Pydantic model to validate step output
        - input_key: Context key to validate (default: "request")
        - validate_output: Whether to validate output (default: True)

        Usage:
            @fg.step
            async def extract_company(ctx): ...

            @fg.step(deps=[extract_company], produces=["company_data"])
            async def process_data(ctx): ...

            # Or with group
            @fg.step(group="context_builder")
            async def build_context(ctx): ...

            # Limit concurrency for rate-limited APIs
            @fg.step(max_concurrency=2)
            async def call_external_api(ctx): ...

            # With resource injection
            @fg.step(resources=["db", "llm"])
            async def fetch_data(ctx, db, llm):
                # db and llm are automatically injected
                data = await db.query("...")
                summary = await llm.generate("...")

            # With input/output contracts (fail-fast validation)
            @fg.step(
                input_model=ChainRequest,
                output_model=ContextBuilderOutput,
                input_key="request",
            )
            async def context_builder(ctx) -> ContextBuilderOutput:
                request = ctx.get("request")  # Already validated as ChainRequest
                # ... process ...
                return output  # Validated against ContextBuilderOutput
        """
        resource_manager = self._resource_manager

        # Support both 'deps' and 'dependencies' (alias)
        effective_deps = deps or dependencies

        def decorator(func: F) -> F:
            step_name = name or func.__name__

            # Resolve dependencies - can be functions or strings
            resolved_deps = []
            if effective_deps:
                for dep in effective_deps:
                    if callable(dep) and hasattr(dep, "_fg_name"):
                        resolved_deps.append(dep._fg_name)
                    elif isinstance(dep, str):
                        resolved_deps.append(dep)
                    else:
                        resolved_deps.append(str(dep))

            # Wrap handler to inject resources
            if resources:
                original_func = func
                is_async = asyncio.iscoroutinefunction(original_func)

                if is_async:
                    async def wrapped_handler(ctx: ChainContext) -> Any:
                        # Inject resources
                        injected = {}
                        for res_name in resources:
                            injected[res_name] = await resource_manager.get(res_name)
                        return await original_func(ctx, **injected)
                else:
                    def wrapped_handler(ctx: ChainContext) -> Any:
                        # Inject resources (sync)
                        injected = {}
                        for res_name in resources:
                            injected[res_name] = resource_manager.get_sync(res_name)
                        return original_func(ctx, **injected)

                wrapped_handler.__name__ = original_func.__name__
                wrapped_handler.__doc__ = original_func.__doc__
                handler = wrapped_handler
            else:
                handler = func

            # Register step with dedicated fields (no more overloading retry_config)
            self._step_registry.register_step(
                name=step_name,
                handler=handler,
                dependencies=resolved_deps,
                produces=produces,
                resources=resources,  # Dedicated resources field
                description=description,
                group=group,
                timeout_ms=timeout_ms,
                retry_count=retry,  # Explicit retry count
                max_concurrency=max_concurrency,  # Dedicated concurrency field
                input_model=input_model,  # Input contract
                output_model=output_model,  # Output contract
                input_key=input_key,  # Key to validate
                validate_output=validate_output,  # Whether to validate output
            )
            func._fg_name = step_name
            func._fg_type = "step"
            func._fg_deps = resolved_deps
            func._fg_produces = produces or []
            func._fg_resources = resources or []
            func._fg_input_model = input_model
            func._fg_output_model = output_model
            return func

        if func is not None:
            return decorator(func)
        return decorator

    def chain(
        self,
        cls: type[T] | None = None,
        *,
        name: str | None = None,
        description: str = "",
        group: str | None = None,
    ) -> type[T] | Callable[[type[T]], type[T]]:
        """
        Register a chain (similar to Dagster's @job).

        Supports chain composition - you can include other chains as steps,
        and they will be automatically expanded into wrapper steps that
        execute the subchain.

        Usage:
            @fg.chain
            class MeetingPrepChain:
                steps = ["extract_company", "fetch_data", "build_response"]

            # Or with step functions directly
            @fg.chain
            class MyChain:
                steps = [extract_company, fetch_data]

            # Chain composition - include other chains as steps
            @fg.chain
            class ParentChain:
                steps = [
                    "preprocessing_step",
                    "child_chain",       # Another chain as a step
                    "postprocessing_step",
                ]
        """

        def decorator(cls: type[T]) -> type[T]:
            chain_name = name or cls.__name__

            # Resolve steps - can be functions, strings, or chain references
            raw_steps = getattr(cls, "steps", [])
            resolved_steps = []
            for s in raw_steps:
                if callable(s) and hasattr(s, "_fg_name"):
                    # Check if it's a chain or step
                    if getattr(s, "_fg_type", None) == "chain":
                        # It's a chain - create a wrapper step
                        subchain_name = s._fg_name
                        wrapper_step_name = self._create_subchain_step(
                            subchain_name, chain_name
                        )
                        resolved_steps.append(wrapper_step_name)
                    else:
                        resolved_steps.append(s._fg_name)
                elif isinstance(s, str):
                    # Check if string refers to a chain
                    if self._chain_registry.is_chain(s):
                        wrapper_step_name = self._create_subchain_step(s, chain_name)
                        resolved_steps.append(wrapper_step_name)
                    else:
                        resolved_steps.append(s)
                else:
                    resolved_steps.append(str(s))

            # Extract error_handling from class if defined
            error_handling = getattr(cls, "error_handling", "fail_fast")

            # Extract parallel_groups from class if defined
            parallel_groups = getattr(cls, "parallel_groups", None)

            self._chain_registry.register_chain(
                name=chain_name,
                steps=resolved_steps,
                description=description,
                group=group,
                error_handling=error_handling,
                parallel_groups=parallel_groups,
            )
            cls._fg_name = chain_name
            cls._fg_type = "chain"
            return cls

        if cls is not None:
            return decorator(cls)
        return decorator

    def _create_subchain_step(
        self,
        subchain_name: str,
        parent_chain_name: str,
    ) -> str:
        """
        Create a wrapper step that executes a subchain.

        This enables chain composition by wrapping chains as steps.

        Args:
            subchain_name: Name of the chain to execute as a step
            parent_chain_name: Name of the parent chain (for namespacing)

        Returns:
            Name of the created wrapper step
        """
        wrapper_step_name = f"__subchain__{subchain_name}"

        # Check if wrapper already exists
        if self._step_registry.has(wrapper_step_name):
            return wrapper_step_name

        # Capture forge reference for closure
        forge = self

        async def subchain_handler(ctx: ChainContext) -> dict[str, Any]:
            """
            Execute the subchain and merge results into parent context.

            The subchain receives a copy of the current context data and
            its outputs are merged back into the parent context.
            """
            # Prepare data for subchain - pass current context data
            subchain_data = {}
            for key in ctx.keys():
                subchain_data[key] = ctx.get(key)

            # Execute the subchain
            logger.info(f"Executing subchain '{subchain_name}' from parent '{parent_chain_name}'")
            result = await forge.launch(
                subchain_name,
                data=subchain_data,
                validate_input=False,  # Parent already validated
            )

            # Merge subchain context back into parent
            if result.get("success") and "context" in result:
                subchain_ctx_data = result["context"].get("data", {})
                for key, value in subchain_ctx_data.items():
                    # Don't overwrite keys that were in original context
                    if not ctx.has(key) or key not in subchain_data:
                        ctx.set(key, value, scope=ContextScope.CHAIN)

            # Store subchain result for reference
            ctx.set(
                f"_subchain_{subchain_name}_result",
                result,
                scope=ContextScope.CHAIN,
            )

            if not result.get("success"):
                error_info = result.get("error", {})
                error_msg = error_info.get("message", "Subchain failed") if isinstance(error_info, dict) else str(error_info)
                raise RuntimeError(f"Subchain '{subchain_name}' failed: {error_msg}")

            return {
                "subchain": subchain_name,
                "success": result["success"],
                "steps_executed": len(result.get("results", [])),
            }

        # Set name for debugging
        subchain_handler.__name__ = wrapper_step_name
        subchain_handler.__doc__ = f"Wrapper step that executes the '{subchain_name}' chain"

        # Register the wrapper step
        self._step_registry.register_step(
            name=wrapper_step_name,
            handler=subchain_handler,
            description=f"Executes subchain: {subchain_name}",
            group="__subchains__",
        )

        logger.debug(f"Created subchain wrapper step: {wrapper_step_name}")
        return wrapper_step_name

    def subchain(
        self,
        chain_name: str,
        *,
        deps: list[Any] | None = None,
        produces: list[str] | None = None,
    ) -> str:
        """
        Create a step that executes another chain (explicit subchain reference).

        Use this when you want to explicitly include a chain as a step with
        custom dependencies.

        Args:
            chain_name: Name of the chain to execute as a step
            deps: Dependencies for this subchain step
            produces: What this subchain produces

        Returns:
            Name of the wrapper step (for use in chain definitions)

        Usage:
            @fg.chain
            class ParentChain:
                steps = [
                    "setup_step",
                    fg.subchain("data_processing_chain", deps=["setup_step"]),
                    "finalize_step",
                ]

        Example with dependencies:
            # Define inner chain
            @fg.chain
            class DataProcessing:
                steps = ["fetch", "transform", "validate"]

            # Use in parent chain with explicit dependencies
            @fg.chain
            class Pipeline:
                steps = [
                    "init",
                    fg.subchain("DataProcessing", deps=["init"]),
                    "report",
                ]
        """
        if not self._chain_registry.is_chain(chain_name):
            raise ValueError(f"Chain '{chain_name}' not found. Register it first.")

        # Create the wrapper step
        wrapper_name = self._create_subchain_step(chain_name, "__explicit__")

        # Update dependencies if provided
        if deps:
            spec = self._step_registry.get_spec(wrapper_name)
            if spec:
                resolved_deps = []
                for dep in deps:
                    if callable(dep) and hasattr(dep, "_fg_name"):
                        resolved_deps.append(dep._fg_name)
                    elif isinstance(dep, str):
                        resolved_deps.append(dep)
                    else:
                        resolved_deps.append(str(dep))
                spec.dependencies = resolved_deps

        # Update produces if provided
        if produces:
            spec = self._step_registry.get_spec(wrapper_name)
            if spec:
                spec.produces = produces

        return wrapper_name

    # ══════════════════════════════════════════════════════════════════
    #                    PROGRAMMATIC REGISTRATION
    # ══════════════════════════════════════════════════════════════════

    def register_agent(
        self,
        name: str,
        agent_class: type,
        **kwargs,
    ) -> "FlowForge":
        """Programmatically register an agent"""
        self._agent_registry.register_agent(name=name, agent_class=agent_class, **kwargs)
        return self

    def register_step(
        self,
        name: str,
        handler: Callable,
        deps: list[str] | None = None,
        produces: list[str] | None = None,
        **kwargs,
    ) -> "FlowForge":
        """Programmatically register a step"""
        self._step_registry.register_step(
            name=name,
            handler=handler,
            dependencies=deps,
            produces=produces,
            **kwargs,
        )
        return self

    def register_chain(
        self,
        name: str,
        steps: list[str],
        **kwargs,
    ) -> "FlowForge":
        """Programmatically register a chain"""
        self._chain_registry.register_chain(name=name, steps=steps, **kwargs)
        return self

    def register_resource(
        self,
        name: str,
        resource: Any = None,
        *,
        factory: Callable[[], Any] | None = None,
        scope: ResourceScope = ResourceScope.SINGLETON,
        cleanup: Callable[[Any], Any] | None = None,
        dependencies: list[str] | None = None,
    ) -> "FlowForge":
        """
        Register a shared resource (config, clients, etc.).

        All resources are now managed through ResourceManager for unified
        lifecycle management.

        Usage:
            # Direct instance
            forge.register_resource("config", config_dict)

            # Factory with cleanup
            forge.register_resource(
                "db",
                factory=lambda: create_db_pool(),
                cleanup=lambda pool: pool.close(),
            )

            # Async factory with dependencies
            forge.register_resource(
                "cache",
                factory=create_redis,
                cleanup=lambda c: c.close(),
                dependencies=["config"],
            )
        """
        if factory is not None:
            self._resource_manager.register(
                name=name,
                factory=factory,
                scope=scope,
                cleanup=cleanup,
                dependencies=dependencies,
            )
        else:
            # Direct instance - wrap in ResourceManager
            self._resource_manager.register(
                name=name,
                factory=resource,  # ResourceManager handles non-callable
                scope=scope,
                cleanup=cleanup,
                dependencies=dependencies,
            )

        return self

    def resource(
        self,
        name: str | None = None,
        scope: ResourceScope = ResourceScope.SINGLETON,
        cleanup: Callable[[Any], Any] | None = None,
        dependencies: list[str] | None = None,
    ) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
        """
        Decorator to register a factory function as a resource.

        Usage:
            @forge.resource("db", cleanup=lambda c: c.close())
            def create_db():
                return DatabasePool()

            @forge.resource("cache", dependencies=["config"])
            async def create_cache():
                config = await forge.get_resource_async("config")
                return Redis(config.redis_url)
        """
        def decorator(factory: Callable[[], Any]) -> Callable[[], Any]:
            resource_name = name or factory.__name__
            self._resource_manager.register(
                name=resource_name,
                factory=factory,
                scope=scope,
                cleanup=cleanup,
                dependencies=dependencies,
            )
            return factory
        return decorator

    def use(self, middleware: Any) -> "FlowForge":
        """Add middleware to the execution pipeline"""
        self._middleware.append(middleware)
        self._executor.add_middleware(middleware)
        return self

    # ══════════════════════════════════════════════════════════════════
    #                    DAGSTER-STYLE CLI COMMANDS
    # ══════════════════════════════════════════════════════════════════

    def check(self, chain_name: str | None = None) -> dict[str, Any]:
        """
        Validate definitions (like 'dg check defs').

        Checks:
        - All steps exist
        - Dependencies are resolvable
        - No circular dependencies
        - Chains are valid

        Usage:
            fg.check()                    # Check all
            fg.check("meeting_prep")      # Check specific chain
        """
        errors = []
        warnings = []
        chain_results = []

        chains_to_check = [chain_name] if chain_name else self.list_chains()

        if not chains_to_check:
            print("⚠ No chains registered")
            return {"valid": True, "chains": [], "errors": [], "warnings": ["No chains registered"]}

        print(f"\n{'═' * 60}")
        print(f"  FlowForge Check: {self.name} v{self.version}")
        print(f"{'═' * 60}\n")

        for cname in chains_to_check:
            result = self._check_chain(cname)
            chain_results.append(result)

            status = "✓" if result["valid"] else "✗"
            print(f"  {status} {cname}")

            # Show execution levels
            for level_idx, level in enumerate(result.get("levels", [])):
                is_parallel = len(level) > 1
                indent = "    "

                if is_parallel:
                    print(f"{indent}├─ [parallel]")
                    for step in level:
                        deps_str = f" ← {step['deps']}" if step.get("deps") else ""
                        prod_str = f" → {step['produces']}" if step.get("produces") else ""
                        print(f"{indent}│  • {step['name']}{deps_str}{prod_str}")
                else:
                    step = level[0]
                    deps_str = f" ← {step['deps']}" if step.get("deps") else ""
                    prod_str = f" → {step['produces']}" if step.get("produces") else ""
                    prefix = "├─" if level_idx < len(result.get("levels", [])) - 1 else "└─"
                    print(f"{indent}{prefix} {step['name']}{deps_str}{prod_str}")

            if result.get("errors"):
                errors.extend(result["errors"])
                for err in result["errors"]:
                    print(f"    ✗ {err}")

            print()

        valid = len(errors) == 0
        print(f"{'═' * 60}")
        print(f"  Result: {'✓ All checks passed' if valid else '✗ Errors found'}")
        print(
            f"  Agents: {len(self.list_agents())} | Steps: {len(self.list_steps())} | Chains: {len(self.list_chains())}"
        )
        print(f"{'═' * 60}\n")

        return {
            "valid": valid,
            "chains": chain_results,
            "errors": errors,
            "warnings": warnings,
        }

    def _check_chain(self, chain_name: str) -> dict[str, Any]:
        """Validate a single chain"""
        chain_spec = self._chain_registry.get_spec(chain_name)
        if not chain_spec:
            return {
                "name": chain_name,
                "valid": False,
                "errors": [f"Chain not found: {chain_name}"],
            }

        result = {"name": chain_name, "valid": True, "errors": [], "levels": []}

        # Build execution levels
        remaining = list(chain_spec.steps)
        placed = set()

        while remaining:
            level = []
            for step_name in remaining[:]:
                step_spec = self._step_registry.get_spec(step_name)
                if not step_spec:
                    result["errors"].append(f"Step not found: {step_name}")
                    remaining.remove(step_name)
                    continue

                deps = set(step_spec.dependencies) if step_spec.dependencies else set()

                # Check for missing dependencies
                missing = deps - placed - set(chain_spec.steps)
                if missing:
                    result["errors"].append(f"{step_name} requires missing: {missing}")

                if deps.issubset(placed) or not deps:
                    level.append(
                        {
                            "name": step_name,
                            "deps": list(deps) if deps else None,
                            "produces": step_spec.produces if step_spec.produces else None,
                        }
                    )
                    remaining.remove(step_name)

            if level:
                result["levels"].append(level)
                placed.update(s["name"] for s in level)
            elif remaining:
                for s in remaining:
                    result["errors"].append(f"Cannot resolve: {s} (circular dependency?)")
                break

        if result["errors"]:
            result["valid"] = False

        return result

    def list_defs(self) -> dict[str, list[str]]:
        """
        List all definitions (like 'dg list defs').

        Usage:
            fg.list_defs()
        """
        agents = self.list_agents()
        steps = self.list_steps()
        chains = self.list_chains()

        print(f"\n{'═' * 50}")
        print("  FlowForge Definitions")
        print(f"{'═' * 50}\n")

        if agents:
            print("  Agents:")
            for a in agents:
                print(f"    • {a}")
            print()

        if steps:
            print("  Steps:")
            for s in steps:
                spec = self._step_registry.get_spec(s)
                deps = f" ← {spec.dependencies}" if spec and spec.dependencies else ""
                print(f"    • {s}{deps}")
            print()

        if chains:
            print("  Chains:")
            for c in chains:
                spec = self._chain_registry.get_spec(c)
                step_count = len(spec.steps) if spec else 0
                print(f"    • {c} ({step_count} steps)")
            print()

        resources = self.list_resources()
        if resources:
            print("  Resources:")
            for r in resources:
                print(f"    • {r}")
            print()

        print(f"{'═' * 50}\n")

        return {"agents": agents, "steps": steps, "chains": chains}

    def graph(self, chain_name: str, format: str = "ascii") -> str:
        """
        Generate DAG visualization.

        Args:
            chain_name: Chain to visualize
            format: "ascii" or "mermaid"

        Usage:
            fg.graph("meeting_prep")              # ASCII
            fg.graph("meeting_prep", "mermaid")   # Mermaid.js
        """
        from flowforge.core.visualize import DAGVisualizer

        # Pass our registries to handle isolated forge instances
        viz = DAGVisualizer(
            step_registry=self._step_registry,
            chain_registry=self._chain_registry,
        )

        if format == "mermaid":
            output = viz.to_mermaid(chain_name)
        else:
            output = viz.to_ascii(chain_name)

        print(output)
        return output

    # ══════════════════════════════════════════════════════════════════
    #                         EXECUTION
    # ══════════════════════════════════════════════════════════════════

    async def launch(
        self,
        chain_name: str,
        data: dict[str, Any] | None = None,
        request_id: str | None = None,
        debug_callback: DebugCallback | None = None,
        validate_input: bool = True,
    ) -> dict[str, Any]:
        """
        Execute a chain (like 'dg launch').

        Args:
            chain_name: Name of the chain to execute
            data: Initial context data
            request_id: Optional request ID for tracing
            debug_callback: Optional callback invoked after each step for debugging.
                            Receives (ctx, step_name, result_dict) arguments.
                            Useful for CLI debug mode and per-step context snapshots.
            validate_input: If True (default), validate input against chain's
                           input_model before execution starts (fail-fast).

        Usage:
            result = await fg.launch("meeting_prep", {"company": "Apple"})

            # With debug callback
            def on_step(ctx, step_name, result):
                print(f"Step {step_name}: {result}")
            result = await fg.launch("meeting_prep", data, debug_callback=on_step)

        Raises:
            ContractValidationError: If validate_input=True and input fails validation
        """
        # Chain-level input validation (fail-fast)
        if validate_input and data is not None:
            data = self._validate_chain_input(chain_name, data)

        return await self._runner.run(
            chain_name=chain_name,
            initial_data=data,
            request_id=request_id,
            debug_callback=debug_callback,
        )

    def _validate_chain_input(
        self,
        chain_name: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate chain input data before execution starts.

        Checks for input_model on:
        1. The chain definition itself
        2. The first step in the chain

        Returns:
            Validated data (possibly with validated model instances)

        Raises:
            ContractValidationError: If validation fails
        """
        from flowforge.core.validation import validate_chain_input, is_pydantic_model

        # Get chain spec
        chain_spec = self._chain_registry.get_spec(chain_name)
        if not chain_spec:
            return data  # No chain spec, skip validation

        # Check for chain-level input_model
        chain_input_model = getattr(chain_spec, "input_model", None)
        chain_input_key = getattr(chain_spec, "input_key", "request")

        if is_pydantic_model(chain_input_model):
            logger.debug(f"Validating chain '{chain_name}' input against {chain_input_model.__name__}")
            first_step = chain_spec.steps[0] if chain_spec.steps else chain_name
            first_step_name = first_step if isinstance(first_step, str) else getattr(first_step, "_fg_name", str(first_step))
            return validate_chain_input(
                chain_name=chain_name,
                first_step_name=first_step_name,
                input_model=chain_input_model,
                initial_data=data,
                input_key=chain_input_key,
            )

        # Check first step for input_model
        if chain_spec.steps:
            first_step = chain_spec.steps[0]
            first_step_name = first_step if isinstance(first_step, str) else getattr(first_step, "_fg_name", str(first_step))
            step_spec = self._step_registry.get_spec(first_step_name)

            if step_spec:
                step_input_model = getattr(step_spec, "input_model", None)
                step_input_key = getattr(step_spec, "input_key", "request")

                if is_pydantic_model(step_input_model):
                    logger.debug(f"Validating step '{first_step_name}' input against {step_input_model.__name__}")
                    return validate_chain_input(
                        chain_name=chain_name,
                        first_step_name=first_step_name,
                        input_model=step_input_model,
                        initial_data=data,
                        input_key=step_input_key,
                    )

        return data  # No validation configured

    def launch_sync(
        self,
        chain_name: str,
        data: dict[str, Any] | None = None,
        request_id: str | None = None,
        *,
        cleanup: bool = True,
    ) -> dict[str, Any]:
        """
        Synchronous wrapper for launch() with proper resource cleanup.

        Args:
            chain_name: Name of the chain to execute
            data: Initial context data
            request_id: Optional request ID for tracing
            cleanup: If True (default), cleanup resources after execution.
                     Set to False if you plan to run multiple chains and
                     cleanup manually later.

        Note:
            This method creates a new event loop via asyncio.run().
            Resources are automatically cleaned up after execution to prevent
            memory leaks and connection exhaustion.
        """
        async def _run_with_cleanup():
            try:
                return await self.launch(chain_name, data, request_id)
            finally:
                if cleanup:
                    await self.cleanup_resources()

        return asyncio.run(_run_with_cleanup())

    # Aliases for backward compatibility
    async def run(
        self,
        chain_name: str,
        initial_data: dict[str, Any] | None = None,
        debug_callback: DebugCallback | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Alias for launch() - backward compatibility"""
        return await self.launch(
            chain_name, initial_data, debug_callback=debug_callback, **kwargs
        )

    def run_sync(
        self,
        chain_name: str,
        initial_data: dict[str, Any] | None = None,
        cleanup: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        """Alias for launch_sync() - backward compatibility"""
        return self.launch_sync(chain_name, initial_data, cleanup=cleanup, **kwargs)

    # ══════════════════════════════════════════════════════════════════
    #                    RESUMABILITY
    # ══════════════════════════════════════════════════════════════════

    async def launch_resumable(
        self,
        chain_name: str,
        data: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a chain with automatic checkpointing for resumability.

        If the chain fails partway through, you can resume it later using
        resume() or retry_failed().

        Args:
            chain_name: Name of the chain to execute
            data: Initial context data
            run_id: Optional run ID (auto-generated if not provided)

        Returns:
            Result dict containing:
            - run_id: ID for resuming this run
            - success: Whether chain completed successfully
            - status: "completed", "partial", or "failed"
            - checkpoint: Full checkpoint data

        Usage:
            # Run with checkpointing
            result = await forge.launch_resumable("my_chain", {"company": "Apple"})

            # If it fails, resume later
            result = await forge.resume(result["run_id"])
        """
        return await self._resumable_runner.run(
            chain_name=chain_name,
            initial_data=data,
            run_id=run_id,
        )

    async def resume(
        self,
        run_id: str,
        skip_completed: bool = True,
    ) -> dict[str, Any]:
        """
        Resume a failed or partial chain run.

        Loads the checkpoint from run_store and continues execution
        from where it left off.

        Args:
            run_id: ID of the run to resume
            skip_completed: If True, skip steps that already completed

        Returns:
            Result dict with updated checkpoint

        Usage:
            # Resume a failed run
            result = await forge.resume("run_abc123")
        """
        return await self._resumable_runner.resume(
            run_id=run_id,
            skip_completed=skip_completed,
        )

    async def retry_failed(self, run_id: str) -> dict[str, Any]:
        """
        Re-run only the failed steps from a previous run.

        Args:
            run_id: ID of the run with failed steps

        Returns:
            Result dict with updated checkpoint
        """
        return await self._resumable_runner.retry_failed(run_id)

    async def get_partial_output(self, run_id: str) -> dict[str, Any]:
        """
        Get partial outputs from a failed or incomplete run.

        Useful for retrieving results from steps that completed
        before a failure.

        Args:
            run_id: ID of the run

        Returns:
            Dict with outputs from completed steps
        """
        return await self._resumable_runner.get_partial_output(run_id)

    async def list_resumable_runs(
        self,
        chain_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List runs that can be resumed.

        Args:
            chain_name: Filter by chain name (optional)

        Returns:
            List of resumable run summaries
        """
        return await self._resumable_runner.list_resumable(chain_name)

    async def get_run(self, run_id: str) -> RunCheckpoint | None:
        """
        Get a run checkpoint by ID.

        Args:
            run_id: ID of the run

        Returns:
            RunCheckpoint or None if not found
        """
        return await self._run_store.load_checkpoint(run_id)

    async def list_runs(
        self,
        chain_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[RunCheckpoint]:
        """
        List run checkpoints with optional filters.

        Args:
            chain_name: Filter by chain name
            status: Filter by status ("completed", "failed", "partial")
            limit: Maximum number of runs to return

        Returns:
            List of RunCheckpoint objects
        """
        return await self._run_store.list_runs(
            chain_name=chain_name,
            status=status,
            limit=limit,
        )

    async def delete_run(self, run_id: str) -> bool:
        """
        Delete a run checkpoint.

        Args:
            run_id: ID of the run to delete

        Returns:
            True if deleted, False if not found
        """
        return await self._run_store.delete_checkpoint(run_id)

    # ══════════════════════════════════════════════════════════════════
    #                         DISCOVERY
    # ══════════════════════════════════════════════════════════════════

    def list_agents(self) -> list[str]:
        """List all registered agents"""
        return self._agent_registry.list()

    def list_steps(self) -> list[str]:
        """List all registered steps"""
        return self._step_registry.list()

    def list_chains(self) -> list[str]:
        """List all registered chains"""
        return self._chain_registry.list()

    def get_agent(self, name: str, **kwargs) -> Any:
        """Get an agent instance"""
        return self._agent_registry.get_agent(name, **kwargs)

    def get_resource(self, name: str) -> Any:
        """
        Get a registered resource (sync version).

        For resources with factories, this triggers lazy initialization.
        """
        return self._resource_manager.get_sync(name)

    async def get_resource_async(self, name: str) -> Any:
        """
        Get a registered resource (async version).

        For resources with factories, this triggers lazy initialization.
        """
        return await self._resource_manager.get(name)

    def has_resource(self, name: str) -> bool:
        """Check if a resource is registered"""
        return self._resource_manager.has(name)

    def list_resources(self) -> list[str]:
        """List all registered resources"""
        return self._resource_manager.list_resources()

    async def cleanup_resources(self, timeout_seconds: float = 30.0) -> None:
        """
        Cleanup all managed resources with timeout.

        Args:
            timeout_seconds: Maximum time to wait for cleanup (default 30s)

        Raises:
            asyncio.TimeoutError: If cleanup exceeds timeout
        """
        try:
            await asyncio.wait_for(
                self._resource_manager.cleanup_all(),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.error(f"Resource cleanup timed out after {timeout_seconds}s")
            raise

    # ══════════════════════════════════════════════════════════════════
    #                         CONTEXT
    # ══════════════════════════════════════════════════════════════════

    def create_context(
        self,
        request_id: str,
        data: dict[str, Any] | None = None,
    ) -> ChainContext:
        """Create a new chain context"""
        return self._context_manager.create_context(request_id, data)

    def get_context(self, request_id: str) -> ChainContext | None:
        """Get an existing context"""
        return self._context_manager.get_context(request_id)

    # ══════════════════════════════════════════════════════════════════
    #                         UTILITIES
    # ══════════════════════════════════════════════════════════════════

    def clear(self) -> None:
        """Clear all registrations"""
        self._agent_registry.clear()
        self._step_registry.clear()
        self._chain_registry.clear()
        self._resource_manager.clear()

    # Legacy alias
    def clear_registrations(self) -> None:
        """Alias for clear() - backward compatibility"""
        self.clear()

    # Legacy method - kept for backward compatibility
    def validate(
        self,
        chain_name: str | None = None,
        output: str = "ascii",
        print_output: bool = True,
    ) -> dict[str, Any]:
        """
        Legacy validate method - use check() instead.

        Kept for backward compatibility.
        """
        if output == "mermaid":
            if chain_name:
                self.graph(chain_name, "mermaid")
        return self.check(chain_name)

    def __repr__(self) -> str:
        return (
            f"FlowForge(name={self.name!r}, "
            f"agents={len(self.list_agents())}, "
            f"steps={len(self.list_steps())}, "
            f"chains={len(self.list_chains())})"
        )


# ══════════════════════════════════════════════════════════════════════════════
#                           MODULE-LEVEL API
# ══════════════════════════════════════════════════════════════════════════════

_default_forge: FlowForge | None = None


def get_forge() -> FlowForge:
    """Get or create the default FlowForge instance"""
    global _default_forge
    if _default_forge is None:
        _default_forge = FlowForge()
    return _default_forge


def set_forge(forge: FlowForge) -> None:
    """Set the default FlowForge instance"""
    global _default_forge
    _default_forge = forge


# Convenience type alias
Context = ChainContext
