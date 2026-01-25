"""
Financial Deep Research Agent Example

This example demonstrates how to build a multi-stage research agent that:
1. Connects to Refinitiv MCP server for news and market data
2. Decomposes complex research questions into sub-queries
3. Gathers data from multiple sources (news, SEC filings, earnings)
4. Synthesizes findings into a comprehensive analysis report
5. Uses mem0 for persistent memory across sessions

**Context Management Strategy**:
This agent handles large responses from multiple sources using a multi-layered approach:

1. **Source-Level Capping** (cap_per_source): Limits items per source to ensure balanced
   representation. Never blindly discards data - always tracks what was omitted.

2. **Hierarchical Summarization** (SummarizerMiddleware): When combined context exceeds
   thresholds, uses map-reduce to compress while preserving key facts.

3. **Offloading** (OffloadMiddleware): Large raw payloads are stored in Redis/context store,
   replaced with lightweight references. Full data is always recoverable.

4. **Token Budget Management** (TokenManagerMiddleware): Tracks total context tokens,
   auto-triggers summarization or offloading when approaching limits.

See: agentorchestrator/middleware/summarizer.py for strategies (STUFF, MAP_REDUCE, REFINE)

Requirements:
    - Refinitiv MCP server running (NEWS_MCP_URL environment variable)
    - SEC MCP server running (SEC_MCP_URL environment variable)
    - Corporate LLM Gateway access
    - Optional: mem0 memory store for cross-session memory
    - Optional: Redis for large payload offloading

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

# Context management imports
from agentorchestrator.middleware.summarizer import (
    SummarizerMiddleware,
    LangChainSummarizer,
    SummarizationStrategy,
    create_gateway_summarizer,
)
from agentorchestrator.middleware.token_manager import TokenManagerMiddleware
from agentorchestrator.middleware.offload import (
    OffloadMiddleware,
    cap_per_source,
    cap_items_with_metadata,
)

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

    # Context management settings (prevents context window overflow)
    max_context_tokens: int = 100_000  # Total token budget for analysis
    summarization_threshold: int = 8_000  # Summarize step outputs over this
    offload_threshold_bytes: int = 100_000  # Offload payloads over 100KB
    max_items_per_source: int = 20  # Cap items per data source
    enable_auto_summarization: bool = True
    enable_auto_offload: bool = True


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
    """Create the research pipeline orchestrator with context management."""

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
    # Context Management Middleware
    # =========================================================================
    # These middleware components prevent context window overflow when
    # multiple agents return large responses.

    # 1. Token Manager: Track total context budget, auto-trigger compression
    ao.use(TokenManagerMiddleware(
        max_total_tokens=config.max_context_tokens,
        warning_threshold=0.8,  # Warn at 80%, act at 100%
        auto_summarize=config.enable_auto_summarization,
        auto_offload=config.enable_auto_offload,
    ))

    # 2. Summarizer: Compress large step outputs using map-reduce
    if config.enable_auto_summarization and config.llm_server_url:
        try:
            summarizer = create_gateway_summarizer(
                server_url=config.llm_server_url,
                model_name=config.llm_model,
                strategy=SummarizationStrategy.MAP_REDUCE,
                chunk_size=2000,
            )

            # Register domain-specific prompts for financial content
            LangChainSummarizer.register_domain_prompts(
                domain="financial_news",
                map_prompt=(
                    "Summarize this financial news, preserving key facts, "
                    "company names, metrics, dates, and sentiment:\n\n{text}\n\nSummary:"
                ),
                reduce_prompt=(
                    "Combine these news summaries into a cohesive analysis. "
                    "Preserve all key metrics and company mentions:\n\n{text}\n\nFinal Summary:"
                ),
            )

            LangChainSummarizer.register_domain_prompts(
                domain="sec_filings",
                map_prompt=(
                    "Extract key financial data from this SEC filing section, "
                    "including revenue, earnings, risk factors, and guidance:\n\n{text}\n\nKey Data:"
                ),
                reduce_prompt=(
                    "Combine SEC filing extracts into a financial overview:\n\n{text}\n\nOverview:"
                ),
            )

            ao.use(SummarizerMiddleware(
                summarizer=summarizer,
                max_tokens=config.summarization_threshold,
                step_content_types={
                    "gather_news": "financial_news",
                    "gather_sec": "sec_filings",
                    "gather_earnings": "financial_news",
                },
                preserve_original=True,  # Keep original in context for retrieval
            ))
            logger.info("Summarizer middleware enabled with financial domain prompts")
        except Exception as e:
            logger.warning(f"Could not enable summarization: {e}")

    # 3. Offload: Store large payloads in Redis, keep refs in context
    if config.enable_auto_offload:
        try:
            from agentorchestrator.core.context_store import RedisContextStore
            store = RedisContextStore()  # Uses REDIS_URL from env

            ao.use(OffloadMiddleware(
                store=store,
                default_threshold_bytes=config.offload_threshold_bytes,
                step_thresholds={
                    "gather_news": 50_000,  # News can be verbose
                    "gather_sec": 200_000,  # SEC filings are large
                    "gather_earnings": 100_000,
                },
            ))
            logger.info("Offload middleware enabled with Redis context store")
        except ImportError:
            logger.info("Redis not available, using in-memory offloading")
            from agentorchestrator.core.context_store import InMemoryContextStore
            ao.use(OffloadMiddleware(
                store=InMemoryContextStore(),
                default_threshold_bytes=config.offload_threshold_bytes,
            ))

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
    # Step 2: Gather Data from Sources (with intelligent capping)
    # =========================================================================
    @ao.step(name="gather_news", deps=["decompose_question"])
    async def gather_news(ctx: ChainContext) -> dict:
        """
        Gather news from Refinitiv for each research question.

        Uses cap_items_with_metadata to:
        1. Limit total items to prevent context overflow
        2. Preserve metadata about what was omitted
        3. Prioritize by relevance score
        """
        questions = ctx.get("research_questions")
        all_articles = []

        for q in questions:
            if "news" in q.get("sources", []):
                articles = await news_agent.search_news(
                    query=q["question"],
                    companies=q.get("entities", []),
                    limit=config.max_sources_per_query,
                )
                # Tag each article with source question for traceability
                for article in articles:
                    article["_source_question"] = q["question"]
                all_articles.extend(articles)

        # Cap items intelligently - preserve metadata about omissions
        capped_articles, cap_metadata = cap_items_with_metadata(
            all_articles,
            max_items=config.max_items_per_source,
            sort_key=lambda x: x.get("relevance", x.get("score", 0)),
            sort_reverse=True,  # Keep highest relevance
        )

        ctx.set("news_articles", capped_articles)
        ctx.set("news_cap_metadata", cap_metadata)

        logger.info(
            f"Gathered {cap_metadata['original_count']} news articles, "
            f"kept top {cap_metadata['kept_count']} by relevance"
        )
        if cap_metadata['was_capped']:
            logger.info(f"  (omitted {cap_metadata['omitted_count']} lower-relevance articles)")

        return {
            "article_count": cap_metadata['kept_count'],
            "total_found": cap_metadata['original_count'],
            "omitted": cap_metadata['omitted_count'],
        }

    @ao.step(name="gather_sec", deps=["decompose_question"])
    async def gather_sec(ctx: ChainContext) -> dict:
        """
        Gather SEC filings for relevant companies.

        Uses cap_per_source to ensure balanced representation across companies.
        """
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
            # Tag with ticker for source tracking
            for filing in filings:
                filing["_ticker"] = ticker
            all_filings.extend(filings)

        # Cap per ticker to ensure balanced representation
        capped_filings, cap_metadata = cap_per_source(
            all_filings,
            source_field="_ticker",
            max_per_source=5,  # Max 5 filings per company
            total_max=config.max_items_per_source,
        )

        ctx.set("sec_filings", capped_filings)
        ctx.set("sec_cap_metadata", cap_metadata)

        logger.info(
            f"Gathered {cap_metadata['original_count']} SEC filings from {len(tickers)} companies, "
            f"kept {cap_metadata['kept_count']}"
        )
        return {
            "filing_count": cap_metadata['kept_count'],
            "companies": list(tickers),
            "per_company": cap_metadata.get('per_source_counts', {}),
        }

    @ao.step(name="gather_earnings", deps=["decompose_question"])
    async def gather_earnings(ctx: ChainContext) -> dict:
        """
        Gather earnings call transcripts.

        Uses cap_per_source to balance across companies.
        """
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
            for call in calls:
                call["_ticker"] = ticker
            all_calls.extend(calls)

        # Cap per ticker
        capped_calls, cap_metadata = cap_per_source(
            all_calls,
            source_field="_ticker",
            max_per_source=4,  # Last 4 quarters per company
            total_max=config.max_items_per_source,
        )

        ctx.set("earnings_calls", capped_calls)
        ctx.set("earnings_cap_metadata", cap_metadata)

        logger.info(
            f"Gathered {cap_metadata['original_count']} earnings calls, "
            f"kept {cap_metadata['kept_count']}"
        )
        return {
            "call_count": cap_metadata['kept_count'],
            "companies": list(tickers),
        }

    # =========================================================================
    # Step 3: Analyze and Synthesize (Context-Aware)
    # =========================================================================
    @ao.step(name="analyze_findings", deps=["gather_news", "gather_sec", "gather_earnings"])
    async def analyze_findings(ctx: ChainContext) -> dict:
        """
        Analyze gathered data and extract key findings.

        Context Management Strategy:
        1. Check if data was already summarized by SummarizerMiddleware
        2. If raw data is too large, use hierarchical summarization
        3. Include metadata about what was omitted (never blind truncation)
        4. Build context incrementally, checking token budget
        """
        from agentorchestrator.middleware.summarizer import count_tokens

        query: ResearchQuery = ctx.get("query")
        questions = ctx.get("research_questions")

        # Get data - may be summarized by middleware or raw
        news = ctx.get("news_articles", [])
        filings = ctx.get("sec_filings", [])
        calls = ctx.get("earnings_calls", [])

        # Get cap metadata to inform LLM about omissions
        news_meta = ctx.get("news_cap_metadata", {})
        sec_meta = ctx.get("sec_cap_metadata", {})
        earnings_meta = ctx.get("earnings_cap_metadata", {})

        # Build context incrementally, respecting token budget
        max_context_tokens = config.summarization_threshold * 2  # Allow 2x threshold for combined
        context_parts = []
        current_tokens = 0

        # Helper to add section if within budget
        def add_section(title: str, content: str, meta: dict) -> bool:
            nonlocal current_tokens
            section_tokens = count_tokens(content)

            # Add omission note if data was capped
            omission_note = ""
            if meta.get("was_capped"):
                omission_note = f"\n(Note: Showing {meta['kept_count']} of {meta['original_count']} items, " \
                               f"omitted {meta['omitted_count']} lower-relevance items)"

            if current_tokens + section_tokens > max_context_tokens:
                logger.warning(f"Skipping {title} section - would exceed token budget")
                return False

            context_parts.append(f"{title}:{omission_note}\n{content}")
            current_tokens += section_tokens
            return True

        # News section
        if news:
            # Check if news is a string (already summarized by middleware)
            if isinstance(news, str):
                news_content = news
            else:
                news_content = "\n".join([
                    f"- [{a.get('_ticker', 'N/A')}] {a.get('title', 'Untitled')}: "
                    f"{a.get('excerpt', a.get('summary', ''))[:300]}"
                    for a in news
                ])
            add_section("NEWS ARTICLES", news_content, news_meta)

        # SEC filings section
        if filings:
            if isinstance(filings, str):
                sec_content = filings
            else:
                sec_content = "\n".join([
                    f"- [{f.get('_ticker', 'N/A')}] {f.get('type', 'Filing')} "
                    f"({f.get('date', 'N/A')}): {f.get('summary', '')[:400]}"
                    for f in filings
                ])
            add_section("SEC FILINGS", sec_content, sec_meta)

        # Earnings section
        if calls:
            if isinstance(calls, str):
                calls_content = calls
            else:
                calls_content = "\n".join([
                    f"- [{c.get('_ticker', 'N/A')}] Q{c.get('quarter', '?')} "
                    f"{c.get('year', '?')}: {c.get('summary', c.get('highlights', ''))[:400]}"
                    for c in calls
                ])
            add_section("EARNINGS CALLS", calls_content, earnings_meta)

        context = "\n\n".join(context_parts)

        prompt = f"""You are a senior financial analyst. Analyze the following research data
and extract key findings.

RESEARCH TOPIC: {query.topic}
FOCUS AREAS: {', '.join(query.focus_areas or ['general'])}

RESEARCH QUESTIONS:
{chr(10).join([f"- {q['question']}" for q in questions])}

DATA GATHERED:
{context}

CONTEXT NOTE: The data above may be summarized or capped. Where noted, additional
lower-relevance items were omitted to focus on the most important findings.

Extract 5-8 key findings. For each finding:
1. State the finding clearly
2. Rate confidence (0.0-1.0) - lower if based on limited data
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
        logger.info(f"Analyze step using ~{current_tokens} tokens of context")
        response = await llm.generate_async(prompt)

        import json
        try:
            parsed = json.loads(response)
            findings = parsed.get("findings", [])
        except json.JSONDecodeError:
            findings = []

        ctx.set("findings", findings)
        return {
            "finding_count": len(findings),
            "context_tokens_used": current_tokens,
        }

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
