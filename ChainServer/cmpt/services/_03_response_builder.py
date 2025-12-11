"""
Response Builder Service

Stage 3 of the CMPT chain: Execute agents and build the final response.

This service uses AgentOrchestrator's agent framework (BaseAgent, ResilientAgent)
and LCEL chains for LLM interactions with built-in retry and type-safe parsing.
"""

import json
import logging
from datetime import datetime
from typing import Any

from agentorchestrator.agents.base import AgentResult as AOAgentResult

from cmpt.services.models import (
    AgentResult,
    ContentPrioritizationOutput,
    ContextBuilderOutput,
    FinancialMetricsResponse,
    ResponseBuilderOutput,
    StrategicAnalysisResponse,
    Subquery,
)
from cmpt.services.llm_prompts import (
    DATA_FOR_FINANCIAL_METRICS_PROMPT,
    DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
    FINANCIAL_METRICS_PROMPT,
    FINANCIAL_METRICS_SYSTEM_PROMPT,
    STRATEGIC_ANALYSIS_PROMPT,
    STRATEGIC_ANALYSIS_SYSTEM_PROMPT,
)
from cmpt.services._02_content_prioritization import ToolName

logger = logging.getLogger(__name__)


def combine_agent_chunks(agent_results: dict[str, AgentResult]) -> dict[str, str]:
    """Combine agent results into text chunks for LLM prompts."""
    result = {}
    for agent_name, agent_result in agent_results.items():
        if agent_result.success and agent_result.items:
            chunks = [json.dumps(item, indent=2) if isinstance(item, dict) else str(item)
                      for item in agent_result.items]
            result[agent_name] = "\n\n".join(chunks)
        elif agent_result.success and agent_result.data:
            result[agent_name] = json.dumps(agent_result.data, indent=2)
        else:
            result[agent_name] = ""
    return result


class ResponseBuilderService:
    """
    Stage 3: Build the final meeting prep response.

    This service:
    1. Executes data agents to fetch SEC filings, earnings, news
    2. Uses LCEL chains to extract financial metrics (with retry/fallback)
    3. Uses LCEL chains to generate strategic analysis (with retry/fallback)
    4. Builds the final prepared content

    Usage:
        # With LCEL chains (recommended)
        service = ResponseBuilderService(llm=my_langchain_llm)

        # With legacy LLM client (backward compatible)
        service = ResponseBuilderService(llm_client=my_legacy_client)

        output = await service.execute(context_output, prioritization_output)
    """

    def __init__(
        self,
        llm: Any | None = None,
        llm_client: Any | None = None,  # Legacy support
        agents: dict[str, Any] | None = None,
        fallback_llm: Any | None = None,
        retries: int = 3,
    ):
        """
        Initialize the response builder.

        Args:
            llm: LangChain chat model for LCEL chains (recommended)
            llm_client: Legacy LLM client (backward compatible)
            agents: Dictionary of agent name -> agent instance
            fallback_llm: Optional fallback LLM if primary fails
            retries: Number of retry attempts (default: 3)
        """
        self.llm = llm
        self.llm_client = llm_client  # Legacy support
        self.agents = agents or {}
        self.fallback_llm = fallback_llm
        self.retries = retries

        # Build LCEL chains if LLM is provided
        self._financial_metrics_chain = None
        self._strategic_analysis_chain = None

        if self.llm is not None:
            self._build_chains()

    def _build_chains(self) -> None:
        """Build LCEL chains for LLM interactions."""
        try:
            from agentorchestrator.llm import create_extraction_chain, ChainConfig

            config = ChainConfig(retries=self.retries)

            # Financial metrics extraction chain
            # Note: We use a simplified template here since we build the full prompt dynamically
            self._financial_metrics_chain = create_extraction_chain(
                prompt_template="{prompt}",
                response_model=FinancialMetricsResponse,
                llm=self.llm,
                system_prompt=FINANCIAL_METRICS_SYSTEM_PROMPT,
                fallback_llm=self.fallback_llm,
                config=config,
            )

            # Strategic analysis chain
            self._strategic_analysis_chain = create_extraction_chain(
                prompt_template="{prompt}",
                response_model=StrategicAnalysisResponse,
                llm=self.llm,
                system_prompt=STRATEGIC_ANALYSIS_SYSTEM_PROMPT,
                fallback_llm=self.fallback_llm,
                config=config,
            )

            logger.info("LCEL chains built successfully (with retry and fallback support)")

        except ImportError as e:
            logger.warning(f"Could not build LCEL chains: {e}. Falling back to legacy mode.")
            self._financial_metrics_chain = None
            self._strategic_analysis_chain = None

    async def execute(
        self,
        context: ContextBuilderOutput,
        prioritization: ContentPrioritizationOutput,
    ) -> ResponseBuilderOutput:
        """Execute agents and build the final response."""
        start_time = datetime.now()
        timing: dict[str, float] = {}
        errors: dict[str, str] = {}
        company_name = context.company_name or "Unknown Company"

        # Get priority distribution from proper model field
        priority_distribution = prioritization.priority_distribution or None

        # Step 1: Execute agents
        agent_start = datetime.now()
        agent_results = await self._execute_agents(prioritization.subqueries)
        timing["agent_execution"] = (datetime.now() - agent_start).total_seconds() * 1000

        # Collect results
        results_dict: dict[str, AgentResult] = {}
        all_items: list[dict[str, Any]] = []
        agents_succeeded = agents_failed = 0

        for result in agent_results:
            results_dict[result.agent] = result
            if result.success:
                agents_succeeded += 1
                all_items.extend(result.items)
            else:
                agents_failed += 1
                if result.error:
                    errors[result.agent] = result.error

        # Step 2: Combine agent chunks
        agent_chunks = combine_agent_chunks(results_dict)

        # Step 3: Extract financial metrics
        metrics_start = datetime.now()
        financial_metrics = await self._extract_financial_metrics(company_name, agent_chunks)
        timing["financial_metrics"] = (datetime.now() - metrics_start).total_seconds() * 1000

        # Step 4: Generate strategic analysis
        analysis_start = datetime.now()
        strategic_analysis = await self._generate_strategic_analysis(company_name, agent_chunks, priority_distribution)
        timing["strategic_analysis"] = (datetime.now() - analysis_start).total_seconds() * 1000

        # Step 5: Build final content
        content_start = datetime.now()
        prepared_content = self._build_prepared_content(company_name, financial_metrics, strategic_analysis)
        timing["build_content"] = (datetime.now() - content_start).total_seconds() * 1000

        timing["total"] = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"Response builder completed in {timing['total']:.0f}ms ({agents_succeeded} succeeded, {agents_failed} failed)")

        return ResponseBuilderOutput(
            agent_results=results_dict,
            all_items=all_items,
            total_items=len(all_items),
            financial_metrics=financial_metrics,
            strategic_analysis=strategic_analysis,
            prepared_content=prepared_content,
            parsed_data_agent_chunks=agent_chunks,
            agents_succeeded=agents_succeeded,
            agents_failed=agents_failed,
            company_name=company_name,
            errors=errors,
            timing_ms=timing,
        )

    async def _execute_agents(self, subqueries: list[Subquery]) -> list[AgentResult]:
        """Execute agents for each subquery concurrently with proper params.

        Note: Timeout/retry handling is delegated to ResilientAgent wrapper.
        We don't add another asyncio.wait_for here to avoid cutting retries short.
        The Subquery.timeout_ms is used to configure the ResilientAgent's timeout.
        """
        import asyncio

        async def fetch_one(sq: Subquery) -> AgentResult:
            """Fetch single agent with params from subquery."""
            agent = self.agents.get(sq.agent)
            if not agent:
                return self._get_mock_result(sq)

            try:
                # Pass subquery params to agent.fetch
                # ResilientAgent handles timeout/retries internally
                ao_result: AOAgentResult = await agent.fetch(sq.query, **sq.params)
                return AgentResult(
                    agent=sq.agent,
                    success=ao_result.success,
                    data=ao_result.data if isinstance(ao_result.data, dict) else {"items": ao_result.data},
                    items=ao_result.data if isinstance(ao_result.data, list) else [],
                    item_count=len(ao_result.data) if isinstance(ao_result.data, list) else 0,
                    query=sq.query,
                    source=ao_result.source,
                    duration_ms=ao_result.duration_ms,
                    error=ao_result.error,
                )
            except Exception as e:
                return AgentResult(agent=sq.agent, success=False, error=str(e), query=sq.query)

        # Execute all agents concurrently
        tasks = [fetch_one(sq) for sq in subqueries]
        return await asyncio.gather(*tasks)

    def _get_mock_result(self, sq: Subquery) -> AgentResult:
        """Return mock data for testing."""
        mock_data = {
            ToolName.SEC_TOOL.value: [{"type": "10-K", "filing_date": "2024-10-30", "title": f"{sq.query} Annual Report"}],
            ToolName.EARNINGS_TOOL.value: [{"quarter": "Q3 2024", "eps_actual": 1.25, "beat": True}],
            ToolName.NEWS_TOOL.value: [{"title": f"{sq.query} Reports Strong Results", "date": "2024-11-15"}],
        }
        items = mock_data.get(sq.agent, [])
        return AgentResult(agent=sq.agent, success=True, data={"items": items}, items=items, item_count=len(items), query=sq.query, source="mock")

    async def _extract_financial_metrics(self, company_name: str, agent_chunks: dict[str, str]) -> dict[str, Any]:
        """Extract financial metrics using LCEL chain or legacy client."""
        prompt = self._build_financial_metrics_prompt(company_name, agent_chunks)

        # Try LCEL chain first (recommended path)
        if self._financial_metrics_chain is not None:
            try:
                result: FinancialMetricsResponse = await self._financial_metrics_chain.ainvoke({"prompt": prompt})
                logger.debug("Financial metrics extracted via LCEL chain")
                return result.model_dump()
            except Exception as e:
                logger.warning(f"LCEL chain failed for financial metrics: {e}")
                # Fall through to legacy if LCEL fails

        # Legacy path (backward compatibility)
        if self.llm_client is not None:
            return await self._extract_financial_metrics_legacy(prompt)

        return {}

    async def _extract_financial_metrics_legacy(self, prompt: str) -> dict[str, Any]:
        """Legacy extraction using llm_client (backward compatibility)."""
        try:
            if hasattr(self.llm_client, 'generate_structured_async'):
                response = await self.llm_client.generate_structured_async(
                    prompt=prompt,
                    system_prompt=FINANCIAL_METRICS_SYSTEM_PROMPT,
                    response_model=FinancialMetricsResponse
                )
                return response.model_dump() if hasattr(response, 'model_dump') else dict(response)
            else:
                response = await self.llm_client.generate_async(
                    f"{FINANCIAL_METRICS_SYSTEM_PROMPT}\n\n{prompt}"
                )
                return self._parse_json(response) or {}
        except Exception as e:
            logger.warning(f"Legacy LLM metrics extraction failed: {e}")
            return {}

    async def _generate_strategic_analysis(
        self, company_name: str, agent_chunks: dict[str, str], priority_distribution: dict[str, int] | None
    ) -> dict[str, Any]:
        """Generate strategic analysis using LCEL chain or legacy client."""
        prompt = self._build_strategic_analysis_prompt(company_name, agent_chunks, priority_distribution)

        # Try LCEL chain first (recommended path)
        if self._strategic_analysis_chain is not None:
            try:
                result: StrategicAnalysisResponse = await self._strategic_analysis_chain.ainvoke({"prompt": prompt})
                logger.debug("Strategic analysis generated via LCEL chain")
                return result.model_dump()
            except Exception as e:
                logger.warning(f"LCEL chain failed for strategic analysis: {e}")
                # Fall through to legacy if LCEL fails

        # Legacy path (backward compatibility)
        if self.llm_client is not None:
            return await self._generate_strategic_analysis_legacy(prompt)

        return {"strength": [], "weakness": [], "opportunity": [], "threat": []}

    async def _generate_strategic_analysis_legacy(self, prompt: str) -> dict[str, Any]:
        """Legacy analysis using llm_client (backward compatibility)."""
        try:
            if hasattr(self.llm_client, 'generate_structured_async'):
                response = await self.llm_client.generate_structured_async(
                    prompt=prompt,
                    system_prompt=STRATEGIC_ANALYSIS_SYSTEM_PROMPT,
                    response_model=StrategicAnalysisResponse
                )
                return response.model_dump() if hasattr(response, 'model_dump') else dict(response)
            else:
                response = await self.llm_client.generate_async(
                    f"{STRATEGIC_ANALYSIS_SYSTEM_PROMPT}\n\n{prompt}"
                )
                return self._parse_json(response) or {}
        except Exception as e:
            logger.warning(f"Legacy LLM strategic analysis failed: {e}")
            return {"strength": [], "weakness": [], "opportunity": [], "threat": []}

    def _build_financial_metrics_prompt(self, company_name: str, agent_chunks: dict[str, str]) -> str:
        """Build the financial metrics extraction prompt."""
        data = DATA_FOR_FINANCIAL_METRICS_PROMPT.format(
            SEC_AGENT_CONTENT=agent_chunks.get(ToolName.SEC_TOOL.value, "No data"),
            EARNINGS_AGENT_CONTENT=agent_chunks.get(ToolName.EARNINGS_TOOL.value, "No data"),
            NEWS_AGENT_CONTENT=agent_chunks.get(ToolName.NEWS_TOOL.value, "No data"),
        )
        return FINANCIAL_METRICS_PROMPT.format(COMPANY_NAME=company_name, DATA_FOR_FINANCIAL_METRICS=data)

    def _build_strategic_analysis_prompt(
        self,
        company_name: str,
        agent_chunks: dict[str, str],
        priority_distribution: dict[str, int] | None = None,
    ) -> str:
        """Build the strategic analysis prompt."""
        if priority_distribution is None:
            priority_distribution = {
                ToolName.NEWS_TOOL.value: 60,
                ToolName.EARNINGS_TOOL.value: 20,
                ToolName.SEC_TOOL.value: 20
            }

        data = DATA_FOR_STRATEGIC_ANALYSIS_PROMPT.format(
            NEWS_percentage=priority_distribution.get(ToolName.NEWS_TOOL.value, 60),
            NEWS_AGENT_CONTENT=agent_chunks.get(ToolName.NEWS_TOOL.value, "No data"),
            EARNINGS_percentage=priority_distribution.get(ToolName.EARNINGS_TOOL.value, 20),
            EARNINGS_AGENT_CONTENT=agent_chunks.get(ToolName.EARNINGS_TOOL.value, "No data"),
            SEC_percentage=priority_distribution.get(ToolName.SEC_TOOL.value, 20),
        )
        return STRATEGIC_ANALYSIS_PROMPT.format(COMPANY_NAME=company_name, DATA_FOR_STRATEGIC_ANALYSIS=data)

    def _build_prepared_content(self, company_name: str, metrics: dict, analysis: dict) -> str:
        """Build markdown meeting prep content."""
        sections = [f"# Meeting Prep: {company_name}\n", "## Financial Highlights"]
        if metrics.get("current_annual_revenue"):
            sections.append(f"- Revenue: ${metrics['current_annual_revenue']}B")
        if metrics.get("stock_price"):
            sections.append(f"- Stock Price: ${metrics['stock_price']}")

        sections.append("\n## Strategic Analysis")
        if analysis.get("strength"):
            sections.append("**Strengths:** " + ", ".join(analysis["strength"][:3]))
        if analysis.get("opportunity"):
            sections.append("**Opportunities:** " + ", ".join(analysis["opportunity"][:3]))

        return "\n".join(sections)

    def _parse_json(self, response: str) -> dict | None:
        """Parse JSON from LLM response (legacy fallback only)."""
        import re
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass
        return None


# Keep module-level helper functions for backward compatibility
def build_financial_metrics_prompt(company_name: str, agent_chunks: dict[str, str]) -> str:
    """Build the financial metrics extraction prompt (deprecated, use service method)."""
    data = DATA_FOR_FINANCIAL_METRICS_PROMPT.format(
        SEC_AGENT_CONTENT=agent_chunks.get(ToolName.SEC_TOOL.value, "No data"),
        EARNINGS_AGENT_CONTENT=agent_chunks.get(ToolName.EARNINGS_TOOL.value, "No data"),
        NEWS_AGENT_CONTENT=agent_chunks.get(ToolName.NEWS_TOOL.value, "No data"),
    )
    return FINANCIAL_METRICS_PROMPT.format(COMPANY_NAME=company_name, DATA_FOR_FINANCIAL_METRICS=data)


def build_strategic_analysis_prompt(
    company_name: str,
    agent_chunks: dict[str, str],
    priority_distribution: dict[str, int] | None = None,
) -> str:
    """Build the strategic analysis prompt (deprecated, use service method)."""
    if priority_distribution is None:
        priority_distribution = {ToolName.NEWS_TOOL.value: 60, ToolName.EARNINGS_TOOL.value: 20, ToolName.SEC_TOOL.value: 20}

    data = DATA_FOR_STRATEGIC_ANALYSIS_PROMPT.format(
        NEWS_percentage=priority_distribution.get(ToolName.NEWS_TOOL.value, 60),
        NEWS_AGENT_CONTENT=agent_chunks.get(ToolName.NEWS_TOOL.value, "No data"),
        EARNINGS_percentage=priority_distribution.get(ToolName.EARNINGS_TOOL.value, 20),
        EARNINGS_AGENT_CONTENT=agent_chunks.get(ToolName.EARNINGS_TOOL.value, "No data"),
        SEC_percentage=priority_distribution.get(ToolName.SEC_TOOL.value, 20),
    )
    return STRATEGIC_ANALYSIS_PROMPT.format(COMPANY_NAME=company_name, DATA_FOR_STRATEGIC_ANALYSIS=data)
