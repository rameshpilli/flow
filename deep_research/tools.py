"""Deep Research Agent — ToolRegistry definitions.

Registers plain Python fallback tools (web search stub, date helpers) that
work without any MCP connection.  These are used when a real MCP adapter is
unavailable or as supplementary tools inside a ReActAgent.

Real data-source tools are registered dynamically in react_searcher.py once
the MCP adapters are connected.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agentorchestrator.agents.tools import ToolRegistry

logger = logging.getLogger(__name__)

# One shared registry — imported by react_searcher and steps
tool_registry = ToolRegistry(name="deep_research")


# ── Utility tools ─────────────────────────────────────────────────────────────

@tool_registry.tool(
    name="get_current_date",
    description="Returns today's date in ISO-8601 format. Use this to anchor recency filters.",
    category="utility",
)
async def get_current_date() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


@tool_registry.tool(
    name="parse_date_range",
    description=(
        "Given a natural-language time expression like 'last 2 weeks' or 'past month', "
        "returns a JSON object with 'start_date' and 'end_date' in ISO-8601 format."
    ),
    category="utility",
)
async def parse_date_range(expression: str) -> str:
    """Very lightweight parser — covers the most common research windows."""
    from datetime import timedelta

    now = datetime.now(tz=timezone.utc)
    expression = expression.lower().strip()

    if "2 week" in expression or "two week" in expression:
        start = now - timedelta(weeks=2)
    elif "week" in expression:
        start = now - timedelta(weeks=1)
    elif "month" in expression:
        start = now - timedelta(days=30)
    elif "quarter" in expression or "3 month" in expression:
        start = now - timedelta(days=90)
    elif "year" in expression:
        start = now - timedelta(days=365)
    else:
        # Default: 2 weeks
        start = now - timedelta(weeks=2)

    return json.dumps({
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": now.strftime("%Y-%m-%d"),
    })


@tool_registry.tool(
    name="filter_by_threshold",
    description=(
        "Given a JSON list of deals/items and a numeric threshold field name + minimum value, "
        "returns only items that meet the threshold. "
        "Args: items_json (str), field (str), min_value (float)."
    ),
    category="filtering",
)
async def filter_by_threshold(items_json: str, field: str, min_value: float) -> str:
    """Filter a list of dicts by a numeric field minimum."""
    try:
        items: list[dict[str, Any]] = json.loads(items_json)
        filtered = [
            item for item in items
            if isinstance(item, dict) and float(item.get(field, 0)) >= min_value
        ]
        return json.dumps({"filtered": filtered, "count": len(filtered)})
    except Exception as exc:
        return json.dumps({"error": str(exc), "filtered": [], "count": 0})


@tool_registry.tool(
    name="deduplicate_results",
    description=(
        "Given a JSON list of result items, removes near-duplicates based on a key field "
        "(e.g. 'title' or 'deal_id'). Returns deduplicated list."
    ),
    category="filtering",
)
async def deduplicate_results(items_json: str, key_field: str = "title") -> str:
    """Deduplicate a result list by a key field."""
    try:
        items: list[dict[str, Any]] = json.loads(items_json)
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in items:
            key = str(item.get(key_field, "")).lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        return json.dumps({"deduplicated": unique, "count": len(unique)})
    except Exception as exc:
        return json.dumps({"error": str(exc), "deduplicated": [], "count": 0})


# ── Stub search tools (replaced by MCP adapters at runtime) ───────────────────

@tool_registry.tool(
    name="search_news_stub",
    description=(
        "[STUB — replace with MCP adapter] Search news articles for a given query. "
        "Returns placeholder data until MCP_NEWS_ENDPOINT is configured."
    ),
    category="search",
    tags=["news", "stub"],
)
async def search_news_stub(query: str, start_date: str = "", end_date: str = "") -> str:
    logger.warning("search_news_stub called — configure MCP_NEWS_ENDPOINT for real data")
    return json.dumps({
        "source": "news_stub",
        "query": query,
        "results": [],
        "note": "Configure MCP_NEWS_ENDPOINT to enable real news search.",
    })


@tool_registry.tool(
    name="search_sec_stub",
    description=(
        "[STUB — replace with MCP adapter] Search SEC/EDGAR filings for a given query. "
        "Returns placeholder data until MCP_SEC_ENDPOINT is configured."
    ),
    category="search",
    tags=["sec", "filings", "stub"],
)
async def search_sec_stub(query: str, form_type: str = "8-K", start_date: str = "") -> str:
    logger.warning("search_sec_stub called — configure MCP_SEC_ENDPOINT for real data")
    return json.dumps({
        "source": "sec_stub",
        "query": query,
        "results": [],
        "note": "Configure MCP_SEC_ENDPOINT to enable real SEC filings search.",
    })


@tool_registry.tool(
    name="search_financial_stub",
    description=(
        "[STUB — replace with MCP adapter] Search financial data (M&A, deals) for a given query. "
        "Returns placeholder data until MCP_FINANCIAL_ENDPOINT is configured."
    ),
    category="search",
    tags=["financial", "deals", "stub"],
)
async def search_financial_stub(query: str, deal_type: str = "M&A", min_value_usd: float = 0) -> str:
    logger.warning("search_financial_stub called — configure MCP_FINANCIAL_ENDPOINT for real data")
    return json.dumps({
        "source": "financial_stub",
        "query": query,
        "results": [],
        "note": "Configure MCP_FINANCIAL_ENDPOINT to enable real financial data search.",
    })
