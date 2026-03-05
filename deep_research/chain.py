"""Deep Research Agent — Pipeline / Chain definition.

Wires the five research steps into a DAG using the Pipeline DSL from
agentorchestrator.dsl.pipeline.  The four search steps run in parallel
(they all depend only on plan_research), then converge at aggregate_sources.

    plan_research
         │
    ┌────┴────────────────────┐
    ▼    ▼         ▼          ▼
 search_news  search_sec  search_financial  search_web
    └────┬────────────────────┘
         ▼
  aggregate_sources
         ▼
    cross_verify
         ▼
   generate_report

Call build_pipeline(ao) once at application startup to register all steps and
the chain with the provided AgentOrchestrator instance.
"""

from __future__ import annotations

import logging

from agentorchestrator.core.orchestrator import AgentOrchestrator
from agentorchestrator.dsl.pipeline import Pipeline

from deep_research.steps import (
    aggregate_sources,
    cross_verify,
    generate_report,
    plan_research,
    search_financial,
    search_news,
    search_sec,
    search_web,
)

logger = logging.getLogger(__name__)

CHAIN_NAME = "deep_research"


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
        # ── Steps 2a-2d: parallel search (all depend only on plan_research) ───
        .step(
            "search_news",
            fn=search_news,
            deps=["plan_research"],
            description="Search news sources (MCP/stub) for relevant findings.",
            timeout_ms=60_000,
        )
        .step(
            "search_sec",
            fn=search_sec,
            deps=["plan_research"],
            description="Search SEC/EDGAR filings (MCP/stub).",
            timeout_ms=60_000,
        )
        .step(
            "search_financial",
            fn=search_financial,
            deps=["plan_research"],
            description="Search financial databases for deal data (MCP/stub).",
            timeout_ms=60_000,
        )
        .step(
            "search_web",
            fn=search_web,
            deps=["plan_research"],
            description="Supplementary web search using LLM knowledge.",
            timeout_ms=60_000,
        )
        # ── Step 3: aggregate ─────────────────────────────────────────────────
        .step(
            "aggregate_sources",
            fn=aggregate_sources,
            deps=["search_news", "search_sec", "search_financial", "search_web"],
            description="Merge, deduplicate, and rank findings from all sources.",
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
