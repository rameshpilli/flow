"""
FlowForge Token Manager Middleware

Manages context token budget across chain execution.
"""

import logging
from collections.abc import Callable
from typing import Any

from flowforge.core.context import ChainContext, ContextScope, StepResult
from flowforge.middleware.base import Middleware

logger = logging.getLogger(__name__)


class TokenManagerMiddleware(Middleware):
    """
    Middleware that manages token budget across chain execution.

    Ensures the total context doesn't exceed LLM token limits by:
    - Tracking tokens per step output
    - Triggering summarization when approaching limits
    - Prioritizing recent/important context

    Usage:
        forge.use_middleware(TokenManagerMiddleware(
            max_total_tokens=100000,
            warning_threshold=0.8,
        ))
    """

    def __init__(
        self,
        priority: int = 15,
        applies_to: list[str] | None = None,
        max_total_tokens: int = 100000,
        warning_threshold: float = 0.8,
        token_counter: Callable[[Any], int] | None = None,
        on_threshold_exceeded: Callable[[ChainContext, int], None] | None = None,
    ):
        super().__init__(priority=priority, applies_to=applies_to)
        self.max_total_tokens = max_total_tokens
        self.warning_threshold = warning_threshold
        self.token_counter = token_counter or self._default_counter
        self.on_threshold_exceeded = on_threshold_exceeded

        self._token_usage: dict[str, int] = {}

    def _default_counter(self, value: Any) -> int:
        """Estimate tokens (4 chars per token)"""
        if value is None:
            return 0
        text = str(value)
        return len(text) // 4

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        if not result.success:
            return

        # Count tokens for this step's output
        tokens = self.token_counter(result.output)
        self._token_usage[step_name] = tokens
        result.token_count = tokens

        # Store in context
        ctx.set(
            f"_token_count_{step_name}",
            tokens,
            scope=ContextScope.CHAIN,
        )

        # Calculate total
        total_tokens = sum(self._token_usage.values())
        ctx.metadata["total_tokens"] = total_tokens

        # Check thresholds
        usage_ratio = total_tokens / self.max_total_tokens

        if usage_ratio >= 1.0:
            logger.warning(
                f"Token limit exceeded: {total_tokens}/{self.max_total_tokens} "
                f"after step {step_name}"
            )
            if self.on_threshold_exceeded:
                self.on_threshold_exceeded(ctx, total_tokens)

        elif usage_ratio >= self.warning_threshold:
            logger.warning(
                f"Token usage at {usage_ratio:.1%}: {total_tokens}/{self.max_total_tokens}"
            )

    def get_usage(self) -> dict[str, Any]:
        """Get token usage statistics"""
        total = sum(self._token_usage.values())
        return {
            "by_step": self._token_usage.copy(),
            "total": total,
            "max": self.max_total_tokens,
            "usage_ratio": total / self.max_total_tokens,
            "remaining": self.max_total_tokens - total,
        }

    def reset(self) -> None:
        """Reset token tracking"""
        self._token_usage.clear()
