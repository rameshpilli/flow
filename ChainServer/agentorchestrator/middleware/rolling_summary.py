"""
AgentOrchestrator Rolling Summary Middleware

Maintains a rolling/incremental summary that updates progressively
instead of re-summarizing everything on each update.

This is more efficient for iterative data gathering where:
- Data arrives in batches (pagination, streaming)
- Re-summarizing the full history is wasteful
- Recent context should be preserved in full

Pattern inspired by LangChain's ConversationSummaryBufferMemory.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agentorchestrator.core.context import ChainContext, ContextScope, StepResult
from agentorchestrator.middleware.base import Middleware
from agentorchestrator.middleware.summarizer import count_tokens

if TYPE_CHECKING:
    from agentorchestrator.middleware.summarizer import LangChainSummarizer

logger = logging.getLogger(__name__)


@dataclass
class RollingSummaryState:
    """
    State for a rolling summary.

    Attributes:
        summary: The current rolling summary text.
        token_count: Current token count of the summary.
        sources_included: List of source identifiers included in summary.
        version: Number of times the summary has been updated.
        original_tokens_processed: Total tokens processed (before summarization).
    """

    summary: str = ""
    token_count: int = 0
    sources_included: list[str] = field(default_factory=list)
    version: int = 0
    original_tokens_processed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Export state to dictionary."""
        return {
            "summary": self.summary,
            "token_count": self.token_count,
            "sources_included": self.sources_included.copy(),
            "version": self.version,
            "original_tokens_processed": self.original_tokens_processed,
            "compression_ratio": (
                self.token_count / self.original_tokens_processed
                if self.original_tokens_processed > 0
                else 1.0
            ),
        }


class RollingSummaryMiddleware(Middleware):
    """
    Middleware that maintains rolling summaries for step outputs.

    Instead of re-summarizing the entire history when new data arrives,
    this middleware:
    1. Summarizes only the NEW content
    2. Merges the new summary with the existing rolling summary
    3. Preserves recent content in full while compressing older content

    This is ideal for:
    - Iterative data gathering (pagination, streaming)
    - Long-running conversations
    - Multi-source aggregation

    Usage:
        # Basic usage
        ao.use(RollingSummaryMiddleware(
            max_tokens=4000,
            summarizer=my_summarizer,
            applies_to=["gather_*"],
        ))

        # With recent buffer (keep last N tokens uncompressed)
        ao.use(RollingSummaryMiddleware(
            max_tokens=4000,
            recent_buffer_tokens=1000,  # Keep last 1000 tokens in full
            summarizer=my_summarizer,
            applies_to=["gather_news", "gather_social"],
        ))

    How it works:
        Iteration 1: 15K tokens → summarize → 2K tokens
        Iteration 2: +10K tokens → summarize new only → merge → 3K tokens
        Iteration 3: +8K tokens → summarize new only → merge → 3.5K tokens

        Total processed: 33K tokens
        Final summary: 3.5K tokens (vs 33K if re-summarizing everything)
    """

    def __init__(
        self,
        priority: int = 55,
        applies_to: list[str] | None = None,
        excludes: list[str] | None = None,
        max_tokens: int = 4000,
        summarizer: "LangChainSummarizer | None" = None,
        recent_buffer_tokens: int = 0,
        merge_prompt: str | None = None,
        on_update: Callable[[str, RollingSummaryState], None] | None = None,
    ):
        """
        Initialize the Rolling Summary middleware.

        Args:
            priority: Middleware priority (default: 55, after standard summarizer)
            applies_to: Step name patterns to apply to (supports glob patterns)
            excludes: Step name patterns to exclude
            max_tokens: Maximum tokens for the rolling summary
            summarizer: LangChainSummarizer instance for summarization
            recent_buffer_tokens: Keep this many recent tokens uncompressed.
                Useful for preserving recent context in full.
            merge_prompt: Custom prompt for merging summaries.
            on_update: Callback when summary is updated (step_name, state)
        """
        super().__init__(priority=priority, applies_to=applies_to, excludes=excludes)
        self.max_tokens = max_tokens
        self.summarizer = summarizer
        self.recent_buffer_tokens = recent_buffer_tokens
        self.on_update = on_update

        self.merge_prompt = merge_prompt or self._default_merge_prompt()

        # State per context key (request_id:step_name)
        self._states: dict[str, RollingSummaryState] = {}

    def _default_merge_prompt(self) -> str:
        return """You have an existing summary and new information to incorporate.
Update the summary to include the new information while staying concise.
Preserve all key facts, numbers, dates, and named entities from BOTH sources.

EXISTING SUMMARY:
{existing_summary}

NEW INFORMATION:
{new_content}

UPDATED SUMMARY:"""

    def _get_state_key(self, ctx: ChainContext, step_name: str) -> str:
        """Get the state key for a context/step combination."""
        return f"{ctx.request_id}:{step_name}"

    def _get_or_create_state(
        self, ctx: ChainContext, step_name: str
    ) -> RollingSummaryState:
        """Get or create rolling summary state for a step."""
        key = self._get_state_key(ctx, step_name)
        if key not in self._states:
            self._states[key] = RollingSummaryState()
        return self._states[key]

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Process step output and update rolling summary."""
        if not result.success or result.output is None:
            return

        # Get current state
        state = self._get_or_create_state(ctx, step_name)

        # Convert output to string
        new_content = self._to_string(result.output)
        new_tokens = count_tokens(new_content)

        state.original_tokens_processed += new_tokens

        # Check if we need to summarize
        combined_tokens = state.token_count + new_tokens

        if combined_tokens <= self.max_tokens:
            # No summarization needed, just append
            if state.summary:
                state.summary = f"{state.summary}\n\n{new_content}"
            else:
                state.summary = new_content
            state.token_count = combined_tokens
            state.sources_included.append(f"{step_name}_v{state.version}")
            state.version += 1

            logger.debug(
                f"RollingSummary [{step_name}]: Appended {new_tokens} tokens "
                f"(total: {state.token_count}/{self.max_tokens})"
            )
        else:
            # Need to summarize
            await self._update_summary(ctx, step_name, state, new_content, new_tokens)

        # Store in context
        ctx.set(
            f"{step_name}_rolling_summary",
            state.summary,
            scope=ContextScope.CHAIN,
        )
        ctx.set(
            f"{step_name}_rolling_state",
            state.to_dict(),
            scope=ContextScope.CHAIN,
        )

        # Update result metadata
        result.metadata.update({
            "rolling_summary": True,
            "rolling_version": state.version,
            "rolling_tokens": state.token_count,
            "original_tokens_processed": state.original_tokens_processed,
        })

        # Callback
        if self.on_update:
            self.on_update(step_name, state)

    async def _update_summary(
        self,
        ctx: ChainContext,
        step_name: str,
        state: RollingSummaryState,
        new_content: str,
        new_tokens: int,
    ) -> None:
        """Update the rolling summary with new content."""
        if not self.summarizer:
            # No summarizer, truncate instead
            logger.warning(
                f"RollingSummary [{step_name}]: No summarizer configured, truncating"
            )
            state.summary = new_content[: self.max_tokens * 4]  # Rough char estimate
            state.token_count = count_tokens(state.summary)
            state.version += 1
            return

        logger.info(
            f"RollingSummary [{step_name}]: Updating summary "
            f"(existing: {state.token_count}, new: {new_tokens}, max: {self.max_tokens})"
        )

        # Handle recent buffer
        recent_content = ""
        content_to_summarize = new_content

        if self.recent_buffer_tokens > 0:
            # Keep recent content in full
            recent_tokens = 0
            lines = new_content.split("\n")
            recent_lines = []

            for line in reversed(lines):
                line_tokens = count_tokens(line)
                if recent_tokens + line_tokens <= self.recent_buffer_tokens:
                    recent_lines.insert(0, line)
                    recent_tokens += line_tokens
                else:
                    break

            if recent_lines:
                recent_content = "\n".join(recent_lines)
                # Remove recent content from what needs summarizing
                content_to_summarize = new_content[: -len(recent_content)].strip()

        # Summarize new content if it's large enough
        if count_tokens(content_to_summarize) > self.max_tokens // 2:
            new_summary = await self.summarizer.summarize(
                content_to_summarize,
                max_tokens=self.max_tokens // 3,
            )
        else:
            new_summary = content_to_summarize

        # Merge with existing summary
        if state.summary:
            merged = await self._merge_summaries(state.summary, new_summary)
        else:
            merged = new_summary

        # Add recent buffer back
        if recent_content:
            merged = f"{merged}\n\n[Recent]\n{recent_content}"

        # Final token count
        merged_tokens = count_tokens(merged)

        # If still over limit, compress the merged summary
        if merged_tokens > self.max_tokens:
            logger.info(
                f"RollingSummary [{step_name}]: Merged summary too large "
                f"({merged_tokens} > {self.max_tokens}), compressing"
            )
            merged = await self.summarizer.summarize(
                merged,
                max_tokens=int(self.max_tokens * 0.8),
            )
            merged_tokens = count_tokens(merged)

        # Update state
        state.summary = merged
        state.token_count = merged_tokens
        state.sources_included.append(f"{step_name}_v{state.version}")
        state.version += 1

        logger.info(
            f"RollingSummary [{step_name}]: Updated v{state.version} "
            f"({state.token_count} tokens, "
            f"processed {state.original_tokens_processed} total)"
        )

    async def _merge_summaries(self, existing: str, new: str) -> str:
        """Merge new summary into existing summary."""
        if not self.summarizer:
            return f"{existing}\n\n{new}"

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            chain = (
                ChatPromptTemplate.from_template(self.merge_prompt)
                | self.summarizer.llm
                | StrOutputParser()
            )

            return await chain.ainvoke({
                "existing_summary": existing,
                "new_content": new,
            })
        except Exception as e:
            logger.error(f"Failed to merge summaries: {e}")
            # Fallback to concatenation
            return f"{existing}\n\n{new}"

    def _to_string(self, output: Any) -> str:
        """Convert output to string."""
        import json

        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            return json.dumps(output, indent=2, default=str)
        if hasattr(output, "model_dump"):
            return json.dumps(output.model_dump(), indent=2, default=str)
        return str(output)

    def get_state(self, ctx: ChainContext, step_name: str) -> RollingSummaryState | None:
        """Get the rolling summary state for a step."""
        key = self._get_state_key(ctx, step_name)
        return self._states.get(key)

    def get_summary(self, ctx: ChainContext, step_name: str) -> str | None:
        """Get the current rolling summary for a step."""
        state = self.get_state(ctx, step_name)
        return state.summary if state else None

    def reset(self, ctx: ChainContext | None = None, step_name: str | None = None) -> None:
        """
        Reset rolling summary state.

        Args:
            ctx: If provided with step_name, reset only that state.
                If None, reset all states.
            step_name: Step name to reset (requires ctx).
        """
        if ctx and step_name:
            key = self._get_state_key(ctx, step_name)
            if key in self._states:
                del self._states[key]
        else:
            self._states.clear()

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Get all rolling summary states."""
        return {key: state.to_dict() for key, state in self._states.items()}
