"""Deep Research Agent — search tools and ReAct-based searcher.

Combines the shared ToolRegistry (utility tools + source stubs) with the
ReActAgent factory that drives each data-source search step.

ToolRegistry contents
─────────────────────
  Utility tools (always injected into every ReActAgent):
    get_current_date     – anchor recency filters
    parse_date_range     – convert "last 2 weeks" → ISO-8601 range
    filter_by_threshold  – filter a JSON list by a numeric field
    deduplicate_results  – remove near-duplicates within a source

  Stub tools (fallback when no MCP endpoint is configured):
    search_news_stub, search_sec_stub, search_financial_stub

ReActAgent entry point
──────────────────────
  search_source(source, sub_queries, ..., adapter, llm) → list[dict]
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from agentorchestrator.agents.react import ReActAgent, ReActConfig, Tool
from agentorchestrator.agents.tools import ToolRegistry
from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter

from deep_research.config import settings

logger = logging.getLogger(__name__)

# ── Shared tool registry ───────────────────────────────────────────────────────

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
async def search_financial_stub(
    query: str, deal_type: str = "M&A", min_value_usd: float = 0
) -> str:
    logger.warning("search_financial_stub called — configure MCP_FINANCIAL_ENDPOINT for real data")
    return json.dumps({
        "source": "financial_stub",
        "query": query,
        "results": [],
        "note": "Configure MCP_FINANCIAL_ENDPOINT to enable real financial data search.",
    })


# ── ReAct searcher ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPTS: dict[str, str] = {
    "news": (
        "You are a financial news researcher. Your job is to search for news articles "
        "about mergers, acquisitions, and corporate deals. "
        "Always filter results to the specified date range and deal-value threshold. "
        "If a search returns fewer than 3 results, refine the query and try again. "
        "When you have enough results, return a JSON list of findings with fields: "
        "title, date, source, summary, deal_value_usd, companies_involved, url."
    ),
    "sec": (
        "You are an SEC filings researcher. Your job is to find relevant SEC filings "
        "(8-K, SC-13D, SC-TO, merger proxy) for the given query. "
        "Always include the filing date, form type, and filer. "
        "When you have enough results, return a JSON list of findings with fields: "
        "title, date, form_type, filer, description, deal_value_usd, url."
    ),
    "financial": (
        "You are a financial data researcher. Your job is to find deal data from "
        "financial databases (M&A transactions, valuations, deal terms). "
        "Prioritise completeness: include target, acquirer, deal value, status, region. "
        "When you have enough results, return a JSON list of findings with fields: "
        "deal_id, target, acquirer, deal_value_usd, status, announced_date, region, source."
    ),
    "web": (
        "You are a web research assistant. Your job is to supplement financial data "
        "with publicly available web information. Focus on recency and credibility. "
        "When you have enough results, return a JSON list of findings with fields: "
        "title, date, source, summary, url."
    ),
}

_TASK_TEMPLATE = (
    "Research the following sub-queries and return all relevant findings as a "
    "single JSON array.  Apply these system instructions strictly:\n"
    "{system_instructions}\n\n"
    "Sub-queries:\n{sub_queries}\n\n"
    "Date range: {start_date} to {end_date}\n"
    "Minimum deal value: ${min_value_usd:,.0f}\n\n"
    "Return ONLY the JSON array — no markdown, no commentary."
)


def _td_to_tool(td: Any) -> Tool:
    """Convert a ToolDefinition (list[ToolParameter]) to a react.Tool (dict schema)."""
    params_schema = {p.name: p.to_json_schema() for p in (td.parameters or [])}
    required = [p.name for p in (td.parameters or []) if p.required]
    return Tool(
        name=td.name,
        description=td.description,
        func=td.func,
        parameters=params_schema,
        required_params=required,
    )


def _build_tools_for_source(source: str, adapter: Optional[MCPToolAdapter]) -> list[Tool]:
    """Return a list of Tool objects for the ReActAgent.

    If a live MCPToolAdapter is available its tools are exposed directly.
    Otherwise the stub tool registered for this source is used as fallback.
    Utility tools (date helpers, filters) are always included.
    """
    tools: list[Tool] = []

    for name in ("get_current_date", "parse_date_range", "filter_by_threshold", "deduplicate_results"):
        td = tool_registry.get(name)
        if td:
            tools.append(_td_to_tool(td))

    if adapter and adapter.session:
        for mcp_tool in (adapter.tools_list or []):
            tool_name = mcp_tool.get("name", "")
            tool_desc = mcp_tool.get("description", "")
            input_schema = mcp_tool.get("inputSchema") or mcp_tool.get("parameters", {})
            required = input_schema.get("required", [])
            properties = input_schema.get("properties", {})

            async def _call(adapter=adapter, tool_name=tool_name, **kwargs: Any) -> str:
                result = await adapter.session.call_tool(tool_name, kwargs)
                return json.dumps(result) if not isinstance(result, str) else result

            tools.append(Tool(
                name=tool_name,
                description=tool_desc,
                func=_call,
                parameters=properties,
                required_params=required,
            ))
    else:
        stub_name = f"search_{source}_stub"
        td = tool_registry.get(stub_name)
        if td:
            tools.append(_td_to_tool(td))

    return tools


async def search_source(
    source: str,
    sub_queries: list[str],
    system_instructions: list[str],
    date_range: dict[str, str],
    min_value_usd: float,
    adapter: Optional[MCPToolAdapter],
    llm: Any,
) -> list[dict[str, Any]]:
    """Run a ReAct search loop for a single data source.

    Args:
        source: One of "news", "sec", "financial", "web".
        sub_queries: List of query strings from the planner step.
        system_instructions: Extra constraints from the user (e.g. "exclude deals < $1B").
        date_range: Dict with "start_date" and "end_date" (ISO-8601).
        min_value_usd: Minimum deal value in USD (0 = no filter).
        adapter: Live MCPToolAdapter or None (uses stub).
        llm: LLMGatewayClient instance.

    Returns:
        List of finding dicts from the agent's final answer.
    """
    system_prompt = _SYSTEM_PROMPTS.get(source, _SYSTEM_PROMPTS["web"])
    tools = _build_tools_for_source(source, adapter)

    config = ReActConfig(
        max_iterations=settings.react_max_iterations,
        max_tokens=settings.react_max_tokens,
        temperature=0.1,
        stop_on_final_answer=True,
    )

    agent = ReActAgent(
        llm_client=llm,
        tools=tools,
        config=config,
        system_prompt=system_prompt,
        name=f"ReActSearcher[{source}]",
    )

    task = _TASK_TEMPLATE.format(
        system_instructions="\n".join(f"- {i}" for i in system_instructions) or "- None",
        sub_queries="\n".join(f"- {q}" for q in sub_queries),
        start_date=date_range.get("start_date", ""),
        end_date=date_range.get("end_date", ""),
        min_value_usd=min_value_usd,
    )

    logger.info("[%s] Starting ReAct search — %d sub-queries", source, len(sub_queries))
    result = await agent.run(question=task)

    if not result.success:
        logger.warning("[%s] ReAct loop did not succeed: %s", source, result.final_answer)
        return []

    try:
        answer = result.final_answer or "[]"
        answer = answer.strip()
        if answer.startswith("```"):
            lines = answer.splitlines()
            answer = "\n".join(line for line in lines if not line.startswith("```"))
        findings: list[dict[str, Any]] = json.loads(answer)
        if not isinstance(findings, list):
            findings = [findings]
        logger.info("[%s] ReAct returned %d findings", source, len(findings))
        return findings
    except json.JSONDecodeError as exc:
        logger.warning("[%s] Could not parse ReAct JSON output: %s", source, exc)
        return [{"source": source, "raw": result.final_answer, "parse_error": str(exc)}]
