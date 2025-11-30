# FlowForge CMPT Chain - Complete Flow Guide

This guide explains the complete flow of the Client Meeting Prep (CMPT) chain,
including all files involved, inputs, outputs, and execution flow.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Chain Execution Flow](#chain-execution-flow)
3. [Stage 1: Context Builder](#stage-1-context-builder)
4. [Stage 2: Content Prioritization](#stage-2-content-prioritization)
5. [Stage 3: Response Builder](#stage-3-response-builder)
6. [Summarization Strategy](#summarization-strategy)
7. [Production Features](#production-features)
8. [File Reference](#file-reference)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CMPT Chain Flow                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   INPUT                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  ChainRequest                                                        │  │
│   │  ├─ corporate_company_name: "Apple Inc"                             │  │
│   │  ├─ meeting_datetime: "2025-01-15T10:00:00Z"                        │  │
│   │  ├─ rbc_employee_email: "john.doe@rbc.com"                          │  │
│   │  └─ corporate_client_email: "jane.smith@apple.com"                  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  STAGE 1: Context Builder                                           │  │
│   │  File: flowforge/services/context_builder.py                        │  │
│   │  ─────────────────────────────────────────────────────────────────  │  │
│   │  Extractors:                                                         │  │
│   │  ├─ corporate_client_firm_extractor() → CompanyInfo                 │  │
│   │  ├─ temporal_content_extractor() → TemporalContext                  │  │
│   │  ├─ rbc_persona_extractor() → PersonaInfo                           │  │
│   │  └─ corporate_client_persona_extractor() → List[PersonaInfo]        │  │
│   │                                                                      │  │
│   │  Output: ContextBuilderOutput                                        │  │
│   │  ├─ company_info: {name, ticker, industry, sector, market_cap}      │  │
│   │  ├─ temporal_context: {current_quarter, fiscal_year, days_to_earn}  │  │
│   │  ├─ rbc_persona: {name, email, role, department}                    │  │
│   │  └─ corporate_client_personas: [{name, email, role, company}]       │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  STAGE 2: Content Prioritization                                    │  │
│   │  File: flowforge/services/content_prioritization.py                 │  │
│   │  ─────────────────────────────────────────────────────────────────  │  │
│   │  Components:                                                         │  │
│   │  ├─ temporal_source_prioritizer() → prioritized sources by earnings │  │
│   │  ├─ subquery_engine() → generate queries for each agent             │  │
│   │  └─ grid_config → lookback periods & limits                         │  │
│   │                                                                      │  │
│   │  Prioritization Logic:                                               │  │
│   │  ├─ Near Earnings (≤2 weeks): SEC_FILING + EARNINGS = PRIMARY       │  │
│   │  ├─ Large Cap: NEWS = PRIMARY                                       │  │
│   │  └─ Otherwise: NEWS = PRIMARY, others SECONDARY                     │  │
│   │                                                                      │  │
│   │  Output: ContentPrioritizationOutput                                 │  │
│   │  ├─ prioritized_sources: [{source, priority, lookback, max_results}]│  │
│   │  ├─ subqueries: [{agent, query, params, priority, timeout}]         │  │
│   │  └─ prioritization_reasoning: "explanation of decisions..."         │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  STAGE 3: Response Builder                                          │  │
│   │  File: flowforge/services/response_builder.py                       │  │
│   │  ─────────────────────────────────────────────────────────────────  │  │
│   │  Components:                                                         │  │
│   │  ├─ _execute_agents() → parallel agent execution                    │  │
│   │  ├─ _extract_financial_metrics() → EPS, revenue, beat/miss          │  │
│   │  ├─ _generate_strategic_analysis() → sentiment, themes, risks       │  │
│   │  └─ _build_prepared_content() → final markdown output               │  │
│   │                                                                      │  │
│   │  Agents Executed (parallel by priority):                             │  │
│   │  ├─ PRIMARY: news, sec_filing (if near earnings)                    │  │
│   │  └─ SECONDARY: earnings, transcripts                                │  │
│   │                                                                      │  │
│   │  Output: ResponseBuilderOutput                                       │  │
│   │  ├─ agent_results: {news: {...}, sec_filing: {...}, ...}            │  │
│   │  ├─ financial_metrics: {eps_actual, eps_beat, revenue, ...}         │  │
│   │  ├─ strategic_analysis: {sentiment, themes, risks, opportunities}   │  │
│   │  └─ prepared_content: "# Meeting Prep: Apple Inc\n..."              │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│   OUTPUT                                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  ChainResponse                                                       │  │
│   │  ├─ success: true                                                   │  │
│   │  ├─ context_builder: {...stage 1 output...}                         │  │
│   │  ├─ content_prioritization: {...stage 2 output...}                  │  │
│   │  ├─ response_builder: {...stage 3 output...}                        │  │
│   │  └─ timings: {context_builder: 0.29, content_prioritization: 0.17}  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Chain Execution Flow

### Where Does the Input Come From?

The `ChainRequest` inputs come from **the calling application/UI**, not from LLM extraction.
In the current design:

1. **User provides structured input** - The frontend/calendar integration provides:
   - `corporate_company_name` - From calendar invite or user selection
   - `meeting_datetime` - From calendar event
   - `rbc_employee_email` - From logged-in user session
   - `corporate_client_email` - From calendar attendees

2. **No NLU/prompt parsing** - This chain doesn't parse natural language questions.
   The user isn't asking "Who am I meeting with?" - they're triggering prep for a specific meeting.

3. **Integration points** (from old code):
   - Calendar integration populates meeting details
   - Active Directory/LDAP provides RBC employee info
   - ZoomInfo lookup uses client email/name

```
┌─────────────────────────────────────────────────────────────────┐
│                    Input Sources                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Calendar System (Outlook, etc.)                                │
│  ├─ meeting_datetime ────────────────────┐                      │
│  ├─ corporate_company_name (from invite) ─┼──▶ ChainRequest     │
│  └─ corporate_client_email (attendees) ───┘        │            │
│                                                    │            │
│  User Session                                      │            │
│  └─ rbc_employee_email ────────────────────────────┘            │
│                                                                 │
│  Manual Override (optional)                                     │
│  └─ User can edit/specify any field ───────────────────────────▶│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Entry Point

```python
# File: flowforge/chains/cmpt.py

from flowforge.chains import CMPTChain

chain = CMPTChain()

# Validate chain definition
chain.check()

# Visualize DAG
chain.graph("ascii")

# Execute chain - inputs typically come from calendar/session
result = await chain.run(
    corporate_company_name="Apple Inc",           # From calendar invite
    meeting_datetime="2025-01-15T10:00:00Z",      # From calendar event
    rbc_employee_email="john.doe@rbc.com",        # From user session
    corporate_client_email="jane.smith@apple.com", # From calendar attendees
)

# Access results
print(result.context_builder)           # Stage 1 output
print(result.content_prioritization)    # Stage 2 output
print(result.response_builder)          # Stage 3 output
print(result.response_builder['prepared_content'])  # Final output
```

### DAG Execution Order

```
[Group 1 - Parallel]     [Group 2 - Parallel]     [Group 3 - Parallel]
┌─────────────────┐      ┌────────────────────┐   ┌─────────────────┐
│ context_builder │ ───▶ │content_prioritiz.  │──▶│ response_builder│
└─────────────────┘      └────────────────────┘   └─────────────────┘
     ~0.3ms                    ~0.2ms                   ~0.2ms
```

---

## Stage 1: Context Builder

**File:** `flowforge/services/context_builder.py`
**Models:** `flowforge/services/models.py`

### What It Does

The Context Builder takes the raw input (company name, emails, date) and **enriches it**
by calling external services. It doesn't extract info from prompts - it looks up info from:

- **Foundation DB** - Company metadata (ticker, industry, market cap)
- **Earnings Calendar API** - Upcoming/recent earnings dates
- **LDAP/Active Directory** - RBC employee details
- **ZoomInfo** - External client details

---

### Old Approach (from `requirements_and_old_code.MD`)

**File:** `src/services/context_builder_service.py`

```python
class ContextBuilderService:
    HTTP_TIMEOUT = 20.0  # 20 seconds

    @staticmethod
    async def corporate_client_firm_extractor(company_name: str, ticker_symbol: str) -> tuple:
        """POST to Foundation DB /find_company_matches"""
        url = os.environ.get('FOUNDATION_COMPANY_MATCHES')
        async with httpx.AsyncClient(verify=False, timeout=HTTP_TIMEOUT) as client:
            response = await client.post(url, json={"company_name": company_name})
            return response.json(), None

    @staticmethod
    async def temporal_content_extractor(company_name: str, ticker_symbol: str) -> tuple:
        """POST to Foundation DB /company_earnings_calendar"""
        url = os.environ.get('FOUNDATION_EARNING_CALENDAR_URL')
        payload = {"company_name": company_name, "top_n": GRID.get("earnings_proximity_weeks")}
        async with httpx.AsyncClient(verify=False, timeout=HTTP_TIMEOUT) as client:
            response = await client.post(url, json=payload)
            return response.json(), None

    @staticmethod
    async def rbc_persona_extractor(email: str) -> Dict[str, Any]:
        """LDAP lookup using LDAPService"""
        ldap_service = LDAPService(LDAPEmailStrategy())
        return ldap_service.lookup([email])[0]

    @staticmethod
    async def corporate_client_persona_extractor(email: str, names: str, company_name: str):
        """ZoomInfo lookup with company ranking"""
        zoom_service = ZoomInfoService()
        profiles = zoom_service.get_user_details_from_zoominfo(email=email)
        # Rank by company similarity
        return ContextBuilderService.rank_profiles_by_company(profiles, company_name)

    @staticmethod
    async def execute(request: ChainServerRequest) -> ContextBuilderOutput:
        """Execute full pipeline with real HTTP calls"""
        # All extractors run sequentially with timing
        corporate_client_firm_response, _ = await corporate_client_firm_extractor(...)
        temporal_content_response, _ = await temporal_content_extractor(...)
        rbc_persona = await rbc_persona_extractor(...)
        corporate_client_persona = await corporate_client_persona_extractor(...)
        return ContextBuilderOutput(...)
```

**Key characteristics:**
- Real HTTP calls to Foundation DB, LDAP, ZoomInfo
- `httpx.AsyncClient` with 20s timeout
- Returns `(result, error)` tuples
- `rank_profiles_by_company()` uses `SequenceMatcher` for fuzzy matching

---

### New Approach (FlowForge)

**File:** `flowforge/services/context_builder.py`

```python
class ContextBuilderService:
    async def execute(self, request: ChainRequest) -> ContextBuilderOutput:
        """Execute context building with parallel extractors"""
        # Run extractors in parallel where possible
        tasks = [
            self._extract_company_info(request.corporate_company_name),
            self._extract_temporal_context(request.corporate_company_name, request.meeting_datetime),
            self._extract_rbc_persona(request.rbc_employee_email),
            self._extract_client_personas(request.corporate_client_email, request.corporate_client_names),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return ContextBuilderOutput(...)

    async def _extract_company_info(self, company_name: str) -> CompanyInfo:
        """TODO: Replace with real Foundation DB call"""
        return self._get_mock_company_info(company_name)

    async def _extract_temporal_context(self, company_name: str, meeting_date: str) -> TemporalContext:
        """TODO: Replace with real earnings calendar API call"""
        return self._get_mock_temporal_context(meeting_date)
```

**Key differences:**
| Aspect | Old | New |
|--------|-----|-----|
| HTTP calls | Real (httpx) | Mock (TODO: implement) |
| Execution | Sequential | Parallel with `asyncio.gather` |
| Error handling | `(result, error)` tuples | Exceptions |
| Output model | Dict-based `ContextBuilderOutput` | Pydantic `ContextBuilderOutput` |

---

### Input

```python
ChainRequest(
    corporate_company_name="Apple Inc",        # From calendar invite
    meeting_datetime="2025-01-15T10:00:00Z",   # From calendar event
    rbc_employee_email="john.doe@rbc.com",     # From user session
    corporate_client_email="jane.smith@apple.com",  # From calendar attendees
)
```

### Extractors

| Extractor | External Service | Old Code | New Code |
|-----------|------------------|----------|----------|
| `corporate_client_firm_extractor()` | Foundation DB `/find_company_matches` | Real HTTP | Mock |
| `temporal_content_extractor()` | Foundation DB `/company_earnings_calendar` | Real HTTP | Mock |
| `rbc_persona_extractor()` | LDAP/Active Directory | Real LDAP | Mock |
| `corporate_client_persona_extractor()` | ZoomInfo API | Real HTTP | Mock |

### Output

```python
ContextBuilderOutput(
    company_info=CompanyInfo(
        name="Apple Inc",
        ticker="APPL",
        industry="Technology",
        sector="Information Technology",
        market_cap="Large Cap",
    ),
    temporal_context=TemporalContext(
        # From earnings calendar API (Foundation DB)
        event_dt="2025-01-25",          # Next earnings date
        fiscal_year="2025",             # From API
        fiscal_quarter="1",             # "1", "2", "3", or "4" (from fiscal_period)
        meeting_date="2025-01-15",      # From request
        days_to_earnings=10,            # Computed
        news_lookback_days=30,
    ),
    rbc_persona=PersonaInfo(
        name="John Doe",
        email="john.doe@rbc.com",
        role="Investment Banker",
        is_internal=True,
    ),
    corporate_client_personas=[
        PersonaInfo(
            name="Jane Smith",
            email="jane.smith@apple.com",
            role="CFO",
            company="Apple Inc",
        )
    ],
    timing_ms={"firm_extractor": 0.05, "temporal": 0.02, "total": 0.29},
)
```

### Temporal Context Fallback

If the earnings calendar API is unavailable, fiscal quarter is computed from meeting date:

```python
# From old code (content_prioritization_service.py):
if temporal_content_response:
    event_dt = temporal_content_response["event_dt"]
    fiscal_year = temporal_content_response.get("fiscal_year")
    fiscal_quarter = temporal_content_response.get("fiscal_period")
else:
    # Fallback: compute from meeting date
    event_dt = meeting_date
    fiscal_year = str(int(meeting_date[:4]))
    month = int(meeting_date[5:7])
    fiscal_quarter = str((month - 1) // 3 + 1)  # 1, 2, 3, or 4
```

---

## Stage 2: Content Prioritization

**File:** `flowforge/services/content_prioritization.py`
**Models:** `flowforge/services/models.py`

### What It Does

This stage decides **which data sources to query** and **what queries to send** based on:
- How close we are to earnings (temporal context from Stage 1)
- Company size/type (market cap from Stage 1)

---

### Old Approach (from `requirements_and_old_code.MD`)

**Files:**
- `src/services/content_prioritization_service.py`
- `src/services/static_subquery_engine.py`

```python
class ContentPrioritizationService:
    @staticmethod
    async def temporal_source_prioritizer(company_type: str, meeting_date: str, max_earnings_event_date: str):
        """Determine source priorities based on temporal context"""
        # Rule-based prioritization
        if company_type == "PUB" and abs((max_earnings_event_date - meeting_date).days) <= window:
            return {"earnings": "PRIMARY", "sec": "PRIMARY", "news": "SECONDARY"}
        return {"earnings": "SECONDARY", "sec": "SECONDARY", "news": "PRIMARY"}

    @staticmethod
    async def subquery_engine(company_name: str, fiscal_year: str, fiscal_quarter: str) -> tuple:
        """Generate subqueries using StaticSubqueryEngine"""
        return StaticSubqueryEngine.get_subquery_arguments(company_name, fiscal_year, fiscal_quarter)


class StaticSubqueryEngine:
    @staticmethod
    def get_SEC_agent_query_argument(company_name) -> list:
        return [
            {
                "reporting_entity": company_name,
                "search_queries": ["consolidated statements of operations", "total revenue"],
                "keywords": ["net sales", "total revenue", "quarterly revenue"],
                "get_latest": 8,
            },
            {
                "reporting_entity": company_name,
                "search_queries": ["consolidated balance sheets", "stockholders equity"],
                "keywords": ["outstanding shares", "common stock"],
                "get_latest": 1,
            }
        ]

    @staticmethod
    def get_earnings_agent_query_argument(company_name: str, fiscal_year: str, fiscal_quarter: str):
        return [{
            "query": f"Give me the earnings transcript for {company_name} "
                     f"for fiscal year: {fiscal_year} and quarter: {fiscal_quarter}."
        }]

    @staticmethod
    def get_news_agent_query_argument(company_name: str) -> list:
        end_date = datetime.now().strftime('%Y-%m-%d')
        one_month_ago = (datetime.now() - timedelta(days=31)).strftime('%Y-%m-%d')
        return [
            {
                "search_query": f"{company_name} executive leadership changes appointments CEO CFO",
                "topics": ["executive", "CEO", "CFO", "leadership"],
                "absolute_date_range": {"start_date": one_month_ago, "end_date": end_date}
            },
            {
                "search_query": f"{company_name} mergers acquisitions M&A strategic transactions",
                "topics": ["merger", "acquisition", "M&A", "deal"],
                "absolute_date_range": {"start_date": one_month_ago, "end_date": end_date}
            },
            {
                "search_query": f"{company_name} regulatory issues lawsuit litigation",
                "topics": ["regulatory", "lawsuit", "litigation"],
                "absolute_date_range": {"start_date": one_month_ago, "end_date": end_date}
            },
            # ... more topic-specific queries
        ]
```

**Key characteristics:**
- `StaticSubqueryEngine` with hardcoded query templates
- Specific search queries per topic (executive changes, M&A, regulatory, etc.)
- Date ranges computed dynamically (`one_month_ago`, `one_year_ago`)
- SEC queries include specific keywords for financial statement extraction

---

### New Approach (FlowForge)

**File:** `flowforge/services/content_prioritization.py`

```python
class ContentPrioritizationService:
    def __init__(self, grid_config: Optional[Dict] = None):
        self.grid_config = grid_config or DEFAULT_GRID_CONFIG

    async def execute(self, context: ContextBuilderOutput) -> ContentPrioritizationOutput:
        # Step 1: Prioritize sources based on temporal context
        prioritized_sources = self._prioritize_sources(context)

        # Step 2: Generate subqueries for each enabled source
        subqueries = self._generate_subqueries(context, prioritized_sources)

        return ContentPrioritizationOutput(
            prioritized_sources=prioritized_sources,
            subqueries=subqueries,
            subqueries_by_agent={...},
        )

    def _prioritize_sources(self, context: ContextBuilderOutput) -> List[PrioritizedSource]:
        """Prioritize based on earnings proximity and market cap"""
        near_earnings = context.temporal_context.days_to_earnings <= 14
        # SEC/Earnings PRIMARY if near earnings, else SECONDARY
        # News priority based on market cap
        ...

    def _generate_subqueries(self, context, sources) -> List[Subquery]:
        """Generate Subquery objects for each source"""
        for source in sources:
            if source.source == DataSource.SEC_FILING:
                subqueries.append(Subquery(
                    agent="sec_filing",
                    query=company_name,
                    params={"ticker": ticker, "quarters": 8, "types": ["10-K", "10-Q"]},
                ))
            elif source.source == DataSource.NEWS:
                subqueries.append(Subquery(
                    agent="news",
                    query=company_name,
                    params={"days": 30, "max_results": 50},
                ))
        ...
```

**Key differences:**
| Aspect | Old | New |
|--------|-----|-----|
| Subquery generation | `StaticSubqueryEngine` with hardcoded templates | Generic `Subquery` model with params |
| Query specificity | Topic-specific queries (6+ per agent) | Single query per agent with params |
| Date handling | Computed in subquery engine | Passed as lookback_days param |
| SEC queries | Specific keywords for financial extraction | Generic ticker + quarters |
| Output | Dict with tool names as keys | `List[Subquery]` + `subqueries_by_agent` |

**TODO for production:** Port the topic-specific query templates from `StaticSubqueryEngine`

---

### Input

```python
ContentPrioritizationInput(
    context=context_builder_output  # Enriched company/temporal info from Stage 1
)
```

### Prioritization Logic

```python
# Grid Configuration (default)
DEFAULT_GRID_CONFIG = {
    "earnings_proximity_weeks": 2,
    "news_lookback_days": {
        "large_cap": 30,
        "mid_cap": 60,
        "small_cap": 90,
    },
    "max_news_results": 50,
    "max_filing_results": 20,
    "include_filing_types": ["10-K", "10-Q", "8-K"],
}
```

**Decision Tree:**

```
                    ┌─────────────────────┐
                    │ Days to Earnings?   │
                    └─────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
      ≤ 14 days        Unknown/None        > 14 days
            │                 │                 │
            ▼                 ▼                 ▼
   ┌─────────────────────────────────────────────────┐
   │ SEC_FILING: PRIMARY   │ SEC_FILING: SECONDARY   │
   │ EARNINGS: PRIMARY     │ EARNINGS: SECONDARY     │
   └─────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │ Market Cap?         │
                    └─────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
       Large Cap          Mid Cap          Small Cap
            │                 │                 │
            ▼                 ▼                 ▼
   NEWS: PRIMARY      NEWS: SECONDARY   NEWS: SECONDARY
   lookback: 30d      lookback: 60d     lookback: 90d
```

### Output

```python
ContentPrioritizationOutput(
    prioritized_sources=[
        PrioritizedSource(
            source=DataSource.NEWS,
            priority=Priority.PRIMARY,
            lookback_days=30,
            max_results=50,
        ),
        PrioritizedSource(
            source=DataSource.SEC_FILING,
            priority=Priority.SECONDARY,
            lookback_quarters=8,
            include_types=["10-K", "10-Q", "8-K"],
        ),
        PrioritizedSource(
            source=DataSource.EARNINGS,
            priority=Priority.SECONDARY,
            lookback_quarters=4,
        ),
        PrioritizedSource(
            source=DataSource.TRANSCRIPTS,
            priority=Priority.SECONDARY,
            lookback_quarters=4,
        ),
    ],
    subqueries=[
        Subquery(agent="news", query="Apple Inc", params={...}, priority=Priority.PRIMARY),
        Subquery(agent="sec_filing", query="Apple Inc", params={...}, priority=Priority.SECONDARY),
        Subquery(agent="earnings", query="Apple Inc", params={...}, priority=Priority.SECONDARY),
        Subquery(agent="transcripts", query="Apple Inc", params={...}, priority=Priority.SECONDARY),
    ],
    prioritization_reasoning="""
    Prioritization for Apple Inc:
    - Earnings proximity unknown: Using default prioritization
    - Market cap: Large Cap
    - Primary sources: news
    """,
)
```

---

## Stage 3: Response Builder

**File:** `flowforge/services/response_builder.py`
**Models:** `flowforge/services/models.py`

### What It Does

This stage executes subqueries against data agents (MCP servers), parses responses,
and generates the final financial metrics and strategic analysis using LLM.

---

### Old Approach (from `requirements_and_old_code.MD`)

**File:** `src/services/response_builder_and_generator.py`

```python
class ResponseBuilderAndGenerator:

    @staticmethod
    async def execute_subqueries_on_data_agents(subqueries_by_agent: dict):
        """Execute subqueries via MCP sessions - one session per agent"""
        data_agent_chunks = {
            ToolName.NEWS_TOOL.value: [],
            ToolName.EARNINGS_TOOL.value: [],
            ToolName.SEC_TOOL.value: []
        }

        for agent_name, subqueries in subqueries_by_agent.items():
            # Get MCP config from env vars
            bearer_token = os.getenv(f"{agent_name}_AGENT_MCP_BEARER_TOKEN")
            server_url = os.getenv(f"{agent_name}_AGENT_MCP_URL")
            tool_name = os.getenv(f"{agent_name}_AGENT_MCP_TOOL")

            # Create one MCP session per agent, reuse for all subqueries
            async with streamablehttp_client(server_url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    for subquery in subqueries:
                        chunks = await session.call_tool(name=tool_name, arguments=subquery)
                        data_agent_chunks[agent_name].extend(chunks.model_dump()["content"])

        return data_agent_chunks, errors

    @staticmethod
    async def context_parser(data_agent_chunks: Dict) -> tuple:
        """Parse raw MCP responses into structured chunks"""
        for agent, chunks in data_agent_chunks.items():
            if agent == ToolName.EARNINGS_TOOL.value:
                # Parse earnings transcript format with regex
                chunks = await parse_earnings_agent_response(text_field)

    @staticmethod
    async def prompt_builder(parsed_data_agent_chunks, company_name, ...):
        """Build prompts for LLM calls"""
        financial_prompt = FINANCIAL_METRICS_PROMPT.format(
            EARNINGS_AGENT_CONTENT=parsed_data_agent_chunks["earnings"],
            SEC_AGENT_CONTENT=parsed_data_agent_chunks["sec"],
            NEWS_AGENT_CONTENT=parsed_data_agent_chunks["news"],
            COMPANY_NAME=company_name
        )
        # Sanitize for guardrails
        strategic_prompt = sanitize_prompt_for_guardrails(strategic_prompt)
        return financial_prompt, strategic_prompt

    @staticmethod
    async def response_builder(financial_prompt, strategic_prompt, ...):
        """Execute parallel LLM calls for metrics and analysis"""
        return await asyncio.gather(
            get_structured_response(financial_prompt, FinancialMetricsResponse),
            get_structured_response(strategic_prompt, StrategicAnalysisResponse),
        )

    @staticmethod
    async def execute(context_builder_output, content_prioritization_output):
        """Full pipeline: subqueries → parse → prompt → LLM → validate"""
        # Step 1: Execute subqueries on MCP agents
        data_agent_chunks, _ = await execute_subqueries_on_data_agents(...)

        # Step 2: Parse agent responses
        parsed_chunks, _ = await context_parser(data_agent_chunks)

        # Step 3: Build prompts
        financial_prompt, strategic_prompt = await prompt_builder(...)

        # Step 4: Call LLM with structured output
        (financial_result, _), (strategic_result, _) = await response_builder(...)

        # Step 5: Validate (optional)
        validation_results = await validate_extraction_results(...)

        return ResponseBuilderOutput(...)
```

**Key characteristics:**
- Real MCP client connections (`ClientSession`, `streamablehttp_client`)
- One MCP session per agent, reused for all subqueries
- Complex regex parsing for earnings transcripts
- `sanitize_prompt_for_guardrails()` to avoid false positives
- Parallel LLM calls via `asyncio.gather`
- Pydantic structured output (`FinancialMetricsResponse`, `StrategicAnalysisResponse`)

---

### New Approach (FlowForge)

**File:** `flowforge/services/response_builder.py`

```python
class ResponseBuilderService:
    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, context, prioritization) -> ResponseBuilderOutput:
        # Step 1: Group subqueries by priority
        primary = [sq for sq in prioritization.subqueries if sq.priority == Priority.PRIMARY]
        secondary = [sq for sq in prioritization.subqueries if sq.priority == Priority.SECONDARY]

        # Step 2: Execute PRIMARY first, then SECONDARY
        primary_results = await self._execute_subqueries(primary)
        secondary_results = await self._execute_subqueries(secondary)
        all_results = primary_results + secondary_results

        # Step 3: Post-processing (mock for now)
        metrics = self._extract_financial_metrics(all_results)
        analysis = self._generate_strategic_analysis(all_results)
        content = self._build_prepared_content(metrics, analysis)

        return ResponseBuilderOutput(...)

    async def _execute_subqueries(self, subqueries: List[Subquery]) -> List[AgentResult]:
        """Execute subqueries in parallel with semaphore"""
        tasks = [self._execute_single_agent(sq) for sq in subqueries]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_single_agent(self, subquery: Subquery) -> AgentResult:
        """Execute single subquery - TODO: implement real MCP calls"""
        async with self.semaphore:
            # Mock implementation
            return self._get_mock_agent_data(subquery.agent, subquery.query)
```

**Key differences:**
| Aspect | Old | New |
|--------|-----|-----|
| MCP calls | Real (`ClientSession.call_tool`) | Mock (TODO: implement) |
| Agent execution | Sequential per agent | Parallel with semaphore |
| Priority handling | Not explicit | PRIMARY → SECONDARY groups |
| Response parsing | Complex regex | Simple (delegated to agents) |
| LLM calls | Real with structured output | Mock extraction methods |
| Prompt building | Template-based with sanitization | Not yet implemented |

**TODO for production:**
1. Implement real MCP client calls in `_execute_single_agent()`
2. Port `parse_earnings_agent_response()` regex parsing
3. Port `prompt_builder()` with template formatting
4. Port `sanitize_prompt_for_guardrails()`
5. Implement real LLM calls with structured output

---

### Input

```python
ResponseBuilderInput(
    context=context_builder_output,       # From Stage 1
    prioritization=prioritization_output, # From Stage 2
)
```

### Agent Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Execution Order                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Priority Groups (executed sequentially):                       │
│                                                                 │
│  ┌─ PRIMARY ────────────────────────────────────────────────┐  │
│  │  Executed in parallel with semaphore (max 5 concurrent)  │  │
│  │  ┌──────────┐                                            │  │
│  │  │  news    │ ─────────────────────────────────────────▶ │  │
│  │  └──────────┘                                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           │                                     │
│                           ▼                                     │
│  ┌─ SECONDARY ──────────────────────────────────────────────┐  │
│  │  Executed in parallel after PRIMARY completes            │  │
│  │  ┌────────────┐  ┌──────────┐  ┌─────────────┐          │  │
│  │  │ sec_filing │  │ earnings │  │ transcripts │          │  │
│  │  └────────────┘  └──────────┘  └─────────────┘          │  │
│  │        │              │              │                   │  │
│  │        └──────────────┼──────────────┘                   │  │
│  │                       ▼                                  │  │
│  │              All execute in parallel                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           │                                     │
│                           ▼                                     │
│  ┌─ TERTIARY ───────────────────────────────────────────────┐  │
│  │  (Currently unused - would execute last)                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Post-Processing Pipeline

```
Agent Results
     │
     ▼
┌─────────────────────────────────────────┐
│ _extract_financial_metrics()            │
│ ─────────────────────────────────────── │
│ Input: earnings agent results           │
│ Output: {                               │
│   eps_actual: 1.25,                     │
│   eps_beat: true,                       │
│   revenue_actual: "25.5B",              │
│ }                                       │
│                                         │
│ NOTE: In production, use LLM here       │
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│ _generate_strategic_analysis()          │
│ ─────────────────────────────────────── │
│ Input: news + other agent results       │
│ Output: {                               │
│   market_sentiment: "positive",         │
│   key_themes: [...],                    │
│   risks: [...],                         │
│   opportunities: [...],                 │
│ }                                       │
│                                         │
│ NOTE: In production, use LLM here       │
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│ _build_prepared_content()               │
│ ─────────────────────────────────────── │
│ Input: metrics + analysis               │
│ Output: Markdown formatted string       │
└─────────────────────────────────────────┘
```

### Output

```python
ResponseBuilderOutput(
    agent_results={
        "news": AgentResult(success=True, items=[...], item_count=2),
        "sec_filing": AgentResult(success=True, items=[...], item_count=2),
        "earnings": AgentResult(success=True, items=[...], item_count=1),
        "transcripts": AgentResult(success=True, items=[...], item_count=1),
    },
    total_items=6,
    agents_succeeded=4,
    agents_failed=0,
    financial_metrics={
        "latest_quarter": "Q3 2024",
        "eps_beat": True,
        "eps_actual": 1.25,
        "revenue_actual": "25.5B",
    },
    strategic_analysis={
        "market_sentiment": "positive",
        "key_themes": ["earnings performance", "product innovation"],
        "risks": ["market competition", "regulatory changes"],
        "opportunities": ["market expansion", "new product launches"],
    },
    prepared_content="""
# Meeting Prep: Apple Inc

## Financial Highlights
- Latest quarter beat expectations
- EPS: $1.25
- Revenue: 25.5B

## Market Sentiment
- Overall sentiment: positive
- Key themes: earnings performance, product innovation

## Key Risks & Opportunities
- Risks: market competition, regulatory changes
- Opportunities: market expansion, new product launches
    """,
)
```

---

## Summarization Strategy

**File:** `flowforge/middleware/summarizer.py`

### The Problem

Agent responses can be huge (especially transcripts and SEC filings):
- An earnings call transcript: ~50,000 tokens
- SEC 10-K filing: ~100,000+ tokens
- Combined: Could easily exceed LLM context limits

Without summarization, you'd blow past context windows and get errors or truncated results.

### Solution: SummarizerMiddleware

The middleware intercepts step outputs and automatically summarizes anything that exceeds your token threshold.

```python
from flowforge.middleware.summarizer import (
    SummarizerMiddleware,
    LangChainSummarizer,
    SummarizationStrategy,
    create_openai_summarizer,
)

# Option 1: Simple truncation (default, no LLM needed)
forge.use_middleware(SummarizerMiddleware(
    max_tokens=4000,
    applies_to=["response_builder"],
))

# Option 2: LLM-powered summarization (recommended for production)
summarizer = create_openai_summarizer(model="gpt-4")
# or: summarizer = create_anthropic_summarizer(model="claude-3-sonnet-20240229")

forge.use_middleware(SummarizerMiddleware(
    max_tokens=4000,
    summarizer=summarizer,
    preserve_original=True,  # Keep original in context for debugging
    step_thresholds={
        "transcripts_agent": 2000,   # Stricter for transcripts
        "sec_filing_agent": 3000,    # More lenient for filings
    },
))
```

### Three Summarization Strategies

The `LangChainSummarizer` supports three strategies for handling large text:

| Strategy | How it Works | Best For |
|----------|--------------|----------|
| **STUFF** | Single LLM call with all text | Small documents that fit in context |
| **MAP_REDUCE** | Split → summarize each chunk in parallel → combine | Large docs, faster (parallel) |
| **REFINE** | Start with first chunk, iteratively refine with each additional chunk | Better context preservation, slower |

```python
# Choose your strategy
summarizer = LangChainSummarizer(
    llm=llm,
    strategy=SummarizationStrategy.MAP_REDUCE,  # default
    chunk_size=2000,      # tokens per chunk
    chunk_overlap=200,    # overlap for context continuity
)
```

### What Happens Under the Hood

```
┌─────────────────────────────────────────────────────────────────┐
│                  SummarizerMiddleware Flow                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step Output (e.g., 50,000 tokens transcript)                   │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. TOKEN COUNT                                           │   │
│  │    Uses tiktoken for accurate count, or ~4 chars/token   │   │
│  │    count_tokens("long text...") → 50,000                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                         │
│       ├─── ≤ max_tokens? ───▶ Pass through unchanged           │
│       │                                                         │
│       └─── > max_tokens? ───▼                                  │
│                             │                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 2. TEXT SPLITTING (if using MAP_REDUCE or REFINE)        │   │
│  │    TokenTextSplitter splits into ~2000 token chunks      │   │
│  │    with 200 token overlap for context continuity         │   │
│  │                                                          │   │
│  │    50,000 tokens → [chunk1, chunk2, ... chunk25]         │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 3. SUMMARIZATION (strategy-dependent)                    │   │
│  │                                                          │   │
│  │ MAP_REDUCE (parallel, fast):                             │   │
│  │   ┌────────┐ ┌────────┐ ┌────────┐                      │   │
│  │   │chunk 1 │ │chunk 2 │ │chunk 3 │  ... (all parallel)  │   │
│  │   └───┬────┘ └───┬────┘ └───┬────┘                      │   │
│  │       │          │          │                            │   │
│  │       ▼          ▼          ▼                            │   │
│  │   [summary1] [summary2] [summary3]                       │   │
│  │       │          │          │                            │   │
│  │       └──────────┼──────────┘                            │   │
│  │                  ▼                                       │   │
│  │          Combined summaries                              │   │
│  │                  │                                       │   │
│  │                  ▼                                       │   │
│  │          Final reduce step → FINAL SUMMARY               │   │
│  │                                                          │   │
│  │ REFINE (sequential, better context):                     │   │
│  │   chunk1 → summary1                                      │   │
│  │   summary1 + chunk2 → refined_summary                    │   │
│  │   refined_summary + chunk3 → more_refined                │   │
│  │   ... → FINAL SUMMARY                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 4. STORE RESULTS                                         │   │
│  │                                                          │   │
│  │ if preserve_original:                                    │   │
│  │   ctx.set("_original_{step}_output", original_data)      │   │
│  │                                                          │   │
│  │ result.output = summarized_content                       │   │
│  │ result.metadata = {                                      │   │
│  │   "summarized": True,                                    │   │
│  │   "original_tokens": 50000,                              │   │
│  │   "summarized_tokens": 4000,                             │   │
│  │   "summarization_strategy": "map_reduce"                 │   │
│  │ }                                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### How This Helps Your Chain

1. **Prevents Context Overflow**: A 100K token SEC filing gets reduced to 4K tokens
2. **Preserves Key Information**: LLM-based summarization keeps important facts, metrics, dates
3. **Per-Step Control**: Different thresholds for different agents (transcripts vs news)
4. **Debugging**: Original content preserved in context if needed
5. **Automatic**: Just add the middleware, it handles the rest

### Customizing Prompts

The summarizer uses sensible defaults, but you can customize:

```python
summarizer = LangChainSummarizer(
    llm=llm,
    map_prompt=(
        "Summarize this financial content, preserving:\n"
        "- Key metrics (EPS, revenue, margins)\n"
        "- Important dates and deadlines\n"
        "- Risk factors and forward guidance\n\n"
        "{text}\n\nSummary:"
    ),
    reduce_prompt=(
        "Combine these summaries into one cohesive summary.\n"
        "Prioritize quantitative data over qualitative:\n\n"
        "{text}\n\nFinal Summary:"
    ),
)
```

### Domain-Specific Summarization (Content-Aware)

Since we know what type of content each agent returns, we can use **domain-specific prompts**
that extract the most important information for each content type.

```python
from flowforge.middleware.summarizer import (
    create_domain_aware_middleware,
    DOMAIN_PROMPTS,
    get_domain_prompts,
)

# Easiest: Use pre-configured middleware for CMPT chain
middleware = create_domain_aware_middleware(llm=my_llm, max_tokens=4000)
forge.use_middleware(middleware)
```

#### What Each Domain Extracts:

| Content Type | What It Prioritizes |
|--------------|---------------------|
| **sec_filing** | Revenue, earnings, margins (with exact numbers), forward guidance, risk factors, segment performance |
| **earnings** | EPS actual vs estimate, beat/miss amounts, YoY/QoQ growth, next quarter guidance |
| **news** | Event type (M&A, launch, lawsuit), dates, impact (positive/negative), analyst opinions |
| **transcripts** | Management statements, specific targets, Q&A insights, tone (confident/cautious) |
| **pricing** | P/E, P/S, EV/EBITDA multiples, analyst price targets, peer comparisons |

#### How It Works:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             Domain-Aware MAP_REDUCE Example (SEC Filing)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  10-K Filing (100,000 tokens)                                               │
│       │                                                                     │
│       ▼                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ MAP Phase: Extract financial data from each chunk                     │  │
│  │                                                                       │  │
│  │ Prompt: "Extract key financial information from this SEC filing:     │  │
│  │         - Revenue, earnings, margins (with exact numbers and dates)  │  │
│  │         - Forward guidance and projections                           │  │
│  │         - Risk factors and material changes..."                      │  │
│  │                                                                       │  │
│  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                  │  │
│  │ │ Chunk 1  │ │ Chunk 2  │ │ Chunk 3  │ │ Chunk N  │  (parallel)     │  │
│  │ │ Revenue  │ │ Risk     │ │ Segment  │ │ Guidance │                  │  │
│  │ │ section  │ │ factors  │ │ data     │ │ section  │                  │  │
│  │ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘                  │  │
│  │      │            │            │            │                        │  │
│  │      ▼            ▼            ▼            ▼                        │  │
│  │  "Q4 rev:     "Supply      "Cloud:      "FY25:                       │  │
│  │   $119.6B,    chain        +22% YoY,    expect                       │  │
│  │   +2% YoY"    risks..."    $24.3B"      +8-10%"                      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│       │                                                                     │
│       ▼                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ REDUCE Phase: Consolidate into financial overview                     │  │
│  │                                                                       │  │
│  │ Prompt: "Combine these SEC filing summaries into a financial overview:│  │
│  │         - Consolidate all revenue/earnings figures with periods      │  │
│  │         - List all forward guidance statements                       │  │
│  │         - Highlight material risks..."                               │  │
│  │                                                                       │  │
│  │ Output:                                                               │  │
│  │ "Financial Summary:                                                   │  │
│  │  - Q4 FY24 Revenue: $119.6B (+2% YoY), EPS: $2.18 (beat by $0.08)   │  │
│  │  - Cloud segment: $24.3B (+22% YoY), now 20% of total revenue       │  │
│  │  - FY25 Guidance: +8-10% revenue growth, margin expansion 50-75bps  │  │
│  │  - Key Risks: Supply chain concentration, FX headwinds, regulation" │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  100,000 tokens → 3,000 tokens (97% reduction with key metrics preserved) │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Manual Step-to-ContentType Mapping:

```python
# If your step names don't match the defaults, map them explicitly:
middleware = SummarizerMiddleware(
    summarizer=LangChainSummarizer(llm=my_llm),
    max_tokens=4000,
    step_content_types={
        "my_sec_step": "sec_filing",
        "my_earnings_step": "earnings",
        "get_latest_news": "news",
        "call_transcripts": "transcripts",
        "valuation_data": "pricing",
    },
)
```

#### Calling Summarizer with Content Type Directly:

```python
# In your agent or step code:
summarizer = LangChainSummarizer(llm=my_llm)

# Without content type (generic prompts)
summary = await summarizer.summarize(sec_text, max_tokens=3000)

# With content type (domain-specific prompts)
summary = await summarizer.summarize(
    sec_text,
    max_tokens=3000,
    content_type="sec_filing"  # Uses SEC-specific extraction prompts
)
```

#### Available Domain Prompts:

```python
from flowforge.middleware.summarizer import DOMAIN_PROMPTS

# See all available domains
print(DOMAIN_PROMPTS.keys())
# dict_keys(['sec_filing', 'earnings', 'news', 'transcripts', 'pricing'])

# Get prompts for a domain
map_prompt, reduce_prompt = get_domain_prompts("earnings")
```

### No LLM? No Problem

Without an LLM, the summarizer falls back to simple truncation:

```python
# This still works - just truncates instead of summarizing
summarizer = LangChainSummarizer(llm=None)  # default

# Output: "First 4000 tokens of content...\n[... truncated ...]"
```

### Alternative: Agent-Level Summarization

For more control, summarize at the agent level in `response_builder.py`:

```python
async def _execute_single_agent(self, subquery: Subquery) -> AgentResult:
    # ... execute agent ...

    # Summarize large responses before returning
    if count_tokens(str(items)) > 12000:
        items = await self.summarizer.summarize(str(items), max_tokens=3000)

    return AgentResult(
        agent=subquery.agent,
        items=items,
        metadata={"summarized": True},
    )
```

### Quick Start Examples

```python
# Minimal setup (truncation only)
forge.use_middleware(SummarizerMiddleware(max_tokens=4000))

# With OpenAI
from flowforge.middleware.summarizer import create_openai_summarizer
forge.use_middleware(SummarizerMiddleware(
    summarizer=create_openai_summarizer(model="gpt-4"),
    max_tokens=4000,
))

# With Anthropic Claude
from flowforge.middleware.summarizer import create_anthropic_summarizer
forge.use_middleware(SummarizerMiddleware(
    summarizer=create_anthropic_summarizer(model="claude-3-sonnet-20240229"),
    max_tokens=4000,
))

# Legacy callable support (backward compatible)
async def my_custom_summarizer(text: str, max_tokens: int) -> str:
    # your custom logic
    return summarized_text

forge.use_middleware(SummarizerMiddleware(summarizer=my_custom_summarizer))
```

---

## Production Features

FlowForge includes several enterprise-grade features for production deployments.

### CLI Tool

FlowForge provides a command-line interface for common operations:

```bash
# Run a chain
flowforge run cmpt_chain --data '{"company": "Apple"}'

# Validate definitions
flowforge check

# List all registered components
flowforge list

# Visualize DAG
flowforge graph cmpt_chain
flowforge graph cmpt_chain --format mermaid

# Scaffold new components
flowforge new agent MyAgent
flowforge new chain MyChain

# Development mode with hot reload
flowforge dev --watch

# Debug mode with context snapshots
flowforge debug cmpt_chain --data '{"company": "Apple"}'
flowforge debug cmpt_chain --snapshot-dir ./debug_output

# Health check (returns exit code 1 if unhealthy)
flowforge health
flowforge health --json

# Version info
flowforge version

# Show configuration (secrets masked)
flowforge config
```

### Debug Mode

Debug mode saves context snapshots after each step for troubleshooting:

```bash
flowforge debug my_pipeline --data '{"company": "Apple"}'

# Output directory structure:
# ./snapshots/my_pipeline_20250128_143022/
#   ├── 00_summary.json          # Final execution summary
#   ├── 01_step_extract.json     # Context after step 1
#   ├── 02_step_transform.json   # Context after step 2
#   └── 99_error.json            # Error details (if failed)
```

Each snapshot includes step name, status, context data, timing, and any errors.

**Programmatic Debug Callbacks:**

You can also use debug callbacks programmatically:

```python
from flowforge import FlowForge, ChainContext

forge = FlowForge(name="my_app")

def debug_callback(ctx: ChainContext, step_name: str, result: dict):
    """Called after each step with context and result"""
    print(f"[{step_name}] {'✓' if result['success'] else '✗'} ({result['duration_ms']:.1f}ms)")
    if not result['success']:
        print(f"  Error: {result.get('error', 'unknown')}")

# Pass callback to launch/run
result = await forge.launch(
    "my_pipeline",
    data={"company": "Apple"},
    debug_callback=debug_callback,
)
```

The CLI `debug` command uses this callback mechanism internally, wiring it through `forge.launch` → `runner.run` → `executor.execute` → each step execution.

### Circuit Breaker Pattern

Protect external service calls from cascading failures:

```python
from flowforge import CircuitBreaker, CircuitBreakerConfig, get_circuit_breaker

# Configure circuit breaker
config = CircuitBreakerConfig(
    failure_threshold=5,      # Open after 5 consecutive failures
    recovery_timeout=30.0,    # Wait 30s before trying again
    half_open_max_calls=3,    # Allow 3 test calls when half-open
)

breaker = CircuitBreaker("foundation_db", config)

# Use as decorator
@breaker
async def call_foundation_db(company_name: str):
    async with httpx.AsyncClient() as client:
        return await client.post(f"{FOUNDATION_URL}/find_company_matches", json={...})

# Use in response builder for agent calls
@get_circuit_breaker("mcp_news")
async def execute_news_agent(subquery):
    async with mcp_session as session:
        return await session.call_tool("search_news", subquery)
```

**Circuit States:**
- **CLOSED**: Normal operation, all requests pass through
- **OPEN**: Circuit is open, requests fail immediately without calling the service
- **HALF_OPEN**: Testing if service is back, limited requests allowed

### Retry with Exponential Backoff

Configure automatic retries for transient failures:

```python
from flowforge import async_retry, RetryPolicy

# Simple retry
@async_retry(max_attempts=3, delay=1.0, backoff=2.0)
async def fetch_earnings_calendar(company_name: str):
    return await client.post(EARNINGS_CALENDAR_URL, json={...})

# Policy-based retry
policy = RetryPolicy(
    max_attempts=5,
    initial_delay=0.5,
    max_delay=30.0,
    backoff_multiplier=2.0,
    retryable_exceptions=(httpx.HTTPError, TimeoutError),
)

@async_retry(policy=policy)
async def resilient_ldap_lookup(email: str):
    return ldap_service.lookup([email])
```

### Connection Pooling

The LLM Gateway uses connection pooling for high concurrency:

```python
from flowforge import LLMGatewayClient, create_managed_client

# Managed client with automatic cleanup
client = create_managed_client(
    base_url=os.getenv("LLM_GATEWAY_URL"),
    timeout=30.0,
    max_retries=3,
    circuit_breaker_enabled=True,
)

# Pool configuration happens automatically
# - max_connections=100
# - max_keepalive_connections=20
# - keepalive timeout = 30s

# Use as context manager for explicit control
async with client:
    result = await client.complete_async(prompt)

# Cleanup happens automatically on process exit via atexit
```

### Resource Management

Register resources with dependency injection and lifecycle management:

```python
from flowforge import FlowForge, ResourceScope

forge = FlowForge(name="cmpt")

# Register database pool
forge.register_resource(
    "db_pool",
    factory=lambda: create_db_pool(os.getenv("DATABASE_URL")),
    cleanup=lambda pool: pool.close(),
)

# Register LLM client with dependency
forge.register_resource(
    "llm",
    factory=lambda: create_managed_client(os.getenv("LLM_URL")),
    cleanup=lambda c: c.close_sync(),
    dependencies=["config"],  # Initialize config first
)

# Inject into steps
@forge.step(name="fetch_data", resources=["db_pool", "llm"])
async def fetch_data(ctx, db_pool, llm):
    data = await db_pool.query("SELECT ...")
    summary = await llm.complete_async(str(data))
    return {"data": summary}
```

### Structured Logging

Configure structured logging for production:

```python
from flowforge import configure_logging, get_logger, ChainLogger

# Configure at startup
configure_logging(
    level="INFO",
    json_output=True,  # JSON for production log aggregation
)

# Use in services
logger = get_logger("context_builder")
logger.info("Extracting company info", company=company_name, ticker=ticker)

# Chain-aware logger
chain_logger = ChainLogger("cmpt", request_id)
chain_logger.chain_start()
chain_logger.step_start("context_builder")
chain_logger.step_complete("context_builder", duration_ms=290.5)
chain_logger.chain_complete(total_ms=1250.0, success=True)
```

### Distributed Tracing

FlowForge includes built-in OpenTelemetry tracing that's automatically integrated at the DAG executor layer:

```python
from flowforge import FlowForge, configure_tracing, ChainTracer, trace_span

# Configure at startup
configure_tracing(
    service_name="cmpt-chain",
    endpoint=os.getenv("OTEL_ENDPOINT", "http://jaeger:4317"),
)

# Automatic tracing for all chain executions
# Each chain creates a parent span with child spans for each step
forge = FlowForge(name="cmpt")
result = await forge.run("cmpt_chain")  # Automatically traced

# For custom tracing, use ChainTracer directly
tracer = ChainTracer("cmpt", request_id)
with tracer.chain_span(total_steps=3):
    with tracer.step_span("context_builder", agent="foundation_db"):
        result = await context_builder.execute(request)

    with tracer.step_span("content_prioritization"):
        result = await content_prioritization.execute(context)

    with tracer.step_span("response_builder", agents=["news", "sec", "earnings"]):
        result = await response_builder.execute(context, prioritization)
```

**Tracing attributes automatically captured:**
- `chain.name`: Name of the chain being executed
- `chain.request_id`: Unique request identifier
- `chain.total_steps`: Number of steps in the chain
- `step.name`: Name of each step
- `step.duration_ms`: Execution time
- `step.success`: Whether the step succeeded
- `step.retry_count`: Number of retries (if any)

### Explicit Parallel Groups

Override dependency-based execution order:

```python
@forge.chain(
    name="enhanced_cmpt",
    parallel_groups=[
        ["context_builder"],                              # Stage 1
        ["fetch_news", "fetch_sec", "fetch_earnings"],    # Stage 2: parallel
        ["aggregate_data"],                               # Stage 3
        ["generate_report"],                              # Stage 4
    ]
)
class EnhancedCMPT:
    steps = [
        "context_builder",
        "fetch_news", "fetch_sec", "fetch_earnings",
        "aggregate_data",
        "generate_report",
    ]
```

### Per-Step Concurrency Limits

Control parallelism for rate-limited APIs:

```python
@forge.step(
    name="fetch_zoominfo",
    max_concurrency=2,  # ZoomInfo has rate limits
)
async def fetch_zoominfo(ctx):
    return await zoominfo_service.lookup(ctx.get("email"))

@forge.step(
    name="call_llm",
    max_concurrency=5,  # Allow 5 concurrent LLM calls
)
async def call_llm(ctx):
    return await llm_client.complete_async(ctx.get("prompt"))
```

### True Fail-Fast Execution

FlowForge implements true fail-fast behavior that immediately cancels pending tasks:

```python
# OLD behavior (most frameworks):
# asyncio.gather(..., return_exceptions=True) waits for ALL tasks
# Even if task 1 fails in 100ms, tasks 2-5 continue running

# FlowForge behavior:
# Uses asyncio.wait(return_when=FIRST_COMPLETED)
# When first failure detected, cancels all pending tasks immediately
# No wasted API calls, no unwanted side effects

@forge.chain(name="my_chain", error_handling="fail_fast")
class MyChain:
    steps = ["step_a", "step_b", "step_c"]

# For continue mode, all tasks run to completion:
@forge.chain(name="my_chain", error_handling="continue")
class MyChain:
    steps = ["step_a", "step_b", "step_c"]
```

### Graceful Degradation (Continue Mode)

For multi-agent workflows where partial success is acceptable:

```python
@forge.chain(name="data_pipeline", error_handling="continue")
class DataPipeline:
    steps = ["fetch_news", "fetch_sec", "fetch_earnings", "aggregate"]

result = await forge.run("data_pipeline")

# Check for partial success
if result["success"]:
    print("All steps succeeded!")
elif result.get("partial_success"):
    print(f"Partial success: {result['completion_rate']}% completed")

    # Examine individual step results
    for r in result["results"]:
        if r["error"]:
            print(f"  {r['step_name']}: FAILED - {r['error']}")
            print(f"    Type: {r['error_type']}")
            print(f"    Traceback: {r['error_traceback'][:100]}...")
        elif r.get("skipped_reason"):
            print(f"  {r['step_name']}: SKIPPED - {r['skipped_reason']}")
        else:
            print(f"  {r['step_name']}: SUCCESS ({r['duration_ms']:.1f}ms)")
```

### Rich Error Metadata

Each step result includes detailed error information:

```python
from flowforge.core.context import StepResult, ExecutionSummary

# StepResult fields:
# - step_name: str
# - output: Any
# - duration_ms: float
# - error: Exception | None
# - error_type: str | None (e.g., "ValueError")
# - error_traceback: str | None (full stack trace)
# - retry_count: int
# - skipped_reason: str | None

# ExecutionSummary aggregates results:
summary = ExecutionSummary(chain_name="my_chain", request_id="req-123", total_steps=4)
# After execution:
print(summary.completed_steps)   # 2
print(summary.failed_steps)      # 1
print(summary.skipped_steps)     # 1
print(summary.completion_rate)   # 50.0
print(summary.partial_success)   # True

# Helper methods:
summary.get_successful_steps()  # List[StepResult]
summary.get_failed_steps()      # List[StepResult]
summary.get_skipped_steps()     # List[StepResult]
```

### Typed Configuration with Secret Masking

Configure FlowForge with environment variables and automatic secret masking:

```python
from flowforge.utils import get_config, FlowForgeConfig, SecretString

# Load configuration (lazy, cached)
config = get_config()

# Access typed values
print(config.llm_model)        # "gpt-4"
print(config.max_parallel)     # 10
print(config.llm_api_key)      # ***REDACTED*** (masked)

# Get actual secret value when needed
api_key = str(config.llm_api_key)

# Safe dict for logging (all secrets masked)
safe_config = config.to_safe_dict()

# Access nested configuration
print(config.cache.ttl_seconds)       # 300
print(config.rate_limit.enabled)      # False
print(config.retry_policy.max_retries)  # 3
```

**Key environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWFORGE_ENV` | `development` | Environment name |
| `LLM_API_KEY` | - | LLM API key (masked) |
| `LLM_BASE_URL` | `http://localhost:8000` | LLM service URL |
| `FLOWFORGE_MAX_PARALLEL` | `10` | Max parallel steps |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry |
| `LOG_FORMAT` | `text` | Log format (text/json) |

### External Secret Backends

For production, use external secret backends instead of environment variables:

```python
from flowforge.utils import (
    FlowForgeConfig,
    AWSSecretsManagerBackend,
    VaultSecretBackend,
)

# AWS Secrets Manager
aws_backend = AWSSecretsManagerBackend(
    secret_name="flowforge/prod",
    region_name="us-east-1",
    cache_ttl_seconds=300,  # Cache for 5 minutes
)
config = FlowForgeConfig.from_env(secret_backend=aws_backend)

# HashiCorp Vault
vault_backend = VaultSecretBackend(
    url="https://vault.example.com",
    token="hvs.xxxxx",
    path="secret/data/flowforge",
)
config = FlowForgeConfig.from_env(secret_backend=vault_backend)
```

Secrets are automatically fetched for any `ConfigField` marked as `secret=True`.

### Health Checks

Built-in health checks for operational visibility:

```python
from flowforge.utils import get_health, get_version

# Get health status
health = get_health()
print(health.status)      # "healthy", "degraded", or "unhealthy"
print(health.checks)      # {"config_loaded": True, "llm_configured": True}

# Get version info
version = get_version()   # {"name": "flowforge", "version": "1.0.0", ...}
```

Use in CI/CD pipelines or container health probes:

```bash
# Returns exit code 0 if healthy, 1 otherwise
flowforge health || exit 1

# Dockerfile example
HEALTHCHECK --interval=30s --timeout=3s \
  CMD flowforge health || exit 1
```

### OTel-Compliant Structured Logging

ChainRunner now logs with OTel-compliant structured attributes:

```python
# On failure, logs include:
logger.error(
    "Chain execution failed: my_chain",
    extra={
        "otel.status_code": "ERROR",
        "exception.type": "ValueError",
        "exception.message": "Step failed",
        "chain.name": "my_chain",
        "request.id": "abc-123",
        "error.traceback": "...",
    },
)

# Results include structured error info:
result = await runner.run("my_chain")
if not result["success"]:
    print(result["error"]["type"])       # "ValueError"
    print(result["error"]["message"])    # "Step failed"
    print(result["error"]["traceback"])  # Full stack trace
    print(result["error"]["request_id"]) # For correlation
```

### Middleware Exception Isolation

Middleware failures no longer crash step execution:

```python
# Before: Failing middleware crashes the step
# After: Middleware errors are logged, step continues

# LoggerMiddleware throws an exception?
# - Error is logged with warning level
# - Step execution continues normally
# - Core pipeline functionality is preserved

logger.warning(
    f"Before middleware {mw.__class__.__name__} failed for "
    f"step {step_name}: {e}. Continuing execution."
)
```

### Registry Isolation

FlowForge uses isolated registries by default to prevent state bleed:

```python
from flowforge import FlowForge

# Isolated by default (safe for testing)
forge = FlowForge(name="my_app")  # isolated=True is default

# Explicit shared registries (for global singleton)
forge = FlowForge(name="my_app", isolated=False)

# For testing, use temp_registries context manager
with FlowForge.temp_registries("test") as forge:
    # Define steps and chains
    @forge.step(name="test_step")
    async def test_step(ctx):
        return {"ok": True}

    # Test runs in isolation
    result = asyncio.run(forge.run("test_chain"))
# Registries automatically cleaned up
```

### Registry Strict Mode

Prevent accidental overwrites when registering components:

```python
from flowforge.core.registry import get_step_registry, get_chain_registry

# Default: silently overwrites existing registrations
registry = get_step_registry()
registry.register_step("my_step", handler1)
registry.register_step("my_step", handler2)  # Overwrites handler1

# Strict mode: raises ValueError if component already exists
registry.register_step("my_step", handler3, strict=True)
# ValueError: Component 'my_step' already registered. Use strict=False to overwrite.

# Works with all registry types
chain_registry = get_chain_registry()
chain_registry.register_chain("my_chain", steps, strict=True)

agent_registry = get_agent_registry()
agent_registry.register_agent("my_agent", MyAgent, strict=True)
```

### Resource Cleanup with Timeout

Prevent indefinite hanging during resource cleanup:

```python
from flowforge import FlowForge

forge = FlowForge(name="my_app")

# Register resource with cleanup handler
forge.register_resource(
    "db_pool",
    factory=lambda: create_db_pool(),
    cleanup=lambda pool: pool.close(),  # Could hang if connections stuck
)

# Async context manager uses 30s default timeout
async with forge:
    result = await forge.run("my_chain")
# Resources cleaned up with 30s timeout

# Custom timeout for manual cleanup
await forge.cleanup_resources(timeout_seconds=60.0)

# If cleanup exceeds timeout, raises asyncio.TimeoutError
try:
    await forge.cleanup_resources(timeout_seconds=5.0)
except asyncio.TimeoutError:
    logger.error("Resource cleanup timed out")
```

### Module-Level Decorators

The decorators in `flowforge/core/decorators.py` delegate to the global FlowForge instance:

```python
from flowforge.core.decorators import agent, step, chain

# These register to the global forge instance (from get_forge())
@agent
class MyAgent:
    pass

@step
async def my_step(ctx):
    return {"done": True}

@step(name="custom_step", deps=[my_step], produces=["output"])
async def another_step(ctx):
    return {"output": "result"}

@chain
class MyChain:
    steps = ["my_step", "custom_step"]

# Access the global forge to run chains
from flowforge.core.forge import get_forge
forge = get_forge()
result = await forge.run("mychain")
```

This provides a clean, simple API for quick scripts while still allowing full control via the `FlowForge` class when needed.

---

## File Reference

### Core Framework

| File | Purpose |
|------|---------|
| `flowforge/__init__.py` | Package exports and usage examples |
| `flowforge/core/forge.py` | Main FlowForge class, decorators, execution, cleanup timeout |
| `flowforge/core/dag.py` | DAG builder and executor (supports explicit parallel_groups) |
| `flowforge/core/context.py` | ChainContext, StepResult, ExecutionSummary |
| `flowforge/core/registry.py` | Agent, Step, Chain registries (isolated by default, strict mode) |
| `flowforge/core/decorators.py` | @agent, @step, @chain decorators (delegate to global forge) |
| `flowforge/core/resources.py` | Resource management and dependency injection |
| `flowforge/core/visualize.py` | DAG visualization (ASCII and Mermaid) |
| `flowforge/cli.py` | Command-line interface (run, check, list, graph, new, dev) |

### CMPT Chain

| File | Purpose |
|------|---------|
| `flowforge/chains/__init__.py` | Chain exports |
| `flowforge/chains/cmpt.py` | CMPT chain definition and CMPTChain class |

### Services (Business Logic)

| File | Purpose | Stage |
|------|---------|-------|
| `flowforge/services/__init__.py` | Service exports |  |
| `flowforge/services/models.py` | All Pydantic models | All |
| `flowforge/services/context_builder.py` | Context extraction | 1 |
| `flowforge/services/content_prioritization.py` | Source prioritization | 2 |
| `flowforge/services/response_builder.py` | Agent execution & response | 3 |

### Middleware

| File | Purpose |
|------|---------|
| `flowforge/middleware/__init__.py` | Middleware exports |
| `flowforge/middleware/base.py` | Base Middleware class |
| `flowforge/middleware/summarizer.py` | Token/content summarization (stuff/map_reduce/refine strategies) |
| `flowforge/middleware/cache.py` | Response caching |
| `flowforge/middleware/logger.py` | Execution logging |
| `flowforge/middleware/token_manager.py` | Token usage tracking |

**Key exports from `summarizer.py`:**
- `SummarizerMiddleware` - Middleware that triggers summarization on large outputs
- `LangChainSummarizer` - Core summarizer with stuff/map_reduce/refine strategies
- `SummarizationStrategy` - Enum: STUFF, MAP_REDUCE, REFINE
- `count_tokens()` - Token counting utility (tiktoken or fallback)
- `create_openai_summarizer()` - Factory for OpenAI-backed summarizer
- `create_anthropic_summarizer()` - Factory for Claude-backed summarizer

### Utilities (Production)

| File | Purpose |
|------|---------|
| `flowforge/utils/__init__.py` | Utility exports |
| `flowforge/utils/circuit_breaker.py` | Circuit breaker pattern implementation |
| `flowforge/utils/logging.py` | Structured logging (structlog integration) |
| `flowforge/utils/tracing.py` | Distributed tracing (OpenTelemetry) |
| `flowforge/utils/timing.py` | Timing decorators (@timed, @async_timed) |
| `flowforge/utils/retry.py` | Retry with exponential backoff |
| `flowforge/utils/config.py` | Typed configuration with secret masking |

**Key exports from `config.py`:**
- `FlowForgeConfig` - Typed configuration dataclass
- `SecretString` - Auto-masking secret string
- `ConfigError` - Configuration validation error
- `get_config()` - Get global config (lazy, cached)
- `set_config()` - Set global config (for testing)
- `get_health()` - Get health status
- `get_version()` - Get version info
- `HealthStatus` - Health check response dataclass
- `SecretBackend` - Abstract base class for secret backends
- `EnvSecretBackend` - Environment variable backend (default)
- `AWSSecretsManagerBackend` - AWS Secrets Manager backend
- `VaultSecretBackend` - HashiCorp Vault backend
- `CacheConfig` - Cache configuration (enabled, ttl, max_size, strategy)
- `RateLimitConfig` - Rate limit configuration (enabled, requests_per_second, burst_size)
- `RetryPolicyConfig` - Retry policy configuration (max_retries, delays, backoff)

**Key exports from `circuit_breaker.py`:**
- `CircuitBreaker` - Main circuit breaker class
- `CircuitBreakerConfig` - Configuration (threshold, timeout, half_open_max)
- `CircuitBreakerError` - Exception raised when circuit is open
- `CircuitState` - Enum: CLOSED, OPEN, HALF_OPEN
- `get_circuit_breaker()` - Get or create named circuit breaker

**Key exports from `logging.py`:**
- `configure_logging()` - Configure structured logging
- `get_logger()` - Get a logger instance
- `LogContext` - Context manager for request-scoped logging
- `ChainLogger` - Specialized logger for chain execution

**Key exports from `tracing.py`:**
- `configure_tracing()` - Configure OpenTelemetry tracing
- `get_tracer()` - Get a tracer instance
- `trace_span()` - Context manager for creating spans
- `ChainTracer` - Specialized tracer for chain execution

### Testing

| File | Purpose |
|------|---------|
| `flowforge/test_cmpt_chain.py` | End-to-end test suite |

---

## Running the Chain

### Using the CLI

```bash
# Run a chain directly
flowforge run cmpt_chain --data '{"company": "Apple Inc"}'

# Validate all definitions first
flowforge check

# List registered components
flowforge list

# Visualize the DAG
flowforge graph cmpt_chain
```

### Using Python

```bash
# Activate virtual environment
source flowforge/.venv/bin/activate

# Run end-to-end test
python -m flowforge.test_cmpt_chain

# Or in Python
python -c "
import asyncio
from flowforge.chains import CMPTChain

async def main():
    chain = CMPTChain()
    result = await chain.run(
        corporate_company_name='Apple Inc',
        meeting_datetime='2025-01-15T10:00:00Z',
    )
    print(result.response_builder['prepared_content'])

asyncio.run(main())
"
```

### Development Mode

```bash
# Watch for file changes and auto-reload
flowforge dev --watch

# With custom port
flowforge dev --watch --port 8000
```

---

## Next Steps for Production

1. **Replace Mock Data**: Update `_get_mock_agent_data()` in `response_builder.py` with real API calls
2. **Add LLM Summarization**: Configure `SummarizerMiddleware` with OpenAI/Claude
3. **Connect Real Extractors**: Update `context_builder.py` to call Foundation DB, LDAP, ZoomInfo
4. **Add Caching**: Use `CacheMiddleware` for expensive API calls
5. **Add Monitoring**: Use `LoggerMiddleware` for execution tracing
6. **Configure Circuit Breakers**: Wrap external service calls with circuit breakers
7. **Add Retry Policies**: Configure retry with exponential backoff for transient failures
8. **Enable Tracing**: Configure OpenTelemetry for distributed tracing
9. **Resource Management**: Register database pools, LLM clients with lifecycle hooks
10. **Use Parallel Groups**: Define explicit execution ordering for optimized performance
# Build a CMP-like Flow in 30 Minutes

This guide walks you through building a Client Meeting Prep (CMP) style flow using FlowForge. By the end, you'll have a working chain that:

1. Extracts context from meeting requests
2. Prioritizes data sources
3. Fetches data from multiple agents in parallel
4. Builds a comprehensive response

## Prerequisites

- Python 3.11+
- FlowForge installed (`pip install flowforge`)
- Redis running locally (optional, for context store)

## Step 1: Create a New Project (2 minutes)

```bash
# Create new project
flowforge new project meeting_prep

# Navigate to project
cd meeting_prep

# Install dependencies
pip install -e ".[dev]"

# Verify setup
flowforge check
```

## Step 2: Define Your Data Models (5 minutes)

Create `src/meeting_prep/models/request.py`:

```python
"""Request and response models for Meeting Prep chain."""

from datetime import datetime
from pydantic import BaseModel, Field


class MeetingRequest(BaseModel):
    """Input request for meeting preparation."""

    company_name: str = Field(..., description="Company name for the meeting")
    meeting_date: datetime = Field(default_factory=datetime.utcnow)
    attendees: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class CompanyContext(BaseModel):
    """Extracted company context."""

    company_name: str
    ticker: str | None = None
    sector: str | None = None
    market_cap: float | None = None


class PrioritizedSources(BaseModel):
    """Prioritized data sources."""

    primary_sources: list[str]
    secondary_sources: list[str]
    lookback_days: int = 30


class MeetingBrief(BaseModel):
    """Final meeting brief output."""

    company: CompanyContext
    key_points: list[str]
    recent_news: list[dict]
    financial_highlights: dict
    talking_points: list[str]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
```

## Step 3: Create Custom Agents (10 minutes)

Create `src/meeting_prep/agents/company_agent.py`:

```python
"""Company data agent."""

from flowforge.agents.base import BaseAgent, AgentResult
from flowforge.plugins.capability import CapabilitySchema, AgentCapability, CapabilityParameter


class CompanyAgent(BaseAgent):
    """Agent for fetching company information."""

    _flowforge_name = "company_agent"
    _flowforge_version = "1.0.0"

    CAPABILITIES = CapabilitySchema(
        name="company_agent",
        version="1.0.0",
        description="Fetches company information",
        capabilities=[
            AgentCapability(
                name="lookup",
                description="Look up company by name",
                parameters=[
                    CapabilityParameter(name="company_name", type="string", required=True),
                ],
            ),
        ],
    )

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch company information."""
        import time
        start = time.perf_counter()

        # In production, this would call a real API
        data = {
            "company_name": query,
            "ticker": "AAPL" if "apple" in query.lower() else "UNKNOWN",
            "sector": "Technology",
            "market_cap": 3000000000000,
        }

        duration = (time.perf_counter() - start) * 1000

        return AgentResult(
            data=data,
            source=self._flowforge_name,
            query=query,
            duration_ms=duration,
        )
```

Create `src/meeting_prep/agents/news_agent.py`:

```python
"""News agent using HTTP adapter."""

from flowforge.plugins.http_adapter import HTTPAdapterAgent, HTTPAdapterConfig


def create_news_agent():
    """Create a news agent using HTTP adapter."""

    config = HTTPAdapterConfig(
        base_url="https://newsapi.org/v2",
        auth_type="api_key",
        auth_token="YOUR_API_KEY",  # Set via env var
        api_key_header="X-Api-Key",
        timeout_seconds=10.0,
        max_retries=3,
    )

    agent = HTTPAdapterAgent(config)
    agent._flowforge_name = "news_agent"

    return agent
```

## Step 4: Build the Chain Steps (10 minutes)

Create `src/meeting_prep/chains/meeting_prep_chain.py`:

```python
"""Meeting Prep Chain - Full implementation."""

from flowforge import FlowForge, ChainContext, get_forge
from flowforge.utils.tracing import trace_span

from meeting_prep.models.request import (
    MeetingRequest,
    CompanyContext,
    PrioritizedSources,
    MeetingBrief,
)
from meeting_prep.agents.company_agent import CompanyAgent

# Get global forge instance
forge = get_forge()

# Register agents
forge.register_agent("company_agent", CompanyAgent)


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 1: Context Extraction
# ═══════════════════════════════════════════════════════════════════════════════

@forge.step(
    name="extract_context",
    produces=["company_context"],
    description="Extracts company context from meeting request",
    timeout_ms=10000,
)
async def extract_context(ctx: ChainContext):
    """Extract company and meeting context."""

    with trace_span("step.extract_context"):
        # Get request from context
        request_data = ctx.get("request", {})
        request = MeetingRequest(**request_data) if isinstance(request_data, dict) else request_data

        # Fetch company info
        company_agent = forge.get_agent("company_agent")
        result = await company_agent.fetch(request.company_name)

        if result.success:
            context = CompanyContext(**result.data)
        else:
            context = CompanyContext(company_name=request.company_name)

        ctx.set("company_context", context.model_dump())

        return context.model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 2: Source Prioritization
# ═══════════════════════════════════════════════════════════════════════════════

@forge.step(
    name="prioritize_sources",
    deps=[extract_context],
    produces=["prioritized_sources"],
    description="Prioritizes data sources based on context",
    timeout_ms=5000,
)
async def prioritize_sources(ctx: ChainContext):
    """Determine which data sources to query."""

    with trace_span("step.prioritize_sources"):
        company_context = ctx.get("company_context", {})

        # Simple prioritization logic
        primary = ["news", "financials"]
        secondary = ["sec_filings", "analyst_reports"]

        # Adjust based on sector
        if company_context.get("sector") == "Technology":
            primary.append("product_launches")

        sources = PrioritizedSources(
            primary_sources=primary,
            secondary_sources=secondary,
            lookback_days=30,
        )

        ctx.set("prioritized_sources", sources.model_dump())

        return sources.model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 3: Parallel Data Fetching
# ═══════════════════════════════════════════════════════════════════════════════

@forge.step(
    name="fetch_news",
    deps=[prioritize_sources],
    produces=["news_data"],
    description="Fetches recent news articles",
    timeout_ms=15000,
)
async def fetch_news(ctx: ChainContext):
    """Fetch news data in parallel with other sources."""

    company_context = ctx.get("company_context", {})
    company_name = company_context.get("company_name", "Unknown")

    # Simulated news fetch (replace with real API)
    news_data = [
        {
            "title": f"Latest update on {company_name}",
            "date": "2025-01-15",
            "source": "Financial Times",
            "sentiment": 0.7,
        },
    ]

    ctx.set("news_data", news_data)
    return {"articles": news_data, "count": len(news_data)}


@forge.step(
    name="fetch_financials",
    deps=[prioritize_sources],
    produces=["financial_data"],
    description="Fetches financial data",
    timeout_ms=15000,
)
async def fetch_financials(ctx: ChainContext):
    """Fetch financial data in parallel with news."""

    company_context = ctx.get("company_context", {})

    # Simulated financial data
    financial_data = {
        "revenue": 394.3e9,
        "net_income": 97.0e9,
        "eps": 6.13,
        "pe_ratio": 28.5,
    }

    ctx.set("financial_data", financial_data)
    return financial_data


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 4: Build Response
# ═══════════════════════════════════════════════════════════════════════════════

@forge.step(
    name="build_brief",
    deps=[fetch_news, fetch_financials],
    produces=["meeting_brief"],
    description="Builds the final meeting brief",
    timeout_ms=10000,
)
async def build_brief(ctx: ChainContext):
    """Combine all data into final meeting brief."""

    with trace_span("step.build_brief"):
        company_context = ctx.get("company_context", {})
        news_data = ctx.get("news_data", [])
        financial_data = ctx.get("financial_data", {})

        # Build brief
        brief = MeetingBrief(
            company=CompanyContext(**company_context),
            key_points=[
                f"Market cap: ${company_context.get('market_cap', 0) / 1e9:.1f}B",
                f"Sector: {company_context.get('sector', 'Unknown')}",
            ],
            recent_news=news_data,
            financial_highlights=financial_data,
            talking_points=[
                "Recent financial performance",
                "Market position and competition",
                "Growth opportunities",
            ],
        )

        ctx.set("meeting_brief", brief.model_dump())

        return brief.model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
#                         CHAIN DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════

@forge.chain(
    name="meeting_prep_chain",
    description="Prepares briefing materials for client meetings",
    version="1.0.0",
)
class MeetingPrepChain:
    """Meeting Prep Chain."""

    steps = [
        extract_context,
        prioritize_sources,
        fetch_news,
        fetch_financials,
        build_brief,
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#                         CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def run(company_name: str, **kwargs) -> dict:
    """Run the meeting prep chain."""

    request = MeetingRequest(company_name=company_name, **kwargs)

    return await forge.launch_resumable(
        "meeting_prep_chain",
        {"request": request.model_dump()},
    )


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run("Apple Inc"))
    print(result)
```

## Step 5: Test Your Chain (3 minutes)

```bash
# Validate the chain
flowforge validate meeting_prep_chain

# Run with sample data
flowforge run meeting_prep_chain --data '{"request": {"company_name": "Apple Inc"}}'

# Visualize the DAG
flowforge graph meeting_prep_chain --format mermaid
```

Expected DAG:

```
extract_context
       ↓
prioritize_sources
       ↓
   ┌───┴───┐
   ↓       ↓
fetch_news fetch_financials
   ↓       ↓
   └───┬───┘
       ↓
  build_brief
```

## Step 6: Add API Server (Optional)

Your project already has an API server in `src/meeting_prep/api.py`. Start it:

```bash
pip install -e ".[api]"
uvicorn meeting_prep.api:app --reload --port 8000
```

Test endpoints:

```bash
# Health check
curl http://localhost:8000/health

# Run chain
curl -X POST http://localhost:8000/run/meeting_prep_chain \
  -H "Content-Type: application/json" \
  -d '{"data": {"request": {"company_name": "Apple Inc"}}}'

# Check run status
curl http://localhost:8000/runs/{run_id}

# Get partial outputs
curl http://localhost:8000/runs/{run_id}/output
```

## Next Steps

1. **Add resilience**: Wrap agents with `ResilientAgent` for timeout/retry/circuit-breaker
2. **Add caching**: Use `CacheMiddleware` to cache expensive API calls
3. **Add tracing**: Enable OpenTelemetry for observability
4. **Deploy**: Use the included Dockerfile and docker-compose.yml

## Common Patterns

### Parallel Data Fetching

Steps with the same dependencies run in parallel:

```python
@forge.step(deps=[prioritize_sources])
async def fetch_news(ctx): ...

@forge.step(deps=[prioritize_sources])
async def fetch_financials(ctx): ...

# Both run in parallel after prioritize_sources completes
```

### Resumable Chains

```python
# Run with checkpointing
result = await forge.launch_resumable("my_chain", data)
run_id = result["run_id"]

# If failed, resume from checkpoint
result = await forge.resume(run_id)

# Get partial outputs
partial = await forge.get_partial_output(run_id)
```

### Input Validation

```python
from pydantic import BaseModel

class MyInput(BaseModel):
    company_name: str
    limit: int = 10

@forge.step(input_model=MyInput, input_key="request")
async def my_step(ctx):
    # Input is validated before step runs
    ...
```

## Troubleshooting

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for common issues and solutions.
