"""
Deep Research Agent Example
===========================

This example demonstrates a multi-stage research agent that:
1. Decomposes a research question into sub-questions
2. Searches multiple sources in parallel for each sub-question
3. Synthesizes findings into a comprehensive report
4. Uses reflection to improve report quality

**Large Response Handling**:
This agent uses the following patterns to handle large data:

1. **TokenBudget**: Explicit token reservation prevents context overflow
2. **SummarizerMiddleware**: Compresses large research findings using TREE strategy
3. **RollingSummaryMiddleware**: Incrementally summarizes as data accumulates
4. **get_middleware_metrics()**: Monitor token usage and compression stats

This pattern is commonly used for:
- Market research and competitive analysis
- Technical due diligence
- Literature reviews
- Investment research

Usage:
    python deep_research_agent.py "What are the key trends in AI infrastructure?"

Architecture:
    ┌─────────────────┐
    │ Question Input  │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │   Decompose     │  Break into sub-questions
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  Parallel       │  Search each sub-question
    │  Research       │  across multiple sources
    │  ┌───┬───┬───┐  │  (SummarizerMiddleware compresses)
    │  │Q1 │Q2 │Q3 │  │
    │  └───┴───┴───┘  │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │   Synthesize    │  Combine findings
    └────────┬────────┘  (RollingSummaryMiddleware)
             │
    ┌────────▼────────┐
    │   Reflect &     │  Quality check & improve
    │   Improve       │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  Final Report   │
    └─────────────────┘
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.context import ChainContext, ContextScope
from agentorchestrator.middleware import (
    ReflectionMiddleware,
    ReflectionConfig,
    TokenManagerMiddleware,
    TokenBudget,
    SummarizerMiddleware,
    SummarizationStrategy,
    RollingSummaryMiddleware,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create orchestrator
ao = AgentOrchestrator(name="deep_research")

# ═══════════════════════════════════════════════════════════════════════════════
#                         MIDDLEWARE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# 1. Token Budget with explicit reservations (prevents context overflow)
budget = TokenBudget(
    context_window=128000,      # GPT-4-turbo / Claude context window
    reserved_output=8000,       # Reserve for model response
    reserved_system=3000,       # Reserve for system prompt
    reserved_history=10000,     # Reserve for conversation history
    warning_threshold=0.8,      # Warn at 80% usage
    critical_threshold=0.95,    # Force compression at 95%
)

# 2. Token Manager - tracks usage and auto-triggers compression
ao.use(TokenManagerMiddleware(
    priority=10,
    budget=budget,
    auto_summarize=True,
    target_ratio_after_compression=0.7,
))

# 3. Summarizer for parallel research step (handles large multi-source data)
# Uses TREE strategy for efficient hierarchical summarization
ao.use(SummarizerMiddleware(
    priority=20,
    max_tokens=5000,
    strategy=SummarizationStrategy.TREE,  # Best for 50K+ token results
    applies_to=["parallel_research"],  # Only on research step
))

# 4. Rolling summary for synthesize step (accumulates findings incrementally)
ao.use(RollingSummaryMiddleware(
    priority=25,
    max_tokens=4000,
    recent_buffer_tokens=1000,  # Keep last 1K tokens uncompressed
    applies_to=["synthesize_report"],
))

# 5. Reflection middleware for quality improvement
ao.use(ReflectionMiddleware(
    priority=30,
    config=ReflectionConfig(
        quality_threshold=0.8,
        max_revisions=2,
        applies_to=["synthesize_report"],  # Only reflect on final report
    ),
))


@dataclass
class ResearchConfig:
    """Configuration for the research agent."""
    max_sub_questions: int = 5
    sources: list[str] = None
    search_depth: int = 3
    
    def __post_init__(self):
        if self.sources is None:
            self.sources = ["web", "academic", "news"]


# ═══════════════════════════════════════════════════════════════════════════════
#                              STEP DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════


@ao.step(name="decompose_question", produces=["sub_questions"])
async def decompose_question(ctx: ChainContext) -> dict[str, Any]:
    """
    Break down the main research question into focused sub-questions.
    
    Uses LLM to analyze the question and identify key aspects that
    need separate investigation.
    """
    question = ctx.get("question")
    config: ResearchConfig = ctx.get("config", ResearchConfig())
    
    logger.info(f"Decomposing question: {question}")
    
    # In production, this would call an LLM
    # For demo, we'll simulate the decomposition
    sub_questions = _simulate_decomposition(question, config.max_sub_questions)
    
    ctx.set("sub_questions", sub_questions, scope=ContextScope.CHAIN)
    
    return {
        "sub_questions": sub_questions,
        "count": len(sub_questions),
    }


@ao.step(name="parallel_research", deps=["decompose_question"], produces=["research_findings"])
async def parallel_research(ctx: ChainContext) -> dict[str, Any]:
    """
    Research each sub-question in parallel across multiple sources.
    
    This step demonstrates dynamic step injection - it creates
    parallel research tasks based on the decomposed questions.
    """
    sub_questions = ctx.get("sub_questions")
    config: ResearchConfig = ctx.get("config", ResearchConfig())
    
    logger.info(f"Researching {len(sub_questions)} sub-questions across {len(config.sources)} sources")
    
    # Research each sub-question in parallel
    findings = {}
    tasks = []
    
    for i, sq in enumerate(sub_questions):
        for source in config.sources:
            tasks.append(_research_source(sq, source, config.search_depth))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Organize findings by sub-question
    idx = 0
    for i, sq in enumerate(sub_questions):
        findings[sq] = {}
        for source in config.sources:
            result = results[idx]
            if isinstance(result, Exception):
                logger.warning(f"Research failed for {sq[:30]}... from {source}: {result}")
                findings[sq][source] = {"error": str(result)}
            else:
                findings[sq][source] = result
            idx += 1
    
    ctx.set("research_findings", findings, scope=ContextScope.CHAIN)
    
    return {
        "findings": findings,
        "sources_searched": len(config.sources) * len(sub_questions),
    }


@ao.step(name="synthesize_report", deps=["parallel_research"], produces=["report"])
async def synthesize_report(ctx: ChainContext) -> dict[str, Any]:
    """
    Synthesize research findings into a comprehensive report.
    
    This step is configured for reflection - the middleware will
    automatically critique and improve the report.
    """
    question = ctx.get("question")
    sub_questions = ctx.get("sub_questions")
    findings = ctx.get("research_findings")
    
    logger.info("Synthesizing research report")
    
    # In production, this would use an LLM to synthesize
    report = _simulate_synthesis(question, sub_questions, findings)
    
    ctx.set("report", report, scope=ContextScope.CHAIN)
    
    return {
        "report": report,
        "sections": len(report.get("sections", [])),
    }


@ao.step(name="format_output", deps=["synthesize_report"])
async def format_output(ctx: ChainContext) -> dict[str, Any]:
    """
    Format the final report for output.
    """
    report = ctx.get("report")
    
    formatted = _format_report(report)
    
    return {
        "formatted_report": formatted,
        "word_count": len(formatted.split()),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#                              CHAIN DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════


@ao.chain(name="deep_research")
class DeepResearchChain:
    """
    Multi-stage research pipeline with parallel source searching.
    """
    steps = [
        "decompose_question",
        "parallel_research",
        "synthesize_report",
        "format_output",
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#                              HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def _simulate_decomposition(question: str, max_questions: int) -> list[str]:
    """Simulate question decomposition (replace with LLM call in production)."""
    # Simple simulation based on question
    base_aspects = [
        f"What are the current developments in {question}?",
        f"Who are the key players involved in {question}?",
        f"What are the challenges and limitations of {question}?",
        f"What are the future predictions for {question}?",
        f"What are the practical applications of {question}?",
    ]
    return base_aspects[:max_questions]


async def _research_source(question: str, source: str, depth: int) -> dict[str, Any]:
    """Simulate source research (replace with actual search in production)."""
    # Simulate network latency
    await asyncio.sleep(0.1)
    
    return {
        "source": source,
        "query": question,
        "results": [
            {"title": f"Result 1 from {source}", "snippet": f"Relevant info about {question[:30]}..."},
            {"title": f"Result 2 from {source}", "snippet": f"More details on {question[:30]}..."},
        ],
        "relevance_score": 0.85,
    }


def _simulate_synthesis(
    question: str,
    sub_questions: list[str],
    findings: dict,
) -> dict[str, Any]:
    """Simulate report synthesis (replace with LLM call in production)."""
    sections = []
    
    for sq in sub_questions:
        sq_findings = findings.get(sq, {})
        section = {
            "title": sq,
            "summary": f"Based on {len(sq_findings)} sources, the key findings are...",
            "sources": list(sq_findings.keys()),
        }
        sections.append(section)
    
    return {
        "title": f"Research Report: {question}",
        "executive_summary": f"This report analyzes {len(sub_questions)} aspects of {question}.",
        "sections": sections,
        "methodology": "Multi-source parallel research with LLM synthesis",
        "confidence_score": 0.82,
    }


def _format_report(report: dict) -> str:
    """Format report as readable text."""
    lines = [
        f"# {report['title']}",
        "",
        "## Executive Summary",
        report['executive_summary'],
        "",
    ]
    
    for section in report.get('sections', []):
        lines.extend([
            f"## {section['title']}",
            section['summary'],
            f"Sources: {', '.join(section['sources'])}",
            "",
        ])
    
    lines.extend([
        "## Methodology",
        report['methodology'],
        "",
        f"Confidence Score: {report['confidence_score']:.0%}",
    ])
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#                                    MAIN
# ═══════════════════════════════════════════════════════════════════════════════


async def main():
    """Run the deep research agent."""
    import sys

    # Get question from command line or use default
    question = (
        " ".join(sys.argv[1:]) if len(sys.argv) > 1
        else "What are the key trends in AI infrastructure for 2025?"
    )

    print(f"\n{'='*60}")
    print(f"Deep Research Agent")
    print(f"{'='*60}")
    print(f"Question: {question}\n")

    # Show middleware configuration
    print("Middleware Stack:")
    for mw in ao.list_middleware():
        print(f"  - {mw['type']} (priority={mw['priority']}, has_metrics={mw['has_metrics']})")
    print()

    # Configure research
    config = ResearchConfig(
        max_sub_questions=4,
        sources=["web", "academic", "news"],
        search_depth=3,
    )

    # Run the research pipeline
    result = await ao.launch(
        "deep_research",
        data={
            "question": question,
            "config": config,
        },
    )

    if result["success"]:
        print("\n" + result["context"]["data"].get("formatted_report", "No report generated"))

        # Show reflection trace if available
        reflection_trace = result["context"]["data"].get("_reflection_trace", {})
        if reflection_trace:
            print(f"\n{'='*60}")
            print("Reflection Results")
            print(f"{'='*60}")
            for step, trace in reflection_trace.items():
                print(f"Step: {step}")
                print(f"  Quality Score: {trace['quality_score']:.2%}")
                print(f"  Revisions: {trace['revision_count']}")
                print(f"  Passed Threshold: {trace['passed_threshold']}")

        # Show middleware metrics (NEW: monitoring token usage and compression)
        print(f"\n{'='*60}")
        print("Middleware Metrics")
        print(f"{'='*60}")
        metrics = ao.get_middleware_metrics()
        for mw_name, mw_metrics in metrics.items():
            print(f"\n{mw_name}:")
            if isinstance(mw_metrics, dict):
                for key, value in mw_metrics.items():
                    if isinstance(value, float):
                        print(f"  {key}: {value:.2f}")
                    else:
                        print(f"  {key}: {value}")
            else:
                print(f"  {mw_metrics}")
    else:
        print(f"Research failed: {result.get('error', 'Unknown error')}")

    print(f"\nTotal duration: {result['duration_ms']:.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
