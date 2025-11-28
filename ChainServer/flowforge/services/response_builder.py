"""
Response Builder Service

Executes data agents and builds the final response:
- Agent Executor: Runs subqueries against data agents in parallel
- Prompt Builder: Constructs LLM prompts from agent results
- Response Generator: Generates final meeting prep content

This is the third stage of the CMPT chain.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from flowforge.services.models import (
    AgentResult,
    ContentPrioritizationOutput,
    ContextBuilderOutput,
    Priority,
    ResponseBuilderOutput,
    Subquery,
)

logger = logging.getLogger(__name__)


class ResponseBuilderService:
    """
    Service for executing agents and building the final response.

    Usage:
        service = ResponseBuilderService()
        output = await service.execute(context_output, prioritization_output)

    Or as a step in FlowForge:
        @forge.step(deps=[content_prioritization], produces=["response_builder_output"])
        async def response_builder(ctx):
            service = ResponseBuilderService()
            output = await service.execute(
                ctx.get("context_builder_output"),
                ctx.get("content_prioritization_output"),
            )
            ctx.set("response_builder_output", output)
            return output.model_dump()
    """

    def __init__(
        self,
        max_parallel_agents: int = 5,
        collect_errors: bool = True,
        forge: Any | None = None,
    ):
        """
        Initialize the Response Builder service.

        Args:
            max_parallel_agents: Maximum agents to run in parallel
            collect_errors: Whether to collect errors instead of failing fast
            forge: FlowForge instance for getting agent references
        """
        self.max_parallel_agents = max_parallel_agents
        self.collect_errors = collect_errors
        self.forge = forge

    async def execute(
        self,
        context: ContextBuilderOutput,
        prioritization: ContentPrioritizationOutput,
    ) -> ResponseBuilderOutput:
        """
        Execute agents and build the final response.

        Args:
            context: Output from context builder
            prioritization: Output from content prioritization

        Returns:
            ResponseBuilderOutput with agent results and generated content
        """
        start_time = datetime.now()
        timing: dict[str, float] = {}
        errors: dict[str, str] = {}

        # Step 1: Execute agents in parallel
        agent_start = datetime.now()
        agent_results = await self._execute_agents(prioritization.subqueries)
        timing["agent_execution"] = (datetime.now() - agent_start).total_seconds() * 1000

        # Collect results and errors
        results_dict: dict[str, AgentResult] = {}
        all_items: list[dict[str, Any]] = []
        agents_succeeded = 0
        agents_failed = 0

        for result in agent_results:
            results_dict[result.agent] = result
            if result.success:
                agents_succeeded += 1
                all_items.extend(result.items)
            else:
                agents_failed += 1
                if result.error:
                    errors[result.agent] = result.error

        # Step 2: Extract financial metrics (would call LLM in production)
        metrics_start = datetime.now()
        financial_metrics = await self._extract_financial_metrics(context, results_dict)
        timing["financial_metrics"] = (datetime.now() - metrics_start).total_seconds() * 1000

        # Step 3: Generate strategic analysis (would call LLM in production)
        analysis_start = datetime.now()
        strategic_analysis = await self._generate_strategic_analysis(context, results_dict)
        timing["strategic_analysis"] = (datetime.now() - analysis_start).total_seconds() * 1000

        # Step 4: Build final prepared content
        content_start = datetime.now()
        prepared_content = self._build_prepared_content(
            context,
            financial_metrics,
            strategic_analysis,
        )
        timing["build_content"] = (datetime.now() - content_start).total_seconds() * 1000

        total_duration = (datetime.now() - start_time).total_seconds() * 1000
        timing["total"] = total_duration

        logger.info(
            f"Response builder completed in {total_duration:.2f}ms "
            f"({agents_succeeded} succeeded, {agents_failed} failed)"
        )

        return ResponseBuilderOutput(
            agent_results=results_dict,
            all_items=all_items,
            total_items=len(all_items),
            financial_metrics=financial_metrics,
            strategic_analysis=strategic_analysis,
            prepared_content=prepared_content,
            agents_succeeded=agents_succeeded,
            agents_failed=agents_failed,
            errors=errors,
            timing_ms=timing,
        )

    async def _execute_agents(
        self,
        subqueries: list[Subquery],
    ) -> list[AgentResult]:
        """
        Execute subqueries against data agents in parallel.

        Groups by priority and executes PRIMARY first, then SECONDARY.
        """
        results: list[AgentResult] = []

        # Group by priority
        primary = [sq for sq in subqueries if sq.priority == Priority.PRIMARY]
        secondary = [sq for sq in subqueries if sq.priority == Priority.SECONDARY]
        tertiary = [sq for sq in subqueries if sq.priority == Priority.TERTIARY]

        # Execute in priority order
        for priority_group in [primary, secondary, tertiary]:
            if not priority_group:
                continue

            # Execute group in parallel with semaphore
            semaphore = asyncio.Semaphore(self.max_parallel_agents)

            async def execute_with_semaphore(sq: Subquery) -> AgentResult:
                async with semaphore:
                    return await self._execute_single_agent(sq)

            group_results = await asyncio.gather(
                *[execute_with_semaphore(sq) for sq in priority_group],
                return_exceptions=self.collect_errors,
            )

            for sq, result in zip(priority_group, group_results):
                if isinstance(result, Exception):
                    results.append(
                        AgentResult(
                            agent=sq.agent,
                            success=False,
                            error=str(result),
                            query=sq.query,
                        )
                    )
                else:
                    results.append(result)

        return results

    async def _execute_single_agent(
        self,
        subquery: Subquery,
    ) -> AgentResult:
        """Execute a single subquery against an agent"""
        start = datetime.now()

        try:
            logger.info(f"Executing agent {subquery.agent}: {subquery.query}")

            # In production, this would call the actual agent
            # For now, return mock data based on agent type
            items = self._get_mock_agent_data(subquery)

            duration = (datetime.now() - start).total_seconds() * 1000

            return AgentResult(
                agent=subquery.agent,
                success=True,
                data={"items": items},
                items=items,
                item_count=len(items),
                query=subquery.query,
                source=subquery.agent,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (datetime.now() - start).total_seconds() * 1000
            logger.error(f"Agent {subquery.agent} failed: {e}")

            return AgentResult(
                agent=subquery.agent,
                success=False,
                error=str(e),
                query=subquery.query,
                duration_ms=duration,
            )

    def _get_mock_agent_data(self, subquery: Subquery) -> list[dict[str, Any]]:
        """Generate mock data for testing - replace with actual agent calls"""
        agent = subquery.agent
        query = subquery.query

        if agent == "sec_filing":
            return [
                {
                    "type": "10-K",
                    "filing_date": "2024-10-30",
                    "period": "FY2024",
                    "title": f"{query} Annual Report",
                    "url": f"https://sec.gov/filings/{query}/10-K",
                },
                {
                    "type": "10-Q",
                    "filing_date": "2024-07-30",
                    "period": "Q3 2024",
                    "title": f"{query} Quarterly Report",
                    "url": f"https://sec.gov/filings/{query}/10-Q",
                },
            ]

        elif agent == "news":
            return [
                {
                    "title": f"{query} Reports Strong Quarterly Results",
                    "source": "Reuters",
                    "date": "2024-11-15",
                    "sentiment": "positive",
                    "summary": f"Summary of news about {query}...",
                },
                {
                    "title": f"{query} Announces New Product Line",
                    "source": "Bloomberg",
                    "date": "2024-11-10",
                    "sentiment": "neutral",
                    "summary": f"Product announcement for {query}...",
                },
            ]

        elif agent == "earnings":
            return [
                {
                    "quarter": "Q3 2024",
                    "eps_actual": 1.25,
                    "eps_estimate": 1.20,
                    "beat": True,
                    "revenue_actual": "25.5B",
                    "revenue_estimate": "25.0B",
                },
            ]

        elif agent == "transcripts":
            return [
                {
                    "type": "earnings_call",
                    "date": "2024-10-30",
                    "quarter": "Q3 2024",
                    "summary": f"Key highlights from {query} earnings call...",
                },
            ]

        return []

    async def _extract_financial_metrics(
        self,
        context: ContextBuilderOutput,
        agent_results: dict[str, AgentResult],
    ) -> dict[str, Any]:
        """
        Extract financial metrics from agent results.

        In production, this would call an LLM to extract structured metrics.
        """
        # Mock implementation - in production would use LLM
        earnings = agent_results.get("earnings")
        if earnings and earnings.success and earnings.items:
            latest = earnings.items[0]
            return {
                "latest_quarter": latest.get("quarter"),
                "eps_beat": latest.get("beat", False),
                "eps_actual": latest.get("eps_actual"),
                "eps_estimate": latest.get("eps_estimate"),
                "revenue_actual": latest.get("revenue_actual"),
                "revenue_estimate": latest.get("revenue_estimate"),
            }

        return {}

    async def _generate_strategic_analysis(
        self,
        context: ContextBuilderOutput,
        agent_results: dict[str, AgentResult],
    ) -> dict[str, Any]:
        """
        Generate strategic analysis from agent results.

        In production, this would call an LLM to generate analysis.
        """
        # Mock implementation - in production would use LLM
        news = agent_results.get("news")
        sentiment_summary = "neutral"

        if news and news.success and news.items:
            sentiments = [item.get("sentiment", "neutral") for item in news.items]
            positive = sentiments.count("positive")
            negative = sentiments.count("negative")

            if positive > negative:
                sentiment_summary = "positive"
            elif negative > positive:
                sentiment_summary = "negative"

        return {
            "market_sentiment": sentiment_summary,
            "key_themes": ["earnings performance", "product innovation"],
            "risks": ["market competition", "regulatory changes"],
            "opportunities": ["market expansion", "new product launches"],
        }

    def _build_prepared_content(
        self,
        context: ContextBuilderOutput,
        financial_metrics: dict[str, Any],
        strategic_analysis: dict[str, Any],
    ) -> str:
        """Build the final prepared meeting content"""
        company_name = context.company_name or "Unknown Company"

        sections = [
            f"# Meeting Prep: {company_name}",
            "",
            "## Financial Highlights",
        ]

        if financial_metrics:
            if financial_metrics.get("eps_beat"):
                sections.append("- Latest quarter beat expectations")
            if financial_metrics.get("eps_actual"):
                sections.append(f"- EPS: ${financial_metrics['eps_actual']}")
            if financial_metrics.get("revenue_actual"):
                sections.append(f"- Revenue: {financial_metrics['revenue_actual']}")

        sections.extend(
            [
                "",
                "## Market Sentiment",
                f"- Overall sentiment: {strategic_analysis.get('market_sentiment', 'N/A')}",
            ]
        )

        if strategic_analysis.get("key_themes"):
            sections.append("- Key themes: " + ", ".join(strategic_analysis["key_themes"]))

        sections.extend(
            [
                "",
                "## Key Risks & Opportunities",
            ]
        )

        if strategic_analysis.get("risks"):
            sections.append("- Risks: " + ", ".join(strategic_analysis["risks"]))
        if strategic_analysis.get("opportunities"):
            sections.append("- Opportunities: " + ", ".join(strategic_analysis["opportunities"]))

        return "\n".join(sections)
