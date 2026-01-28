"""
AgentOrchestrator Token Manager Middleware

Manages context token budget across chain execution with automatic
summarization and offloading when thresholds are exceeded.

Features:
- Track tokens per step
- Reserve tokens for output, system prompts, and history
- Auto-trigger summarization when approaching limits
- Auto-offload to Redis when over limit
- NEVER lose data - offload preserves full payloads

Token Budget Reservation:
- context_window: Total LLM context window (e.g., 128K for GPT-4)
- reserved_output: Tokens reserved for model response
- reserved_system: Tokens reserved for system prompt and tools
- reserved_history: Tokens reserved for conversation history
- available_for_content: What's left for step outputs
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from agentorchestrator.core.context import ChainContext, ContextScope, StepResult
from agentorchestrator.middleware.base import Middleware

if TYPE_CHECKING:
    from agentorchestrator.core.context_store import ContextStore
    from agentorchestrator.middleware.summarizer import SummarizerMiddleware

logger = logging.getLogger(__name__)


class BudgetStatus(Enum):
    """Token budget status levels."""

    OK = "ok"                # Under warning threshold
    WARNING = "warning"      # Above warning threshold, below critical
    CRITICAL = "critical"    # Above critical threshold, below overflow
    OVERFLOW = "overflow"    # Exceeded available budget


@dataclass
class TokenBudget:
    """
    Token budget configuration with explicit reservations.

    Instead of using a single max_total_tokens, this breaks down
    the context window into explicit reservations to prevent
    silent truncation of model outputs.

    Attributes:
        context_window: Total LLM context window size (e.g., 128000 for GPT-4-turbo)
        reserved_output: Tokens reserved for model response (e.g., 8000)
        reserved_system: Tokens reserved for system prompt and tools (e.g., 3000)
        reserved_history: Tokens reserved for conversation history (e.g., 10000)
        warning_threshold: Ratio of available_for_content at which to warn (default: 0.8)
        critical_threshold: Ratio at which to force compression (default: 0.95)

    Example:
        >>> budget = TokenBudget(
        ...     context_window=128000,
        ...     reserved_output=8000,
        ...     reserved_system=3000,
        ...     reserved_history=15000,
        ... )
        >>> budget.available_for_content
        102000
        >>> budget.get_status(80000)
        <BudgetStatus.OK: 'ok'>
        >>> budget.get_status(95000)
        <BudgetStatus.WARNING: 'warning'>
    """

    context_window: int = 128000
    reserved_output: int = 8000
    reserved_system: int = 3000
    reserved_history: int = 10000
    warning_threshold: float = 0.8
    critical_threshold: float = 0.95

    @property
    def available_for_content(self) -> int:
        """
        Calculate tokens available for step outputs.

        Returns:
            int: context_window - reserved_output - reserved_system - reserved_history
        """
        return (
            self.context_window
            - self.reserved_output
            - self.reserved_system
            - self.reserved_history
        )

    def get_status(self, current_content_tokens: int) -> BudgetStatus:
        """
        Get budget status based on current token usage.

        Args:
            current_content_tokens: Current tokens used by step outputs.

        Returns:
            BudgetStatus: OK, WARNING, CRITICAL, or OVERFLOW.
        """
        if self.available_for_content <= 0:
            return BudgetStatus.OVERFLOW

        ratio = current_content_tokens / self.available_for_content

        if ratio > 1.0:
            return BudgetStatus.OVERFLOW
        elif ratio > self.critical_threshold:
            return BudgetStatus.CRITICAL
        elif ratio > self.warning_threshold:
            return BudgetStatus.WARNING
        return BudgetStatus.OK

    def tokens_to_compress(self, current: int, target_ratio: float = 0.7) -> int:
        """
        Calculate how many tokens to compress to reach target ratio.

        Args:
            current: Current token count.
            target_ratio: Target ratio of available_for_content (default: 0.7).

        Returns:
            int: Number of tokens to compress (0 if already under target).
        """
        target = int(self.available_for_content * target_ratio)
        return max(0, current - target)

    def get_report(self, current_content_tokens: int) -> dict[str, Any]:
        """
        Generate a detailed budget report.

        Args:
            current_content_tokens: Current tokens used by step outputs.

        Returns:
            dict: Comprehensive budget status report.
        """
        status = self.get_status(current_content_tokens)
        available = self.available_for_content
        usage_ratio = current_content_tokens / available if available > 0 else 1.0

        return {
            "context_window": self.context_window,
            "allocated": {
                "output_reserved": self.reserved_output,
                "system_reserved": self.reserved_system,
                "history_reserved": self.reserved_history,
                "content_available": available,
            },
            "current_usage": {
                "content_tokens": current_content_tokens,
                "remaining": max(0, available - current_content_tokens),
            },
            "usage_ratio": round(usage_ratio, 3),
            "usage_percent": round(usage_ratio * 100, 1),
            "status": status.value,
            "action_needed": status in (BudgetStatus.CRITICAL, BudgetStatus.OVERFLOW),
            "tokens_to_compress": self.tokens_to_compress(current_content_tokens)
            if status in (BudgetStatus.CRITICAL, BudgetStatus.OVERFLOW)
            else 0,
        }

    @classmethod
    def from_max_tokens(
        cls,
        max_total_tokens: int,
        output_ratio: float = 0.08,
        system_ratio: float = 0.03,
        history_ratio: float = 0.10,
    ) -> "TokenBudget":
        """
        Create TokenBudget from legacy max_total_tokens parameter.

        This provides backwards compatibility with the old configuration style.

        Args:
            max_total_tokens: Legacy max_total_tokens value.
            output_ratio: Ratio to reserve for output (default: 8%).
            system_ratio: Ratio to reserve for system (default: 3%).
            history_ratio: Ratio to reserve for history (default: 10%).

        Returns:
            TokenBudget: Configured budget instance.

        Example:
            >>> budget = TokenBudget.from_max_tokens(100000)
            >>> budget.reserved_output
            8000
        """
        return cls(
            context_window=max_total_tokens,
            reserved_output=int(max_total_tokens * output_ratio),
            reserved_system=int(max_total_tokens * system_ratio),
            reserved_history=int(max_total_tokens * history_ratio),
        )


class TokenManagerMiddleware(Middleware):
    """
    Middleware that manages token budget across chain execution.

    Ensures the total context doesn't exceed LLM token limits by:
    - Tracking tokens per step output
    - Reserving tokens for output, system prompts, and history
    - Triggering summarization when approaching limits
    - Auto-offloading large data to Redis (NEVER loses data)
    - Prioritizing recent/important context

    Enhanced Features:
    - TokenBudget for explicit reservation management
    - Hook to SummarizerMiddleware for auto-summarization
    - Hook to ContextStore for auto-offloading
    - Loss-aware: always preserves key fields and metadata
    - Detailed budget reporting

    Usage:
        # Basic usage with explicit budget
        budget = TokenBudget(
            context_window=128000,
            reserved_output=8000,    # For model response
            reserved_system=3000,    # For system prompt
            reserved_history=15000,  # For chat history
        )
        ao.use(TokenManagerMiddleware(budget=budget))

        # Legacy usage (auto-converts to TokenBudget)
        ao.use(TokenManagerMiddleware(
            max_total_tokens=100000,
            warning_threshold=0.8,
        ))

        # With auto-summarization and offloading
        from agentorchestrator.core.context_store import RedisContextStore

        store = RedisContextStore(port=6380)
        summarizer = SummarizerMiddleware(...)

        ao.use(TokenManagerMiddleware(
            budget=TokenBudget(context_window=128000),
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
        excludes: list[str] | None = None,
        # New: Explicit token budget
        budget: TokenBudget | None = None,
        # Legacy: max_total_tokens (converted to budget)
        max_total_tokens: int | None = None,
        warning_threshold: float = 0.8,
        token_counter: Callable[[Any], int] | None = None,
        on_threshold_exceeded: Callable[[ChainContext, int], None] | None = None,
        on_status_change: Callable[[ChainContext, BudgetStatus, dict], None] | None = None,
        # Auto-summarization
        auto_summarize: bool = False,
        summarizer: "SummarizerMiddleware | None" = None,
        summarize_oldest_first: bool = True,
        target_ratio_after_compression: float = 0.7,
        # Auto-offloading
        auto_offload: bool = False,
        context_store: "ContextStore | None" = None,
        offload_threshold_bytes: int = 50000,
    ):
        super().__init__(priority=priority, applies_to=applies_to, excludes=excludes)

        # Initialize budget (prefer explicit budget, fall back to legacy)
        if budget is not None:
            self.budget = budget
        elif max_total_tokens is not None:
            self.budget = TokenBudget.from_max_tokens(max_total_tokens)
            self.budget.warning_threshold = warning_threshold
        else:
            # Default budget
            self.budget = TokenBudget()
            self.budget.warning_threshold = warning_threshold

        # Legacy compatibility
        self.max_total_tokens = self.budget.context_window
        self.warning_threshold = self.budget.warning_threshold

        self.token_counter = token_counter or self._default_counter
        self.on_threshold_exceeded = on_threshold_exceeded
        self.on_status_change = on_status_change

        # Auto-summarization config
        self.auto_summarize = auto_summarize
        self.summarizer = summarizer
        self.summarize_oldest_first = summarize_oldest_first
        self.target_ratio_after_compression = target_ratio_after_compression

        # Auto-offloading config
        self.auto_offload = auto_offload
        self.context_store = context_store
        self.offload_threshold_bytes = offload_threshold_bytes

        self._token_usage: dict[str, int] = {}
        self._step_order: list[str] = []  # Track step execution order
        self._last_status: BudgetStatus = BudgetStatus.OK

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

        # Calculate total and get budget status
        total_tokens = sum(self._token_usage.values())
        status = self.budget.get_status(total_tokens)
        report = self.budget.get_report(total_tokens)

        # Store budget info in context metadata
        ctx.metadata["total_tokens"] = total_tokens
        ctx.metadata["token_budget_status"] = status.value
        ctx.metadata["token_budget_report"] = report

        # Check if status changed
        if status != self._last_status:
            if self.on_status_change:
                self.on_status_change(ctx, status, report)
            self._last_status = status

        # Handle based on status
        if status == BudgetStatus.OVERFLOW:
            logger.warning(
                f"Token budget OVERFLOW: {total_tokens}/{self.budget.available_for_content} "
                f"after step {step_name} (context_window={self.budget.context_window})"
            )

            # Auto-offload large payloads to Redis if configured
            if self.auto_offload and self.context_store:
                await self._auto_offload_large_steps(ctx)

            # Auto-summarize oldest steps if configured
            if self.auto_summarize and self.summarizer:
                await self._auto_summarize_steps(ctx, total_tokens)

            # Custom callback (legacy)
            if self.on_threshold_exceeded:
                self.on_threshold_exceeded(ctx, total_tokens)

        elif status == BudgetStatus.CRITICAL:
            logger.warning(
                f"Token budget CRITICAL: {report['usage_percent']}% "
                f"({total_tokens}/{self.budget.available_for_content}) after step {step_name}"
            )

            # Pre-emptive auto-offload
            if self.auto_offload and self.context_store:
                await self._auto_offload_large_steps(ctx)

            # Force summarization at critical level
            if self.auto_summarize and self.summarizer:
                await self._auto_summarize_steps(ctx, total_tokens)

        elif status == BudgetStatus.WARNING:
            logger.warning(
                f"Token budget WARNING: {report['usage_percent']}% "
                f"({total_tokens}/{self.budget.available_for_content}) after step {step_name}"
            )

    async def _auto_offload_large_steps(self, ctx: ChainContext) -> None:
        """
        Auto-offload large step outputs to Redis context store.

        NEVER loses data - full payloads preserved in Redis, replaced with refs.
        """
        from agentorchestrator.core.context_store import is_context_ref

        offloaded_count = 0

        for step_name in self._step_order:
            step_keys = ctx.keys_for_step(step_name)
            if not step_keys and ctx.has(step_name):
                step_keys = [step_name]

            for key in step_keys:
                step_data = ctx.get(key)
                if step_data is None or is_context_ref(step_data):
                    continue

                # Estimate size
                size = self._estimate_size(step_data)
                if size < self.offload_threshold_bytes:
                    continue

                logger.info(
                    f"TokenManager: Auto-offloading '{step_name}' key '{key}' "
                    f"({size} bytes > {self.offload_threshold_bytes} threshold)"
                )

                # Store in context store
                ref = await self.context_store.store(
                    key=key,
                    data=step_data,
                    summary=f"Auto-offloaded from {step_name}:{key} ({size} bytes)",
                    source_step=step_name,
                )

                # Replace in context (preserve scope when possible)
                entry = ctx.get_entry(key)
                scope = entry.scope if entry else ContextScope.CHAIN
                ctx.set(key, ref, scope=scope)
                offloaded_count += 1

            if step_keys:
                # Recount tokens for this step based on current stored values
                new_tokens = 0
                for key in step_keys:
                    value = ctx.get(key)
                    if value is not None:
                        new_tokens += self.token_counter(value)
                self._token_usage[step_name] = new_tokens

        if offloaded_count:
            logger.info(f"TokenManager: Auto-offloaded {offloaded_count} step(s) to Redis")

    async def _auto_summarize_steps(self, ctx: ChainContext, total_tokens: int) -> None:
        """
        Auto-summarize steps to reduce token count.

        Summarizes oldest steps first (if summarize_oldest_first=True).
        Uses target_ratio_after_compression to determine target token count.
        """
        target_tokens = int(self.budget.available_for_content * self.target_ratio_after_compression)
        tokens_to_reduce = total_tokens - target_tokens

        if tokens_to_reduce <= 0:
            return

        logger.info(
            f"TokenManager: Need to reduce {tokens_to_reduce} tokens "
            f"(current: {total_tokens}, target: {target_tokens})"
        )

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
                f"({step_tokens} tokens, need to reduce {tokens_to_reduce - tokens_reduced} more)"
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

        # Log final result
        new_total = sum(self._token_usage.values())
        new_status = self.budget.get_status(new_total)
        logger.info(
            f"TokenManager: Compression complete. "
            f"Reduced {tokens_reduced} tokens. "
            f"New total: {new_total}/{self.budget.available_for_content} ({new_status.value})"
        )

    def _estimate_size(self, data: Any) -> int:
        """Estimate serialized size of data."""
        import json
        try:
            return len(json.dumps(data, default=str).encode())
        except (TypeError, ValueError):
            return len(str(data).encode())

    def get_usage(self) -> dict[str, Any]:
        """
        Get comprehensive token usage statistics.

        Returns:
            dict: Token usage including per-step breakdown and budget report.
        """
        total = sum(self._token_usage.values())
        report = self.budget.get_report(total)

        return {
            "by_step": self._token_usage.copy(),
            "step_order": self._step_order.copy(),
            "total": total,
            # Budget info
            "budget": {
                "context_window": self.budget.context_window,
                "reserved_output": self.budget.reserved_output,
                "reserved_system": self.budget.reserved_system,
                "reserved_history": self.budget.reserved_history,
                "available_for_content": self.budget.available_for_content,
            },
            "status": report["status"],
            "usage_ratio": report["usage_ratio"],
            "usage_percent": report["usage_percent"],
            "remaining": report["current_usage"]["remaining"],
            "action_needed": report["action_needed"],
            # Legacy compatibility
            "max": self.max_total_tokens,
        }

    def get_budget_report(self) -> dict[str, Any]:
        """
        Get detailed budget report.

        Returns:
            dict: Full budget report with allocations and status.
        """
        total = sum(self._token_usage.values())
        return self.budget.get_report(total)

    def reset(self) -> None:
        """Reset token tracking"""
        self._token_usage.clear()
        self._step_order.clear()
        self._last_status = BudgetStatus.OK
