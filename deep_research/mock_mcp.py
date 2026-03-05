"""Mock MCP server for local development/testing.

Serves realistic fixture data for both RavenPack News and S&P Capital IQ on a
single FastAPI process.  Two route-prefixes expose separate "tool namespaces":

    POST /ravenpack/mcp   (JSON-RPC 2.0)
    POST /capiq/mcp       (JSON-RPC 2.0)

Start with:
    uvicorn deep_research.mock_mcp:app --port 8001 --reload

Expected env vars for deep_research to reach this server:
    MCP_RAVENPACK_ENDPOINT=http://localhost:8001/ravenpack
    MCP_CAPIQ_ENDPOINT=http://localhost:8001/capiq

Cleanup: just stop the uvicorn process (or docker-compose down).
"""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load fixtures once at startup
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    path = _FIXTURE_DIR / name
    if not path.exists():
        logger.warning("Fixture %s not found – returning empty list", path)
        return []
    with path.open() as f:
        return json.load(f)


_NEWS: list[dict] = _load("ravenpack_news.json")
_DEALS: list[dict] = _load("capiq_deals.json")

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _ok(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _err(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _parse_body(body: dict) -> tuple[str, dict, Any]:
    """Return (method, params, id) from a JSON-RPC body."""
    method = body.get("method", "")
    params = body.get("params") or {}
    req_id = body.get("id")
    return method, params, req_id


# ---------------------------------------------------------------------------
# Tool definitions exposed to callers
# ---------------------------------------------------------------------------

_RAVENPACK_TOOLS = [
    {
        "name": "search_news",
        "description": (
            "Search RavenPack News for financial news articles. "
            "Returns a list of recent news items matching the query."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "from_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "to_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "max_results": {"type": "integer", "description": "Max articles to return", "default": 20},
                "min_relevance": {"type": "number", "description": "Minimum relevance score 0-1", "default": 0.5},
                "topics": {"type": "array", "items": {"type": "string"}, "description": "Filter by topic tags"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_entity_sentiment",
        "description": "Get aggregated sentiment score for a named entity over a date range.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "Company or person name"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
            },
            "required": ["entity_name"],
        },
    },
]

_CAPIQ_TOOLS = [
    {
        "name": "search_deals",
        "description": (
            "Search S&P Capital IQ for M&A deals, transactions, and corporate actions. "
            "Returns structured deal records with financial details."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Deal or company search query"},
                "deal_type": {"type": "string", "description": "Filter: Acquisition, Merger, Take-Private, etc."},
                "status": {"type": "string", "description": "Filter: Announced, Pending, Completed, etc."},
                "from_date": {"type": "string", "description": "Announcement date from (YYYY-MM-DD)"},
                "to_date": {"type": "string", "description": "Announcement date to (YYYY-MM-DD)"},
                "min_value_usd": {"type": "number", "description": "Minimum deal value USD"},
                "max_results": {"type": "integer", "description": "Max deals to return", "default": 15},
                "sector": {"type": "string", "description": "Filter by industry sector"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_company_financials",
        "description": "Retrieve key financials for a public or private company.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "ticker": {"type": "string"},
                "metrics": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["company_name"],
        },
    },
]

# ---------------------------------------------------------------------------
# Search logic (simple keyword matching on fixture data)
# ---------------------------------------------------------------------------


def _score_news(article: dict, query: str, min_relevance: float) -> float:
    """Return relevance score for an article, or 0 if below threshold."""
    base = article.get("relevance_score", 0.5)
    q_lower = query.lower()
    text = (
        article.get("headline", "").lower()
        + " "
        + article.get("body", "").lower()
        + " "
        + " ".join(t.lower() for t in article.get("topics", []))
        + " "
        + " ".join(e.get("name", "").lower() for e in article.get("entities", []))
    )
    boost = 0.0
    for word in q_lower.split():
        if len(word) >= 3 and word in text:
            boost += 0.05
    score = min(1.0, base + boost)
    if score < min_relevance:
        return 0.0
    return score


def _search_news(params: dict) -> list[dict]:
    query = params.get("query", "")
    min_rel = float(params.get("min_relevance", 0.5))
    max_res = int(params.get("max_results", 20))
    topic_filter = [t.lower() for t in (params.get("topics") or [])]

    scored = []
    for art in _NEWS:
        score = _score_news(art, query, min_rel)
        if score <= 0:
            continue
        if topic_filter:
            art_topics = [t.lower() for t in art.get("topics", [])]
            if not any(tf in " ".join(art_topics) for tf in topic_filter):
                continue
        scored.append({**art, "_match_score": round(score, 3)})

    scored.sort(key=lambda x: x["_match_score"], reverse=True)
    return scored[:max_res]


def _get_entity_sentiment(params: dict) -> dict:
    entity = params.get("entity_name", "").lower()
    matched = [
        art for art in _NEWS
        if any(entity in e.get("name", "").lower() for e in art.get("entities", []))
    ]
    if not matched:
        return {"entity": params.get("entity_name"), "sentiment_avg": None, "article_count": 0}
    avg_sent = sum(a.get("sentiment_score", 0.5) for a in matched) / len(matched)
    return {
        "entity": params.get("entity_name"),
        "sentiment_avg": round(avg_sent, 3),
        "article_count": len(matched),
        "sentiment_label": "positive" if avg_sent > 0.6 else ("negative" if avg_sent < 0.4 else "neutral"),
    }


def _score_deal(deal: dict, query: str) -> float:
    q_lower = query.lower()
    text = (
        deal.get("deal_name", "").lower()
        + " "
        + (deal.get("acquirer", {}).get("name", "") if isinstance(deal.get("acquirer"), dict) else "").lower()
        + " "
        + (deal.get("target", {}).get("name", "") if isinstance(deal.get("target"), dict) else "").lower()
        + " "
        + deal.get("strategic_rationale", "").lower()
        + " "
        + deal.get("notes", "").lower()
    )
    boost = sum(0.1 for word in q_lower.split() if len(word) >= 3 and word in text)
    return min(1.0, 0.5 + boost)


def _search_deals(params: dict) -> list[dict]:
    query = params.get("query", "")
    deal_type = (params.get("deal_type") or "").lower()
    status = (params.get("status") or "").lower()
    sector = (params.get("sector") or "").lower()
    min_val = float(params.get("min_value_usd") or 0)
    max_res = int(params.get("max_results", 15))

    scored = []
    for deal in _DEALS:
        val = deal.get("deal_value_usd", 0) or 0
        if val < min_val:
            continue
        if deal_type:
            dt = deal.get("deal_type", "").lower()
            if deal_type not in dt:
                continue
        if status:
            ds = deal.get("status", "").lower()
            if status not in ds:
                continue
        if sector:
            acq_sec = (deal.get("acquirer", {}) or {}).get("sector", "").lower() if isinstance(deal.get("acquirer"), dict) else ""
            tgt_sec = (deal.get("target", {}) or {}).get("sector", "").lower() if isinstance(deal.get("target"), dict) else ""
            if sector not in acq_sec and sector not in tgt_sec:
                continue
        score = _score_deal(deal, query)
        scored.append({**deal, "_match_score": round(score, 3)})

    scored.sort(key=lambda x: x["_match_score"], reverse=True)
    return scored[:max_res]


def _get_company_financials(params: dict) -> dict:
    name = (params.get("company_name") or "").lower()
    ticker = (params.get("ticker") or "").lower()

    for deal in _DEALS:
        for role in ("acquirer", "target"):
            entity = deal.get(role)
            if not isinstance(entity, dict):
                continue
            if name and name in entity.get("name", "").lower():
                return {
                    "company": entity.get("name"),
                    "ticker": entity.get("ticker"),
                    "sector": entity.get("sector"),
                    "market_cap_usd": entity.get("market_cap_usd"),
                    "revenue_ttm_usd": entity.get("revenue_ttm_usd"),
                    "ebitda_ttm_usd": entity.get("ebitda_ttm_usd"),
                    "data_source": "CapIQ mock fixture",
                }
            if ticker and ticker == entity.get("ticker", "").lower():
                return {
                    "company": entity.get("name"),
                    "ticker": entity.get("ticker"),
                    "sector": entity.get("sector"),
                    "market_cap_usd": entity.get("market_cap_usd"),
                    "revenue_ttm_usd": entity.get("revenue_ttm_usd"),
                    "ebitda_ttm_usd": entity.get("ebitda_ttm_usd"),
                    "data_source": "CapIQ mock fixture",
                }
    return {"company": params.get("company_name"), "error": "Not found in mock data"}


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="Mock MCP Server (RavenPack + CapIQ)", version="0.1.0")


async def _dispatch_ravenpack(body: dict) -> dict:
    method, params, req_id = _parse_body(body)

    if method == "initialize":
        return _ok(req_id, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "mock-ravenpack", "version": "0.1.0"}, "capabilities": {"tools": {}}})

    if method == "tools/list":
        return _ok(req_id, {"tools": _RAVENPACK_TOOLS})

    if method == "tools/call":
        tool_name = params.get("name")
        tool_params = params.get("arguments") or params.get("input") or {}

        if tool_name == "search_news":
            results = _search_news(tool_params)
            return _ok(req_id, {"content": [{"type": "text", "text": json.dumps({"articles": results, "total": len(results), "source": "RavenPack News (mock)"})}]})

        if tool_name == "get_entity_sentiment":
            result = _get_entity_sentiment(tool_params)
            return _ok(req_id, {"content": [{"type": "text", "text": json.dumps(result)}]})

        return _err(req_id, -32601, f"Unknown tool: {tool_name}")

    return _err(req_id, -32601, f"Unknown method: {method}")


async def _dispatch_capiq(body: dict) -> dict:
    method, params, req_id = _parse_body(body)

    if method == "initialize":
        return _ok(req_id, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "mock-capiq", "version": "0.1.0"}, "capabilities": {"tools": {}}})

    if method == "tools/list":
        return _ok(req_id, {"tools": _CAPIQ_TOOLS})

    if method == "tools/call":
        tool_name = params.get("name")
        tool_params = params.get("arguments") or params.get("input") or {}

        if tool_name == "search_deals":
            results = _search_deals(tool_params)
            return _ok(req_id, {"content": [{"type": "text", "text": json.dumps({"deals": results, "total": len(results), "source": "S&P Capital IQ (mock)"})}]})

        if tool_name == "get_company_financials":
            result = _get_company_financials(tool_params)
            return _ok(req_id, {"content": [{"type": "text", "text": json.dumps(result)}]})

        return _err(req_id, -32601, f"Unknown tool: {tool_name}")

    return _err(req_id, -32601, f"Unknown method: {method}")


def _sse(payload: dict) -> Response:
    """Wrap a JSON-RPC result in SSE format that parse_sse_response() can read."""
    body = f"data: {json.dumps(payload)}\n\n"
    return Response(content=body, media_type="text/event-stream")


async def _handle_ravenpack(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    result = await _dispatch_ravenpack(body)
    return _sse(result)


async def _handle_capiq(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    result = await _dispatch_capiq(body)
    return _sse(result)


# Serve at both /ravenpack and /ravenpack/mcp so the MCPToolAdapter works
# regardless of whether use_path_routing=True or False is chosen.
@app.post("/ravenpack")
@app.post("/ravenpack/mcp")
async def ravenpack_mcp(request: Request) -> JSONResponse:
    return await _handle_ravenpack(request)


@app.post("/capiq")
@app.post("/capiq/mcp")
async def capiq_mcp(request: Request) -> JSONResponse:
    return await _handle_capiq(request)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "ravenpack_articles": len(_NEWS),
        "capiq_deals": len(_DEALS),
    }


@app.get("/")
async def root() -> dict:
    return {
        "service": "Mock MCP Server",
        "endpoints": {
            "ravenpack": "POST /ravenpack/mcp",
            "capiq": "POST /capiq/mcp",
            "health": "GET /health",
        },
        "note": "For local development only. Replace with real MCP endpoints in production.",
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("MOCK_MCP_PORT", "8001"))
    uvicorn.run("deep_research.mock_mcp:app", host="0.0.0.0", port=port, reload=True)
