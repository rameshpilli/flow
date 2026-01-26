"""
AgentOrchestrator Main Class
============================

This module provides the main AgentOrchestrator class - a DAG-based Chain
Orchestration Framework inspired by Dagster patterns.

AgentOrchestrator is the central class for defining, validating, and executing
chains of steps. It provides decorator-driven registration, dependency resolution,
parallel execution, and comprehensive lifecycle management.

Classes:
    Definitions: Container for AgentOrchestrator definitions (agents, steps, chains).
    AgentOrchestrator: Main orchestrator class with all registration and execution methods.

Functions:
    get_orchestrator: Get or create the default global orchestrator instance.
    set_orchestrator: Set the default global orchestrator instance.

Usage:
    import agentorchestrator as ao

    # Define an agent
    @ao.agent
    class NewsAgent:
        async def fetch(self, query: str) -> dict: ...

    # Define steps with dependencies
    @ao.step
    async def extract_company(ctx):
        return {"company": "Apple"}

    @ao.step(deps=[extract_company])
    async def fetch_data(ctx):
        return {"data": [...]}

    # Define and run a chain
    @ao.chain
    class MyChain:
        steps = [extract_company, fetch_data]

    result = await ao.launch("MyChain", {"query": "Apple"})

Example:
    >>> from agentorchestrator import AgentOrchestrator
    >>>
    >>> # Create isolated orchestrator instance
    >>> ao = AgentOrchestrator(name="my_app", isolated=True)
    >>>
    >>> # Register components
    >>> @ao.step
    ... async def my_step(ctx):
    ...     return {"result": "success"}
    >>>
    >>> @ao.chain
    ... class MyChain:
    ...     steps = [my_step]
    >>>
    >>> # Validate and visualize
    >>> ao.check()  # Validate all definitions
    >>> ao.graph("MyChain")  # ASCII DAG visualization
    >>>
    >>> # Execute
    >>> result = await ao.launch("MyChain", {"input": "data"})
    >>> print(result["success"])  # True

See Also:
    - agentorchestrator.core.context: ChainContext for step data flow.
    - agentorchestrator.core.decorators: Module-level decorator functions.
    - agentorchestrator.agents.base: Base classes for agents.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from agentorchestrator.core.context import ChainContext, ContextManager, ContextScope
from agentorchestrator.core.dag import ChainRunner, DAGExecutor, DebugCallback
from agentorchestrator.core.event_bus import Event, EventBus, get_event_bus
from agentorchestrator.core.registry import (
    AgentRegistry,
    ChainRegistry,
    StepRegistry,
    create_isolated_registries,
    get_agent_registry,
    get_chain_registry,
    get_step_registry,
)
from agentorchestrator.core.resources import (
    ResourceManager,
    ResourceScope,
    get_resource_manager,
)
from agentorchestrator.core.run_store import (
    FileRunStore,
    InMemoryRunStore,
    ResumableChainRunner,
    RunCheckpoint,
    RunStore,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AgentOrchestrator",
    "Definitions",
    "Context",
    "get_orchestrator",
    "set_orchestrator",
]

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class Definitions:
    """
    Container for AgentOrchestrator definitions (similar to Dagster's Definitions).

    Holds all registered agents, steps, chains, and resources. Use this
    to bundle and organize definitions for deployment or testing.

    Attributes:
        agents (list[Any]): List of agent classes.
        steps (list[Any]): List of step functions.
        chains (list[Any]): List of chain classes.
        resources (dict[str, Any]): Dict of resource name to resource.

    Example:
        >>> defs = Definitions(
        ...     agents=[NewsAgent, SECAgent],
        ...     steps=[extract_company, fetch_data],
        ...     chains=[MyChain],
        ...     resources={"db": db_pool},
        ... )
    """

    def __init__(
        self,
        agents: list[Any] | None = None,
        steps: list[Any] | None = None,
        chains: list[Any] | None = None,
        resources: dict[str, Any] | None = None,
    ):
        """
        Initialize a Definitions container.

        Args:
            agents (list[Any] | None): List of agent classes.
            steps (list[Any] | None): List of step functions.
            chains (list[Any] | None): List of chain classes.
            resources (dict[str, Any] | None): Dict of resources.
        """
        self.agents = agents or []
        self.steps = steps or []
        self.chains = chains or []
        self.resources = resources or {}


class AgentOrchestrator:
    """
    AgentOrchestrator: A DAG-based Chain Orchestration Framework.

    Inspired by Dagster's clean API patterns, AgentOrchestrator provides
    a powerful yet simple way to define and execute chains of processing
    steps with dependency management, parallel execution, and resilience.

    Attributes:
        name (str): Name of this orchestrator instance.
        version (str): Version string for this instance.

    Core Decorators:
        agent(): Register a class as a data agent.
        step(): Register a function as a chain step.
        chain(): Register a class as an execution chain.

    Execution Methods:
        launch(): Execute a chain asynchronously.
        launch_sync(): Execute a chain synchronously.
        run_step(): Run a single step in isolation.
        launch_resumable(): Execute with checkpointing for resume.
        resume(): Resume a failed chain run.

    Validation Methods:
        check(): Validate all definitions and show DAG structure.
        list_defs(): List all registered definitions.
        graph(): Generate DAG visualization.

    Registration Methods:
        register_agent(): Programmatically register an agent.
        register_step(): Programmatically register a step.
        register_chain(): Programmatically register a chain.
        register_resource(): Register a shared resource.
        resource(): Decorator for resource factories.

    Discovery Methods:
        list_agents(): List all registered agents.
        list_steps(): List all registered steps.
        list_chains(): List all registered chains.
        list_resources(): List all registered resources.
        get_agent(): Get an agent instance by name.
        get_resource(): Get a resource by name.

    Lifecycle Methods:
        clear(): Clear all registrations.
        cleanup_resources(): Cleanup all managed resources.

    Example:
        >>> import agentorchestrator as ao
        >>>
        >>> # Define an agent
        >>> @ao.agent
        ... class NewsAgent:
        ...     async def fetch(self, query: str) -> dict:
        ...         return {"news": [...]}
        >>>
        >>> # Define steps with dependencies via 'deps' parameter
        >>> @ao.step
        ... def extract_company(ctx):
        ...     return {"company": ctx.get("query")}
        >>>
        >>> @ao.step(deps=[extract_company])
        ... def fetch_data(ctx):
        ...     company = ctx.get("company")
        ...     return {"data": [...]}
        >>>
        >>> # Define a chain
        >>> @ao.chain
        ... class MeetingPrepChain:
        ...     steps = [extract_company, fetch_data]
        >>>
        >>> # Validate & Run
        >>> ao.check()                    # Validate definitions
        >>> ao.list_defs()                # List all definitions
        >>> result = await ao.launch("MeetingPrepChain", {"query": "Apple"})

    Context Manager Usage:
        >>> async with AgentOrchestrator(isolated=True) as ao:
        ...     @ao.step
        ...     async def temp_step(ctx):
        ...         return {"result": "test"}
        ...
        ...     result = await ao.launch("TempChain")
        ... # Resources automatically cleaned up

    See Also:
        ChainContext: Context object passed to steps.
        agentorchestrator.agents.base: Base classes for agents.
        agentorchestrator.core.decorators: Module-level decorators.
    """

    def __init__(
        self,
        name: str = "agentorchestrator",
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
        event_bus: EventBus | None = None,
    ):
        """
        Initialize an AgentOrchestrator instance.

        Args:
            name (str): Name of this orchestrator instance. Used in logging
                and identification. Default: "agentorchestrator".
            version (str): Version string. Default: "1.0.0".
            max_parallel (int): Maximum concurrent steps during execution.
                Enforced via semaphore. Default: 10.
            default_timeout_ms (int): Default timeout for steps in milliseconds.
                Default: 30000 (30 seconds).
            isolated (bool): If True (default), create isolated registries.
                This prevents state bleed between tests or instances.
                Set to False to use global shared registries.
            agent_registry (AgentRegistry | None): Custom agent registry.
                Overrides the isolated flag if provided.
            step_registry (StepRegistry | None): Custom step registry.
                Overrides the isolated flag if provided.
            chain_registry (ChainRegistry | None): Custom chain registry.
                Overrides the isolated flag if provided.
            run_store (RunStore | None): Custom run store for checkpointing.
                Overrides checkpoint_dir if provided.
            checkpoint_dir (str | None): Directory for file-based checkpoints.
                If None, uses in-memory storage (lost on restart).

        Example:
            >>> # Default isolated instance (recommended)
            >>> ao = AgentOrchestrator()
            >>>
            >>> # Named instance with custom settings
            >>> ao = AgentOrchestrator(
            ...     name="my_app",
            ...     max_parallel=5,
            ...     default_timeout_ms=60000,
            ... )
            >>>
            >>> # Use global shared registries (for backward compatibility)
            >>> ao = AgentOrchestrator(isolated=False)
            >>>
            >>> # With file-based checkpointing for resumability
            >>> ao = AgentOrchestrator(checkpoint_dir="/tmp/checkpoints")
            >>>
            >>> # With custom registries for testing
            >>> from agentorchestrator.core.registry import create_isolated_registries
            >>> a, s, c = create_isolated_registries()
            >>> ao = AgentOrchestrator(
            ...     agent_registry=a,
            ...     step_registry=s,
            ...     chain_registry=c,
            ... )

        Note:
            Use `isolated=True` (default) for testing to prevent state bleed
            between test cases. Use `isolated=False` only when you need
            multiple orchestrator instances to share registrations.
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

        # Event bus (Redis-backed if available, otherwise in-memory)
        self._event_bus = event_bus or get_event_bus(prefer_redis=True)
        self._event_handlers: dict[str, list[Any]] = {}

        # Executor & Runner
        self._executor = DAGExecutor(
            max_parallel=max_parallel,
            default_timeout_ms=default_timeout_ms,
            event_bus=self._event_bus,
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

        logger.info(f"AgentOrchestrator initialized: {name} v{version} (isolated={isolated})")

    # ══════════════════════════════════════════════════════════════════
    #                    CONTEXT MANAGERS
    # ══════════════════════════════════════════════════════════════════

    @classmethod
    def temp_registries(cls, name: str = "temp", **kwargs) -> "AgentOrchestrator":
        """
        Create an AgentOrchestrator instance with temporary isolated registries.

        Use as a context manager for temporary definitions that are
        automatically cleaned up when exiting the context.

        Args:
            name (str): Name for the temporary instance. Default: "temp".
            **kwargs: Additional arguments passed to __init__.

        Returns:
            AgentOrchestrator: New instance with isolated registries.

        Example:
            >>> with AgentOrchestrator.temp_registries() as ao:
            ...     @ao.step
            ...     def my_step(ctx):
            ...         return {"result": "test"}
            ...
            ...     @ao.chain
            ...     class TestChain:
            ...         steps = [my_step]
            ...
            ...     result = ao.launch_sync("TestChain")
            ... # Registries automatically cleared after block
        """
        return cls(name=name, isolated=True, **kwargs)

    def __enter__(self) -> "AgentOrchestrator":
        """
        Enter context manager.

        Returns:
            AgentOrchestrator: This instance.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Exit context manager with resource cleanup.

        Cleans up managed resources and clears registries if isolated.

        Note:
            For sync context manager, async cleanup is attempted via
            new event loop. For better cleanup guarantees, use the
            async context manager (async with).

        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception value if an error occurred.
            exc_tb: Exception traceback if an error occurred.
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

        Handles both cases:
        - Called from sync context: uses asyncio.run()
        - Called from async context: schedules cleanup task

        Args:
            timeout_seconds (float): Maximum time to wait for cleanup.
                Default: 30.0 seconds.
        """
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - schedule the cleanup
            # Create a task and let it run (fire-and-forget in sync __exit__)
            # The async __aexit__ will properly await cleanup
            task = loop.create_task(self.cleanup_resources(timeout_seconds))
            # Add callback to log errors
            def _on_done(t):
                try:
                    t.result()
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"Background resource cleanup failed: {e}")
            task.add_done_callback(_on_done)
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            try:
                asyncio.run(self.cleanup_resources(timeout_seconds))
            except Exception as e:
                logger.warning(f"Failed to cleanup resources: {e}")

    async def __aenter__(self) -> "AgentOrchestrator":
        """
        Async context manager entry.

        Returns:
            AgentOrchestrator: This instance.
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Async context manager exit with proper resource cleanup.

        Ensures all managed resources (DB connections, HTTP clients, etc.)
        are properly cleaned up when exiting the context.

        This prevents:
        - Memory leaks from unclosed connections
        - Connection pool exhaustion
        - File handle leaks

        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception value if an error occurred.
            exc_tb: Exception traceback if an error occurred.
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
        resilient: bool = False,
        resilient_config: dict[str, Any] | None = None,
    ) -> type[T] | Callable[[type[T]], type[T]]:
        """
        Register a data agent (similar to Dagster's resource).

        Agents are responsible for fetching data from external sources.
        They can be wrapped with resilience (timeout, retry, circuit-breaker)
        for production use.

        Args:
            cls (type[T] | None): Agent class (auto-provided when used
                without parentheses).
            name (str | None): Custom agent name. Default: class name.
            description (str): Human-readable description.
            group (str | None): Group name for organization.
            resilient (bool): If True, auto-wrap instances in ResilientAgent.
                Default: False.
            resilient_config (dict[str, Any] | None): Config for ResilientAgent.
                Keys: timeout_seconds, max_retries, circuit_failure_threshold.

        Returns:
            type[T] | Callable[[type[T]], type[T]]: Decorated class or decorator.

        Example:
            >>> @ao.agent
            ... class NewsAgent:
            ...     async def fetch(self, query: str) -> dict:
            ...         return {"news": [...]}
            >>>
            >>> @ao.agent(name="sec_agent", group="financial")
            ... class SECFilingAgent:
            ...     async def fetch(self, query: str) -> dict:
            ...         return {"filings": [...]}
            >>>
            >>> @ao.agent(
            ...     name="earnings_agent",
            ...     resilient=True,
            ...     resilient_config={"timeout_seconds": 30.0, "max_retries": 2},
            ... )
            ... class EarningsAgent:
            ...     async def fetch(self, ticker: str) -> dict:
            ...         return {"earnings": {...}}

        See Also:
            get_agent(): Retrieve an agent instance by name.
            agentorchestrator.agents.base.BaseAgent: Base class for agents.
        """

        def decorator(cls: type[T]) -> type[T]:
            agent_name = name or cls.__name__
            self._agent_registry.register_agent(
                name=agent_name,
                agent_class=cls,
                description=description,
                group=group,
                resilient=resilient,
                resilient_config=resilient_config or {},
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
        state_model: type | None = None,
    ) -> F | Callable[[F], F]:
        """
        Register a chain step (similar to Dagster's @asset).

        Steps are the building blocks of chains. Each step receives a
        ChainContext and can read from or write to it.

        Args:
            func (F | None): Step function (auto-provided when used
                without parentheses).
            name (str | None): Custom step name. Default: function name.
            deps (list[Any] | None): Steps that must complete before this one.
                Can be step functions or string names.
            dependencies (list[Any] | None): Alias for deps (backward compat).
            produces (list[str] | None): Context keys this step produces.
            resources (list[str] | None): Resource names to inject as kwargs.
            description (str): Human-readable description.
            group (str | None): Step group for organization.
            timeout_ms (int): Execution timeout in milliseconds. Default: 30000.
            retry (int): Number of retries on failure. Default: 0.
            max_concurrency (int | None): Max parallel instances. None = unlimited.
            input_model (type | None): Pydantic model to validate input.
            output_model (type | None): Pydantic model to validate output.
            input_key (str | None): Context key to validate. Default: "request".
            validate_output (bool): Whether to validate output. Default: True.

        Returns:
            F | Callable[[F], F]: Decorated function or decorator.

        Example:
            >>> @ao.step
            ... async def extract_company(ctx):
            ...     return {"company": ctx.get("query")}
            >>>
            >>> @ao.step(deps=[extract_company], produces=["data"])
            ... async def fetch_data(ctx):
            ...     company = ctx.get("company")
            ...     return {"data": [...]}
            >>>
            >>> # With resource injection
            >>> @ao.step(resources=["db", "llm"])
            ... async def process_with_resources(ctx, db, llm):
            ...     data = await db.query("...")
            ...     summary = await llm.generate("...")
            ...     return {"summary": summary}
            >>>
            >>> # With input/output contracts (fail-fast validation)
            >>> from pydantic import BaseModel
            >>>
            >>> class RequestModel(BaseModel):
            ...     query: str
            ...     limit: int = 10
            >>>
            >>> @ao.step(input_model=RequestModel, input_key="request")
            ... async def validated_step(ctx):
            ...     request = ctx.get("request")  # Already validated
            ...     return {"result": request.query}

        See Also:
            chain(): Combine steps into chains.
            register_resource(): Register resources for injection.
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
            func._fg_state_model = state_model
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

        Chains define the execution order of steps. Supports chain composition
        where other chains can be included as steps.

        Args:
            cls (type[T] | None): Chain class (auto-provided when used
                without parentheses).
            name (str | None): Custom chain name. Default: class name.
            description (str): Human-readable description.
            group (str | None): Chain group for organization.

        Returns:
            type[T] | Callable[[type[T]], type[T]]: Decorated class or decorator.

        Example:
            >>> @ao.chain
            ... class MeetingPrepChain:
            ...     steps = ["extract_company", "fetch_data", "build_response"]
            >>>
            >>> # With step functions directly
            >>> @ao.chain
            ... class MyChain:
            ...     steps = [extract_company, fetch_data]
            >>>
            >>> # Chain composition - include other chains as steps
            >>> @ao.chain
            ... class ParentChain:
            ...     steps = [
            ...         "preprocessing_step",
            ...         "child_chain",  # Another chain as a step
            ...         "postprocessing_step",
            ...     ]
            >>>
            >>> # With error handling configuration
            >>> @ao.chain
            ... class ResilientChain:
            ...     steps = ["step1", "step2", "step3"]
            ...     error_handling = "continue"  # Continue on step failure

        Chain Class Attributes:
            steps (list): Required. List of step functions or names.
            error_handling (str): Optional. "fail_fast" or "continue".
            parallel_groups (list[list[str]]): Optional. Parallel step groups.

        See Also:
            launch(): Execute a registered chain.
            subchain(): Explicitly include a chain as a step.
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
        The subchain receives current context data and its outputs
        are merged back into the parent context.

        Args:
            subchain_name (str): Name of the chain to execute as a step.
            parent_chain_name (str): Name of the parent chain (for namespacing).

        Returns:
            str: Name of the created wrapper step.
        """
        wrapper_step_name = f"__subchain__{subchain_name}"

        # Check if wrapper already exists
        if self._step_registry.has(wrapper_step_name):
            return wrapper_step_name

        # Capture ao reference for closure
        ao = self

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
            result = await ao.launch(
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

        Use this when you want to explicitly include a chain as a step
        with custom dependencies.

        Args:
            chain_name (str): Name of the chain to execute as a step.
            deps (list[Any] | None): Dependencies for this subchain step.
            produces (list[str] | None): What this subchain produces.

        Returns:
            str: Name of the wrapper step (for use in chain definitions).

        Raises:
            ValueError: If the specified chain is not registered.

        Example:
            >>> @ao.chain
            ... class ParentChain:
            ...     steps = [
            ...         "setup_step",
            ...         ao.subchain("data_processing_chain", deps=["setup_step"]),
            ...         "finalize_step",
            ...     ]
            >>>
            >>> # Define inner chain first
            >>> @ao.chain
            ... class DataProcessing:
            ...     steps = ["fetch", "transform", "validate"]
            >>>
            >>> # Use in parent chain with explicit dependencies
            >>> @ao.chain
            ... class Pipeline:
            ...     steps = [
            ...         "init",
            ...         ao.subchain("DataProcessing", deps=["init"]),
            ...         "report",
            ...     ]
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
    #                         EVENT HANDLERS
    # ══════════════════════════════════════════════════════════════════

    def event_handler(
        self,
        events: str | list[str],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        Decorator to register an event handler for one or more event types.

        Handler signature:
            async def handler(ctx: ChainContext, event: Event) -> Event | list[Event] | None
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            event_list = [events] if isinstance(events, str) else list(events)
            for event_type in event_list:
                self._event_handlers.setdefault(event_type, []).append(func)
            return func

        return decorator

    async def emit_event(self, event: Event) -> None:
        """Publish a single event to the configured event bus."""
        if event.run_id is None:
            event.run_id = f"evt_{uuid.uuid4().hex[:8]}"
        await self._event_bus.publish(event)

    async def _dispatch_event(self, event: Event, ctx: ChainContext) -> None:
        """Invoke handlers for an incoming event and publish any emitted events."""
        handlers = self._event_handlers.get(event.type, [])
        for handler in handlers:
            result = handler(ctx, event)
            if asyncio.iscoroutine(result):
                result = await result
            if result:
                events = result if isinstance(result, list) else [result]
                for ev in events:
                    if isinstance(ev, Event):
                        if ev.run_id is None:
                            ev.run_id = event.run_id
                        await self._event_bus.publish(ev)

    async def run_event_loop(
        self,
        seed_events: list[Event] | None = None,
        *,
        max_events: int = 100,
        timeout_s: float = 30.0,
        run_id: str | None = None,
        stop_when: Callable[[Event, ChainContext], bool] | None = None,
        min_events: int = 0,
    ) -> dict[str, Any]:
        """
        Minimal event-driven runner. Publishes seed events and processes inbound
        events with registered handlers until:
        - stop_when returns True, or
        - processed >= max_events, or
        - timeout reached.
        """
        run_id = run_id or f"event_{uuid.uuid4().hex[:8]}"
        ctx = ChainContext(request_id=run_id)

        sub = self._event_bus.subscribe()

        # Publish seeds
        if seed_events:
            for ev in seed_events:
                if ev.run_id is None:
                    ev.run_id = run_id
                await self._event_bus.publish(ev)

        processed = 0
        start = time.time()

        try:
            while processed < max_events:
                remaining = timeout_s - (time.time() - start)
                if remaining <= 0:
                    break
                try:
                    event = await asyncio.wait_for(sub.__anext__(), timeout=remaining)
                except (asyncio.TimeoutError, StopAsyncIteration):
                    break

                processed += 1
                await self._dispatch_event(event, ctx)

                if stop_when and processed >= min_events:
                    try:
                        if stop_when(event, ctx):
                            break
                    except Exception:
                        # ignore predicate errors; keep running
                        pass
        finally:
            if hasattr(sub, "aclose"):
                try:
                    await sub.aclose()
                except Exception:
                    pass

        return {
            "run_id": run_id,
            "processed": processed,
            "handlers": {k: len(v) for k, v in self._event_handlers.items()},
            "duration_ms": (time.time() - start) * 1000,
        }

    # ══════════════════════════════════════════════════════════════════
    #                    PROGRAMMATIC REGISTRATION
    # ══════════════════════════════════════════════════════════════════

    def register_agent(
        self,
        name: str,
        agent_class: type,
        **kwargs,
    ) -> "AgentOrchestrator":
        """
        Programmatically register an agent.

        Args:
            name (str): Unique agent name.
            agent_class (type): The agent class to register.
            **kwargs: Additional registration options (description, group, etc.).

        Returns:
            AgentOrchestrator: Self for method chaining.

        Example:
            >>> ao.register_agent("news", NewsAgent, group="data")
        """
        self._agent_registry.register_agent(name=name, agent_class=agent_class, **kwargs)
        return self

    def register_step(
        self,
        name: str,
        handler: Callable,
        deps: list[str] | None = None,
        produces: list[str] | None = None,
        **kwargs,
    ) -> "AgentOrchestrator":
        """
        Programmatically register a step.

        Args:
            name (str): Unique step name.
            handler (Callable): The step function to register.
            deps (list[str] | None): Step dependencies.
            produces (list[str] | None): Context keys produced.
            **kwargs: Additional registration options.

        Returns:
            AgentOrchestrator: Self for method chaining.

        Example:
            >>> ao.register_step(
            ...     "fetch_data",
            ...     fetch_data_handler,
            ...     deps=["extract_company"],
            ...     produces=["data"],
            ... )
        """
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
    ) -> "AgentOrchestrator":
        """
        Programmatically register a chain.

        Args:
            name (str): Unique chain name.
            steps (list[str]): List of step names in execution order.
            **kwargs: Additional registration options.

        Returns:
            AgentOrchestrator: Self for method chaining.

        Example:
            >>> ao.register_chain(
            ...     "my_chain",
            ...     ["step1", "step2", "step3"],
            ...     error_handling="continue",
            ... )
        """
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
    ) -> "AgentOrchestrator":
        """
        Register a shared resource (config, clients, etc.).

        Resources are managed through ResourceManager for unified
        lifecycle management including cleanup.

        Args:
            name (str): Unique resource name.
            resource (Any): Direct resource instance. Mutually exclusive
                with factory.
            factory (Callable[[], Any] | None): Factory function to create
                the resource lazily. Mutually exclusive with resource.
            scope (ResourceScope): Resource scope. Default: SINGLETON.
                SINGLETON: One instance shared across all uses.
                REQUEST: New instance per chain execution.
            cleanup (Callable[[Any], Any] | None): Cleanup function called
                when resource is disposed.
            dependencies (list[str] | None): Other resources this depends on.

        Returns:
            AgentOrchestrator: Self for method chaining.

        Example:
            >>> # Direct instance
            >>> ao.register_resource("config", config_dict)
            >>>
            >>> # Factory with cleanup
            >>> ao.register_resource(
            ...     "db",
            ...     factory=lambda: create_db_pool(),
            ...     cleanup=lambda pool: pool.close(),
            ... )
            >>>
            >>> # Async factory with dependencies
            >>> ao.register_resource(
            ...     "cache",
            ...     factory=create_redis,
            ...     cleanup=lambda c: c.close(),
            ...     dependencies=["config"],
            ... )

        See Also:
            resource(): Decorator for resource factories.
            get_resource(): Retrieve a resource by name.
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

        Args:
            name (str | None): Resource name. Default: function name.
            scope (ResourceScope): Resource scope. Default: SINGLETON.
            cleanup (Callable[[Any], Any] | None): Cleanup function.
            dependencies (list[str] | None): Resource dependencies.

        Returns:
            Callable: The decorator function.

        Example:
            >>> @ao.resource("db", cleanup=lambda c: c.close())
            ... def create_db():
            ...     return DatabasePool()
            >>>
            >>> @ao.resource("cache", dependencies=["config"])
            ... async def create_cache():
            ...     config = await ao.get_resource_async("config")
            ...     return Redis(config.redis_url)
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

    def get_agent(self, name: str, **init_kwargs) -> Any:
        """
        Get an agent instance by name with runtime configuration.

        Args:
            name (str): Registered agent name.
            **init_kwargs: Arguments passed to agent constructor.

        Returns:
            Any: Agent instance (auto-wrapped in ResilientAgent if configured).

        Raises:
            KeyError: If agent is not registered.

        Example:
            >>> # Get agent with runtime config
            >>> sec_agent = ao.get_agent("sec_filing_agent", mcp_url="http://sec-mcp:8000")
            >>>
            >>> # Get agent without config (for mock mode)
            >>> sec_agent = ao.get_agent("sec_filing_agent")
        """
        return self._agent_registry.get_agent(name, **init_kwargs)

    def use(self, middleware: Any) -> "AgentOrchestrator":
        """
        Add middleware to the execution pipeline.

        Middleware intercepts step execution for cross-cutting concerns.

        Args:
            middleware: Middleware instance with before/after methods.

        Returns:
            AgentOrchestrator: Self for method chaining.

        Example:
            >>> ao.use(TimingMiddleware())
            >>> ao.use(LoggingMiddleware())
        """
        self._middleware.append(middleware)
        self._executor.add_middleware(middleware)
        return self

    # ══════════════════════════════════════════════════════════════════
    #                    DAGSTER-STYLE CLI COMMANDS
    # ══════════════════════════════════════════════════════════════════

    def check(self, chain_name: str | None = None) -> dict[str, Any]:
        """
        Validate definitions (like 'dg check defs').

        Validates all registered definitions and displays the DAG structure
        with execution order and parallel groups.

        Checks performed:
        - All steps in chains exist
        - Dependencies are resolvable
        - No circular dependencies
        - Chains are valid

        Args:
            chain_name (str | None): Specific chain to check. If None, checks all.

        Returns:
            dict[str, Any]: Validation result with keys:
                - valid (bool): True if all checks passed.
                - chains (list): Per-chain validation results.
                - errors (list): List of error messages.
                - warnings (list): List of warnings.

        Example:
            >>> result = ao.check()  # Check all
            >>> if not result["valid"]:
            ...     for error in result["errors"]:
            ...         print(f"Error: {error}")
            >>>
            >>> ao.check("meeting_prep")  # Check specific chain

        See Also:
            list_defs(): List all definitions.
            graph(): Visualize the DAG.
        """
        errors = []
        warnings = []
        chain_results = []

        chains_to_check = [chain_name] if chain_name else self.list_chains()

        if not chains_to_check:
            print("⚠ No chains registered")
            return {"valid": True, "chains": [], "errors": [], "warnings": ["No chains registered"]}

        print(f"\n{'═' * 60}")
        print(f"  AgentOrchestrator Check: {self.name} v{self.version}")
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
        """Validate a single chain."""
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

        Displays all registered agents, steps, chains, and resources
        with their dependencies and relationships.

        Returns:
            dict[str, list[str]]: Dict with keys "agents", "steps", "chains".

        Example:
            >>> defs = ao.list_defs()
            >>> print(f"Registered: {len(defs['steps'])} steps")
        """
        agents = self.list_agents()
        steps = self.list_steps()
        chains = self.list_chains()

        print(f"\n{'═' * 50}")
        print("  AgentOrchestrator Definitions")
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
            chain_name (str): Chain to visualize.
            format (str): Output format. "ascii" or "mermaid".

        Returns:
            str: The visualization string.

        Example:
            >>> ao.graph("meeting_prep")  # ASCII art
            >>> ao.graph("meeting_prep", "mermaid")  # Mermaid.js format
        """
        from agentorchestrator.core.visualize import DAGVisualizer

        # Pass our registries to handle isolated ao instances
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

        This is the main method for running chains asynchronously.
        The chain's steps are executed in dependency order with
        parallel execution where possible.

        Args:
            chain_name (str): Name of the chain to execute.
            data (dict[str, Any] | None): Initial context data.
            request_id (str | None): Optional request ID for tracing.
                Auto-generated if not provided.
            debug_callback (DebugCallback | None): Optional callback invoked
                after each step for debugging. Receives (ctx, step_name, result).
            validate_input (bool): If True (default), validate input against
                chain's input_model before execution (fail-fast).

        Returns:
            dict[str, Any]: Execution result with keys:
                - success (bool): True if chain completed successfully.
                - results (list): Per-step results.
                - context (dict): Final context state.
                - duration_ms (float): Total execution time.
                - error (dict | None): Error details if failed.

        Raises:
            ContractValidationError: If validate_input=True and input
                fails validation.

        Example:
            >>> result = await ao.launch("meeting_prep", {"company": "Apple"})
            >>> if result["success"]:
            ...     print(f"Completed in {result['duration_ms']}ms")
            ... else:
            ...     print(f"Failed: {result['error']}")
            >>>
            >>> # With debug callback
            >>> def on_step(ctx, step_name, result):
            ...     print(f"Step {step_name}: {result}")
            >>> result = await ao.launch("chain", data, debug_callback=on_step)

        See Also:
            launch_sync(): Synchronous wrapper.
            launch_resumable(): Execute with checkpointing.
            run_step(): Run a single step in isolation.
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
        from agentorchestrator.core.validation import is_pydantic_model, validate_chain_input

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

        Creates a new event loop via asyncio.run() and executes the chain.
        Resources are automatically cleaned up after execution.

        Args:
            chain_name (str): Name of the chain to execute.
            data (dict[str, Any] | None): Initial context data.
            request_id (str | None): Optional request ID for tracing.
            cleanup (bool): If True (default), cleanup resources after execution.
                Set to False if you plan to run multiple chains.

        Returns:
            dict[str, Any]: Execution result (same as launch()).

        Example:
            >>> result = ao.launch_sync("meeting_prep", {"company": "Apple"})

        Note:
            This method creates a new event loop. For multiple chain executions
            in async code, use launch() directly.
        """
        async def _run_with_cleanup():
            try:
                return await self.launch(chain_name, data, request_id)
            finally:
                if cleanup:
                    await self.cleanup_resources()

        return asyncio.run(_run_with_cleanup())

    async def run_step(
        self,
        step_name: str,
        data: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run a single step in isolation for testing.

        Executes any step independently without running the entire chain.
        Dependencies are NOT executed - the provided data is used directly.

        This is useful for:
        - Unit testing individual steps
        - Debugging step behavior
        - Integration testing with mock data

        Args:
            step_name (str): Name of the step to run.
            data (dict[str, Any] | None): Initial context data (simulates
                what dependencies would provide).
            request_id (str | None): Optional request ID for tracing.

        Returns:
            dict[str, Any]: Result with keys:
                - success (bool): Whether step completed successfully.
                - step_name (str): Name of the executed step.
                - output (Any): Step's return value.
                - context (dict): Context state after execution.
                - duration_ms (float): Execution time.
                - error (dict | None): Error details if failed.

        Example:
            >>> # Test a step in isolation
            >>> result = await ao.run_step("context_builder", {
            ...     "request": {"corporate_company_name": "Apple Inc"}
            ... })
            >>> assert result["success"]
            >>> assert result["output"]["company"] == "Apple Inc"
            >>>
            >>> # Provide mock data for dependent steps
            >>> result = await ao.run_step("response_builder", {
            ...     "context_output": {...},  # Mock from context_builder
            ...     "prioritization_output": {...},  # Mock from prioritization
            ... })

        See Also:
            run_step_sync(): Synchronous version.
            launch(): Run a full chain.
        """
        import time
        import uuid

        step_spec = self._step_registry.get_spec(step_name)
        if not step_spec:
            return {
                "success": False,
                "error": {
                    "message": f"Step '{step_name}' not found",
                    "type": "StepNotFoundError",
                },
            }

        # Create isolated context for this step test
        req_id = request_id or f"step_test_{uuid.uuid4().hex[:8]}"
        ctx = self.create_context(req_id, data)

        start_time = time.perf_counter()

        try:
            # Execute the step handler within step_scope for proper STEP-scoped cleanup
            handler = step_spec.handler
            async with ctx.step_scope(step_name):
                if asyncio.iscoroutinefunction(handler):
                    output = await handler(ctx)
                else:
                    output = handler(ctx)

            duration_ms = (time.perf_counter() - start_time) * 1000

            return {
                "success": True,
                "step_name": step_name,
                "output": output,
                "context": {
                    "request_id": ctx.request_id,
                    "data": {k: v for k, v in ctx.to_dict().get("data", {}).items()},
                },
                "duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Step '{step_name}' failed: {e}")

            return {
                "success": False,
                "step_name": step_name,
                "error": {
                    "message": str(e),
                    "type": type(e).__name__,
                },
                "context": {
                    "request_id": ctx.request_id,
                    "data": {k: v for k, v in ctx.to_dict().get("data", {}).items()},
                },
                "duration_ms": duration_ms,
            }

    def run_step_sync(
        self,
        step_name: str,
        data: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Synchronous version of run_step().

        Args:
            step_name (str): Name of the step to run.
            data (dict[str, Any] | None): Initial context data.
            request_id (str | None): Optional request ID.

        Returns:
            dict[str, Any]: Step execution result.

        Example:
            >>> result = ao.run_step_sync("context_builder", {"request": {...}})
        """
        return asyncio.run(self.run_step(step_name, data, request_id))

    # Aliases for backward compatibility
    async def run(
        self,
        chain_name: str,
        initial_data: dict[str, Any] | None = None,
        debug_callback: DebugCallback | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Alias for launch() - backward compatibility.

        See launch() for full documentation.
        """
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
        """
        Alias for launch_sync() - backward compatibility.

        See launch_sync() for full documentation.
        """
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
        resume() or retry_failed(). Checkpoints are saved after each step.

        Args:
            chain_name (str): Name of the chain to execute.
            data (dict[str, Any] | None): Initial context data.
            run_id (str | None): Optional run ID. Auto-generated if not provided.

        Returns:
            dict[str, Any]: Result with keys:
                - run_id (str): ID for resuming this run.
                - success (bool): Whether chain completed successfully.
                - status (str): "completed", "partial", or "failed".
                - checkpoint (dict): Full checkpoint data.

        Example:
            >>> # Run with checkpointing
            >>> result = await ao.launch_resumable("my_chain", {"company": "Apple"})
            >>> run_id = result["run_id"]
            >>>
            >>> # If it fails, resume later
            >>> if not result["success"]:
            ...     result = await ao.resume(run_id)

        See Also:
            resume(): Resume a failed run.
            retry_failed(): Re-run only failed steps.
            get_partial_output(): Get outputs from completed steps.
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

        Loads the checkpoint and continues execution from where it left off.

        Args:
            run_id (str): ID of the run to resume.
            skip_completed (bool): If True, skip steps that already completed.
                Default: True.

        Returns:
            dict[str, Any]: Result with updated checkpoint.

        Raises:
            ValueError: If run_id is not found.

        Example:
            >>> # Resume a failed run
            >>> result = await ao.resume("run_abc123")
            >>> print(f"Status: {result['status']}")
        """
        return await self._resumable_runner.resume(
            run_id=run_id,
            skip_completed=skip_completed,
        )

    async def retry_failed(self, run_id: str) -> dict[str, Any]:
        """
        Re-run only the failed steps from a previous run.

        Args:
            run_id (str): ID of the run with failed steps.

        Returns:
            dict[str, Any]: Result with updated checkpoint.

        Example:
            >>> result = await ao.retry_failed("run_abc123")
        """
        return await self._resumable_runner.retry_failed(run_id)

    async def get_partial_output(self, run_id: str) -> dict[str, Any]:
        """
        Get partial outputs from a failed or incomplete run.

        Useful for retrieving results from steps that completed
        before a failure.

        Args:
            run_id (str): ID of the run.

        Returns:
            dict[str, Any]: Outputs from completed steps.

        Example:
            >>> outputs = await ao.get_partial_output("run_abc123")
            >>> print(f"Completed: {list(outputs.keys())}")
        """
        return await self._resumable_runner.get_partial_output(run_id)

    async def list_resumable_runs(
        self,
        chain_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List runs that can be resumed.

        Args:
            chain_name (str | None): Filter by chain name.

        Returns:
            list[dict[str, Any]]: List of resumable run summaries.

        Example:
            >>> runs = await ao.list_resumable_runs()
            >>> for run in runs:
            ...     print(f"{run['run_id']}: {run['status']}")
        """
        return await self._resumable_runner.list_resumable(chain_name)

    async def get_run(self, run_id: str) -> RunCheckpoint | None:
        """
        Get a run checkpoint by ID.

        Args:
            run_id (str): ID of the run.

        Returns:
            RunCheckpoint | None: The checkpoint or None if not found.

        Example:
            >>> checkpoint = await ao.get_run("run_abc123")
            >>> if checkpoint:
            ...     print(f"Chain: {checkpoint.chain_name}")
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
            chain_name (str | None): Filter by chain name.
            status (str | None): Filter by status ("completed", "failed", "partial").
            limit (int): Maximum number of runs to return. Default: 100.

        Returns:
            list[RunCheckpoint]: List of matching checkpoints.

        Example:
            >>> # List all failed runs
            >>> runs = await ao.list_runs(status="failed")
            >>>
            >>> # List runs for a specific chain
            >>> runs = await ao.list_runs(chain_name="my_chain", limit=10)
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
            run_id (str): ID of the run to delete.

        Returns:
            bool: True if deleted, False if not found.

        Example:
            >>> if await ao.delete_run("run_abc123"):
            ...     print("Checkpoint deleted")
        """
        return await self._run_store.delete_checkpoint(run_id)

    # ══════════════════════════════════════════════════════════════════
    #                         DISCOVERY
    # ══════════════════════════════════════════════════════════════════

    def list_agents(self) -> list[str]:
        """
        List all registered agents.

        Returns:
            list[str]: List of agent names.

        Example:
            >>> agents = ao.list_agents()
            >>> print(f"Registered agents: {agents}")
        """
        return self._agent_registry.list()

    def list_steps(self) -> list[str]:
        """
        List all registered steps.

        Returns:
            list[str]: List of step names.

        Example:
            >>> steps = ao.list_steps()
            >>> print(f"Registered steps: {steps}")
        """
        return self._step_registry.list()

    def list_chains(self) -> list[str]:
        """
        List all registered chains.

        Returns:
            list[str]: List of chain names.

        Example:
            >>> chains = ao.list_chains()
            >>> print(f"Registered chains: {chains}")
        """
        return self._chain_registry.list()

    def get_resource(self, name: str) -> Any:
        """
        Get a registered resource (sync version).

        For resources with factories, this triggers lazy initialization.

        Args:
            name (str): Resource name.

        Returns:
            Any: The resource instance.

        Raises:
            KeyError: If resource is not registered.

        Example:
            >>> db = ao.get_resource("db")
        """
        return self._resource_manager.get_sync(name)

    async def get_resource_async(self, name: str) -> Any:
        """
        Get a registered resource (async version).

        For resources with async factories, use this method.

        Args:
            name (str): Resource name.

        Returns:
            Any: The resource instance.

        Raises:
            KeyError: If resource is not registered.

        Example:
            >>> db = await ao.get_resource_async("db")
        """
        return await self._resource_manager.get(name)

    def has_resource(self, name: str) -> bool:
        """
        Check if a resource is registered.

        Args:
            name (str): Resource name to check.

        Returns:
            bool: True if registered.

        Example:
            >>> if ao.has_resource("db"):
            ...     db = ao.get_resource("db")
        """
        return self._resource_manager.has(name)

    def list_resources(self) -> list[str]:
        """
        List all registered resources.

        Returns:
            list[str]: List of resource names.

        Example:
            >>> resources = ao.list_resources()
        """
        return self._resource_manager.list_resources()

    async def cleanup_resources(self, timeout_seconds: float = 30.0) -> None:
        """
        Cleanup all managed resources with timeout.

        Calls cleanup functions for all resources that have them.
        Resources are cleaned up in reverse dependency order.

        Args:
            timeout_seconds (float): Maximum time to wait for cleanup.
                Default: 30.0 seconds.

        Raises:
            asyncio.TimeoutError: If cleanup exceeds timeout.

        Example:
            >>> await ao.cleanup_resources()
            >>>
            >>> # With custom timeout
            >>> await ao.cleanup_resources(timeout_seconds=60.0)
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
        state_model: type | None = None,
    ) -> ChainContext:
        """
        Create a new chain context.

        Args:
            request_id (str): Unique request identifier.
            data (dict[str, Any] | None): Initial context data.
            state_model (type | None): Optional Pydantic model for type-safe state.

        Returns:
            ChainContext: The new context.

        Example:
            >>> ctx = ao.create_context("req_123", {"query": "Apple"})
            >>>
            >>> # With type-safe state
            >>> from pydantic import BaseModel
            >>> class MyState(BaseModel):
            ...     counter: int = 0
            >>> ctx = ao.create_context("req_123", state_model=MyState)
        """
        ctx = ChainContext(request_id=request_id, initial_data=data, state_model=state_model)
        self._context_manager._contexts[request_id] = ctx
        return ctx

    def get_context(self, request_id: str) -> ChainContext | None:
        """
        Get an existing context.

        Args:
            request_id (str): The request ID to look up.

        Returns:
            ChainContext | None: The context or None if not found.

        Example:
            >>> ctx = ao.get_context("req_123")
        """
        return self._context_manager.get_context(request_id)

    # ══════════════════════════════════════════════════════════════════
    #                         UTILITIES
    # ══════════════════════════════════════════════════════════════════

    def clear(self) -> None:
        """
        Clear all registrations.

        Removes all registered agents, steps, chains, and resources.
        Use in tests to reset state between test cases.

        Example:
            >>> ao.clear()
            >>> assert len(ao.list_steps()) == 0
        """
        self._agent_registry.clear()
        self._step_registry.clear()
        self._chain_registry.clear()
        self._resource_manager.clear()

    # Legacy alias
    def clear_registrations(self) -> None:
        """
        Alias for clear() - backward compatibility.

        See clear() for documentation.
        """
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

        See check() for documentation.
        """
        if output == "mermaid":
            if chain_name:
                self.graph(chain_name, "mermaid")
        return self.check(chain_name)

    def __repr__(self) -> str:
        """Return string representation of the orchestrator."""
        return (
            f"AgentOrchestrator(name={self.name!r}, "
            f"agents={len(self.list_agents())}, "
            f"steps={len(self.list_steps())}, "
            f"chains={len(self.list_chains())})"
        )


# ══════════════════════════════════════════════════════════════════════════════
#                           MODULE-LEVEL API
# ══════════════════════════════════════════════════════════════════════════════

_default_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    """
    Get or create the default AgentOrchestrator instance.

    Returns the global singleton orchestrator instance. Creates one
    if it doesn't exist.

    Returns:
        AgentOrchestrator: The default orchestrator instance.

    Example:
        >>> ao = get_orchestrator()
        >>> @ao.step
        ... async def my_step(ctx): ...

    See Also:
        set_orchestrator(): Set a custom default instance.
    """
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = AgentOrchestrator()
    return _default_orchestrator


def set_orchestrator(ao: AgentOrchestrator) -> None:
    """
    Set the default AgentOrchestrator instance.

    Use this to replace the global singleton with a custom instance.

    Args:
        ao (AgentOrchestrator): The orchestrator to use as default.

    Example:
        >>> custom_ao = AgentOrchestrator(name="custom", max_parallel=5)
        >>> set_orchestrator(custom_ao)

    See Also:
        get_orchestrator(): Get the default instance.
    """
    global _default_orchestrator
    _default_orchestrator = ao


# Convenience type alias
Context = ChainContext
