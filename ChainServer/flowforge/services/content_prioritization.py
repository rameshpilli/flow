"""
Content Prioritization Service

Prioritizes data sources and generates subqueries:
- Temporal Source Prioritizer: Determines source priority based on earnings proximity
- Subquery Engine: Generates optimized queries for each data agent
- Topic Ranker: (deferred) Ranks topics by relevance
- Grid Config: Applies grid configuration for lookback periods

This is the second stage of the CMPT chain.
"""

import logging
from datetime import datetime
from typing import Any

from flowforge.services.models import (
    ContentPrioritizationOutput,
    ContextBuilderOutput,
    DataSource,
    PrioritizedSource,
    Priority,
    Subquery,
)

logger = logging.getLogger(__name__)


# Default grid configuration
DEFAULT_GRID_CONFIG = {
    "earnings_proximity_weeks": 2,
    "news_lookback_days": {
        "large_cap": 30,
        "mid_cap": 60,
        "small_cap": 90,
    },
    "filing_quarters": {
        "revenue": 8,
        "other": 4,
    },
    "max_news_results": 50,
    "max_filing_results": 20,
    "include_filing_types": ["10-K", "10-Q", "8-K"],
}


class ContentPrioritizationService:
    """
    Service for prioritizing content sources and generating subqueries.

    Usage:
        service = ContentPrioritizationService()
        output = await service.execute(context_builder_output)

    Or as a step in FlowForge:
        @forge.step(deps=[context_builder], produces=["content_prioritization_output"])
        async def content_prioritization(ctx):
            service = ContentPrioritizationService()
            context_output = ctx.get("context_builder_output")
            output = await service.execute(context_output)
            ctx.set("content_prioritization_output", output)
            return output.model_dump()
    """

    def __init__(
        self,
        grid_config: dict[str, Any] | None = None,
    ):
        """
        Initialize the Content Prioritization service.

        Args:
            grid_config: Grid configuration for lookback periods and limits
        """
        self.grid_config = grid_config or DEFAULT_GRID_CONFIG

    async def execute(
        self,
        context: ContextBuilderOutput,
    ) -> ContentPrioritizationOutput:
        """
        Execute content prioritization.

        Args:
            context: Output from context builder

        Returns:
            ContentPrioritizationOutput with prioritized sources and subqueries
        """
        start_time = datetime.now()
        timing: dict[str, float] = {}

        # Step 1: Prioritize sources based on temporal context
        prioritize_start = datetime.now()
        prioritized_sources = self._prioritize_sources(context)
        timing["prioritize_sources"] = (datetime.now() - prioritize_start).total_seconds() * 1000

        # Step 2: Generate subqueries for each enabled source
        subquery_start = datetime.now()
        subqueries = self._generate_subqueries(context, prioritized_sources)
        timing["generate_subqueries"] = (datetime.now() - subquery_start).total_seconds() * 1000

        # Group subqueries by agent
        subqueries_by_agent: dict[str, list[Subquery]] = {}
        for sq in subqueries:
            if sq.agent not in subqueries_by_agent:
                subqueries_by_agent[sq.agent] = []
            subqueries_by_agent[sq.agent].append(sq)

        # Generate prioritization reasoning
        reasoning = self._generate_reasoning(context, prioritized_sources)

        total_duration = (datetime.now() - start_time).total_seconds() * 1000
        timing["total"] = total_duration

        logger.info(f"Content prioritization completed in {total_duration:.2f}ms")

        return ContentPrioritizationOutput(
            prioritized_sources=prioritized_sources,
            subqueries=subqueries,
            subqueries_by_agent=subqueries_by_agent,
            grid_config=self.grid_config,
            prioritization_reasoning=reasoning,
            timing_ms=timing,
        )

    def _prioritize_sources(
        self,
        context: ContextBuilderOutput,
    ) -> list[PrioritizedSource]:
        """
        Prioritize data sources based on temporal context.

        Logic:
        - If near earnings (within X weeks): SEC filings + Earnings are PRIMARY
        - News is always included but priority varies by market cap
        - Transcripts are SECONDARY
        """
        sources: list[PrioritizedSource] = []
        temporal = context.temporal_context
        company = context.company_info

        # Determine if near earnings
        near_earnings = False
        if temporal and temporal.days_to_earnings is not None:
            weeks_to_earnings = temporal.days_to_earnings / 7
            near_earnings = weeks_to_earnings <= self.grid_config.get("earnings_proximity_weeks", 2)

        # Determine market cap for news lookback
        market_cap = company.market_cap.lower() if company and company.market_cap else "large_cap"
        market_cap_key = market_cap.replace(" ", "_").replace("-", "_")
        if market_cap_key not in self.grid_config.get("news_lookback_days", {}):
            market_cap_key = "large_cap"

        news_lookback = self.grid_config.get("news_lookback_days", {}).get(market_cap_key, 30)

        # SEC Filing - Always PRIMARY when near earnings
        sources.append(
            PrioritizedSource(
                source=DataSource.SEC_FILING,
                priority=Priority.PRIMARY if near_earnings else Priority.SECONDARY,
                enabled=True,
                lookback_quarters=self.grid_config.get("filing_quarters", {}).get("revenue", 8),
                max_results=self.grid_config.get("max_filing_results", 20),
                include_types=self.grid_config.get("include_filing_types", ["10-K", "10-Q", "8-K"]),
            )
        )

        # Earnings - PRIMARY when near earnings
        sources.append(
            PrioritizedSource(
                source=DataSource.EARNINGS,
                priority=Priority.PRIMARY if near_earnings else Priority.SECONDARY,
                enabled=True,
                lookback_quarters=4,
            )
        )

        # News - Priority based on market cap
        news_priority = Priority.PRIMARY if market_cap_key == "large_cap" else Priority.SECONDARY
        sources.append(
            PrioritizedSource(
                source=DataSource.NEWS,
                priority=news_priority,
                enabled=True,
                lookback_days=news_lookback,
                max_results=self.grid_config.get("max_news_results", 50),
            )
        )

        # Transcripts - Always SECONDARY
        sources.append(
            PrioritizedSource(
                source=DataSource.TRANSCRIPTS,
                priority=Priority.SECONDARY,
                enabled=True,
                lookback_quarters=4,
            )
        )

        # Sort by priority
        priority_order = {Priority.PRIMARY: 0, Priority.SECONDARY: 1, Priority.TERTIARY: 2}
        sources.sort(key=lambda s: priority_order.get(s.priority, 99))

        return sources

    def _generate_subqueries(
        self,
        context: ContextBuilderOutput,
        prioritized_sources: list[PrioritizedSource],
    ) -> list[Subquery]:
        """
        Generate subqueries for each enabled data source.

        Creates optimized queries based on company info and temporal context.
        """
        subqueries: list[Subquery] = []

        company_name = context.company_name or ""
        ticker = context.ticker or ""
        temporal = context.temporal_context

        for source in prioritized_sources:
            if not source.enabled:
                continue

            if source.source == DataSource.SEC_FILING:
                subqueries.append(
                    Subquery(
                        agent="sec_filing",
                        query=company_name,
                        params={
                            "ticker": ticker,
                            "quarters": source.lookback_quarters or 8,
                            "types": source.include_types or ["10-K", "10-Q"],
                            "max_results": source.max_results or 20,
                        },
                        priority=source.priority,
                        timeout_ms=30000,
                    )
                )

            elif source.source == DataSource.NEWS:
                subqueries.append(
                    Subquery(
                        agent="news",
                        query=company_name,
                        params={
                            "ticker": ticker,
                            "days": source.lookback_days or 30,
                            "sentiment": True,
                            "max_results": source.max_results or 50,
                        },
                        priority=source.priority,
                        timeout_ms=20000,
                    )
                )

            elif source.source == DataSource.EARNINGS:
                subqueries.append(
                    Subquery(
                        agent="earnings",
                        query=company_name,
                        params={
                            "ticker": ticker,
                            "include_estimates": True,
                            "include_historical": True,
                            "quarters": source.lookback_quarters or 4,
                        },
                        priority=source.priority,
                        timeout_ms=20000,
                    )
                )

            elif source.source == DataSource.TRANSCRIPTS:
                subqueries.append(
                    Subquery(
                        agent="transcripts",
                        query=company_name,
                        params={
                            "ticker": ticker,
                            "quarters": source.lookback_quarters or 4,
                            "types": ["earnings_call", "investor_day"],
                        },
                        priority=source.priority,
                        timeout_ms=30000,
                    )
                )

        return subqueries

    def _generate_reasoning(
        self,
        context: ContextBuilderOutput,
        prioritized_sources: list[PrioritizedSource],
    ) -> str:
        """Generate human-readable reasoning for prioritization decisions"""
        reasons = []

        company_name = context.company_name or "Unknown Company"
        temporal = context.temporal_context

        reasons.append(f"Prioritization for {company_name}:")

        if temporal and temporal.days_to_earnings is not None:
            days = temporal.days_to_earnings
            if days <= 14:
                reasons.append(
                    f"- Near earnings ({days} days): SEC filings and earnings data prioritized"
                )
            else:
                reasons.append(
                    f"- Not near earnings ({days} days): Standard prioritization applied"
                )
        else:
            reasons.append("- Earnings proximity unknown: Using default prioritization")

        if context.company_info and context.company_info.market_cap:
            reasons.append(f"- Market cap: {context.company_info.market_cap}")

        primary_sources = [
            s.source.value for s in prioritized_sources if s.priority == Priority.PRIMARY
        ]
        if primary_sources:
            reasons.append(f"- Primary sources: {', '.join(primary_sources)}")

        return "\n".join(reasons)
