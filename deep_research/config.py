"""Deep Research Agent — Configuration.

All settings are read from environment variables. Copy .env.example to .env,
fill in your values, then run the service.  In Kubernetes, mount the values
from a ConfigMap (non-secret) and a Secret (credentials).
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
    # News  (e.g. RavenPack)
    mcp_news_endpoint: Optional[str]
    mcp_news_secret: Optional[str]
    mcp_news_routing: str           # "path" | "jsonrpc"
    mcp_news_verify_ssl: bool

    # SEC / EDGAR filings
    mcp_sec_endpoint: Optional[str]
    mcp_sec_secret: Optional[str]
    mcp_sec_routing: str
    mcp_sec_verify_ssl: bool

    # Financial data  (e.g. S&P Capital IQ / Factset)
    mcp_financial_endpoint: Optional[str]
    mcp_financial_secret: Optional[str]
    mcp_financial_routing: str
    mcp_financial_verify_ssl: bool

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

        # MCP — News
        self.mcp_news_endpoint = os.getenv("MCP_NEWS_ENDPOINT")
        self.mcp_news_secret = os.getenv("MCP_NEWS_SECRET")
        self.mcp_news_routing = os.getenv("MCP_NEWS_ROUTING", "path")
        self.mcp_news_verify_ssl = _bool("MCP_NEWS_VERIFY_SSL", False)

        # MCP — SEC
        self.mcp_sec_endpoint = os.getenv("MCP_SEC_ENDPOINT")
        self.mcp_sec_secret = os.getenv("MCP_SEC_SECRET")
        self.mcp_sec_routing = os.getenv("MCP_SEC_ROUTING", "path")
        self.mcp_sec_verify_ssl = _bool("MCP_SEC_VERIFY_SSL", False)

        # MCP — Financial
        self.mcp_financial_endpoint = os.getenv("MCP_FINANCIAL_ENDPOINT")
        self.mcp_financial_secret = os.getenv("MCP_FINANCIAL_SECRET")
        self.mcp_financial_routing = os.getenv("MCP_FINANCIAL_ROUTING", "path")
        self.mcp_financial_verify_ssl = _bool("MCP_FINANCIAL_VERIFY_SSL", False)

        # Chain
        self.chain_max_parallel_steps = _int("CHAIN_MAX_PARALLEL_STEPS", 4)
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
