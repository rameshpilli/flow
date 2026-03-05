"""Deep Research Agent — DAG wiring and middleware stack.

Two setup functions called once at application startup:

  build_pipeline(ao)        — registers all steps and the chain with the
                              AgentOrchestrator using the Pipeline DSL.

  setup_middleware(ao, llm) — attaches 7 middleware layers to the orchestrator.

DAG shape
─────────
         plan_research
               │
       ┌───────┴───────┐
       ▼               ▼
  search_news    search_capiq
  (RavenPack)    (Capital IQ)
       └───────┬───────┘
               ▼
       aggregate_sources
               ▼
          cross_verify
               ▼
         generate_report

Middleware order (run_before fires top→bottom, run_after fires bottom→top)
──────────────────────────────────────────────────────────────────────────
  1. LoggerMiddleware         — structured step-level logging
  2. MetricsMiddleware        — latency / success counters
  3. CacheMiddleware          — short-circuit repeated sub-queries (TTL 300 s)
  4. TokenManagerMiddleware   — per-namespace token budgets
  5. RollingSummaryMiddleware — prevent context window overflow on large payloads
  6. ReflectionMiddleware     — self-critique on cross_verify + generate_report
  7. CitationMiddleware       — track every source reference end-to-end
  8. OffloadMiddleware        — offload large step outputs to Redis when
                                CONTEXT_STORE_BACKEND=redis (skipped in
                                memory mode so no Redis dependency locally)
"""

from __future__ import annotations

import logging
from typing import Any

from agentorchestrator.core.orchestrator import AgentOrchestrator
from agentorchestrator.dsl.pipeline import Pipeline
from agentorchestrator.core.context import InMemoryContextStore, RedisContextStore
from agentorchestrator.middleware import (
    CacheMiddleware,
    CitationMiddleware,
    LoggerMiddleware,
    MetricsMiddleware,
    ReflectionConfig,
    ReflectionMiddleware,
    RollingSummaryMiddleware,
    TokenManagerMiddleware,
    create_metrics_middleware,
)
from agentorchestrator.middleware.offload import OffloadMiddleware

from deep_research.config import settings
from deep_research.steps import (
    aggregate_sources,
    cross_verify,
    generate_report,
    plan_research,
    search_capiq,
    search_news,
)

logger = logging.getLogger(__name__)

CHAIN_NAME = "deep_research"


# ── DAG wiring ────────────────────────────────────────────────────────────────

def build_pipeline(ao: AgentOrchestrator) -> Pipeline:
    """Register all steps and the chain with the orchestrator.

    Returns the Pipeline instance (useful for inspection / testing).
    """
    pipe = (
        Pipeline(CHAIN_NAME)
        # ── Step 1: plan ──────────────────────────────────────────────────────
        .step(
            "plan_research",
            fn=plan_research,
            description="Decompose the user query into structured sub-queries and filters.",
            timeout_ms=30_000,
        )
        # ── Steps 2a-2b: parallel search (both depend only on plan_research) ───
        .step(
            "search_news",
            fn=search_news,
            deps=["plan_research"],
            description="Search RavenPack News MCP for relevant findings.",
            timeout_ms=60_000,
        )
        .step(
            "search_capiq",
            fn=search_capiq,
            deps=["plan_research"],
            description="Search S&P Capital IQ MCP for deal data.",
            timeout_ms=60_000,
        )
        # ── Step 3: aggregate ─────────────────────────────────────────────────
        .step(
            "aggregate_sources",
            fn=aggregate_sources,
            deps=["search_news", "search_capiq"],
            description="Merge, deduplicate, and rank findings from both sources.",
            timeout_ms=30_000,
        )
        # ── Step 4: verify ────────────────────────────────────────────────────
        .step(
            "cross_verify",
            fn=cross_verify,
            deps=["aggregate_sources"],
            description="LLM-based cross-verification and conflict detection.",
            timeout_ms=60_000,
        )
        # ── Step 5: report ────────────────────────────────────────────────────
        .step(
            "generate_report",
            fn=generate_report,
            deps=["cross_verify"],
            description="Synthesise a comprehensive final research report.",
            timeout_ms=120_000,
        )
    )

    pipe.register(ao)
    logger.info("Deep research pipeline registered (%s)", CHAIN_NAME)
    return pipe


# ── Middleware stack ───────────────────────────────────────────────────────────

def setup_middleware(ao: AgentOrchestrator, llm: Any) -> None:
    """Register all middleware with the orchestrator.

    Args:
        ao:  The AgentOrchestrator instance for this service.
        llm: Initialised LLMGatewayClient (needed by reflection middleware).
    """
    # 1. Structured logging — log every step start / end / error
    ao.use(LoggerMiddleware())

    # 2. Metrics — in-memory counters; pass otel_meter=<meter> for production
    ao.use(create_metrics_middleware())

    # 3. Cache — avoid re-running identical search sub-queries within a run
    ao.use(CacheMiddleware(ttl_seconds=300))

    # 4. Token budget — caps total tokens consumed across all steps
    ao.use(TokenManagerMiddleware())

    # 5. Rolling summary — summarises large context payloads to stay within
    #    the LLM's context window as the pipeline progresses
    ao.use(RollingSummaryMiddleware())

    # 6. Reflection — self-critique on the two most expensive steps;
    #    retries if LLM critic scores output below 75/100
    reflection_cfg = ReflectionConfig(
        quality_threshold=0.75,
        max_revisions=2,
        applies_to=["cross_verify", "generate_report"],
    )
    ao.use(ReflectionMiddleware(
        config=reflection_cfg,
        llm_client=llm,
    ))

    # 7. Citation tracking — records every source reference for the bibliography
    ao.use(CitationMiddleware())

    # 8. Offload — serialize large step outputs to Redis so in-process context
    #    does not balloon.  Only enabled when CONTEXT_STORE_BACKEND=redis so the
    #    service can run in pure in-memory mode without any Redis dependency.
    if settings.context_store_backend == "redis":
        # Note: RedisContextStore does not yet accept `username` (Redis ACL).
        # For corporate Redis with ACL, extend RedisContextStore.__init__ to
        # accept `username` and pass it to redis.asyncio.ConnectionPool.
        store = RedisContextStore(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            ssl=settings.redis_ssl,
        )
        ao.use(OffloadMiddleware(store=store, default_threshold_bytes=50_000))
        logger.info(
            "OffloadMiddleware enabled → Redis at %s:%s",
            settings.redis_host,
            settings.redis_port,
        )
    else:
        ao.use(OffloadMiddleware(store=InMemoryContextStore(), default_threshold_bytes=50_000))
        logger.info("OffloadMiddleware enabled → in-memory store")

    logger.info("Deep research middleware stack registered (8 layers)")
