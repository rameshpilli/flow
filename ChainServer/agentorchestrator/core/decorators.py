"""
AgentOrchestrator Decorators

Provides decorator-based registration for agents, steps, chains, and middleware.
These decorators delegate to the global AgentOrchestrator instance for unified behavior.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


def _get_orchestrator():
    """Get the global forge instance (lazy import to avoid circular deps)"""
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

    Delegates to the global AgentOrchestrator instance for unified behavior.

    Usage:
        @agent
        class NewsAgent:
            async def fetch(self, query: str) -> dict:
                ...

        @agent(name="sec_agent", group="financial", version="1.0.0")
        class SECFilingAgent:
            async def fetch(self, query: str) -> dict:
                ...

    Args:
        name: Agent name (defaults to class name)
        description: Human-readable description
        group: Agent group for organization
        version: Agent version string
        capabilities: List of capabilities this agent provides
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
) -> F | Callable[[F], F]:
    """
    Decorator to register a function as a chain step.

    Delegates to the global AgentOrchestrator instance for unified behavior.

    Usage:
        @step
        async def extract_company(ctx): ...

        @step(deps=[extract_company], produces=["company_data"])
        async def process_data(ctx): ...

        @step(max_concurrency=2)
        async def call_external_api(ctx): ...

        # With input/output contracts (fail-fast validation)
        @step(
            input_model=ChainRequest,
            output_model=ContextBuilderOutput,
            input_key="request",
        )
        async def context_builder(ctx):
            request = ctx.get("request")  # Already validated
            return output  # Validated against output_model

    Args:
        name: Step name (defaults to function name)
        deps: Steps that must complete before this one
        dependencies: Alias for deps (backward compatibility)
        produces: Context keys this step produces
        resources: Resource names to inject
        description: Human-readable description
        group: Step group for organization
        timeout_ms: Execution timeout
        retry: Number of retries on failure
        max_concurrency: Max parallel instances (None = unlimited)
        input_model: Pydantic model to validate input data (fail-fast)
        output_model: Pydantic model to validate step output
        input_key: Context key to validate (default: "request")
        validate_output: Whether to validate output (default: True)
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

    Delegates to the global AgentOrchestrator instance for unified behavior.

    Usage:
        @chain
        class MeetingPrepChain:
            steps = ["extract_company", "fetch_data", "build_response"]

        @chain(name="my_chain", group="workflows")
        class MyChain:
            steps = [extract_company, fetch_data]

    Args:
        name: Chain name (defaults to class name)
        description: Human-readable description
        group: Chain group for organization
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

    Usage:
        @middleware(name="summarizer", priority=50)
        class SummarizerMiddleware:
            async def before(self, ctx: ChainContext, step_name: str):
                ...
            async def after(self, ctx: ChainContext, step_name: str, result: Any):
                ...

    Args:
        name: Middleware name (defaults to class name)
        priority: Execution priority (lower = earlier)
        applies_to: List of step names to apply to (None = all)
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

    Usage:
        @parallel("fetch_news", "fetch_filings", "fetch_earnings")
        @chain(name="data_fetcher")
        class DataFetcherChain:
            steps = ["fetch_news", "fetch_filings", "fetch_earnings", "merge_results"]
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

    Usage:
        @depends_on("context_builder")
        @step(name="prioritizer")
        async def prioritize(ctx):
            ...
    """

    def decorator(func: F) -> F:
        existing = getattr(func, "_ao_dependencies", [])
        func._ao_dependencies = existing + list(step_names)
        return func

    return decorator


def produces(*context_keys: str):
    """
    Alternative way to declare what a step produces.

    Usage:
        @produces("context", "metadata")
        @step(name="context_builder")
        async def build_context(ctx):
            ...
    """

    def decorator(func: F) -> F:
        existing = getattr(func, "_ao_produces", [])
        func._ao_produces = existing + list(context_keys)
        return func

    return decorator
