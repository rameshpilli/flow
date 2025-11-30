#!/usr/bin/env python3
"""
================================================================================
RUN.PY - Main Entry Point for CMPT Chain
================================================================================

This is the file you run to execute the CMPT chain.

USAGE:
    # Basic run
    python examples/cmpt/run.py

    # With custom company
    python examples/cmpt/run.py --company "Microsoft"

    # With all options
    python examples/cmpt/run.py --company "Apple Inc" --meeting-date "2025-01-15"

WHAT HAPPENS:
    1. Creates an AgentOrchestrator instance
    2. Registers the CMPT chain (3 stages)
    3. Runs the chain with your input
    4. Outputs the meeting prep content
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(__file__).rsplit("/", 3)[0])

from agentorchestrator import AgentOrchestrator
from examples.cmpt.services import (
    ChainRequest,
    ContextBuilderService,
    ContentPrioritizationService,
    ResponseBuilderService,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def create_cmpt_chain(ao: AgentOrchestrator) -> None:
    """Register the CMPT chain with AgentOrchestrator."""

    # Initialize services
    context_builder = ContextBuilderService()
    content_prioritizer = ContentPrioritizationService()
    response_builder = ResponseBuilderService()

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 1: Context Builder
    # ══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="context_builder",
        produces=["context_output"],
        description="Extract company info, temporal context, and personas",
    )
    async def context_builder_step(ctx):
        """Stage 1: Build context from the request."""
        request_data = ctx.get("request", {})
        request = ChainRequest(**request_data) if isinstance(request_data, dict) else request_data

        logger.info(f"📋 Stage 1: Building context for {request.corporate_company_name}...")
        output = await context_builder.execute(request)

        ctx.set("context_output", output)
        ctx.set("company_name", output.company_name)
        ctx.set("ticker", output.ticker)

        return {"stage": "context_builder", "company": output.company_name}

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 2: Content Prioritization
    # ══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="content_prioritization",
        deps=["context_builder"],
        produces=["prioritization_output"],
        description="Prioritize data sources and generate subqueries",
    )
    async def content_prioritization_step(ctx):
        """Stage 2: Prioritize content sources."""
        context_output = ctx.get("context_output")

        logger.info("🎯 Stage 2: Prioritizing content sources...")
        output = await content_prioritizer.execute(context_output)

        ctx.set("prioritization_output", output)
        return {"stage": "content_prioritization", "sources": len(output.prioritized_sources)}

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 3: Response Builder
    # ══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="response_builder",
        deps=["content_prioritization"],
        produces=["response_output"],
        description="Execute agents and build final response",
    )
    async def response_builder_step(ctx):
        """Stage 3: Build the final response."""
        context_output = ctx.get("context_output")
        prioritization_output = ctx.get("prioritization_output")

        logger.info("📝 Stage 3: Building response...")
        output = await response_builder.execute(context_output, prioritization_output)

        ctx.set("response_output", output)
        return {"stage": "response_builder", "success": True}

    # ══════════════════════════════════════════════════════════════════════════
    # CHAIN DEFINITION
    # ══════════════════════════════════════════════════════════════════════════

    @ao.chain(name="cmpt_chain", description="Client Meeting Prep Tool Chain")
    class CMPTChain:
        """
        3-Stage CMPT Pipeline:
        1. Context Builder → Extract company, temporal, persona info
        2. Content Prioritization → Prioritize sources, generate subqueries
        3. Response Builder → Execute agents, build final response
        """
        steps = ["context_builder", "content_prioritization", "response_builder"]


async def main(company: str, meeting_date: str):
    """Run the CMPT chain."""
    print("\n" + "═" * 60)
    print("  CMPT - Client Meeting Prep Tool")
    print("═" * 60 + "\n")

    # Create orchestrator
    ao = AgentOrchestrator(name="cmpt", isolated=True)

    # Register the chain
    create_cmpt_chain(ao)

    # Validate
    print("✓ Chain registered and validated\n")

    # Build request
    request = {
        "corporate_company_name": company,
        "meeting_datetime": meeting_date,
    }

    print(f"Company: {company}")
    print(f"Meeting Date: {meeting_date}")
    print("-" * 40 + "\n")

    # Run the chain
    result = await ao.launch("cmpt_chain", {"request": request})

    # Show results
    print("\n" + "-" * 40)
    if result.get("success"):
        print("✅ Chain completed successfully!")
        print(f"Duration: {result.get('duration_ms', 0):.0f}ms")
    else:
        print("❌ Chain failed")
        print(f"Error: {result.get('error')}")

    print("\n" + "═" * 60 + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CMPT Chain")
    parser.add_argument("--company", default="Apple Inc", help="Company name")
    parser.add_argument("--meeting-date", default=datetime.now().strftime("%Y-%m-%d"), help="Meeting date")
    args = parser.parse_args()

    asyncio.run(main(args.company, args.meeting_date))
