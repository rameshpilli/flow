"""Deep Research Agent — Middleware stack composition.

Builds and registers all middleware onto an AgentOrchestrator instance.
Import and call setup_middleware(ao, llm) once during application startup,
after the LLM client is initialised.

Middleware order (applied in order; run_before fires top→bottom, run_after
fires bottom→top):

  1. LoggerMiddleware        — structured step-level logging
  2. MetricsMiddleware       — latency / success counters (in-memory or OTel)
  3. CacheMiddleware         — short-circuit repeated identical sub-queries
  4. TokenManagerMiddleware  — enforce per-namespace token budgets
  5. RollingSummaryMiddleware — prevent context window overflow on large payloads
  6. ReflectionMiddleware    — applied only on cross_verify + generate_report
  7. CitationMiddleware      — track every source reference end-to-end
"""

from __future__ import annotations

import logging
from typing import Any

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
from agentorchestrator.core.orchestrator import AgentOrchestrator
from deep_research.config import settings

logger = logging.getLogger(__name__)


def setup_middleware(ao: AgentOrchestrator, llm: Any) -> None:
    """Register all middleware with the orchestrator.

    Args:
        ao:  The AgentOrchestrator instance for this service.
        llm: Initialised LLMGatewayClient (needed by reflection middleware).
    """

    # 1. Structured logging — log every step start / end / error
    ao.use(LoggerMiddleware())

    # 2. Metrics — in-memory counters; swap OTelMetricsBackend for production
    ao.use(create_metrics_middleware(backend="in_memory"))

    # 3. Cache — avoid re-running identical search sub-queries within a run
    #    TTL of 300 s keeps repeated refinement loops fast without stale data
    ao.use(CacheMiddleware(ttl=300))

    # 4. Token budget — caps total tokens consumed across all steps so a
    #    single run cannot exhaust the gateway quota
    ao.use(TokenManagerMiddleware())

    # 5. Rolling summary — automatically summarises large context payloads
    #    (e.g. hundreds of raw search results) so the context window stays
    #    within the LLM's limit as the pipeline progresses
    ao.use(RollingSummaryMiddleware())

    # 6. Reflection — self-critique on the two most expensive steps
    #    quality_threshold=0.75 means the step retries if the LLM critic
    #    scores the output below 75/100
    reflection_cfg = ReflectionConfig(
        quality_threshold=0.75,
        max_revisions=2,
        applies_to=["cross_verify", "generate_report"],
    )
    ao.use(ReflectionMiddleware(
        config=reflection_cfg,
        llm_client=llm,
    ))

    # 7. Citation tracking — automatically records every source reference so
    #    the final report can include a full bibliography
    ao.use(CitationMiddleware())

    logger.info("Deep research middleware stack registered (7 layers)")
