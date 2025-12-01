"""
================================================================================
CMPT (Client Meeting Prep Tool) - Production Example
================================================================================

PURPOSE:
    This is a COMPLETE PRODUCTION EXAMPLE of a chain that prepares
    client meeting materials. Use this as a reference for building
    your own production chains.

HOW TO RUN:
    python cmpt/run.py --company "Apple Inc"

FOLDER STRUCTURE:
    cmpt/
    ├── run.py                   # 👈 START HERE - Main entry point
    ├── services/                # Business logic (the actual work)
    │   ├── models.py            # Pydantic data models
    │   ├── context_builder.py   # Stage 1: Extract context
    │   ├── content_prioritization.py  # Stage 2: Prioritize sources
    │   ├── response_builder.py  # Stage 3: Build response
    │   └── llm_gateway.py       # LLM client with OAuth
    ├── 02_cmpt_tutorial.ipynb   # Interactive tutorial notebook
    └── 03_cmpt_tests.py         # Test examples

THE 3-STAGE PIPELINE:
    ┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────┐
    │ Context Builder │───▶│Content Prioritizer  │───▶│Response Builder │
    │                 │    │                     │    │                 │
    │ • Company Info  │    │ • Source Priority   │    │ • Agent Calls   │
    │ • Temporal Info │    │ • Subquery Engine   │    │ • LLM Response  │
    │ • Persona Info  │    │ • Topic Ranker      │    │ • Final Output  │
    └─────────────────┘    └─────────────────────┘    └─────────────────┘

USAGE:
    # Option 1: Run directly
    python cmpt/run.py --company "Apple Inc"

    # Option 2: Import and use programmatically
    from cmpt import run_cmpt_chain
    result = await run_cmpt_chain("Apple Inc", "2025-01-15")

    # Option 3: Register with your own orchestrator
    from cmpt import register_cmpt_chain
    from agentorchestrator import AgentOrchestrator
    ao = AgentOrchestrator(name="my_app")
    register_cmpt_chain(ao)
    result = await ao.launch("cmpt_chain", {"request": {...}})

    # Option 4: Use services directly (without AgentOrchestrator)
    from cmpt.services import ContextBuilderService
    service = ContextBuilderService()
    output = await service.execute(request)
"""

from cmpt.chain import register_cmpt_chain, run_cmpt_chain

# Re-export services for direct use
from cmpt.services import (
    ChainRequest,
    ChainResponse,
    ContextBuilderService,
    ContentPrioritizationService,
    ResponseBuilderService,
)

__all__ = [
    "register_cmpt_chain",
    "run_cmpt_chain",
    "ChainRequest",
    "ChainResponse",
    "ContextBuilderService",
    "ContentPrioritizationService",
    "ResponseBuilderService",
]
