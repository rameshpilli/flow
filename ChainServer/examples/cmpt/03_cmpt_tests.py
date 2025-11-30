#!/usr/bin/env python3
"""
================================================================================
03_CMPT_TESTS.PY - Test the CMPT Chain
================================================================================

PURPOSE:
    Test the CMPT chain integration with AgentOrchestrator.
    Demonstrates the complete flow:
    1. Context Builder - extracts firm info, temporal context, personas
    2. Content Prioritization - prioritizes sources, generates subqueries
    3. Response Builder - executes agents, builds final response

RUN THIS EXAMPLE:
    python examples/cmpt/03_cmpt_tests.py

    OR via pytest:
    pytest examples/cmpt/03_cmpt_tests.py -v
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agentorchestrator import AgentOrchestrator
from examples.cmpt.run import create_cmpt_chain
from examples.cmpt.services import (
    ChainRequest,
    ContextBuilderService,
    ContentPrioritizationService,
    ResponseBuilderService,
)


def print_section(title: str, char: str = "="):
    """Print a formatted section header."""
    width = 70
    print(f"\n{char * width}")
    print(f" {title}")
    print(f"{char * width}")


# ============================================================
# TEST: Chain Validation
# ============================================================

def test_chain_validation():
    """Test chain validation (like 'ao check')."""
    print_section("CMPT Chain - Validation (ao.check)")

    ao = AgentOrchestrator(name="cmpt_test", isolated=True)
    create_cmpt_chain(ao)

    # Validate chain
    ao.check("cmpt_chain")
    print("  ✓ Chain validation passed")


# ============================================================
# TEST: List Definitions
# ============================================================

def test_list_definitions():
    """Test listing definitions (like 'ao list')."""
    print_section("CMPT Chain - List Definitions (ao.list_*)")

    ao = AgentOrchestrator(name="cmpt_test", isolated=True)
    create_cmpt_chain(ao)

    print("\n  Steps:")
    for step in ao.list_steps():
        print(f"    - {step}")

    print("\n  Chains:")
    for chain in ao.list_chains():
        print(f"    - {chain}")


# ============================================================
# TEST: DAG Visualization
# ============================================================

def test_dag_visualization():
    """Test DAG visualization (like 'ao graph')."""
    print_section("CMPT Chain - DAG Visualization")

    ao = AgentOrchestrator(name="cmpt_test", isolated=True)
    create_cmpt_chain(ao)

    print("\n  ASCII DAG:")
    dag = ao.graph("cmpt_chain")
    print(dag)


# ============================================================
# TEST: Services Directly
# ============================================================

async def test_services_directly():
    """Test the underlying services without AgentOrchestrator."""
    print_section("CMPT Services - Direct Execution")

    # Stage 1: Context Builder
    print("\n  Stage 1: Context Builder")
    print("  " + "-" * 40)

    request = ChainRequest(
        corporate_company_name="Apple Inc",
        meeting_datetime="2025-01-15T10:00:00Z",
    )

    context_service = ContextBuilderService()
    context_output = await context_service.execute(request)

    print(f"    Company: {context_output.company_name}")
    print(f"    Ticker: {context_output.ticker}")
    print(f"    Industry: {context_output.company_info.industry if context_output.company_info else 'N/A'}")
    print(f"    Quarter: Q{context_output.temporal_context.fiscal_quarter} {context_output.temporal_context.fiscal_year}" if context_output.temporal_context else "N/A")

    # Stage 2: Content Prioritization
    print("\n  Stage 2: Content Prioritization")
    print("  " + "-" * 40)

    priority_service = ContentPrioritizationService()
    priority_output = await priority_service.execute(context_output)

    print(f"    Sources: {len(priority_output.prioritized_sources)}")
    for src in priority_output.prioritized_sources[:3]:
        print(f"      - {src.source}: priority {src.priority}")
    print(f"    Subqueries: {len(priority_output.subqueries)}")

    # Stage 3: Response Builder
    print("\n  Stage 3: Response Builder")
    print("  " + "-" * 40)

    response_service = ResponseBuilderService()
    response_output = await response_service.execute(context_output, priority_output)

    print(f"    Total Items: {response_output.total_items}")
    print(f"    Agents Succeeded: {response_output.agents_succeeded}")
    print(f"    Agents Failed: {response_output.agents_failed}")

    print("\n  ✓ All services executed successfully")
    return context_output, priority_output, response_output


# ============================================================
# TEST: Full Chain Execution
# ============================================================

async def test_full_chain():
    """Test complete chain execution with AgentOrchestrator."""
    print_section("CMPT Chain - Full Execution")

    # Create orchestrator and register chain
    ao = AgentOrchestrator(name="cmpt_test", isolated=True)
    create_cmpt_chain(ao)

    print("\n  Input Request:")
    print("  " + "-" * 40)
    print("    company: Apple Inc")
    print("    meeting_date: 2025-01-15")

    # Execute the chain
    result = await ao.launch("cmpt_chain", {
        "request": {
            "corporate_company_name": "Apple Inc",
            "meeting_datetime": "2025-01-15T10:00:00Z",
        }
    })

    # Display results
    print("\n  Execution Results:")
    print("  " + "-" * 40)
    print(f"    Success: {result.get('success')}")
    print(f"    Duration: {result.get('duration_ms', 0):.1f}ms")

    if result.get("results"):
        print("\n  Step Results:")
        for step_result in result["results"]:
            status = "✓" if step_result.get("success") else "✗"
            name = step_result.get("step", "unknown")
            duration = step_result.get("duration_ms", 0)
            print(f"    {status} {name}: {duration:.1f}ms")

    # Show context data
    ctx_data = result.get("context", {}).get("data", {})
    if ctx_data.get("company_name"):
        print(f"\n  Company: {ctx_data.get('company_name')}")
        print(f"  Ticker: {ctx_data.get('ticker')}")

    print("\n  ✓ Chain executed successfully")
    return result


# ============================================================
# TEST: Raw JSON Output
# ============================================================

async def test_json_output():
    """Show raw JSON output for debugging."""
    print_section("CMPT Chain - Raw JSON Output")

    ao = AgentOrchestrator(name="cmpt_test", isolated=True)
    create_cmpt_chain(ao)

    result = await ao.launch("cmpt_chain", {
        "request": {
            "corporate_company_name": "Microsoft Corporation",
            "meeting_datetime": "2025-02-20T14:30:00Z",
        }
    })

    # Pretty print essential fields
    output = {
        "success": result.get("success"),
        "duration_ms": result.get("duration_ms"),
        "steps_executed": len(result.get("results", [])),
        "company": result.get("context", {}).get("data", {}).get("company_name"),
    }

    print("\n" + json.dumps(output, indent=2, default=str))
    return result


# ============================================================
# MAIN
# ============================================================

def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("     AgentOrchestrator CMPT Chain - Test Suite")
    print("=" * 70)
    print("\nThis test demonstrates the complete Client Meeting Prep chain flow.")
    print("All data is MOCKED - no external API calls are made.\n")

    # 1. Validation
    test_chain_validation()

    # 2. List definitions
    test_list_definitions()

    # 3. DAG visualization
    test_dag_visualization()

    # 4. Test services directly
    asyncio.run(test_services_directly())

    # 5. Run full chain
    asyncio.run(test_full_chain())

    # 6. Show JSON output (optional)
    # asyncio.run(test_json_output())

    print_section("All Tests Completed Successfully!", "=")
    print("\nThe CMPT chain is fully functional with mock data.")
    print("To connect to real APIs, update the service implementations.\n")


if __name__ == "__main__":
    main()
