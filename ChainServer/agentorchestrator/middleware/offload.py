"""
AgentOrchestrator Offload Middleware - Automatic Large Payload Offloading

Automatically offloads large step outputs to Redis context store,
keeping chain context lightweight while preserving 100% of the data.

Key Principles:
1. NEVER lose data - full payloads preserved in Redis
2. NEVER blind-truncate - always keep summaries, key fields, counts
3. Automatic - no manual intervention needed per step
4. Configurable thresholds per step/agent

Architecture:
    Step Output (1.2MB)
           │
           ▼
    ┌──────────────────────────────────────────────────────────┐
    │              Offload Middleware                           │
    │  if size > threshold:                                     │
    │    1. Extract key_fields (revenue, dates, entities)      │
    │    2. Generate summary                                    │
    │    3. Store full data in Redis                           │
    │    4. Replace output with ContextRef                     │
    └──────────────────────────────────────────────────────────┘
           │
           ▼
    Context gets ContextRef (500 bytes)
    Redis stores full data (1.2MB)

Usage:
    from agentorchestrator.middleware.offload import OffloadMiddleware
    from agentorchestrator.core.context_store import RedisContextStore

    store = RedisContextStore(host="localhost", port=6380)

    forge.use(OffloadMiddleware(
        store=store,
        default_threshold_bytes=100_000,  # 100KB
        step_thresholds={
            "fetch_sec_data": 50_000,   # More aggressive for SEC
            "fetch_news_data": 100_000,
        },
    ))
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


# ═══════════════════════════════════════════════════════════════════════════════
#                    KEY FIELD EXTRACTORS (Domain-Aware)
# ═══════════════════════════════════════════════════════════════════════════════


def extract_sec_key_fields(data: Any) -> dict[str, Any]:
    """Extract key fields from SEC filing data."""
    key_fields = {}

    if isinstance(data, dict):
        # Common SEC fields
        for field in [
            "ticker", "cik", "company_name", "filing_type", "filing_date",
            "fiscal_year", "fiscal_quarter", "accession_number",
            "total_revenue", "net_income", "total_assets", "total_liabilities",
        ]:
            if field in data:
                key_fields[field] = data[field]

    elif isinstance(data, list):
        key_fields["filing_count"] = len(data)
        if len(data) > 0 and isinstance(data[0], dict):
            # Get unique tickers/filing types
            tickers = set()
            filing_types = set()
            for item in data[:20]:  # Sample first 20
                if "ticker" in item:
                    tickers.add(item["ticker"])
                if "filing_type" in item:
                    filing_types.add(item["filing_type"])
            if tickers:
                key_fields["tickers"] = list(tickers)[:5]
            if filing_types:
                key_fields["filing_types"] = list(filing_types)

    return key_fields


def extract_news_key_fields(data: Any) -> dict[str, Any]:
    """Extract key fields from news data."""
    key_fields = {}

    if isinstance(data, list):
        key_fields["article_count"] = len(data)

        # Extract sentiment distribution if available
        sentiments = {"positive": 0, "negative": 0, "neutral": 0}
        sources = set()
        topics = set()

        for item in data[:50]:  # Sample first 50
            if isinstance(item, dict):
                if "sentiment" in item:
                    sent = item["sentiment"].lower()
                    if sent in sentiments:
                        sentiments[sent] += 1
                if "source" in item:
                    sources.add(item["source"])
                if "topics" in item and isinstance(item["topics"], list):
                    topics.update(item["topics"][:3])

        if any(sentiments.values()):
            key_fields["sentiment_distribution"] = sentiments
        if sources:
            key_fields["sources"] = list(sources)[:10]
        if topics:
            key_fields["topics"] = list(topics)[:10]

    return key_fields


def extract_earnings_key_fields(data: Any) -> dict[str, Any]:
    """Extract key fields from earnings data."""
    key_fields = {}

    if isinstance(data, dict):
        for field in [
            "ticker", "company_name", "fiscal_year", "fiscal_quarter",
            "eps", "eps_estimate", "eps_surprise",
            "revenue", "revenue_estimate", "revenue_surprise",
            "earnings_date", "transcript_date",
        ]:
            if field in data:
                key_fields[field] = data[field]

    elif isinstance(data, list):
        key_fields["earnings_count"] = len(data)
        if len(data) > 0 and isinstance(data[0], dict):
            quarters = set()
            for item in data[:10]:
                if "fiscal_quarter" in item and "fiscal_year" in item:
                    quarters.add(f"{item['fiscal_year']}Q{item['fiscal_quarter']}")
            if quarters:
                key_fields["quarters_covered"] = sorted(list(quarters))

    return key_fields


# Map agent/step names to extractors
KEY_FIELD_EXTRACTORS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "sec": extract_sec_key_fields,
    "sec_agent": extract_sec_key_fields,
    "fetch_sec_data": extract_sec_key_fields,
    "news": extract_news_key_fields,
    "news_agent": extract_news_key_fields,
    "fetch_news_data": extract_news_key_fields,
    "earnings": extract_earnings_key_fields,
    "earnings_agent": extract_earnings_key_fields,
    "fetch_earnings_data": extract_earnings_key_fields,
}


def get_key_field_extractor(step_name: str) -> Callable[[Any], dict[str, Any]]:
    """Get the appropriate key field extractor for a step."""
    # Check for exact match
    if step_name in KEY_FIELD_EXTRACTORS:
        return KEY_FIELD_EXTRACTORS[step_name]

    # Check for partial match
    step_lower = step_name.lower()
    for key, extractor in KEY_FIELD_EXTRACTORS.items():
        if key in step_lower:
            return extractor

    # Default extractor
    return _default_key_field_extractor


def _default_key_field_extractor(data: Any) -> dict[str, Any]:
    """Default key field extractor for unknown data types."""
    key_fields = {}

    if isinstance(data, dict):
        # Extract common fields
        for field in ["id", "name", "type", "date", "count", "total"]:
            if field in data:
                key_fields[field] = data[field]
        key_fields["keys"] = list(data.keys())[:10]

    elif isinstance(data, list):
        key_fields["count"] = len(data)
        if len(data) > 0:
            key_fields["item_type"] = type(data[0]).__name__
            if isinstance(data[0], dict):
                key_fields["sample_keys"] = list(data[0].keys())[:5]

    return key_fields


# ═══════════════════════════════════════════════════════════════════════════════
#                    SUMMARY GENERATORS (Domain-Aware)
# ═══════════════════════════════════════════════════════════════════════════════


def generate_sec_summary(data: Any, key_fields: dict[str, Any]) -> str:
    """Generate summary for SEC filing data."""
    if isinstance(data, list):
        count = len(data)
        tickers = key_fields.get("tickers", [])
        filing_types = key_fields.get("filing_types", [])

        parts = [f"{count} SEC filing(s)"]
        if tickers:
            parts.append(f"for {', '.join(tickers[:3])}")
        if filing_types:
            parts.append(f"types: {', '.join(filing_types[:3])}")

        return " ".join(parts)

    elif isinstance(data, dict):
        ticker = key_fields.get("ticker", "Unknown")
        filing_type = key_fields.get("filing_type", "filing")
        fiscal = ""
        if "fiscal_year" in key_fields:
            fiscal = f" FY{key_fields['fiscal_year']}"
            if "fiscal_quarter" in key_fields:
                fiscal += f"Q{key_fields['fiscal_quarter']}"

        return f"SEC {filing_type} for {ticker}{fiscal}"

    return "SEC filing data"


def generate_news_summary(data: Any, key_fields: dict[str, Any]) -> str:
    """Generate summary for news data."""
    count = key_fields.get("article_count", len(data) if isinstance(data, list) else 1)
    sources = key_fields.get("sources", [])
    sentiment = key_fields.get("sentiment_distribution", {})

    parts = [f"{count} news article(s)"]
    if sources:
        parts.append(f"from {', '.join(sources[:3])}")
    if sentiment:
        dominant = max(sentiment.items(), key=lambda x: x[1], default=("neutral", 0))
        if dominant[1] > 0:
            parts.append(f"(mostly {dominant[0]})")

    return " ".join(parts)


def generate_earnings_summary(data: Any, key_fields: dict[str, Any]) -> str:
    """Generate summary for earnings data."""
    if isinstance(data, list):
        count = len(data)
        quarters = key_fields.get("quarters_covered", [])

        parts = [f"{count} earnings record(s)"]
        if quarters:
            parts.append(f"covering {', '.join(quarters[:3])}")

        return " ".join(parts)

    elif isinstance(data, dict):
        ticker = key_fields.get("ticker", "Unknown")
        quarter = ""
        if "fiscal_year" in key_fields and "fiscal_quarter" in key_fields:
            quarter = f" {key_fields['fiscal_year']}Q{key_fields['fiscal_quarter']}"

        return f"Earnings data for {ticker}{quarter}"

    return "Earnings data"


SUMMARY_GENERATORS: dict[str, Callable[[Any, dict], str]] = {
    "sec": generate_sec_summary,
    "sec_agent": generate_sec_summary,
    "fetch_sec_data": generate_sec_summary,
    "news": generate_news_summary,
    "news_agent": generate_news_summary,
    "fetch_news_data": generate_news_summary,
    "earnings": generate_earnings_summary,
    "earnings_agent": generate_earnings_summary,
    "fetch_earnings_data": generate_earnings_summary,
}


def get_summary_generator(step_name: str) -> Callable[[Any, dict], str]:
    """Get the appropriate summary generator for a step."""
    if step_name in SUMMARY_GENERATORS:
        return SUMMARY_GENERATORS[step_name]

    step_lower = step_name.lower()
    for key, generator in SUMMARY_GENERATORS.items():
        if key in step_lower:
            return generator

    return _default_summary_generator


def _default_summary_generator(data: Any, key_fields: dict[str, Any]) -> str:
    """Default summary generator."""
    if isinstance(data, list):
        return f"{len(data)} items"
    elif isinstance(data, dict):
        return f"Dict with {len(data)} keys"
    elif isinstance(data, str):
        return f"Text ({len(data)} chars)"
    return f"{type(data).__name__} data"


# ═══════════════════════════════════════════════════════════════════════════════
#                    OFFLOAD MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════


class OffloadMiddleware(Middleware):
    """
    Middleware that automatically offloads large step outputs to Redis.

    NEVER loses data - full payloads preserved, only refs in context.

    Features:
    - Configurable size thresholds (global and per-step)
    - Domain-aware key field extraction
    - Domain-aware summary generation
    - Automatic source tracking

    Usage:
        from agentorchestrator.middleware.offload import OffloadMiddleware
        from agentorchestrator.core.context_store import RedisContextStore

        store = RedisContextStore(host="localhost", port=6380)

        forge.use(OffloadMiddleware(
            store=store,
            default_threshold_bytes=100_000,
            step_thresholds={
                "fetch_sec_data": 50_000,
            },
        ))
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
            store: Context store (Redis). Created if not provided.
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

        # Statistics
        self._offload_count = 0
        self._total_bytes_offloaded = 0

    def _get_threshold(self, step_name: str) -> int:
        """Get size threshold for a step."""
        return self._step_thresholds.get(step_name, self._default_threshold)

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

        # Offload to Redis
        logger.info(f"Offloading '{step_name}' output to Redis ({size} bytes > {threshold} threshold)")

        # Extract key fields using domain-aware extractor
        extractor = get_key_field_extractor(step_name)
        key_fields = extractor(result.output)

        # Generate summary using domain-aware generator
        generator = get_summary_generator(step_name)
        summary = generator(result.output, key_fields)

        # Store in Redis
        ref = await self._store.store(
            key=step_name,
            data=result.output,
            ttl_seconds=self._ttl_seconds,
            summary=summary,
            key_fields=key_fields,
            source_step=step_name,
        )

        # Update the result output to use the ref
        # Note: StepResult is a dataclass, so we can modify output
        result.output = ref

        # Also update context if the step stored data there
        # Check for common patterns like ctx.set("step_name_result", ...)
        for key_pattern in [
            f"{step_name}_result",
            f"{step_name}_data",
            step_name,
        ]:
            if ctx.has(key_pattern):
                old_value = ctx.get(key_pattern)
                if not is_context_ref(old_value):
                    # Replace with ref
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
            "total_mb_offloaded": self._total_bytes_offloaded / (1024 * 1024),
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
        articles, meta = cap_items_with_metadata(
            news_articles,
            max_items=10,
            sort_key=lambda x: x.get("relevance_score", 0),
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
        # Sample omitted item keys/types
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
        articles, meta = cap_per_source(
            all_articles,
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
