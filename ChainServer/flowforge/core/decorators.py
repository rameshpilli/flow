"""
FlowForge Decorators

Provides decorator-based registration for agents, steps, chains, and middleware.
This is the primary user-facing API for building chains.
"""

import inspect
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from flowforge.core.registry import (
    get_agent_registry,
    get_chain_registry,
    get_step_registry,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


def agent(
    name: str | None = None,
    version: str = "1.0.0",
    description: str = "",
    capabilities: list[str] | None = None,
    config: dict[str, Any] | None = None,
    aliases: list[str] | None = None,
) -> Callable[[type[T]], type[T]]:
    """
    Decorator to register a class as a data agent.

    Usage:
        @agent(name="news_agent", version="1.0", capabilities=["fetch_news", "search"])
        class NewsAgent:
            async def fetch(self, query: str) -> dict:
                ...

    Args:
        name: Agent name (defaults to class name)
        version: Semantic version
        description: Human-readable description
        capabilities: List of agent capabilities
        config: Default configuration
        aliases: Alternative names for the agent
    """

    def decorator(cls: type[T]) -> type[T]:
        agent_name = name or cls.__name__
        registry = get_agent_registry()

        registry.register_agent(
            name=agent_name,
            agent_class=cls,
            version=version,
            description=description or cls.__doc__ or "",
            capabilities=capabilities,
            config=config,
            aliases=aliases,
        )

        # Add metadata to class
        cls._flowforge_agent = True
        cls._flowforge_name = agent_name
        cls._flowforge_version = version

        logger.debug(f"Agent registered: {agent_name} v{version}")
        return cls

    return decorator


def step(
    name: str | None = None,
    dependencies: list[str] | None = None,
    produces: list[str] | None = None,
    version: str = "1.0.0",
    description: str = "",
    timeout_ms: int = 30000,
    retry_count: int = 0,
    retry_delay_ms: int = 1000,
    aliases: list[str] | None = None,
) -> Callable[[F], F]:
    """
    Decorator to register a function as a chain step.

    Usage:
        @step(name="context_builder", produces=["context"])
        async def build_context(ctx: ChainContext) -> dict:
            ...

        @step(name="prioritizer", dependencies=["context_builder"])
        async def prioritize_content(ctx: ChainContext) -> dict:
            ...

    Args:
        name: Step name (defaults to function name)
        dependencies: Steps that must complete before this one
        produces: Context keys this step produces
        version: Semantic version
        description: Human-readable description
        timeout_ms: Execution timeout
        retry_count: Number of retries on failure
        retry_delay_ms: Delay between retries
        aliases: Alternative names for the step
    """

    def decorator(func: F) -> F:
        step_name = name or func.__name__
        registry = get_step_registry()

        retry_config = (
            {
                "count": retry_count,
                "delay_ms": retry_delay_ms,
            }
            if retry_count > 0
            else {}
        )

        registry.register_step(
            name=step_name,
            handler=func,
            dependencies=dependencies,
            produces=produces,
            version=version,
            description=description or func.__doc__ or "",
            timeout_ms=timeout_ms,
            retry_config=retry_config,
            aliases=aliases,
        )

        # Add metadata to function
        func._flowforge_step = True
        func._flowforge_name = step_name
        func._flowforge_dependencies = dependencies or []
        func._flowforge_produces = produces or []

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        # Preserve attributes on wrapper
        wrapper._flowforge_step = True
        wrapper._flowforge_name = step_name
        wrapper._flowforge_dependencies = dependencies or []
        wrapper._flowforge_produces = produces or []

        logger.debug(f"Step registered: {step_name} v{version}")

        # Return original if already async, wrapper if not
        if inspect.iscoroutinefunction(func):
            func._flowforge_step = True
            return func
        return wrapper

    return decorator


def chain(
    name: str | None = None,
    steps: list[str] | None = None,
    parallel_groups: list[list[str]] | None = None,
    error_handling: str = "fail_fast",
    version: str = "1.0.0",
    description: str = "",
    aliases: list[str] | None = None,
) -> Callable[[type[T]], type[T]]:
    """
    Decorator to register a class as a chain definition.

    Usage:
        @chain(name="meeting_prep", steps=["context_builder", "prioritizer", "generator"])
        class MeetingPrepChain:
            # Optional: override step execution
            async def before_step(self, step_name: str, ctx: ChainContext):
                ...

    Args:
        name: Chain name (defaults to class name)
        steps: Ordered list of step names (or use class attribute)
        parallel_groups: Groups of steps to run in parallel
        error_handling: How to handle errors ("fail_fast", "continue", "retry")
        version: Semantic version
        description: Human-readable description
        aliases: Alternative names for the chain
    """

    def decorator(cls: type[T]) -> type[T]:
        chain_name = name or cls.__name__

        # Get steps from decorator arg or class attribute
        chain_steps = steps or getattr(cls, "steps", [])
        if not chain_steps:
            raise ValueError(f"Chain {chain_name} must define steps")

        registry = get_chain_registry()

        registry.register_chain(
            name=chain_name,
            steps=chain_steps,
            chain_class=cls,
            parallel_groups=parallel_groups,
            error_handling=error_handling,
            version=version,
            description=description or cls.__doc__ or "",
            aliases=aliases,
        )

        # Add metadata to class
        cls._flowforge_chain = True
        cls._flowforge_name = chain_name
        cls._flowforge_steps = chain_steps

        logger.debug(f"Chain registered: {chain_name} v{version} with {len(chain_steps)} steps")
        return cls

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
        cls._flowforge_middleware = True
        cls._flowforge_name = middleware_name
        cls._flowforge_priority = priority
        cls._flowforge_applies_to = applies_to

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
        if not hasattr(cls, "_flowforge_parallel_groups"):
            cls._flowforge_parallel_groups = []
        cls._flowforge_parallel_groups.append(list(step_names))
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
        existing = getattr(func, "_flowforge_dependencies", [])
        func._flowforge_dependencies = existing + list(step_names)
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
        existing = getattr(func, "_flowforge_produces", [])
        func._flowforge_produces = existing + list(context_keys)
        return func

    return decorator
