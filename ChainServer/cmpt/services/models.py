"""
AgentOrchestrator Service Models

Pydantic models for all CMPT chain services with validation.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════════════════
#                              ENUMS
# ═══════════════════════════════════════════════════════════════════════════════


class DataSource(str, Enum):
    """Available data sources for the CMPT chain"""

    SEC_FILING = "sec_filing"
    NEWS = "news"
    EARNINGS = "earnings"
    TRANSCRIPTS = "transcripts"
    RESEARCH = "research"


class Priority(str, Enum):
    """Priority levels for data sources"""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"


# ═══════════════════════════════════════════════════════════════════════════════
#                         CHAIN REQUEST/RESPONSE
# ═══════════════════════════════════════════════════════════════════════════════


class ChainRequest(BaseModel):
    """
    Unified request model for the CMPT chain server.

    Input comes from the calling application (calendar integration, UI),
    not from natural language parsing. Fields are passed as-is from:
    - Calendar invite → corporate_company_name, meeting_datetime
    - Calendar attendees → corporate_client_email, corporate_client_names
    - User session → rbc_employee_email

    User Overrides:
    Users can override any computed/extracted values by providing them in the
    `overrides` field. These take precedence over API-extracted values.
    """

    # From calendar invite
    corporate_company_name: str | None = None
    meeting_datetime: str | None = None  # "YYYY-MM-DD" or ISO format

    # From calendar attendees
    corporate_client_email: str | None = None
    corporate_client_names: str | None = None  # Comma-separated names

    # From user session
    rbc_employee_email: str | None = None

    # Options
    verbose: bool = False

    # ═══════════════════════════════════════════════════════════════════════════
    #                          USER OVERRIDES
    # ═══════════════════════════════════════════════════════════════════════════
    # Users can override computed/extracted values. These take precedence.
    overrides: "ChainRequestOverrides | None" = Field(
        None, description="User-provided overrides for computed values"
    )


class ChainRequestOverrides(BaseModel):
    """
    User-provided overrides for computed/extracted values.

    When these fields are set, they take precedence over values
    extracted from APIs (earnings calendar, company lookup, etc.).

    Usage:
        request = ChainRequest(
            corporate_company_name="Apple Inc",
            meeting_datetime="2025-02-15",
            overrides=ChainRequestOverrides(
                ticker="AAPL",
                fiscal_quarter="Q1",
                fiscal_year="2025",
                next_earnings_date="2025-01-30",
            )
        )
    """

    # Company info overrides
    ticker: str | None = Field(None, description="Override extracted ticker symbol")
    company_cik: str | None = Field(None, description="Override SEC CIK number")
    industry: str | None = Field(None, description="Override industry classification")
    sector: str | None = Field(None, description="Override business sector")

    # Temporal context overrides
    fiscal_quarter: str | None = Field(
        None, description="Override fiscal quarter (e.g., 'Q1', 'Q2', 'Q3', 'Q4')"
    )
    fiscal_year: str | None = Field(
        None, description="Override fiscal year (e.g., '2025', 'FY2025')"
    )
    next_earnings_date: str | None = Field(
        None, description="Override next earnings date (YYYY-MM-DD)"
    )

    # Lookback period overrides
    news_lookback_days: int | None = Field(
        None, ge=1, le=365, description="Override news lookback period (days)"
    )
    filing_quarters: int | None = Field(
        None, ge=1, le=20, description="Override SEC filing lookback (quarters)"
    )

    # Persona overrides
    rbc_persona_name: str | None = Field(None, description="Override RBC employee name")
    rbc_persona_role: str | None = Field(None, description="Override RBC employee role/title")
    client_persona_name: str | None = Field(None, description="Override client contact name")
    client_persona_role: str | None = Field(None, description="Override client contact role/title")

    # Data source overrides
    skip_earnings_calendar_api: bool = Field(
        False, description="Skip earnings calendar API call (use computed quarter)"
    )
    skip_company_lookup: bool = Field(
        False, description="Skip company lookup API call (use provided company name)"
    )

    class Config:
        extra = "allow"  # Allow additional custom overrides


# Update ChainRequest to use the forward reference
ChainRequest.model_rebuild()


class ChainResponse(BaseModel):
    """Unified response model for the CMPT chain server"""

    # Company info
    company_name: str | None = None
    ticker: str | None = None

    # Generated content
    financial_metrics: dict[str, Any] | None = None
    strategic_analysis: dict[str, Any] | None = None
    prepared_content: str | None = None

    # Agent results
    agent_results: dict[str, Any] | None = None

    # Validation
    validation_results: dict[str, Any] | None = None

    # Timing and status
    timing_ms: dict[str, float] | None = None
    success: bool = True
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
#                         CONTEXT BUILDER MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class CompanyInfo(BaseModel):
    """
    Extracted company information from corporate_client_firm_extractor.

    This is the result of looking up company details from the foundation service.
    """

    name: str = Field(..., description="Company name")
    ticker: str | None = Field(None, description="Stock ticker symbol", max_length=10)
    cik: str | None = Field(None, description="SEC CIK number")
    industry: str | None = Field(None, description="Industry classification")
    sector: str | None = Field(None, description="Business sector")
    market_cap: str | None = Field(None, description="Market capitalization category")
    country: str | None = Field(None, description="Country of incorporation")
    exchange: str | None = Field(None, description="Stock exchange")

    # Additional metadata
    company_id: str | None = Field(None, description="Internal company ID")
    match_score: float | None = Field(None, ge=0, le=1, description="Match confidence score")

    class Config:
        extra = "allow"  # Allow additional fields from API responses


class TemporalContext(BaseModel):
    """
    Temporal context from temporal_content_extractor (earnings calendar API).

    The old code gets this from Foundation DB /company_earnings_calendar endpoint,
    which returns fiscal_year and fiscal_period (quarter number like "1", "2", "3", "4").
    """

    # From earnings calendar API response
    event_dt: str | None = None  # Earnings event date "YYYY-MM-DD"
    fiscal_year: str | None = None  # "2025"
    fiscal_quarter: str | None = None  # "1", "2", "3", "4" (from fiscal_period)

    # Computed from meeting date if API unavailable
    meeting_date: str | None = None  # Meeting date "YYYY-MM-DD"

    # Earnings proximity (computed)
    days_to_earnings: int | None = None

    # Lookback config (from GRID config)
    news_lookback_days: int = 30
    filing_quarters: int = 8


class PersonaInfo(BaseModel):
    """
    Extracted persona information from RBC or corporate client extractors.

    Contains details about meeting participants.
    """

    # Basic info
    name: str = Field(..., description="Full name")
    first_name: str | None = Field(None, description="First name")
    last_name: str | None = Field(None, description="Last name")
    email: str | None = Field(None, description="Email address")

    # Role info
    role: str | None = Field(None, description="Job title/role")
    department: str | None = Field(None, description="Department")
    division: str | None = Field(None, description="Division")

    # Company info
    company: str | None = Field(None, description="Company name")
    company_id: str | None = Field(None, description="Company ID")

    # Internal flags
    is_internal: bool = Field(False, description="Whether this is an RBC employee")

    # Matching metadata
    match_score: float | None = Field(None, ge=0, le=1, description="Match confidence")
    source: str | None = Field(None, description="Data source (LDAP, ZoomInfo, etc.)")

    class Config:
        extra = "allow"


class ContextBuilderInput(BaseModel):
    """Input to the Context Builder service"""

    request: ChainRequest = Field(..., description="Original chain request")


class ContextBuilderOutput(BaseModel):
    """
    Output from the Context Builder service.

    Contains all extracted context needed for content prioritization.
    """

    # Company info
    company_info: CompanyInfo | None = Field(None, description="Extracted company information")
    company_name: str | None = Field(None, description="Resolved company name")
    ticker: str | None = Field(None, description="Resolved ticker symbol")

    # Temporal context
    temporal_context: TemporalContext | None = Field(None, description="Extracted temporal context")

    # Personas
    rbc_persona: PersonaInfo | None = Field(None, description="RBC employee persona")
    corporate_client_personas: list[PersonaInfo] = Field(
        default_factory=list, description="Corporate client personas"
    )

    # Raw data for debugging
    raw_firm_response: dict[str, Any] | None = Field(
        None, description="Raw response from firm extractor"
    )
    raw_temporal_response: dict[str, Any] | None = Field(
        None, description="Raw response from temporal extractor"
    )

    # Errors
    errors: dict[str, str] = Field(default_factory=dict, description="Errors by extractor name")

    # Timing
    timing_ms: dict[str, float] | None = Field(None, description="Timing for each extractor")


# ═══════════════════════════════════════════════════════════════════════════════
#                    CONTENT PRIORITIZATION MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class PrioritizedSource(BaseModel):
    """A prioritized data source with configuration"""

    source: DataSource = Field(..., description="Data source type")
    priority: Priority = Field(..., description="Priority level")
    enabled: bool = Field(True, description="Whether to query this source")

    # Source-specific config
    lookback_days: int | None = Field(None, description="Days to look back")
    lookback_quarters: int | None = Field(None, description="Quarters to look back")
    max_results: int | None = Field(None, description="Maximum results to retrieve")

    # Filtering
    include_types: list[str] | None = Field(
        None, description="Document types to include (e.g., ['10-K', '10-Q'])"
    )
    exclude_types: list[str] | None = Field(None, description="Document types to exclude")


class Subquery(BaseModel):
    """
    A subquery to be executed against a data agent.

    Generated by the subquery engine based on context and priorities.
    """

    agent: str = Field(..., description="Target agent name")
    query: str = Field(..., description="Query string")

    # Parameters
    params: dict[str, Any] = Field(default_factory=dict, description="Agent-specific parameters")

    # Metadata
    priority: Priority = Field(Priority.PRIMARY, description="Query priority")
    timeout_ms: int = Field(30000, ge=1000, le=300000, description="Query timeout")
    retry_count: int = Field(1, ge=0, le=5, description="Number of retries")


class ContentPrioritizationInput(BaseModel):
    """Input to the Content Prioritization service"""

    context: ContextBuilderOutput = Field(..., description="Output from context builder")


class ContentPrioritizationOutput(BaseModel):
    """
    Output from the Content Prioritization service.

    Contains prioritized sources and subqueries for agent execution.
    """

    # Prioritized sources
    prioritized_sources: list[PrioritizedSource] = Field(
        default_factory=list, description="Sources ordered by priority"
    )

    # Generated subqueries
    subqueries: list[Subquery] = Field(
        default_factory=list, description="Subqueries for each agent"
    )
    subqueries_by_agent: dict[str, list[Subquery]] = Field(
        default_factory=dict, description="Subqueries grouped by agent"
    )

    # Grid configuration used
    grid_config: dict[str, Any] | None = Field(None, description="Grid configuration applied")

    # Reasoning
    prioritization_reasoning: str | None = Field(
        None, description="Explanation of prioritization decisions"
    )

    # Timing
    timing_ms: dict[str, float] | None = Field(None, description="Timing for prioritization steps")


# ═══════════════════════════════════════════════════════════════════════════════
#                       RESPONSE BUILDER MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class AgentResult(BaseModel):
    """Result from a single data agent execution"""

    agent: str = Field(..., description="Agent name")
    success: bool = Field(..., description="Whether the query succeeded")

    # Data
    data: dict[str, Any] | None = Field(None, description="Retrieved data")
    items: list[dict[str, Any]] = Field(default_factory=list, description="List of retrieved items")
    item_count: int = Field(0, ge=0, description="Number of items retrieved")

    # Metadata
    query: str | None = Field(None, description="Query that was executed")
    source: str | None = Field(None, description="Upstream data source")
    duration_ms: float | None = Field(None, ge=0, description="Query duration")

    # Errors
    error: str | None = Field(None, description="Error message if failed")
    error_code: str | None = Field(None, description="Error code")


class ResponseBuilderInput(BaseModel):
    """Input to the Response Builder service"""

    context: ContextBuilderOutput = Field(..., description="Output from context builder")
    prioritization: ContentPrioritizationOutput = Field(
        ..., description="Output from content prioritization"
    )


class ResponseBuilderOutput(BaseModel):
    """
    Output from the Response Builder service.

    Contains agent results and the final generated response.
    """

    # Agent results
    agent_results: dict[str, AgentResult] = Field(
        default_factory=dict, description="Results from each agent"
    )

    # Aggregated data
    all_items: list[dict[str, Any]] = Field(
        default_factory=list, description="All retrieved items combined"
    )
    total_items: int = Field(0, ge=0, description="Total items retrieved")

    # Generated content
    financial_metrics: dict[str, Any] | None = Field(
        None, description="Extracted financial metrics"
    )
    strategic_analysis: dict[str, Any] | None = Field(
        None, description="Generated strategic analysis"
    )
    prepared_content: str | None = Field(None, description="Final prepared meeting content")

    # Parsed data from agents
    parsed_data_agent_chunks: dict[str, str] | None = Field(
        None, description="Parsed content from each agent"
    )

    # Validation
    validation_results: dict[str, Any] | None = Field(
        None, description="Validation results for financial metrics"
    )

    # Metadata
    agents_succeeded: int = Field(0, ge=0, description="Number of agents that succeeded")
    agents_failed: int = Field(0, ge=0, description="Number of agents that failed")
    company_name: str | None = Field(None, description="Company name used for analysis")

    # Cache info
    cached: dict[str, Any] | None = Field(None, description="Cache hit info per agent")

    # Errors
    errors: dict[str, str] = Field(default_factory=dict, description="Errors by agent name")

    # Timing
    timing_ms: dict[str, float] | None = Field(
        None, description="Timing for each agent and LLM call"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#                       LLM SCHEMA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class CitationDict(BaseModel):
    """Structured citation with source tracking and reasoning"""
    source_agent: list[str] = Field(
        description="List of data agents used. Valid values: 'SEC_agent', 'earnings_agent', 'news_agent'"
    )
    source_content: list[str] = Field(
        description="List of verbatim quotes from source chunks. DO NOT paraphrase."
    )
    reasoning: str = Field(
        description="Explanation of how you derived this metric."
    )


class MetricWithCitation(BaseModel):
    """A metric value with its citation"""
    value: float | str | dict | None = None
    citation: CitationDict | None = None


class FinancialMetricsResponse(BaseModel):
    """Structured response for financial metrics extraction"""

    # Revenue metrics
    current_annual_revenue: float | None = Field(None, description="Current annual revenue in billions USD")
    current_annual_revenue_citation: CitationDict | None = None
    current_annual_revenue_date: str | None = Field(None, description="Date of SEC filing (YYYY-MM-DD)")
    current_annual_revenue_yoy_change: float | None = Field(None, description="YoY percentage change in revenue")

    # Projected revenue
    estimated_annual_revenue_next_year: float | None = Field(None, description="Projected revenue for next FY in billions USD")
    estimated_annual_revenue_next_year_citation: CitationDict | None = None

    # EBITDA
    ebitda_margin: float | None = Field(None, description="EBITDA margin as percentage")
    ebitda_margin_citation: CitationDict | None = None
    ebitda_margin_yoy_change: float | None = Field(None, description="YoY change in EBITDA margin (percentage points)")

    # Stock metrics
    stock_price: float | None = Field(None, description="Most recent stock price in USD")
    stock_price_citation: CitationDict | None = None
    stock_price_daily_change: float | None = Field(None, description="Today's stock price change in USD")
    stock_price_daily_change_percent: float | None = Field(None, description="Today's stock price percentage change")
    stock_price_yoy_change: float | None = Field(None, description="YoY percentage change in stock price")

    # Market cap
    market_cap: float | None = Field(None, description="Market capitalization in billions USD")
    market_cap_citation: CitationDict | None = None
    market_cap_date: str | None = Field(None, description="Date of market cap calculation (YYYY-MM-DD)")

    # Trajectory
    revenue_growth_trajectory: dict[str, float | None] | None = Field(None, description="Quarterly revenue for last 7 quarters")
    revenue_growth_trajectory_citation: CitationDict | None = None


class StrategicAnalysisResponse(BaseModel):
    """Structured response for strategic analysis"""

    strength: list[str] = Field(
        default_factory=list,
        description="4-6 key competitive strengths from SWOT analysis"
    )
    weakness: list[str] = Field(
        default_factory=list,
        description="4-6 key vulnerabilities from SWOT analysis"
    )
    opportunity: list[str] = Field(
        default_factory=list,
        description="4-6 growth opportunities from SWOT analysis"
    )
    threat: list[str] = Field(
        default_factory=list,
        description="4-6 external threats from SWOT analysis"
    )

    investment_thesis: list[dict[str, list[str]]] = Field(
        default_factory=list,
        description="Investment thesis as list of dicts with subheading -> bullet points"
    )

    key_risk_highlights: list[str] = Field(
        default_factory=list,
        description="5-7 critical risks that could impact investment thesis"
    )

    strategic_opportunities: list[dict[str, list[str]]] = Field(
        default_factory=list,
        description="Strategic opportunities for company and RBC engagement"
    )

    recent_developments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Recent firm-level developments with category, header, date, description, source_url"
    )

    sources: list[str] = Field(
        default_factory=list,
        description="List of all sources cited in the analysis"
    )

    news_summary: list[dict[str, list[str]]] = Field(
        default_factory=list,
        description="Summary of recent news organized by theme"
    )

    key_highlights: list[dict[str, list[str]]] = Field(
        default_factory=list,
        description="Key highlights from latest quarterly earnings"
    )
