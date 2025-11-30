"""
================================================================================
05_CAPIQ_INTEGRATION.PY - Advanced: Capital IQ Data Integration
================================================================================

PURPOSE:
    Demonstrates integrating external financial data APIs (Capital IQ)
    into your chains. Use this as a template for any data provider.

WHAT YOU'LL LEARN:
    1. Creating a Capital IQ agent with authentication
    2. Fetching company financials, estimates, transcripts
    3. Combining CapIQ data with other sources
    4. Building a comprehensive financial analysis pipeline
    5. Handling API rate limits and errors

PREREQUISITES:
    - Complete examples 01-04 first
    - Requires Capital IQ API credentials (uses mock data if unavailable)

NEXT STEPS:
    Explore the cmpt/ folder for a complete production example

RUN THIS EXAMPLE:
    python examples/05_capiq_integration.py
"""

import asyncio
import logging
from typing import Any

from agentorchestrator import ChainContext, AgentOrchestrator
from agentorchestrator.agents import AgentResult, BaseAgent
from agentorchestrator.middleware import LoggerMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 1. CREATE THE AGENTORCHESTRATOR INSTANCE
# ============================================================

ao = AgentOrchestrator(
    name="capiq_integration",
    version="1.0.0",
    max_parallel=5,
)

# Add middleware
ao.use_middleware(LoggerMiddleware())


# ============================================================
# 2. DEFINE THE CAPITAL IQ AGENT
# ============================================================


@ao.agent(
    name="capiq",
    version="1.0",
    description="Capital IQ data agent for financial metrics",
    capabilities=["financials", "estimates", "ownership", "events"],
)
class CapIQAgent(BaseAgent):
    """
    Agent for fetching data from S&P Capital IQ API.

    Supported data types:
    - financials: Historical financial statements (revenue, EBITDA, net income)
    - estimates: Analyst estimates and consensus (EPS, revenue estimates)
    - ownership: Institutional ownership data (top holders, ownership %)
    - events: Corporate events (earnings dates, dividends, M&A)

    Configuration:
        config = {
            "api_key": "your-capiq-api-key",
            "base_url": "https://api.capitaliq.com/v1",  # Optional
        }

    Usage:
        agent = ao.get_agent("capiq")
        result = await agent.fetch("AAPL", data_type="financials", periods=4)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.base_url = (config or {}).get("base_url", "https://api.capitaliq.com/v1")
        self.api_key = (config or {}).get("api_key")

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch data from Capital IQ.

        Args:
            query: Company identifier (ticker symbol or CIQ ID)
            **kwargs:
                data_type: Type of data to fetch
                    - "financials": Income statement, balance sheet data
                    - "estimates": Analyst consensus estimates
                    - "ownership": Institutional ownership breakdown
                    - "events": Upcoming corporate events
                periods: Number of periods (for financials)
                metrics: List of specific metrics to fetch

        Returns:
            AgentResult with Capital IQ data
        """
        import time

        start = time.perf_counter()

        data_type = kwargs.get("data_type", "financials")
        periods = kwargs.get("periods", 4)
        metrics = kwargs.get("metrics", ["revenue", "ebitda", "net_income"])

        try:
            # Mock data for demonstration
            # In production, replace with real API call:
            # data = await self._call_capiq_api(query, data_type, periods, metrics)
            data = self._get_mock_data(query, data_type, periods, metrics)

            duration = (time.perf_counter() - start) * 1000
            logger.info(f"CapIQ {data_type} for {query}: {duration:.1f}ms")

            return AgentResult(
                data=data,
                source="capiq",
                query=query,
                duration_ms=duration,
                metadata={"data_type": data_type, "periods": periods},
            )

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            logger.error(f"CapIQ error for {query}: {e}")
            return AgentResult(
                data=None,
                source="capiq",
                query=query,
                duration_ms=duration,
                error=str(e),
            )

    def _get_mock_data(
        self, query: str, data_type: str, periods: int, metrics: list[str]
    ) -> dict[str, Any]:
        """Generate mock data for testing."""

        if data_type == "financials":
            # Historical financial data
            return {
                "company": query,
                "currency": "USD",
                "periods": [
                    {
                        "period": "Q4 2024",
                        "period_end": "2024-12-31",
                        "revenue": 119.58e9,
                        "revenue_yoy": 0.04,
                        "gross_profit": 54.86e9,
                        "gross_margin": 0.459,
                        "ebitda": 42.31e9,
                        "ebitda_margin": 0.354,
                        "net_income": 33.92e9,
                        "net_margin": 0.284,
                        "eps_diluted": 2.18,
                    },
                    {
                        "period": "Q3 2024",
                        "period_end": "2024-09-30",
                        "revenue": 94.93e9,
                        "revenue_yoy": 0.06,
                        "gross_profit": 43.88e9,
                        "gross_margin": 0.462,
                        "ebitda": 31.24e9,
                        "ebitda_margin": 0.329,
                        "net_income": 24.52e9,
                        "net_margin": 0.258,
                        "eps_diluted": 1.64,
                    },
                    {
                        "period": "Q2 2024",
                        "period_end": "2024-06-30",
                        "revenue": 85.78e9,
                        "revenue_yoy": 0.05,
                        "gross_profit": 39.68e9,
                        "gross_margin": 0.463,
                        "ebitda": 28.12e9,
                        "ebitda_margin": 0.328,
                        "net_income": 21.45e9,
                        "net_margin": 0.250,
                        "eps_diluted": 1.40,
                    },
                    {
                        "period": "Q1 2024",
                        "period_end": "2024-03-31",
                        "revenue": 90.75e9,
                        "revenue_yoy": -0.04,
                        "gross_profit": 42.27e9,
                        "gross_margin": 0.466,
                        "ebitda": 30.54e9,
                        "ebitda_margin": 0.337,
                        "net_income": 23.64e9,
                        "net_margin": 0.260,
                        "eps_diluted": 1.53,
                    },
                ][:periods],
            }

        elif data_type == "estimates":
            # Analyst estimates
            return {
                "company": query,
                "currency": "USD",
                "as_of_date": "2025-01-15",
                "fiscal_year": "FY2025",
                "estimates": {
                    "eps": {
                        "consensus": 7.35,
                        "high": 8.10,
                        "low": 6.80,
                        "analyst_count": 42,
                        "revision_trend": "up",
                    },
                    "revenue": {
                        "consensus": 415.2e9,
                        "high": 430.0e9,
                        "low": 400.0e9,
                        "analyst_count": 38,
                        "revision_trend": "stable",
                    },
                },
                "next_quarter": {
                    "period": "Q1 2025",
                    "eps_estimate": 2.35,
                    "revenue_estimate": 118.5e9,
                },
                "recent_actuals": {
                    "period": "Q4 2024",
                    "eps_actual": 2.18,
                    "eps_estimate": 2.10,
                    "eps_surprise": 0.08,
                    "eps_surprise_pct": 0.038,
                    "revenue_actual": 119.58e9,
                    "revenue_estimate": 117.9e9,
                },
            }

        elif data_type == "ownership":
            # Institutional ownership
            return {
                "company": query,
                "as_of_date": "2024-12-31",
                "shares_outstanding": 15.44e9,
                "institutional_ownership": 0.72,
                "insider_ownership": 0.001,
                "top_institutional_holders": [
                    {"name": "Vanguard Group", "shares": 1.31e9, "pct": 0.085, "change_qoq": 0.02},
                    {"name": "BlackRock", "shares": 1.04e9, "pct": 0.067, "change_qoq": -0.01},
                    {
                        "name": "Berkshire Hathaway",
                        "shares": 0.91e9,
                        "pct": 0.059,
                        "change_qoq": 0.00,
                    },
                    {"name": "State Street", "shares": 0.62e9, "pct": 0.040, "change_qoq": 0.01},
                    {"name": "FMR LLC", "shares": 0.35e9, "pct": 0.023, "change_qoq": 0.03},
                ],
                "ownership_trend": {
                    "institutional_3m": 0.01,  # +1% change
                    "institutional_12m": 0.03,  # +3% change
                },
            }

        elif data_type == "events":
            # Corporate events
            return {
                "company": query,
                "upcoming_events": [
                    {
                        "type": "earnings",
                        "date": "2025-01-30",
                        "time": "16:30 ET",
                        "period": "Q1 FY2025",
                        "confirmed": True,
                    },
                    {
                        "type": "dividend",
                        "ex_date": "2025-02-07",
                        "pay_date": "2025-02-14",
                        "amount": 0.25,
                        "yield_annualized": 0.005,
                    },
                    {
                        "type": "conference",
                        "date": "2025-03-15",
                        "name": "Morgan Stanley TMT Conference",
                        "confirmed": False,
                    },
                ],
                "recent_events": [
                    {
                        "type": "earnings",
                        "date": "2024-10-31",
                        "period": "Q4 FY2024",
                        "result": "beat",
                    },
                ],
            }

        return {"company": query, "data_type": data_type, "_mock": True}

    async def _call_capiq_api(
        self, query: str, data_type: str, periods: int, metrics: list[str]
    ) -> dict[str, Any]:
        """
        Production implementation: Make actual API call to Capital IQ.

        Example implementation (requires httpx):
        ```python
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/{data_type}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "identifier": query,
                    "identifierType": "ticker",
                    "periods": periods,
                    "metrics": metrics,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
        ```
        """
        raise NotImplementedError("Replace with real Capital IQ API implementation")


# ============================================================
# 3. DEFINE ADDITIONAL AGENTS (for comparison)
# ============================================================


@ao.agent(name="sec_filing", version="1.0")
class SECFilingAgent(BaseAgent):
    """Mock SEC filing agent for demonstration"""

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        import time

        start = time.perf_counter()

        data = {
            "company": query,
            "filings": [
                {"type": "10-K", "filed": "2024-10-30", "period": "FY2024"},
                {"type": "10-Q", "filed": "2024-07-31", "period": "Q3 2024"},
            ],
        }

        return AgentResult(
            data=data,
            source="sec_filing",
            query=query,
            duration_ms=(time.perf_counter() - start) * 1000,
        )


@ao.agent(name="news", version="1.0")
class NewsAgent(BaseAgent):
    """Mock news agent for demonstration"""

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        import time

        start = time.perf_counter()

        data = {
            "company": query,
            "articles": [
                {"title": "Q4 Earnings Beat Expectations", "sentiment": 0.8, "date": "2024-10-31"},
                {"title": "New AI Features Announced", "sentiment": 0.7, "date": "2024-11-15"},
            ],
        }

        return AgentResult(
            data=data,
            source="news",
            query=query,
            duration_ms=(time.perf_counter() - start) * 1000,
        )


# ============================================================
# 4. DEFINE CHAIN STEPS
# ============================================================


@ao.step(name="extract_context", produces=["company_name", "ticker"])
async def extract_context(ctx: ChainContext):
    """Extract company context from request"""
    company = ctx.get("company_name", "Unknown Company")
    ticker = ctx.get("ticker", company[:4].upper())

    ctx.set("company_name", company)
    ctx.set("ticker", ticker)

    logger.info(f"Context: {company} ({ticker})")
    return {"company_name": company, "ticker": ticker}


@ao.step(
    name="fetch_capiq_financials",
    dependencies=["extract_context"],
    produces=["capiq_financials"],
)
async def fetch_capiq_financials(ctx: ChainContext):
    """Fetch financial statements from Capital IQ"""
    ticker = ctx.get("ticker")

    agent = ao.get_agent("capiq")
    result = await agent.fetch(
        ticker,
        data_type="financials",
        periods=4,
    )

    ctx.set("capiq_financials", result.data)
    return {"capiq_financials": result.data, "success": result.success}


@ao.step(
    name="fetch_capiq_estimates",
    dependencies=["extract_context"],
    produces=["capiq_estimates"],
)
async def fetch_capiq_estimates(ctx: ChainContext):
    """Fetch analyst estimates from Capital IQ"""
    ticker = ctx.get("ticker")

    agent = ao.get_agent("capiq")
    result = await agent.fetch(
        ticker,
        data_type="estimates",
    )

    ctx.set("capiq_estimates", result.data)
    return {"capiq_estimates": result.data, "success": result.success}


@ao.step(
    name="fetch_capiq_ownership",
    dependencies=["extract_context"],
    produces=["capiq_ownership"],
)
async def fetch_capiq_ownership(ctx: ChainContext):
    """Fetch ownership data from Capital IQ"""
    ticker = ctx.get("ticker")

    agent = ao.get_agent("capiq")
    result = await agent.fetch(
        ticker,
        data_type="ownership",
    )

    ctx.set("capiq_ownership", result.data)
    return {"capiq_ownership": result.data, "success": result.success}


@ao.step(
    name="fetch_capiq_events",
    dependencies=["extract_context"],
    produces=["capiq_events"],
)
async def fetch_capiq_events(ctx: ChainContext):
    """Fetch upcoming events from Capital IQ"""
    ticker = ctx.get("ticker")

    agent = ao.get_agent("capiq")
    result = await agent.fetch(
        ticker,
        data_type="events",
    )

    ctx.set("capiq_events", result.data)
    return {"capiq_events": result.data, "success": result.success}


@ao.step(
    name="fetch_sec_filings",
    dependencies=["extract_context"],
    produces=["sec_filings"],
)
async def fetch_sec_filings(ctx: ChainContext):
    """Fetch SEC filings"""
    ticker = ctx.get("ticker")

    agent = ao.get_agent("sec_filing")
    result = await agent.fetch(ticker)

    ctx.set("sec_filings", result.data)
    return {"sec_filings": result.data}


@ao.step(
    name="fetch_news",
    dependencies=["extract_context"],
    produces=["news_data"],
)
async def fetch_news(ctx: ChainContext):
    """Fetch recent news"""
    company = ctx.get("company_name")

    agent = ao.get_agent("news")
    result = await agent.fetch(company)

    ctx.set("news_data", result.data)
    return {"news_data": result.data}


@ao.step(
    name="aggregate_data",
    dependencies=[
        "fetch_capiq_financials",
        "fetch_capiq_estimates",
        "fetch_capiq_ownership",
        "fetch_capiq_events",
        "fetch_sec_filings",
        "fetch_news",
    ],
    produces=["aggregated_data"],
)
async def aggregate_data(ctx: ChainContext):
    """Aggregate all data sources"""
    aggregated = {
        "capiq": {
            "financials": ctx.get("capiq_financials"),
            "estimates": ctx.get("capiq_estimates"),
            "ownership": ctx.get("capiq_ownership"),
            "events": ctx.get("capiq_events"),
        },
        "sec": ctx.get("sec_filings"),
        "news": ctx.get("news_data"),
    }

    ctx.set("aggregated_data", aggregated)
    return {"aggregated_data": aggregated}


@ao.step(
    name="generate_analysis",
    dependencies=["aggregate_data"],
    produces=["analysis"],
)
async def generate_analysis(ctx: ChainContext):
    """Generate financial analysis from aggregated data"""
    company = ctx.get("company_name")
    data = ctx.get("aggregated_data", {})

    capiq = data.get("capiq", {})
    financials = capiq.get("financials", {})
    estimates = capiq.get("estimates", {})
    ownership = capiq.get("ownership", {})
    events = capiq.get("events", {})

    # Extract key metrics
    latest_period = (financials.get("periods") or [{}])[0]
    recent_actuals = estimates.get("recent_actuals", {})

    analysis = {
        "company": company,
        "summary": {
            "latest_quarter": latest_period.get("period", "N/A"),
            "revenue": latest_period.get("revenue"),
            "revenue_yoy": latest_period.get("revenue_yoy"),
            "eps": latest_period.get("eps_diluted"),
            "gross_margin": latest_period.get("gross_margin"),
            "net_margin": latest_period.get("net_margin"),
        },
        "estimates": {
            "next_quarter_eps": estimates.get("next_quarter", {}).get("eps_estimate"),
            "fy_eps_consensus": estimates.get("estimates", {}).get("eps", {}).get("consensus"),
            "analyst_count": estimates.get("estimates", {}).get("eps", {}).get("analyst_count"),
        },
        "earnings_performance": {
            "last_eps_surprise": recent_actuals.get("eps_surprise"),
            "last_eps_surprise_pct": recent_actuals.get("eps_surprise_pct"),
            "beat_or_miss": "beat" if (recent_actuals.get("eps_surprise", 0) > 0) else "miss",
        },
        "ownership": {
            "institutional_pct": ownership.get("institutional_ownership"),
            "top_holder": (ownership.get("top_institutional_holders") or [{}])[0].get("name"),
        },
        "upcoming_events": [
            e for e in (events.get("upcoming_events") or []) if e.get("type") == "earnings"
        ],
    }

    ctx.set("analysis", analysis)
    return {"analysis": analysis}


@ao.step(
    name="generate_report",
    dependencies=["generate_analysis"],
    produces=["final_report"],
)
async def generate_report(ctx: ChainContext):
    """Generate final markdown report"""
    analysis = ctx.get("analysis", {})
    company = analysis.get("company", "Unknown")
    summary = analysis.get("summary", {})
    estimates = analysis.get("estimates", {})
    performance = analysis.get("earnings_performance", {})
    ownership = analysis.get("ownership", {})
    events = analysis.get("upcoming_events", [])

    # Format numbers
    def fmt_b(n):
        return f"${n/1e9:.1f}B" if n else "N/A"

    def fmt_pct(n):
        return f"{n*100:.1f}%" if n else "N/A"

    report = f"""
# Financial Analysis: {company}

## Latest Quarter: {summary.get('latest_quarter', 'N/A')}

| Metric | Value |
|--------|-------|
| Revenue | {fmt_b(summary.get('revenue'))} |
| Revenue YoY | {fmt_pct(summary.get('revenue_yoy'))} |
| EPS | ${summary.get('eps', 'N/A')} |
| Gross Margin | {fmt_pct(summary.get('gross_margin'))} |
| Net Margin | {fmt_pct(summary.get('net_margin'))} |

## Analyst Estimates

- **FY EPS Consensus:** ${estimates.get('fy_eps_consensus', 'N/A')}
- **Next Quarter EPS:** ${estimates.get('next_quarter_eps', 'N/A')}
- **Analyst Coverage:** {estimates.get('analyst_count', 'N/A')} analysts

## Earnings Performance

- **Last Result:** {performance.get('beat_or_miss', 'N/A').upper()}
- **EPS Surprise:** ${performance.get('last_eps_surprise', 'N/A')} ({fmt_pct(performance.get('last_eps_surprise_pct'))})

## Ownership

- **Institutional:** {fmt_pct(ownership.get('institutional_pct'))}
- **Top Holder:** {ownership.get('top_holder', 'N/A')}

## Upcoming Events

"""
    for event in events[:3]:
        report += f"- **{event.get('type', 'Event').title()}:** {event.get('date', 'TBD')} ({event.get('period', '')})\n"

    report += "\n---\n*Generated by AgentOrchestrator with Capital IQ data*\n"

    ctx.set("final_report", report)
    return {"final_report": report}


# ============================================================
# 5. DEFINE THE CHAIN
# ============================================================


@ao.chain(
    name="capiq_analysis",
    version="1.0",
    description="Comprehensive financial analysis using Capital IQ data",
)
class CapIQAnalysisChain:
    """
    Financial analysis pipeline that combines Capital IQ data with other sources.

    Flow:
    ```
    extract_context
         │
         ├──► fetch_capiq_financials ──┐
         ├──► fetch_capiq_estimates ───┤
         ├──► fetch_capiq_ownership ───┼──► aggregate_data ──► generate_analysis ──► generate_report
         ├──► fetch_capiq_events ──────┤
         ├──► fetch_sec_filings ───────┤
         └──► fetch_news ──────────────┘
    ```

    Input:
        - company_name: Company name (e.g., "Apple Inc")
        - ticker: Stock ticker (e.g., "AAPL")

    Output:
        - final_report: Markdown formatted financial analysis
    """

    steps = [
        "extract_context",
        "fetch_capiq_financials",
        "fetch_capiq_estimates",
        "fetch_capiq_ownership",
        "fetch_capiq_events",
        "fetch_sec_filings",
        "fetch_news",
        "aggregate_data",
        "generate_analysis",
        "generate_report",
    ]


# ============================================================
# 6. MAIN EXECUTION
# ============================================================


async def main():
    print("\n" + "=" * 70)
    print("  AgentOrchestrator: Capital IQ Integration Demo")
    print("=" * 70 + "\n")

    # Validate definitions
    print("Validating chain definitions...")
    ao.check()
    print("  ✓ All definitions valid\n")

    # Show registered components
    print("Registered Components:")
    print(f"  Agents: {ao.list_agents()}")
    print(f"  Steps: {ao.list_steps()}")
    print(f"  Chains: {ao.list_chains()}")
    print()

    # Visualize the chain
    print("Chain DAG:")
    print(ao.visualize_chain("capiq_analysis"))
    print()

    # Execute the chain
    print("Executing chain...")
    print("-" * 50)

    result = await ao.run(
        "capiq_analysis",
        initial_data={
            "company_name": "Apple Inc",
            "ticker": "AAPL",
        },
    )

    # Display results
    print("\n" + "=" * 70)
    print("  EXECUTION RESULTS")
    print("=" * 70)

    print(f"\nRequest ID: {result['request_id']}")
    print(f"Success: {result['success']}")
    print(f"Duration: {result['duration_ms']:.2f}ms\n")

    print("Step Results:")
    for step_result in result["results"]:
        status = "✓" if step_result["success"] else "✗"
        print(f"  {status} {step_result['step']}: {step_result['duration_ms']:.2f}ms")

    # Show final report
    print("\n" + "=" * 70)
    print("  FINAL REPORT")
    print("=" * 70)

    final_report = result["context"]["data"].get("final_report", "No report generated")
    print(final_report)

    return result


if __name__ == "__main__":
    asyncio.run(main())
