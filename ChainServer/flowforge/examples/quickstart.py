#!/usr/bin/env python3
"""
FlowForge Quickstart Example

Minimal example showing core FlowForge concepts:
- Step registration with @step decorator
- Dependencies between steps using 'deps' parameter
- Chain definition with @chain decorator
- Running chains with forge.launch()
- Using resumable chains with checkpointing

Run this example:
    python -m flowforge.examples.quickstart
"""

import asyncio

from flowforge import FlowForge, ChainContext

# Create FlowForge instance (isolated to prevent registry bleed)
forge = FlowForge(name="quickstart", isolated=True)


# ══════════════════════════════════════════════════════════════════
#                           STEP DEFINITIONS
# ══════════════════════════════════════════════════════════════════

@forge.step
async def fetch_data(ctx: ChainContext) -> dict:
    """Step 1: Fetch initial data from context."""
    company = ctx.initial_data.get("company", "Unknown")
    print(f"  📥 Fetching data for: {company}")

    # Simulate fetching data
    data = {
        "company": company,
        "revenue": 394_328_000_000,
        "employees": 161_000,
        "founded": 1976,
    }

    ctx.set("company_data", data)
    return data


@forge.step(deps=[fetch_data])
async def process_data(ctx: ChainContext) -> dict:
    """Step 2: Process the fetched data (depends on fetch_data)."""
    company_data = ctx.get("company_data")
    print(f"  ⚙️ Processing data for: {company_data['company']}")

    # Simulate processing
    processed = {
        "company": company_data["company"],
        "revenue_billions": company_data["revenue"] / 1_000_000_000,
        "company_age": 2024 - company_data["founded"],
        "employee_count": company_data["employees"],
    }

    ctx.set("processed_data", processed)
    return processed


@forge.step(deps=[process_data])
async def generate_report(ctx: ChainContext) -> dict:
    """Step 3: Generate final report (depends on process_data)."""
    processed = ctx.get("processed_data")
    print(f"  📊 Generating report for: {processed['company']}")

    # Generate report
    report = {
        "title": f"{processed['company']} Company Overview",
        "highlights": [
            f"Revenue: ${processed['revenue_billions']:.1f}B",
            f"Employees: {processed['employee_count']:,}",
            f"Company Age: {processed['company_age']} years",
        ],
        "summary": f"{processed['company']} is a {processed['company_age']}-year-old "
                   f"company with ${processed['revenue_billions']:.1f}B in revenue "
                   f"and {processed['employee_count']:,} employees.",
    }

    return report


# ══════════════════════════════════════════════════════════════════
#                           CHAIN DEFINITION
# ══════════════════════════════════════════════════════════════════

@forge.chain
class QuickstartChain:
    """Simple chain demonstrating FlowForge basics."""
    steps = [fetch_data, process_data, generate_report]


# ══════════════════════════════════════════════════════════════════
#                           RUN THE CHAIN
# ══════════════════════════════════════════════════════════════════

async def main():
    """Run the quickstart example."""
    print("\n" + "═" * 60)
    print("  FlowForge Quickstart Example")
    print("═" * 60 + "\n")

    # Validate the chain
    print("📋 Validating chain...")
    forge.check("QuickstartChain")

    # Run the chain
    print("\n🚀 Running chain...\n")
    result = await forge.launch("QuickstartChain", {"company": "Apple"})

    # Show results
    print("\n" + "═" * 60)
    if result.get("success"):
        print("  ✅ Chain completed successfully!")
        final_output = result.get("final_output", {})
        if final_output:
            print(f"\n  Report: {final_output.get('title', 'N/A')}")
            for highlight in final_output.get("highlights", []):
                print(f"    • {highlight}")
    else:
        print("  ❌ Chain failed!")
        print(f"  Error: {result.get('error', 'Unknown error')}")
    print("═" * 60 + "\n")

    return result


async def demo_resumable():
    """Demonstrate resumable chain execution."""
    print("\n" + "═" * 60)
    print("  Resumable Chain Demo")
    print("═" * 60 + "\n")

    # Run with checkpointing enabled
    print("🚀 Running chain with checkpointing...")
    result = await forge.launch_resumable("QuickstartChain", {"company": "Microsoft"})

    run_id = result.get("run_id")
    print(f"\n  Run ID: {run_id}")
    print(f"  Status: {result.get('status')}")
    print(f"  Success: {result.get('success')}")

    # List runs
    print("\n📋 Listing recent runs...")
    runs = await forge.list_runs(limit=5)
    for run in runs:
        print(f"  • {run.run_id}: {run.chain_name} ({run.status})")

    print("\n═" * 60 + "\n")
    return result


if __name__ == "__main__":
    # Run basic example
    asyncio.run(main())

    # Demonstrate resumable chains
    asyncio.run(demo_resumable())
