#!/usr/bin/env python3
"""End-to-end test for the Deep Research Agent.

Tests the full pipeline using:
  • mock_mcp.py     — fake RavenPack News + CapIQ fixture data (port 8001)
  • Local Redis     — started by docker-compose.dev.yml (port 6379)
  • Stub LLM calls  — overrides LLMGatewayClient with deterministic stubs so
                      no real LLM endpoint is required

Usage
─────
  # 1. Start the dev stack (Redis + mock MCP):
  docker compose -f deep_research/docker-compose.dev.yml up -d

  # 2. Run the E2E test (from repo root):
  python -m deep_research.run_e2e

  # 3. Optional: run against the live service instead of in-process:
  python -m deep_research.run_e2e --mode http --base-url http://localhost:8000

Exit codes
──────────
  0  All assertions passed
  1  One or more assertions failed
  2  Infrastructure not reachable (Redis / mock MCP down)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import traceback
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("e2e")

# ─────────────────────────────────────────────────────────────────────────────
# Infrastructure readiness checks
# ─────────────────────────────────────────────────────────────────────────────

MOCK_MCP_BASE = "http://localhost:8001"
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_PASSWORD = "devpassword"


async def check_mock_mcp() -> bool:
    """Verify mock MCP server is up and serving fixture data."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{MOCK_MCP_BASE}/health")
            r.raise_for_status()
            data = r.json()
            assert data["ravenpack_articles"] > 0, "No RavenPack articles in fixture"
            assert data["capiq_deals"] > 0, "No CapIQ deals in fixture"
            logger.info(
                "✓ Mock MCP server healthy — %d news articles, %d deals",
                data["ravenpack_articles"],
                data["capiq_deals"],
            )
            return True
    except Exception as exc:
        logger.error("✗ Mock MCP server not reachable: %s", exc)
        logger.error(
            "  Start it with: docker compose -f deep_research/docker-compose.dev.yml up -d"
        )
        return False


async def check_redis() -> bool:
    """Verify Redis is up."""
    try:
        import redis.asyncio as aioredis  # type: ignore

        r = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)
        await r.ping()
        await r.aclose()
        logger.info("✓ Redis healthy at %s:%s", REDIS_HOST, REDIS_PORT)
        return True
    except Exception as exc:
        logger.error("✗ Redis not reachable: %s", exc)
        logger.error(
            "  Start it with: docker compose -f deep_research/docker-compose.dev.yml up -d"
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# LLM stub — avoids real LLM dependency
# ─────────────────────────────────────────────────────────────────────────────

def _make_llm_stub() -> MagicMock:
    """Return a mock LLMGatewayClient that returns plausible JSON responses."""

    stub = MagicMock()

    async def _complete(prompt: str, **kwargs: Any) -> str:
        # Step detection from prompt content
        p = prompt.lower()

        # Planning step: the planner prompt contains "research plan" AND asks for sub_queries JSON
        if ("research plan" in p or "research planning assistant" in p) and "sub_queries" in p:
            return json.dumps({
                "sub_queries": [
                    "M&A deals technology sector 2026",
                    "large acquisitions financial sector Q1 2026",
                ],
                "date_range": {"from": "2026-01-01", "to": "2026-03-05"},
                "min_value_usd": 1000000000,
                "system_instructions": ["Focus on deals > $1B", "Include all sectors"],
                "entities_of_interest": ["technology", "healthcare", "energy"],
            })

        # ReAct search agent prompt: always begins with "Question: Research the following sub-queries"
        if "question:" in p and "research the following" in p:
            findings = json.dumps([
                {
                    "title": "Alphabet Acquires Wiz for $32B",
                    "date": "2026-02-25",
                    "source": "RavenPack",
                    "deal_value_usd": 32000000000,
                    "acquirer": "Alphabet Inc.",
                    "target": "Wiz Inc.",
                    "sector": "Cloud Security",
                    "summary": "Alphabet acquired Wiz in the largest deal in its history.",
                },
                {
                    "title": "BlackRock / HPS Investment Partners",
                    "date": "2026-01-12",
                    "source": "CapIQ",
                    "deal_id": "ciq-2026-00452",
                    "deal_value_usd": 12500000000,
                    "acquirer": "BlackRock Inc.",
                    "target": "HPS Investment Partners",
                    "sector": "Asset Management",
                    "summary": "BlackRock acquires credit-focused HPS to build out alternatives platform.",
                },
            ])
            return f"Thought: I have the findings.\nFinal Answer: {findings}"

        if "cross-verif" in p or "verify" in p or "conflict" in p:
            return json.dumps({
                "verified_findings": [
                    {
                        "claim": "Alphabet acquired Wiz for $32B",
                        "confidence": 0.98,
                        "sources": ["RavenPack News", "CapIQ Deals"],
                        "conflicts": [],
                    },
                    {
                        "claim": "BlackRock acquired HPS Investment Partners for $12.5B",
                        "confidence": 0.97,
                        "sources": ["RavenPack News", "CapIQ Deals"],
                        "conflicts": [],
                    },
                ],
                "conflicts_detected": [],
                "overall_confidence": 0.95,
            })

        if "report" in p or "markdown" in p or "summary" in p:
            return """# M&A Market Research Report: Q1 2026

## Executive Summary

The first quarter of 2026 has seen robust M&A activity, with several landmark transactions
across technology, healthcare, and energy sectors. Total deal value for analyzed transactions
exceeds $200 billion.

## Key Findings

### Technology Sector
- **Alphabet / Wiz** ($32B): Largest acquisition in Alphabet history; enhances Google Cloud
  security portfolio. Pending HSR regulatory review.
- **Meta Platforms / Scale AI** ($14.3B): Secures proprietary AI training data pipeline.
  Under FTC scrutiny.

### Financial Services
- **BlackRock / HPS Investment Partners** ($12.5B): Creates world's largest private credit
  platform with $12.5T total AUM.

### Healthcare
- **Elevance Health / Molina Healthcare** ($19B): Creates largest Medicare Advantage provider
  in the United States.

## Deal Statistics

| Metric | Value |
|--------|-------|
| Total deals analyzed | 35 |
| Combined deal value | ~$250B |
| Average deal premium | 32% |
| Largest deal | Chevron/Hess ($58B) |

## Methodology

Research conducted via RavenPack News and S&P Capital IQ. Findings cross-verified with
confidence score 0.95. All values in USD unless otherwise stated.

*Generated by Deep Research Agent v1.0.0*
"""

        if "react" in p or "action" in p or "thought" in p:
            return json.dumps({
                "thought": "I should search for M&A deals matching the query.",
                "action": "search_news",
                "action_input": {"query": "M&A deals technology 2026", "max_results": 15},
            })

        # Default fallback
        return json.dumps({"result": "Stub LLM response", "success": True})

    stub.complete = AsyncMock(side_effect=_complete)
    stub.chat = AsyncMock(side_effect=_complete)
    stub.generate = AsyncMock(side_effect=_complete)
    stub.generate_async = AsyncMock(side_effect=_complete)
    stub.acomplete = AsyncMock(side_effect=_complete)
    return stub


# ─────────────────────────────────────────────────────────────────────────────
# In-process pipeline test
# ─────────────────────────────────────────────────────────────────────────────

async def run_in_process_test() -> bool:
    """Run the full deep_research pipeline in-process with mocked LLM."""
    logger.info("─" * 60)
    logger.info("In-process E2E test (stub LLM + mock MCP + local Redis)")
    logger.info("─" * 60)

    # Set env vars before importing settings
    import os
    os.environ.setdefault("CONTEXT_STORE_BACKEND", "redis")
    os.environ.setdefault("REDIS_HOST", REDIS_HOST)
    os.environ.setdefault("REDIS_PORT", str(REDIS_PORT))
    os.environ.setdefault("REDIS_PASSWORD", REDIS_PASSWORD)
    os.environ.setdefault("MCP_RAVENPACK_ENDPOINT", f"{MOCK_MCP_BASE}/ravenpack")
    os.environ.setdefault("MCP_RAVENPACK_ROUTING", "jsonrpc")
    os.environ.setdefault("MCP_CAPIQ_ENDPOINT", f"{MOCK_MCP_BASE}/capiq")
    os.environ.setdefault("MCP_CAPIQ_ROUTING", "jsonrpc")
    # Dummy auth env vars so MCPToolAdapter can generate a JWT for the mock server
    # (the mock MCP server ignores authentication headers entirely)
    os.environ.setdefault("MCP_USER_EMAIL", "dev@local.test")
    os.environ.setdefault("MCP_SECRET", "dev-local-secret-for-testing-only")
    os.environ.setdefault("MCP_USER_NAME", "Dev User")
    os.environ.setdefault("MAX_OBSERVATION_CHARS", "32000")
    os.environ.setdefault("REACT_MAX_ITERATIONS", "2")
    os.environ.setdefault("PLANNER_MAX_SUB_QUERIES", "2")
    os.environ.setdefault("RESULTS_PER_SOURCE", "5")

    # Import after env vars are set so Settings picks them up
    # Re-instantiate settings to pick up env changes
    import importlib
    import deep_research.config as cfg_module
    cfg_module.settings = cfg_module.Settings()

    from agentorchestrator.core.orchestrator import AgentOrchestrator
    from agentorchestrator.services.mcp_service import MCPServiceManager
    from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter
    from deep_research.pipeline import CHAIN_NAME, build_pipeline, setup_middleware

    llm_stub = _make_llm_stub()

    # Build orchestrator
    ao = AgentOrchestrator(
        name="e2e_test",
        max_parallel=2,
        default_timeout_ms=30_000,
    )
    build_pipeline(ao)
    setup_middleware(ao, llm_stub)

    # Connect mock MCP adapters
    mcp = MCPServiceManager()
    for source_name, endpoint in [
        ("ravenpack", f"{MOCK_MCP_BASE}/ravenpack"),
        ("capiq", f"{MOCK_MCP_BASE}/capiq"),
    ]:
        adapter = MCPToolAdapter(name=source_name)
        connected = await adapter.connect(
            endpoint=endpoint,
            secret=None,
            use_path_routing=False,
            verify_ssl=False,
        )
        if connected:
            mcp.register_adapter(adapter)
            logger.info("  ✓ MCP adapter '%s' connected → %s", source_name, endpoint)
        else:
            logger.warning("  ✗ MCP adapter '%s' failed — will use stubs", source_name)

    # Patch LLM calls in steps that instantiate LLMGatewayClient
    with patch(
        "agentorchestrator.services.llm_gateway.LLMGatewayClient",
        return_value=llm_stub,
    ):
        initial_data = {
            "query": "Show me all M&A deals greater than $1 billion in Q1 2026",
            "system_instructions": ["Focus on technology and healthcare sectors"],
            "llm_client": llm_stub,
            "mcp_service": mcp,
        }

        steps_seen: list[str] = []

        def _dbg(ctx: Any, step_name: str, result: dict) -> None:
            status = "✓" if result.get("success", True) else "✗"
            dur = round(result.get("duration_ms", 0), 0)
            logger.info("  %s Step %-22s  %s ms", status, step_name, dur)
            if result.get("success", True):
                steps_seen.append(step_name)

        logger.info("Launching deep_research pipeline…")
        t0 = time.perf_counter()

        try:
            result = await ao.launch(
                CHAIN_NAME,
                initial_data,
                request_id="e2e-test-001",
                debug_callback=_dbg,
            )
            elapsed = round((time.perf_counter() - t0) * 1000)

            logger.info("")
            logger.info("Pipeline completed in %d ms", elapsed)
        except Exception as exc:
            elapsed = round((time.perf_counter() - t0) * 1000)
            logger.error("Pipeline raised exception after %d ms: %s", elapsed, exc)
            traceback.print_exc()
            return False

    # ── Assertions ────────────────────────────────────────────────────────────
    failures: list[str] = []

    expected_steps = {
        "plan_research", "search_news", "search_capiq",
        "aggregate_sources", "cross_verify", "generate_report",
    }
    missing = expected_steps - set(steps_seen)
    if missing:
        failures.append(f"Steps not completed: {missing}")

    # Step outputs are in result["context"]["data"] (set via ctx.set() in steps)
    ctx_data: dict = result.get("context", {}).get("data", {})

    report = ctx_data.get("report")
    if not report:
        failures.append("Final report is empty")
    else:
        logger.info("  ✓ Report generated (%d chars)", len(report))

    if ctx_data.get("research_plan"):
        logger.info("  ✓ Research plan present in context")

    news = ctx_data.get("news_findings") or []
    capiq = ctx_data.get("capiq_findings") or []
    if not news and not capiq:
        failures.append("No findings from either source (both news_findings and capiq_findings empty)")
    else:
        logger.info("  ✓ Findings: %d news, %d deals", len(news), len(capiq))

    agg = ctx_data.get("aggregated_findings") or []
    logger.info("  ✓ Aggregated findings: %d items", len(agg))

    # ── Result ────────────────────────────────────────────────────────────────
    if failures:
        logger.error("")
        logger.error("FAILURES (%d):", len(failures))
        for f in failures:
            logger.error("  • %s", f)
        return False

    logger.info("")
    logger.info("All assertions passed ✓")

    # Print a snippet of the report
    report = result.get("report", "")
    snippet = report[:500].replace("\n", "\n  ")
    logger.info("")
    logger.info("Report snippet:\n  %s…", snippet)

    return True


# ─────────────────────────────────────────────────────────────────────────────
# HTTP mode — test against a running service
# ─────────────────────────────────────────────────────────────────────────────

async def run_http_test(base_url: str) -> bool:
    """Test against a live running service via HTTP."""
    logger.info("─" * 60)
    logger.info("HTTP E2E test → %s", base_url)
    logger.info("─" * 60)

    async with httpx.AsyncClient(base_url=base_url, timeout=180) as client:
        # Health check
        try:
            r = await client.get("/health")
            health = r.json()
            logger.info("Health: %s", json.dumps(health, indent=2))
        except Exception as exc:
            logger.error("Health check failed: %s", exc)
            return False

        # Submit streaming run
        payload = {
            "query": "Show me all M&A deals greater than $1B in Q1 2026",
            "system_instructions": ["Focus on completed and announced deals"],
        }
        logger.info("Submitting streaming research run…")
        steps_seen: list[str] = []
        final_event: dict = {}

        try:
            async with client.stream(
                "POST",
                "/run/deep_research/stream",
                json=payload,
                headers={"Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()
                run_id = response.headers.get("X-Run-Id", "unknown")
                logger.info("Run ID: %s", run_id)

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("event")
                    if etype == "step_completed":
                        status = "✓" if event.get("success", True) else "✗"
                        logger.info(
                            "  %s %-22s  %.0f ms",
                            status,
                            event.get("step", ""),
                            event.get("duration_ms", 0),
                        )
                        if event.get("success"):
                            steps_seen.append(event["step"])
                    elif etype in ("pipeline_completed", "pipeline_failed"):
                        final_event = event
                        break

        except Exception as exc:
            logger.error("Streaming request failed: %s", exc)
            traceback.print_exc()
            return False

        # Assertions
        failures: list[str] = []
        if final_event.get("event") != "pipeline_completed":
            failures.append(
                f"Pipeline did not complete: {final_event.get('event')} — {final_event.get('error')}"
            )

        expected_steps = {
            "plan_research", "search_news", "search_capiq",
            "aggregate_sources", "cross_verify", "generate_report",
        }
        missing = expected_steps - set(steps_seen)
        if missing:
            failures.append(f"Steps not seen in stream: {missing}")

        # Fetch the report
        if run_id != "unknown":
            r = await client.get(f"/runs/{run_id}/output")
            if r.status_code == 200:
                output = r.json()
                if not output.get("report"):
                    failures.append("Report is empty in /output endpoint")
                else:
                    logger.info("  ✓ Report retrieved (%d chars)", len(output["report"]))

        if failures:
            logger.error("FAILURES (%d):", len(failures))
            for f in failures:
                logger.error("  • %s", f)
            return False

        logger.info("All assertions passed ✓")
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Mock MCP unit tests
# ─────────────────────────────────────────────────────────────────────────────

async def run_mock_mcp_unit_tests() -> bool:
    """Quick JSON-RPC 2.0 tests against the mock MCP server."""
    logger.info("─" * 60)
    logger.info("Mock MCP unit tests")
    logger.info("─" * 60)
    failures: list[str] = []

    async with httpx.AsyncClient(timeout=10) as client:

        cases = [
            # (description, url, payload, assertion_fn)
            (
                "RavenPack tools/list",
                f"{MOCK_MCP_BASE}/ravenpack/mcp",
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                lambda r: len(r.get("result", {}).get("tools", [])) >= 1,
            ),
            (
                "RavenPack search_news",
                f"{MOCK_MCP_BASE}/ravenpack/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "search_news", "arguments": {"query": "M&A acquisition 2026", "max_results": 5}},
                },
                lambda r: len(json.loads(r["result"]["content"][0]["text"]).get("articles", [])) > 0,
            ),
            (
                "CapIQ tools/list",
                f"{MOCK_MCP_BASE}/capiq/mcp",
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
                lambda r: len(r.get("result", {}).get("tools", [])) >= 1,
            ),
            (
                "CapIQ search_deals",
                f"{MOCK_MCP_BASE}/capiq/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "search_deals", "arguments": {"query": "technology acquisition", "max_results": 5}},
                },
                lambda r: len(json.loads(r["result"]["content"][0]["text"]).get("deals", [])) > 0,
            ),
            (
                "RavenPack entity sentiment",
                f"{MOCK_MCP_BASE}/ravenpack/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "get_entity_sentiment", "arguments": {"entity_name": "Alphabet"}},
                },
                lambda r: r["result"]["content"][0]["text"] is not None,
            ),
            (
                "CapIQ company financials",
                f"{MOCK_MCP_BASE}/capiq/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "get_company_financials", "arguments": {"company_name": "BlackRock"}},
                },
                lambda r: r["result"]["content"][0]["text"] is not None,
            ),
        ]

        def _parse_mock_resp(resp_text: str) -> dict:
            """Parse SSE or plain JSON from mock MCP response."""
            for line in resp_text.strip().split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
            return json.loads(resp_text)

        for desc, url, payload, assert_fn in cases:
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = _parse_mock_resp(resp.text)
                if "error" in data:
                    failures.append(f"{desc}: JSON-RPC error — {data['error']}")
                    logger.error("  ✗ %s → %s", desc, data["error"])
                elif assert_fn(data):
                    logger.info("  ✓ %s", desc)
                else:
                    failures.append(f"{desc}: assertion failed — {json.dumps(data)[:200]}")
                    logger.error("  ✗ %s", desc)
            except Exception as exc:
                failures.append(f"{desc}: exception — {exc}")
                logger.error("  ✗ %s: %s", desc, exc)

    if failures:
        logger.error("Mock MCP FAILURES (%d):", len(failures))
        for f in failures:
            logger.error("  • %s", f)
        return False

    logger.info("All mock MCP tests passed ✓")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main(mode: str, base_url: str) -> int:
    logger.info("=" * 60)
    logger.info("Deep Research Agent — End-to-End Test")
    logger.info("Mode: %s", mode)
    logger.info("=" * 60)

    # ── Infra checks ──────────────────────────────────────────────────────────
    mcp_ok = await check_mock_mcp()
    redis_ok = await check_redis()

    if not mcp_ok or not redis_ok:
        logger.error("")
        logger.error("Infrastructure not ready.  Start the dev stack:")
        logger.error("  docker compose -f deep_research/docker-compose.dev.yml up -d")
        return 2

    logger.info("")

    # ── Mock MCP unit tests ───────────────────────────────────────────────────
    mcp_tests_ok = await run_mock_mcp_unit_tests()
    logger.info("")

    # ── Pipeline test ─────────────────────────────────────────────────────────
    if mode == "http":
        pipeline_ok = await run_http_test(base_url)
    else:
        pipeline_ok = await run_in_process_test()

    logger.info("")
    logger.info("=" * 60)
    if mcp_tests_ok and pipeline_ok:
        logger.info("RESULT: ALL TESTS PASSED ✓")
        logger.info("=" * 60)
        return 0
    else:
        logger.error("RESULT: SOME TESTS FAILED ✗")
        if not mcp_tests_ok:
            logger.error("  • Mock MCP unit tests failed")
        if not pipeline_ok:
            logger.error("  • Pipeline E2E test failed")
        logger.info("=" * 60)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deep Research Agent E2E test")
    parser.add_argument(
        "--mode",
        choices=["in-process", "http"],
        default="in-process",
        help="Test mode: in-process (default) or http (against running service)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL for HTTP mode (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(main(args.mode, args.base_url))
    sys.exit(exit_code)
