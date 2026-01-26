"""
AgentOrchestrator Decorators
============================

This module provides decorator-based registration for agents, steps, chains,
and middleware in AgentOrchestrator.

Decorators offer a clean, declarative way to define and register components.
They delegate to the global AgentOrchestrator instance for unified behavior
and automatic registration.

Functions:
    agent: Decorator to register a class as a data agent.
    step: Decorator to register a function as a chain step.
    chain: Decorator to register a class as a chain definition.
    middleware: Decorator to register a class as middleware.
    parallel: Decorator to mark steps that can run in parallel.
    depends_on: Alternative way to declare step dependencies.
    produces: Alternative way to declare what a step produces.

Usage:
    from agentorchestrator.core.decorators import agent, step, chain

    # Register an agent
    @agent(name="news_agent", group="data")
    class NewsAgent:
        async def fetch(self, query: str) -> dict:
            ...

    # Register steps with dependencies
    @step
    async def extract_company(ctx):
        return {"company": "Apple"}

    @step(deps=[extract_company], produces=["data"])
    async def fetch_data(ctx):
        company = ctx.get("company")
        return {"data": [...]}

    # Register a chain
    @chain(name="my_chain")
    class MyChain:
        steps = [extract_company, fetch_data]

Example:
    >>> from agentorchestrator.core.decorators import step, chain, agent
    >>>
    >>> @agent(name="my_agent", version="1.0.0")
    ... class MyAgent:
    ...     async def fetch(self, query: str) -> dict:
    ...         return {"result": query}
    >>>
    >>> @step(timeout_ms=10000, retry=3)
    ... async def process_data(ctx):
    ...     agent = MyAgent()
    ...     return await agent.fetch(ctx.get("query"))
    >>>
    >>> @chain
    ... class DataPipeline:
    ...     steps = [process_data]

See Also:
    - agentorchestrator.core.orchestrator: AgentOrchestrator class these delegate to.
    - agentorchestrator.core.context: ChainContext passed to step functions.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


def _get_orchestrator():
    """
    Get the global ao instance (lazy import to avoid circular deps).

    Returns:
        AgentOrchestrator: The global orchestrator instance.
    """
    from agentorchestrator.core.orchestrator import get_orchestrator
    return get_orchestrator()


def agent(
    cls: type[T] | None = None,
    *,
    name: str | None = None,
    description: str = "",
    group: str | None = None,
    version: str | None = None,
    capabilities: list[str] | None = None,
) -> type[T] | Callable[[type[T]], type[T]]:
    """
    Decorator to register a class as a data agent.

    Agents are responsible for fetching data from external sources.
    This decorator registers the agent class with the global
    AgentOrchestrator instance for unified management.

    Can be used with or without parentheses:
        @agent
        class MyAgent: ...

        @agent(name="custom_name")
        class MyAgent: ...

    Args:
        cls (type[T] | None): The agent class (auto-provided when used
            without parentheses).
        name (str | None): Custom agent name. Default: class name.
        description (str): Human-readable description of what this agent does.
        group (str | None): Agent group for organization (e.g., "financial",
            "news", "social").
        version (str | None): Agent version string (e.g., "1.0.0").
        capabilities (list[str] | None): List of capabilities this agent
            provides (e.g., ["sec_filings", "earnings"]).

    Returns:
        type[T] | Callable[[type[T]], type[T]]: The decorated class or
            decorator function.

    Example:
        >>> @agent
        ... class NewsAgent:
        ...     async def fetch(self, query: str) -> dict:
        ...         return {"news": [...]}
        >>>
        >>> @agent(name="sec_agent", group="financial", version="1.0.0")
        ... class SECFilingAgent:
        ...     async def fetch(self, query: str, filing_type: str = "10-K") -> dict:
        ...         return {"filings": [...]}
        >>>
        >>> @agent(
        ...     name="earnings_agent",
        ...     capabilities=["earnings", "guidance", "transcripts"],
        ... )
        ... class EarningsAgent:
        ...     async def fetch(self, ticker: str) -> dict:
        ...         return {"earnings": {...}}

    Note:
        The decorated class will have `_fg_name` and `_fg_type` attributes
        set for introspection.

    See Also:
        agentorchestrator.agents.base.BaseAgent: Base class for agents.
        AgentOrchestrator.agent(): Instance method this delegates to.
    """
    def decorator(cls: type[T]) -> type[T]:
        # Store version and capabilities on class for introspection
        if version:
            cls._fg_version = version
        if capabilities:
            cls._fg_capabilities = capabilities
        return _get_orchestrator().agent(
            cls,
            name=name,
            description=description,
            group=group,
        )

    if cls is not None:
        return decorator(cls)
    return decorator


def step(
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
    # Input/Output Contracts
    input_model: type | None = None,
    output_model: type | None = None,
    input_key: str | None = None,
    validate_output: bool = True,
    # Type-safe state management
    state_model: type | None = None,
) -> F | Callable[[F], F]:
    """
    Decorator to register a function as a chain step.

    Steps are the building blocks of chains. Each step receives a
    ChainContext and can read from or write to it. Steps can have
    dependencies on other steps, declare what they produce, and
    include validation contracts.

    Can be used with or without parentheses:
        @step
        async def my_step(ctx): ...

        @step(timeout_ms=5000)
        async def my_step(ctx): ...

    Args:
        func (F | None): The step function (auto-provided when used
            without parentheses).
        name (str | None): Custom step name. Default: function name.
        deps (list[Any] | None): Steps that must complete before this one.
            Can be step functions or string names.
        dependencies (list[Any] | None): Alias for deps (backward compat).
        produces (list[str] | None): Context keys this step produces.
            Used for dependency tracking and validation.
        resources (list[str] | None): Resource names to inject as kwargs.
            Resources are registered via ao.register_resource().
        description (str): Human-readable description.
        group (str | None): Step group for organization.
        timeout_ms (int): Execution timeout in milliseconds. Default: 30000.
        retry (int): Number of retries on failure. Default: 0.
        max_concurrency (int | None): Max parallel instances of this step.
            None means unlimited. Use for rate-limited APIs.
        input_model (type | None): Pydantic model to validate input data.
            Enables fail-fast validation before step execution.
        output_model (type | None): Pydantic model to validate step output.
        input_key (str | None): Context key to validate. Default: "request".
        validate_output (bool): Whether to validate output. Default: True.
        state_model (type | None): Pydantic model for type-safe state management.
            Enables ctx.state and ctx.edit_state() with IDE autocomplete.

    Returns:
        F | Callable[[F], F]: The decorated function or decorator function.

    Example:
        >>> @step
        ... async def extract_company(ctx):
        ...     query = ctx.get("query")
        ...     return {"company": "Apple Inc"}
        >>>
        >>> @step(deps=[extract_company], produces=["data"])
        ... async def fetch_data(ctx):
        ...     company = ctx.get("company")
        ...     return {"data": [...]}
        >>>
        >>> # With resource injection
        >>> @step(resources=["db", "llm"])
        ... async def process_with_resources(ctx, db, llm):
        ...     data = await db.query("...")
        ...     summary = await llm.generate("...")
        ...     return {"summary": summary}
        >>>
        >>> # With input/output contracts
        >>> from pydantic import BaseModel
        >>>
        >>> class InputModel(BaseModel):
        ...     query: str
        ...     limit: int = 10
        >>>
        >>> class OutputModel(BaseModel):
        ...     results: list[dict]
        >>>
        >>> @step(input_model=InputModel, output_model=OutputModel)
        ... async def validated_step(ctx) -> dict:
        ...     request = ctx.get("request")  # Already validated
        ...     return {"results": [...]}
        >>>
        >>> # With concurrency limit for rate-limited APIs
        >>> @step(max_concurrency=2, timeout_ms=60000, retry=3)
        ... async def call_external_api(ctx):
        ...     return await slow_api.fetch(...)
        >>>
        >>> # With type-safe state
        >>> from pydantic import BaseModel, Field
        >>>
        >>> class PipelineState(BaseModel):
        ...     counter: int = 0
        ...     items: list[str] = Field(default_factory=list)
        >>>
        >>> @step(state_model=PipelineState)
        ... async def process(ctx: Context[PipelineState]):
        ...     async with ctx.edit_state() as state:
        ...         state.counter += 1  # Type-safe!
        ...     return {"count": ctx.state.counter}

    Note:
        The decorated function will have `_fg_name`, `_fg_type`,
        `_fg_deps`, `_fg_produces`, and `_fg_resources` attributes
        set for introspection.

    See Also:
        chain: Decorator to combine steps into chains.
        depends_on: Alternative dependency declaration.
        produces: Alternative produces declaration.
    """
    # Support both 'deps' and 'dependencies' (alias)
    resolved_deps = deps or dependencies

    def decorator(func: F) -> F:
        return _get_orchestrator().step(
            func,
            name=name,
            deps=resolved_deps,
            produces=produces,
            resources=resources,
            description=description,
            group=group,
            timeout_ms=timeout_ms,
            retry=retry,
            max_concurrency=max_concurrency,
            input_model=input_model,
            output_model=output_model,
            input_key=input_key,
            validate_output=validate_output,
            state_model=state_model,
        )

    if func is not None:
        return decorator(func)
    return decorator


def chain(
    cls: type[T] | None = None,
    *,
    name: str | None = None,
    description: str = "",
    group: str | None = None,
) -> type[T] | Callable[[type[T]], type[T]]:
    """
    Decorator to register a class as a chain definition.

    Chains define the execution order of steps. The class must have
    a `steps` attribute listing the steps to execute (as functions
    or string names).

    Can be used with or without parentheses:
        @chain
        class MyChain: ...

        @chain(name="custom_name")
        class MyChain: ...

    Args:
        cls (type[T] | None): The chain class (auto-provided when used
            without parentheses).
        name (str | None): Custom chain name. Default: class name.
        description (str): Human-readable description.
        group (str | None): Chain group for organization.

    Returns:
        type[T] | Callable[[type[T]], type[T]]: The decorated class or
            decorator function.

    Example:
        >>> @chain
        ... class MeetingPrepChain:
        ...     steps = ["extract_company", "fetch_data", "build_response"]
        >>>
        >>> @chain(name="my_chain", group="workflows")
        ... class MyChain:
        ...     steps = [extract_company, fetch_data]
        >>>
        >>> # With error handling configuration
        >>> @chain
        ... class ResilientChain:
        ...     steps = ["step1", "step2", "step3"]
        ...     error_handling = "continue"  # Continue on step failure
        >>>
        >>> # With parallel groups
        >>> @chain
        ... class ParallelChain:
        ...     steps = ["fetch_news", "fetch_filings", "merge_results"]
        ...     parallel_groups = [["fetch_news", "fetch_filings"]]

    Chain Class Attributes:
        steps (list): Required. List of step functions or names.
        error_handling (str): Optional. "fail_fast" or "continue".
            Default: "fail_fast".
        parallel_groups (list[list[str]]): Optional. Groups of steps
            that can run in parallel.

    Note:
        The decorated class will have `_fg_name` and `_fg_type`
        attributes set for introspection.

    See Also:
        step: Decorator for individual steps.
        AgentOrchestrator.launch(): Execute a registered chain.
    """
    def decorator(cls: type[T]) -> type[T]:
        return _get_orchestrator().chain(
            cls,
            name=name,
            description=description,
            group=group,
        )

    if cls is not None:
        return decorator(cls)
    return decorator


def middleware(
    name: str | None = None,
    priority: int = 100,
    applies_to: list[str] | None = None,
) -> Callable[[type[T]], type[T]]:
    """
    Decorator to register a class as middleware.

    Middleware intercepts step execution for cross-cutting concerns
    like logging, caching, rate limiting, or context modification.

    Args:
        name (str | None): Middleware name. Default: class name.
        priority (int): Execution priority. Lower values run first.
            Default: 100. Suggested ranges:
            - 0-25: Critical (security, auth)
            - 25-50: High (caching, rate limiting)
            - 50-75: Normal (logging, metrics)
            - 75-100: Low (cleanup, formatting)
        applies_to (list[str] | None): List of step names to apply to.
            None means all steps. Default: None.

    Returns:
        Callable[[type[T]], type[T]]: The decorator function.

    Example:
        >>> @middleware(name="timer", priority=50)
        ... class TimingMiddleware:
        ...     async def before(self, ctx, step_name: str) -> None:
        ...         ctx.set(f"_timer_{step_name}", time.time())
        ...
        ...     async def after(self, ctx, step_name: str, result: Any) -> Any:
        ...         start = ctx.get(f"_timer_{step_name}")
        ...         duration = time.time() - start
        ...         logger.info(f"{step_name} took {duration:.2f}s")
        ...         return result
        >>>
        >>> @middleware(priority=25, applies_to=["fetch_data"])
        ... class CacheMiddleware:
        ...     async def before(self, ctx, step_name: str) -> Any:
        ...         cache_key = f"{step_name}:{ctx.get('query')}"
        ...         if cached := self.cache.get(cache_key):
        ...             return cached  # Skip step execution
        ...         return None
        ...
        ...     async def after(self, ctx, step_name: str, result: Any) -> Any:
        ...         cache_key = f"{step_name}:{ctx.get('query')}"
        ...         self.cache.set(cache_key, result)
        ...         return result

    Middleware Methods:
        before(ctx, step_name): Called before step execution.
            Return a value to skip the step and use that value instead.
            Return None to proceed with step execution.
        after(ctx, step_name, result): Called after step execution.
            Can modify and return a different result.

    Note:
        The decorated class will have `_ao_middleware`, `_ao_name`,
        `_ao_priority`, and `_ao_applies_to` attributes set.

    See Also:
        AgentOrchestrator.use(): Add middleware to the pipeline.
    """

    def decorator(cls: type[T]) -> type[T]:
        middleware_name = name or cls.__name__

        # Add metadata to class
        cls._ao_middleware = True
        cls._ao_name = middleware_name
        cls._ao_priority = priority
        cls._ao_applies_to = applies_to

        logger.debug(f"Middleware registered: {middleware_name} (priority={priority})")
        return cls

    return decorator


# Convenience decorators for common patterns


def parallel(*step_names: str):
    """
    Decorator to mark steps that can run in parallel.

    Use this on a chain class to specify which steps can be
    executed concurrently. This is an alternative to setting
    the `parallel_groups` class attribute.

    Args:
        *step_names (str): Names of steps that can run in parallel.

    Returns:
        Callable[[type[T]], type[T]]: The decorator function.

    Example:
        >>> @parallel("fetch_news", "fetch_filings", "fetch_earnings")
        ... @chain(name="data_fetcher")
        ... class DataFetcherChain:
        ...     steps = [
        ...         "fetch_news",
        ...         "fetch_filings",
        ...         "fetch_earnings",
        ...         "merge_results",  # Runs after all fetches complete
        ...     ]
        >>>
        >>> # Multiple parallel groups
        >>> @parallel("step_a", "step_b")
        ... @parallel("step_c", "step_d")
        ... @chain
        ... class MultiParallelChain:
        ...     steps = ["step_a", "step_b", "step_c", "step_d", "final"]

    Note:
        Steps in a parallel group must not have dependencies on
        each other. Dependencies are still respected - parallel
        execution only happens when all dependencies are satisfied.

    See Also:
        chain: Chain decorator that processes parallel groups.
    """

    def decorator(cls: type[T]) -> type[T]:
        if not hasattr(cls, "_ao_parallel_groups"):
            cls._ao_parallel_groups = []
        cls._ao_parallel_groups.append(list(step_names))
        return cls

    return decorator


def depends_on(*step_names: str):
    """
    Alternative way to declare step dependencies.

    Use this decorator in addition to @step when you want to
    declare dependencies separately from the step definition.
    Useful for cleaner code organization or conditional dependencies.

    Args:
        *step_names (str): Names of steps this step depends on.

    Returns:
        Callable[[F], F]: The decorator function.

    Example:
        >>> @depends_on("context_builder")
        ... @step(name="prioritizer")
        ... async def prioritize(ctx):
        ...     context = ctx.get("context")  # From context_builder
        ...     return {"priorities": [...]}
        >>>
        >>> # Multiple dependencies
        >>> @depends_on("step_a", "step_b", "step_c")
        ... @step
        ... async def aggregate(ctx):
        ...     a = ctx.get("result_a")
        ...     b = ctx.get("result_b")
        ...     c = ctx.get("result_c")
        ...     return {"combined": [a, b, c]}

    Note:
        Dependencies from @depends_on are added to any dependencies
        specified in the @step decorator's `deps` parameter.

    See Also:
        step: Main step decorator with deps parameter.
    """

    def decorator(func: F) -> F:
        existing = getattr(func, "_ao_dependencies", [])
        func._ao_dependencies = existing + list(step_names)
        return func

    return decorator


def produces(*context_keys: str):
    """
    Alternative way to declare what a step produces.

    Use this decorator in addition to @step when you want to
    declare produces separately from the step definition.
    Useful for cleaner code organization.

    Args:
        *context_keys (str): Context keys this step produces.

    Returns:
        Callable[[F], F]: The decorator function.

    Example:
        >>> @produces("context", "metadata")
        ... @step(name="context_builder")
        ... async def build_context(ctx):
        ...     context = {"company": "Apple", "year": 2024}
        ...     metadata = {"source": "request", "timestamp": "..."}
        ...     ctx.set("context", context)
        ...     ctx.set("metadata", metadata)
        ...     return {"context": context, "metadata": metadata}
        >>>
        >>> # Combined with depends_on
        >>> @produces("summary")
        ... @depends_on("fetch_data")
        ... @step
        ... async def summarize(ctx):
        ...     data = ctx.get("data")
        ...     summary = generate_summary(data)
        ...     ctx.set("summary", summary)
        ...     return {"summary": summary}

    Note:
        The produces declaration is used for dependency tracking
        and validation. Steps that depend on these keys will wait
        for this step to complete.

    See Also:
        step: Main step decorator with produces parameter.
        depends_on: Declare step dependencies.
    """

    def decorator(func: F) -> F:
        existing = getattr(func, "_ao_produces", [])
        func._ao_produces = existing + list(context_keys)
        return func

    return decorator
