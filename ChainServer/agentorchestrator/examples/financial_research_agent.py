"""
Financial Deep Research Agent Example

This example demonstrates how to build a multi-stage research agent that:
1. Connects to Refinitiv MCP server for news and market data
2. Decomposes complex research questions into sub-queries
3. Gathers data from multiple sources (news, SEC filings, earnings)
4. Synthesizes findings into a comprehensive analysis report
5. Uses mem0 for persistent memory across sessions

Requirements:
    - Refinitiv MCP server running (NEWS_MCP_URL environment variable)
    - SEC MCP server running (SEC_MCP_URL environment variable)
    - Corporate LLM Gateway access
    - Optional: mem0 memory store for cross-session memory

Usage:
    python -m agentorchestrator.examples.financial_research_agent

    # Or programmatically:
    from agentorchestrator.examples.financial_research_agent import (
        create_financial_research_agent,
        run_research,
    )

    agent = create_financial_research_agent()
    report = await run_research(agent, "Analyze Tesla's competitive position in EVs")
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator

from pydantic import BaseModel

# Core framework imports
from agentorchestrator import AgentOrchestrator
from agentorchestrator.core import ChainContext
from agentorchestrator.plugins.mcp_adapter import MCPAdapterAgent, MCPAdapterConfig
from agentorchestrator.services.llm_gateway import LLMGatewayClient
from agentorchestrator.squad.storage import Mem0Memory, InMemoryChatStorage

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ResearchConfig:
    """Configuration for the financial research agent."""

    # MCP Server URLs (from environment)
    refinitiv_mcp_url: str = field(
        default_factory=lambda: os.getenv("REFINITIV_MCP_URL", "http://localhost:3001")
    )
    sec_mcp_url: str = field(
        default_factory=lambda: os.getenv("SEC_MCP_URL", "http://localhost:3002")
    )
    earnings_mcp_url: str = field(
        default_factory=lambda: os.getenv("EARNINGS_MCP_URL", "http://localhost:3003")
    )

    # LLM Gateway
    llm_server_url: str = field(
        default_factory=lambda: os.getenv("LLM_SERVER_URL", "")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL_NAME", "claude-sonnet-4")
    )

    # Memory store (optional)
    mem0_url: str = field(
        default_factory=lambda: os.getenv("MEM0_URL", "https://mem0.cfk.devfg.rbc.com")
    )

    # Research settings
    max_iterations: int = 5
    max_sources_per_query: int = 10
    report_format: str = "markdown"


# =============================================================================
# Data Models
# =============================================================================

class ResearchQuery(BaseModel):
    """Input for research agent."""
    topic: str
    focus_areas: list[str] | None = None
    time_range: str = "last_30_days"
    depth: str = "comprehensive"  # quick, detailed, comprehensive


class ResearchSource(BaseModel):
    """A source used in research."""
    url: str
    title: str
    source_type: str  # news, sec_filing, earnings_call, analyst_report
    relevance_score: float
    excerpt: str
    timestamp: datetime | None = None


class ResearchFinding(BaseModel):
    """A key finding from research."""
    finding: str
    confidence: float
    sources: list[str]
    category: str  # financial, strategic, risk, opportunity


class ResearchReport(BaseModel):
    """Output from research agent."""
    topic: str
    executive_summary: str
    key_findings: list[ResearchFinding]
    sources: list[ResearchSource]
    questions_explored: list[str]
    methodology: str
    generated_at: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# MCP Agents (Connect to Refinitiv, SEC, Earnings servers)
# =============================================================================

class RefinitivNewsAgent(MCPAdapterAgent):
    """
    Agent that connects to Refinitiv MCP server for news and market data.

    Provides access to:
    - Real-time news articles
    - Company news sentiment
    - Market data and analysis
    - Analyst reports
    """

    def __init__(self, config: ResearchConfig):
        super().__init__(
            config=MCPAdapterConfig(
                name="refinitiv_news",
                server_url=config.refinitiv_mcp_url,
                transport="http",
                timeout_seconds=30.0,
                headers={"Authorization": f"Bearer {os.getenv('REFINITIV_API_KEY', '')}"},
            )
        )
        self.tool_name = "news_search"

    async def search_news(
        self,
        query: str,
        companies: list[str] | None = None,
        date_range: str = "last_30_days",
        limit: int = 10,
    ) -> list[dict]:
        """Search Refinitiv news for relevant articles."""
        result = await self.invoke_tool(
            self.tool_name,
            {
                "query": query,
                "companies": companies or [],
                "date_range": date_range,
                "limit": limit,
            },
        )
        return result.get("articles", [])

    async def get_company_sentiment(self, ticker: str) -> dict:
        """Get news sentiment analysis for a company."""
        result = await self.invoke_tool(
            "company_sentiment",
            {"ticker": ticker},
        )
        return result


class SECFilingsAgent(MCPAdapterAgent):
    """Agent for SEC EDGAR filings (10-K, 10-Q, 8-K, etc.)."""

    def __init__(self, config: ResearchConfig):
        super().__init__(
            config=MCPAdapterConfig(
                name="sec_filings",
                server_url=config.sec_mcp_url,
                transport="http",
                timeout_seconds=60.0,  # SEC filings can be large
            )
        )

    async def get_filings(
        self,
        ticker: str,
        filing_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Get SEC filings for a company."""
        result = await self.invoke_tool(
            "sec_filing_retrieval_tool",
            {
                "ticker": ticker,
                "filing_types": filing_types or ["10-K", "10-Q", "8-K"],
                "limit": limit,
            },
        )
        return result.get("filings", [])


class EarningsAgent(MCPAdapterAgent):
    """Agent for earnings call transcripts and analysis."""

    def __init__(self, config: ResearchConfig):
        super().__init__(
            config=MCPAdapterConfig(
                name="earnings",
                server_url=config.earnings_mcp_url,
                transport="http",
                timeout_seconds=45.0,
            )
        )

    async def get_earnings_calls(
        self,
        ticker: str,
        quarters: int = 4,
    ) -> list[dict]:
        """Get recent earnings call transcripts."""
        result = await self.invoke_tool(
            "_earnings_call_analyzer_with_docs",
            {
                "ticker": ticker,
                "num_quarters": quarters,
            },
        )
        return result.get("calls", [])


# =============================================================================
# Research Pipeline Steps
# =============================================================================

def create_research_orchestrator(config: ResearchConfig) -> AgentOrchestrator:
    """Create the research pipeline orchestrator."""

    ao = AgentOrchestrator(name="financial_research")

    # Initialize agents
    news_agent = RefinitivNewsAgent(config)
    sec_agent = SECFilingsAgent(config)
    earnings_agent = EarningsAgent(config)

    # Initialize LLM client
    llm = LLMGatewayClient(
        server_url=config.llm_server_url,
        model_name=config.llm_model,
    )

    # =========================================================================
    # Step 1: Question Decomposition
    # =========================================================================
    @ao.step(name="decompose_question")
    async def decompose_question(ctx: ChainContext) -> dict:
        """
        Decompose the research topic into focused sub-questions.

        This step uses LLM to break down a complex research question
        into specific, answerable sub-queries.
        """
        query: ResearchQuery = ctx.get("query")

        prompt = f"""You are a financial research analyst. Decompose this research topic
into 3-5 specific, focused questions that will guide comprehensive research.

Topic: {query.topic}
Focus areas: {', '.join(query.focus_areas or ['general analysis'])}
Depth: {query.depth}

For each question, identify:
1. The specific question to answer
2. The best data sources (news, SEC filings, earnings calls)
3. Key entities to search for (companies, people, products)

Return as JSON:
{{
    "questions": [
        {{
            "question": "...",
            "sources": ["news", "sec", "earnings"],
            "entities": ["TSLA", "Elon Musk", ...]
        }}
    ]
}}
"""
        response = await llm.generate_async(prompt)

        # Parse questions from LLM response
        import json
        try:
            parsed = json.loads(response)
            questions = parsed.get("questions", [])
        except json.JSONDecodeError:
            # Fallback: create basic questions
            questions = [
                {
                    "question": query.topic,
                    "sources": ["news", "sec", "earnings"],
                    "entities": [],
                }
            ]

        ctx.set("research_questions", questions)
        logger.info(f"Decomposed into {len(questions)} research questions")

        return {"questions": questions}

    # =========================================================================
    # Step 2: Gather Data from Sources
    # =========================================================================
    @ao.step(name="gather_news", deps=["decompose_question"])
    async def gather_news(ctx: ChainContext) -> dict:
        """Gather news from Refinitiv for each research question."""
        questions = ctx.get("research_questions")
        all_articles = []

        for q in questions:
            if "news" in q.get("sources", []):
                articles = await news_agent.search_news(
                    query=q["question"],
                    companies=q.get("entities", []),
                    limit=config.max_sources_per_query,
                )
                all_articles.extend(articles)

        ctx.set("news_articles", all_articles)
        logger.info(f"Gathered {len(all_articles)} news articles")
        return {"article_count": len(all_articles)}

    @ao.step(name="gather_sec", deps=["decompose_question"])
    async def gather_sec(ctx: ChainContext) -> dict:
        """Gather SEC filings for relevant companies."""
        questions = ctx.get("research_questions")
        all_filings = []

        # Extract unique tickers
        tickers = set()
        for q in questions:
            for entity in q.get("entities", []):
                if entity.isupper() and len(entity) <= 5:  # Likely a ticker
                    tickers.add(entity)

        for ticker in tickers:
            filings = await sec_agent.get_filings(ticker=ticker)
            all_filings.extend(filings)

        ctx.set("sec_filings", all_filings)
        logger.info(f"Gathered {len(all_filings)} SEC filings")
        return {"filing_count": len(all_filings)}

    @ao.step(name="gather_earnings", deps=["decompose_question"])
    async def gather_earnings(ctx: ChainContext) -> dict:
        """Gather earnings call transcripts."""
        questions = ctx.get("research_questions")
        all_calls = []

        # Extract unique tickers
        tickers = set()
        for q in questions:
            for entity in q.get("entities", []):
                if entity.isupper() and len(entity) <= 5:
                    tickers.add(entity)

        for ticker in tickers:
            calls = await earnings_agent.get_earnings_calls(ticker=ticker)
            all_calls.extend(calls)

        ctx.set("earnings_calls", all_calls)
        logger.info(f"Gathered {len(all_calls)} earnings calls")
        return {"call_count": len(all_calls)}

    # =========================================================================
    # Step 3: Analyze and Synthesize
    # =========================================================================
    @ao.step(name="analyze_findings", deps=["gather_news", "gather_sec", "gather_earnings"])
    async def analyze_findings(ctx: ChainContext) -> dict:
        """Analyze gathered data and extract key findings."""
        query: ResearchQuery = ctx.get("query")
        questions = ctx.get("research_questions")
        news = ctx.get("news_articles", [])
        filings = ctx.get("sec_filings", [])
        calls = ctx.get("earnings_calls", [])

        # Prepare context for LLM analysis
        context_parts = []

        if news:
            news_summary = "\n".join([
                f"- {a.get('title', 'Untitled')}: {a.get('excerpt', '')[:200]}..."
                for a in news[:10]
            ])
            context_parts.append(f"NEWS ARTICLES:\n{news_summary}")

        if filings:
            filing_summary = "\n".join([
                f"- {f.get('type', 'Filing')} ({f.get('date', 'N/A')}): {f.get('summary', '')[:200]}..."
                for f in filings[:5]
            ])
            context_parts.append(f"SEC FILINGS:\n{filing_summary}")

        if calls:
            calls_summary = "\n".join([
                f"- Q{c.get('quarter', '?')} {c.get('year', '?')}: {c.get('summary', '')[:200]}..."
                for c in calls[:4]
            ])
            context_parts.append(f"EARNINGS CALLS:\n{calls_summary}")

        context = "\n\n".join(context_parts)

        prompt = f"""You are a senior financial analyst. Analyze the following research data
and extract key findings.

RESEARCH TOPIC: {query.topic}
FOCUS AREAS: {', '.join(query.focus_areas or ['general'])}

RESEARCH QUESTIONS:
{chr(10).join([f"- {q['question']}" for q in questions])}

DATA GATHERED:
{context}

Extract 5-8 key findings. For each finding:
1. State the finding clearly
2. Rate confidence (0.0-1.0)
3. List supporting sources
4. Categorize as: financial, strategic, risk, or opportunity

Return as JSON:
{{
    "findings": [
        {{
            "finding": "...",
            "confidence": 0.85,
            "sources": ["source1", "source2"],
            "category": "strategic"
        }}
    ]
}}
"""
        response = await llm.generate_async(prompt)

        import json
        try:
            parsed = json.loads(response)
            findings = parsed.get("findings", [])
        except json.JSONDecodeError:
            findings = []

        ctx.set("findings", findings)
        return {"finding_count": len(findings)}

    # =========================================================================
    # Step 4: Generate Report
    # =========================================================================
    @ao.step(name="generate_report", deps=["analyze_findings"])
    async def generate_report(ctx: ChainContext) -> dict:
        """Generate the final research report."""
        query: ResearchQuery = ctx.get("query")
        questions = ctx.get("research_questions")
        findings = ctx.get("findings", [])
        news = ctx.get("news_articles", [])
        filings = ctx.get("sec_filings", [])
        calls = ctx.get("earnings_calls", [])

        # Compile sources
        sources = []
        for article in news:
            sources.append(ResearchSource(
                url=article.get("url", ""),
                title=article.get("title", ""),
                source_type="news",
                relevance_score=article.get("relevance", 0.5),
                excerpt=article.get("excerpt", "")[:300],
            ))

        for filing in filings:
            sources.append(ResearchSource(
                url=filing.get("url", ""),
                title=f"{filing.get('type', 'Filing')} - {filing.get('company', '')}",
                source_type="sec_filing",
                relevance_score=0.9,
                excerpt=filing.get("summary", "")[:300],
            ))

        # Generate executive summary
        findings_text = "\n".join([f"- {f['finding']}" for f in findings])
        prompt = f"""Write a concise executive summary (2-3 paragraphs) for this research:

Topic: {query.topic}

Key Findings:
{findings_text}

The summary should:
1. State the main conclusion
2. Highlight the most important findings
3. Note any significant risks or opportunities
"""
        executive_summary = await llm.generate_async(prompt)

        report = ResearchReport(
            topic=query.topic,
            executive_summary=executive_summary,
            key_findings=[
                ResearchFinding(
                    finding=f["finding"],
                    confidence=f["confidence"],
                    sources=f["sources"],
                    category=f["category"],
                )
                for f in findings
            ],
            sources=sources[:20],  # Top 20 sources
            questions_explored=[q["question"] for q in questions],
            methodology=f"Multi-source analysis using {len(news)} news articles, "
                        f"{len(filings)} SEC filings, and {len(calls)} earnings calls.",
        )

        ctx.set("report", report)
        return {"report": report.model_dump()}

    # =========================================================================
    # Define the Research Chain
    # =========================================================================
    @ao.chain(name="financial_research")
    class FinancialResearchChain:
        steps = [
            "decompose_question",
            "gather_news",
            "gather_sec",
            "gather_earnings",
            "analyze_findings",
            "generate_report",
        ]

    return ao


# =============================================================================
# High-Level API
# =============================================================================

class FinancialResearchAgent:
    """
    High-level API for financial deep research.

    Example:
        agent = FinancialResearchAgent()

        # Run research
        report = await agent.research(
            topic="Analyze Tesla's competitive position in the EV market",
            focus_areas=["market share", "technology", "financials"],
        )

        print(report.executive_summary)
        for finding in report.key_findings:
            print(f"- {finding.finding} ({finding.confidence:.0%} confidence)")

        # Stream research progress
        async for event in agent.research_stream("Impact of AI on financial services"):
            print(f"[{event['step']}] {event['message']}")
    """

    def __init__(self, config: ResearchConfig | None = None):
        self.config = config or ResearchConfig()
        self.orchestrator = create_research_orchestrator(self.config)
        self._memory = None

    def with_memory(self, memory: Mem0Memory) -> "FinancialResearchAgent":
        """Add persistent memory for cross-session context."""
        self._memory = memory
        return self

    async def research(
        self,
        topic: str,
        focus_areas: list[str] | None = None,
        time_range: str = "last_30_days",
        depth: str = "comprehensive",
    ) -> ResearchReport:
        """
        Run financial deep research on a topic.

        Args:
            topic: Research topic or question
            focus_areas: Specific areas to focus on
            time_range: Time range for data (last_7_days, last_30_days, last_90_days)
            depth: Research depth (quick, detailed, comprehensive)

        Returns:
            ResearchReport with findings, sources, and executive summary
        """
        query = ResearchQuery(
            topic=topic,
            focus_areas=focus_areas,
            time_range=time_range,
            depth=depth,
        )

        # Check memory for relevant context
        if self._memory:
            context = await self._memory.get_context_for_query(topic)
            if context:
                logger.info(f"Found relevant memory context: {context[:100]}...")

        result = await self.orchestrator.launch(
            "financial_research",
            {"query": query},
        )

        report = result.get("report")
        if not report:
            raise RuntimeError("Research failed to produce a report")

        # Store in memory for future reference
        if self._memory:
            await self._memory.add(
                f"Researched: {topic}. Key finding: {report.get('executive_summary', '')[:200]}",
                metadata={"topic": topic, "timestamp": datetime.utcnow().isoformat()},
            )

        return ResearchReport(**report)

    async def research_stream(
        self,
        topic: str,
        focus_areas: list[str] | None = None,
    ) -> AsyncIterator[dict]:
        """
        Stream research progress events.

        Yields events like:
            {"step": "decompose_question", "message": "Breaking down research topic..."}
            {"step": "gather_news", "message": "Found 15 relevant news articles"}
            {"step": "analyze_findings", "message": "Extracted 6 key findings"}
            {"step": "complete", "report": ResearchReport(...)}
        """
        query = ResearchQuery(topic=topic, focus_areas=focus_areas)

        yield {"step": "start", "message": f"Starting research on: {topic}"}

        # TODO: Integrate with event-driven execution when implemented
        # For now, run synchronously and yield completion
        report = await self.research(topic, focus_areas)

        yield {
            "step": "complete",
            "message": "Research complete",
            "report": report.model_dump(),
        }


def create_financial_research_agent(
    config: ResearchConfig | None = None,
) -> FinancialResearchAgent:
    """Create a financial research agent with default configuration."""
    return FinancialResearchAgent(config)


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Run example financial research."""
    import argparse

    parser = argparse.ArgumentParser(description="Financial Deep Research Agent")
    parser.add_argument(
        "topic",
        nargs="?",
        default="Analyze Tesla's competitive position in the EV market for 2026",
        help="Research topic",
    )
    parser.add_argument(
        "--focus",
        nargs="+",
        default=["market share", "technology", "financial health"],
        help="Focus areas for research",
    )
    parser.add_argument(
        "--depth",
        choices=["quick", "detailed", "comprehensive"],
        default="comprehensive",
        help="Research depth",
    )

    args = parser.parse_args()

    # Create agent
    agent = create_financial_research_agent()

    # Optional: Add memory
    try:
        from app import MemoryStoreClient
        mem0_client = MemoryStoreClient(
            base_url=os.getenv("MEM0_URL", "https://mem0.cfk.devfg.rbc.com"),
            agent_id="financial-research-agent",
        )
        agent.with_memory(Mem0Memory(client=mem0_client))
        print("✓ Connected to mem0 memory store")
    except ImportError:
        print("ℹ Running without persistent memory (mem0 not available)")

    print(f"\n🔍 Researching: {args.topic}")
    print(f"   Focus areas: {', '.join(args.focus)}")
    print(f"   Depth: {args.depth}\n")

    # Run research
    try:
        report = await agent.research(
            topic=args.topic,
            focus_areas=args.focus,
            depth=args.depth,
        )

        print("=" * 60)
        print("RESEARCH REPORT")
        print("=" * 60)
        print(f"\n📋 Topic: {report.topic}")
        print(f"\n📝 Executive Summary:\n{report.executive_summary}")
        print(f"\n🔑 Key Findings ({len(report.key_findings)}):")
        for i, finding in enumerate(report.key_findings, 1):
            print(f"   {i}. [{finding.category.upper()}] {finding.finding}")
            print(f"      Confidence: {finding.confidence:.0%}")
        print(f"\n📚 Sources Used: {len(report.sources)}")
        print(f"📊 Methodology: {report.methodology}")

    except Exception as e:
        print(f"❌ Research failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
