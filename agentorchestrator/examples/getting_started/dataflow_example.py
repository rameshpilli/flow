"""
Dataflow-Based Dependencies Example
====================================

Demonstrates automatic dependency resolution using produces/consumes declarations.

Usage:
    python dataflow_example.py

What this example demonstrates:
    - Using @produces and @consumes decorators
    - Enabling dataflow=True on a chain
    - Automatic dependency resolution based on data flow
    - Merging explicit deps with dataflow-inferred deps

Expected output:
    Step fetch_company producing: company_data
    Step analyze consuming company_data, producing: analysis
    Step report consuming company_data and analysis

    Execution order (from ao.check()):
    - fetch_company (no deps)
    - analyze (depends on fetch_company via dataflow)
    - report (depends on fetch_company and analyze via dataflow)

    Final Report:
    AAPL Analysis Report
    - Company: Apple Inc.
    - Score: 95
    - Recommendation: Strong Buy
"""

from __future__ import annotations

import asyncio

from agentorchestrator import AgentOrchestrator, produces, consumes


def create_dataflow_orchestrator() -> AgentOrchestrator:
    """
    Create an orchestrator demonstrating dataflow-based dependencies.

    Instead of explicit deps=["step_name"], we declare what data each step
    produces and consumes. With dataflow=True on the chain, dependencies
    are resolved automatically.

    Returns:
        Configured AgentOrchestrator instance
    """
    ao = AgentOrchestrator(name="dataflow_example", isolated=True)

    @produces("company_data")
    @ao.step(name="fetch_company", description="Fetch company information")
    async def fetch_company(ctx):
        """
        Step 1: Fetch company data.

        Produces: company_data
        """
        print("Step fetch_company producing: company_data")

        # Simulate API call
        company_data = {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "market_cap": "3T",
        }

        ctx.set("company_data", company_data)
        return {"company_data": company_data}

    @consumes("company_data")
    @produces("analysis")
    @ao.step(name="analyze", description="Analyze company data")
    async def analyze(ctx):
        """
        Step 2: Analyze the company data.

        Consumes: company_data (automatically depends on fetch_company)
        Produces: analysis
        """
        print("Step analyze consuming company_data, producing: analysis")

        company_data = ctx.get("company_data")

        # Simulate analysis
        analysis = {
            "ticker": company_data["ticker"],
            "score": 95,
            "recommendation": "Strong Buy",
            "reasoning": f"{company_data['name']} shows strong fundamentals",
        }

        ctx.set("analysis", analysis)
        return {"analysis": analysis}

    @consumes("company_data", "analysis")
    @ao.step(name="report", description="Generate final report")
    async def report(ctx):
        """
        Step 3: Generate the final report.

        Consumes: company_data, analysis
        (automatically depends on both fetch_company and analyze)
        """
        print("Step report consuming company_data and analysis")

        company_data = ctx.get("company_data")
        analysis = ctx.get("analysis")

        report_text = f"""
{analysis['ticker']} Analysis Report
- Company: {company_data['name']}
- Score: {analysis['score']}
- Recommendation: {analysis['recommendation']}
        """.strip()

        ctx.set("final_report", report_text)
        return {"report": report_text}

    # Enable dataflow-based dependency resolution
    @ao.chain(name="research_chain", dataflow=True)
    class ResearchChain:
        """
        Research chain with dataflow-based dependencies.

        Steps are listed in any order - execution order is determined
        by produces/consumes declarations:
        1. fetch_company (no consumes - runs first)
        2. analyze (consumes company_data - runs after fetch_company)
        3. report (consumes both - runs last)
        """
        steps = ["fetch_company", "analyze", "report"]

    return ao


async def run_dataflow_example() -> dict:
    """
    Run the dataflow example.

    Returns:
        Result dictionary with the final report
    """
    ao = create_dataflow_orchestrator()

    # Show the resolved dependencies
    print("\nValidating chain with dataflow resolution...")
    check_result = ao.check()
    print(f"Validation: {'OK' if check_result['valid'] else 'FAILED'}")

    if check_result.get("chains"):
        for chain_info in check_result["chains"]:
            if chain_info["name"] == "research_chain":
                print(f"\nChain: {chain_info['name']}")
                print(f"  dataflow: {chain_info.get('dataflow', False)}")
                for step in chain_info.get("steps", []):
                    deps = step.get("deps", [])
                    dataflow_deps = step.get("dataflow_deps", [])
                    consumes_keys = step.get("consumes", [])
                    print(f"  - {step['name']}")
                    if deps:
                        print(f"      explicit deps: {deps}")
                    if dataflow_deps:
                        print(f"      dataflow deps: {dataflow_deps}")
                    if consumes_keys:
                        print(f"      consumes: {consumes_keys}")

    print("\n" + "=" * 50)
    print("Running chain...")
    print("=" * 50 + "\n")

    result = await ao.launch("research_chain", {})

    return result


def main():
    """CLI entry point."""
    result = asyncio.run(run_dataflow_example())

    if result["success"]:
        final_report = result["context"]["data"]["final_report"]
        print("\n" + "=" * 50)
        print("Final Report:")
        print("=" * 50)
        print(final_report)
    else:
        print(f"\nChain failed: {result.get('error')}")


if __name__ == "__main__":
    main()
