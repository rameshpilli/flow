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
    search_news_stub, search_capiq_stub

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
    name="search_capiq_stub",
    description=(
        "[STUB — replace with MCP adapter] Search S&P Capital IQ for M&A deal data. "
        "Returns placeholder data until MCP_CAPIQ_ENDPOINT is configured."
    ),
    category="search",
    tags=["capiq", "deals", "stub"],
)
async def search_capiq_stub(
    query: str, deal_type: str = "M&A", min_value_usd: float = 0
) -> str:
    logger.warning("search_capiq_stub called — configure MCP_CAPIQ_ENDPOINT for real data")
    return json.dumps({
        "source": "capiq_stub",
        "query": query,
        "results": [],
        "note": "Configure MCP_CAPIQ_ENDPOINT to enable real Capital IQ data search.",
    })


# ── ReAct searcher ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPTS: dict[str, str] = {
    "ravenpack": (
        "You are a financial news researcher using the RavenPack News MCP server. "
        "Search for news articles, press releases, and wire feeds about mergers, "
        "acquisitions, and corporate deals. "
        "Always filter results to the specified date range and deal-value threshold. "
        "If a search returns fewer than 3 results, refine the query and try again. "
        "When you have enough results, return a JSON list of findings with fields: "
        "title, date, source, summary, deal_value_usd, companies_involved, url."
    ),
    "capiq": (
        "You are a financial data researcher using the S&P Capital IQ MCP server. "
        "Search for M&A transactions, deal valuations, and corporate deal terms. "
        "Prioritise completeness: include target, acquirer, deal value, status, region. "
        "When you have enough results, return a JSON list of findings with fields: "
        "deal_id, target, acquirer, deal_value_usd, status, announced_date, region, source."
    ),
}

_TASK_TEMPLATE = """\
You are a financial research agent. You MUST use the available search tools to \
gather data — do NOT answer from memory or training data.

Sub-queries to research:
{sub_queries}

Constraints:
- Date range: {start_date} to {end_date}
- Minimum deal value: ${min_value_usd:,.0f}
- Additional instructions: {system_instructions}

Required steps:
1. Call the primary search tool for EACH sub-query above.
2. If a search returns fewer than 3 results, try a broader query.
3. After all searches, compile ALL findings into one JSON array.
4. End your response with EXACTLY this line (no markdown fences):
   Final Answer: [{{...}}, {{...}}]

The JSON array items must include every field returned by the search tools. \
Do NOT summarise or omit fields. Return the raw tool results merged together.\
"""


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
                raw = json.dumps(result) if not isinstance(result, str) else result
                # Guard: RavenPack / CapIQ can return thousands of records in one
                # response. Truncating here — before the string enters the ReAct
                # observation — prevents context-window overflow in the LLM.
                # The agent will iterate with refined queries if it needs more data.
                limit = settings.max_observation_chars
                if len(raw) > limit:
                    logger.warning(
                        "MCP response from '%s' truncated %d → %d chars "
                        "(increase MAX_OBSERVATION_CHARS to allow more)",
                        tool_name, len(raw), limit,
                    )
                    raw = raw[:limit] + "\n... [truncated — response exceeded MAX_OBSERVATION_CHARS]"
                return raw

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


async def _direct_mcp_search(
    source: str,
    sub_queries: list[str],
    date_range: dict[str, str],
    min_value_usd: float,
    adapter: MCPToolAdapter,
    llm: Any,
) -> list[dict[str, Any]]:
    """Directly call MCP tools for each sub-query, then use LLM to synthesise.

    This is used as a fallback (or primary path) when the ReAct loop returns
    empty results — newer LLMs sometimes skip the tool-call step.
    """
    raw_results: list[str] = []
    tool_names = [t.get("name", "") for t in (adapter.tools_list or [])]

    # Pick the most relevant tool for this source
    search_tool = None
    for candidate in tool_names:
        if "search" in candidate.lower() or "news" in candidate.lower() or "deal" in candidate.lower():
            search_tool = candidate
            break
    if not search_tool and tool_names:
        search_tool = tool_names[0]

    if not search_tool:
        logger.warning("[%s] No search tool found on adapter", source)
        return []

    logger.info("[%s] Direct MCP search — tool=%s queries=%d", source, search_tool, len(sub_queries))
    for q in sub_queries:
        try:
            result = await adapter.session.call_tool(search_tool, {"query": q})
            raw = json.dumps(result) if not isinstance(result, str) else result
            limit = settings.max_observation_chars
            if len(raw) > limit:
                raw = raw[:limit] + "\n... [truncated]"
            raw_results.append(raw)
            logger.debug("[%s] tool call returned %d chars for query: %s", source, len(raw), q[:60])
        except Exception as exc:
            logger.warning("[%s] MCP tool call failed for query %r: %s", source, q, exc)

    if not raw_results:
        return []

    # Ask the LLM to extract structured findings from the raw tool output
    combined = "\n\n---\n\n".join(raw_results)
    synthesis_prompt = (
        f"You are a financial data analyst. Below are raw results from the {source} data source.\n"
        f"Extract ALL deals/articles that match: deal value >= ${min_value_usd:,.0f}, "
        f"date range {date_range.get('start_date', 'any')} to {date_range.get('end_date', 'today')}.\n\n"
        f"Raw data:\n{combined}\n\n"
        f"Return a JSON array of findings. Each item must include every field present in the raw data. "
        f"Do NOT filter out items unless they clearly fail the criteria. "
        f"Return ONLY the JSON array — no markdown, no explanation."
    )

    try:
        raw_answer = await llm.generate_async(synthesis_prompt, max_tokens=4096, temperature=0.0)
        raw_answer = raw_answer.strip()
        if raw_answer.startswith("```"):
            raw_answer = "\n".join(l for l in raw_answer.splitlines() if not l.startswith("```")).strip()
        findings: list[dict[str, Any]] = json.loads(raw_answer)
        if not isinstance(findings, list):
            findings = [findings]
        logger.info("[%s] Direct synthesis returned %d findings", source, len(findings))
        return findings
    except Exception as exc:
        logger.warning("[%s] Direct synthesis failed: %s", source, exc)
        return []


async def search_source(
    source: str,
    sub_queries: list[str],
    system_instructions: list[str],
    date_range: dict[str, str],
    min_value_usd: float,
    adapter: Optional[MCPToolAdapter],
    llm: Any,
) -> list[dict[str, Any]]:
    """Search a single data source using ReAct loop with direct-call fallback.

    Strategy:
      1. Try the ReAct loop (works well with smaller/older models that follow
         text-format instructions strictly).
      2. If ReAct returns 0 findings AND a live adapter is available, fall back
         to calling the MCP tools directly and asking the LLM to synthesise
         (more reliable with larger/newer models like Sonnet-4-5).
    """
    system_prompt = _SYSTEM_PROMPTS.get(source, next(iter(_SYSTEM_PROMPTS.values())))
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
        start_date=date_range.get("start_date", "any"),
        end_date=date_range.get("end_date", "today"),
        min_value_usd=min_value_usd,
    )

    logger.info("[%s] Starting ReAct search — %d sub-queries", source, len(sub_queries))
    result = await agent.run(question=task)

    findings: list[dict[str, Any]] = []

    if result.success and result.final_answer:
        try:
            answer = result.final_answer.strip()
            if answer.startswith("```"):
                answer = "\n".join(l for l in answer.splitlines() if not l.startswith("```")).strip()
            parsed = json.loads(answer)
            findings = parsed if isinstance(parsed, list) else [parsed]
            logger.info("[%s] ReAct returned %d findings", source, len(findings))
        except json.JSONDecodeError as exc:
            logger.warning("[%s] Could not parse ReAct JSON output: %s", source, exc)

    # Fallback: if ReAct gave 0 findings and we have a live adapter, call tools directly
    if not findings and adapter and adapter.session:
        logger.info("[%s] ReAct returned empty — falling back to direct MCP call", source)
        findings = await _direct_mcp_search(
            source=source,
            sub_queries=sub_queries,
            date_range=date_range,
            min_value_usd=min_value_usd,
            adapter=adapter,
            llm=llm,
        )

    if not findings:
        logger.warning("[%s] No findings from ReAct or direct MCP search", source)

    return findings
