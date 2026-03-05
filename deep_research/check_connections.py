"""
Deep Research Agent — Connection Checker
=========================================
Run this BEFORE starting the full service to verify all external dependencies.

Usage (from repo root):
    python -m deep_research.check_connections

    # Or with an explicit env file:
    env $(cat deep_research/.env.corp | grep -v ^# | xargs) \
        python -m deep_research.check_connections

Checks:
  1. Redis           — ping + SET/GET round-trip
  2. LLM Gateway     — minimal chat completion (1 token)
  3. RavenPack MCP   — connect + tools/list
  4. CapIQ MCP       — connect + tools/list
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

# ── Load .env.* if present ────────────────────────────────────────────────────
def _load_dotenv(path: str) -> None:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass

for _p in ["deep_research/.env", "deep_research/.env.corp", ".env"]:
    _load_dotenv(_p)


# ── Helpers ───────────────────────────────────────────────────────────────────

_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

def _ok(label: str, detail: str = "") -> None:
    marker = f"{_GREEN}✓{_RESET}"
    print(f"  {marker}  {_BOLD}{label}{_RESET}  {detail}")

def _fail(label: str, detail: str = "") -> None:
    marker = f"{_RED}✗{_RESET}"
    print(f"  {marker}  {_BOLD}{label}{_RESET}  {_RED}{detail}{_RESET}")

def _warn(label: str, detail: str = "") -> None:
    marker = f"{_YELLOW}!{_RESET}"
    print(f"  {marker}  {_BOLD}{label}{_RESET}  {_YELLOW}{detail}{_RESET}")

def _section(title: str) -> None:
    print(f"\n{_BOLD}{'─'*60}{_RESET}")
    print(f"{_BOLD}  {title}{_RESET}")
    print(f"{_BOLD}{'─'*60}{_RESET}")


# ── Redis ─────────────────────────────────────────────────────────────────────

async def check_redis() -> bool:
    _section("1 / 4  Redis")
    host     = os.getenv("REDIS_HOST", "localhost")
    port     = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD") or None
    username = os.getenv("REDIS_USERNAME") or None
    use_ssl  = os.getenv("REDIS_SSL", "false").lower() == "true"
    backend  = os.getenv("CONTEXT_STORE_BACKEND", "memory")

    print(f"  Host:    {host}:{port}")
    print(f"  SSL:     {use_ssl}")
    print(f"  Backend: {backend}")

    if backend != "redis":
        _warn("Redis", "CONTEXT_STORE_BACKEND != redis — skipping (in-memory offload will be used)")
        return True

    try:
        from agentorchestrator.services.redis import RedisService
        t0 = time.monotonic()
        svc = RedisService(
            host=host, port=port,
            password=password, username=username, ssl=use_ssl,
        )
        # RedisService requires an explicit connect() before use
        await svc.connect()
        await svc.ping()
        ms = (time.monotonic() - t0) * 1000

        # Round-trip SET / GET
        await svc.set("ao_check", "ok", ttl=10)
        val = await svc.get("ao_check")
        assert val in (b"ok", "ok"), f"unexpected value: {val!r}"

        _ok("Redis ping + SET/GET", f"{ms:.0f} ms")
        return True

    except Exception as exc:
        _fail("Redis", str(exc))
        print(f"       {_YELLOW}Tip: check REDIS_HOST, REDIS_PORT, REDIS_PASSWORD in your .env{_RESET}")
        return False


# ── LLM Gateway ───────────────────────────────────────────────────────────────

async def check_llm() -> bool:
    _section("2 / 4  LLM Gateway")
    url        = os.getenv("LLM_SERVER_URL", "")
    model      = os.getenv("LLM_MODEL_NAME", "")
    api_key    = os.getenv("LLM_API_KEY", "")
    oauth_ep   = os.getenv("LLM_OAUTH_ENDPOINT", "")
    client_id  = os.getenv("LLM_CLIENT_ID", "")
    secret     = os.getenv("LLM_CLIENT_SECRET", "")
    # Corporate environments often use internal CAs not in the default bundle.
    # Set LLM_VERIFY_SSL=false in your .env to bypass cert verification.
    verify_ssl = os.getenv("LLM_VERIFY_SSL", "true").lower() != "false"

    print(f"  URL:        {url or '(not set)'}")
    print(f"  Model:      {model or '(not set)'}")
    print(f"  Auth:       {'OAuth' if oauth_ep else 'API key' if api_key else 'none'}")
    print(f"  Verify SSL: {verify_ssl}")

    if not url:
        _warn("LLM Gateway", "LLM_SERVER_URL not set — skipping")
        return True

    # If using OAuth + corporate CA, the SSL fetch itself may fail.
    # Honour LLM_VERIFY_SSL=false by patching httpx/requests ssl before import.
    if not verify_ssl:
        import ssl
        import httpx
        os.environ.setdefault("CURL_CA_BUNDLE", "")
        os.environ.setdefault("REQUESTS_CA_BUNDLE", "")
        # Monkey-patch a permissive SSL context for this check only
        _orig_create = ssl.create_default_context
        def _no_verify(*args, **kwargs):
            ctx = _orig_create(*args, **kwargs)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        ssl.create_default_context = _no_verify

    try:
        from agentorchestrator.services.llm_gateway import LLMGatewayClient
        client = LLMGatewayClient(
            server_url=url,
            model_name=model,
            temperature=0.0,
            max_tokens=5,
            timeout=30.0,
            api_key=api_key or None,
            oauth_endpoint=oauth_ep or None,
            client_id=client_id or None,
            client_secret=secret or None,
        )
        t0 = time.monotonic()
        response = await client.generate_async("Say: ok", max_tokens=5)
        ms = (time.monotonic() - t0) * 1000
        _ok("LLM Gateway", f"{ms:.0f} ms  ← {response!r:.60s}")
        return True

    except Exception as exc:
        _fail("LLM Gateway", str(exc))
        if "SSL" in str(exc) or "certificate" in str(exc).lower():
            print(f"       {_YELLOW}Tip: Add  LLM_VERIFY_SSL=false  to your .env to bypass corp SSL certs{_RESET}")
        elif "authentication" in str(exc).lower() or "token" in str(exc).lower():
            print(f"       {_YELLOW}Tip: Check LLM_OAUTH_ENDPOINT, LLM_CLIENT_ID, LLM_CLIENT_SECRET{_RESET}")
        return False


# ── MCP adapter ───────────────────────────────────────────────────────────────

async def check_mcp_adapter(
    label: str,
    endpoint: str,
    secret: str,
    routing: str,
    verify_ssl: bool,
) -> bool:
    if not endpoint:
        _warn(label, "endpoint not set — skipping")
        return True

    print(f"  Endpoint: {endpoint}")
    print(f"  Routing:  {routing}  |  Verify SSL: {verify_ssl}")

    try:
        from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter
        adapter = MCPToolAdapter(name=label.lower().replace(" ", "_"))
        t0 = time.monotonic()
        ok = await adapter.connect(
            endpoint=endpoint,
            secret=secret or None,
            use_path_routing=(routing == "path"),
            verify_ssl=verify_ssl,
        )
        ms = (time.monotonic() - t0) * 1000

        if not ok:
            _fail(label, "connect() returned False")
            _print_mcp_tips(label, endpoint)
            return False

        tools: list[dict[str, Any]] = adapter.tools_list or []
        tool_names = [t.get("name", "?") for t in tools]
        _ok(label, f"{ms:.0f} ms  |  {len(tools)} tool(s): {tool_names}")
        return True

    except Exception as exc:
        err = str(exc)
        _fail(label, err)
        _print_mcp_tips(label, endpoint, err)
        return False


def _print_mcp_tips(label: str, endpoint: str, err: str = "") -> None:
    if "redirect" in err.lower():
        print(f"       {_YELLOW}Tip: 'Too many redirects' usually means the endpoint URL is wrong{_RESET}")
        print(f"       {_YELLOW}     or auth is failing (no bearer token → redirect loop).{_RESET}")
        print(f"       {_YELLOW}     Current endpoint: {endpoint}{_RESET}")
        print(f"       {_YELLOW}     Try adding /mcp/ suffix if not present, e.g.:{_RESET}")
        base = endpoint.rstrip("/")
        if not base.endswith("/mcp"):
            print(f"       {_YELLOW}     {base}/mcp/{_RESET}")
        print(f"       {_YELLOW}     Also check MCP_*_SECRET is set correctly (JWT bearer token){_RESET}")
    elif "ssl" in err.lower() or "certificate" in err.lower():
        print(f"       {_YELLOW}Tip: Set MCP_{label.upper()}_VERIFY_SSL=false in your .env{_RESET}")


async def check_mcp() -> bool:
    _section("3 / 4  RavenPack MCP")
    rp_ok = await check_mcp_adapter(
        label      = "RavenPack",
        endpoint   = os.getenv("MCP_RAVENPACK_ENDPOINT", ""),
        secret     = os.getenv("MCP_RAVENPACK_SECRET", ""),
        routing    = os.getenv("MCP_RAVENPACK_ROUTING", "jsonrpc"),
        verify_ssl = os.getenv("MCP_RAVENPACK_VERIFY_SSL", "true").lower() == "true",
    )

    _section("4 / 4  Capital IQ MCP")
    cq_ok = await check_mcp_adapter(
        label      = "CapIQ",
        endpoint   = os.getenv("MCP_CAPIQ_ENDPOINT", ""),
        secret     = os.getenv("MCP_CAPIQ_SECRET", ""),
        routing    = os.getenv("MCP_CAPIQ_ROUTING", "jsonrpc"),
        verify_ssl = os.getenv("MCP_CAPIQ_VERIFY_SSL", "true").lower() == "true",
    )

    return rp_ok and cq_ok


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    print(f"\n{_BOLD}{'='*60}{_RESET}")
    print(f"{_BOLD}  Deep Research Agent — Connection Check{_RESET}")
    print(f"{_BOLD}{'='*60}{_RESET}")

    results = await asyncio.gather(
        check_redis(),
        check_llm(),
        check_mcp(),
        return_exceptions=True,
    )

    redis_ok = results[0] if not isinstance(results[0], Exception) else False
    llm_ok   = results[1] if not isinstance(results[1], Exception) else False
    mcp_ok   = results[2] if not isinstance(results[2], Exception) else False

    _section("Summary")
    overall = True
    for label, ok in [
        ("Redis",          redis_ok),
        ("LLM Gateway",    llm_ok),
        ("MCP (both)",     mcp_ok),
    ]:
        if ok:
            _ok(label)
        else:
            _fail(label)
            overall = False

    print()
    if overall:
        print(f"  {_GREEN}{_BOLD}All checks passed — safe to start the service.{_RESET}")
        print(f"  Run:  uvicorn deep_research.server:app --host 0.0.0.0 --port 8000")
    else:
        print(f"  {_RED}{_BOLD}One or more checks failed — fix the issues above first.{_RESET}")

    print()
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
