"""Deep Research Agent — ReAct-based iterative source searcher.

Each data source (news, SEC, financial) gets its own ReActAgent instance that
wraps the corresponding MCPToolAdapter.  If an adapter is not connected (no
endpoint configured), the agent falls back to the stub tools in tools.py.

The ReAct loop gives the agent up to N iterations to:
  1. Decide which tool arguments best answer the sub-query
  2. Observe the result
  3. Refine the query or pivot to a different tool if the result is sparse
  4. Return a structured list of findings

Usage (called from steps.py):
    from deep_research.react_searcher import search_source

    findings = await search_source(
        source="news",
        sub_queries=["M&A deals > $1B past 2 weeks"],
        adapter=mcp_service.get_adapter("news"),
        llm=llm_client,
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agentorchestrator.agents.react import ReActAgent, ReActConfig, Tool
from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter
from deep_research.config import settings
from deep_research.tools import tool_registry

logger = logging.getLogger(__name__)

# ── Prompt templates per source ───────────────────────────────────────────────

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


# ── Helpers ───────────────────────────────────────────────────────────────────

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

    If a live MCPToolAdapter is available we expose its tools directly as
    agentorchestrator.agents.react.Tool objects (thin wrappers).  Otherwise we
    fall back to the stub tools registered in tool_registry.
    """
    tools: list[Tool] = []

    # Always include utility tools from the shared registry
    for name in ("get_current_date", "parse_date_range", "filter_by_threshold", "deduplicate_results"):
        td = tool_registry.get(name)
        if td:
            tools.append(_td_to_tool(td))

    if adapter and adapter.session:
        # Wrap each MCP tool as a react.Tool
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
        # Fall back to stub tools for this source
        stub_name = f"search_{source}_stub"
        td = tool_registry.get(stub_name)
        if td:
            tools.append(_td_to_tool(td))

    return tools


# ── Public API ─────────────────────────────────────────────────────────────────

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

    # Parse the JSON array from final_answer
    try:
        answer = result.final_answer or "[]"
        # Strip any accidental markdown code fences
        answer = answer.strip()
        if answer.startswith("```"):
            lines = answer.splitlines()
            answer = "\n".join(
                line for line in lines
                if not line.startswith("```")
            )
        findings: list[dict[str, Any]] = json.loads(answer)
        if not isinstance(findings, list):
            findings = [findings]
        logger.info("[%s] ReAct returned %d findings", source, len(findings))
        return findings
    except json.JSONDecodeError as exc:
        logger.warning("[%s] Could not parse ReAct JSON output: %s", source, exc)
        # Return a single raw-text result so nothing is lost
        return [{"source": source, "raw": result.final_answer, "parse_error": str(exc)}]
