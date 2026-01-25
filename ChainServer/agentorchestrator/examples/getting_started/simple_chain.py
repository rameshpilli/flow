"""
Simple Chain Example
====================

A multi-step pipeline demonstrating step dependencies.

Usage:
    python simple_chain.py

What this example demonstrates:
    - Step dependencies with deps=["step_name"]
    - Passing data between steps via context
    - Chain execution order based on DAG resolution

Expected output:
    Step 1: Fetching data...
    Step 2: Processing data...
    Step 3: Summarizing results...

    Result:
    - Fetched 5 items
    - Processed into [2, 4, 6, 8, 10]
    - Sum: 30, Count: 5
"""

from __future__ import annotations

import asyncio

from agentorchestrator import AgentOrchestrator


def create_simple_chain_orchestrator() -> AgentOrchestrator:
    """
    Create a simple multi-step chain orchestrator.

    Pipeline:
        fetch -> process -> summarize

    Returns:
        Configured AgentOrchestrator instance
    """
    ao = AgentOrchestrator(name="simple_chain", isolated=True)

    @ao.step(name="fetch", description="Fetch raw data")
    async def fetch(ctx):
        """
        Step 1: Fetch data from a source.

        In a real application, this might call an API or database.
        """
        print("Step 1: Fetching data...")

        # Simulate fetching data
        data = [1, 2, 3, 4, 5]

        # Store in context for downstream steps
        ctx.set("raw_data", data)

        return {"fetched": True, "count": len(data)}

    @ao.step(name="process", deps=["fetch"], description="Process the fetched data")
    async def process(ctx):
        """
        Step 2: Process the fetched data.

        This step depends on 'fetch' - it won't run until fetch completes.
        """
        print("Step 2: Processing data...")

        # Read from context (set by fetch step)
        raw_data = ctx.get("raw_data", [])

        # Transform the data
        processed = [x * 2 for x in raw_data]

        # Store processed data for downstream
        ctx.set("processed_data", processed)

        return {"processed": True, "result": processed}

    @ao.step(name="summarize", deps=["process"], description="Summarize the results")
    async def summarize(ctx):
        """
        Step 3: Summarize the processed data.

        This step depends on 'process' - runs last in the chain.
        """
        print("Step 3: Summarizing results...")

        processed_data = ctx.get("processed_data", [])

        summary = {
            "sum": sum(processed_data),
            "count": len(processed_data),
            "min": min(processed_data) if processed_data else 0,
            "max": max(processed_data) if processed_data else 0,
        }

        return summary

    @ao.chain(name="data_pipeline")
    class DataPipeline:
        """
        Three-step data pipeline.

        Execution order is determined by dependencies:
        1. fetch (no deps - runs first)
        2. process (deps: fetch)
        3. summarize (deps: process)
        """
        steps = ["fetch", "process", "summarize"]

    return ao


async def run_simple_chain() -> dict:
    """
    Run the simple chain example.

    Returns:
        Result dictionary with summary statistics
    """
    ao = create_simple_chain_orchestrator()

    result = await ao.launch("data_pipeline", {})

    return result


def main():
    """CLI entry point."""
    result = asyncio.run(run_simple_chain())

    print("\nResult:")
    print(f"  - Sum: {result.get('sum')}")
    print(f"  - Count: {result.get('count')}")
    print(f"  - Min: {result.get('min')}")
    print(f"  - Max: {result.get('max')}")


if __name__ == "__main__":
    main()
