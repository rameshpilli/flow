"""
Client Meeting Prep Tool (CMPT) Chain Implementation using FlowForge

This module implements the full CMPT pipeline using FlowForge's DAG-based
chain orchestration framework. It migrates the original chain server
architecture to use decorators, dependency resolution, and parallel execution.

Architecture:
    ┌─────────────────────────────────────────────────────────────────────┐
    │                     CMPT Chain Pipeline                              │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                      │
    │  ┌──────────────────┐    ┌─────────────────────┐    ┌─────────────┐ │
    │  │  Context Builder │    │ Content Prioritizer │    │  Response   │ │
    │  │                  │───▶│                     │───▶│  Builder    │ │
    │  │  • Company Info  │    │  • Temporal Rules   │    │             │ │
    │  │  • Earnings Cal  │    │  • Subquery Engine  │    │  • Metrics  │ │
    │  │  • Persona       │    │  • Topic Ranker     │    │  • Analysis │ │
    │  └──────────────────┘    └─────────────────────┘    └─────────────┘ │
    │                                    │                                 │
    │                                    ▼                                 │
    │                          ┌─────────────────────┐                     │
    │                          │    Data Agents      │                     │
    │                          │  (parallel fetch)   │                     │
    │                          │ • News  • SEC       │                     │
    │                          │ • Earnings          │                     │
    │                          └─────────────────────┘                     │
    └─────────────────────────────────────────────────────────────────────┘

Usage:
    from flowforge.examples.cmpt_chain import forge, CMPTRequest

    # Run the chain
    result = await forge.launch(
        "cmpt_pipeline",
        data={
            "company_name": "Apple Inc.",
            "meeting_date": "2025-01-15",
            "client_email": "client@example.com",
        }
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from flowforge import FlowForge
from flowforge.core.context import ChainContext, ContextScope

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                           DATA MODELS & SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class ToolName(Enum):
    """Data agent tool names"""
    EARNINGS_TOOL = "earnings_agent"
    NEWS_TOOL = "news_agent"
    SEC_TOOL = "sec_agent"


class CMPTRequest(BaseModel):
    """Unified request model for CMPT chain"""
    corporate_client_email: str | None = None
    corporate_client_names: str | None = None
    rbc_employee_email: str | None = None
    meeting_datetime: str | None = None
    corporate_company_name: str | None = None
    verbose: bool = False


class CitationDict(BaseModel):
    """Structured citation with source tracking"""
    source_agent: list[str] = Field(
        description="List of data agents used (SEC_agent, earnings_agent, news_agent)"
    )
    source_content: list[str] = Field(
        description="List of verbatim quotes from source chunks"
    )
    reasoning: str = Field(
        description="Explanation of extraction/calculation logic"
    )


class FinancialMetricsResponse(BaseModel):
    """Financial metrics extraction response"""
    current_annual_revenue: float | None = None
    current_annual_revenue_date: str | None = None
    current_annual_revenue_citation: CitationDict | None = None
    current_annual_revenue_yoy_change: float | None = None
    current_annual_revenue_yoy_change_citation: CitationDict | None = None
    estimated_annual_revenue_next_year: float | None = None
    estimated_annual_revenue_next_year_date: str | None = None
    estimated_annual_revenue_next_year_citation: CitationDict | None = None
    ebitda_margin: float | None = None
    ebitda_margin_citation: CitationDict | None = None
    ebitda_margin_yoy_change: float | None = None
    ebitda_margin_yoy_change_citation: CitationDict | None = None
    stock_price: float | None = None
    stock_price_citation: CitationDict | None = None
    stock_price_daily_change: float | None = None
    stock_price_daily_change_percent: float | None = None
    stock_price_yoy_change: float | None = None
    stock_price_yoy_change_citation: CitationDict | None = None
    market_cap: float | None = None
    market_cap_citation: CitationDict | None = None
    market_cap_date: str | None = None
    revenue_growth_trajectory: dict[str, float | None] | None = None
    revenue_growth_trajectory_citation: CitationDict | None = None


class StrategicAnalysisResponse(BaseModel):
    """Strategic analysis response for client meeting"""
    strength: list[str] = Field(description="4-6 key competitive strengths")
    weakness: list[str] = Field(description="4-6 key vulnerabilities")
    opportunity: list[str] = Field(description="4-6 growth opportunities")
    threat: list[str] = Field(description="4-6 external threats")
    investment_thesis: list[dict[str, list[str]]] = Field(
        description="3-4 investment thesis points with bullets"
    )
    key_risk_highlights: list[str] = Field(description="5-7 critical risks")
    strategic_opportunities: list[dict[str, list[str]]] = Field(
        description="3-4 strategic opportunities"
    )
    recent_developments: list[dict[str, Any]] = Field(
        description="4-6 recent developments with category, date, description, source_url"
    )
    sources: list[str] = Field(description="8-12 sources cited")


# ═══════════════════════════════════════════════════════════════════════════════
#                     STEP INPUT/OUTPUT CONTRACT MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class CompanyInfoOutput(BaseModel):
    """Output contract for extract_company_info step"""
    company_name: str
    ticker_symbol: str | None = None
    company_type: str = "PUB"  # PUB, PRIV, SUB
    sector: str | None = None
    industry: str | None = None


class ContextBuilderOutput(BaseModel):
    """Output contract for build_context step"""
    company_info: dict | None = None
    temporal_context: dict | None = None
    meeting_date: str
    company_name: str | None = None
    company_type: str = "PUB"


class SourcePrioritiesOutput(BaseModel):
    """Output contract for temporal_source_prioritizer step"""
    earnings_agent: int = Field(default=20, ge=0, le=100)
    news_agent: int = Field(default=60, ge=0, le=100)
    sec_agent: int = Field(default=20, ge=0, le=100)


class CMPTFinalResponse(BaseModel):
    """Final output contract for the CMPT chain"""
    context_builder: dict
    content_prioritization: dict
    response_builder_and_generator: dict


# ═══════════════════════════════════════════════════════════════════════════════
#                           GRID CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


GRID_CONFIG = {
    "earnings_proximity_weeks": 1,

    "priority_profiles": {
        "earnings_dominant": {
            ToolName.EARNINGS_TOOL.value: 50,
            ToolName.NEWS_TOOL.value: 30,
            ToolName.SEC_TOOL.value: 20
        },
        "news_dominant": {
            ToolName.EARNINGS_TOOL.value: 20,
            ToolName.NEWS_TOOL.value: 60,
            ToolName.SEC_TOOL.value: 20
        }
    },

    "temporal_source_prioritizer": {
        "rules": [
            {
                "name": "non_public_company",
                "condition": lambda ctx: ctx["company_type"] not in ["PUB", "SUB"],
                "priority_profile": "news_dominant"
            },
            {
                "name": "earnings_proximity",
                "condition": lambda ctx: (
                    ctx["company_type"] in ["PUB", "SUB"] and
                    ctx.get("max_earnings_event_date") and
                    abs((ctx["max_earnings_event_date"] - ctx["meeting_date"]).days) <= ctx["window"]
                ),
                "priority_profile": "earnings_dominant"
            }
        ],
        "default_profile": "news_dominant"
    },

    "content_prioritization_topics": [
        "financial_performance",
        "strategic_initiatives",
        "market_position",
        "risk_factors",
        "management_changes"
    ]
}


# ═══════════════════════════════════════════════════════════════════════════════
#                           INITIALIZE FLOWFORGE
# ═══════════════════════════════════════════════════════════════════════════════


forge = FlowForge(
    name="cmpt_chain",
    version="2.0.0",
    max_parallel=10,
    default_timeout_ms=60000,
)


# ═══════════════════════════════════════════════════════════════════════════════
#                           DATA AGENTS
# ═══════════════════════════════════════════════════════════════════════════════


@forge.agent(name="news_agent", group="data", description="Fetches news articles via MCP")
class NewsAgent:
    """News data agent using MCP integration"""

    def __init__(self):
        self.server_url = os.getenv("NEWS_AGENT_MCP_URL")
        self.bearer_token = os.getenv("NEWS_AGENT_MCP_BEARER_TOKEN")
        self.tool_name = os.getenv("NEWS_AGENT_MCP_TOOL", "search_news")

    async def fetch(self, company_name: str, **kwargs) -> list[dict]:
        """Fetch news for a company"""
        subqueries = self._build_subqueries(company_name)
        results = []

        for subquery in subqueries:
            try:
                # In production, this would use MCP client
                # For now, return structured placeholder
                result = await self._execute_query(subquery)
                if result:
                    results.extend(result)
            except Exception as e:
                logger.error(f"News query failed: {e}")

        return results

    def _build_subqueries(self, company_name: str) -> list[dict]:
        """Build news search subqueries"""
        end_date = datetime.now().strftime('%Y-%m-%d')
        month_ago = (datetime.now() - timedelta(days=31)).strftime('%Y-%m-%d')
        five_days_ago = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

        return [
            {
                "search_query": f"{company_name} executive leadership changes",
                "topics": ["executive", "CEO", "CFO", "leadership"],
                "absolute_date_range": {"start_date": month_ago, "end_date": end_date}
            },
            {
                "search_query": f"{company_name} mergers acquisitions M&A",
                "topics": ["merger", "acquisition", "M&A", "deal"],
                "absolute_date_range": {"start_date": month_ago, "end_date": end_date}
            },
            {
                "search_query": f"{company_name} stock price market cap",
                "topics": ["market cap", "stock price", "valuation"],
                "absolute_date_range": {"start_date": five_days_ago, "end_date": end_date}
            },
        ]

    async def _execute_query(self, subquery: dict) -> list[dict]:
        """Execute MCP query - placeholder for real implementation"""
        # TODO: Integrate with actual MCP client
        logger.info(f"Executing news query: {subquery.get('search_query', '')[:50]}...")
        return []


@forge.agent(name="sec_agent", group="data", description="Fetches SEC filings via MCP")
class SECAgent:
    """SEC filings data agent"""

    def __init__(self):
        self.server_url = os.getenv("SEC_AGENT_MCP_URL")
        self.bearer_token = os.getenv("SEC_AGENT_MCP_BEARER_TOKEN")
        self.tool_name = os.getenv("SEC_AGENT_MCP_TOOL", "search_filings")

    async def fetch(self, company_name: str, **kwargs) -> list[dict]:
        """Fetch SEC filings for a company"""
        subqueries = self._build_subqueries(company_name)
        results = []

        for subquery in subqueries:
            try:
                result = await self._execute_query(subquery)
                if result:
                    results.extend(result)
            except Exception as e:
                logger.error(f"SEC query failed: {e}")

        return results

    def _build_subqueries(self, company_name: str) -> list[dict]:
        """Build SEC search subqueries"""
        return [
            {
                "reporting_entity": company_name,
                "search_queries": [
                    "consolidated statements of operations",
                    "statements of income",
                    "total revenue"
                ],
                "keywords": [
                    "net sales", "total revenue", "quarterly revenue",
                    "three months ended", "revenue"
                ],
                "get_latest": 8
            },
            {
                "reporting_entity": company_name,
                "search_queries": [
                    "consolidated balance sheets",
                    "stockholders equity",
                    "common stock outstanding shares"
                ],
                "keywords": [
                    "outstanding shares", "common stock", "shares outstanding"
                ],
                "get_latest": 1
            }
        ]

    async def _execute_query(self, subquery: dict) -> list[dict]:
        """Execute MCP query - placeholder for real implementation"""
        logger.info(f"Executing SEC query for: {subquery.get('reporting_entity', '')}")
        return []


@forge.agent(name="earnings_agent", group="data", description="Fetches earnings transcripts via MCP")
class EarningsAgent:
    """Earnings transcript data agent"""

    def __init__(self):
        self.server_url = os.getenv("EARNINGS_AGENT_MCP_URL")
        self.bearer_token = os.getenv("EARNINGS_AGENT_MCP_BEARER_TOKEN")
        self.tool_name = os.getenv("EARNINGS_AGENT_MCP_TOOL", "search_earnings")

    async def fetch(
        self,
        company_name: str,
        fiscal_year: str,
        fiscal_quarter: str,
        **kwargs
    ) -> list[dict]:
        """Fetch earnings transcripts for a company"""
        try:
            subquery = {
                "query": f"Give me the earnings transcript for {company_name} for fiscal year: {fiscal_year} and quarter: {fiscal_quarter}."
            }
            return await self._execute_query(subquery)
        except Exception as e:
            logger.error(f"Earnings query failed: {e}")
            return []

    async def _execute_query(self, subquery: dict) -> list[dict]:
        """Execute MCP query - placeholder for real implementation"""
        logger.info(f"Executing earnings query: {subquery.get('query', '')[:50]}...")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#                           CHAIN STEPS
# ═══════════════════════════════════════════════════════════════════════════════


# ---------- CONTEXT BUILDER STEPS ----------


@forge.step(
    name="extract_company_info",
    produces=["company_info"],
    description="Extract company information from external API",
    timeout_ms=30000,
    group="context_builder",
    # ═══════════════════════════════════════════════════════════════════════════
    #                    INPUT/OUTPUT CONTRACTS (FAIL-FAST)
    # ═══════════════════════════════════════════════════════════════════════════
    # input_model validates data BEFORE chain starts - fail fast on bad payloads
    input_model=CMPTRequest,
    input_key="request",  # Key in initial_data to validate
    # output_model validates step output - ensures downstream steps get expected data
    output_model=CompanyInfoOutput,
    validate_output=False,  # Set to True in production for strict validation
)
async def extract_company_info(ctx: ChainContext) -> dict:
    """
    Extract company information (ticker, type, etc.) from foundation service.

    Equivalent to: ContextBuilderService.corporate_client_firm_extractor

    Input Contract: CMPTRequest (validated at launch time)
    Output Contract: CompanyInfoOutput
    """
    # Access validated request - already a CMPTRequest instance if validation passed
    request = ctx.get("request")
    if isinstance(request, CMPTRequest):
        company_name = request.corporate_company_name
    else:
        company_name = ctx.get("company_name")

    if not company_name:
        logger.warning("No company name provided")
        return {"company_info": None}

    try:
        # In production, this would call the foundation service
        # url = os.getenv('FOUNDATION_COMPANY_MATCHES')
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, json={"company_name": company_name})
        #     result = response.json()

        # Placeholder response structure
        company_info = {
            "company_name": company_name,
            "ticker_symbol": None,
            "company_type": "PUB",  # PUB, PRIV, SUB
            "sector": None,
            "industry": None,
        }

        ctx.set("company_info", company_info, scope=ContextScope.CHAIN)
        logger.info(f"Extracted company info for: {company_name}")

        return {"company_info": company_info}

    except Exception as e:
        logger.error(f"Company info extraction failed: {e}")
        return {"company_info": None, "error": str(e)}


@forge.step(
    name="extract_temporal_context",
    deps=["extract_company_info"],
    produces=["temporal_context"],
    description="Extract temporal context (earnings calendar) for the company",
    timeout_ms=30000,
    group="context_builder"
)
async def extract_temporal_context(ctx: ChainContext) -> dict:
    """
    Extract temporal context including earnings calendar.

    Equivalent to: ContextBuilderService.temporal_content_extractor
    """
    company_info = ctx.get("company_info", {})
    company_name = company_info.get("company_name") or ctx.get("company_name")
    # ticker available for future API calls: company_info.get("ticker_symbol")

    try:
        # In production, this would call the earnings calendar API
        # url = os.getenv('FOUNDATION_EARNING_CALENDAR_URL')

        # Placeholder response
        temporal_context = {
            "event_dt": None,
            "fiscal_year": str(datetime.now().year),
            "fiscal_period": str((datetime.now().month - 1) // 3 + 1),
            "earnings_events": []
        }

        ctx.set("temporal_context", temporal_context, scope=ContextScope.CHAIN)
        logger.info(f"Extracted temporal context for: {company_name}")

        return {"temporal_context": temporal_context}

    except Exception as e:
        logger.error(f"Temporal context extraction failed: {e}")
        return {"temporal_context": None, "error": str(e)}


@forge.step(
    name="build_context",
    deps=["extract_company_info", "extract_temporal_context"],
    produces=["context_builder_output"],
    description="Combine all context builder outputs",
    group="context_builder"
)
async def build_context(ctx: ChainContext) -> dict:
    """
    Combine all context builder outputs into a unified structure.

    Equivalent to: ContextBuilderService.execute
    """
    company_info = ctx.get("company_info", {})
    temporal_context = ctx.get("temporal_context", {})
    meeting_date = ctx.get("meeting_date") or datetime.now().strftime("%Y-%m-%d")

    context_builder_output = {
        "company_info": company_info,
        "temporal_context": temporal_context,
        "meeting_date": meeting_date,
        "company_name": company_info.get("company_name") or ctx.get("company_name"),
        "company_type": company_info.get("company_type", "PUB"),
    }

    ctx.set("context_builder_output", context_builder_output, scope=ContextScope.CHAIN)

    return {"context_builder_output": context_builder_output}


# ---------- CONTENT PRIORITIZATION STEPS ----------


@forge.step(
    name="temporal_source_prioritizer",
    deps=["build_context"],
    produces=["source_priorities"],
    description="Determine data source priorities based on temporal context",
    group="content_prioritization"
)
async def temporal_source_prioritizer(ctx: ChainContext) -> dict:
    """
    Determine data source priorities based on meeting date and earnings proximity.

    Equivalent to: ContentPrioritizationService.temporal_source_prioritizer
    """
    context_output = ctx.get("context_builder_output", {})
    temporal_context = context_output.get("temporal_context", {})
    meeting_date = context_output.get("meeting_date")
    company_type = context_output.get("company_type", "PUB")

    config = GRID_CONFIG
    earnings_proximity_weeks = config.get("earnings_proximity_weeks", 1)
    window = earnings_proximity_weeks * 7  # days

    # Parse dates
    meeting_datetime = datetime.strptime(meeting_date, "%Y-%m-%d") if meeting_date else datetime.now()
    max_earnings_date = None
    if temporal_context.get("event_dt"):
        max_earnings_date = datetime.strptime(temporal_context["event_dt"], "%Y-%m-%d")

    # Build rule context
    rule_context = {
        "company_type": company_type,
        "meeting_date": meeting_datetime,
        "max_earnings_event_date": max_earnings_date,
        "window": window
    }

    # Evaluate rules
    prioritizer_config = config["temporal_source_prioritizer"]
    priority_profiles = config["priority_profiles"]
    default_profile = prioritizer_config["default_profile"]
    source_priorities = priority_profiles[default_profile]

    for rule in prioritizer_config["rules"]:
        try:
            if callable(rule["condition"]) and rule["condition"](rule_context):
                profile_name = rule["priority_profile"]
                source_priorities = priority_profiles[profile_name]
                logger.info(f"Applied priority rule: {rule['name']} -> {profile_name}")
                break
        except Exception as e:
            logger.warning(f"Error evaluating rule '{rule.get('name')}': {e}")

    ctx.set("source_priorities", source_priorities, scope=ContextScope.CHAIN)

    return {"source_priorities": source_priorities}


@forge.step(
    name="generate_subqueries",
    deps=["build_context"],
    produces=["subqueries"],
    description="Generate subqueries for data agents",
    group="content_prioritization"
)
async def generate_subqueries(ctx: ChainContext) -> dict:
    """
    Generate subqueries for each data agent.

    Equivalent to: ContentPrioritizationService.subquery_engine
    """
    context_output = ctx.get("context_builder_output", {})
    company_name = context_output.get("company_name", "")
    temporal_context = context_output.get("temporal_context", {})

    fiscal_year = temporal_context.get("fiscal_year", str(datetime.now().year))
    fiscal_quarter = temporal_context.get("fiscal_period", "1")

    # Get agents to build their subqueries
    news_agent = forge.get_agent("news_agent")
    sec_agent = forge.get_agent("sec_agent")

    subqueries = {
        ToolName.NEWS_TOOL.value: news_agent._build_subqueries(company_name),
        ToolName.SEC_TOOL.value: sec_agent._build_subqueries(company_name),
        ToolName.EARNINGS_TOOL.value: [{
            "company_name": company_name,
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fiscal_quarter
        }]
    }

    ctx.set("subqueries", subqueries, scope=ContextScope.CHAIN)

    return {"subqueries": subqueries}


@forge.step(
    name="prioritize_content",
    deps=["temporal_source_prioritizer", "generate_subqueries"],
    produces=["content_prioritization_output"],
    description="Combine prioritization outputs",
    group="content_prioritization"
)
async def prioritize_content(ctx: ChainContext) -> dict:
    """
    Combine all content prioritization outputs.

    Equivalent to: ContentPrioritizationService.execute
    """
    source_priorities = ctx.get("source_priorities", {})
    subqueries = ctx.get("subqueries", {})

    content_prioritization_output = {
        "temporal_source_prioritizer": source_priorities,
        "subqueries_from_engine": subqueries,
        "topic_ranker_result": GRID_CONFIG.get("content_prioritization_topics", [])
    }

    ctx.set("content_prioritization_output", content_prioritization_output, scope=ContextScope.CHAIN)

    return {"content_prioritization_output": content_prioritization_output}


# ---------- DATA FETCHING STEPS (PARALLEL) ----------


@forge.step(
    name="fetch_news_data",
    deps=["prioritize_content"],
    produces=["news_data"],
    description="Fetch news data from news agent",
    timeout_ms=60000,
    group="data_fetch"
)
async def fetch_news_data(ctx: ChainContext) -> dict:
    """Fetch news data using the news agent"""
    context_output = ctx.get("context_builder_output", {})
    company_name = context_output.get("company_name", "")

    try:
        news_agent = forge.get_agent("news_agent")
        news_data = await news_agent.fetch(company_name)
        ctx.set("news_data", news_data, scope=ContextScope.CHAIN)
        return {"news_data": news_data}
    except Exception as e:
        logger.error(f"News data fetch failed: {e}")
        return {"news_data": [], "error": str(e)}


@forge.step(
    name="fetch_sec_data",
    deps=["prioritize_content"],
    produces=["sec_data"],
    description="Fetch SEC filings data",
    timeout_ms=60000,
    group="data_fetch"
)
async def fetch_sec_data(ctx: ChainContext) -> dict:
    """Fetch SEC filings data using the SEC agent"""
    context_output = ctx.get("context_builder_output", {})
    company_name = context_output.get("company_name", "")

    try:
        sec_agent = forge.get_agent("sec_agent")
        sec_data = await sec_agent.fetch(company_name)
        ctx.set("sec_data", sec_data, scope=ContextScope.CHAIN)
        return {"sec_data": sec_data}
    except Exception as e:
        logger.error(f"SEC data fetch failed: {e}")
        return {"sec_data": [], "error": str(e)}


@forge.step(
    name="fetch_earnings_data",
    deps=["prioritize_content"],
    produces=["earnings_data"],
    description="Fetch earnings transcript data",
    timeout_ms=60000,
    group="data_fetch"
)
async def fetch_earnings_data(ctx: ChainContext) -> dict:
    """Fetch earnings data using the earnings agent"""
    context_output = ctx.get("context_builder_output", {})
    temporal_context = context_output.get("temporal_context", {})
    company_name = context_output.get("company_name", "")

    fiscal_year = temporal_context.get("fiscal_year", str(datetime.now().year))
    fiscal_quarter = temporal_context.get("fiscal_period", "1")

    try:
        earnings_agent = forge.get_agent("earnings_agent")
        earnings_data = await earnings_agent.fetch(
            company_name,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter
        )
        ctx.set("earnings_data", earnings_data, scope=ContextScope.CHAIN)
        return {"earnings_data": earnings_data}
    except Exception as e:
        logger.error(f"Earnings data fetch failed: {e}")
        return {"earnings_data": [], "error": str(e)}


# ---------- RESPONSE BUILDER STEPS ----------


@forge.step(
    name="parse_agent_data",
    deps=["fetch_news_data", "fetch_sec_data", "fetch_earnings_data"],
    produces=["parsed_agent_data"],
    description="Parse and format data from all agents",
    group="response_builder"
)
async def parse_agent_data(ctx: ChainContext) -> dict:
    """
    Parse and format data from all agents into a unified structure.

    Equivalent to: ResponseBuilderAndGenerator.context_parser
    """
    news_data = ctx.get("news_data", [])
    sec_data = ctx.get("sec_data", [])
    earnings_data = ctx.get("earnings_data", [])

    def format_chunks(data: list, agent_name: str) -> str:
        """Format data chunks into readable text"""
        if not data:
            return ""

        formatted_chunks = []
        for idx, item in enumerate(data, 1):
            if isinstance(item, dict):
                chunk_str = f"CHUNK-{idx}\n\n"
                chunk_str += "METADATA\n"

                metadata = {k: v for k, v in item.items() if k != "text"}
                for k, v in metadata.items():
                    chunk_str += f"{k}: {v}\n"

                chunk_str += "\n\nCHUNK-CONTENT\n"
                chunk_str += item.get("text", str(item))
                formatted_chunks.append(chunk_str)

        return "\n\n\n".join(formatted_chunks)

    parsed_agent_data = {
        ToolName.NEWS_TOOL.value: format_chunks(news_data, "news"),
        ToolName.SEC_TOOL.value: format_chunks(sec_data, "sec"),
        ToolName.EARNINGS_TOOL.value: format_chunks(earnings_data, "earnings"),
    }

    ctx.set("parsed_agent_data", parsed_agent_data, scope=ContextScope.CHAIN)

    return {"parsed_agent_data": parsed_agent_data}


@forge.step(
    name="build_prompts",
    deps=["parse_agent_data"],
    produces=["prompts"],
    description="Build LLM prompts for metrics and analysis",
    group="response_builder"
)
async def build_prompts(ctx: ChainContext) -> dict:
    """
    Build LLM prompts for financial metrics and strategic analysis.

    Equivalent to: ResponseBuilderAndGenerator.prompt_builder
    """
    parsed_data = ctx.get("parsed_agent_data", {})
    context_output = ctx.get("context_builder_output", {})
    prioritization = ctx.get("content_prioritization_output", {})

    company_name = context_output.get("company_name", "Unknown Company")
    source_priorities = prioritization.get("temporal_source_prioritizer", {})

    # Build financial metrics prompt
    financial_metrics_prompt = f"""
## Task: Extract Financial Metrics for {company_name}

[SEC_AGENT]
{parsed_data.get(ToolName.SEC_TOOL.value, 'No SEC data available')}

[EARNINGS_AGENT]
{parsed_data.get(ToolName.EARNINGS_TOOL.value, 'No earnings data available')}

[NEWS_AGENT]
{parsed_data.get(ToolName.NEWS_TOOL.value, 'No news data available')}

Extract precise financial metrics with citations for each value.
"""

    # Build strategic analysis prompt
    news_pct = source_priorities.get(ToolName.NEWS_TOOL.value, 40)
    earnings_pct = source_priorities.get(ToolName.EARNINGS_TOOL.value, 30)
    sec_pct = source_priorities.get(ToolName.SEC_TOOL.value, 30)

    strategic_analysis_prompt = f"""
## Task: Strategic Analysis for {company_name}

[NEWS_AGENT] (Include {news_pct}% from this source)
{parsed_data.get(ToolName.NEWS_TOOL.value, 'No news data available')}

[EARNINGS_AGENT] (Include {earnings_pct}% from this source)
{parsed_data.get(ToolName.EARNINGS_TOOL.value, 'No earnings data available')}

[SEC_AGENT] (Include {sec_pct}% from this source)
{parsed_data.get(ToolName.SEC_TOOL.value, 'No SEC data available')}

Generate comprehensive strategic analysis including SWOT, investment thesis, and recent developments.
"""

    prompts = {
        "financial_metrics_prompt": financial_metrics_prompt,
        "strategic_analysis_prompt": strategic_analysis_prompt,
    }

    ctx.set("prompts", prompts, scope=ContextScope.CHAIN)

    return {"prompts": prompts}


@forge.step(
    name="generate_financial_metrics",
    deps=["build_prompts"],
    produces=["financial_metrics"],
    description="Generate financial metrics using LLM",
    timeout_ms=120000,
    group="response_builder"
)
async def generate_financial_metrics(ctx: ChainContext) -> dict:
    """
    Generate financial metrics using structured LLM output.

    Equivalent to: ResponseBuilderAndGenerator.get_structured_response (for metrics)
    """
    # In production, get prompt from: ctx.get("prompts", {}).get("financial_metrics_prompt")
    # and call the LLM gateway
    # from flowforge.services.llm_gateway import get_llm_client
    # client = get_llm_client()
    # response = await client.generate_async(prompt, ...)

    # Placeholder response
    financial_metrics = {
        "current_annual_revenue": None,
        "ebitda_margin": None,
        "stock_price": None,
        "market_cap": None,
        "revenue_growth_trajectory": None,
    }

    ctx.set("financial_metrics", financial_metrics, scope=ContextScope.CHAIN)

    return {"financial_metrics": financial_metrics}


@forge.step(
    name="generate_strategic_analysis",
    deps=["build_prompts"],
    produces=["strategic_analysis"],
    description="Generate strategic analysis using LLM",
    timeout_ms=120000,
    group="response_builder"
)
async def generate_strategic_analysis(ctx: ChainContext) -> dict:
    """
    Generate strategic analysis using structured LLM output.

    Equivalent to: ResponseBuilderAndGenerator.get_structured_response (for analysis)
    """
    # In production, get prompt from: ctx.get("prompts", {}).get("strategic_analysis_prompt")
    # Placeholder response
    strategic_analysis = {
        "strength": [],
        "weakness": [],
        "opportunity": [],
        "threat": [],
        "investment_thesis": [],
        "key_risk_highlights": [],
        "strategic_opportunities": [],
        "recent_developments": [],
        "sources": [],
    }

    ctx.set("strategic_analysis", strategic_analysis, scope=ContextScope.CHAIN)

    return {"strategic_analysis": strategic_analysis}


@forge.step(
    name="validate_metrics",
    deps=["generate_financial_metrics"],
    produces=["validation_results"],
    description="Validate extracted financial metrics against sources",
    group="response_builder"
)
async def validate_metrics(ctx: ChainContext) -> dict:
    """
    Validate extracted financial metrics against source documents.

    Equivalent to: MetricsValidator.validate_financial_metrics
    """
    # In production, validate: ctx.get("financial_metrics") against ctx.get("parsed_agent_data")
    # Placeholder validation
    validation_results = {
        "validation_summary": {
            "total_fields_checked": 0,
            "fields_with_values": 0,
            "sources_verified": 0,
            "warnings_count": 0,
        },
        "field_validations": {},
        "warnings": [],
        "sanity_checks": {"passed": [], "failed": [], "warnings": []}
    }

    ctx.set("validation_results", validation_results, scope=ContextScope.CHAIN)

    return {"validation_results": validation_results}


@forge.step(
    name="build_response",
    deps=["generate_financial_metrics", "generate_strategic_analysis", "validate_metrics"],
    produces=["final_response"],
    description="Build final CMPT response",
    group="response_builder",
    output_model=CMPTFinalResponse,
    validate_output=False,  # Set to True for strict validation
)
async def build_response(ctx: ChainContext) -> dict:
    """
    Build the final CMPT response combining all outputs.

    Equivalent to: ChainOrchestrator.execute_chain (final assembly)
    """
    context_output = ctx.get("context_builder_output", {})
    prioritization = ctx.get("content_prioritization_output", {})
    financial_metrics = ctx.get("financial_metrics", {})
    strategic_analysis = ctx.get("strategic_analysis", {})
    validation_results = ctx.get("validation_results", {})
    parsed_data = ctx.get("parsed_agent_data", {})

    final_response = {
        "context_builder": {
            "company_info": context_output.get("company_info"),
            "temporal_context": context_output.get("temporal_context"),
            "meeting_date": context_output.get("meeting_date"),
        },
        "content_prioritization": {
            "temporal_source_prioritizer": prioritization.get("temporal_source_prioritizer"),
            "subqueries_from_engine": prioritization.get("subqueries_from_engine"),
            "topic_ranker_result": prioritization.get("topic_ranker_result"),
        },
        "response_builder_and_generator": {
            "financial_metrics_result": financial_metrics,
            "strategic_analysis_result": strategic_analysis,
            "validation_results": validation_results,
            "parsed_data_agent_chunks": {k: len(v) for k, v in parsed_data.items()},
            "company_name": context_output.get("company_name"),
        },
    }

    ctx.set("final_response", final_response, scope=ContextScope.CHAIN)

    return {"final_response": final_response}


# ═══════════════════════════════════════════════════════════════════════════════
#                           CHAIN DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════


@forge.chain(name="cmpt_pipeline", description="Client Meeting Prep Tool pipeline")
class CMPTPipeline:
    """
    Complete CMPT pipeline chain.

    Execution Flow:
    1. Context Builder: extract_company_info, extract_temporal_context → build_context
    2. Content Prioritization: temporal_source_prioritizer, generate_subqueries → prioritize_content
    3. Data Fetch (parallel): fetch_news_data, fetch_sec_data, fetch_earnings_data
    4. Response Builder: parse_agent_data → build_prompts
    5. LLM Generation (parallel): generate_financial_metrics, generate_strategic_analysis
    6. Validation & Response: validate_metrics → build_response
    """

    steps = [
        # Context Builder
        "extract_company_info",
        "extract_temporal_context",
        "build_context",
        # Content Prioritization
        "temporal_source_prioritizer",
        "generate_subqueries",
        "prioritize_content",
        # Data Fetch (will run in parallel due to shared deps)
        "fetch_news_data",
        "fetch_sec_data",
        "fetch_earnings_data",
        # Response Builder
        "parse_agent_data",
        "build_prompts",
        # LLM Generation (will run in parallel due to shared deps)
        "generate_financial_metrics",
        "generate_strategic_analysis",
        # Validation & Final Response
        "validate_metrics",
        "build_response",
    ]

    error_handling = "continue"  # Continue on non-critical failures


# ═══════════════════════════════════════════════════════════════════════════════
#                           CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


async def run_cmpt_chain(
    company_name: str,
    meeting_date: str | None = None,
    client_email: str | None = None,
    verbose: bool = False,
) -> dict:
    """
    Convenience function to run the CMPT chain.

    The input is validated against CMPTRequest before execution starts.
    If validation fails, a ContractValidationError is raised immediately
    with clear error messages about what fields are invalid.

    Args:
        company_name: Name of the company to analyze
        meeting_date: Meeting date (YYYY-MM-DD format)
        client_email: Client email address
        verbose: Enable verbose logging

    Returns:
        Final CMPT response dictionary

    Raises:
        ContractValidationError: If input validation fails

    Example:
        # This will fail fast with clear errors if request is invalid
        result = await run_cmpt_chain(
            company_name="Apple Inc.",
            meeting_date="2025-01-15",
        )

        # Or use CMPTRequest directly for better type safety
        request = CMPTRequest(
            corporate_company_name="Apple Inc.",
            meeting_datetime="2025-01-15",
        )
        result = await forge.launch("cmpt_pipeline", data={"request": request})
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    # Build request using the validated model
    # This provides type safety and validation at construction time
    request = CMPTRequest(
        corporate_company_name=company_name,
        meeting_datetime=meeting_date or datetime.now().strftime("%Y-%m-%d"),
        corporate_client_email=client_email,
        verbose=verbose,
    )

    # Launch with the validated request
    # FlowForge will validate again at launch time for fail-fast behavior
    result = await forge.launch("cmpt_pipeline", data={"request": request})
    return result


def validate_chain():
    """Validate the CMPT chain configuration"""
    return forge.check("cmpt_pipeline")


def visualize_chain(format: str = "ascii"):
    """Visualize the CMPT chain DAG"""
    return forge.graph("cmpt_pipeline", format=format)


# ═══════════════════════════════════════════════════════════════════════════════
#                           CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    import sys

    # Validate chain
    print("\n" + "=" * 60)
    print("  CMPT Chain Validation")
    print("=" * 60)

    validation = validate_chain()

    if validation["valid"]:
        print("\n✓ Chain validation passed!")
    else:
        print("\n✗ Chain validation failed!")
        for error in validation.get("errors", []):
            print(f"  - {error}")
        sys.exit(1)

    # Show chain graph
    print("\n" + "=" * 60)
    print("  CMPT Chain DAG")
    print("=" * 60)
    visualize_chain()

    # Run example if --run flag provided
    if "--run" in sys.argv:
        print("\n" + "=" * 60)
        print("  Running CMPT Chain")
        print("=" * 60)

        async def main():
            result = await run_cmpt_chain(
                company_name="Apple Inc.",
                meeting_date="2025-01-15",
                verbose=True,
            )

            print("\n" + "=" * 60)
            print("  CMPT Chain Result")
            print("=" * 60)

            import json
            print(json.dumps(result, indent=2, default=str))

        asyncio.run(main())
