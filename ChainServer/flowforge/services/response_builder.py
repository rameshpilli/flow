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
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
#                           AGENT PROVIDER INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class AgentExecutionConfig:
    """Configuration for agent execution"""

    timeout_ms: int = 30000
    retry_count: int = 2
    retry_delay_ms: int = 1000
    retry_backoff: float = 2.0
    circuit_breaker_enabled: bool = True


@dataclass
class AgentExecutionMetrics:
    """Metrics collected during agent execution"""

    agent_name: str
    query: str
    success: bool
    duration_ms: float
    retry_count: int = 0
    error: str | None = None
    error_type: str | None = None
    items_returned: int = 0


class AgentProvider(ABC):
    """
    Abstract interface for agent providers.

    Implement this to swap between mock data, registered agents, or external services.

    Usage:
        # Use mock provider for testing
        provider = MockAgentProvider()
        service = ResponseBuilderService(agent_provider=provider)

        # Use registry provider for production
        provider = RegistryAgentProvider(forge=my_forge)
        service = ResponseBuilderService(agent_provider=provider)

        # With per-agent configuration
        provider = RegistryAgentProvider(
            agent_configs={
                "news": AgentExecutionConfig(timeout_ms=10000, retry_count=3),
                "earnings": AgentExecutionConfig(timeout_ms=5000, retry_count=1),
            }
        )
    """

    @abstractmethod
    async def execute(
        self,
        agent_name: str,
        query: str,
        config: AgentExecutionConfig | None = None,
        **kwargs,
    ) -> AgentResult:
        """
        Execute an agent with the given query.

        Args:
            agent_name: Name of the agent (e.g., "news", "sec_filing", "earnings")
            query: Query to execute
            config: Execution configuration (timeout, retry, etc.)
            **kwargs: Additional agent-specific parameters

        Returns:
            AgentResult with fetched data
        """
        pass

    def get_metrics(self) -> list[AgentExecutionMetrics]:
        """Get collected execution metrics"""
        return []

    def clear_metrics(self) -> None:
        """Clear collected metrics"""
        pass

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get summary statistics of agent execution metrics"""
        metrics = self.get_metrics()
        if not metrics:
            return {"total_executions": 0}

        by_agent: dict[str, list[AgentExecutionMetrics]] = {}
        for m in metrics:
            by_agent.setdefault(m.agent_name, []).append(m)

        summary = {
            "total_executions": len(metrics),
            "total_successes": sum(1 for m in metrics if m.success),
            "total_failures": sum(1 for m in metrics if not m.success),
            "avg_duration_ms": sum(m.duration_ms for m in metrics) / len(metrics),
            "by_agent": {},
        }

        for agent_name, agent_metrics in by_agent.items():
            successes = [m for m in agent_metrics if m.success]
            failures = [m for m in agent_metrics if not m.success]
            summary["by_agent"][agent_name] = {
                "executions": len(agent_metrics),
                "successes": len(successes),
                "failures": len(failures),
                "success_rate": len(successes) / len(agent_metrics) if agent_metrics else 0,
                "avg_duration_ms": sum(m.duration_ms for m in agent_metrics) / len(agent_metrics),
                "avg_items_returned": sum(m.items_returned for m in successes) / len(successes) if successes else 0,
                "retry_count": sum(m.retry_count for m in agent_metrics),
            }

        return summary


class RegistryAgentProvider(AgentProvider):
    """
    Agent provider that uses registered agents from the FlowForge registry.

    This is the production implementation that uses real agent instances.
    Supports per-agent timeout/retry configuration and collects execution metrics.
    """

    # Mapping from subquery agent names to registered agent names
    AGENT_NAME_MAPPING = {
        "sec_filing": "sec_filing_agent",
        "news": "news_agent",
        "earnings": "earnings_agent",
        "transcripts": "transcripts_agent",
    }

    def __init__(
        self,
        forge: Any | None = None,
        default_config: AgentExecutionConfig | None = None,
        agent_configs: dict[str, AgentExecutionConfig] | None = None,
    ):
        """
        Initialize the registry-based agent provider.

        Args:
            forge: FlowForge instance (uses global if not provided)
            default_config: Default execution config for all agents
            agent_configs: Per-agent execution configurations
        """
        self._forge = forge
        self._default_config = default_config or AgentExecutionConfig()
        self._agent_configs = agent_configs or {}
        self._metrics: list[AgentExecutionMetrics] = []
        self._agent_instances: dict[str, Any] = {}

    def _get_forge(self):
        """Get FlowForge instance (lazy initialization)"""
        if self._forge is None:
            from flowforge.core.forge import get_forge

            self._forge = get_forge()
        return self._forge

    def _get_config(self, agent_name: str) -> AgentExecutionConfig:
        """Get execution config for an agent"""
        return self._agent_configs.get(agent_name, self._default_config)

    def _get_agent_instance(self, agent_name: str) -> Any | None:
        """Get or create an agent instance"""
        # Map subquery agent name to registered agent name
        registered_name = self.AGENT_NAME_MAPPING.get(agent_name, agent_name)

        if registered_name not in self._agent_instances:
            forge = self._get_forge()
            agent = forge.get_agent(registered_name)
            if agent:
                self._agent_instances[registered_name] = agent
                logger.debug(f"Instantiated agent: {registered_name}")

        return self._agent_instances.get(registered_name)

    async def execute(
        self,
        agent_name: str,
        query: str,
        config: AgentExecutionConfig | None = None,
        **kwargs,
    ) -> AgentResult:
        """Execute an agent with retry and timeout handling"""
        exec_config = config or self._get_config(agent_name)
        start_time = time.perf_counter()
        last_error: Exception | None = None
        retry_count = 0

        for attempt in range(1 + exec_config.retry_count):
            if attempt > 0:
                retry_count = attempt
                delay_ms = exec_config.retry_delay_ms * (
                    exec_config.retry_backoff ** (attempt - 1)
                )
                logger.info(
                    f"Retrying agent {agent_name} (attempt {attempt + 1}/"
                    f"{exec_config.retry_count + 1})"
                )
                await asyncio.sleep(delay_ms / 1000)

            try:
                # Get agent instance
                agent = self._get_agent_instance(agent_name)

                if agent is None:
                    raise ValueError(
                        f"Agent '{agent_name}' not found in registry. "
                        f"Available mappings: {list(self.AGENT_NAME_MAPPING.keys())}"
                    )

                # Execute with timeout
                timeout_seconds = exec_config.timeout_ms / 1000
                result = await asyncio.wait_for(
                    agent.fetch(query, **kwargs),
                    timeout=timeout_seconds,
                )

                duration_ms = (time.perf_counter() - start_time) * 1000

                # Extract items from result
                items = []
                if isinstance(result.data, dict):
                    items = result.data.get("items", [])

                # Record metrics
                self._metrics.append(
                    AgentExecutionMetrics(
                        agent_name=agent_name,
                        query=query,
                        success=result.success,
                        duration_ms=duration_ms,
                        retry_count=retry_count,
                        error=result.error,
                        items_returned=len(items),
                    )
                )

                # Convert to service AgentResult format
                return AgentResult(
                    agent=agent_name,
                    success=result.success,
                    data=result.data,
                    items=items,
                    item_count=len(items),
                    query=query,
                    source=result.source,
                    duration_ms=duration_ms,
                    error=result.error,
                )

            except asyncio.TimeoutError:
                last_error = TimeoutError(
                    f"Agent {agent_name} timed out after {exec_config.timeout_ms}ms"
                )
                logger.warning(f"Agent {agent_name} timed out (attempt {attempt + 1})")

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Agent {agent_name} failed (attempt {attempt + 1}): {e}"
                )

        # All retries exhausted
        duration_ms = (time.perf_counter() - start_time) * 1000
        error_str = str(last_error) if last_error else "Unknown error"

        # Record failure metrics
        self._metrics.append(
            AgentExecutionMetrics(
                agent_name=agent_name,
                query=query,
                success=False,
                duration_ms=duration_ms,
                retry_count=retry_count,
                error=error_str,
                error_type=type(last_error).__name__ if last_error else None,
            )
        )

        return AgentResult(
            agent=agent_name,
            success=False,
            error=error_str,
            query=query,
            duration_ms=duration_ms,
        )

    def get_metrics(self) -> list[AgentExecutionMetrics]:
        """Get collected execution metrics"""
        return self._metrics.copy()

    def clear_metrics(self) -> None:
        """Clear collected metrics"""
        self._metrics.clear()


class MockAgentProvider(AgentProvider):
    """
    Mock agent provider for testing and development.

    Returns mock data without calling real agents.
    """

    def __init__(self, default_config: AgentExecutionConfig | None = None):
        self._default_config = default_config or AgentExecutionConfig()
        self._metrics: list[AgentExecutionMetrics] = []

    async def execute(
        self,
        agent_name: str,
        query: str,
        config: AgentExecutionConfig | None = None,
        **kwargs,
    ) -> AgentResult:
        """Return mock data based on agent type"""
        start_time = time.perf_counter()

        # Simulate some latency
        await asyncio.sleep(0.01)

        items = self._get_mock_data(agent_name, query)
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Record metrics
        self._metrics.append(
            AgentExecutionMetrics(
                agent_name=agent_name,
                query=query,
                success=True,
                duration_ms=duration_ms,
                items_returned=len(items),
            )
        )

        return AgentResult(
            agent=agent_name,
            success=True,
            data={"items": items},
            items=items,
            item_count=len(items),
            query=query,
            source=agent_name,
            duration_ms=duration_ms,
        )

    def _get_mock_data(self, agent_name: str, query: str) -> list[dict[str, Any]]:
        """Generate mock data for testing"""
        if agent_name == "sec_filing":
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

        elif agent_name == "news":
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

        elif agent_name == "earnings":
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

        elif agent_name == "transcripts":
            return [
                {
                    "type": "earnings_call",
                    "date": "2024-10-30",
                    "quarter": "Q3 2024",
                    "summary": f"Key highlights from {query} earnings call...",
                },
            ]

        return []

    def get_metrics(self) -> list[AgentExecutionMetrics]:
        return self._metrics.copy()

    def clear_metrics(self) -> None:
        self._metrics.clear()


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
        # Default: uses MockAgentProvider (for testing/development)
        service = ResponseBuilderService()
        output = await service.execute(context_output, prioritization_output)

        # Production: use RegistryAgentProvider with real agents
        provider = RegistryAgentProvider(forge=my_forge)
        service = ResponseBuilderService(agent_provider=provider)
        output = await service.execute(context_output, prioritization_output)

        # With per-agent configuration
        provider = RegistryAgentProvider(
            agent_configs={
                "news": AgentExecutionConfig(timeout_ms=10000, retry_count=3),
                "earnings": AgentExecutionConfig(timeout_ms=5000, retry_count=1),
            }
        )
        service = ResponseBuilderService(agent_provider=provider)

        # With LLM gateway
        from flowforge.services.llm_gateway import get_llm_client
        llm_client = get_llm_client()
        service = ResponseBuilderService(
            agent_provider=provider,
            llm_client=llm_client,
        )
        output = await service.execute(context_output, prioritization_output)

        # Get per-agent metrics after execution
        metrics = service.get_agent_metrics_summary()
        print(f"News agent success rate: {metrics['by_agent']['news']['success_rate']}")

    Or as a step in FlowForge:
        @forge.step(deps=[content_prioritization], produces=["response_builder_output"])
        async def response_builder(ctx):
            provider = RegistryAgentProvider(forge=ctx.get("forge"))
            service = ResponseBuilderService(
                agent_provider=provider,
                llm_client=ctx.get("llm_client"),
            )
            output = await service.execute(
                ctx.get("context_builder_output"),
                ctx.get("content_prioritization_output"),
            )
            ctx.set("response_builder_output", output)
            ctx.set("agent_metrics", service.get_agent_metrics_summary())
            return output.model_dump()
    """

    def __init__(
        self,
        max_parallel_agents: int = 5,
        collect_errors: bool = True,
        agent_provider: AgentProvider | None = None,
        llm_client: Any | None = None,
        use_llm_for_metrics: bool = True,
        use_llm_for_analysis: bool = True,
        use_llm_for_content: bool = True,
        # Legacy parameters (deprecated, use agent_provider instead)
        forge: Any | None = None,
    ):
        """
        Initialize the Response Builder service.

        Args:
            max_parallel_agents: Maximum agents to run in parallel
            collect_errors: Whether to collect errors instead of failing fast
            agent_provider: Provider for agent execution (default: MockAgentProvider)
            llm_client: LLMGatewayClient instance for LLM calls
            use_llm_for_metrics: Use LLM for financial metrics extraction
            use_llm_for_analysis: Use LLM for strategic analysis generation
            use_llm_for_content: Use LLM for final content generation
            forge: (Deprecated) Use agent_provider=RegistryAgentProvider(forge=...) instead
        """
        self.max_parallel_agents = max_parallel_agents
        self.collect_errors = collect_errors
        self.llm_client = llm_client
        self.use_llm_for_metrics = use_llm_for_metrics
        self.use_llm_for_analysis = use_llm_for_analysis
        self.use_llm_for_content = use_llm_for_content

        # Set up agent provider
        if agent_provider is not None:
            self._agent_provider = agent_provider
        elif forge is not None:
            # Legacy support: create RegistryAgentProvider from forge
            logger.warning(
                "Using 'forge' parameter is deprecated. "
                "Use agent_provider=RegistryAgentProvider(forge=...) instead."
            )
            self._agent_provider = RegistryAgentProvider(forge=forge)
        else:
            # Default to mock provider for testing/development
            self._agent_provider = MockAgentProvider()

    def get_agent_metrics(self) -> list[AgentExecutionMetrics]:
        """Get raw agent execution metrics"""
        return self._agent_provider.get_metrics()

    def get_agent_metrics_summary(self) -> dict[str, Any]:
        """Get summarized agent execution metrics (latency, error rates, etc.)"""
        return self._agent_provider.get_metrics_summary()

    def clear_agent_metrics(self) -> None:
        """Clear collected agent metrics"""
        self._agent_provider.clear_metrics()

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
        """
        Execute a single subquery against an agent using the configured provider.

        The provider handles:
        - Registry lookup (RegistryAgentProvider) or mock data (MockAgentProvider)
        - Per-agent timeout and retry configuration
        - Metrics collection for latency and error rates
        """
        logger.info(f"Executing agent {subquery.agent}: {subquery.query}")

        # Delegate to the agent provider
        return await self._agent_provider.execute(
            agent_name=subquery.agent,
            query=subquery.query,
        )

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
