"""
AgentOrchestrator Offload Middleware - Automatic Large Payload Offloading

Automatically offloads large step outputs to context store (Redis, mem0, etc.),
keeping chain context lightweight while preserving 100% of the data.

Key Principles:
1. NEVER lose data - full payloads preserved in context store
2. NEVER blind-truncate - always keep summaries, key fields, counts
3. Automatic - no manual intervention needed per step
4. Pluggable - register domain-specific extractors at application level

Architecture:
    Step Output (1.2MB)
           │
           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │              Offload Middleware                               │
    │  if size > threshold:                                         │
    │    1. Extract key_fields (via registered extractor)          │
    │    2. Generate summary (via registered generator)            │
    │    3. Store full data in context store                       │
    │    4. Replace output with ContextRef                         │
    └──────────────────────────────────────────────────────────────┘
           │
           ▼
    Context gets ContextRef (500 bytes)
    Store holds full data (1.2MB)

Usage:
    from agentorchestrator.middleware.offload import OffloadMiddleware
    from agentorchestrator.core.context_store import RedisContextStore

    store = RedisContextStore(host="localhost", port=6379)

    middleware = OffloadMiddleware(
        store=store,
        default_threshold_bytes=100_000,  # 100KB
        step_thresholds={
            "fetch_data": 50_000,
        },
    )

    # Register domain-specific extractor (at application level)
    middleware.register_extractor("my_step", my_key_field_extractor)
    middleware.register_generator("my_step", my_summary_generator)

    forge.use(middleware)
"""

import json
import logging
import pickle
from collections.abc import Callable
from typing import Any

from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.core.context_store import (
    ContextStore,
    InMemoryContextStore,
    is_context_ref,
)
from agentorchestrator.middleware.base import Middleware

logger = logging.getLogger(__name__)


# Type aliases for extractors and generators
KeyFieldExtractor = Callable[[Any], dict[str, Any]]
SummaryGenerator = Callable[[Any, dict[str, Any]], str]


# ═══════════════════════════════════════════════════════════════════════════════
#                    DEFAULT EXTRACTORS & GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════


def default_key_field_extractor(data: Any) -> dict[str, Any]:
    """
    Default key field extractor for generic data types.

    Extracts common fields and structural information.
    Override by registering domain-specific extractors.
    """
    key_fields = {}

    if isinstance(data, dict):
        # Extract common fields
        for field in ["id", "name", "type", "date", "count", "total", "status"]:
            if field in data:
                key_fields[field] = data[field]
        key_fields["keys"] = list(data.keys())[:10]
        key_fields["key_count"] = len(data)

    elif isinstance(data, list):
        key_fields["count"] = len(data)
        if len(data) > 0:
            key_fields["item_type"] = type(data[0]).__name__
            if isinstance(data[0], dict):
                key_fields["sample_keys"] = list(data[0].keys())[:5]

    elif isinstance(data, str):
        key_fields["length"] = len(data)

    return key_fields


def default_summary_generator(data: Any, key_fields: dict[str, Any]) -> str:
    """
    Default summary generator for generic data types.

    Override by registering domain-specific generators.
    """
    if isinstance(data, list):
        count = key_fields.get("count", len(data))
        item_type = key_fields.get("item_type", "item")
        return f"{count} {item_type}(s)"

    elif isinstance(data, dict):
        key_count = key_fields.get("key_count", len(data))
        name = key_fields.get("name", "")
        if name:
            return f"{name} (dict with {key_count} keys)"
        return f"Dict with {key_count} keys"

    elif isinstance(data, str):
        length = key_fields.get("length", len(data))
        return f"Text ({length} chars)"

    return f"{type(data).__name__} data"


# ═══════════════════════════════════════════════════════════════════════════════
#                    OFFLOAD MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════


class OffloadMiddleware(Middleware):
    """
    Middleware that automatically offloads large step outputs to context store.

    NEVER loses data - full payloads preserved, only refs in context.

    Features:
    - Configurable size thresholds (global and per-step)
    - Pluggable key field extraction (register domain-specific extractors)
    - Pluggable summary generation (register domain-specific generators)
    - Automatic source tracking

    Usage:
        from agentorchestrator.middleware.offload import OffloadMiddleware
        from agentorchestrator.core.context_store import RedisContextStore

        store = RedisContextStore(host="localhost", port=6379)

        middleware = OffloadMiddleware(
            store=store,
            default_threshold_bytes=100_000,
        )

        # Register domain-specific handlers at application level
        middleware.register_extractor("my_agent", my_extractor_func)
        middleware.register_generator("my_agent", my_generator_func)

        forge.use(middleware)
    """

    def __init__(
        self,
        store: ContextStore | None = None,
        default_threshold_bytes: int = 100_000,  # 100KB
        step_thresholds: dict[str, int] | None = None,
        ttl_seconds: int = 3600,
        priority: int = 90,  # Run late, after step completes
        applies_to: list[str] | None = None,
    ):
        """
        Initialize offload middleware.

        Args:
            store: Context store (Redis, mem0, etc.). Uses InMemory if not provided.
            default_threshold_bytes: Default size threshold for offloading
            step_thresholds: Per-step size thresholds
            ttl_seconds: TTL for stored data
            priority: Middleware priority
            applies_to: Steps to apply to (None = all)
        """
        super().__init__(priority=priority, applies_to=applies_to)
        self._store = store or InMemoryContextStore()
        self._default_threshold = default_threshold_bytes
        self._step_thresholds = step_thresholds or {}
        self._ttl_seconds = ttl_seconds

        # Pluggable extractors and generators
        self._extractors: dict[str, KeyFieldExtractor] = {}
        self._generators: dict[str, SummaryGenerator] = {}

        # Statistics
        self._offload_count = 0
        self._total_bytes_offloaded = 0

    def register_extractor(
        self,
        step_pattern: str,
        extractor: KeyFieldExtractor,
    ) -> "OffloadMiddleware":
        """
        Register a domain-specific key field extractor.

        Args:
            step_pattern: Step name or pattern to match
            extractor: Function that extracts key fields from data

        Returns:
            self for chaining

        Example:
            def extract_order_fields(data):
                return {
                    "order_id": data.get("id"),
                    "total": data.get("total"),
                    "status": data.get("status"),
                }

            middleware.register_extractor("process_order", extract_order_fields)
        """
        self._extractors[step_pattern] = extractor
        return self

    def register_generator(
        self,
        step_pattern: str,
        generator: SummaryGenerator,
    ) -> "OffloadMiddleware":
        """
        Register a domain-specific summary generator.

        Args:
            step_pattern: Step name or pattern to match
            generator: Function that generates summary from data and key_fields

        Returns:
            self for chaining

        Example:
            def generate_order_summary(data, key_fields):
                order_id = key_fields.get("order_id", "unknown")
                total = key_fields.get("total", 0)
                return f"Order {order_id} - ${total}"

            middleware.register_generator("process_order", generate_order_summary)
        """
        self._generators[step_pattern] = generator
        return self

    def _get_threshold(self, step_name: str) -> int:
        """Get size threshold for a step."""
        return self._step_thresholds.get(step_name, self._default_threshold)

    def _get_extractor(self, step_name: str) -> KeyFieldExtractor:
        """Get the appropriate key field extractor for a step."""
        # Check for exact match
        if step_name in self._extractors:
            return self._extractors[step_name]

        # Check for partial match
        step_lower = step_name.lower()
        for pattern, extractor in self._extractors.items():
            if pattern.lower() in step_lower:
                return extractor

        # Default extractor
        return default_key_field_extractor

    def _get_generator(self, step_name: str) -> SummaryGenerator:
        """Get the appropriate summary generator for a step."""
        # Check for exact match
        if step_name in self._generators:
            return self._generators[step_name]

        # Check for partial match
        step_lower = step_name.lower()
        for pattern, generator in self._generators.items():
            if pattern.lower() in step_lower:
                return generator

        # Default generator
        return default_summary_generator

    def _estimate_size(self, data: Any) -> int:
        """Estimate serialized size of data."""
        try:
            return len(json.dumps(data, default=str).encode())
        except (TypeError, ValueError):
            return len(pickle.dumps(data))

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Check step output and offload if large.

        Called after step execution with the result.
        """
        if not result.success or result.output is None:
            return

        # Skip if already a context ref
        if is_context_ref(result.output):
            return

        # Check size
        threshold = self._get_threshold(step_name)
        size = self._estimate_size(result.output)

        if size < threshold:
            logger.debug(f"Step '{step_name}' output is small ({size} bytes), keeping in context")
            return

        # Offload to store
        logger.info(f"Offloading '{step_name}' output ({size} bytes > {threshold} threshold)")

        # Extract key fields using appropriate extractor
        extractor = self._get_extractor(step_name)
        key_fields = extractor(result.output)

        # Generate summary using appropriate generator
        generator = self._get_generator(step_name)
        summary = generator(result.output, key_fields)

        # Store in context store
        ref = await self._store.store(
            key=step_name,
            data=result.output,
            ttl_seconds=self._ttl_seconds,
            summary=summary,
            key_fields=key_fields,
            source_step=step_name,
        )

        # Update the result output to use the ref
        result.output = ref

        # Also update context if the step stored data there
        for key_pattern in [
            f"{step_name}_result",
            f"{step_name}_data",
            step_name,
        ]:
            if ctx.has(key_pattern):
                old_value = ctx.get(key_pattern)
                if not is_context_ref(old_value):
                    ctx.set(key_pattern, ref)
                    logger.debug(f"Updated context key '{key_pattern}' with ContextRef")

        # Update statistics
        self._offload_count += 1
        self._total_bytes_offloaded += size

    def get_stats(self) -> dict[str, Any]:
        """Get offload statistics."""
        return {
            "offload_count": self._offload_count,
            "total_bytes_offloaded": self._total_bytes_offloaded,
            "total_mb_offloaded": round(self._total_bytes_offloaded / (1024 * 1024), 2),
            "registered_extractors": list(self._extractors.keys()),
            "registered_generators": list(self._generators.keys()),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#                    ITEM CAPPING UTILITY
# ═══════════════════════════════════════════════════════════════════════════════


def cap_items_with_metadata(
    items: list[Any],
    max_items: int,
    sort_key: Callable[[Any], Any] | None = None,
    sort_reverse: bool = True,
) -> tuple[list[Any], dict[str, Any]]:
    """
    Cap a list of items while preserving metadata about what was omitted.

    NEVER loses track of omitted data - always records count and summary.

    Args:
        items: List of items to cap
        max_items: Maximum items to keep
        sort_key: Optional sort key function (to keep most important)
        sort_reverse: Sort descending (default True for relevance scores)

    Returns:
        Tuple of (capped_items, metadata)

    Usage:
        results, meta = cap_items_with_metadata(
            search_results,
            max_items=10,
            sort_key=lambda x: x.get("score", 0),
        )
        # meta = {"original_count": 150, "omitted_count": 140, ...}
    """
    if not items or len(items) <= max_items:
        return items, {
            "original_count": len(items),
            "kept_count": len(items),
            "omitted_count": 0,
            "was_capped": False,
        }

    # Sort if key provided
    if sort_key:
        sorted_items = sorted(items, key=sort_key, reverse=sort_reverse)
    else:
        sorted_items = items

    # Cap
    kept = sorted_items[:max_items]
    omitted = sorted_items[max_items:]

    # Build metadata about omitted items
    metadata = {
        "original_count": len(items),
        "kept_count": len(kept),
        "omitted_count": len(omitted),
        "was_capped": True,
    }

    # Add info about what was omitted
    if omitted and isinstance(omitted[0], dict):
        sample = omitted[0]
        metadata["omitted_sample_keys"] = list(sample.keys())[:5]

        # If items have dates, show date range of omitted
        if "date" in sample:
            dates = [item.get("date") for item in omitted if item.get("date")]
            if dates:
                metadata["omitted_date_range"] = {
                    "earliest": min(dates),
                    "latest": max(dates),
                }

    return kept, metadata


def cap_per_source(
    items: list[dict[str, Any]],
    source_field: str,
    max_per_source: int,
    total_max: int | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """
    Cap items per source while preserving metadata.

    Useful for ensuring balanced representation from multiple data sources.

    Args:
        items: List of item dicts
        source_field: Field name containing source identifier
        max_per_source: Max items per source
        total_max: Optional total maximum across all sources

    Returns:
        Tuple of (capped_items, metadata)

    Usage:
        results, meta = cap_per_source(
            all_results,
            source_field="agent",
            max_per_source=10,
            total_max=30,
        )
    """
    # Group by source
    by_source: dict[str, list[dict]] = {}
    for item in items:
        source = item.get(source_field, "unknown")
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(item)

    # Cap per source
    result = []
    omitted_by_source = {}

    for source, source_items in by_source.items():
        kept = source_items[:max_per_source]
        omitted = len(source_items) - len(kept)

        result.extend(kept)
        if omitted > 0:
            omitted_by_source[source] = omitted

    # Apply total cap if specified
    total_omitted = 0
    if total_max and len(result) > total_max:
        total_omitted = len(result) - total_max
        result = result[:total_max]

    metadata = {
        "original_count": len(items),
        "kept_count": len(result),
        "omitted_count": sum(omitted_by_source.values()) + total_omitted,
        "was_capped": bool(omitted_by_source) or total_omitted > 0,
        "sources": list(by_source.keys()),
        "per_source_counts": {s: len(items) for s, items in by_source.items()},
        "omitted_per_source": omitted_by_source,
    }

    return result, metadata
