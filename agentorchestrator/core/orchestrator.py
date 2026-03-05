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
        version: str = "0.1.0",
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
            version (str): Version string. Default: "0.1.0".
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
            
            logger.warning(
                "Using synchronous context manager ('with AgentOrchestrator()') inside a running event loop. "
                "Resource cleanup will be scheduled as a background task and may not complete before the program exits. "
                "Use 'async with AgentOrchestrator()' instead to ensure proper cleanup."
            )
            
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
        consumes: list[str] | None = None,
        resources: list[str] | None = None,
        description: str = "",
        group: str | None = None,
        timeout_ms: int = 30000,
        timeout: float | int | None = None,  # Alias (seconds)
        retry: int = 0,
        retry_delay_ms: int | None = None,
        retry_delay: float | int | None = None,  # Alias (seconds)
        max_concurrency: int | None = None,
        input_model: type | None = None,
        output_model: type | None = None,
        input_key: str | None = None,
        validate_output: bool = True,
        state_model: type | None = None,
        condition: Callable[[Any], bool] | None = None,
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
            consumes (list[str] | None): Context keys this step requires.
                Enables dataflow-based dependency resolution when the chain
                has dataflow=True.
            resources (list[str] | None): Resource names to inject as kwargs.
            description (str): Human-readable description.
            group (str | None): Step group for organization.
            timeout_ms (int): Execution timeout in milliseconds. Default: 30000.
            timeout (float | int | None): Alias for timeout in seconds. If set,
                overrides timeout_ms.
            retry (int): Number of retries on failure. Default: 0.
            retry_delay_ms (int | None): Delay between retries in milliseconds.
                Default: 1000ms if not set.
            retry_delay (float | int | None): Alias for retry_delay in seconds.
            max_concurrency (int | None): Max parallel instances. None = unlimited.
            input_model (type | None): Pydantic model to validate input.
            output_model (type | None): Pydantic model to validate output.
            input_key (str | None): Context key to validate. Default: "request".
            validate_output (bool): Whether to validate output. Default: True.
            condition (Callable[[Any], bool] | None): Optional condition function
                that receives ctx and returns bool. Step only executes if condition
                returns True. If False, step is skipped with reason "condition not met".

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

            # Merge deps from @depends_on decorator with explicit deps parameter
            # @depends_on sets _ao_dependencies on the function
            decorator_deps = getattr(func, "_ao_dependencies", [])
            all_deps = list(effective_deps or []) + list(decorator_deps)

            # Merge produces from @produces decorator with explicit produces parameter
            decorator_produces = getattr(func, "_ao_produces", [])
            all_produces = list(produces or []) + list(decorator_produces)

            # Merge consumes from @consumes decorator with explicit consumes parameter
            decorator_consumes = getattr(func, "_ao_consumes", [])
            all_consumes = list(consumes or []) + list(decorator_consumes)

            # Resolve dependencies - can be functions or strings
            resolved_deps = []
            for dep in all_deps:
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

            # Normalize timeout/retry delay aliases
            effective_timeout_ms = (
                int(float(timeout) * 1000)
                if timeout is not None
                else timeout_ms
            )
            effective_retry_delay_ms = (
                int(float(retry_delay) * 1000)
                if retry_delay is not None
                else (retry_delay_ms if retry_delay_ms is not None else 1000)
            )

            # Register step with dedicated fields (no more overloading retry_config)
            self._step_registry.register_step(
                name=step_name,
                handler=handler,
                dependencies=resolved_deps,
                produces=all_produces or None,  # Merged from decorator and param
                consumes=all_consumes or None,  # Merged from decorator and param
                resources=resources,  # Dedicated resources field
                description=description,
                group=group,
                timeout_ms=effective_timeout_ms,
                retry_count=retry,  # Explicit retry count
                retry_delay_ms=effective_retry_delay_ms,
                max_concurrency=max_concurrency,  # Dedicated concurrency field
                input_model=input_model,  # Input contract
                output_model=output_model,  # Output contract
                input_key=input_key,  # Key to validate
                validate_output=validate_output,  # Whether to validate output
                state_model=state_model,  # Typed state model (optional)
                condition=condition,  # Conditional execution
            )
            func._fg_name = step_name
            func._fg_type = "step"
            func._fg_deps = resolved_deps
            func._fg_produces = all_produces or []
            func._fg_consumes = all_consumes or []
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
        error_handling: str | None = None,
        dataflow: bool = False,
        input_model: type | None = None,
        output_model: type | None = None,
        input_key: str = "request",
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
            error_handling (str | None): Optional override for chain error handling.
                If not provided, uses class attribute error_handling or fail_fast.
            dataflow (bool): Enable automatic dependency resolution via
                produces/consumes declarations. When True, if step A has
                produces=["foo"] and step B has consumes=["foo"], then B
                will automatically depend on A. Default: False.
            input_model (type | None): Pydantic model for chain input validation.
                If set, input data is validated at launch() time before any
                steps execute (fail-fast). Can also be set as class attribute.
            output_model (type | None): Pydantic model for chain output validation.
            input_key (str): Key in initial data to validate. Default: "request".

        Returns:
            type[T] | Callable[[type[T]], type[T]]: Decorated class or decorator.

        Example:
            >>> @ao.chain
            ... class MeetingPrepChain:
            ...     steps = ["extract_company", "fetch_data", "build_response"]
            >>>
            >>> # With input validation
            >>> from pydantic import BaseModel
            >>> class MeetingRequest(BaseModel):
            ...     company: str
            ...     meeting_date: str
            >>>
            >>> @ao.chain(input_model=MeetingRequest)
            ... class ValidatedChain:
            ...     steps = ["prepare", "process"]
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
            input_model (type): Optional. Can also be set via decorator arg.
            output_model (type): Optional. Can also be set via decorator arg.
            input_key (str): Optional. Can also be set via decorator arg.

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
            error_handling_value = error_handling or getattr(cls, "error_handling", None)
            if error_handling_value is None and hasattr(cls, "fail_fast"):
                error_handling_value = "fail_fast" if getattr(cls, "fail_fast") else "continue"
            if error_handling_value is None:
                error_handling_value = "fail_fast"

            # Extract parallel_groups from class attrs and @parallel decorator
            # @parallel decorator sets _ao_parallel_groups, class may have parallel_groups
            class_parallel = getattr(cls, "parallel_groups", None) or []
            decorator_parallel = getattr(cls, "_ao_parallel_groups", [])
            parallel_groups = list(class_parallel) + list(decorator_parallel) or None

            # Extract input/output models - decorator args take precedence over class attrs
            chain_input_model = input_model or getattr(cls, "input_model", None)
            chain_output_model = output_model or getattr(cls, "output_model", None)
            chain_input_key = input_key if input_key != "request" else getattr(cls, "input_key", "request")

            # Extract dataflow from class if not explicitly set
            chain_dataflow = dataflow or getattr(cls, "dataflow", False)

            self._chain_registry.register_chain(
                name=chain_name,
                steps=resolved_steps,
                description=description,
                group=group,
                error_handling=error_handling_value,
                dataflow=chain_dataflow,
                parallel_groups=parallel_groups,
                input_model=chain_input_model,
                output_model=chain_output_model,
                input_key=chain_input_key,
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
        merge_map: dict[str, str] | None = None,
        merge_mode: str = "safe",
    ) -> str:
        """
        Create a wrapper step that executes a subchain.

        This enables chain composition by wrapping chains as steps.
        The subchain receives current context data and its outputs
        are merged back into the parent context.

        Args:
            subchain_name (str): Name of the chain to execute as a step.
            parent_chain_name (str): Name of the parent chain (for namespacing).
            merge_map (dict[str, str] | None): Optional mapping of subchain output keys
                to parent context keys. Example: {"subchain_result": "final_result"}
                This prevents accidental overwrites by explicitly mapping outputs.
            merge_mode (str): How to merge subchain results:
                - "safe": Only merge new keys, never overwrite (default)
                - "selective": Only merge keys specified in merge_map
                - "all": Merge all keys (may overwrite parent data)
                - "none": Don't merge any keys (access via _subchain_*_result)

        Returns:
            str: Name of the created wrapper step.
        """
        # Include parent chain and config hash to avoid collisions when same
        # subchain is used with different merge_map/merge_mode in different chains
        import hashlib
        config_hash = hashlib.md5(
            f"{merge_map}:{merge_mode}".encode()
        ).hexdigest()[:8]
        wrapper_step_name = f"__subchain__{parent_chain_name}__{subchain_name}__{config_hash}"

        # Check if wrapper already exists with same config
        if self._step_registry.has(wrapper_step_name):
            return wrapper_step_name

        # Capture references for closure
        ao = self
        _merge_map = merge_map
        _merge_mode = merge_mode

        async def subchain_handler(ctx: ChainContext) -> dict[str, Any]:
            """
            Execute the subchain and merge results into parent context.

            The subchain receives a copy of the current context data and
            its outputs are merged back into the parent context according
            to the configured merge_mode and merge_map.
            """
            # Prepare data for subchain - pass current context data
            subchain_data = {}
            parent_keys = set()
            for key in ctx.keys():
                subchain_data[key] = ctx.get(key)
                parent_keys.add(key)

            # Execute the subchain
            logger.info(f"Executing subchain '{subchain_name}' from parent '{parent_chain_name}'")
            result = await ao.launch(
                subchain_name,
                data=subchain_data,
                validate_input=False,  # Parent already validated
            )

            # Store subchain result for reference (always available)
            ctx.set(
                f"_subchain_{subchain_name}_result",
                result,
                scope=ContextScope.CHAIN,
            )

            # Merge subchain context back into parent based on merge_mode
            if result.get("success") and "context" in result:
                subchain_ctx_data = result["context"].get("data", {})
                
                if _merge_mode == "none":
                    # Don't merge anything - user accesses via _subchain_*_result
                    logger.debug(f"Subchain '{subchain_name}' merge_mode=none, skipping merge")
                
                elif _merge_mode == "selective" and _merge_map:
                    # Only merge explicitly mapped keys
                    for src_key, dst_key in _merge_map.items():
                        if src_key in subchain_ctx_data:
                            ctx.set(dst_key, subchain_ctx_data[src_key], scope=ContextScope.CHAIN)
                            logger.debug(f"Subchain merge: {src_key} -> {dst_key}")
                
                elif _merge_mode == "all":
                    # Merge all keys (may overwrite)
                    for key, value in subchain_ctx_data.items():
                        if _merge_map and key in _merge_map:
                            # Use mapped name if available
                            ctx.set(_merge_map[key], value, scope=ContextScope.CHAIN)
                        else:
                            ctx.set(key, value, scope=ContextScope.CHAIN)
                    if parent_keys & set(subchain_ctx_data.keys()):
                        logger.warning(
                            f"Subchain '{subchain_name}' overwrote parent keys: "
                            f"{parent_keys & set(subchain_ctx_data.keys())}"
                        )
                
                else:  # "safe" mode (default)
                    # Only merge new keys, never overwrite
                    skipped_keys = []
                    for key, value in subchain_ctx_data.items():
                        target_key = _merge_map.get(key, key) if _merge_map else key
                        if target_key not in parent_keys:
                            ctx.set(target_key, value, scope=ContextScope.CHAIN)
                        else:
                            skipped_keys.append(target_key)
                    
                    # Log at warning level when data is being skipped - this could indicate
                    # a configuration issue that users should be aware of
                    if skipped_keys:
                        logger.warning(
                            f"Subchain '{subchain_name}' skipped overwriting parent keys: "
                            f"{skipped_keys}. Use merge_mode='all' to overwrite or "
                            f"merge_map to rename keys."
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
        merge_map: dict[str, str] | None = None,
        merge_mode: str = "safe",
    ) -> str:
        """
        Create a step that executes another chain (explicit subchain reference).

        Use this when you want to explicitly include a chain as a step
        with custom dependencies.

        Args:
            chain_name (str): Name of the chain to execute as a step.
            deps (list[Any] | None): Dependencies for this subchain step.
            produces (list[str] | None): What this subchain produces.
            merge_map (dict[str, str] | None): Optional mapping of subchain output keys
                to parent context keys. Example: {"subchain_result": "final_result"}
                This prevents accidental overwrites by explicitly mapping outputs.
            merge_mode (str): How to merge subchain results:
                - "safe": Only merge new keys, never overwrite (default)
                - "selective": Only merge keys specified in merge_map
                - "all": Merge all keys (may overwrite parent data)
                - "none": Don't merge any keys (access via _subchain_*_result)

        Returns:
            str: Name of the wrapper step (for use in chain definitions).

        Raises:
            ValueError: If the specified chain is not registered.

        Example:
            >>> # Basic usage
            >>> @ao.chain
            ... class ParentChain:
            ...     steps = [
            ...         "setup_step",
            ...         ao.subchain("data_processing_chain", deps=["setup_step"]),
            ...         "finalize_step",
            ...     ]
            >>>
            >>> # With merge mapping (prevents overwrites)
            >>> @ao.chain
            ... class SafePipeline:
            ...     steps = [
            ...         "init",
            ...         ao.subchain(
            ...             "DataProcessing",
            ...             deps=["init"],
            ...             merge_map={"result": "processing_result"},
            ...             merge_mode="selective",
            ...         ),
            ...         "report",
            ...     ]
        """
        if not self._chain_registry.is_chain(chain_name):
            raise ValueError(f"Chain '{chain_name}' not found. Register it first.")

        # Create the wrapper step with merge configuration
        wrapper_name = self._create_subchain_step(
            chain_name, "__explicit__",
            merge_map=merge_map,
            merge_mode=merge_mode,
        )

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
        isolate_run: bool = True,
        run_store: "RunStore | None" = None,
        checkpoint_interval: int = 10,
        initial_context_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Event-driven workflow runner with run isolation and optional checkpointing.
        
        Publishes seed events and processes inbound events with registered handlers
        until one of these conditions:
        - stop_when returns True, or
        - processed >= max_events, or
        - timeout reached.

        Args:
            seed_events: Initial events to publish to start the workflow.
            max_events: Maximum number of events to process (default: 100).
            timeout_s: Maximum time in seconds to run (default: 30.0).
            run_id: Unique identifier for this run. Auto-generated if not provided.
            stop_when: Predicate function (event, ctx) -> bool to stop early.
            min_events: Minimum events to process before checking stop_when.
            isolate_run: If True (default), only process events matching this run_id.
                On a shared Redis bus, this prevents consuming other runs' events.
            run_store: Optional RunStore for checkpointing (enables resumability).
            checkpoint_interval: Save checkpoint every N events (default: 10).
            initial_context_data: Optional initial context data to restore on resume.

        Returns:
            dict with run_id, processed count, handlers, duration_ms, and
            checkpoint_id if run_store was provided.

        Example:
            >>> # Basic usage
            >>> result = await ao.run_event_loop(
            ...     seed_events=[Event(type="Start", payload={"query": "..."})],
            ...     stop_when=lambda e, ctx: e.type == "Complete",
            ... )
            >>>
            >>> # With checkpointing for resumability
            >>> from agentorchestrator.core.run_store import FileRunStore
            >>> store = FileRunStore("./checkpoints")
            >>> result = await ao.run_event_loop(
            ...     seed_events=[...],
            ...     run_store=store,
            ...     checkpoint_interval=5,
            ... )
        """
        run_id = run_id or f"event_{uuid.uuid4().hex[:8]}"
        ctx = ChainContext(
            request_id=run_id,
            initial_data=initial_context_data,
            resource_manager=self._resource_manager,
        )
        
        # Initialize checkpoint tracking
        checkpoint_id = None
        events_since_checkpoint = 0
        processed_event_types: list[str] = []

        processed = 0
        skipped = 0
        start = time.time()

        # Subscribe before publishing seeds to ensure delivery in in-memory mode
        sub = await self._event_bus.subscribe()
        try:
            if seed_events:
                for ev in seed_events:
                    if ev.run_id is None:
                        ev.run_id = run_id
                    await self._event_bus.publish(ev)
            while processed < max_events:
                remaining = timeout_s - (time.time() - start)
                if remaining <= 0:
                    break
                try:
                    event = await asyncio.wait_for(sub.__anext__(), timeout=remaining)
                except (asyncio.TimeoutError, StopAsyncIteration):
                    break
                except asyncio.CancelledError:
                    logger.debug(f"Event loop cancelled for run_id={run_id}")
                    break

                # Run isolation: skip events from other runs on shared bus
                if isolate_run and event.run_id != run_id:
                    skipped += 1
                    continue

                processed += 1
                events_since_checkpoint += 1
                processed_event_types.append(event.type)
                
                await self._dispatch_event(event, ctx)

                # Checkpoint periodically if run_store provided
                if run_store and events_since_checkpoint >= checkpoint_interval:
                    try:
                        from agentorchestrator.core.run_store import RunCheckpoint
                        checkpoint = RunCheckpoint(
                            run_id=run_id,
                            chain_name="__event_loop__",
                            status="running",
                            context_data=ctx.to_dict(),
                            initial_data={"processed_events": processed_event_types.copy()},
                        )
                        await run_store.save_checkpoint(checkpoint)
                        checkpoint_id = run_id
                        events_since_checkpoint = 0
                        logger.debug(f"Event loop checkpoint saved: {run_id}")
                    except Exception as e:
                        logger.warning(f"Failed to save event loop checkpoint: {e}")

                if stop_when and processed >= min_events:
                    try:
                        if stop_when(event, ctx):
                            break
                    except Exception:
                        # ignore predicate errors; keep running
                        pass
        finally:
            # Always close subscription to prevent leaks
            await sub.aclose()
            
            # Final checkpoint on completion
            if run_store:
                try:
                    from agentorchestrator.core.run_store import RunCheckpoint
                    checkpoint = RunCheckpoint(
                        run_id=run_id,
                        chain_name="__event_loop__",
                        status="completed",
                        context_data=ctx.to_dict(),
                        step_outputs={"processed_events": processed_event_types},
                    )
                    await run_store.save_checkpoint(checkpoint)
                    checkpoint_id = run_id
                except Exception as e:
                    logger.warning(f"Failed to save final event loop checkpoint: {e}")

        result = {
            "run_id": run_id,
            "processed": processed,
            "skipped": skipped,  # Events from other runs
            "handlers": {k: len(v) for k, v in self._event_handlers.items()},
            "duration_ms": (time.time() - start) * 1000,
        }
        
        if checkpoint_id:
            result["checkpoint_id"] = checkpoint_id
        
        return result
    
    async def resume_event_loop(
        self,
        run_id: str,
        run_store: "RunStore",
        seed_events: list[Event] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Resume an event loop from a checkpoint.
        
        Loads the checkpoint, restores context, and continues processing.
        
        Args:
            run_id: The run_id to resume.
            run_store: RunStore containing the checkpoint.
            seed_events: Optional additional events to publish on resume.
            **kwargs: Additional arguments passed to run_event_loop().
            
        Returns:
            Same as run_event_loop().
            
        Example:
            >>> store = FileRunStore("./checkpoints")
            >>> result = await ao.resume_event_loop(
            ...     run_id="event_abc123",
            ...     run_store=store,
            ...     seed_events=[Event(type="Resume")],
            ... )
        """
        checkpoint = await run_store.load_checkpoint(run_id)
        if checkpoint is None:
            raise ValueError(f"No checkpoint found for run_id: {run_id}")

        # Restore context data from checkpoint (supports full ctx.to_dict or data-only)
        context_data = checkpoint.context_data or {}
        if isinstance(context_data, dict) and "data" in context_data:
            context_data = context_data.get("data", {})

        # The checkpoint contains context data from where we left off.
        # We pass the run_id to continue from where we stopped.
        logger.info(f"Resuming event loop from checkpoint: {run_id}")

        return await self.run_event_loop(
            seed_events=seed_events,
            run_id=run_id,
            run_store=run_store,
            initial_context_data=context_data,
            **kwargs,
        )

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

    def provide(
        self,
        name: str,
        instance_or_factory: Any,
        scope: ResourceScope = ResourceScope.SINGLETON,
        cleanup: Callable[[Any], Any] | None = None,
    ) -> "AgentOrchestrator":
        """
        Register a resource with simplified API (convenience method).

        This is a more intuitive alternative to register_resource() for common cases.
        Use this when you want to quickly register a resource instance or factory.

        Args:
            name (str): Resource identifier (e.g., "db_manager", "s3_client").
            instance_or_factory (Any): Either a resource instance or a factory function.
                If callable, treated as factory. If not, treated as instance.
            scope (ResourceScope): Resource lifetime. Default: SINGLETON.
            cleanup (Callable[[Any], Any] | None): Optional cleanup function.

        Returns:
            AgentOrchestrator: Self for method chaining.

        Example:
            >>> # Direct instances
            >>> ao.provide("db_manager", db_manager)
            >>> ao.provide("s3_client", s3_client)
            >>> ao.provide("llm_gateway", llm_gateway)
            >>>
            >>> # Factory function
            >>> ao.provide(
            ...     "cache",
            ...     lambda: Redis(host="localhost"),
            ...     cleanup=lambda c: c.close()
            ... )
            >>>
            >>> # Access in steps
            >>> async def my_step(ctx: ChainContext):
            ...     db = await ctx.get_resource("db_manager")
            ...     s3 = await ctx.get_resource("s3_client")
            ...     # Use resources...

        See Also:
            register_resource(): Full-featured resource registration.
            ctx.get_resource(): Access resources in steps.
        """
        return self.register_resource(
            name=name,
            resource=instance_or_factory if not callable(instance_or_factory) else None,
            factory=instance_or_factory if callable(instance_or_factory) else None,
            scope=scope,
            cleanup=cleanup,
        )

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
        # Sort by priority (lower priority runs first)
        self._middleware.sort(key=lambda m: getattr(m, "_ao_priority", 100))
        self._executor.add_middleware(middleware)
        return self

    def get_middleware_metrics(self, middleware_name: str | None = None) -> dict[str, Any]:
        """
        Get metrics from middleware for monitoring and tuning.

        Retrieves metrics from all middleware or a specific one by name/type.
        Useful for monitoring token usage, compression stats, cache hits, etc.

        Args:
            middleware_name (str | None): Name or type of middleware to query.
                If None, returns metrics from all middleware that support it.
                Examples: "token_manager", "summarizer", "TokenManagerMiddleware"

        Returns:
            dict[str, Any]: Metrics keyed by middleware name/type.
                Each middleware may include different metrics:
                - TokenManagerMiddleware: token usage, budget status, compressions
                - SummarizerMiddleware: compression ratios, tokens saved
                - RollingSummaryMiddleware: summary stats, versions
                - ResultAggregator: aggregation stats

        Example:
            >>> # Get all middleware metrics
            >>> metrics = ao.get_middleware_metrics()
            >>> for name, data in metrics.items():
            ...     print(f"{name}: {data}")
            >>>
            >>> # Get specific middleware metrics
            >>> token_metrics = ao.get_middleware_metrics("token_manager")
            >>> print(f"Peak usage: {token_metrics.get('peak_usage', 0)}")
            >>>
            >>> # After a chain run
            >>> result = await ao.launch("my_chain", input_data)
            >>> metrics = ao.get_middleware_metrics()
            >>> print(f"Tokens saved: {metrics['token_manager']['tokens_saved']}")

        See Also:
            use(): Add middleware to the pipeline.
            TokenManagerMiddleware: Token budget management.
            SummarizerMiddleware: Content compression.
        """
        metrics: dict[str, Any] = {}

        for mw in self._middleware:
            mw_type = type(mw).__name__
            mw_key = mw_type.lower().replace("middleware", "").strip("_") or mw_type

            # Check if this middleware matches the filter
            if middleware_name is not None:
                filter_lower = middleware_name.lower()
                if filter_lower not in mw_type.lower() and filter_lower != mw_key:
                    continue

            # Try to get metrics from the middleware
            if hasattr(mw, "get_metrics"):
                try:
                    mw_metrics = mw.get_metrics()
                    if middleware_name is not None:
                        # Return directly if specific middleware requested
                        return mw_metrics
                    metrics[mw_key] = mw_metrics
                except Exception as e:
                    metrics[mw_key] = {"error": str(e)}
            elif hasattr(mw, "get_usage"):
                # TokenManagerMiddleware compatibility
                try:
                    metrics[mw_key] = mw.get_usage()
                except Exception as e:
                    metrics[mw_key] = {"error": str(e)}
            elif hasattr(mw, "get_budget_report"):
                # Alternative accessor
                try:
                    metrics[mw_key] = mw.get_budget_report()
                except Exception as e:
                    metrics[mw_key] = {"error": str(e)}

        if middleware_name is not None and not metrics:
            return {"error": f"No middleware found matching '{middleware_name}'"}

        return metrics

    def list_middleware(self) -> list[dict[str, Any]]:
        """
        List all registered middleware with their configuration.

        Returns:
            list[dict]: List of middleware info including:
                - type: Class name of the middleware
                - priority: Execution priority
                - applies_to: Step patterns it applies to
                - has_metrics: Whether it supports get_metrics()

        Example:
            >>> for mw in ao.list_middleware():
            ...     print(f"{mw['type']} (priority={mw['priority']})")
        """
        result = []
        for mw in self._middleware:
            info = {
                "type": type(mw).__name__,
                "priority": getattr(mw, "priority", 0),
                "applies_to": getattr(mw, "_ao_applies_to", None),
                "excludes": getattr(mw, "_ao_excludes", None),
                "has_metrics": hasattr(mw, "get_metrics") or hasattr(mw, "get_usage"),
            }
            result.append(info)
        return result

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
            dataflow_badge = " [dataflow]" if result.get("dataflow") else ""
            print(f"  {status} {cname}{dataflow_badge}")

            # Show execution levels
            for level_idx, level in enumerate(result.get("levels", [])):
                is_parallel = len(level) > 1
                indent = "    "

                if is_parallel:
                    print(f"{indent}├─ [parallel]")
                    for step in level:
                        deps_str = f" ← {step['deps']}" if step.get("deps") else ""
                        prod_str = f" → {step['produces']}" if step.get("produces") else ""
                        cons_str = f" ⇐ {step['consumes']}" if step.get("consumes") else ""
                        print(f"{indent}│  • {step['name']}{deps_str}{cons_str}{prod_str}")
                else:
                    step = level[0]
                    deps_str = f" ← {step['deps']}" if step.get("deps") else ""
                    prod_str = f" → {step['produces']}" if step.get("produces") else ""
                    cons_str = f" ⇐ {step['consumes']}" if step.get("consumes") else ""
                    prefix = "├─" if level_idx < len(result.get("levels", [])) - 1 else "└─"
                    print(f"{indent}{prefix} {step['name']}{deps_str}{cons_str}{prod_str}")

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
        """Validate a single chain, including dataflow dependencies if enabled."""
        chain_spec = self._chain_registry.get_spec(chain_name)
        if not chain_spec:
            return {
                "name": chain_name,
                "valid": False,
                "errors": [f"Chain not found: {chain_name}"],
            }

        result = {"name": chain_name, "valid": True, "errors": [], "warnings": [], "levels": []}

        # If dataflow is enabled, resolve produces/consumes dependencies
        dataflow_deps: dict[str, set[str]] = {}
        if chain_spec.dataflow:
            result["dataflow"] = True
            # Build produces index
            produces_index: dict[str, list[str]] = {}
            for step_name in chain_spec.steps:
                step_spec = self._step_registry.get_spec(step_name)
                if step_spec:
                    for key in step_spec.produces:
                        if key not in produces_index:
                            produces_index[key] = []
                        produces_index[key].append(step_name)

            # Resolve consumes -> dependencies
            for step_name in chain_spec.steps:
                step_spec = self._step_registry.get_spec(step_name)
                if step_spec and step_spec.consumes:
                    dataflow_deps[step_name] = set()
                    for key in step_spec.consumes:
                        producers = produces_index.get(key, [])
                        if not producers:
                            result["warnings"].append(
                                f"{step_name} consumes '{key}' but no step produces it"
                            )
                        for producer in producers:
                            if producer != step_name:
                                dataflow_deps[step_name].add(producer)

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

                # Combine explicit deps with dataflow-resolved deps
                deps = set(step_spec.dependencies) if step_spec.dependencies else set()
                if step_name in dataflow_deps:
                    deps = deps | dataflow_deps[step_name]

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
                            "consumes": step_spec.consumes if step_spec.consumes else None,
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
        validated = False
        if validate_input and data is not None:
            data, validated = self._validate_chain_input(chain_name, data)

        return await self._runner.run(
            chain_name=chain_name,
            initial_data=data,
            request_id=request_id,
            debug_callback=debug_callback,
            skip_validation=validated,  # Skip double validation in runner only if we validated
        )

    def _validate_chain_input(
        self,
        chain_name: str,
        data: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """
        Validate chain input data before execution starts.

        Checks for input_model on:
        1. The chain definition itself (if input_model is set on ChainSpec)
        2. The first step in the chain (fallback)

        Note: Only the first step's input_model is checked as a fallback.
        Mid-chain steps with input_model are validated when they execute,
        not at chain launch time.

        Returns:
            Tuple of (validated_data, was_validated) where was_validated
            indicates if actual Pydantic validation occurred.

        Raises:
            ContractValidationError: If validation fails
        """
        from agentorchestrator.core.validation import is_pydantic_model, validate_chain_input

        # Get chain spec
        chain_spec = self._chain_registry.get_spec(chain_name)
        if not chain_spec:
            return data, False  # No chain spec, skip validation

        # Check for chain-level input_model
        chain_input_model = getattr(chain_spec, "input_model", None)
        chain_input_key = getattr(chain_spec, "input_key", "request")

        if is_pydantic_model(chain_input_model):
            logger.debug(f"Validating chain '{chain_name}' input against {chain_input_model.__name__}")
            first_step = chain_spec.steps[0] if chain_spec.steps else chain_name
            first_step_name = first_step if isinstance(first_step, str) else getattr(first_step, "_fg_name", str(first_step))
            validated_data = validate_chain_input(
                chain_name=chain_name,
                first_step_name=first_step_name,
                input_model=chain_input_model,
                initial_data=data,
                input_key=chain_input_key,
            )
            return validated_data, True

        # Check first step for input_model (fallback)
        if chain_spec.steps:
            first_step = chain_spec.steps[0]
            first_step_name = first_step if isinstance(first_step, str) else getattr(first_step, "_fg_name", str(first_step))
            step_spec = self._step_registry.get_spec(first_step_name)

            if step_spec:
                step_input_model = getattr(step_spec, "input_model", None)
                step_input_key = getattr(step_spec, "input_key", "request")

                if is_pydantic_model(step_input_model):
                    logger.debug(f"Validating step '{first_step_name}' input against {step_input_model.__name__}")
                    validated_data = validate_chain_input(
                        chain_name=chain_name,
                        first_step_name=first_step_name,
                        input_model=step_input_model,
                        initial_data=data,
                        input_key=step_input_key,
                    )
                    return validated_data, True

        return data, False  # No validation configured

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
        ctx = self.create_context(req_id, data, state_model=getattr(step_spec, "state_model", None))

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
        ctx = ChainContext(
            request_id=request_id,
            initial_data=data,
            state_model=state_model,
            resource_manager=self._resource_manager,
        )
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

    def remove_context(self, request_id: str) -> bool:
        """
        Remove a context after chain completion.
        
        Call this to free memory after a chain execution is complete.
        This prevents memory leaks in long-running processes.
        
        Args:
            request_id (str): The request ID to remove.
            
        Returns:
            bool: True if context was found and removed.
            
        Example:
            >>> ctx = ao.create_context("req_123")
            >>> # ... use context ...
            >>> ao.remove_context("req_123")  # Free memory
        """
        return self._context_manager.remove_context(request_id)

    def cleanup_old_contexts(self, max_age_seconds: float = 3600) -> int:
        """
        Remove contexts older than the specified age.
        
        Call this periodically in long-running processes to prevent
        memory leaks from accumulated contexts.
        
        Args:
            max_age_seconds (float): Maximum age in seconds. Default: 3600 (1 hour).
            
        Returns:
            int: Number of contexts removed.
            
        Example:
            >>> # In a background task
            >>> removed = ao.cleanup_old_contexts(max_age_seconds=1800)
            >>> logger.info(f"Cleaned up {removed} old contexts")
        """
        from datetime import datetime, timedelta, timezone
        
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        removed = 0
        
        # Get list of keys to avoid modifying dict during iteration
        context_ids = list(self._context_manager._contexts.keys())
        
        for request_id in context_ids:
            ctx = self._context_manager._contexts.get(request_id)
            if ctx:
                # Get created_at, ensure it's timezone-aware for comparison
                created_at = ctx.created_at
                if created_at.tzinfo is None:
                    # Assume UTC if naive
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at < cutoff:
                    self._context_manager.remove_context(request_id)
                    removed += 1
        
        if removed > 0:
            logger.info(f"Cleaned up {removed} old contexts (older than {max_age_seconds}s)")
        
        return removed

    async def start_auto_cleanup(
        self,
        interval_seconds: float = 300,
        max_age_seconds: float = 3600,
    ) -> asyncio.Task:
        """
        Start a background task that periodically cleans up old contexts.
        
        This prevents memory leaks in long-running processes by automatically
        removing contexts older than max_age_seconds every interval_seconds.
        
        Args:
            interval_seconds (float): How often to run cleanup. Default: 300 (5 min).
            max_age_seconds (float): Maximum context age. Default: 3600 (1 hour).
            
        Returns:
            asyncio.Task: The background cleanup task. Cancel it to stop cleanup.
            
        Example:
            >>> # Start auto cleanup
            >>> cleanup_task = await ao.start_auto_cleanup(
            ...     interval_seconds=60,  # Every minute
            ...     max_age_seconds=1800,  # Remove contexts older than 30 min
            ... )
            >>>
            >>> # Later, stop the cleanup
            >>> cleanup_task.cancel()
            
        Note:
            The task runs indefinitely until cancelled. Store the returned task
            if you need to cancel it later (e.g., during shutdown).
        """
        async def _cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    self.cleanup_old_contexts(max_age_seconds)
                except asyncio.CancelledError:
                    logger.debug("Auto context cleanup task cancelled")
                    break
                except Exception as e:
                    logger.warning(f"Error in auto context cleanup: {e}")
                    # Continue running despite errors
        
        task = asyncio.create_task(_cleanup_loop())
        self._cleanup_task = task  # Store reference
        logger.info(
            f"Started auto context cleanup (interval={interval_seconds}s, "
            f"max_age={max_age_seconds}s)"
        )
        return task

    def stop_auto_cleanup(self) -> bool:
        """
        Stop the background context cleanup task.
        
        Returns:
            bool: True if task was running and stopped, False otherwise.
            
        Example:
            >>> ao.stop_auto_cleanup()
        """
        if hasattr(self, "_cleanup_task") and self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("Stopped auto context cleanup")
            return True
        return False

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

    # ══════════════════════════════════════════════════════════════════
    #                    DEVELOPER DISCOVERY (DX)
    # ══════════════════════════════════════════════════════════════════

    def help(self, topic: str | None = None) -> str:
        """
        Interactive help for developers - shows available methods and examples.

        When called without arguments, displays a categorized list of all
        available methods with brief descriptions. When called with a topic,
        shows detailed help for that specific topic.

        Args:
            topic: Optional topic to get detailed help on. Options:
                - None: Show all methods categorized
                - "decorators": Show @ao.step, @ao.chain, @ao.agent usage
                - "execution": Show launch(), run_step(), resume() usage
                - "middleware": Show use(), list_middleware() usage
                - "validation": Show check(), graph(), list_defs() usage
                - "patterns": Show common patterns and examples
                - "summarization": Show summarization strategies
                - "multi-agent": Show multi-agent patterns

        Returns:
            str: Formatted help text (also printed to stdout).

        Example:
            >>> ao = AgentOrchestrator()
            >>> ao.help()  # Show all methods
            >>> ao.help("decorators")  # Show decorator usage
            >>> ao.help("patterns")  # Show common patterns
        """
        if topic is None:
            output = self._help_overview()
        elif topic == "decorators":
            output = self._help_decorators()
        elif topic == "execution":
            output = self._help_execution()
        elif topic == "middleware":
            output = self._help_middleware()
        elif topic == "validation":
            output = self._help_validation()
        elif topic == "patterns":
            output = self._help_patterns()
        elif topic == "summarization":
            output = self._help_summarization()
        elif topic == "multi-agent":
            output = self._help_multi_agent()
        else:
            output = f"Unknown topic: {topic}\n\nAvailable topics:\n"
            output += "  decorators, execution, middleware, validation, patterns, summarization, multi-agent"

        print(output)
        return output

    def _help_overview(self) -> str:
        """Generate overview help text."""
        return f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    AgentOrchestrator Help                            ║
║                    {self.name} v{self.version}                                     ║
╚══════════════════════════════════════════════════════════════════════╝

Current State:
  • Agents:     {len(self.list_agents())}
  • Steps:      {len(self.list_steps())}
  • Chains:     {len(self.list_chains())}
  • Middleware: {len(self._middleware)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 DECORATORS (define components)
  @ao.step(name, deps)     Define a processing step
  @ao.chain(name)          Define a chain of steps
  @ao.agent(name)          Define a data agent

🚀 EXECUTION (run workflows)
  ao.launch(chain, data)   Execute a chain async
  ao.launch_sync(...)      Execute synchronously
  ao.run_step(step, data)  Run single step in isolation
  ao.resume(run_id)        Resume a failed run

🔧 MIDDLEWARE (add behaviors)
  ao.use(middleware)       Add middleware to pipeline
  ao.list_middleware()     List registered middleware
  ao.get_middleware_metrics()  Get middleware metrics

✅ VALIDATION (inspect & debug)
  ao.check()               Validate all definitions
  ao.graph(chain)          ASCII DAG visualization
  ao.list_defs()           List all definitions
  ao.explain(chain)        Explain execution plan

📖 MORE HELP
  ao.help("decorators")    Decorator usage examples
  ao.help("execution")     Execution patterns
  ao.help("middleware")    Middleware configuration
  ao.help("patterns")      Common AI workflow patterns
  ao.help("summarization") Large response handling
  ao.help("multi-agent")   Multi-agent patterns

💡 QUICK START
  from agentorchestrator import AgentOrchestrator

  ao = AgentOrchestrator(name="my_app")

  @ao.step(name="greet")
  async def greet(ctx):
      name = ctx.get("name", "World")
      return {{"greeting": f"Hello, {{name}}!"}}

  @ao.chain(name="hello_chain")
  class HelloChain:
      steps = ["greet"]

  result = await ao.launch("hello_chain", {{"name": "Developer"}})
"""

    def _help_decorators(self) -> str:
        """Generate decorator help text."""
        return """
📌 DECORATORS - Define Components
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@ao.step(name, deps, produces, consumes, retry, timeout_ms)
─────────────────────────────────────────────────────────────
Define a processing step in your chain.

  @ao.step(name="fetch_data")
  async def fetch_data(ctx):
      query = ctx.get("query")
      data = await api.fetch(query)
      ctx.set("data", data)
      return {"fetched": len(data)}

  # With dependencies
  @ao.step(name="process", deps=["fetch_data"])
  async def process(ctx):
      data = ctx.get("data")
      return {"processed": transform(data)}

  # With dataflow (auto-dependency resolution)
  from agentorchestrator import produces, consumes

  @produces("company_data")
  @ao.step(name="fetch")
  async def fetch(ctx): ...

  @consumes("company_data")
  @ao.step(name="analyze")
  async def analyze(ctx): ...

@ao.chain(name, dataflow, error_handling)
─────────────────────────────────────────
Define a chain that orchestrates steps.

  @ao.chain(name="my_pipeline")
  class MyPipeline:
      steps = ["fetch_data", "process", "summarize"]

  # With dataflow-based dependencies
  @ao.chain(name="research", dataflow=True)
  class ResearchPipeline:
      steps = ["fetch", "analyze", "report"]

  # With error handling
  @ao.chain(name="robust", error_handling="continue")
  class RobustPipeline:
      steps = ["step1", "step2", "step3"]  # continues on failure

@ao.agent(name, capabilities)
─────────────────────────────
Define a data fetching agent.

  from agentorchestrator.agents import BaseAgent, AgentResult

  @ao.agent(name="news_agent", capabilities=["search"])
  class NewsAgent(BaseAgent):
      async def fetch(self, query: str) -> AgentResult:
          results = await news_api.search(query)
          return AgentResult(data=results, source="news_api", query=query)
"""

    def _help_execution(self) -> str:
        """Generate execution help text."""
        return """
🚀 EXECUTION - Run Workflows
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ao.launch(chain_name, initial_data) → dict
──────────────────────────────────────────
Execute a chain asynchronously.

  result = await ao.launch("my_chain", {"query": "Apple Inc"})

  if result["success"]:
      output = result["results"][-1]["output"]
      context = result["context"]
  else:
      print(f"Failed: {result['error']}")

ao.launch_sync(chain_name, initial_data) → dict
───────────────────────────────────────────────
Execute synchronously (for scripts/notebooks).

  result = ao.launch_sync("my_chain", {"query": "Apple"})

ao.run_step(step_name, initial_data) → dict
───────────────────────────────────────────
Test a single step in isolation.

  result = await ao.run_step("fetch_data", {"query": "test"})
  print(result["output"])

ao.launch_resumable(chain_name, initial_data) → dict
────────────────────────────────────────────────────
Execute with checkpointing for resume support.

  result = await ao.launch_resumable("long_chain", data)
  run_id = result["run_id"]  # Save this!

ao.resume(run_id) → dict
────────────────────────
Resume a failed run from last checkpoint.

  # If chain failed partway through:
  result = await ao.resume(run_id)
"""

    def _help_middleware(self) -> str:
        """Generate middleware help text."""
        return """
🔧 MIDDLEWARE - Add Behaviors
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ao.use(middleware)
──────────────────
Add middleware to the pipeline. Order matters (priority).

  from agentorchestrator.middleware import (
      LoggerMiddleware,
      CacheMiddleware,
      TokenManagerMiddleware,
      TokenBudget,
      SummarizerMiddleware,
      SummarizationStrategy,
      RollingSummaryMiddleware,
  )

  # Logging
  ao.use(LoggerMiddleware(level="INFO"))

  # Caching
  ao.use(CacheMiddleware(ttl_seconds=300))

  # Token budget management (RECOMMENDED)
  budget = TokenBudget(
      context_window=128000,
      reserved_output=8000,
      reserved_system=3000,
      reserved_history=15000,
  )
  ao.use(TokenManagerMiddleware(budget=budget, auto_summarize=True))

  # Summarization for specific steps
  ao.use(SummarizerMiddleware(
      summarizer=my_summarizer,
      strategy=SummarizationStrategy.TREE,  # STUFF, MAP_REDUCE, REFINE, TREE
      applies_to=["gather_*"],  # Glob patterns supported
  ))

  # Rolling summary for iterative data
  ao.use(RollingSummaryMiddleware(
      max_tokens=4000,
      recent_buffer_tokens=1000,
  ))

ao.list_middleware() → list[dict]
─────────────────────────────────
List all registered middleware with info.

  for mw in ao.list_middleware():
      print(f"{mw['type']} (priority={mw['priority']})")

ao.get_middleware_metrics(name=None) → dict
───────────────────────────────────────────
Get metrics from middleware for monitoring.

  # All middleware metrics
  metrics = ao.get_middleware_metrics()

  # Specific middleware
  token_metrics = ao.get_middleware_metrics("token_manager")
  print(f"Peak usage: {token_metrics['peak_usage']}")
"""

    def _help_validation(self) -> str:
        """Generate validation help text."""
        return """
✅ VALIDATION - Inspect & Debug
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ao.check(chain_name=None) → ValidationResult
────────────────────────────────────────────
Validate all definitions or a specific chain.

  result = ao.check()
  print(f"Valid: {result.valid}")
  for warning in result.warnings:
      print(f"⚠️  {warning}")

ao.graph(chain_name, format="ascii") → str
──────────────────────────────────────────
Generate DAG visualization.

  # ASCII (terminal)
  print(ao.graph("my_chain"))

  # Mermaid (for docs)
  print(ao.graph("my_chain", format="mermaid"))

ao.list_defs() → dict
─────────────────────
List all registered definitions.

  defs = ao.list_defs()
  print(f"Agents: {defs['agents']}")
  print(f"Steps: {defs['steps']}")
  print(f"Chains: {defs['chains']}")

ao.explain(chain_name) → str
────────────────────────────
Explain execution plan for a chain.

  explanation = ao.explain("my_chain")
  print(explanation)
"""

    def _help_patterns(self) -> str:
        """Generate patterns help text."""
        return """
📖 COMMON PATTERNS - AI Workflow Examples
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. PARALLEL DATA FETCHING
─────────────────────────
  @ao.step(name="plan")
  async def plan(ctx): ...

  @ao.step(name="fetch_news", deps=["plan"])
  async def fetch_news(ctx): ...

  @ao.step(name="fetch_sec", deps=["plan"])
  async def fetch_sec(ctx): ...

  @ao.step(name="synthesize", deps=["fetch_news", "fetch_sec"])
  async def synthesize(ctx): ...

  # fetch_news and fetch_sec run in parallel!

2. DATAFLOW-BASED DEPENDENCIES
──────────────────────────────
  from agentorchestrator import produces, consumes

  @produces("raw_data")
  @ao.step(name="fetch")
  async def fetch(ctx):
      ctx.set("raw_data", data)

  @consumes("raw_data")
  @produces("analysis")
  @ao.step(name="analyze")
  async def analyze(ctx):
      data = ctx.get("raw_data")
      ctx.set("analysis", result)

  @ao.chain(name="research", dataflow=True)
  class ResearchChain:
      steps = ["fetch", "analyze"]

3. TYPE-SAFE STATE
──────────────────
  from pydantic import BaseModel

  class MyState(BaseModel):
      counter: int = 0
      items: list[str] = []

  @ao.step(name="process", state_model=MyState)
  async def process(ctx):
      async with ctx.edit_state() as state:
          state.counter += 1
          state.items.append("new")

4. WITH MIDDLEWARE STACK
────────────────────────
  from agentorchestrator.middleware import *

  budget = TokenBudget(context_window=128000, reserved_output=8000)
  ao.use(TokenManagerMiddleware(budget=budget))
  ao.use(SummarizerMiddleware(strategy=SummarizationStrategy.TREE))
  ao.use(RollingSummaryMiddleware(max_tokens=4000))

  # Now your chain handles large responses automatically!
"""

    def _help_summarization(self) -> str:
        """Generate summarization help text."""
        return """
📚 SUMMARIZATION - Handle Large Responses
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STRATEGY SELECTION GUIDE
────────────────────────
  | Strategy    | Best For           | Tokens   |
  |-------------|--------------------| ---------|
  | STUFF       | Small docs         | < 4K     |
  | MAP_REDUCE  | Medium, parallel   | 10K-50K  |
  | REFINE      | Quality-critical   | 10K-50K  |
  | TREE        | Massive docs       | 50K+     |

TOKEN BUDGET (Prevents Overflow)
────────────────────────────────
  from agentorchestrator.middleware import TokenBudget, TokenManagerMiddleware

  budget = TokenBudget(
      context_window=128000,    # Total LLM context
      reserved_output=8000,     # For model response
      reserved_system=3000,     # For system prompt
      reserved_history=15000,   # For conversation
      warning_threshold=0.8,    # Warn at 80%
      critical_threshold=0.95,  # Force compress at 95%
  )

  ao.use(TokenManagerMiddleware(
      budget=budget,
      auto_summarize=True,
      target_ratio_after_compression=0.7,
  ))

TREE SUMMARIZATION (For 50K+ tokens)
────────────────────────────────────
  ao.use(SummarizerMiddleware(
      summarizer=my_summarizer,
      strategy=SummarizationStrategy.TREE,
      max_tokens=4000,
      applies_to=["gather_sec", "gather_research"],
  ))

ROLLING SUMMARY (Iterative data)
────────────────────────────────
  ao.use(RollingSummaryMiddleware(
      max_tokens=4000,
      summarizer=my_summarizer,
      recent_buffer_tokens=1000,  # Keep recent uncompressed
      applies_to=["gather_*"],
  ))

QUERY-AWARE COMPRESSION
───────────────────────
  summary = await summarizer.summarize_with_query(
      text=large_doc,
      query="What are the key risks?",
      max_tokens=2000,
      relevance_threshold=0.3,
  )
"""

    def _help_multi_agent(self) -> str:
        """Generate multi-agent help text."""
        return """
🤖 MULTI-AGENT PATTERNS
━━━━━━━━━━━━━━━━━━━━━━━

SQUAD PATTERN (Recommended)
───────────────────────────
  from agentorchestrator.squad import Squad, SquadOptions

  squad = Squad(
      supervisor=lead_agent,
      agents=[research, analyst, writer],
      options=SquadOptions(trace=True),
  )

  result = await squad.run("Research AI trends and write a report")

CONTEXT ISOLATION (Prevent pollution)
─────────────────────────────────────
  from agentorchestrator.squad.context import (
      ContextIsolationManager,
      IsolationLevel,
  )

  isolation = ContextIsolationManager(coordinator_context=ctx)

  # Each agent gets isolated namespace
  ns_research = isolation.create_namespace("research", IsolationLevel.FULL)
  ns_analyst = isolation.create_namespace("analyst", IsolationLevel.FULL)

  # Share only what's needed
  isolation.share_with_all("query")
  isolation.share_between("research", "findings", ["analyst"])

NAMESPACE-AWARE BUDGETS (Multi-agent token management)
─────────────────────────────────────────────────────
  from agentorchestrator.middleware import (
      NamespaceBudgetManager,
      BudgetAllocationStrategy,
  )

  manager = NamespaceBudgetManager(
      global_budget=budget,
      strategy=BudgetAllocationStrategy.PRIORITY,
  )

  manager.register_namespace("research", priority=3)  # More tokens
  manager.register_namespace("summary", priority=1)   # Fewer tokens
  manager.allocate()

RESULT AGGREGATION
──────────────────
  from agentorchestrator.squad.context import (
      ResultAggregator,
      AggregationStrategy,
  )

  aggregator = ResultAggregator(
      strategy=AggregationStrategy.SYNTHESIZE,
      summarizer=my_summarizer,
      pre_summarize_threshold_tokens=10000,
  )

  aggregator.add_from_namespace("research", ns_research)
  aggregator.add_from_namespace("analyst", ns_analyst)

  result = await aggregator.aggregate(llm=llm_client)
"""

    def explain(self, chain_name: str) -> str:
        """
        Explain the execution plan for a chain.

        Provides a human-readable explanation of how a chain will execute,
        including step order, dependencies, and parallel execution groups.

        Args:
            chain_name: Name of the chain to explain.

        Returns:
            str: Human-readable execution explanation.

        Example:
            >>> ao.explain("my_chain")
            Execution Plan for 'my_chain':
            1. [PARALLEL] fetch_news, fetch_sec
            2. [SEQUENTIAL] synthesize (depends on: fetch_news, fetch_sec)
        """
        chain_def = self._chain_registry.get(chain_name)
        if not chain_def:
            return f"Chain '{chain_name}' not found."

        steps = getattr(chain_def, "steps", [])
        if not steps:
            return f"Chain '{chain_name}' has no steps defined."

        output = f"\n📋 Execution Plan for '{chain_name}'\n"
        output += "━" * 50 + "\n\n"

        # Build dependency graph
        step_deps: dict[str, list[str]] = {}
        for step_name in steps:
            step_def = self._step_registry.get(step_name)
            if step_def:
                deps = getattr(step_def, "_ao_deps", [])
                step_deps[step_name] = deps
            else:
                step_deps[step_name] = []

        # Group into execution levels
        executed: set[str] = set()
        level = 1
        remaining = set(steps)

        while remaining:
            # Find steps whose dependencies are all executed
            ready = [s for s in remaining if all(d in executed for d in step_deps.get(s, []))]

            if not ready:
                output += f"⚠️  Circular dependency detected in: {remaining}\n"
                break

            if len(ready) > 1:
                output += f"  {level}. [PARALLEL] {', '.join(ready)}\n"
            else:
                deps = step_deps.get(ready[0], [])
                if deps:
                    output += f"  {level}. {ready[0]} (after: {', '.join(deps)})\n"
                else:
                    output += f"  {level}. {ready[0]}\n"

            executed.update(ready)
            remaining -= set(ready)
            level += 1

        output += "\n"
        output += f"Total steps: {len(steps)}\n"
        output += f"Middleware: {len(self._middleware)}\n"

        print(output)
        return output

    def discover(self, category: str | None = None) -> dict[str, Any]:
        """
        Discover available features and their current state.

        Returns a dictionary of available features organized by category,
        including what's registered and what middleware is active.

        Args:
            category: Optional category to filter. Options:
                - None: Return all categories
                - "agents": List registered agents
                - "steps": List registered steps
                - "chains": List registered chains
                - "middleware": List active middleware
                - "resources": List registered resources

        Returns:
            dict: Discovery results with category details.

        Example:
            >>> ao.discover()  # All categories
            >>> ao.discover("middleware")  # Just middleware
        """
        result: dict[str, Any] = {}

        if category is None or category == "agents":
            agents = self.list_agents()
            result["agents"] = {
                "count": len(agents),
                "names": agents,
                "help": "Use @ao.agent() to register agents",
            }

        if category is None or category == "steps":
            steps = self.list_steps()
            result["steps"] = {
                "count": len(steps),
                "names": steps,
                "help": "Use @ao.step() to register steps",
            }

        if category is None or category == "chains":
            chains = self.list_chains()
            result["chains"] = {
                "count": len(chains),
                "names": chains,
                "help": "Use @ao.chain() to register chains",
            }

        if category is None or category == "middleware":
            mw_list = self.list_middleware()
            result["middleware"] = {
                "count": len(mw_list),
                "active": [m["type"] for m in mw_list],
                "help": "Use ao.use() to add middleware",
            }

        if category is None or category == "resources":
            resources = self.list_resources()
            result["resources"] = {
                "count": len(resources),
                "names": resources,
                "help": "Use ao.register_resource() or @ao.resource()",
            }

        return result

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