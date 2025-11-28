"""
Response Builder Service

Executes data agents and builds the final response:
- Agent Executor: Runs subqueries against data agents in parallel
- Prompt Builder: Constructs LLM prompts from agent results
- Response Generator: Generates final meeting prep content via LLM

This is the third stage of the CMPT chain.
"""

import asyncio
import json
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


# ═══════════════════════════════════════════════════════════════════════════════
#                           LLM PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

FINANCIAL_METRICS_PROMPT = """You are a financial analyst extracting key metrics from data.

Given the following data about {company_name}, extract structured financial metrics.

DATA:
{data}

Extract and return a JSON object with these fields (use null if not available):
{{
    "latest_quarter": "Q3 2024",
    "eps_actual": 1.25,
    "eps_estimate": 1.20,
    "eps_beat": true,
    "eps_surprise_pct": 4.17,
    "revenue_actual": "25.5B",
    "revenue_estimate": "25.0B",
    "revenue_beat": true,
    "revenue_growth_yoy": 12.5,
    "guidance": "Management raised FY guidance to...",
    "key_metrics": ["metric1", "metric2"]
}}

Return ONLY valid JSON, no other text."""

STRATEGIC_ANALYSIS_PROMPT = """You are a strategic analyst preparing meeting insights.

Given the following data about {company_name}, generate a strategic analysis.

COMPANY INFO:
{company_info}

NEWS & EVENTS:
{news_data}

SEC FILINGS:
{sec_data}

EARNINGS DATA:
{earnings_data}

Generate a strategic analysis with these sections (return as JSON):
{{
    "market_sentiment": "positive/negative/neutral",
    "sentiment_reasoning": "Brief explanation...",
    "key_themes": ["theme1", "theme2", "theme3"],
    "risks": ["risk1", "risk2"],
    "opportunities": ["opportunity1", "opportunity2"],
    "talking_points": ["point1", "point2", "point3"],
    "questions_to_ask": ["question1", "question2"]
}}

Return ONLY valid JSON, no other text."""

MEETING_PREP_PROMPT = """You are preparing a concise meeting brief for a client meeting.

COMPANY: {company_name}
MEETING DATE: {meeting_date}

FINANCIAL METRICS:
{financial_metrics}

STRATEGIC ANALYSIS:
{strategic_analysis}

RECENT NEWS:
{news_summary}

Generate a professional meeting preparation document with:
1. Executive Summary (2-3 sentences)
2. Key Financial Highlights (bullet points)
3. Market Sentiment & Themes
4. Risks to Discuss
5. Opportunities to Highlight
6. Suggested Talking Points
7. Questions to Consider

Keep it concise and actionable. Format in Markdown."""


class ResponseBuilderService:
    """
    Service for executing agents and building the final response.

    Usage:
        # Without LLM (mock/fallback mode)
        service = ResponseBuilderService()
        output = await service.execute(context_output, prioritization_output)

        # With LLM gateway
        from flowforge.services.llm_gateway import get_llm_client
        llm_client = get_llm_client()
        service = ResponseBuilderService(llm_client=llm_client)
        output = await service.execute(context_output, prioritization_output)

    Or as a step in FlowForge:
        @forge.step(deps=[content_prioritization], produces=["response_builder_output"])
        async def response_builder(ctx):
            service = ResponseBuilderService(llm_client=ctx.get("llm_client"))
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
        llm_client: Any | None = None,
        use_llm_for_metrics: bool = True,
        use_llm_for_analysis: bool = True,
        use_llm_for_content: bool = True,
    ):
        """
        Initialize the Response Builder service.

        Args:
            max_parallel_agents: Maximum agents to run in parallel
            collect_errors: Whether to collect errors instead of failing fast
            forge: FlowForge instance for getting agent references
            llm_client: LLMGatewayClient instance for LLM calls
            use_llm_for_metrics: Use LLM for financial metrics extraction
            use_llm_for_analysis: Use LLM for strategic analysis generation
            use_llm_for_content: Use LLM for final content generation
        """
        self.max_parallel_agents = max_parallel_agents
        self.collect_errors = collect_errors
        self.forge = forge
        self.llm_client = llm_client
        self.use_llm_for_metrics = use_llm_for_metrics
        self.use_llm_for_analysis = use_llm_for_analysis
        self.use_llm_for_content = use_llm_for_content

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
        if self.llm_client and self.use_llm_for_content:
            try:
                prepared_content = await self._build_prepared_content_with_llm(
                    context,
                    financial_metrics,
                    strategic_analysis,
                    results_dict,
                )
            except Exception as e:
                logger.warning(f"LLM content generation failed, using fallback: {e}")
                prepared_content = self._build_prepared_content(
                    context,
                    financial_metrics,
                    strategic_analysis,
                )
        else:
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

        Uses LLM if available, otherwise falls back to simple extraction.
        """
        # Collect all financial data
        earnings = agent_results.get("earnings")
        sec_filing = agent_results.get("sec_filing")

        # Build data for LLM
        data_parts = []
        if earnings and earnings.success and earnings.items:
            data_parts.append(f"EARNINGS:\n{json.dumps(earnings.items, indent=2)}")
        if sec_filing and sec_filing.success and sec_filing.items:
            data_parts.append(f"SEC FILINGS:\n{json.dumps(sec_filing.items, indent=2)}")

        # Use LLM if available and enabled
        if self.llm_client and self.use_llm_for_metrics and data_parts:
            try:
                company_name = context.company_name or "the company"
                prompt = FINANCIAL_METRICS_PROMPT.format(
                    company_name=company_name,
                    data="\n\n".join(data_parts),
                )

                response = await self.llm_client.generate_async(prompt)
                metrics = self._parse_json_response(response)
                if metrics:
                    logger.info(f"LLM extracted financial metrics for {company_name}")
                    return metrics

            except Exception as e:
                logger.warning(f"LLM metrics extraction failed, using fallback: {e}")

        # Fallback: simple extraction without LLM
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

        Uses LLM if available, otherwise falls back to simple heuristics.
        """
        news = agent_results.get("news")
        sec_filing = agent_results.get("sec_filing")
        earnings = agent_results.get("earnings")

        # Use LLM if available and enabled
        if self.llm_client and self.use_llm_for_analysis:
            try:
                company_name = context.company_name or "the company"

                # Build company info
                company_info = "N/A"
                if context.company_info:
                    company_info = json.dumps(context.company_info.model_dump(), indent=2)

                # Build data sections
                news_data = "No news data available"
                if news and news.success and news.items:
                    news_data = json.dumps(news.items, indent=2)

                sec_data = "No SEC filing data available"
                if sec_filing and sec_filing.success and sec_filing.items:
                    sec_data = json.dumps(sec_filing.items, indent=2)

                earnings_data = "No earnings data available"
                if earnings and earnings.success and earnings.items:
                    earnings_data = json.dumps(earnings.items, indent=2)

                prompt = STRATEGIC_ANALYSIS_PROMPT.format(
                    company_name=company_name,
                    company_info=company_info,
                    news_data=news_data,
                    sec_data=sec_data,
                    earnings_data=earnings_data,
                )

                response = await self.llm_client.generate_async(prompt)
                analysis = self._parse_json_response(response)
                if analysis:
                    logger.info(f"LLM generated strategic analysis for {company_name}")
                    return analysis

            except Exception as e:
                logger.warning(f"LLM strategic analysis failed, using fallback: {e}")

        # Fallback: simple heuristic analysis
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

    async def _build_prepared_content_with_llm(
        self,
        context: ContextBuilderOutput,
        financial_metrics: dict[str, Any],
        strategic_analysis: dict[str, Any],
        agent_results: dict[str, AgentResult],
    ) -> str:
        """Build the final prepared meeting content using LLM."""
        company_name = context.company_name or "Unknown Company"

        # Get meeting date from temporal context
        meeting_date = "TBD"
        if context.temporal_context and context.temporal_context.meeting_date:
            meeting_date = context.temporal_context.meeting_date

        # Build news summary
        news_summary = "No recent news available"
        news = agent_results.get("news")
        if news and news.success and news.items:
            news_items = [f"- {item.get('title', 'N/A')} ({item.get('date', 'N/A')})" for item in news.items[:5]]
            news_summary = "\n".join(news_items)

        prompt = MEETING_PREP_PROMPT.format(
            company_name=company_name,
            meeting_date=meeting_date,
            financial_metrics=json.dumps(financial_metrics, indent=2) if financial_metrics else "No data available",
            strategic_analysis=json.dumps(strategic_analysis, indent=2) if strategic_analysis else "No data available",
            news_summary=news_summary,
        )

        response = await self.llm_client.generate_async(prompt)
        logger.info(f"LLM generated meeting prep content for {company_name}")
        return response

    def _build_prepared_content(
        self,
        context: ContextBuilderOutput,
        financial_metrics: dict[str, Any],
        strategic_analysis: dict[str, Any],
    ) -> str:
        """Build the final prepared meeting content (fallback without LLM)."""
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

    def _parse_json_response(self, response: str) -> dict[str, Any] | None:
        """Parse JSON from LLM response, handling markdown code blocks."""
        try:
            # Try direct parse first
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        try:
            import re

            # Match ```json ... ``` or ``` ... ```
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
            if match:
                return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, AttributeError):
            pass

        # Try to find JSON object in response
        try:
            import re

            match = re.search(r"\{[\s\S]*\}", response)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, AttributeError):
            pass

        logger.warning(f"Failed to parse JSON from LLM response: {response[:200]}...")
        return None
