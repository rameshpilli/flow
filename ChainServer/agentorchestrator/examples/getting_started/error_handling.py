"""
Error Handling Example
======================

Production-ready error handling patterns for DAG workflows.

Usage:
    python error_handling.py
    python error_handling.py --fail  # Simulate failure

What this example demonstrates:
    - Try-except around ao.launch()
    - Checking result["success"] status
    - Accessing error details from result["error"]
    - Step-level error handling within steps
    - Graceful degradation patterns
"""

from __future__ import annotations

import asyncio
import argparse

from agentorchestrator import AgentOrchestrator


def create_error_handling_orchestrator(should_fail: bool = False) -> AgentOrchestrator:
    """
    Create an orchestrator that demonstrates error handling.

    Args:
        should_fail: If True, the process step will raise an error
    """
    ao = AgentOrchestrator(name="error_handling", isolated=True)

    @ao.step(name="fetch", description="Fetch data from external source")
    async def fetch(ctx):
        """
        Fetch step with error handling for external calls.

        Pattern: Wrap external calls in try-except
        """
        try:
            # Simulate external API call
            data = {"items": ["item1", "item2", "item3"]}
            ctx.set("raw_data", data)
            return {"fetched": len(data["items"]), "data": data}

        except Exception as e:
            # Log error and set fallback
            ctx.set("fetch_error", str(e))
            ctx.set("raw_data", {"items": []})  # Fallback to empty
            return {"fetched": 0, "error": str(e)}

    @ao.step(name="process", deps=["fetch"], description="Process fetched data")
    async def process(ctx):
        """
        Process step that may fail.

        Pattern: Check upstream results before processing
        """
        # Check if upstream had errors
        if ctx.get("fetch_error"):
            return {"processed": 0, "skipped": True, "reason": "Upstream fetch failed"}

        raw_data = ctx.get("raw_data", {})
        items = raw_data.get("items", [])

        # Simulate processing that might fail
        if should_fail:
            raise ValueError("Processing failed: simulated error for demonstration")

        processed = [f"processed_{item}" for item in items]
        ctx.set("processed_data", processed)

        return {"processed": len(processed), "data": processed}

    @ao.step(name="save", deps=["process"], description="Save results")
    async def save(ctx):
        """
        Save step with graceful degradation.

        Pattern: Handle missing data gracefully
        """
        processed_data = ctx.get("processed_data", [])

        if not processed_data:
            # Graceful degradation - log but don't fail
            return {"saved": 0, "message": "Nothing to save"}

        # Simulate save
        ctx.set("save_count", len(processed_data))
        return {"saved": len(processed_data), "items": processed_data}

    @ao.chain(name="error_demo_chain")
    class ErrorDemoChain:
        steps = ["fetch", "process", "save"]

    return ao


async def run_with_error_handling(should_fail: bool = False) -> None:
    """
    Run the workflow with proper error handling.

    This demonstrates the recommended pattern for production code.
    """
    ao = create_error_handling_orchestrator(should_fail=should_fail)

    print("=" * 60)
    print("Running workflow with error handling...")
    print("=" * 60)

    try:
        # Always wrap ao.launch() in try-except
        result = await ao.launch("error_demo_chain", {"input": "test"})

        # Check success status
        if result["success"]:
            print("\n✓ Workflow completed successfully!")
            print(f"  Duration: {result['duration_ms']:.2f}ms")

            # Access step results safely
            for step_result in result.get("results", []):
                step_name = step_result.get("step", "unknown")
                output = step_result.get("output", {})
                print(f"  Step '{step_name}': {output}")

        else:
            # Handle workflow failure
            error = result.get("error", {})
            print("\n✗ Workflow failed!")
            print(f"  Failed step: {error.get('step', 'unknown')}")
            print(f"  Error: {error.get('message', 'Unknown error')}")

            # Show partial results (steps that completed before failure)
            print("\n  Partial results (completed steps):")
            for step_result in result.get("results", []):
                if not step_result.get("error"):
                    print(f"    - {step_result.get('step')}: {step_result.get('output')}")

    except Exception as e:
        # Catch unexpected errors (network issues, serialization errors, etc.)
        print(f"\n✗ Unexpected error: {type(e).__name__}: {e}")
        raise  # Re-raise in production for proper logging


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Error Handling Example",
        epilog="""
Examples:
    python error_handling.py          # Run successfully
    python error_handling.py --fail   # Simulate failure
        """
    )
    parser.add_argument(
        "--fail",
        action="store_true",
        help="Simulate a failure in the process step"
    )
    args = parser.parse_args()

    print("\nError Handling Patterns Demo")
    print("-" * 40)

    if args.fail:
        print("Mode: Simulating failure\n")
    else:
        print("Mode: Normal execution\n")

    asyncio.run(run_with_error_handling(should_fail=args.fail))


if __name__ == "__main__":
    main()
