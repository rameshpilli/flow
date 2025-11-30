"""
CMPT Chain - Client Meeting Prep Tool

A complete chain for generating client meeting preparation materials.
Uses a 3-stage pipeline: Context Builder -> Content Prioritization -> Response Builder.

Usage:
    from agentorchestrator.chains import CMPTChain

    chain = CMPTChain()
    chain.check()       # Validate chain
    chain.graph()       # Visualize DAG

    result = await chain.run(
        corporate_company_name="Apple Inc",
        meeting_datetime="2025-01-15T10:00:00Z",
    )
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from agentorchestrator import AgentOrchestrator
from agentorchestrator.services import (
    ChainRequest,
    ChainRequestOverrides,
    ChainResponse,
    ContentPrioritizationService,
    ContextBuilderService,
    ResponseBuilderService,
)


class CMPTChain:
    """
    Client Meeting Prep Tool Chain.

    A 3-stage pipeline for generating meeting preparation materials:
    1. Context Builder - Extract company info, temporal context, personas
    2. Content Prioritization - Prioritize data sources, generate subqueries
    3. Response Builder - Execute agents, build final response

    Example:
        chain = CMPTChain()
        result = await chain.run(
            corporate_company_name="Apple Inc",
            meeting_datetime="2025-01-15T10:00:00Z",
        )
        print(result.prepared_content)
    """

    def __init__(
        self,
        name: str = "cmpt",
        context_builder: ContextBuilderService | None = None,
        content_prioritizer: ContentPrioritizationService | None = None,
        response_builder: ResponseBuilderService | None = None,
    ):
        """
        Initialize the CMPT chain.

        Args:
            name: Chain instance name
            context_builder: Custom context builder service
            content_prioritizer: Custom prioritization service
            response_builder: Custom response builder service
        """
        self._ao = AgentOrchestrator(name=name, isolated=True)
        self._context_builder = context_builder or ContextBuilderService()
        self._content_prioritizer = content_prioritizer or ContentPrioritizationService()
        self._response_builder = response_builder or ResponseBuilderService()

        self._register_chain()

    def _register_chain(self) -> None:
        """Register the CMPT chain steps and chain definition."""
        ao = self._ao
        context_builder = self._context_builder
        content_prioritizer = self._content_prioritizer
        response_builder = self._response_builder

        @ao.step(
            name="context_builder",
            produces=["context_output"],
            description="Extract company info, temporal context, and personas",
        )
        async def context_builder_step(ctx):
            request_data = ctx.get("request", {})
            request = (
                ChainRequest(**request_data)
                if isinstance(request_data, dict)
                else request_data
            )
            output = await context_builder.execute(request)
            ctx.set("context_output", output)
            ctx.set("company_name", output.company_name)
            ctx.set("ticker", output.ticker)
            return {"stage": "context_builder", "company": output.company_name}

        @ao.step(
            name="content_prioritization",
            deps=["context_builder"],
            produces=["prioritization_output"],
            description="Prioritize data sources and generate subqueries",
        )
        async def content_prioritization_step(ctx):
            context_output = ctx.get("context_output")
            output = await content_prioritizer.execute(context_output)
            ctx.set("prioritization_output", output)
            return {
                "stage": "content_prioritization",
                "sources": len(output.prioritized_sources),
            }

        @ao.step(
            name="response_builder",
            deps=["content_prioritization"],
            produces=["response_output"],
            description="Execute agents and build final response",
        )
        async def response_builder_step(ctx):
            context_output = ctx.get("context_output")
            prioritization_output = ctx.get("prioritization_output")
            output = await response_builder.execute(
                context_output, prioritization_output
            )
            ctx.set("response_output", output)
            return {"stage": "response_builder", "success": True}

        @ao.chain(name="cmpt_chain", description="Client Meeting Prep Tool Chain")
        class _CMPTChain:
            steps = ["context_builder", "content_prioritization", "response_builder"]

    def check(self, chain_name: str = "cmpt_chain") -> None:
        """Validate the chain definition."""
        self._ao.check(chain_name)

    def graph(self, chain_name: str = "cmpt_chain") -> str:
        """Generate ASCII DAG visualization."""
        return self._ao.graph(chain_name)

    async def run(
        self,
        corporate_company_name: str,
        meeting_datetime: str | datetime | None = None,
        rbc_employee_email: str | None = None,
        overrides: ChainRequestOverrides | dict[str, Any] | None = None,
    ) -> ChainResponse:
        """
        Execute the CMPT chain.

        Args:
            corporate_company_name: Company name for the meeting
            meeting_datetime: Meeting date/time (ISO format or datetime)
            rbc_employee_email: Optional employee email for persona detection
            overrides: Optional overrides for ticker, fiscal quarter, etc.

        Returns:
            ChainResponse with prepared content and metadata
        """
        # Normalize meeting datetime
        if meeting_datetime is None:
            meeting_datetime = datetime.now().isoformat()
        elif isinstance(meeting_datetime, datetime):
            meeting_datetime = meeting_datetime.isoformat()

        # Normalize overrides
        if isinstance(overrides, dict):
            overrides = ChainRequestOverrides(**overrides)

        # Build request
        request = ChainRequest(
            corporate_company_name=corporate_company_name,
            meeting_datetime=meeting_datetime,
            rbc_employee_email=rbc_employee_email,
            overrides=overrides,
        )

        # Execute chain
        result = await self._ao.launch("cmpt_chain", {"request": request.model_dump()})

        # Build response using the ChainResponse model structure
        ctx_data = result.get("context", {}).get("data", {})
        context_output = ctx_data.get("context_output")
        prioritization_output = ctx_data.get("prioritization_output")
        response_output = ctx_data.get("response_output")

        return ChainResponse(
            success=result.get("success", False),
            context_builder={
                "company_name": ctx_data.get("company_name"),
                "ticker": ctx_data.get("ticker"),
                "output": context_output.model_dump() if context_output else None,
            } if context_output else None,
            content_prioritization={
                "sources": len(prioritization_output.prioritized_sources) if prioritization_output else 0,
                "output": prioritization_output.model_dump() if prioritization_output else None,
            } if prioritization_output else None,
            response_builder={
                "prepared_content": response_output.prepared_content if response_output else None,
                "output": response_output.model_dump() if response_output else None,
            } if response_output else None,
            timings={"duration_ms": result.get("duration_ms", 0)},
        )

    def run_sync(
        self,
        corporate_company_name: str,
        meeting_datetime: str | datetime | None = None,
        rbc_employee_email: str | None = None,
        overrides: ChainRequestOverrides | dict[str, Any] | None = None,
    ) -> ChainResponse:
        """Synchronous version of run()."""
        return asyncio.run(
            self.run(
                corporate_company_name=corporate_company_name,
                meeting_datetime=meeting_datetime,
                rbc_employee_email=rbc_employee_email,
                overrides=overrides,
            )
        )
