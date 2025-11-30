"""
AgentOrchestrator Token Manager Middleware

Manages context token budget across chain execution with automatic
summarization and offloading when thresholds are exceeded.

Features:
- Track tokens per step
- Auto-trigger summarization when approaching limits
- Auto-offload to Redis when over limit
- NEVER lose data - offload preserves full payloads
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agentorchestrator.core.context import ChainContext, ContextScope, StepResult
from agentorchestrator.middleware.base import Middleware

if TYPE_CHECKING:
    from agentorchestrator.core.context_store import ContextStore
    from agentorchestrator.middleware.summarizer import SummarizerMiddleware

logger = logging.getLogger(__name__)


class TokenManagerMiddleware(Middleware):
    """
    Middleware that manages token budget across chain execution.

    Ensures the total context doesn't exceed LLM token limits by:
    - Tracking tokens per step output
    - Triggering summarization when approaching limits
    - Auto-offloading large data to Redis (NEVER loses data)
    - Prioritizing recent/important context

    Enhanced Features:
    - Hook to SummarizerMiddleware for auto-summarization
    - Hook to ContextStore for auto-offloading
    - Loss-aware: always preserves key fields and metadata

    Usage:
        # Basic usage
        forge.use(TokenManagerMiddleware(
            max_total_tokens=100000,
            warning_threshold=0.8,
        ))

        # With auto-summarization and offloading
        from agentorchestrator.core.context_store import RedisContextStore

        store = RedisContextStore(port=6380)
        summarizer = SummarizerMiddleware(...)

        forge.use(TokenManagerMiddleware(
            max_total_tokens=100000,
            warning_threshold=0.8,
            auto_summarize=True,
            summarizer=summarizer,
            auto_offload=True,
            context_store=store,
            offload_threshold_bytes=50000,
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
        # Auto-summarization
        auto_summarize: bool = False,
        summarizer: "SummarizerMiddleware | None" = None,
        summarize_oldest_first: bool = True,
        # Auto-offloading
        auto_offload: bool = False,
        context_store: "ContextStore | None" = None,
        offload_threshold_bytes: int = 50000,
    ):
        super().__init__(priority=priority, applies_to=applies_to)
        self.max_total_tokens = max_total_tokens
        self.warning_threshold = warning_threshold
        self.token_counter = token_counter or self._default_counter
        self.on_threshold_exceeded = on_threshold_exceeded

        # Auto-summarization config
        self.auto_summarize = auto_summarize
        self.summarizer = summarizer
        self.summarize_oldest_first = summarize_oldest_first

        # Auto-offloading config
        self.auto_offload = auto_offload
        self.context_store = context_store
        self.offload_threshold_bytes = offload_threshold_bytes

        self._token_usage: dict[str, int] = {}
        self._step_order: list[str] = []  # Track step execution order

    def _default_counter(self, value: Any) -> int:
        """Estimate tokens (4 chars per token)"""
        if value is None:
            return 0
        text = str(value)
        return len(text) // 4

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        if not result.success:
            return

        # Track step execution order
        if step_name not in self._step_order:
            self._step_order.append(step_name)

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

            # Auto-offload large payloads to Redis if configured
            if self.auto_offload and self.context_store:
                await self._auto_offload_large_steps(ctx)

            # Auto-summarize oldest steps if configured
            if self.auto_summarize and self.summarizer:
                await self._auto_summarize_steps(ctx, total_tokens)

            # Custom callback
            if self.on_threshold_exceeded:
                self.on_threshold_exceeded(ctx, total_tokens)

        elif usage_ratio >= self.warning_threshold:
            logger.warning(
                f"Token usage at {usage_ratio:.1%}: {total_tokens}/{self.max_total_tokens}"
            )

            # Pre-emptive auto-offload when approaching limit
            if self.auto_offload and self.context_store and usage_ratio >= 0.9:
                await self._auto_offload_large_steps(ctx)

    async def _auto_offload_large_steps(self, ctx: ChainContext) -> None:
        """
        Auto-offload large step outputs to Redis context store.

        NEVER loses data - full payloads preserved in Redis, replaced with refs.
        """
        from agentorchestrator.core.context_store import is_context_ref

        offloaded_count = 0

        for step_name in self._step_order:
            step_data = ctx.get(step_name)
            if step_data is None or is_context_ref(step_data):
                continue

            # Estimate size
            size = self._estimate_size(step_data)
            if size < self.offload_threshold_bytes:
                continue

            logger.info(
                f"TokenManager: Auto-offloading '{step_name}' "
                f"({size} bytes > {self.offload_threshold_bytes} threshold)"
            )

            # Store in Redis
            ref = await self.context_store.store(
                key=step_name,
                data=step_data,
                summary=f"Auto-offloaded from {step_name} ({size} bytes)",
                source_step=step_name,
            )

            # Replace in context
            ctx.set(step_name, ref, scope=ContextScope.CHAIN)
            offloaded_count += 1

            # Recount tokens
            self._token_usage[step_name] = self.token_counter(ref)

        if offloaded_count:
            logger.info(f"TokenManager: Auto-offloaded {offloaded_count} step(s) to Redis")

    async def _auto_summarize_steps(self, ctx: ChainContext, total_tokens: int) -> None:
        """
        Auto-summarize steps to reduce token count.

        Summarizes oldest steps first (if summarize_oldest_first=True).
        """
        target_tokens = int(self.max_total_tokens * self.warning_threshold)
        tokens_to_reduce = total_tokens - target_tokens

        if tokens_to_reduce <= 0:
            return

        # Get steps in order (oldest first or newest first)
        steps_to_check = (
            self._step_order if self.summarize_oldest_first else self._step_order[::-1]
        )

        tokens_reduced = 0

        for step_name in steps_to_check:
            if tokens_reduced >= tokens_to_reduce:
                break

            step_tokens = self._token_usage.get(step_name, 0)
            if step_tokens < 1000:  # Don't bother with small steps
                continue

            step_data = ctx.get(step_name)
            if step_data is None:
                continue

            # Skip if already summarized or is a ContextRef
            from agentorchestrator.core.context_store import is_context_ref
            if is_context_ref(step_data):
                continue

            logger.info(
                f"TokenManager: Auto-summarizing '{step_name}' "
                f"({step_tokens} tokens, need to reduce {tokens_to_reduce - tokens_reduced})"
            )

            # Summarize the step output
            try:
                summarized = await self.summarizer.summarize(
                    str(step_data),
                    max_tokens=step_tokens // 2,
                )

                # Update context
                ctx.set(
                    f"_original_{step_name}",
                    step_data,
                    scope=ContextScope.CHAIN,
                )
                ctx.set(step_name, summarized, scope=ContextScope.CHAIN)

                # Recount
                new_tokens = self.token_counter(summarized)
                tokens_saved = step_tokens - new_tokens
                self._token_usage[step_name] = new_tokens
                tokens_reduced += tokens_saved

                logger.info(
                    f"TokenManager: Summarized '{step_name}': "
                    f"{step_tokens} -> {new_tokens} tokens (saved {tokens_saved})"
                )

            except Exception as e:
                logger.error(f"TokenManager: Failed to summarize '{step_name}': {e}")

    def _estimate_size(self, data: Any) -> int:
        """Estimate serialized size of data."""
        import json
        try:
            return len(json.dumps(data, default=str).encode())
        except (TypeError, ValueError):
            return len(str(data).encode())

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
