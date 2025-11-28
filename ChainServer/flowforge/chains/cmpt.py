"""
Client Meeting Prep Chain (CMPT)

FlowForge integration for the CMPT chain services.

Usage:
    from flowforge import FlowForge
    from flowforge.chains.cmpt import create_cmpt_chain

    fg = FlowForge(name="cmpt")
    create_cmpt_chain(fg)

    # Validate the chain
    fg.check()

    # Run the chain
    result = await fg.launch("cmpt_chain", {
        "request": {
            "corporate_company_name": "Apple Inc",
            "meeting_datetime": "2025-01-15T10:00:00Z",
        }
    })
"""

import logging
from typing import Any

from flowforge.core.forge import FlowForge
from flowforge.services import (
    ChainRequest,
    ChainResponse,
    ContentPrioritizationService,
    ContextBuilderService,
    ResponseBuilderService,
)

logger = logging.getLogger(__name__)


def create_cmpt_chain(
    fg: FlowForge,
    context_builder_config: dict[str, Any] | None = None,
    content_prioritization_config: dict[str, Any] | None = None,
    response_builder_config: dict[str, Any] | None = None,
) -> None:
    """
    Create and register the CMPT chain with FlowForge.

    This registers:
    - 3 steps: context_builder, content_prioritization, response_builder
    - 1 chain: cmpt_chain

    Args:
        fg: FlowForge instance
        context_builder_config: Config for ContextBuilderService
        content_prioritization_config: Config for ContentPrioritizationService
        response_builder_config: Config for ResponseBuilderService
    """
    # Initialize services with optional config
    context_svc = ContextBuilderService(**(context_builder_config or {}))
    prioritization_svc = ContentPrioritizationService(**(content_prioritization_config or {}))
    response_svc = ResponseBuilderService(**(response_builder_config or {}))

    # Register services as resources (for access in steps)
    fg.register_resource("context_builder_service", context_svc)
    fg.register_resource("content_prioritization_service", prioritization_svc)
    fg.register_resource("response_builder_service", response_svc)

    # ══════════════════════════════════════════════════════════════════
    #                         STEP 1: Context Builder
    # ══════════════════════════════════════════════════════════════════

    @fg.step(
        name="context_builder",
        produces=["context_builder_output"],
        description="Extracts company, temporal, and persona context from the request",
        group="cmpt",
        timeout_ms=30000,
    )
    async def context_builder(ctx):
        """
        Context Builder Step

        Extracts:
        - Company info (from foundation service)
        - Temporal context (earnings dates, fiscal periods)
        - RBC persona (from LDAP)
        - Corporate client personas (from ZoomInfo)
        """
        # Get request from context
        request_data = ctx.get("request", {})

        # Convert to ChainRequest model with validation
        if isinstance(request_data, ChainRequest):
            request = request_data
        else:
            request = ChainRequest(**request_data)

        # Execute the service
        svc = fg.get_resource("context_builder_service")
        output = await svc.execute(request)

        # Store output in context
        ctx.set("context_builder_output", output)

        logger.info(f"Context builder completed: company={output.company_name}")

        return output.model_dump()

    # ══════════════════════════════════════════════════════════════════
    #                    STEP 2: Content Prioritization
    # ══════════════════════════════════════════════════════════════════

    @fg.step(
        name="content_prioritization",
        deps=[context_builder],
        produces=["content_prioritization_output"],
        description="Prioritizes data sources and generates subqueries",
        group="cmpt",
        timeout_ms=20000,
    )
    async def content_prioritization(ctx):
        """
        Content Prioritization Step

        Determines:
        - Source priority based on earnings proximity
        - Subqueries for each data agent
        - Lookback periods based on grid config
        """
        # Get context builder output
        context_output = ctx.get("context_builder_output")

        # Execute the service
        svc = fg.get_resource("content_prioritization_service")
        output = await svc.execute(context_output)

        # Store output in context
        ctx.set("content_prioritization_output", output)

        logger.info(
            f"Content prioritization completed: " f"{len(output.subqueries)} subqueries generated"
        )

        return output.model_dump()

    # ══════════════════════════════════════════════════════════════════
    #                      STEP 3: Response Builder
    # ══════════════════════════════════════════════════════════════════

    @fg.step(
        name="response_builder",
        deps=[content_prioritization],
        produces=["response_builder_output", "final_response"],
        description="Executes agents and builds the final response",
        group="cmpt",
        timeout_ms=60000,
    )
    async def response_builder(ctx):
        """
        Response Builder Step

        Executes:
        - Data agents in parallel (based on priority)
        - Financial metrics extraction
        - Strategic analysis generation
        - Final content building
        """
        # Get outputs from previous steps
        context_output = ctx.get("context_builder_output")
        prioritization_output = ctx.get("content_prioritization_output")

        # Execute the service
        svc = fg.get_resource("response_builder_service")
        output = await svc.execute(context_output, prioritization_output)

        # Store outputs in context
        ctx.set("response_builder_output", output)

        # Build final response using the actual ChainResponse structure
        final_response = ChainResponse(
            success=True,
            context_builder=context_output.model_dump(),
            content_prioritization=prioritization_output.model_dump(),
            response_builder=output.model_dump(),
            timings={
                "context_builder": context_output.timing_ms.get("total", 0),
                "content_prioritization": prioritization_output.timing_ms.get("total", 0),
                "response_builder": output.timing_ms.get("total", 0),
            },
        )

        ctx.set("final_response", final_response)

        logger.info(
            f"Response builder completed: "
            f"{output.agents_succeeded} agents succeeded, "
            f"{output.agents_failed} failed"
        )

        return final_response.model_dump()

    # ══════════════════════════════════════════════════════════════════
    #                         REGISTER CHAIN
    # ══════════════════════════════════════════════════════════════════

    @fg.chain(
        name="cmpt_chain",
        description="Client Meeting Prep Chain - prepares briefing materials for meetings",
        group="cmpt",
    )
    class CMPTChain:
        """
        Client Meeting Prep Chain

        Stages:
        1. Context Builder - Extract meeting context
        2. Content Prioritization - Prioritize data sources
        3. Response Builder - Execute agents and build response
        """

        steps = [context_builder, content_prioritization, response_builder]

    logger.info("CMPT chain registered with FlowForge")


# ══════════════════════════════════════════════════════════════════════════════
#                    CONVENIENCE CLASS FOR DIRECT USAGE
# ══════════════════════════════════════════════════════════════════════════════


class CMPTChain:
    """
    Convenience wrapper for running the CMPT chain.

    Usage:
        chain = CMPTChain()

        # Validate
        chain.check()

        # Run
        result = await chain.run(
            corporate_company_name="Apple Inc",
            meeting_datetime="2025-01-15T10:00:00Z",
        )
    """

    def __init__(
        self,
        context_builder_config: dict[str, Any] | None = None,
        content_prioritization_config: dict[str, Any] | None = None,
        response_builder_config: dict[str, Any] | None = None,
    ):
        """Initialize the CMPT chain with FlowForge"""
        self.fg = FlowForge(name="cmpt", version="1.0.0")
        create_cmpt_chain(
            self.fg,
            context_builder_config,
            content_prioritization_config,
            response_builder_config,
        )

    def check(self) -> dict[str, Any]:
        """Validate the chain definition"""
        return self.fg.check("cmpt_chain")

    def list_defs(self) -> dict[str, Any]:
        """List all definitions"""
        return self.fg.list_defs()

    def graph(self, format: str = "ascii") -> str:
        """Generate DAG visualization"""
        return self.fg.graph("cmpt_chain", format)

    async def run(
        self,
        corporate_company_name: str | None = None,
        meeting_datetime: str | None = None,
        rbc_employee_email: str | None = None,
        corporate_client_email: str | None = None,
        corporate_client_names: str | None = None,
        **kwargs,
    ) -> ChainResponse:
        """
        Run the CMPT chain.

        Args:
            corporate_company_name: Name of the company for the meeting
            meeting_datetime: Meeting date/time (ISO format)
            rbc_employee_email: RBC employee email
            corporate_client_email: Client email
            corporate_client_names: Comma-separated client names

        Returns:
            ChainResponse with prepared content
        """
        request = ChainRequest(
            corporate_company_name=corporate_company_name,
            meeting_datetime=meeting_datetime,
            rbc_employee_email=rbc_employee_email,
            corporate_client_email=corporate_client_email,
            corporate_client_names=corporate_client_names,
            **kwargs,
        )

        result = await self.fg.launch("cmpt_chain", {"request": request.model_dump()})

        # The result structure: {"context": {"data": {...}, ...}, "results": [...]}
        context_data = result.get("context", {}).get("data", {})
        final_response_data = context_data.get("final_response")

        if isinstance(final_response_data, ChainResponse):
            return final_response_data
        elif isinstance(final_response_data, dict):
            return ChainResponse(**final_response_data)
        else:
            # Fallback: build response from context data
            ctx_builder = context_data.get("context_builder_output")
            if hasattr(ctx_builder, "model_dump"):
                ctx_builder = ctx_builder.model_dump()

            prioritization = context_data.get("content_prioritization_output")
            if hasattr(prioritization, "model_dump"):
                prioritization = prioritization.model_dump()

            resp_builder = context_data.get("response_builder_output")
            if hasattr(resp_builder, "model_dump"):
                resp_builder = resp_builder.model_dump()

            return ChainResponse(
                success=result.get("success", False),
                context_builder=ctx_builder,
                content_prioritization=prioritization,
                response_builder=resp_builder,
                error=result.get("error"),
            )

    def run_sync(self, **kwargs) -> ChainResponse:
        """Synchronous wrapper for run()"""
        import asyncio

        return asyncio.run(self.run(**kwargs))
