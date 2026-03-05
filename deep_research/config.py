"""Deep Research Agent — Configuration.

All settings are read from environment variables. Copy .env.example to .env,
fill in your values, then run the service.  In Kubernetes, mount the values
from a ConfigMap (non-secret) and a Secret (credentials).

Data sources
────────────
  This service connects to two internal MCP servers:
    • RavenPack News MCP  — real-time news, press releases, wire feeds
    • S&P Capital IQ MCP  — M&A deal data, financials, company data

Both follow the AgentOrchestrator MCPToolAdapter protocol (JWT bearer token,
either path-routing or JSON-RPC depending on which CapIQ/RavenPack endpoint
you're targeting).
"""

from __future__ import annotations

import os
from typing import Optional


class Settings:
    """Flat settings object built from environment variables.

    Avoids a hard dependency on pydantic-settings while keeping all
    configuration in one place and easy to override in tests.
    """

    # ── LLM Gateway ──────────────────────────────────────────────────────────
    llm_server_url: str
    llm_model_name: str
    llm_temperature: float
    llm_max_tokens: int
    llm_timeout: float

    # Auth — OAuth takes priority over API key
    llm_oauth_endpoint: Optional[str]
    llm_client_id: Optional[str]
    llm_client_secret: Optional[str]
    llm_api_key: Optional[str]

    # ── MCP Data Sources ──────────────────────────────────────────────────────

    # RavenPack News MCP (path-routing style)
    mcp_ravenpack_endpoint: Optional[str]
    mcp_ravenpack_secret: Optional[str]
    mcp_ravenpack_routing: str       # "path" | "jsonrpc"
    mcp_ravenpack_verify_ssl: bool

    # S&P Capital IQ MCP (JSON-RPC style)
    mcp_capiq_endpoint: Optional[str]
    mcp_capiq_secret: Optional[str]
    mcp_capiq_routing: str           # "path" | "jsonrpc"
    mcp_capiq_verify_ssl: bool

    # ── Large Response Guard ──────────────────────────────────────────────────
    # RavenPack / CapIQ can return very large payloads (thousands of articles
    # or deal records).  This cap is applied to every single MCP tool-call
    # observation *before* it enters the ReAct context window, preventing the
    # LLM from being overwhelmed.  Increase if you need more raw data per call;
    # decrease if you hit context-window limits.
    max_observation_chars: int

    # ── Chain Execution ───────────────────────────────────────────────────────
    chain_max_parallel_steps: int
    chain_default_timeout_ms: int
    chain_default_retries: int
    chain_error_handling: str       # "fail_fast" | "continue"

    # ── Context / State store ─────────────────────────────────────────────────
    context_store_backend: str      # "memory" | "redis"
    redis_host: str
    redis_port: int

    # ── Summarizer ────────────────────────────────────────────────────────────
    summarizer_strategy: str        # "map_reduce" | "stuff" | "refine"
    summarizer_max_tokens: int

    # ── ReAct search agent ────────────────────────────────────────────────────
    react_max_iterations: int
    react_max_tokens: int

    # ── Research pipeline ─────────────────────────────────────────────────────
    # Max sub-queries the planner will emit (keeps parallel fan-out bounded)
    planner_max_sub_queries: int
    # How many search results to keep per source before aggregation
    results_per_source: int
    # Report format hint passed to the LLM in the final step
    report_format: str              # "markdown" | "json"

    # ── MCP Server (expose this service as an MCP tool for Cohere North etc.) ─
    # Set this to a shared secret you configure in Cohere North's MCP connection.
    # Leave empty ("") to disable bearer-token auth (development only).
    mcp_server_secret: str

    # ── Observability ─────────────────────────────────────────────────────────
    enable_tracing: bool
    log_level: str

    # ── Server ────────────────────────────────────────────────────────────────
    host: str
    port: int
    workers: int

    def __init__(self) -> None:
        def _bool(key: str, default: bool = False) -> bool:
            return os.getenv(key, str(default)).lower() in ("1", "true", "yes")

        def _int(key: str, default: int) -> int:
            return int(os.getenv(key, str(default)))

        def _float(key: str, default: float) -> float:
            return float(os.getenv(key, str(default)))

        # LLM
        self.llm_server_url = os.getenv("LLM_SERVER_URL", "http://localhost:8080/v1/chat/completions")
        self.llm_model_name = os.getenv("LLM_MODEL_NAME", "gpt-4")
        self.llm_temperature = _float("LLM_TEMPERATURE", 0.2)
        self.llm_max_tokens = _int("LLM_MAX_TOKENS", 4096)
        self.llm_timeout = _float("LLM_TIMEOUT", 120.0)
        self.llm_oauth_endpoint = os.getenv("LLM_OAUTH_ENDPOINT")
        self.llm_client_id = os.getenv("LLM_CLIENT_ID")
        self.llm_client_secret = os.getenv("LLM_CLIENT_SECRET")
        self.llm_api_key = os.getenv("LLM_API_KEY")

        # MCP — RavenPack News
        self.mcp_ravenpack_endpoint = os.getenv("MCP_RAVENPACK_ENDPOINT")
        self.mcp_ravenpack_secret = os.getenv("MCP_RAVENPACK_SECRET")
        self.mcp_ravenpack_routing = os.getenv("MCP_RAVENPACK_ROUTING", "path")
        self.mcp_ravenpack_verify_ssl = _bool("MCP_RAVENPACK_VERIFY_SSL", False)

        # MCP — S&P Capital IQ
        self.mcp_capiq_endpoint = os.getenv("MCP_CAPIQ_ENDPOINT")
        self.mcp_capiq_secret = os.getenv("MCP_CAPIQ_SECRET")
        self.mcp_capiq_routing = os.getenv("MCP_CAPIQ_ROUTING", "jsonrpc")
        self.mcp_capiq_verify_ssl = _bool("MCP_CAPIQ_VERIFY_SSL", False)

        # Large response guard — cap each MCP observation before it enters ReAct
        # Default 8 000 chars ≈ ~2 000 tokens; tune up/down based on your LLM's
        # context window and the verbosity of your MCP server responses.
        self.max_observation_chars = _int("MAX_OBSERVATION_CHARS", 8000)

        # Chain
        self.chain_max_parallel_steps = _int("CHAIN_MAX_PARALLEL_STEPS", 2)
        self.chain_default_timeout_ms = _int("CHAIN_DEFAULT_TIMEOUT_MS", 60000)
        self.chain_default_retries = _int("CHAIN_DEFAULT_RETRIES", 2)
        self.chain_error_handling = os.getenv("CHAIN_ERROR_HANDLING", "fail_fast")

        # Context store
        self.context_store_backend = os.getenv("CONTEXT_STORE_BACKEND", "memory")
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = _int("REDIS_PORT", 6379)

        # Summarizer
        self.summarizer_strategy = os.getenv("SUMMARIZER_STRATEGY", "map_reduce")
        self.summarizer_max_tokens = _int("SUMMARIZER_MAX_TOKENS", 4000)

        # ReAct
        self.react_max_iterations = _int("REACT_MAX_ITERATIONS", 5)
        self.react_max_tokens = _int("REACT_MAX_TOKENS", 2048)

        # Research pipeline
        self.planner_max_sub_queries = _int("PLANNER_MAX_SUB_QUERIES", 4)
        self.results_per_source = _int("RESULTS_PER_SOURCE", 20)
        self.report_format = os.getenv("REPORT_FORMAT", "markdown")

        # MCP server
        self.mcp_server_secret = os.getenv("MCP_SERVER_SECRET", "")

        # Observability
        self.enable_tracing = _bool("AO_ENABLE_TRACING", False)
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # Server
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = _int("PORT", 8000)
        self.workers = _int("WORKERS", 1)


# Module-level singleton — import this everywhere
settings = Settings()
