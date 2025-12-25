"""
CMPT Domain Configuration for AgentOrchestrator Middleware

Contains all CMPT-specific extractors, generators, and summarizer prompts
that are registered with AgentOrchestrator middleware at application startup.

Usage:
    from cmpt.domain_config import register_cmpt_middleware
    from agentorchestrator.middleware.offload import OffloadMiddleware
    from agentorchestrator.middleware.summarizer import LangChainSummarizer

    # Register all CMPT-specific middleware configuration
    register_cmpt_middleware(offload_middleware, summarizer)
"""

from typing import Any


# =============================================================================
#                    KEY FIELD EXTRACTORS
# =============================================================================


def extract_sec_key_fields(data: Any) -> dict[str, Any]:
    """
    Extract key fields from SEC filing data.

    Used by OffloadMiddleware to preserve important metadata when
    offloading large SEC filing payloads.
    """
    key_fields = {}

    if isinstance(data, dict):
        # SEC-specific fields
        for field in [
            "filing_type",
            "ticker",
            "company",
            "filing_date",
            "fiscal_year",
            "fiscal_period",
            "cik",
            "accession_number",
        ]:
            if field in data:
                key_fields[field] = data[field]

        # Count items if present
        if "items" in data:
            key_fields["item_count"] = len(data["items"])
        if "sections" in data:
            key_fields["section_count"] = len(data["sections"])

    elif isinstance(data, list):
        key_fields["filing_count"] = len(data)
        if len(data) > 0 and isinstance(data[0], dict):
            key_fields["filing_types"] = list(
                set(d.get("filing_type", "unknown") for d in data[:10])
            )
            if "ticker" in data[0]:
                key_fields["ticker"] = data[0]["ticker"]

    return key_fields


def extract_news_key_fields(data: Any) -> dict[str, Any]:
    """
    Extract key fields from news article data.

    Used by OffloadMiddleware to preserve important metadata when
    offloading large news payloads.
    """
    key_fields = {}

    if isinstance(data, dict):
        for field in [
            "headline",
            "title",
            "source",
            "published_date",
            "ticker",
            "sentiment",
            "category",
        ]:
            if field in data:
                key_fields[field] = data[field]

    elif isinstance(data, list):
        key_fields["article_count"] = len(data)
        if len(data) > 0 and isinstance(data[0], dict):
            # Get date range
            dates = [
                d.get("published_date") or d.get("date")
                for d in data
                if d.get("published_date") or d.get("date")
            ]
            if dates:
                key_fields["date_range"] = {
                    "earliest": min(dates),
                    "latest": max(dates),
                }
            # Get sources
            sources = list(set(d.get("source", "unknown") for d in data[:20]))
            key_fields["sources"] = sources[:5]

    return key_fields


def extract_earnings_key_fields(data: Any) -> dict[str, Any]:
    """
    Extract key fields from earnings/transcript data.

    Used by OffloadMiddleware to preserve important metadata when
    offloading large earnings call payloads.
    """
    key_fields = {}

    if isinstance(data, dict):
        for field in [
            "ticker",
            "company",
            "quarter",
            "fiscal_year",
            "call_date",
            "eps",
            "revenue",
            "guidance",
        ]:
            if field in data:
                key_fields[field] = data[field]

        # Track transcript sections
        if "transcript" in data:
            key_fields["has_transcript"] = True
            if isinstance(data["transcript"], str):
                key_fields["transcript_length"] = len(data["transcript"])

    elif isinstance(data, list):
        key_fields["earnings_count"] = len(data)
        if len(data) > 0 and isinstance(data[0], dict):
            quarters = [d.get("quarter") for d in data if d.get("quarter")]
            key_fields["quarters"] = quarters[:4]

    return key_fields


# =============================================================================
#                    SUMMARY GENERATORS
# =============================================================================


def generate_sec_summary(data: Any, key_fields: dict[str, Any]) -> str:
    """
    Generate human-readable summary for SEC filing data.

    Used by OffloadMiddleware when creating ContextRef objects.
    """
    if isinstance(data, list):
        count = key_fields.get("filing_count", len(data))
        types = key_fields.get("filing_types", [])
        ticker = key_fields.get("ticker", "")
        type_str = ", ".join(types[:3]) if types else "filings"
        if ticker:
            return f"{count} SEC {type_str} for {ticker}"
        return f"{count} SEC {type_str}"

    elif isinstance(data, dict):
        filing_type = key_fields.get("filing_type", "filing")
        ticker = key_fields.get("ticker", "")
        date = key_fields.get("filing_date", "")
        if ticker and date:
            return f"{ticker} {filing_type} ({date})"
        elif ticker:
            return f"{ticker} {filing_type}"
        return f"SEC {filing_type}"

    return "SEC filing data"


def generate_news_summary(data: Any, key_fields: dict[str, Any]) -> str:
    """
    Generate human-readable summary for news article data.

    Used by OffloadMiddleware when creating ContextRef objects.
    """
    if isinstance(data, list):
        count = key_fields.get("article_count", len(data))
        sources = key_fields.get("sources", [])
        date_range = key_fields.get("date_range", {})

        summary = f"{count} news articles"
        if sources:
            summary += f" from {', '.join(sources[:2])}"
        if date_range:
            summary += f" ({date_range.get('earliest', '')} to {date_range.get('latest', '')})"
        return summary

    elif isinstance(data, dict):
        headline = key_fields.get("headline") or key_fields.get("title", "")
        source = key_fields.get("source", "")
        if headline:
            truncated = headline[:50] + "..." if len(headline) > 50 else headline
            if source:
                return f'"{truncated}" - {source}'
            return f'"{truncated}"'
        return "News article"

    return "News data"


def generate_earnings_summary(data: Any, key_fields: dict[str, Any]) -> str:
    """
    Generate human-readable summary for earnings/transcript data.

    Used by OffloadMiddleware when creating ContextRef objects.
    """
    if isinstance(data, list):
        count = key_fields.get("earnings_count", len(data))
        quarters = key_fields.get("quarters", [])
        if quarters:
            return f"{count} earnings calls ({', '.join(quarters[:2])})"
        return f"{count} earnings calls"

    elif isinstance(data, dict):
        ticker = key_fields.get("ticker", "")
        quarter = key_fields.get("quarter", "")
        fiscal_year = key_fields.get("fiscal_year", "")

        if ticker and quarter:
            fy = f" FY{fiscal_year}" if fiscal_year else ""
            return f"{ticker} {quarter}{fy} earnings"
        elif ticker:
            return f"{ticker} earnings call"
        return "Earnings data"

    return "Earnings data"


# =============================================================================
#                    SUMMARIZER DOMAIN PROMPTS
# =============================================================================

# Map prompts for LangChain map-reduce summarization
# These are used by LangChainSummarizer.register_domain_prompts()

DOMAIN_PROMPTS = {
    "sec_filing": {
        "map": """You are a financial analyst summarizing SEC filings.
Extract the most important information from this section:

{text}

Focus on:
- Key financial metrics and changes
- Risk factors and material events
- Management discussion highlights
- Forward-looking statements

Provide a concise summary (3-5 sentences):""",
        "reduce": """You are a financial analyst creating an executive summary.
Combine these SEC filing summaries into a coherent overview:

{text}

Create a unified summary that captures:
- Most significant financial information
- Key risks and opportunities
- Strategic direction

Executive Summary:""",
    },
    "earnings": {
        "map": """You are analyzing an earnings call transcript section.
Extract key insights from:

{text}

Focus on:
- Financial performance highlights
- Forward guidance
- Strategic initiatives
- Management tone and confidence

Key points (3-5 bullets):""",
        "reduce": """You are creating an earnings call summary.
Synthesize these section summaries:

{text}

Provide a comprehensive earnings summary covering:
- Financial highlights
- Guidance and outlook
- Key strategic themes
- Notable Q&A points

Summary:""",
    },
    "news": {
        "map": """Summarize this news article for financial analysis:

{text}

Extract:
- Main event or announcement
- Impact on company/industry
- Key quotes or data points
- Market implications

Summary (2-3 sentences):""",
        "reduce": """Create a news briefing from these summaries:

{text}

Organize by theme and highlight:
- Most significant developments
- Market-moving events
- Emerging trends

News Briefing:""",
    },
    "transcripts": {
        "map": """You are summarizing a section of an earnings call transcript.
Extract the key information from:

{text}

Focus on:
- Specific metrics mentioned
- Management commentary
- Analyst questions and concerns
- Forward-looking statements

Section summary:""",
        "reduce": """Create a comprehensive transcript summary from these sections:

{text}

Provide:
- Executive overview
- Key financial takeaways
- Strategic themes
- Notable analyst concerns

Transcript Summary:""",
    },
    "pricing": {
        "map": """Analyze this pricing/valuation data section:

{text}

Extract:
- Key valuation metrics
- Price targets
- Comparable analysis points
- Market multiples

Analysis:""",
        "reduce": """Synthesize pricing analysis from these sections:

{text}

Provide unified analysis of:
- Valuation summary
- Key metrics
- Market positioning

Valuation Overview:""",
    },
}


# =============================================================================
#                    REGISTRATION FUNCTIONS
# =============================================================================


def register_offload_extractors(offload_middleware: Any) -> None:
    """
    Register all CMPT-specific extractors with OffloadMiddleware.

    Args:
        offload_middleware: OffloadMiddleware instance

    Usage:
        from cmpt.domain_config import register_offload_extractors
        from agentorchestrator.middleware.offload import OffloadMiddleware

        middleware = OffloadMiddleware(store=store)
        register_offload_extractors(middleware)
    """
    # Register extractors
    offload_middleware.register_extractor("sec", extract_sec_key_fields)
    offload_middleware.register_extractor("filing", extract_sec_key_fields)
    offload_middleware.register_extractor("news", extract_news_key_fields)
    offload_middleware.register_extractor("article", extract_news_key_fields)
    offload_middleware.register_extractor("earnings", extract_earnings_key_fields)
    offload_middleware.register_extractor("transcript", extract_earnings_key_fields)

    # Register generators
    offload_middleware.register_generator("sec", generate_sec_summary)
    offload_middleware.register_generator("filing", generate_sec_summary)
    offload_middleware.register_generator("news", generate_news_summary)
    offload_middleware.register_generator("article", generate_news_summary)
    offload_middleware.register_generator("earnings", generate_earnings_summary)
    offload_middleware.register_generator("transcript", generate_earnings_summary)


def register_summarizer_prompts(summarizer_class: Any) -> None:
    """
    Register all CMPT-specific domain prompts with LangChainSummarizer.

    Args:
        summarizer_class: LangChainSummarizer class (not instance)

    Usage:
        from cmpt.domain_config import register_summarizer_prompts
        from agentorchestrator.middleware.summarizer import LangChainSummarizer

        register_summarizer_prompts(LangChainSummarizer)
    """
    for domain, prompts in DOMAIN_PROMPTS.items():
        summarizer_class.register_domain_prompts(
            domain=domain,
            map_prompt=prompts["map"],
            reduce_prompt=prompts.get("reduce"),
        )


def register_cmpt_middleware(
    offload_middleware: Any = None,
    summarizer_class: Any = None,
) -> None:
    """
    Register all CMPT-specific middleware configuration.

    This is a convenience function that registers both offload extractors
    and summarizer prompts in one call.

    Args:
        offload_middleware: OffloadMiddleware instance (optional)
        summarizer_class: LangChainSummarizer class (optional)

    Usage:
        from cmpt.domain_config import register_cmpt_middleware
        from agentorchestrator.middleware.offload import OffloadMiddleware
        from agentorchestrator.middleware.summarizer import LangChainSummarizer

        middleware = OffloadMiddleware(store=store)
        register_cmpt_middleware(
            offload_middleware=middleware,
            summarizer_class=LangChainSummarizer,
        )
    """
    if offload_middleware is not None:
        register_offload_extractors(offload_middleware)

    if summarizer_class is not None:
        register_summarizer_prompts(summarizer_class)


# =============================================================================
#                    AGENT CONFIGURATION
# =============================================================================

# Default agent configurations for CMPT
# These can be registered with AgentsConfig.register()

CMPT_AGENTS = {
    "sec": {
        "description": "SEC filings agent - retrieves 10-K, 10-Q, 8-K filings",
        "default_url": "http://localhost:8001/sec",
        "timeout": 60,
        "retry_count": 3,
    },
    "news": {
        "description": "News agent - retrieves financial news and articles",
        "default_url": "http://localhost:8002/news",
        "timeout": 30,
        "retry_count": 2,
    },
    "earnings": {
        "description": "Earnings agent - retrieves earnings calls and transcripts",
        "default_url": "http://localhost:8003/earnings",
        "timeout": 45,
        "retry_count": 3,
    },
    "transcripts": {
        "description": "Transcripts agent - retrieves call transcripts",
        "default_url": "http://localhost:8004/transcripts",
        "timeout": 45,
        "retry_count": 3,
    },
    "pricing": {
        "description": "Pricing agent - retrieves valuation and pricing data",
        "default_url": "http://localhost:8005/pricing",
        "timeout": 30,
        "retry_count": 2,
    },
}


def register_cmpt_agents(agents_config: Any) -> None:
    """
    Register CMPT-specific agents with AgentsConfig.

    Agents are loaded in this priority order:
    1. AGENT_CONFIG JSON env var (already loaded by AgentsConfig.from_env())
    2. Individual AGENT_<NAME>_URL env vars
    3. Default fallback URLs from CMPT_AGENTS

    Args:
        agents_config: AgentsConfig instance

    Usage:
        from cmpt.domain_config import register_cmpt_agents
        from agentorchestrator.config import Config

        config = Config.from_env()
        register_cmpt_agents(config.agents)
    """
    # Import here to avoid circular imports
    from agentorchestrator.config import AgentConfig
    import os

    for name, agent_info in CMPT_AGENTS.items():
        # Skip if already loaded from AGENT_CONFIG JSON
        if agents_config.get(name) is not None:
            continue

        # Check for individual environment variable overrides
        env_url = os.environ.get(f"AGENT_{name.upper()}_URL")
        env_key = os.environ.get(f"AGENT_{name.upper()}_API_KEY")

        config = AgentConfig(
            name=name,
            url=env_url or agent_info["default_url"],
            api_key=env_key,
            timeout=agent_info.get("timeout", 30),
            retries=agent_info.get("retry_count", 3),
        )
        agents_config.register(name, config)


def get_agent_configs_from_env() -> list[dict[str, Any]]:
    """
    Load agent configurations from AGENT_CONFIG env var.

    Returns list of agent config dicts with keys:
        - name: Agent identifier (sec, news, earnings)
        - mcp_url: MCP server URL
        - mcp_tool: Tool name to call
        - mcp_bearer_token: Bearer token for auth
        - cache_enabled: Whether to cache responses
        - cache_seconds: Cache TTL
        - cache_size: Max cache entries

    Usage:
        from cmpt.domain_config import get_agent_configs_from_env

        agents = get_agent_configs_from_env()
        for agent in agents:
            print(f"{agent['name']}: {agent['mcp_url']}")
    """
    import json
    import os

    agent_config_json = os.environ.get("AGENT_CONFIG", "")
    if not agent_config_json:
        return []

    try:
        agents_list = json.loads(agent_config_json)
        if isinstance(agents_list, list):
            return agents_list
    except json.JSONDecodeError:
        pass

    return []


# =============================================================================
#                    CMPT TEST FIXTURES
# =============================================================================

# Sample data generators for CMPT-specific testing
# These were moved from agentorchestrator.testing.fixtures to keep AO generic


def sample_news_articles(count: int = 3, company: str = "Apple") -> list[dict]:
    """Generate sample news articles for CMPT testing."""
    from datetime import datetime

    return [
        {
            "title": f"{company} News Article {i+1}",
            "source": "Reuters" if i % 2 == 0 else "Bloomberg",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": f"This is a sample news article about {company}.",
            "sentiment": "positive" if i % 3 == 0 else "neutral",
            "url": f"https://example.com/news/{i+1}",
        }
        for i in range(count)
    ]


def sample_sec_filings(count: int = 2, ticker: str = "AAPL") -> list[dict]:
    """Generate sample SEC filings for CMPT testing."""
    filing_types = ["10-K", "10-Q", "8-K"]
    return [
        {
            "filing_type": filing_types[i % len(filing_types)],
            "ticker": ticker,
            "date": "2024-01-15",
            "summary": f"Sample {filing_types[i % len(filing_types)]} filing",
            "url": f"https://sec.gov/filing/{ticker}/{i+1}",
        }
        for i in range(count)
    ]


def sample_earnings_data(ticker: str = "AAPL") -> dict:
    """Generate sample earnings data for CMPT testing."""
    return {
        "ticker": ticker,
        "quarter": "Q1 2024",
        "eps_actual": 2.18,
        "eps_estimate": 2.10,
        "revenue_actual": 119500000000,
        "revenue_estimate": 118000000000,
        "guidance": "Positive outlook for FY2024",
        "call_date": "2024-02-01",
    }


def sample_financial_metrics(ticker: str = "AAPL") -> dict:
    """Generate sample financial metrics for CMPT testing."""
    return {
        "ticker": ticker,
        "market_cap": 3000000000000,
        "pe_ratio": 28.5,
        "dividend_yield": 0.5,
        "revenue_ttm": 385000000000,
        "net_income_ttm": 97000000000,
        "debt_to_equity": 1.8,
        "current_ratio": 1.0,
    }


def sample_cmpt_chain_request(
    company: str = "Apple Inc",
    ticker: str = "AAPL",
    **overrides,
) -> dict[str, Any]:
    """
    Create sample CMPT chain request data.

    Args:
        company: Company name
        ticker: Stock ticker
        **overrides: Override any default values

    Returns:
        Dict suitable for forge.launch(data=...)
    """
    from datetime import datetime

    data = {
        "company_name": company,
        "ticker": ticker,
        "user_query": "What are the key financial metrics?",
        "meeting_date": datetime.now().strftime("%Y-%m-%d"),
        "rbc_employee_id": "12345",
        "client_email": "client@example.com",
        "include_news": True,
        "include_sec": True,
        "include_earnings": True,
        "max_results": 10,
    }
    data.update(overrides)
    return data
