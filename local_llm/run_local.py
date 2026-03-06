"""Run the Deep Research Agent locally with a real Claude LLM.

Usage
-----
    # 1. Copy the template and add your key
    cp local_llm/.env.template local_llm/.env.local
    # edit local_llm/.env.local → set ANTHROPIC_API_KEY=sk-ant-...

    # 2. Make sure docker-compose services are up (Redis + mock MCP)
    docker compose -f deep_research/docker-compose.dev.yml up -d

    # 3. Run
    PYTHONPATH=. python -m local_llm.run_local

Optional flags (env vars):
    RESEARCH_QUERY   — the query to run  (default: M&A deals > $1B in Q1 2026)
    OFFLOAD_THRESHOLD_BYTES — bytes before Redis offload triggers (default: 500)
                              Set very low to force offloading even with small payloads
    ANTHROPIC_MODEL  — override model (default: claude-3-5-haiku-20241022)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time

# ── ensure project root on PYTHONPATH ────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from local_llm.client import ClaudeClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("local_run")

# Silence noisy library loggers
for _lib in ("httpx", "httpcore", "anthropic._base_client"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

# ── Config ────────────────────────────────────────────────────────────────────
MOCK_MCP_BASE = os.environ.get("MOCK_MCP_BASE", "http://localhost:8001")
REDIS_HOST    = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT    = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASS    = os.environ.get("REDIS_PASSWORD", "devpassword")

# Publish Redis creds early so the framework's RedisService / EventBus
# pick them up before they initialise their own connections.
os.environ.setdefault("REDIS_HOST",     REDIS_HOST)
os.environ.setdefault("REDIS_PORT",     str(REDIS_PORT))
os.environ.setdefault("REDIS_PASSWORD", REDIS_PASS)

RESEARCH_QUERY = os.environ.get(
    "RESEARCH_QUERY",
    "Show me all M&A deals greater than $1 billion in Q1 2026",
)

# Set low to force offloading even on small payloads during local tests.
# In production (real MCP responses) this would naturally be >> 50 000 bytes.
OFFLOAD_THRESHOLD = int(os.environ.get("OFFLOAD_THRESHOLD_BYTES", "500"))

# Use claude-3-5-sonnet for higher-quality, longer reports.
# Falls back to claude-3-haiku-20240307 if sonnet is not available on your key.
os.environ.setdefault("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# Give the report step plenty of room — deep research reports are long
os.environ.setdefault("LLM_MAX_TOKENS", "8192")
os.environ.setdefault("REACT_MAX_TOKENS", "4096")
os.environ.setdefault("PLANNER_MAX_SUB_QUERIES", "5")
os.environ.setdefault("RESULTS_PER_SOURCE", "30")

# Dummy MCP creds so MCPToolAdapter can generate a JWT for the mock server
os.environ.setdefault("MCP_USER_EMAIL", "local@test.com")
os.environ.setdefault("MCP_SECRET", "local-dev-secret-key-32chars!!!!")


# ── Redis inspection helpers ──────────────────────────────────────────────────

async def redis_keys(pattern: str = "*") -> list[str]:
    """Return all Redis keys matching pattern via redis.asyncio."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS, decode_responses=True)
        keys = await r.keys(pattern)
        await r.aclose()
        return sorted(keys)
    except Exception as exc:
        logger.warning("Redis key scan failed: %s", exc)
        return []


async def redis_key_sizes() -> dict[str, int]:
    """Return {key: byte_size} for all keys."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS, decode_responses=False)
        keys = await r.keys("*")
        sizes = {}
        for k in keys:
            try:
                v = await r.get(k)
                sizes[k.decode()] = len(v) if v else 0
            except Exception:
                pass
        await r.aclose()
        return sizes
    except Exception as exc:
        logger.warning("Redis size scan failed: %s", exc)
        return {}


def _banner(text: str) -> None:
    width = 70
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def _section(text: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print("─" * 60)


# ── Preflight checks ──────────────────────────────────────────────────────────

async def check_mock_mcp() -> bool:
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{MOCK_MCP_BASE}/health")
            data = r.json()
            print(f"  ✓ Mock MCP healthy — {data.get('news_articles', '?')} news articles, "
                  f"{data.get('capiq_deals', '?')} CapIQ deals")
            return True
        except Exception as exc:
            print(f"  ✗ Mock MCP not reachable: {exc}")
            print("    Run:  docker compose -f deep_research/docker-compose.dev.yml up -d")
            return False


async def check_redis() -> bool:
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS)
        await r.ping()
        await r.aclose()
        print(f"  ✓ Redis healthy at {REDIS_HOST}:{REDIS_PORT}")
        return True
    except Exception as exc:
        print(f"  ✗ Redis not reachable: {exc}")
        print("    Run:  docker compose -f deep_research/docker-compose.dev.yml up -d")
        return False


# ── Main run ──────────────────────────────────────────────────────────────────

async def main() -> None:
    _banner("Deep Research Agent — Local Run with Claude + Redis Offload")

    # 1. Build Claude client (reads ANTHROPIC_API_KEY from local_llm/.env.local)
    try:
        llm = ClaudeClient.from_env()
    except RuntimeError as exc:
        print(f"\n  ERROR: {exc}\n")
        sys.exit(1)

    # 2. Preflight checks
    _section("Preflight checks")
    mcp_ok    = await check_mock_mcp()
    redis_ok  = await check_redis()
    if not (mcp_ok and redis_ok):
        sys.exit(1)

    # 3. Snapshot Redis keys before run
    _section("Redis keys BEFORE pipeline run")
    keys_before = await redis_keys()
    if keys_before:
        for k in keys_before:
            print(f"    {k}")
    else:
        print("    (no keys — Redis is empty)")

    # 4. Wire up the orchestrator
    _section("Building pipeline")
    from agentorchestrator.core.orchestrator import AgentOrchestrator
    from agentorchestrator.core.context import RedisContextStore
    from agentorchestrator.middleware.offload import OffloadMiddleware
    from agentorchestrator.services.mcp_service import MCPServiceManager
    from deep_research.pipeline import build_pipeline, setup_middleware
    from deep_research.config import settings

    # Override context_store_backend so OffloadMiddleware uses real Redis
    settings.context_store_backend = "redis"
    settings.redis_host    = REDIS_HOST
    settings.redis_port    = REDIS_PORT
    settings.redis_password = REDIS_PASS

    ao = AgentOrchestrator(name="local_run", version="0.1.0", isolated=True)
    build_pipeline(ao)
    setup_middleware(ao, llm)

    # 5. Connect MCP adapters (mock server)
    _section("Connecting MCP adapters")
    _mcp = MCPServiceManager()

    from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter
    for name, path in [("ravenpack", "ravenpack"), ("capiq", "capiq")]:
        adapter = MCPToolAdapter(name=name)
        connected = await adapter.connect(
            endpoint=f"{MOCK_MCP_BASE}/{path}",
            secret=None,
            use_path_routing=False,
            verify_ssl=False,
        )
        if connected:
            _mcp.register_adapter(adapter)
            print(f"  ✓ {name:12s} → {MOCK_MCP_BASE}/{path}  ({len(adapter.tools_list)} tools)")
        else:
            print(f"  ✗ {name:12s} failed to connect — pipeline will use stubs")

    # 6. Run the pipeline
    _section(f"Running pipeline — query: {RESEARCH_QUERY!r}")
    t0 = time.perf_counter()

    steps_log: list[tuple[str, float]] = []

    def _debug_cb(ctx: object, step_name: str, result: dict) -> None:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        steps_log.append((step_name, elapsed_ms))
        size = len(json.dumps(result, default=str))
        offloaded = "→ OFFLOADED to Redis" if size > OFFLOAD_THRESHOLD else ""
        print(f"  ✓ {step_name:<25s}  {elapsed_ms:7.1f} ms  |  output ~{size:,} bytes  {offloaded}")

    result = await ao.launch(
        "deep_research",
        {
            "query": RESEARCH_QUERY,
            "llm_client": llm,
            "mcp_service": _mcp,
        },
        request_id="local-run-001",
        debug_callback=_debug_cb,
    )
    total_ms = (time.perf_counter() - t0) * 1000

    # 7. Redis keys AFTER run — show what was offloaded
    _section("Redis keys AFTER pipeline run")
    sizes_after = await redis_key_sizes()
    keys_after  = sorted(sizes_after.keys())
    new_keys    = [k for k in keys_after if k not in keys_before]

    if new_keys:
        print(f"  {len(new_keys)} new key(s) written by OffloadMiddleware:\n")
        for k in new_keys:
            sz = sizes_after[k]
            print(f"    {k}")
            print(f"      size: {sz:,} bytes  ({sz / 1024:.1f} KB)")
    else:
        print("  No new Redis keys — all step outputs were under the offload threshold.")
        print(f"  (current threshold = {OFFLOAD_THRESHOLD:,} bytes, set OFFLOAD_THRESHOLD_BYTES to lower it)")

    # 8. Results summary
    _section(f"Pipeline completed in {total_ms:.0f} ms")
    ctx_data: dict = result.get("context", {}).get("data", {})

    plan = ctx_data.get("research_plan", {})
    print(f"\n  Research plan sub-queries: {len(plan.get('sub_queries', []))}")
    for i, q in enumerate(plan.get("sub_queries", []), 1):
        print(f"    {i}. {q}")

    news  = ctx_data.get("news_findings",  [])
    capiq = ctx_data.get("capiq_findings", [])
    agg   = ctx_data.get("aggregated_findings", [])
    print(f"\n  Findings  →  RavenPack: {len(news)}  |  CapIQ: {len(capiq)}  |  Aggregated (unique): {len(agg)}")

    verified = ctx_data.get("verified_findings", [])
    flagged  = ctx_data.get("flagged_findings", [])
    print(f"  Verified: {len(verified)}  |  Flagged: {len(flagged)}")

    # 9. Print the full report
    report = ctx_data.get("report", "")
    if report:
        _banner("FINAL RESEARCH REPORT")
        print(report)
    else:
        print("\n  WARNING: report not found in context — check logs above for errors")

    # ── Citation summary ──────────────────────────────────────────────────
    cs = ctx_data.get("citation_summary") or {}
    if cs.get("total", 0) > 0:
        _banner("CITATION SUMMARY")
        print(f"  Total citations:   {cs['total']}")
        print(f"  Verified:          {cs['verified']}  ({cs.get('verification_rate', 0):.0%})")
        print(f"  Unverified:        {cs.get('unverified', 0)}")
        print(f"  By source:         {cs.get('by_source', {})}")
        print()

    _banner("RUN COMPLETE")
    print(f"  Total wall time: {total_ms:.0f} ms")
    print(f"  Model:           {llm.model}")
    print(f"  Redis keys written: {len(new_keys)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
