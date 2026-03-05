"""
AgentOrchestrator Memory Lifecycle Middleware
=============================================

Provides automatic memory promotion from session to long-term storage.
This middleware intercepts step results and promotes important content
to persistent memory based on configurable criteria.

Features:
- Automatic importance scoring (LLM-based or heuristic)
- Configurable promotion thresholds
- Pattern detection for user preferences
- Deduplication before promotion
- Batch promotion for efficiency

Usage:
    from agentorchestrator.middleware.memory_lifecycle import (
        MemoryLifecycleMiddleware,
        MemoryLifecycleConfig,
        ImportanceEvaluator,
    )

    # Option 1: Simple heuristic-based promotion
    middleware = MemoryLifecycleMiddleware(
        session_storage=redis_storage,
        longterm_memory=mem0_memory,
        config=MemoryLifecycleConfig(
            importance_threshold=0.8,
            auto_promote_patterns=True,
        ),
    )

    # Option 2: LLM-based importance evaluation
    middleware = MemoryLifecycleMiddleware(
        session_storage=redis_storage,
        longterm_memory=mem0_memory,
        evaluator=LLMImportanceEvaluator(llm_client),
        config=MemoryLifecycleConfig(
            importance_threshold=0.7,
        ),
    )

    ao.use(middleware)

Example:
    >>> @ao.step(name="analyze_preferences")
    ... async def analyze(ctx):
    ...     # This step's output will be evaluated for promotion
    ...     return {"preference": "user likes technical explanations"}
    >>>
    >>> # If importance > threshold, automatically promoted to long-term memory
"""

import asyncio
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware

logger = logging.getLogger(__name__)

__all__ = [
    "MemoryLifecycleMiddleware",
    "MemoryLifecycleConfig",
    "ImportanceEvaluator",
    "HeuristicImportanceEvaluator",
    "LLMImportanceEvaluator",
    "PromotionResult",
    "create_memory_lifecycle_middleware",
]


# ═══════════════════════════════════════════════════════════════════════════════
#                           DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class PromotionResult:
    """Result of a memory promotion attempt."""

    promoted: bool
    """Whether the content was promoted."""

    content: str
    """The content that was evaluated."""

    importance_score: float
    """Importance score (0.0-1.0)."""

    reason: str
    """Reason for promotion/rejection."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata."""

    promoted_at: Optional[datetime] = None
    """Timestamp of promotion (if promoted)."""


@dataclass
class MemoryLifecycleConfig:
    """Configuration for memory lifecycle middleware."""

    importance_threshold: float = 0.8
    """Minimum importance score (0.0-1.0) to promote content."""

    auto_promote_patterns: bool = True
    """Automatically promote detected user patterns/preferences."""

    auto_promote_errors: bool = False
    """Promote error resolutions for future reference."""

    auto_promote_decisions: bool = True
    """Promote important decisions and their rationale."""

    batch_size: int = 10
    """Number of items to batch before promoting."""

    batch_timeout_seconds: float = 60.0
    """Max time to wait before flushing batch."""

    deduplicate: bool = True
    """Check for duplicates before promoting."""

    dedup_similarity_threshold: float = 0.9
    """Similarity threshold for deduplication (0.0-1.0)."""

    enabled: bool = True
    """Enable/disable the middleware."""

    applies_to: list[str] | None = None
    """List of step names to apply to (None = all)."""

    excludes: list[str] | None = None
    """List of step names to exclude."""

    # Content type weights for heuristic scoring
    pattern_weight: float = 0.9
    """Weight for user patterns/preferences."""

    decision_weight: float = 0.85
    """Weight for decisions/choices."""

    error_resolution_weight: float = 0.7
    """Weight for error resolutions."""

    general_weight: float = 0.5
    """Weight for general content."""


# ═══════════════════════════════════════════════════════════════════════════════
#                        IMPORTANCE EVALUATORS
# ═══════════════════════════════════════════════════════════════════════════════


class ImportanceEvaluator(ABC):
    """Abstract base class for importance evaluation."""

    @abstractmethod
    async def evaluate(
        self,
        content: str,
        context: dict[str, Any],
    ) -> tuple[float, str]:
        """
        Evaluate the importance of content.

        Args:
            content: Content to evaluate
            context: Additional context (step_name, user_id, etc.)

        Returns:
            Tuple of (importance_score, reason)
        """
        pass


class HeuristicImportanceEvaluator(ImportanceEvaluator):
    """
    Heuristic-based importance evaluator.

    Uses keyword matching and content analysis to score importance.
    Fast and doesn't require LLM calls.
    """

    # Keywords indicating high-importance content
    PATTERN_KEYWORDS = [
        "prefer", "preference", "like", "dislike", "always", "never",
        "style", "format", "tone", "approach", "method",
    ]

    DECISION_KEYWORDS = [
        "decide", "decision", "chose", "choice", "select", "pick",
        "approve", "reject", "confirm", "finalize",
    ]

    ERROR_KEYWORDS = [
        "fix", "fixed", "resolve", "resolved", "solution", "workaround",
        "error", "issue", "problem", "bug",
    ]

    def __init__(self, config: MemoryLifecycleConfig | None = None):
        self.config = config or MemoryLifecycleConfig()

    async def evaluate(
        self,
        content: str,
        context: dict[str, Any],
    ) -> tuple[float, str]:
        """Evaluate importance using heuristics."""
        content_lower = content.lower()
        scores = []
        reasons = []

        # Check for patterns
        pattern_matches = sum(
            1 for kw in self.PATTERN_KEYWORDS if kw in content_lower
        )
        if pattern_matches > 0:
            score = min(1.0, self.config.pattern_weight + (pattern_matches * 0.05))
            scores.append(score)
            reasons.append(f"pattern_keywords:{pattern_matches}")

        # Check for decisions
        decision_matches = sum(
            1 for kw in self.DECISION_KEYWORDS if kw in content_lower
        )
        if decision_matches > 0:
            score = min(1.0, self.config.decision_weight + (decision_matches * 0.05))
            scores.append(score)
            reasons.append(f"decision_keywords:{decision_matches}")

        # Check for error resolutions
        error_matches = sum(
            1 for kw in self.ERROR_KEYWORDS if kw in content_lower
        )
        if error_matches > 0 and self.config.auto_promote_errors:
            score = min(1.0, self.config.error_resolution_weight + (error_matches * 0.05))
            scores.append(score)
            reasons.append(f"error_keywords:{error_matches}")

        # Content length bonus (longer = potentially more important)
        if len(content) > 200:
            scores.append(self.config.general_weight + 0.1)
            reasons.append("substantial_content")

        # Calculate final score
        if scores:
            final_score = max(scores)  # Take highest category score
            reason = ", ".join(reasons)
        else:
            final_score = self.config.general_weight
            reason = "general_content"

        return final_score, reason


class LLMImportanceEvaluator(ImportanceEvaluator):
    """
    LLM-based importance evaluator.

    Uses an LLM to evaluate the importance of content.
    More accurate but requires LLM calls.
    """

    EVALUATION_PROMPT = """
Evaluate the importance of the following content for long-term memory storage.

CONTENT:
{content}

CONTEXT:
- Step: {step_name}
- User: {user_id}
- Session: {session_id}

Rate the importance from 0.0 to 1.0 based on:
- Is this a user preference or pattern? (high importance)
- Is this a key decision or choice? (high importance)
- Is this an error resolution that could help in the future? (medium importance)
- Is this general information? (low importance)

Respond with JSON:
{{"score": 0.0-1.0, "reason": "brief explanation"}}
"""

    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

    async def evaluate(
        self,
        content: str,
        context: dict[str, Any],
    ) -> tuple[float, str]:
        """Evaluate importance using LLM."""
        prompt = self.EVALUATION_PROMPT.format(
            content=content[:1000],  # Truncate for efficiency
            step_name=context.get("step_name", "unknown"),
            user_id=context.get("user_id", "unknown"),
            session_id=context.get("session_id", "unknown"),
        )

        try:
            response = await self.llm_client.generate_async(
                prompt=prompt,
                system_prompt="You are evaluating content importance. Respond only with valid JSON.",
                max_tokens=100,
            )

            result = json.loads(response)
            return result.get("score", 0.5), result.get("reason", "llm_evaluation")

        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}")
            # Fallback to heuristic
            fallback = HeuristicImportanceEvaluator()
            return await fallback.evaluate(content, context)


# ═══════════════════════════════════════════════════════════════════════════════
#                        MEMORY LIFECYCLE MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════


class MemoryLifecycleMiddleware(Middleware):
    """
    Middleware that manages automatic memory promotion from session to long-term.

    This middleware intercepts step results and evaluates them for importance.
    Content that exceeds the importance threshold is automatically promoted
    to long-term memory for future retrieval.

    Attributes:
        session_storage: Session storage backend (e.g., RedisChatStorage)
        longterm_memory: Long-term memory backend (e.g., Mem0Memory)
        evaluator: Importance evaluator (heuristic or LLM-based)
        config: Configuration options

    Example:
        >>> middleware = MemoryLifecycleMiddleware(
        ...     session_storage=redis_storage,
        ...     longterm_memory=mem0_memory,
        ...     config=MemoryLifecycleConfig(
        ...         importance_threshold=0.8,
        ...         auto_promote_patterns=True,
        ...     ),
        ... )
        >>> ao.use(middleware)
    """

    _ao_priority = 95  # Run late, after most processing

    def __init__(
        self,
        session_storage: Any = None,
        longterm_memory: Any = None,
        evaluator: ImportanceEvaluator | None = None,
        config: MemoryLifecycleConfig | None = None,
        applies_to: list[str] | None = None,
    ):
        """
        Initialize memory lifecycle middleware.

        Args:
            session_storage: Session storage backend
            longterm_memory: Long-term memory backend (must have add() method)
            evaluator: Custom importance evaluator (default: heuristic)
            config: Configuration options
            applies_to: Step names to apply to (overrides config)
        """
        self.session_storage = session_storage
        self.longterm_memory = longterm_memory
        self.config = config or MemoryLifecycleConfig()
        self.evaluator = evaluator or HeuristicImportanceEvaluator(self.config)
        self._ao_applies_to = applies_to or self.config.applies_to

        # Batching state
        self._pending_promotions: list[dict[str, Any]] = []
        self._last_flush_time = time.time()
        self._flush_lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "evaluated": 0,
            "promoted": 0,
            "rejected": 0,
            "duplicates_skipped": 0,
            "avg_importance_score": 0.0,
        }

        # Deduplication cache (content hash -> timestamp)
        self._dedup_cache: dict[str, float] = {}

    def _should_process(self, step_name: str) -> bool:
        """Check if step should be processed."""
        if not self.config.enabled:
            return False

        if self.config.excludes and step_name in self.config.excludes:
            return False

        if self._ao_applies_to and step_name not in self._ao_applies_to:
            return False

        return True

    def _content_hash(self, content: str) -> str:
        """Generate hash for deduplication."""
        return hashlib.md5(content.encode()).hexdigest()

    def _is_duplicate(self, content: str) -> bool:
        """Check if content is a duplicate."""
        if not self.config.deduplicate:
            return False

        content_hash = self._content_hash(content)
        if content_hash in self._dedup_cache:
            self._stats["duplicates_skipped"] += 1
            return True

        return False

    def _mark_promoted(self, content: str) -> None:
        """Mark content as promoted in dedup cache."""
        content_hash = self._content_hash(content)
        self._dedup_cache[content_hash] = time.time()

        # Clean old entries (older than 1 hour)
        cutoff = time.time() - 3600
        self._dedup_cache = {
            k: v for k, v in self._dedup_cache.items() if v > cutoff
        }

    async def after(
        self,
        ctx: ChainContext,
        step_name: str,
        result: StepResult,
    ) -> StepResult:
        """
        Process step result for potential memory promotion.
        """
        if not self._should_process(step_name):
            return result

        if not result.success or not result.output:
            return result

        if not self.longterm_memory:
            logger.debug("No long-term memory configured, skipping promotion")
            return result

        try:
            # Extract content to evaluate
            content = self._extract_content(result.output)
            if not content:
                return result

            # Check for duplicates
            if self._is_duplicate(content):
                logger.debug(f"Duplicate content skipped for {step_name}")
                return result

            # Evaluate importance
            context = {
                "step_name": step_name,
                "user_id": ctx.get("user_id", "unknown"),
                "session_id": ctx.get("session_id", "unknown"),
                "request_id": ctx.request_id,
            }

            importance_score, reason = await self.evaluator.evaluate(content, context)

            # Update stats
            self._stats["evaluated"] += 1
            n = self._stats["evaluated"]
            old_avg = self._stats["avg_importance_score"]
            self._stats["avg_importance_score"] = (old_avg * (n - 1) + importance_score) / n

            # Check threshold
            if importance_score >= self.config.importance_threshold:
                # Add to batch
                await self._add_to_batch({
                    "content": content,
                    "importance_score": importance_score,
                    "reason": reason,
                    "context": context,
                    "timestamp": datetime.now().isoformat(),
                })

                logger.info(
                    f"Queued for promotion: {step_name} "
                    f"(score={importance_score:.2f}, reason={reason})"
                )
            else:
                self._stats["rejected"] += 1
                logger.debug(
                    f"Below threshold: {step_name} "
                    f"(score={importance_score:.2f} < {self.config.importance_threshold})"
                )

        except Exception as e:
            logger.warning(f"Memory lifecycle processing failed for {step_name}: {e}")

        return result

    def _extract_content(self, output: Any) -> str | None:
        """Extract string content from step output."""
        if isinstance(output, str):
            return output

        if isinstance(output, dict):
            # Look for common content keys
            for key in ["content", "text", "message", "result", "output", "summary"]:
                if key in output and isinstance(output[key], str):
                    return output[key]

            # Serialize dict if no specific key found
            try:
                return json.dumps(output, default=str)
            except Exception:
                return str(output)

        return str(output) if output else None

    async def _add_to_batch(self, item: dict[str, Any]) -> None:
        """Add item to pending promotions batch."""
        async with self._flush_lock:
            self._pending_promotions.append(item)

            # Check if we should flush
            should_flush = (
                len(self._pending_promotions) >= self.config.batch_size
                or (time.time() - self._last_flush_time) >= self.config.batch_timeout_seconds
            )

            if should_flush:
                await self._flush_batch()

    async def _flush_batch(self) -> None:
        """Flush pending promotions to long-term memory."""
        if not self._pending_promotions:
            return

        items = self._pending_promotions.copy()
        self._pending_promotions.clear()
        self._last_flush_time = time.time()

        for item in items:
            try:
                content = item["content"]

                # Skip if duplicate
                if self._is_duplicate(content):
                    continue

                # Promote to long-term memory
                metadata = {
                    "source_step": item["context"].get("step_name"),
                    "user_id": item["context"].get("user_id"),
                    "importance_score": item["importance_score"],
                    "promotion_reason": item["reason"],
                    "promoted_at": item["timestamp"],
                }

                await self.longterm_memory.add(content, metadata=metadata)
                self._mark_promoted(content)
                self._stats["promoted"] += 1

                logger.info(f"Promoted to long-term memory: {content[:50]}...")

            except Exception as e:
                logger.error(f"Failed to promote content: {e}")
                self._stats["rejected"] += 1

    async def flush(self) -> None:
        """Manually flush pending promotions."""
        async with self._flush_lock:
            await self._flush_batch()

    def get_stats(self) -> dict[str, Any]:
        """Get middleware statistics."""
        return {
            **self._stats,
            "pending_promotions": len(self._pending_promotions),
            "dedup_cache_size": len(self._dedup_cache),
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = {
            "evaluated": 0,
            "promoted": 0,
            "rejected": 0,
            "duplicates_skipped": 0,
            "avg_importance_score": 0.0,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#                           FACTORY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════


def create_memory_lifecycle_middleware(
    session_storage: Any = None,
    longterm_memory: Any = None,
    llm_client: Any = None,
    importance_threshold: float = 0.8,
    auto_promote_patterns: bool = True,
    applies_to: list[str] | None = None,
) -> MemoryLifecycleMiddleware:
    """
    Factory function to create a MemoryLifecycleMiddleware.

    Args:
        session_storage: Session storage backend
        longterm_memory: Long-term memory backend
        llm_client: LLM client for importance evaluation (optional)
        importance_threshold: Minimum score to promote
        auto_promote_patterns: Automatically promote user patterns
        applies_to: Step names to apply to

    Returns:
        Configured MemoryLifecycleMiddleware

    Example:
        >>> middleware = create_memory_lifecycle_middleware(
        ...     session_storage=redis_storage,
        ...     longterm_memory=mem0_memory,
        ...     llm_client=llm_client,  # Optional: enables LLM-based evaluation
        ...     importance_threshold=0.75,
        ... )
        >>> ao.use(middleware)
    """
    config = MemoryLifecycleConfig(
        importance_threshold=importance_threshold,
        auto_promote_patterns=auto_promote_patterns,
        applies_to=applies_to,
    )

    evaluator: ImportanceEvaluator
    if llm_client:
        evaluator = LLMImportanceEvaluator(llm_client)
    else:
        evaluator = HeuristicImportanceEvaluator(config)

    return MemoryLifecycleMiddleware(
        session_storage=session_storage,
        longterm_memory=longterm_memory,
        evaluator=evaluator,
        config=config,
    )