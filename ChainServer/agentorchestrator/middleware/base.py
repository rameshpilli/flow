"""
AgentOrchestrator Base Middleware
=================================

This module provides the base classes and interfaces for middleware components
in AgentOrchestrator.

Middleware intercepts step execution at various points in the chain lifecycle:
before execution, after completion, and on errors. This enables cross-cutting
concerns like logging, caching, rate limiting, and validation without modifying
step logic.

Classes:
    SkipStep: Exception to skip a step's execution from middleware.
    Middleware: Abstract base class for all middleware components.
    CompositeMiddleware: Combines multiple middleware into a single unit.

Usage:
    from agentorchestrator.middleware import Middleware

    class LoggingMiddleware(Middleware):
        async def before(self, ctx: ChainContext, step_name: str) -> None:
            print(f"Starting: {step_name}")

        async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
            print(f"Completed: {step_name} in {result.duration_ms}ms")

    # Register middleware
    ao.use(LoggingMiddleware())

Example:
    >>> from agentorchestrator.middleware import Middleware, SkipStep
    >>>
    >>> class CacheMiddleware(Middleware):
    ...     def __init__(self, cache: dict):
    ...         super().__init__(priority=50)
    ...         self._cache = cache
    ...
    ...     async def before(self, ctx: ChainContext, step_name: str) -> None:
    ...         cache_key = f"{step_name}:{ctx.get('query')}"
    ...         if cache_key in self._cache:
    ...             ctx.set(f"{step_name}_result", self._cache[cache_key])
    ...             raise SkipStep()  # Skip execution, use cached value
    ...
    ...     async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
    ...         cache_key = f"{step_name}:{ctx.get('query')}"
    ...         self._cache[cache_key] = result.output

See Also:
    - agentorchestrator.middleware.rate_limiter: Rate limiting middleware.
    - agentorchestrator.middleware.citation: Citation validation middleware.
    - agentorchestrator.core.context: ChainContext and StepResult classes.
"""

import fnmatch
from abc import ABC
from collections.abc import Callable
from typing import Any

from agentorchestrator.core.context import ChainContext, StepResult

__all__ = [
    "Middleware",
    "SkipStep",
    "CompositeMiddleware",
]


class SkipStep(Exception):
    """
    Exception to skip a step's execution from middleware.

    Raise this exception in a middleware's `before()` method to skip
    the step's execution entirely. This is useful for caching, conditional
    execution, or short-circuiting based on context.

    Attributes:
        None

    Example:
        >>> class CacheMiddleware(Middleware):
        ...     async def before(self, ctx: ChainContext, step_name: str) -> None:
        ...         if self._is_cached(step_name, ctx):
        ...             ctx.set("result", self._get_cached(step_name, ctx))
        ...             raise SkipStep()  # Step will not execute

    Note:
        When SkipStep is raised, the step's main function is not called,
        but after() hooks of middleware that ran before this one will
        still be called in reverse order.

    See Also:
        Middleware.before(): Where SkipStep should be raised.
    """
    pass


class Middleware(ABC):
    """
    Abstract base class for AgentOrchestrator middleware.

    Middleware provides hooks to intercept step execution at various points:
    - before(): Called before step execution (can skip step)
    - after(): Called after successful step execution
    - on_error(): Called when a step fails with an exception

    Middleware is executed in priority order (lower numbers run first).
    For after() hooks, execution is reversed (highest priority last).

    Attributes:
        _ao_middleware (bool): Marker identifying this as AO middleware.
        _ao_priority (int): Execution priority (lower = earlier). Default: 100.
        _ao_applies_to (list[str] | None): Step names/patterns to apply to. None = all steps.
        _ao_excludes (list[str] | None): Step names/patterns to exclude.
        _ao_applies_when (Callable | None): Conditional function for dynamic filtering.

    Methods:
        before(): Pre-execution hook. Override to add pre-processing.
        after(): Post-execution hook. Override to add post-processing.
        on_error(): Error handling hook. Override to handle/log errors.
        should_apply(): Check if middleware applies to a given step.

    Example:
        >>> from agentorchestrator.middleware import Middleware
        >>>
        >>> class TimingMiddleware(Middleware):
        ...     def __init__(self):
        ...         super().__init__(priority=10)  # Run early
        ...         self._timings = {}
        ...
        ...     async def before(self, ctx: ChainContext, step_name: str) -> None:
        ...         import time
        ...         ctx.set(f"_timing_{step_name}", time.perf_counter())
        ...
        ...     async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        ...         import time
        ...         start = ctx.get(f"_timing_{step_name}")
        ...         self._timings[step_name] = time.perf_counter() - start

    Selective Application:
        >>> # Only apply to specific steps
        >>> class DataValidationMiddleware(Middleware):
        ...     def __init__(self):
        ...         super().__init__(
        ...             priority=50,
        ...             applies_to=["fetch_data", "transform_data"],
        ...         )

    Glob Pattern Matching:
        >>> # Apply to all steps matching pattern
        >>> class GatherMiddleware(Middleware):
        ...     def __init__(self):
        ...         super().__init__(
        ...             applies_to=["gather_*", "fetch_*"],  # Glob patterns
        ...             excludes=["*_final", "fetch_summary"],  # Exclusions
        ...         )

    Conditional Application:
        >>> # Apply based on runtime conditions
        >>> class LargeOutputMiddleware(Middleware):
        ...     def __init__(self):
        ...         super().__init__(
        ...             applies_when=lambda ctx, result: result.token_count > 2000,
        ...         )

    See Also:
        SkipStep: Exception to skip step execution.
        CompositeMiddleware: Combine multiple middleware.
        RateLimiterMiddleware: Rate limiting implementation.
    """

    _ao_middleware = True
    _ao_priority = 100
    _ao_applies_to: list[str] | None = None
    _ao_excludes: list[str] | None = None
    _ao_applies_when: Callable[[ChainContext, Any], bool] | None = None

    def __init__(
        self,
        priority: int = 100,
        applies_to: list[str] | None = None,
        excludes: list[str] | None = None,
        applies_when: Callable[[ChainContext, Any], bool] | None = None,
    ):
        """
        Initialize the middleware with optional configuration.

        Args:
            priority (int): Execution priority. Lower values run earlier
                in before() and later in after(). Default: 100.
                Typical ranges:
                - 1-10: Critical (circuit breaker, auth)
                - 10-50: High (rate limiting, validation)
                - 50-100: Normal (logging, metrics)
                - 100+: Low (cleanup, reporting)
            applies_to (list[str] | None): List of step names or glob patterns
                this middleware applies to. Supports Unix shell-style wildcards:
                - `*` matches everything
                - `?` matches any single character
                - `[seq]` matches any character in seq
                - `[!seq]` matches any character not in seq
                If None, applies to all steps. Default: None.
            excludes (list[str] | None): List of step names or glob patterns to
                exclude from application. Exclusions are checked first and take
                precedence over applies_to. Default: None.
            applies_when (Callable | None): Optional function that receives
                (ctx: ChainContext, result: Any) and returns bool. When provided,
                middleware only applies if this returns True. Useful for
                conditional application based on runtime state. Default: None.

        Example:
            >>> # High priority, all steps
            >>> middleware = Middleware(priority=10)
            >>>
            >>> # Normal priority, specific steps
            >>> middleware = Middleware(
            ...     priority=50,
            ...     applies_to=["fetch_news", "fetch_sec"],
            ... )
            >>>
            >>> # Glob patterns with exclusions
            >>> middleware = Middleware(
            ...     applies_to=["gather_*", "research_*"],
            ...     excludes=["gather_final", "*_summary"],
            ... )
            >>>
            >>> # Conditional application
            >>> middleware = Middleware(
            ...     applies_to=["*"],
            ...     applies_when=lambda ctx, result: getattr(result, 'token_count', 0) > 2000,
            ... )
        """
        self._ao_priority = priority
        self._ao_applies_to = applies_to
        self._ao_excludes = excludes or []
        self._ao_applies_when = applies_when

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Called before step execution.

        Override this method to add pre-processing logic such as:
        - Validation of context/inputs
        - Rate limiting checks
        - Cache lookup (raise SkipStep if cached)
        - Logging/tracing
        - Setting up resources

        Args:
            ctx (ChainContext): The chain execution context. Use ctx.get()
                and ctx.set() to read/write values.
            step_name (str): Name of the step about to execute.

        Raises:
            SkipStep: Raise to skip this step's execution entirely.
            Exception: Any other exception will abort the chain.

        Example:
            >>> async def before(self, ctx: ChainContext, step_name: str) -> None:
            ...     # Validate required context
            ...     if not ctx.get("query"):
            ...         raise ValueError(f"Step {step_name} requires 'query' in context")
            ...
            ...     # Log start
            ...     logger.info(f"Starting step: {step_name}")

        See Also:
            SkipStep: Exception to skip execution.
            after(): Called after successful execution.
        """
        pass

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Called after successful step execution.

        Override this method to add post-processing logic such as:
        - Logging completion/metrics
        - Caching results
        - Validation of outputs
        - Cleanup of resources
        - Transforming results

        Note: after() hooks run in reverse priority order (highest priority
        middleware runs last), allowing proper cleanup ordering.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that executed.
            result (StepResult): The step's execution result containing:
                - step_name: Name of the step
                - output: The step's return value
                - success: Whether execution succeeded
                - duration_ms: Execution time in milliseconds
                - error: Error details if failed

        Example:
            >>> async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
            ...     # Log completion
            ...     logger.info(f"Step {step_name} completed in {result.duration_ms}ms")
            ...
            ...     # Cache result
            ...     if result.success:
            ...         self._cache[step_name] = result.output

        See Also:
            before(): Called before execution.
            on_error(): Called on failure.
        """
        pass

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """
        Called when a step fails with an exception.

        Override this method to add error handling logic such as:
        - Logging errors
        - Cleanup of partial state
        - Error transformation
        - Alerting/notifications
        - Circuit breaker updates

        Note: on_error() is called after the exception is caught but before
        it propagates. You cannot prevent propagation from here.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that failed.
            error (Exception): The exception that was raised.

        Example:
            >>> async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
            ...     # Log error details
            ...     logger.error(f"Step {step_name} failed: {error}")
            ...
            ...     # Record for circuit breaker
            ...     self._failure_counts[step_name] = self._failure_counts.get(step_name, 0) + 1
            ...
            ...     # Cleanup partial state
            ...     ctx.delete(f"{step_name}_partial_result")

        See Also:
            after(): Called on success.
            CircuitBreakerMiddleware: Circuit breaker implementation.
        """
        pass

    def should_apply(
        self,
        step_name: str,
        ctx: ChainContext | None = None,
        result: Any = None,
    ) -> bool:
        """
        Check if this middleware should apply to a given step.

        This method is called before each hook (before, after, on_error)
        to determine if the middleware should process this step.

        Evaluation order:
        1. Check excludes patterns (if any match, return False)
        2. Check applies_to patterns (if specified and none match, return False)
        3. Check applies_when condition (if specified and returns False, return False)
        4. Return True

        Args:
            step_name (str): Name of the step to check.
            ctx (ChainContext | None): The chain context (for applies_when).
            result (Any | None): The step result (for applies_when in after hooks).

        Returns:
            bool: True if middleware should apply, False to skip.

        Example:
            >>> # Default behavior (applies_to=None means all steps)
            >>> middleware = Middleware()
            >>> middleware.should_apply("any_step")  # True
            >>>
            >>> # Selective application with exact match
            >>> middleware = Middleware(applies_to=["fetch_data", "process"])
            >>> middleware.should_apply("fetch_data")  # True
            >>> middleware.should_apply("other_step")  # False
            >>>
            >>> # Glob pattern matching
            >>> middleware = Middleware(applies_to=["gather_*", "fetch_*"])
            >>> middleware.should_apply("gather_news")  # True
            >>> middleware.should_apply("gather_sec")   # True
            >>> middleware.should_apply("process_data") # False
            >>>
            >>> # With exclusions
            >>> middleware = Middleware(
            ...     applies_to=["gather_*"],
            ...     excludes=["gather_final"],
            ... )
            >>> middleware.should_apply("gather_news")  # True
            >>> middleware.should_apply("gather_final") # False (excluded)

        Note:
            Override this method for custom filtering logic beyond
            patterns and conditions.
        """
        # Step 1: Check excludes first (explicit exclusion wins)
        if self._ao_excludes:
            for pattern in self._ao_excludes:
                if self._matches_pattern(step_name, pattern):
                    return False

        # Step 2: Check applies_to patterns
        if self._ao_applies_to is not None:
            matched = any(
                self._matches_pattern(step_name, pattern)
                for pattern in self._ao_applies_to
            )
            if not matched:
                return False

        # Step 3: Check applies_when condition
        if self._ao_applies_when is not None:
            try:
                if not self._ao_applies_when(ctx, result):
                    return False
            except Exception:
                # If condition check fails, default to applying
                pass

        return True

    def _matches_pattern(self, step_name: str, pattern: str) -> bool:
        """
        Check if step_name matches a pattern.

        Supports both exact matches and Unix shell-style glob patterns:
        - `*` matches everything
        - `?` matches any single character
        - `[seq]` matches any character in seq
        - `[!seq]` matches any character not in seq

        Args:
            step_name: The step name to check.
            pattern: The pattern to match against.

        Returns:
            bool: True if step_name matches the pattern.

        Example:
            >>> middleware._matches_pattern("gather_news", "gather_*")  # True
            >>> middleware._matches_pattern("gather_news", "gather_news")  # True
            >>> middleware._matches_pattern("fetch_data", "gather_*")  # False
        """
        # First try exact match (faster)
        if pattern == step_name:
            return True

        # Then try glob pattern
        return fnmatch.fnmatch(step_name, pattern)


class CompositeMiddleware(Middleware):
    """
    Combines multiple middleware into a single middleware unit.

    CompositeMiddleware allows you to group related middleware together
    and manage them as a single unit. Middleware within the composite
    are sorted by priority and executed in order.

    Attributes:
        _middleware (list[Middleware]): Sorted list of middleware components.

    Methods:
        before(): Calls before() on all component middleware in priority order.
        after(): Calls after() on all component middleware in reverse order.
        on_error(): Calls on_error() on all component middleware.

    Example:
        >>> from agentorchestrator.middleware import CompositeMiddleware
        >>>
        >>> # Group related middleware
        >>> data_protection = CompositeMiddleware([
        ...     RateLimiterMiddleware(default_config=RateLimitConfig(rps=10)),
        ...     CircuitBreakerMiddleware(default_config=MiddlewareCircuitBreakerConfig()),
        ... ])
        >>>
        >>> # Register as single unit
        >>> ao.use(data_protection)

    Execution Order:
        - before(): Low priority (1) -> High priority (100)
        - after(): High priority (100) -> Low priority (1) [reversed]
        - on_error(): Low priority (1) -> High priority (100)

    See Also:
        Middleware: Base middleware class.
        RateLimitAndCircuitBreakerMiddleware: Pre-built composite.
    """

    def __init__(self, middleware_list: list[Middleware]):
        """
        Initialize composite with a list of middleware to combine.

        Args:
            middleware_list (list[Middleware]): List of middleware components.
                Will be sorted by priority (lower priority values first).

        Example:
            >>> composite = CompositeMiddleware([
            ...     LoggerMiddleware(priority=100),
            ...     CacheMiddleware(priority=50),
            ...     ValidationMiddleware(priority=10),
            ... ])
            >>> # Execution order: Validation -> Cache -> Logger
        """
        super().__init__()
        self._middleware = sorted(middleware_list, key=lambda m: m._ao_priority)

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Call before() on all component middleware in priority order.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step about to execute.

        Raises:
            SkipStep: If any component raises SkipStep.
            Exception: If any component raises an exception.
        """
        for mw in self._middleware:
            if mw.should_apply(step_name, ctx=ctx):
                await mw.before(ctx, step_name)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Call after() on all component middleware in reverse priority order.

        This ensures proper cleanup ordering (last to initialize = first to cleanup).

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that executed.
            result (StepResult): The step's execution result.
        """
        # Run in reverse order for after hooks
        for mw in reversed(self._middleware):
            if mw.should_apply(step_name, ctx=ctx, result=result):
                await mw.after(ctx, step_name, result)

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """
        Call on_error() on all component middleware in priority order.

        Args:
            ctx (ChainContext): The chain execution context.
            step_name (str): Name of the step that failed.
            error (Exception): The exception that was raised.
        """
        for mw in self._middleware:
            if mw.should_apply(step_name, ctx=ctx):
                await mw.on_error(ctx, step_name, error)
