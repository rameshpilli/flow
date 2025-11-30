"""
FlowForge Chain Composition Example

This example demonstrates how to build modular pipelines by composing
chains within other chains. This pattern enables:

- Reusable pipeline components
- Modular testing of individual chains
- Complex workflow orchestration
- Clean separation of concerns

Run with:
    python examples/chain_composition.py
"""

import asyncio

from flowforge import ChainContext, FlowForge
from flowforge.core.context import ContextScope

# Initialize FlowForge
forge = FlowForge(name="composition_example", version="1.0.0")


# ══════════════════════════════════════════════════════════════════════════════
#                           SUBCHAIN 1: Data Extraction
# ══════════════════════════════════════════════════════════════════════════════

@forge.step(name="fetch_users")
async def fetch_users(ctx: ChainContext):
    """Fetch user data from database."""
    # Simulate database fetch
    users = [
        {"id": 1, "name": "Alice", "department": "Engineering"},
        {"id": 2, "name": "Bob", "department": "Sales"},
        {"id": 3, "name": "Charlie", "department": "Engineering"},
    ]
    ctx.set("users", users, scope=ContextScope.CHAIN)
    print(f"  ✓ Fetched {len(users)} users")
    return {"fetched_users": len(users)}


@forge.step(name="fetch_orders")
async def fetch_orders(ctx: ChainContext):
    """Fetch order data from database."""
    # Simulate database fetch
    orders = [
        {"id": 101, "user_id": 1, "amount": 150.00, "status": "completed"},
        {"id": 102, "user_id": 2, "amount": 250.00, "status": "pending"},
        {"id": 103, "user_id": 1, "amount": 75.50, "status": "completed"},
        {"id": 104, "user_id": 3, "amount": 320.00, "status": "completed"},
    ]
    ctx.set("orders", orders, scope=ContextScope.CHAIN)
    print(f"  ✓ Fetched {len(orders)} orders")
    return {"fetched_orders": len(orders)}


@forge.chain(name="data_extraction")
class DataExtractionChain:
    """Chain for extracting data from multiple sources."""
    steps = ["fetch_users", "fetch_orders"]


# ══════════════════════════════════════════════════════════════════════════════
#                           SUBCHAIN 2: Data Transformation
# ══════════════════════════════════════════════════════════════════════════════

@forge.step(name="join_data")
async def join_data(ctx: ChainContext):
    """Join users and orders data."""
    users = ctx.get("users", [])
    orders = ctx.get("orders", [])

    # Create user lookup
    user_map = {u["id"]: u for u in users}

    # Enrich orders with user info
    enriched = []
    for order in orders:
        user = user_map.get(order["user_id"], {})
        enriched.append({
            "order_id": order["id"],
            "user_name": user.get("name", "Unknown"),
            "department": user.get("department", "Unknown"),
            "amount": order["amount"],
            "status": order["status"],
        })

    ctx.set("enriched_orders", enriched, scope=ContextScope.CHAIN)
    print(f"  ✓ Joined {len(enriched)} records")
    return {"joined_records": len(enriched)}


@forge.step(name="calculate_metrics", deps=["join_data"])
async def calculate_metrics(ctx: ChainContext):
    """Calculate aggregate metrics."""
    enriched = ctx.get("enriched_orders", [])

    # Calculate metrics by department
    dept_totals = {}
    for order in enriched:
        if order["status"] == "completed":
            dept = order["department"]
            dept_totals[dept] = dept_totals.get(dept, 0) + order["amount"]

    total_revenue = sum(dept_totals.values())

    metrics = {
        "total_orders": len(enriched),
        "completed_orders": len([o for o in enriched if o["status"] == "completed"]),
        "total_revenue": total_revenue,
        "revenue_by_department": dept_totals,
    }
    ctx.set("metrics", metrics, scope=ContextScope.CHAIN)
    print(f"  ✓ Calculated metrics: ${total_revenue:.2f} total revenue")
    return {"metrics": metrics}


@forge.chain(name="data_transformation")
class DataTransformationChain:
    """Chain for transforming and enriching data."""
    steps = ["join_data", "calculate_metrics"]


# ══════════════════════════════════════════════════════════════════════════════
#                           SUBCHAIN 3: Report Generation
# ══════════════════════════════════════════════════════════════════════════════

@forge.step(name="generate_summary")
async def generate_summary(ctx: ChainContext):
    """Generate a text summary of the metrics."""
    metrics = ctx.get("metrics", {})

    summary_lines = [
        "═" * 50,
        "           SALES PERFORMANCE REPORT",
        "═" * 50,
        f"Total Orders: {metrics.get('total_orders', 0)}",
        f"Completed Orders: {metrics.get('completed_orders', 0)}",
        f"Total Revenue: ${metrics.get('total_revenue', 0):.2f}",
        "",
        "Revenue by Department:",
    ]

    for dept, amount in metrics.get("revenue_by_department", {}).items():
        summary_lines.append(f"  • {dept}: ${amount:.2f}")

    summary_lines.append("═" * 50)

    summary = "\n".join(summary_lines)
    ctx.set("report_summary", summary, scope=ContextScope.CHAIN)
    print("  ✓ Generated summary report")
    return {"summary_generated": True}


@forge.chain(name="report_generation")
class ReportGenerationChain:
    """Chain for generating reports."""
    steps = ["generate_summary"]


# ══════════════════════════════════════════════════════════════════════════════
#                           COMPOSED PARENT PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

@forge.step(name="initialize")
async def initialize(ctx: ChainContext):
    """Initialize the pipeline with configuration."""
    config = {
        "pipeline_name": "Sales Analytics Pipeline",
        "version": "1.0",
        "timestamp": "2024-01-15T10:00:00Z",
    }
    ctx.set("config", config, scope=ContextScope.CHAIN)
    print("  ✓ Pipeline initialized")
    return {"initialized": True}


@forge.step(name="finalize", deps=["__subchain__report_generation"])
async def finalize(ctx: ChainContext):
    """Finalize and output results."""
    config = ctx.get("config", {})
    summary = ctx.get("report_summary", "No summary available")

    print(f"\n{summary}\n")
    print(f"Pipeline: {config.get('pipeline_name')}")
    print("  ✓ Pipeline completed successfully!")

    return {
        "finalized": True,
        "pipeline": config.get("pipeline_name"),
    }


@forge.chain(name="full_analytics_pipeline")
class FullAnalyticsPipeline:
    """
    Composed pipeline that orchestrates multiple subchains.

    Note: Subchain steps are named __subchain__<chain_name> for dependency references.

    Execution flow:
    1. initialize - Set up configuration
    2. data_extraction - Fetch users and orders (subchain)
    3. data_transformation - Join and calculate metrics (subchain)
    4. report_generation - Generate summary report (subchain)
    5. finalize - Output results
    """
    steps = [
        "initialize",
        "data_extraction",       # ← Subchain: fetch_users, fetch_orders
        "data_transformation",   # ← Subchain: join_data, calculate_metrics
        "report_generation",     # ← Subchain: generate_summary
        "finalize",
    ]
    # Explicit ordering using __subchain__ prefixed names
    parallel_groups = [
        ["initialize"],
        ["__subchain__data_extraction"],
        ["__subchain__data_transformation"],
        ["__subchain__report_generation"],
        ["finalize"],
    ]


# ══════════════════════════════════════════════════════════════════════════════
#                                  MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    print("\n" + "=" * 60)
    print("     FlowForge Chain Composition Example")
    print("=" * 60 + "\n")

    print("Running composed pipeline...")
    print("-" * 40)

    # Execute the composed pipeline
    result = await forge.launch("full_analytics_pipeline")

    print("-" * 40)
    print(f"\nPipeline Success: {result['success']}")
    print(f"Total Steps Executed: {len(result.get('results', []))}")

    if not result["success"]:
        print(f"Error: {result.get('error')}")

    # Show step breakdown
    print("\nStep Breakdown:")
    for step_result in result.get("results", []):
        status = "✓" if step_result.get("success") else "✗"
        name = step_result.get("step", "unknown")
        duration = step_result.get("duration_ms", 0)
        print(f"  {status} {name} ({duration:.1f}ms)")


if __name__ == "__main__":
    asyncio.run(main())
