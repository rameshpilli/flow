"""
CMPT Chain Definition
=====================

This file defines the 3-stage CMPT pipeline using AgentOrchestrator decorators
with full utilization of framework features.

Pipeline:
    ┌─────────────────┐     ┌───────────────────────┐     ┌──────────────────┐
    │ Context Builder │ ──► │ Content Prioritization │ ──► │ Response Builder │
    └─────────────────┘     └───────────────────────┘     └──────────────────┘
          Stage 1                   Stage 2                      Stage 3

AgentOrchestrator Features Used:
    - @ao.step(): Define individual pipeline stages with dependencies
    - @ao.chain(): Define the chain that orchestrates steps
    - @produces/@consumes: Dataflow-based dependency resolution
    - state_model: Type-safe Pydantic state with IDE autocomplete
    - input_model/output_model: Automatic validation
    - Middleware stack: Logging, caching, metrics, circuit breaker, summarization
    - Retry configuration: Automatic retry with backoff
    - Event emission: Track pipeline progress
    - Error handling: Continue mode with partial results

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

from pydantic import BaseModel, Field

from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.decorators import produces, consumes

# LLM client import - optional for now
try:
    from agentorchestrator.services.llm_gateway import get_llm_client
except ImportError:
    def get_llm_client():
        """Placeholder when LLM gateway not available."""
        return None

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
    register_cmpt_agents,
    get_cmpt_agents,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                          TYPE-SAFE STATE MODEL
# ═══════════════════════════════════════════════════════════════════════════════


class CMPTState(BaseModel):
    """
    Type-safe state model for the CMPT chain.

    Provides IDE autocomplete and runtime validation for all
    data flowing through the pipeline.
    """
    # Stage 1 outputs
    context_output: ContextBuilderOutput | None = None
    company_name: str | None = None
    ticker: str | None = None

    # Stage 2 outputs
    prioritization_output: ContentPrioritizationOutput | None = None

    # Stage 3 outputs
    response_output: ResponseBuilderOutput | None = None
    final_response: ChainResponse | None = None

    # Metadata
    request_id: str | None = None
    use_mcp: bool = False

    class Config:
        arbitrary_types_allowed = True


# ═══════════════════════════════════════════════════════════════════════════════
#                          INPUT/OUTPUT MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class ContextBuilderInput(BaseModel):
    """Input model for context builder step"""
    request: dict[str, Any] = Field(..., description="Chain request data")


class ContextBuilderStepOutput(BaseModel):
    """Output model for context builder step"""
    step: str = "context_builder"
    company: str | None = None
    ticker: str | None = None
    has_temporal_context: bool = False


class ContentPrioritizationStepOutput(BaseModel):
    """Output model for content prioritization step"""
    step: str = "content_prioritization"
    sources_count: int = 0
    subqueries_count: int = 0
    reasoning: str | None = None


class ResponseBuilderStepOutput(BaseModel):
    """Output model for response builder step"""
    step: str = "response_builder"
    agents_succeeded: list[str] = Field(default_factory=list)
    agents_failed: list[str] = Field(default_factory=list)
    has_financial_metrics: bool = False
    has_strategic_analysis: bool = False
    has_prepared_content: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
#                          CHAIN REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════


def register_cmpt_chain(
    ao: AgentOrchestrator,
    use_mcp: bool = False,
    mcp_config: dict[str, str] | None = None,
    llm_client: Any | None = None,
    enable_cache: bool = True,
    enable_metrics: bool = True,
    enable_summarization: bool = True,
) -> None:
    """
    Register the CMPT chain with an AgentOrchestrator instance.

    This defines:
    1. Three steps (context_builder, content_prioritization, response_builder)
    2. One chain (cmpt_chain) that runs them in sequence with dataflow deps
    3. Comprehensive middleware stack for production use

    Args:
        ao: AgentOrchestrator instance to register with
        use_mcp: Whether to use MCP agents (production) or mock agents
        mcp_config: Optional MCP configuration with agent URLs
        llm_client: Optional LLM client for financial metrics/strategic analysis.
                    If not provided, attempts to get default client via get_llm_client().
        enable_cache: Enable caching middleware (default: True)
        enable_metrics: Enable metrics middleware (default: True)
        enable_summarization: Enable summarization for large responses (default: True)

    Example:
        ao = AgentOrchestrator(name="cmpt")
        register_cmpt_chain(ao, use_mcp=True, mcp_config={
            "sec_url": "http://sec-mcp:8000",
            "earnings_url": "http://earnings-mcp:8000",
            "news_url": "http://news-mcp:8000",
        })
    """

    # ══════════════════════════════════════════════════════════════════════════
    # MIDDLEWARE STACK
    # ══════════════════════════════════════════════════════════════════════════

    _configure_middleware(ao, enable_cache, enable_metrics, enable_summarization)

    # ══════════════════════════════════════════════════════════════════════════
    # REGISTER AGENTS
    # ══════════════════════════════════════════════════════════════════════════

    register_cmpt_agents(ao)
    logger.info("Registered CMPT agent classes with resilience config")

    # Get configured agent instances with runtime MCP URLs
    agents: dict[str, Any] = {}
    if use_mcp:
        agents = get_cmpt_agents(
            ao,
            sec_url=mcp_config.get("sec_url") if mcp_config else None,
            earnings_url=mcp_config.get("earnings_url") if mcp_config else None,
            news_url=mcp_config.get("news_url") if mcp_config else None,
            sec_token=mcp_config.get("sec_token") if mcp_config else None,
            earnings_token=mcp_config.get("earnings_token") if mcp_config else None,
            news_token=mcp_config.get("news_token") if mcp_config else None,
        )
        logger.info(f"Created MCP agent instances: {list(agents.keys())}")
    else:
        agents = get_cmpt_agents(ao)
        logger.info("Created mock agent instances (no MCP URLs)")

    # ══════════════════════════════════════════════════════════════════════════
    # INITIALIZE SERVICES
    # ══════════════════════════════════════════════════════════════════════════

    effective_llm_client = llm_client or get_llm_client()

    context_builder_service = ContextBuilderService()
    content_prioritization_service = ContentPrioritizationService()
    response_builder_service = ResponseBuilderService(
        llm_client=effective_llm_client,
        agents=agents,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 1: CONTEXT BUILDER
    # ══════════════════════════════════════════════════════════════════════════

    @produces("context_output", "company_name", "ticker")
    @ao.step(
        name="context_builder",
        description="Extract company info, temporal context, and personas from the request",
        state_model=CMPTState,
        retry=2,  # Retry twice on failure (API calls to Foundation service)
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

        Output (to ctx via @produces):
            context_output: ContextBuilderOutput
            company_name: str
            ticker: str
        """
        request_data = ctx.get("request", {})

        # Convert dict to ChainRequest if needed
        if isinstance(request_data, dict):
            request = ChainRequest(**request_data)
        else:
            request = request_data

        logger.info(f"[Step 1] Context Builder: {request.corporate_company_name}")

        # Execute the service
        output: ContextBuilderOutput = await context_builder_service.execute(request)

        # Store results in context for next steps (auto-tracked via @produces)
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

    @consumes("context_output")
    @produces("prioritization_output")
    @ao.step(
        name="content_prioritization",
        description="Prioritize data sources and generate subqueries based on context",
        state_model=CMPTState,
    )
    async def content_prioritization_step(ctx) -> dict[str, Any]:
        """
        Stage 2: Prioritize content sources and generate subqueries.

        Uses CMPT's GRID configuration to determine:
        - Which agents to query (SEC, Earnings, News)
        - Priority order based on earnings proximity
        - Subqueries for each agent

        Input (from ctx via @consumes):
            context_output: ContextBuilderOutput from Step 1

        Output (to ctx via @produces):
            prioritization_output: ContentPrioritizationOutput
        """
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

    @consumes("context_output", "prioritization_output")
    @produces("response_output", "final_response")
    @ao.step(
        name="response_builder",
        description="Execute agents, extract metrics, generate strategic analysis, build final response",
        state_model=CMPTState,
        timeout_ms=120000,  # 2 minutes for agent calls + LLM processing
        retry=1,  # Retry once on failure
    )
    async def response_builder_step(ctx) -> dict[str, Any]:
        """
        Stage 3: Build the final response.

        This step:
        1. Executes data agents to fetch SEC filings, earnings, news
        2. Uses LLM to extract financial metrics with citations
        3. Uses LLM to generate strategic analysis (SWOT, investment thesis)
        4. Builds the final meeting prep content

        Input (from ctx via @consumes):
            context_output: ContextBuilderOutput from Step 1
            prioritization_output: ContentPrioritizationOutput from Step 2

        Output (to ctx via @produces):
            response_output: ResponseBuilderOutput
            final_response: ChainResponse
        """
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
        dataflow=True,  # Enable automatic dependency resolution via @produces/@consumes
        error_handling="continue",  # Continue on errors to get partial results
    )
    class CMPTChain:
        """
        CMPT Chain: Client Meeting Prep Tool

        A 3-stage pipeline that prepares meeting materials for client meetings.
        Uses dataflow-based dependencies for automatic execution ordering.

        Pipeline:
            ┌─────────────────┐     ┌───────────────────────┐     ┌──────────────────┐
            │ context_builder │ ──► │ content_prioritization │ ──► │ response_builder │
            └─────────────────┘     └───────────────────────┘     └──────────────────┘
                @produces:              @consumes:                    @consumes:
                - context_output        - context_output              - context_output
                - company_name          @produces:                    - prioritization_output
                - ticker                - prioritization_output       @produces:
                                                                      - response_output
                                                                      - final_response

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


def _configure_middleware(
    ao: AgentOrchestrator,
    enable_cache: bool,
    enable_metrics: bool,
    enable_summarization: bool,
) -> None:
    """Configure the middleware stack for the CMPT chain."""

    # 1. Logger Middleware (priority 10 - runs first)
    from agentorchestrator.middleware import LoggerMiddleware
    ao.use(LoggerMiddleware(
        level="INFO",
        log_inputs=True,
        log_outputs=True,
        priority=10,
    ))
    logger.debug("Added LoggerMiddleware for structured logging")

    # 2. Circuit Breaker Middleware (priority 20 - fail fast on repeated failures)
    try:
        from agentorchestrator.middleware import CircuitBreakerMiddleware, MiddlewareCircuitBreakerConfig
        ao.use(CircuitBreakerMiddleware(
            configs={
                "response_builder": MiddlewareCircuitBreakerConfig(
                    failure_threshold=3,
                    recovery_timeout_ms=30000,
                ),
            },
            priority=20,
        ))
        logger.debug("Added CircuitBreakerMiddleware for resilience")
    except ImportError:
        logger.debug("CircuitBreakerMiddleware not available, skipping")

    # 3. Cache Middleware (priority 30 - check cache before expensive operations)
    if enable_cache:
        from agentorchestrator.middleware import CacheMiddleware
        ao.use(CacheMiddleware(
            ttl_seconds=300,  # 5 minute cache
            max_entries=100,
            applies_to=["context_builder"],  # Cache company lookups
            priority=30,
        ))
        logger.debug("Added CacheMiddleware for response caching")

    # 4. Token Manager Middleware (priority 40 - manage LLM context budget)
    try:
        from agentorchestrator.middleware import TokenManagerMiddleware
        ao.use(TokenManagerMiddleware(
            max_tokens=100000,  # 100K token budget for the chain
            auto_summarize=enable_summarization,
            priority=40,
        ))
        logger.debug("Added TokenManagerMiddleware for context management")
    except ImportError:
        logger.debug("TokenManagerMiddleware not available, skipping")

    # 5. Offload Middleware (priority 50 - handle large payloads)
    try:
        from agentorchestrator.middleware.offload import OffloadMiddleware
        from cmpt.domain_config import register_offload_extractors

        offload_middleware = OffloadMiddleware(
            default_threshold_bytes=100_000,  # 100KB threshold
            step_thresholds={
                "response_builder": 50_000,  # Lower threshold for response builder
            },
            priority=50,
        )
        register_offload_extractors(offload_middleware)
        ao.use(offload_middleware)
        logger.debug("Added OffloadMiddleware for large payload handling")
    except ImportError:
        logger.debug("OffloadMiddleware not available, skipping")

    # 6. Summarizer Middleware (priority 60 - summarize large responses)
    if enable_summarization:
        try:
            from agentorchestrator.middleware import SummarizerMiddleware, SummarizationStrategy
            from cmpt.domain_config import register_summarizer_prompts, DOMAIN_PROMPTS

            # Try to create a summarizer
            try:
                from agentorchestrator.middleware.summarizer import LangChainSummarizer, create_gateway_summarizer
                import os

                if os.getenv("LLM_SERVER_URL"):
                    summarizer = create_gateway_summarizer(
                        server_url=os.getenv("LLM_SERVER_URL"),
                        model_name=os.getenv("LLM_MODEL_NAME", "gpt-4"),
                    )
                    register_summarizer_prompts(type(summarizer))

                    ao.use(SummarizerMiddleware(
                        summarizer=summarizer,
                        strategy=SummarizationStrategy.MAP_REDUCE,
                        max_tokens=8000,
                        threshold_tokens=16000,
                        applies_to=["response_builder"],
                        priority=60,
                    ))
                    logger.debug("Added SummarizerMiddleware for large response handling")
            except Exception as e:
                logger.debug(f"Could not create summarizer: {e}")
        except ImportError:
            logger.debug("SummarizerMiddleware not available, skipping")

    # 7. Metrics Middleware (priority 90 - collect metrics last)
    if enable_metrics:
        try:
            from agentorchestrator.middleware import MetricsMiddleware
            ao.use(MetricsMiddleware(priority=90))
            logger.debug("Added MetricsMiddleware for observability")
        except ImportError:
            logger.debug("MetricsMiddleware not available, skipping")

    # 8. Citation Middleware (priority 100 - track sources for RAG)
    try:
        from agentorchestrator.middleware import CitationMiddleware
        ao.use(CitationMiddleware(
            applies_to=["response_builder"],
            priority=100,
        ))
        logger.debug("Added CitationMiddleware for source tracking")
    except ImportError:
        logger.debug("CitationMiddleware not available, skipping")


# ═══════════════════════════════════════════════════════════════════════════════
#                           CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


async def run_cmpt_chain(
    company_name: str,
    meeting_date: str | None = None,
    use_mcp: bool = False,
    mcp_config: dict[str, str] | None = None,
    llm_client: Any | None = None,
    enable_cache: bool = True,
    enable_metrics: bool = True,
) -> dict[str, Any]:
    """
    Convenience function to run the CMPT chain.

    Args:
        company_name: Name of the company (e.g., "Apple Inc")
        meeting_date: Optional meeting date (YYYY-MM-DD format)
        use_mcp: Whether to use MCP agents
        mcp_config: Optional MCP URLs
        llm_client: Optional LLM client for metrics/analysis generation
        enable_cache: Enable caching middleware (default: True)
        enable_metrics: Enable metrics collection (default: True)

    Returns:
        Chain execution result with context containing final_response

    Example:
        result = await run_cmpt_chain("Apple Inc", "2025-01-15")
        final = result["context"]["final_response"]
        print(final.prepared_content)
    """
    from datetime import datetime

    # Create orchestrator with isolation for this run
    ao = AgentOrchestrator(name="cmpt", isolated=True)

    # Register chain with all options
    register_cmpt_chain(
        ao,
        use_mcp=use_mcp,
        mcp_config=mcp_config,
        llm_client=llm_client,
        enable_cache=enable_cache,
        enable_metrics=enable_metrics,
    )

    # Validate the chain before running
    validation = ao.check()
    if not validation.valid:
        logger.warning(f"Chain validation warnings: {validation.warnings}")

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
        print(result["context"]["final_response"].prepared_content)
    """
    import asyncio

    return asyncio.run(run_cmpt_chain(company_name, meeting_date, use_mcp, mcp_config, llm_client))


# ═══════════════════════════════════════════════════════════════════════════════
#                           RESUMABLE EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════


async def run_cmpt_chain_resumable(
    company_name: str,
    meeting_date: str | None = None,
    use_mcp: bool = False,
    mcp_config: dict[str, str] | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    """
    Run CMPT chain with checkpointing for resumability.

    If the chain fails partway through, you can resume from the last checkpoint
    using the run_id returned in the result.

    Example:
        result = await run_cmpt_chain_resumable("Apple Inc")

        # If it fails, you can resume:
        if not result["success"]:
            resumed = await ao.resume(result["run_id"])
    """
    from datetime import datetime

    ao = AgentOrchestrator(name="cmpt_resumable", isolated=True)

    register_cmpt_chain(
        ao,
        use_mcp=use_mcp,
        mcp_config=mcp_config,
        llm_client=llm_client,
    )

    request = {
        "corporate_company_name": company_name,
        "meeting_datetime": meeting_date or datetime.now().strftime("%Y-%m-%d"),
    }

    # Use launch_resumable for checkpointing
    result = await ao.launch_resumable("cmpt_chain", {"request": request})

    return result
