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
7. [File Reference](#file-reference)

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

## File Reference

### Core Framework

| File | Purpose |
|------|---------|
| `flowforge/__init__.py` | Package exports and usage examples |
| `flowforge/core/forge.py` | Main FlowForge class, decorators, execution |
| `flowforge/core/dag.py` | DAG builder and executor |
| `flowforge/core/context.py` | ChainContext for shared state |
| `flowforge/core/registry.py` | Agent, Step, Chain registries |
| `flowforge/core/decorators.py` | @agent, @step, @chain decorators |

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

**Key exports from `summarizer.py`:**
- `SummarizerMiddleware` - Middleware that triggers summarization on large outputs
- `LangChainSummarizer` - Core summarizer with stuff/map_reduce/refine strategies
- `SummarizationStrategy` - Enum: STUFF, MAP_REDUCE, REFINE
- `count_tokens()` - Token counting utility (tiktoken or fallback)
- `create_openai_summarizer()` - Factory for OpenAI-backed summarizer
- `create_anthropic_summarizer()` - Factory for Claude-backed summarizer

### Testing

| File | Purpose |
|------|---------|
| `flowforge/test_cmpt_chain.py` | End-to-end test suite |

---

## Running the Chain

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

---

## Next Steps for Production

1. **Replace Mock Data**: Update `_get_mock_agent_data()` in `response_builder.py` with real API calls
2. **Add LLM Summarization**: Configure `SummarizerMiddleware` with OpenAI/Claude
3. **Connect Real Extractors**: Update `context_builder.py` to call Foundation DB, LDAP, ZoomInfo
4. **Add Caching**: Use `CacheMiddleware` for expensive API calls
5. **Add Monitoring**: Use `LoggerMiddleware` for execution tracing
