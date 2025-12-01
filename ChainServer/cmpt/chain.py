"""
CMPT Chain Definition

This file defines the 3-stage CMPT pipeline using AgentOrchestrator decorators.

Pipeline:
    ┌─────────────────┐     ┌───────────────────────┐     ┌──────────────────┐
    │ Context Builder │ ──► │ Content Prioritization │ ──► │ Response Builder │
    └─────────────────┘     └───────────────────────┘     └──────────────────┘
          Stage 1                   Stage 2                      Stage 3

Usage:
    from agentorchestrator import AgentOrchestrator
    from cmpt.chain import register_cmpt_chain

    ao = AgentOrchestrator(name="cmpt")
    register_cmpt_chain(ao)

    result = await ao.launch("cmpt_chain", {
        "request": {
            "corporate_company_name": "Apple Inc",
            "meeting_datetime": "2025-01-15",
        }
    })
"""

import logging
from typing import Any

from agentorchestrator import AgentOrchestrator

from agentorchestrator.services.llm_gateway import get_llm_client

from cmpt.services import (
    # Models
    ChainRequest,
    ChainResponse,
    ContextBuilderOutput,
    ContentPrioritizationOutput,
    ResponseBuilderOutput,
    # Services
    ContextBuilderService,
    ContentPrioritizationService,
    ResponseBuilderService,
    # Agents
    create_cmpt_agents,
)

logger = logging.getLogger(__name__)


def register_cmpt_chain(
    ao: AgentOrchestrator,
    use_mcp: bool = False,
    mcp_config: dict[str, str] | None = None,
    llm_client: Any | None = None,
) -> None:
    """
    Register the CMPT chain with an AgentOrchestrator instance.

    This defines:
    1. Three steps (context_builder, content_prioritization, response_builder)
    2. One chain (cmpt_chain) that runs them in sequence

    Args:
        ao: AgentOrchestrator instance to register with
        use_mcp: Whether to use MCP agents (production) or mock agents
        mcp_config: Optional MCP configuration with agent URLs
        llm_client: Optional LLM client for financial metrics/strategic analysis.
                    If not provided, attempts to get default client via get_llm_client().

    Example:
        ao = AgentOrchestrator(name="cmpt")
        register_cmpt_chain(ao, use_mcp=True, mcp_config={
            "sec_url": "http://sec-mcp:8000",
            "earnings_url": "http://earnings-mcp:8000",
            "news_url": "http://news-mcp:8000",
        })
    """

    # ══════════════════════════════════════════════════════════════════════════
    # CREATE AGENTS (always created, MCP URLs optional)
    # ══════════════════════════════════════════════════════════════════════════

    # Create agents - if MCP URLs provided, they'll connect to real services
    # Otherwise they'll return "No MCP connector" errors (handled gracefully)
    agents: dict[str, Any] = {}
    if use_mcp:
        agents = create_cmpt_agents(
            sec_url=mcp_config.get("sec_url") if mcp_config else None,
            earnings_url=mcp_config.get("earnings_url") if mcp_config else None,
            news_url=mcp_config.get("news_url") if mcp_config else None,
        )
        for name, agent in agents.items():
            ao.register_agent(name, agent)
            logger.info(f"Registered MCP agent: {name}")

    # ══════════════════════════════════════════════════════════════════════════
    # INITIALIZE SERVICES (after agents are created)
    # ══════════════════════════════════════════════════════════════════════════

    # Get LLM client - use provided, or fall back to default/global client
    effective_llm_client = llm_client or get_llm_client()

    context_builder_service = ContextBuilderService()
    content_prioritization_service = ContentPrioritizationService()
    # Pass agents to ResponseBuilderService so it can execute them
    response_builder_service = ResponseBuilderService(
        llm_client=effective_llm_client,
        agents=agents,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 1: CONTEXT BUILDER
    # ══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="context_builder",
        description="Extract company info, temporal context, and personas from the request",
        produces=["context_output", "company_name", "ticker"],
    )
    async def context_builder_step(ctx) -> dict[str, Any]:
        """
        Stage 1: Build context from the incoming request.

        Extracts:
        - Company info (name, ticker, industry, sector)
        - Temporal context (fiscal quarter, earnings dates, meeting date)
        - Personas (RBC employee info, client contacts)

        Input (from ctx):
            request: dict with corporate_company_name, meeting_datetime, etc.

        Output (to ctx):
            context_output: ContextBuilderOutput
            company_name: str
            ticker: str
        """
        # Get request from context
        request_data = ctx.get("request", {})

        # Convert dict to ChainRequest if needed
        if isinstance(request_data, dict):
            request = ChainRequest(**request_data)
        else:
            request = request_data

        logger.info(f"[Step 1] Context Builder: {request.corporate_company_name}")

        # Execute the service
        output: ContextBuilderOutput = await context_builder_service.execute(request)

        # Store results in context for next steps
        ctx.set("context_output", output)
        ctx.set("company_name", output.company_name)
        ctx.set("ticker", output.ticker)

        return {
            "step": "context_builder",
            "company": output.company_name,
            "ticker": output.ticker,
            "has_temporal_context": output.temporal_context is not None,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 2: CONTENT PRIORITIZATION
    # ══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="content_prioritization",
        description="Prioritize data sources and generate subqueries based on context",
        deps=["context_builder"],  # Depends on Step 1
        produces=["prioritization_output"],
    )
    async def content_prioritization_step(ctx) -> dict[str, Any]:
        """
        Stage 2: Prioritize content sources and generate subqueries.

        Uses CMPT's GRID configuration to determine:
        - Which agents to query (SEC, Earnings, News)
        - Priority order based on earnings proximity
        - Subqueries for each agent

        Input (from ctx):
            context_output: ContextBuilderOutput from Step 1

        Output (to ctx):
            prioritization_output: ContentPrioritizationOutput
        """
        # Get context from previous step
        context_output: ContextBuilderOutput = ctx.get("context_output")

        logger.info(f"[Step 2] Content Prioritization: {ctx.get('company_name')}")

        # Execute the service
        output: ContentPrioritizationOutput = await content_prioritization_service.execute(
            context_output
        )

        # Store results in context
        ctx.set("prioritization_output", output)

        return {
            "step": "content_prioritization",
            "sources_count": len(output.prioritized_sources),
            "subqueries_count": len(output.subqueries),
            "reasoning": output.prioritization_reasoning[:100] + "..." if output.prioritization_reasoning else None,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 3: RESPONSE BUILDER
    # ══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="response_builder",
        description="Execute agents, extract metrics, generate strategic analysis, build final response",
        deps=["content_prioritization"],  # Depends on Step 2
        produces=["response_output", "final_response"],
    )
    async def response_builder_step(ctx) -> dict[str, Any]:
        """
        Stage 3: Build the final response.

        This step:
        1. Executes data agents to fetch SEC filings, earnings, news
        2. Uses LLM to extract financial metrics with citations
        3. Uses LLM to generate strategic analysis (SWOT, investment thesis)
        4. Builds the final meeting prep content

        Input (from ctx):
            context_output: ContextBuilderOutput from Step 1
            prioritization_output: ContentPrioritizationOutput from Step 2

        Output (to ctx):
            response_output: ResponseBuilderOutput
            final_response: ChainResponse
        """
        # Get outputs from previous steps
        context_output: ContextBuilderOutput = ctx.get("context_output")
        prioritization_output: ContentPrioritizationOutput = ctx.get("prioritization_output")

        logger.info(f"[Step 3] Response Builder: {ctx.get('company_name')}")

        # Execute the service
        output: ResponseBuilderOutput = await response_builder_service.execute(
            context_output,
            prioritization_output,
        )

        # Build final response
        final_response = ChainResponse(
            company_name=output.company_name or ctx.get("company_name"),
            ticker=ctx.get("ticker"),
            financial_metrics=output.financial_metrics,
            strategic_analysis=output.strategic_analysis,
            prepared_content=output.prepared_content,
            agent_results={k: v.model_dump() for k, v in output.agent_results.items()},
            validation_results=output.validation_results,
            timing_ms=output.timing_ms,
        )

        # Store results in context
        ctx.set("response_output", output)
        ctx.set("final_response", final_response)

        return {
            "step": "response_builder",
            "agents_succeeded": output.agents_succeeded,
            "agents_failed": output.agents_failed,
            "has_financial_metrics": output.financial_metrics is not None,
            "has_strategic_analysis": output.strategic_analysis is not None,
            "has_prepared_content": output.prepared_content is not None,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # CHAIN DEFINITION
    # ══════════════════════════════════════════════════════════════════════════

    @ao.chain(
        name="cmpt_chain",
        description="Client Meeting Prep Tool - 3 stage pipeline for meeting preparation",
    )
    class CMPTChain:
        """
        CMPT Chain: Client Meeting Prep Tool

        A 3-stage pipeline that prepares meeting materials for client meetings.

        Pipeline:
            ┌─────────────────┐     ┌───────────────────────┐     ┌──────────────────┐
            │ context_builder │ ──► │ content_prioritization │ ──► │ response_builder │
            └─────────────────┘     └───────────────────────┘     └──────────────────┘

        Input:
            request: {
                "corporate_company_name": "Apple Inc",
                "meeting_datetime": "2025-01-15",
                "rbc_employee_email": "analyst@rbc.com",  # optional
            }

        Output:
            final_response: ChainResponse with:
                - financial_metrics: Extracted metrics with citations
                - strategic_analysis: SWOT, investment thesis, risks
                - prepared_content: Formatted meeting prep document
        """

        steps = ["context_builder", "content_prioritization", "response_builder"]


# ═══════════════════════════════════════════════════════════════════════════════
#                           CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


async def run_cmpt_chain(
    company_name: str,
    meeting_date: str | None = None,
    use_mcp: bool = False,
    mcp_config: dict[str, str] | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    """
    Convenience function to run the CMPT chain.

    Args:
        company_name: Name of the company (e.g., "Apple Inc")
        meeting_date: Optional meeting date (YYYY-MM-DD format)
        use_mcp: Whether to use MCP agents
        mcp_config: Optional MCP URLs
        llm_client: Optional LLM client for metrics/analysis generation

    Returns:
        Chain execution result

    Example:
        result = await run_cmpt_chain("Apple Inc", "2025-01-15")
        print(result["context"]["final_response"].prepared_content)
    """
    from datetime import datetime

    # Create orchestrator
    ao = AgentOrchestrator(name="cmpt", isolated=True)

    # Register chain with LLM client
    register_cmpt_chain(ao, use_mcp=use_mcp, mcp_config=mcp_config, llm_client=llm_client)

    # Build request
    request = {
        "corporate_company_name": company_name,
        "meeting_datetime": meeting_date or datetime.now().strftime("%Y-%m-%d"),
    }

    # Run chain
    result = await ao.launch("cmpt_chain", {"request": request})

    return result


def run_cmpt_chain_sync(
    company_name: str,
    meeting_date: str | None = None,
    use_mcp: bool = False,
    mcp_config: dict[str, str] | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    """
    Synchronous version of run_cmpt_chain.

    Example:
        result = run_cmpt_chain_sync("Apple Inc")
    """
    import asyncio

    return asyncio.run(run_cmpt_chain(company_name, meeting_date, use_mcp, mcp_config, llm_client))
