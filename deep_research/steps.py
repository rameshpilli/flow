"""Deep Research Agent — DAG step functions.

Five steps that implement the research pipeline:

  plan_research        →  [search_news, search_capiq]
                        ↓
                     aggregate_sources
                        ↓
                     cross_verify
                        ↓
                     generate_report

Each function receives a ChainContext and returns a dict that is merged back
into the context for downstream steps.  Heavy work (LLM calls, MCP I/O) is
done inside the step; the step itself is a thin orchestration layer.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agentorchestrator.middleware.offload import cap_per_source

from deep_research.config import settings
from deep_research.search import search_source

logger = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────────────

_PLAN_PROMPT = """\
You are a research planning assistant. Given a user query and optional system
instructions, produce a research plan in JSON.

User query: {query}

System instructions:
{system_instructions}

Return a JSON object with the following fields:
- sub_queries: list of 2–{max_sub_queries} precise search strings that together
  cover the full scope of the user query. Each string should be independently
  searchable.
- date_range: object with start_date and end_date (ISO-8601, based on any
  recency constraints in the query or instructions).
- min_value_usd: minimum deal/transaction value in USD (0 if not specified).
- source_hints: list of source types most likely to have relevant data.
  Choose from: news, sec, financial, web.
- filters: any additional structured filters (region, deal_type, etc.) as
  key-value pairs.

Return ONLY the JSON — no markdown, no commentary.
"""

_VERIFY_PROMPT = """\
You are a fact-checking and verification assistant for financial research.

Below is a list of findings from multiple sources. Your job is to:
1. Identify any findings that appear to be duplicates (same deal reported by
   multiple sources) and keep only the most complete version.
2. Flag any findings where the deal value, date, or key parties conflict across
   sources.
3. Remove findings that clearly do not meet the user's criteria:
   {criteria}

Return a JSON object with:
- verified: list of findings that passed all checks (enriched with a
  "confidence" field: "high" | "medium" | "low")
- flagged: list of findings with conflicts (include a "conflict_reason" field)
- removed: count of items removed for not meeting criteria

Input findings:
{findings_json}

Return ONLY the JSON — no markdown, no commentary.
"""

_REPORT_PROMPT = """\
You are a senior financial analyst writing a comprehensive research report.

User query: {query}

System instructions applied:
{system_instructions}

Research findings (verified):
{findings_json}

Write a {format} report that:
1. Opens with an executive summary (2–3 sentences).
2. Organises findings by category (e.g. by region or deal type if applicable).
3. For each finding includes: deal name, parties involved, deal value, date,
   status, and the source(s) it came from.
4. Ends with a "Coverage Notes" section listing which sources were searched,
   the date range covered, and any gaps or caveats.
5. Uses clear headings and bullet points for easy scanning.
6. Cites every source inline using [Source Name] notation.

Be comprehensive — include ALL verified findings, not just highlights.
"""


# ── Step implementations ───────────────────────────────────────────────────────

async def plan_research(ctx: Any) -> dict[str, Any]:
    """Step 1: Decompose the user query into structured search sub-queries."""
    query: str = ctx.get("query", "")
    system_instructions: list[str] = ctx.get("system_instructions", [])
    llm = ctx.get("llm_client")

    if not query:
        raise ValueError("plan_research: 'query' is required in initial context")

    prompt = _PLAN_PROMPT.format(
        query=query,
        system_instructions="\n".join(f"- {i}" for i in system_instructions) or "- None",
        max_sub_queries=settings.planner_max_sub_queries,
    )

    logger.info("Planning research for query: %s", query[:120])
    raw = await llm.generate_async(prompt, max_tokens=1024, temperature=0.1)

    try:
        plan: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Planner returned non-JSON; using defaults")
        plan = {
            "sub_queries": [query],
            "date_range": {"start_date": "", "end_date": ""},
            "min_value_usd": 0,
            "source_hints": ["ravenpack", "capiq"],
            "filters": {},
        }

    # Ensure sub_queries is capped
    plan["sub_queries"] = plan.get("sub_queries", [query])[: settings.planner_max_sub_queries]
    plan["system_instructions"] = system_instructions

    logger.info(
        "Research plan: %d sub-queries, sources=%s, date_range=%s",
        len(plan["sub_queries"]),
        plan.get("source_hints"),
        plan.get("date_range"),
    )
    return {"research_plan": plan}


async def search_news(ctx: Any) -> dict[str, Any]:
    """Step 2a: Parallel — Search RavenPack News MCP or stub."""
    plan: dict[str, Any] = ctx.get("research_plan", {})
    llm = ctx.get("llm_client")
    mcp_service = ctx.get("mcp_service")

    adapter = mcp_service.get_adapter("ravenpack") if mcp_service else None
    findings = await search_source(
        source="ravenpack",
        sub_queries=plan.get("sub_queries", []),
        system_instructions=plan.get("system_instructions", []),
        date_range=plan.get("date_range", {}),
        min_value_usd=float(plan.get("min_value_usd", 0)),
        adapter=adapter,
        llm=llm,
    )
    return {"news_findings": cap_per_source(findings, max_per_source=settings.results_per_source)}


async def search_capiq(ctx: Any) -> dict[str, Any]:
    """Step 2b: Parallel — Search S&P Capital IQ MCP or stub."""
    plan: dict[str, Any] = ctx.get("research_plan", {})
    llm = ctx.get("llm_client")
    mcp_service = ctx.get("mcp_service")

    adapter = mcp_service.get_adapter("capiq") if mcp_service else None
    findings = await search_source(
        source="capiq",
        sub_queries=plan.get("sub_queries", []),
        system_instructions=plan.get("system_instructions", []),
        date_range=plan.get("date_range", {}),
        min_value_usd=float(plan.get("min_value_usd", 0)),
        adapter=adapter,
        llm=llm,
    )
    return {"capiq_findings": cap_per_source(findings, max_per_source=settings.results_per_source)}


async def aggregate_sources(ctx: Any) -> dict[str, Any]:
    """Step 3: Merge findings from RavenPack and CapIQ, deduplicate, rank by recency."""
    news = ctx.get("news_findings") or []
    capiq = ctx.get("capiq_findings") or []

    # Tag each item with its source bucket for downstream citation
    def _tag(items: list[dict], source: str) -> list[dict]:
        for item in items:
            item.setdefault("_source_bucket", source)
        return items

    all_findings: list[dict[str, Any]] = (
        _tag(list(news), "ravenpack")
        + _tag(list(capiq), "capiq")
    )

    # Basic deduplication by title/deal_id similarity
    seen_keys: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in all_findings:
        key = (
            str(item.get("deal_id", ""))
            or str(item.get("title", "")).lower()[:60]
        ).strip()
        if key and key not in seen_keys:
            seen_keys.add(key)
            unique.append(item)
        elif not key:
            unique.append(item)

    # Sort by date descending (best effort — field names vary by source)
    def _date_key(item: dict) -> str:
        for field in ("date", "announced_date", "filing_date", "published_date"):
            if item.get(field):
                return str(item[field])
        return ""

    unique.sort(key=_date_key, reverse=True)

    logger.info(
        "Aggregated %d raw findings → %d unique (ravenpack=%d, capiq=%d)",
        len(all_findings), len(unique), len(news), len(capiq),
    )

    return {
        "aggregated_findings": unique,
        "source_counts": {
            "ravenpack": len(news),
            "capiq": len(capiq),
            "total_raw": len(all_findings),
            "total_unique": len(unique),
        },
    }


async def cross_verify(ctx: Any) -> dict[str, Any]:
    """Step 4: LLM-based cross-verification and conflict detection."""
    aggregated: list[dict[str, Any]] = ctx.get("aggregated_findings") or []
    plan: dict[str, Any] = ctx.get("research_plan", {})
    llm = ctx.get("llm_client")

    if not aggregated:
        logger.warning("cross_verify: no findings to verify")
        return {"verified_findings": [], "flagged_findings": [], "verification_summary": {}}

    criteria_parts: list[str] = list(plan.get("system_instructions", []))
    if plan.get("min_value_usd"):
        criteria_parts.append(f"Deal value must be >= ${float(plan['min_value_usd']):,.0f}")
    date_range = plan.get("date_range", {})
    if date_range.get("start_date"):
        criteria_parts.append(
            f"Date must be between {date_range['start_date']} and {date_range.get('end_date', 'today')}"
        )

    findings_json = json.dumps(aggregated, indent=2)
    # Truncate if very long to stay within token budget
    if len(findings_json) > 24000:
        findings_json = findings_json[:24000] + "\n... (truncated for token budget)"

    prompt = _VERIFY_PROMPT.format(
        criteria="\n".join(f"- {c}" for c in criteria_parts) or "- None specified",
        findings_json=findings_json,
    )

    logger.info("Cross-verifying %d findings", len(aggregated))
    raw = await llm.generate_async(prompt, max_tokens=4096, temperature=0.0)

    try:
        verification: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("cross_verify LLM returned non-JSON; passing findings through unverified")
        verification = {
            "verified": [dict(item, confidence="medium") for item in aggregated],
            "flagged": [],
            "removed": 0,
        }

    verified = verification.get("verified") or []
    flagged = verification.get("flagged") or []
    logger.info(
        "Verification complete: %d verified, %d flagged, %d removed",
        len(verified), len(flagged), verification.get("removed", 0),
    )

    return {
        "verified_findings": verified,
        "flagged_findings": flagged,
        "verification_summary": {
            "verified_count": len(verified),
            "flagged_count": len(flagged),
            "removed_count": verification.get("removed", 0),
        },
    }


async def generate_report(ctx: Any) -> dict[str, Any]:
    """Step 5: Synthesise a final research report from verified findings."""
    verified: list[dict[str, Any]] = ctx.get("verified_findings") or []
    flagged: list[dict[str, Any]] = ctx.get("flagged_findings") or []
    plan: dict[str, Any] = ctx.get("research_plan", {})
    source_counts: dict[str, Any] = ctx.get("source_counts") or {}
    query: str = ctx.get("query", "")
    llm = ctx.get("llm_client")

    if not verified:
        report = (
            "# Research Report\n\n"
            "No verified findings matched your query and criteria.\n\n"
            "**Query:** " + query + "\n\n"
            "**Suggestion:** Broaden the date range or lower the deal-value threshold."
        )
        return {"report": report, "report_format": settings.report_format}

    findings_json = json.dumps(verified, indent=2)
    if len(findings_json) > 28000:
        findings_json = findings_json[:28000] + "\n... (truncated — see raw findings for full list)"

    prompt = _REPORT_PROMPT.format(
        query=query,
        system_instructions="\n".join(
            f"- {i}" for i in plan.get("system_instructions", [])
        ) or "- None",
        findings_json=findings_json,
        format=settings.report_format,
    )

    logger.info("Generating final report from %d verified findings", len(verified))
    report = await llm.generate_async(prompt, max_tokens=settings.llm_max_tokens, temperature=0.2)

    # Append flagged items as an appendix
    if flagged:
        report += (
            "\n\n---\n\n## Appendix: Flagged / Conflicting Items\n\n"
            "The following items were found but contained data conflicts across sources:\n\n"
        )
        for item in flagged[:10]:
            reason = item.get("conflict_reason", "Unknown conflict")
            title = item.get("title") or item.get("deal_id") or "Unnamed"
            report += f"- **{title}**: {reason}\n"
        if len(flagged) > 10:
            report += f"\n_...and {len(flagged) - 10} more flagged items._\n"

    return {
        "report": report,
        "report_format": settings.report_format,
        "stats": {
            "verified_findings": len(verified),
            "flagged_findings": len(flagged),
            "source_counts": source_counts,
        },
    }
