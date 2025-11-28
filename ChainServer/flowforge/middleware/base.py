"""
FlowForge Base Middleware

Provides the base class and interface for middleware components.
"""

from abc import ABC

from flowforge.core.context import ChainContext, StepResult


class Middleware(ABC):
    """
    Base class for FlowForge middleware.

    Middleware can intercept step execution at various points:
    - before: Called before step execution
    - after: Called after step execution (with result)
    - on_error: Called when a step fails

    Usage:
        class MyMiddleware(Middleware):
            async def before(self, ctx: ChainContext, step_name: str):
                print(f"Starting: {step_name}")

            async def after(self, ctx: ChainContext, step_name: str, result: StepResult):
                print(f"Completed: {step_name} in {result.duration_ms}ms")
    """

    _flowforge_middleware = True
    _flowforge_priority = 100
    _flowforge_applies_to: list[str] | None = None

    def __init__(self, priority: int = 100, applies_to: list[str] | None = None):
        """
        Initialize middleware.

        Args:
            priority: Execution priority (lower = earlier)
            applies_to: List of step names to apply to (None = all)
        """
        self._flowforge_priority = priority
        self._flowforge_applies_to = applies_to

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Called before step execution.

        Override this to add pre-processing logic.

        Args:
            ctx: The chain context
            step_name: Name of the step about to execute
        """
        pass

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Called after step execution.

        Override this to add post-processing logic.

        Args:
            ctx: The chain context
            step_name: Name of the step that executed
            result: The step execution result
        """
        pass

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """
        Called when a step fails.

        Override this to add error handling logic.

        Args:
            ctx: The chain context
            step_name: Name of the step that failed
            error: The exception that occurred
        """
        pass

    def should_apply(self, step_name: str) -> bool:
        """Check if this middleware should apply to a step"""
        if self._flowforge_applies_to is None:
            return True
        return step_name in self._flowforge_applies_to


class CompositeMiddleware(Middleware):
    """
    Combines multiple middleware into one.

    Usage:
        composite = CompositeMiddleware([
            LoggerMiddleware(),
            CacheMiddleware(),
        ])
    """

    def __init__(self, middleware_list: list[Middleware]):
        super().__init__()
        self._middleware = sorted(middleware_list, key=lambda m: m._flowforge_priority)

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        for mw in self._middleware:
            if mw.should_apply(step_name):
                await mw.before(ctx, step_name)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        # Run in reverse order for after hooks
        for mw in reversed(self._middleware):
            if mw.should_apply(step_name):
                await mw.after(ctx, step_name, result)

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        for mw in self._middleware:
            if mw.should_apply(step_name):
                await mw.on_error(ctx, step_name, error)
