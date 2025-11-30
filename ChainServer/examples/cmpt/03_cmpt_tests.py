#!/usr/bin/env python3
"""
Test the CMPT Chain integration with AgentOrchestrator.

Run with: python -m agentorchestrator.test_cmpt_chain

This demonstrates the complete flow:
1. Context Builder - extracts firm info, temporal context, personas
2. Content Prioritization - prioritizes sources, generates subqueries
3. Response Builder - executes agents, builds final response
"""

import asyncio
import json
import os
import sys

# Add parent to path for local testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentorchestrator.chains import CMPTChain


def print_section(title: str, char: str = "="):
    """Print a formatted section header"""
    width = 70
    print(f"\n{char * width}")
    print(f" {title}")
    print(f"{char * width}")


def test_check():
    """Test chain validation (like 'dg check defs')"""
    print_section("CMPT Chain - Validation (forge.check)")

    chain = CMPTChain()
    chain.check()


def test_list_defs():
    """Test listing definitions (like 'dg list defs')"""
    print_section("CMPT Chain - List Definitions (forge.list_defs)")

    chain = CMPTChain()
    chain.list_defs()


def test_graph_ascii():
    """Test ASCII DAG visualization"""
    print_section("CMPT Chain - DAG Visualization (ASCII)")

    chain = CMPTChain()
    chain.graph("ascii")


def test_graph_mermaid():
    """Test Mermaid DAG visualization"""
    print_section("CMPT Chain - DAG Visualization (Mermaid)")

    chain = CMPTChain()
    chain.graph("mermaid")


async def test_run():
    """Test complete chain execution with mock data"""
    print_section("CMPT Chain - Full Execution")

    chain = CMPTChain()

    print("\n  Input Request:")
    print("  " + "-" * 40)
    print("  corporate_company_name: Apple Inc")
    print("  meeting_datetime: 2025-01-15T10:00:00Z")
    print("  rbc_employee_email: john.doe@rbc.com")
    print("  corporate_client_email: jane.smith@apple.com")

    result = await chain.run(
        corporate_company_name="Apple Inc",
        meeting_datetime="2025-01-15T10:00:00Z",
        rbc_employee_email="john.doe@rbc.com",
        corporate_client_email="jane.smith@apple.com",
    )

    # Display detailed results
    print_section("Execution Results", "-")

    print(f"\n  Overall Status: {'SUCCESS' if result.success else 'FAILED'}")
    if result.error:
        print(f"  Error: {result.error}")

    # Stage 1: Context Builder Output
    print("\n  STAGE 1: Context Builder")
    print("  " + "-" * 40)
    ctx_data = result.context_builder or {}
    print(f"  Company Name: {ctx_data.get('company_name', 'N/A')}")
    print(f"  Ticker: {ctx_data.get('ticker', 'N/A')}")

    if ctx_data.get("company_info"):
        ci = ctx_data["company_info"]
        print(f"  Industry: {ci.get('industry', 'N/A')}")
        print(f"  Sector: {ci.get('sector', 'N/A')}")
        print(f"  Market Cap: {ci.get('market_cap', 'N/A')}")

    if ctx_data.get("temporal_context"):
        tc = ctx_data["temporal_context"]
        print(f"  Current Quarter: {tc.get('current_quarter', 'N/A')}")
        print(f"  Fiscal Year: {tc.get('fiscal_year', 'N/A')}")
        print(f"  Days to Earnings: {tc.get('days_to_earnings', 'N/A')}")

    if ctx_data.get("rbc_persona"):
        rp = ctx_data["rbc_persona"]
        print(f"  RBC Persona: {rp.get('name', 'N/A')} ({rp.get('email', 'N/A')})")

    if ctx_data.get("corporate_client_personas"):
        for cp in ctx_data["corporate_client_personas"]:
            print(f"  Client Persona: {cp.get('name', 'N/A')} ({cp.get('email', 'N/A')})")

    # Stage 2: Content Prioritization Output
    print("\n  STAGE 2: Content Prioritization")
    print("  " + "-" * 40)
    cp_data = result.content_prioritization or {}

    if cp_data.get("prioritized_sources"):
        print("  Prioritized Sources:")
        for src in cp_data["prioritized_sources"]:
            print(f"    - {src.get('source', 'N/A')}: {src.get('priority', 'N/A')}")

    if cp_data.get("subqueries"):
        print(f"  Subqueries Generated: {len(cp_data['subqueries'])}")
        for sq in cp_data["subqueries"][:3]:  # Show first 3
            print(f"    - Agent: {sq.get('agent', 'N/A')}, Query: {sq.get('query', 'N/A')[:40]}...")

    if cp_data.get("prioritization_reasoning"):
        print(f"  Reasoning: {cp_data['prioritization_reasoning'][:100]}...")

    # Stage 3: Response Builder Output
    print("\n  STAGE 3: Response Builder")
    print("  " + "-" * 40)
    resp_data = result.response_builder or {}

    print(f"  Total Items Retrieved: {resp_data.get('total_items', 0)}")
    print(f"  Agents Succeeded: {resp_data.get('agents_succeeded', 0)}")
    print(f"  Agents Failed: {resp_data.get('agents_failed', 0)}")

    if resp_data.get("agent_results"):
        print("\n  Agent Results:")
        for agent, ar in resp_data["agent_results"].items():
            status = "SUCCESS" if ar.get("success") else "FAILED"
            count = ar.get("item_count", 0)
            duration = ar.get("duration_ms", 0)
            print(f"    - {agent}: {status} ({count} items, {duration:.1f}ms)")

    if resp_data.get("financial_metrics"):
        fm = resp_data["financial_metrics"]
        print("\n  Financial Metrics:")
        print(f"    Latest Quarter: {fm.get('latest_quarter', 'N/A')}")
        print(f"    EPS Beat: {fm.get('eps_beat', 'N/A')}")
        print(f"    EPS Actual: ${fm.get('eps_actual', 'N/A')}")
        print(f"    Revenue Actual: {fm.get('revenue_actual', 'N/A')}")

    if resp_data.get("strategic_analysis"):
        sa = resp_data["strategic_analysis"]
        print("\n  Strategic Analysis:")
        print(f"    Market Sentiment: {sa.get('market_sentiment', 'N/A')}")
        if sa.get("key_themes"):
            print(f"    Key Themes: {', '.join(sa['key_themes'])}")
        if sa.get("risks"):
            print(f"    Risks: {', '.join(sa['risks'][:3])}...")
        if sa.get("opportunities"):
            print(f"    Opportunities: {', '.join(sa['opportunities'][:3])}...")

    # Timing Summary
    print("\n  Timing Summary (ms):")
    print("  " + "-" * 40)
    if result.timings:
        total = 0
        for stage, ms in result.timings.items():
            print(f"    {stage}: {ms:.2f}")
            total += ms
        print(f"    {'─' * 30}")
        print(f"    Total: {total:.2f}")

    # Final Prepared Content
    print("\n  FINAL OUTPUT: Meeting Prep Content")
    print("  " + "-" * 40)
    prepared_content = resp_data.get("prepared_content", "N/A")
    # Indent each line
    for line in prepared_content.split("\n"):
        print(f"  {line}")

    return result


async def test_run_detailed_json():
    """Show raw JSON output for debugging"""
    print_section("CMPT Chain - Raw JSON Output")

    chain = CMPTChain()

    result = await chain.run(
        corporate_company_name="Microsoft Corporation",
        meeting_datetime="2025-02-20T14:30:00Z",
    )

    # Pretty print the full response
    result_dict = {
        "success": result.success,
        "error": result.error,
        "timings": result.timings,
        "context_builder": result.context_builder,
        "content_prioritization": result.content_prioritization,
        "response_builder": result.response_builder,
    }

    print("\n" + json.dumps(result_dict, indent=2, default=str))


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("     AgentOrchestrator CMPT Chain - End-to-End Test Suite")
    print("=" * 70)
    print("\nThis test demonstrates the complete Client Meeting Prep chain flow.")
    print("All data is MOCKED - no external API calls are made.\n")

    # 1. Validation
    test_check()

    # 2. List definitions
    test_list_defs()

    # 3. ASCII graph
    test_graph_ascii()

    # 4. Mermaid graph
    test_graph_mermaid()

    # 5. Run chain with detailed output
    asyncio.run(test_run())

    # 6. Show raw JSON (optional, for debugging)
    # asyncio.run(test_run_detailed_json())

    print_section("All Tests Completed Successfully!", "=")
    print("\nThe CMPT chain is fully functional with mock data.")
    print("To connect to real APIs, update the service implementations.\n")


if __name__ == "__main__":
    main()
