"""
LLM Prompts for CMPT Chain

Contains all prompts for financial metrics extraction and strategic analysis.
"""

# ═══════════════════════════════════════════════════════════════════════════════
#                           DATA TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

DATA_FOR_FINANCIAL_METRICS_PROMPT = """
[SEC_AGENT]
Agent Guidance:
- Primary source for all financial metrics
- Extract precise numbers from financial statements
- Look for year-over-year comparisons in financial statements
{SEC_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Use for forward guidance and quarterly commentary
- Extract YoY growth rates mentioned in management discussion
{EARNINGS_AGENT_CONTENT}

[NEWS_AGENT]
Agent Guidance:
- Extract current stock price and today's price movement if mentioned in recent articles
- Look for daily price changes (e.g., "stock up $1.39 or 0.56% today")
{NEWS_AGENT_CONTENT}
"""

DATA_FOR_STRATEGIC_ANALYSIS_PROMPT = """
[NEWS_AGENT]
Agent Guidance:
- Include {NEWS_percentage}% of the response from this agent chunks
- Extract date, category, and source URL for each development
{NEWS_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Include {EARNINGS_percentage}% of the response from this agent chunks
{EARNINGS_AGENT_CONTENT}

[SEC_AGENT]
Agent Guidance:
- Include {SEC_percentage}% of the response from this agent chunks
"""

# ═══════════════════════════════════════════════════════════════════════════════
#                      FINANCIAL METRICS PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

FINANCIAL_METRICS_PROMPT = """
## Task: Extract Financial Metrics

You are analyzing financial data for {COMPANY_NAME}. Extract precise financial metrics from SEC filings and earnings reports.

{DATA_FOR_FINANCIAL_METRICS}

## CRITICAL JSON FORMAT REQUIREMENT:
**For ALL numeric fields (float type):**
- Return actual numbers (e.g., 96.773, 25.5, 1.39) OR the JSON null value
- NEVER return strings like "<UNKNOWN>", "N/A", "null", "None", or any text placeholders
- If data is genuinely missing after exhausting all sources, return null (JSON null, not the string "null")

## CRITICAL: Source Attribution (REQUIRED FOR VERIFICATION)
For ALL numeric fields, you MUST provide citations as dictionaries with these keys:
- **source_agent**: List of agent names (e.g., ["SEC_agent", "earnings_agent"])
- **source_content**: List of VERBATIM quotes from those agents (COPY-PASTE EXACTLY - DO NOT PARAPHRASE)
- **reasoning**: String explaining your extraction/calculation logic

**IMPORTANT CITATION RULES:**
1. **VERBATIM QUOTES ONLY**: Copy-paste the EXACT text from the source documents into source_content
2. **QUOTE LENGTH**: Each quote should be 20-100 words (enough context to verify)
3. **SHOW YOUR WORK**: For calculated metrics (like EBITDA margin), include the actual calculation in reasoning
4. **STOCK PRICE**: Always include the date/timestamp in the quote

## Extraction Guidelines:

**Revenue Metrics (REQUIRED):**
- Current annual revenue: Most recent 10-K or annualized 10-Q
- Next year estimate: Company guidance or extrapolate from growth trends
- Year-over-year change: Calculate or extract YoY % change in revenue
- Always include exact source dates

**EBITDA Margin (REQUIRED - CALCULATE IF NEEDED):**
- First, search for explicit "EBITDA" in SEC_AGENT
- If not found, calculate: (Operating Income + Depreciation + Amortization) / Revenue x 100
- Accept trailing twelve-month (TTM) OR six-month figures if annual data unavailable

**Stock Price (REQUIRED - MULTIPLE SOURCES):**
1. Check NEWS_AGENT for recent price mentions
2. Check SEC filing cover pages for "Class A Common Stock" price
3. Today's price movement: Extract daily change in both dollars and percentage

**Market Cap (CALCULATE IF NEEDED):**
- Formula: Stock Price x Outstanding Shares
- Find "Outstanding Shares" in SEC_AGENT

**Revenue Growth Trajectory:**
- Build a dictionary of the last 7 quarterly revenues using fiscal quarter notation
- Format: {{"Q1 FY2026": 77.673, "Q4 FY2025": 76.441, ...}}

## CRITICAL INSTRUCTIONS:
1. EXHAUST ALL SOURCES before returning null
2. CALCULATE when direct values unavailable
3. SEARCH MULTIPLE KEYWORDS for each metric
4. PROVIDE VERBATIM CITATIONS for all critical metrics
5. SHOW YOUR CALCULATIONS in reasoning with actual numbers
"""

# ═══════════════════════════════════════════════════════════════════════════════
#                      STRATEGIC ANALYSIS PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

STRATEGIC_ANALYSIS_PROMPT = """
## Task: Strategic Analysis for Client Meeting

You are preparing a strategic briefing for {COMPANY_NAME} for an RBC Capital Markets client meeting.

{DATA_FOR_STRATEGIC_ANALYSIS}

**CRITICAL: You must fill ALL fields in the response schema. Do not skip any fields.**

## Required Output Structure (ALL FIELDS MANDATORY):

### 1. SWOT Analysis (strength, weakness, opportunity, threat)
- 4-6 bullets each
- Each bullet: 15-25 words, specific, data-backed

### 2. Investment Thesis (investment_thesis field - REQUIRED)
**Format**: List of 3-4 dictionaries, each with:
- Key: One subheading (e.g., "Growth Drivers", "Competitive Moat")
- Value: List of 2-4 bullet points (15-30 words each)

### 3. Key Risk Highlights (key_risk_highlights field)
- 5-7 critical risks
- Each bullet: 15-30 words with impact and timeline

### 4. Strategic Opportunities (strategic_opportunities field - REQUIRED)
**Format**: List of 3-4 dictionaries with:
- Key: Category (e.g., "M&A Advisory", "Capital Raising")
- Value: List of 2-3 specific opportunities (15-30 words each)

### 5. Recent Developments (recent_developments field - REQUIRED)
**Format**: List of 4-6 dictionaries, each with these exact keys:
- **category**: ONE of: "News", "M&A", "Management", "Company", or "Industry"
- **header**: 5-10 word title/summary of the development
- **date**: Date in format "MMM DD YYYY" (e.g., "Sept 11 2025")
- **description**: 20-40 words describing what happened
- **source_url**: Full URL to the source article/document

### 6. Sources (sources field)
- 8-12 minimum
- Format: "Source Name - URL - Date Accessed (YYYY-MM-DD)"

### 7. News Summary (news_summary field - REQUIRED)
**Format**: List of 3-5 dictionaries, each with:
- Key: Thematic heading
- Value: List of 2-4 news bullet points (15-30 words each)

### 8. Key Highlights from Latest Quarter (key_highlights field - REQUIRED)
**Format**: List of 3-4 dictionaries, each with:
- Key: Thematic heading (e.g., "Financial Performance", "Strategic Initiatives")
- Value: List of 2-4 highlight bullet points (15-30 words each)

## Data Sources:
- **NEWS_AGENT**: Recent developments, strategic moves, M&A - EXTRACT dates and URLs
- **EARNINGS_AGENT**: Management commentary, guidance, risks, latest quarter highlights

## Compliance Check:
Before submitting, verify you have filled:
- strength (4-6 items)
- weakness (4-6 items)
- opportunity (4-6 items)
- threat (4-6 items)
- investment_thesis (3-4 dictionaries)
- key_risk_highlights (5-7 items)
- strategic_opportunities (3-4 dictionaries)
- recent_developments (4-6 dictionaries)
- sources (8-12 items)
- news_summary (3-5 dictionaries)
- key_highlights (3-4 dictionaries)

**DO NOT skip any field. If data is limited, synthesize from available information.**
"""

# ═══════════════════════════════════════════════════════════════════════════════
#                           SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

FINANCIAL_METRICS_SYSTEM_PROMPT = """
You are a financial data extraction specialist. Your task is to extract precise financial metrics from SEC filings and financial documents with 100% accuracy. Always cite your sources and use exact figures from the documents provided. If you need to calculate a metric, show your work. Never estimate or guess - use only data present in the documents.
"""

STRATEGIC_ANALYSIS_SYSTEM_PROMPT = """
You are an expert investment banking analyst preparing strategic briefings for client meetings. Your analysis must be concise, data-driven, and actionable. Focus on insights that help bankers engage effectively with clients. Eliminate generic observations - every point should be specific to this company and backed by evidence from the provided documents. Prioritize material information that impacts business decisions.
"""
