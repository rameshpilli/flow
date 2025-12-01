"""
Step 2: Content Prioritization Service

Prioritizes data sources based on temporal context (earnings proximity)
and generates subqueries for each data agent.

This is the second stage of the CMPT chain.
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any

from cmpt.services.models import (
    ContentPrioritizationOutput,
    ContextBuilderOutput,
    DataSource,
    PrioritizedSource,
    Priority,
    Subquery,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                           TOOL NAMES & CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

class ToolName(Enum):
    """Data agent tool names"""
    EARNINGS_TOOL = "earnings_agent"
    NEWS_TOOL = "news_agent"
    SEC_TOOL = "SEC_agent"


# Priority profiles for temporal source prioritization
PRIORITY_PROFILES = {
    "earnings_dominant": {ToolName.EARNINGS_TOOL.value: 50, ToolName.NEWS_TOOL.value: 30, ToolName.SEC_TOOL.value: 20},
    "news_dominant": {ToolName.EARNINGS_TOOL.value: 20, ToolName.NEWS_TOOL.value: 60, ToolName.SEC_TOOL.value: 20},
}

# Grid configuration
GRID_CONFIG = {
    "earnings_proximity_weeks": 1,
    "news_lookback_days": {"large_cap": 30, "mid_cap": 60, "small_cap": 90},
    "filing_quarters": {"revenue": 8, "other": 4},
    "max_news_results": 50,
    "max_filing_results": 20,
    "include_filing_types": ["10-K", "10-Q", "8-K"],
}


# ═══════════════════════════════════════════════════════════════════════════════
#                           SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class ContentPrioritizationService:
    """
    Service for prioritizing content sources and generating subqueries.

    Usage:
        service = ContentPrioritizationService()
        output = await service.execute(context_builder_output)
    """

    def __init__(self, grid_config: dict[str, Any] | None = None):
        self.grid_config = grid_config or GRID_CONFIG

    async def execute(self, context: ContextBuilderOutput) -> ContentPrioritizationOutput:
        """Execute content prioritization."""
        start_time = datetime.now()
        temporal = context.temporal_context

        # Get fiscal info
        meeting_date = temporal.meeting_date if temporal else datetime.now().strftime("%Y-%m-%d")
        company_name = context.company_name or "Unknown"
        fiscal_year = temporal.fiscal_year if temporal else str(datetime.now().year)
        fiscal_quarter = temporal.fiscal_quarter if temporal else str((datetime.now().month - 1) // 3 + 1)
        event_dt = temporal.event_dt if temporal else None

        # Step 1: Determine temporal priority
        temporal_priority = self._get_temporal_priority(meeting_date, event_dt)

        # Step 2: Prioritize sources
        prioritized_sources = self._prioritize_sources(context)

        # Step 3: Generate subqueries
        subqueries = self._generate_subqueries(context, prioritized_sources)
        subqueries_by_agent = {}
        for sq in subqueries:
            subqueries_by_agent.setdefault(sq.agent, []).append(sq)

        output = ContentPrioritizationOutput(
            prioritized_sources=prioritized_sources,
            subqueries=subqueries,
            subqueries_by_agent=subqueries_by_agent,
            priority_distribution=temporal_priority,  # Proper model field, survives serialization
            grid_config=self.grid_config,
            prioritization_reasoning=self._generate_reasoning(context, prioritized_sources),
            timing_ms={"total": (datetime.now() - start_time).total_seconds() * 1000},
        )
        return output

    def _get_temporal_priority(self, meeting_date: str, earnings_date: str | None) -> dict:
        """Get priority profile based on earnings proximity."""
        if not earnings_date:
            return PRIORITY_PROFILES["news_dominant"]

        try:
            meeting_dt = datetime.strptime(meeting_date, "%Y-%m-%d")
            earnings_dt = datetime.strptime(earnings_date, "%Y-%m-%d")
            days_diff = abs((earnings_dt - meeting_dt).days)
            window = self.grid_config.get("earnings_proximity_weeks", 1) * 7

            if days_diff <= window:
                return PRIORITY_PROFILES["earnings_dominant"]
        except (ValueError, TypeError):
            pass

        return PRIORITY_PROFILES["news_dominant"]

    def _prioritize_sources(self, context: ContextBuilderOutput) -> list[PrioritizedSource]:
        """Prioritize data sources based on temporal context."""
        temporal = context.temporal_context
        company = context.company_info

        # Determine if near earnings
        near_earnings = False
        if temporal and temporal.days_to_earnings is not None:
            near_earnings = temporal.days_to_earnings / 7 <= self.grid_config.get("earnings_proximity_weeks", 2)

        # Get market cap for news lookback (fallback)
        market_cap_key = (company.market_cap.lower().replace(" ", "_") if company and company.market_cap else "large_cap")
        if market_cap_key not in self.grid_config.get("news_lookback_days", {}):
            market_cap_key = "large_cap"
        default_news_lookback = self.grid_config["news_lookback_days"].get(market_cap_key, 30)

        # Use temporal context overrides if available, otherwise use GRID defaults
        news_lookback = temporal.news_lookback_days if temporal else default_news_lookback
        filing_quarters = temporal.filing_quarters if temporal else self.grid_config["filing_quarters"]["revenue"]

        sources = [
            PrioritizedSource(
                source=DataSource.SEC_FILING, priority=Priority.PRIMARY if near_earnings else Priority.SECONDARY,
                enabled=True, lookback_quarters=filing_quarters,
                max_results=self.grid_config["max_filing_results"], include_types=self.grid_config["include_filing_types"],
            ),
            PrioritizedSource(
                source=DataSource.EARNINGS, priority=Priority.PRIMARY if near_earnings else Priority.SECONDARY,
                enabled=True, lookback_quarters=4,
            ),
            PrioritizedSource(
                source=DataSource.NEWS, priority=Priority.PRIMARY if market_cap_key == "large_cap" else Priority.SECONDARY,
                enabled=True, lookback_days=news_lookback, max_results=self.grid_config["max_news_results"],
            ),
            PrioritizedSource(source=DataSource.TRANSCRIPTS, priority=Priority.SECONDARY, enabled=True, lookback_quarters=4),
        ]
        sources.sort(key=lambda s: {Priority.PRIMARY: 0, Priority.SECONDARY: 1, Priority.TERTIARY: 2}.get(s.priority, 99))
        return sources

    def _generate_subqueries(self, context: ContextBuilderOutput, sources: list[PrioritizedSource]) -> list[Subquery]:
        """Generate subqueries for each data source with temporal context."""
        company_name, ticker = context.company_name or "", context.ticker or ""
        temporal = context.temporal_context

        # Extract temporal context for agents
        fiscal_year = temporal.fiscal_year if temporal else str(datetime.now().year)
        fiscal_quarter = f"Q{temporal.fiscal_quarter}" if temporal and temporal.fiscal_quarter else "Q1"
        news_lookback = temporal.news_lookback_days if temporal else 30
        filing_quarters = temporal.filing_quarters if temporal else 8

        source_config = {
            DataSource.SEC_FILING: (
                ToolName.SEC_TOOL.value, 30000,
                lambda s: {
                    "ticker": ticker,
                    "quarters": s.lookback_quarters or filing_quarters,
                    "types": s.include_types or ["10-K", "10-Q"],
                    "max_results": s.max_results or 20,
                }
            ),
            DataSource.NEWS: (
                ToolName.NEWS_TOOL.value, 20000,
                lambda s: {
                    "ticker": ticker,
                    "days": s.lookback_days or news_lookback,
                    "sentiment": True,
                    "max_results": s.max_results or 50,
                }
            ),
            DataSource.EARNINGS: (
                ToolName.EARNINGS_TOOL.value, 20000,
                lambda s: {
                    "ticker": ticker,
                    "fiscal_year": fiscal_year,
                    "fiscal_quarter": fiscal_quarter,
                    "include_estimates": True,
                    "include_historical": True,
                    "quarters": s.lookback_quarters or 4,
                }
            ),
            DataSource.TRANSCRIPTS: (
                "transcripts", 30000,
                lambda s: {
                    "ticker": ticker,
                    "fiscal_year": fiscal_year,
                    "fiscal_quarter": fiscal_quarter,
                    "quarters": s.lookback_quarters or 4,
                    "types": ["earnings_call", "investor_day"],
                }
            ),
        }

        return [
            Subquery(agent=agent, query=company_name, params=params_fn(src), priority=src.priority, timeout_ms=timeout)
            for src in sources if src.enabled and src.source in source_config
            for agent, timeout, params_fn in [source_config[src.source]]
        ]

    def _generate_reasoning(self, context: ContextBuilderOutput, sources: list[PrioritizedSource]) -> str:
        """Generate human-readable prioritization reasoning."""
        reasons = [f"Prioritization for {context.company_name or 'Unknown Company'}:"]
        temporal = context.temporal_context

        if temporal and temporal.days_to_earnings is not None:
            days = temporal.days_to_earnings
            reasons.append(f"- {'Near' if days <= 14 else 'Not near'} earnings ({days} days)")
        else:
            reasons.append("- Earnings proximity unknown: Using default prioritization")

        if context.company_info and context.company_info.market_cap:
            reasons.append(f"- Market cap: {context.company_info.market_cap}")

        primary = [s.source.value for s in sources if s.priority == Priority.PRIMARY]
        if primary:
            reasons.append(f"- Primary sources: {', '.join(primary)}")

        return "\n".join(reasons)
