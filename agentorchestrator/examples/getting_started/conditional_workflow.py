"""
Conditional Workflow Example
============================

Demonstrates DAG workflows with conditional logic:

    validate -> (route_decision) -> [fast_path OR deep_analysis] -> respond

Key patterns shown:
    - Conditional step execution based on context
    - Early termination when conditions aren't met
    - Dynamic routing between workflow branches
    - Error handling in DAG workflows

Usage:
    python conditional_workflow.py
    python conditional_workflow.py --query "simple question"
    python conditional_workflow.py --query "complex analysis needed"

What this example demonstrates:
    - How to add conditional logic to DAG workflows
    - Pattern for routing to different execution paths
    - Proper error handling in production workflows
"""

from __future__ import annotations

import asyncio
import argparse

from agentorchestrator import AgentOrchestrator


def create_conditional_workflow() -> AgentOrchestrator:
    """
    Create a workflow with conditional execution paths.

    DAG Structure:
        validate
            |
        route_decision
           /    \\
    fast_path  deep_analysis  (only one runs based on condition)
           \\    /
          respond
    """
    ao = AgentOrchestrator(name="conditional_workflow", isolated=True)

    @ao.step(name="validate", description="Validate input and check prerequisites")
    async def validate(ctx):
        """
        First step: validate input and set routing flags.

        This step demonstrates:
        - Input validation with proper error handling
        - Setting context flags for downstream routing
        """
        query = ctx.get("query", "").strip()

        # Validation with proper error handling
        if not query:
            ctx.set("validation_error", "Query cannot be empty")
            ctx.set("is_valid", False)
            return {"valid": False, "error": "Query cannot be empty"}

        if len(query) < 3:
            ctx.set("validation_error", "Query too short (min 3 chars)")
            ctx.set("is_valid", False)
            return {"valid": False, "error": "Query too short"}

        # Classify query complexity for routing
        complex_keywords = ["analyze", "compare", "research", "deep", "complex"]
        is_complex = any(kw in query.lower() for kw in complex_keywords)

        ctx.set("is_valid", True)
        ctx.set("is_complex", is_complex)
        ctx.set("validated_query", query)

        return {
            "valid": True,
            "is_complex": is_complex,
            "query": query,
        }

    @ao.step(name="route_decision", deps=["validate"], description="Decide execution path")
    async def route_decision(ctx):
        """
        Routing step: decide which path to take.

        This step demonstrates:
        - Checking upstream results
        - Early termination on validation failure
        - Setting flags to control downstream execution
        """
        # Check if validation passed
        if not ctx.get("is_valid", False):
            ctx.set("skip_processing", True)
            ctx.set("skip_reason", ctx.get("validation_error", "Validation failed"))
            return {"route": "skip", "reason": ctx.get("validation_error")}

        # Route based on complexity
        is_complex = ctx.get("is_complex", False)
        route = "deep_analysis" if is_complex else "fast_path"

        ctx.set("selected_route", route)
        ctx.set("skip_processing", False)

        return {"route": route, "is_complex": is_complex}

    @ao.step(name="fast_path", deps=["route_decision"], description="Quick response path")
    async def fast_path(ctx):
        """
        Fast path: for simple queries.

        This step demonstrates:
        - Conditional execution (skip if wrong route)
        - Returning early with skip indicator
        """
        # Conditional execution - skip if not our route
        selected_route = ctx.get("selected_route", "")
        if selected_route != "fast_path" or ctx.get("skip_processing"):
            return {"skipped": True, "reason": "Not fast_path route"}

        query = ctx.get("validated_query", "")

        # Simulate quick processing
        response = f"Quick answer for: {query}"
        ctx.set("response_draft", response)
        ctx.set("processing_type", "fast")

        return {"response": response, "type": "fast"}

    @ao.step(name="deep_analysis", deps=["route_decision"], description="Deep analysis path")
    async def deep_analysis(ctx):
        """
        Deep analysis path: for complex queries.

        This step demonstrates:
        - Conditional execution (skip if wrong route)
        - More elaborate processing
        """
        # Conditional execution - skip if not our route
        selected_route = ctx.get("selected_route", "")
        if selected_route != "deep_analysis" or ctx.get("skip_processing"):
            return {"skipped": True, "reason": "Not deep_analysis route"}

        query = ctx.get("validated_query", "")

        # Simulate deep analysis
        analysis = {
            "query": query,
            "findings": [
                "Finding 1: Detailed analysis point",
                "Finding 2: Supporting evidence",
                "Finding 3: Contextual information",
            ],
            "confidence": 0.85,
        }

        response = f"Deep analysis for '{query}':\n" + "\n".join(
            f"  - {f}" for f in analysis["findings"]
        )

        ctx.set("response_draft", response)
        ctx.set("processing_type", "deep")
        ctx.set("analysis_details", analysis)

        return {"response": response, "type": "deep", "analysis": analysis}

    @ao.step(
        name="respond",
        deps=["fast_path", "deep_analysis"],
        description="Finalize response"
    )
    async def respond(ctx):
        """
        Final step: format and return response.

        This step demonstrates:
        - Handling multiple upstream paths
        - Error response formatting
        - Aggregating results from conditional branches
        """
        # Handle validation failures
        if ctx.get("skip_processing"):
            error_msg = ctx.get("skip_reason", "Processing skipped")
            return {
                "success": False,
                "error": error_msg,
                "response": f"Error: {error_msg}",
            }

        # Get response from whichever path executed
        response_draft = ctx.get("response_draft", "No response generated")
        processing_type = ctx.get("processing_type", "unknown")

        # Format final response
        final_response = {
            "success": True,
            "response": response_draft,
            "processing_type": processing_type,
            "route_taken": ctx.get("selected_route", "unknown"),
        }

        ctx.set("final_response", final_response)
        return final_response

    @ao.chain(name="conditional_chain")
    class ConditionalChain:
        """
        Chain with conditional execution paths.

        Note: All steps are listed, but fast_path and deep_analysis
        skip execution based on the selected route.
        """
        steps = ["validate", "route_decision", "fast_path", "deep_analysis", "respond"]

    return ao


async def run_conditional_workflow(query: str) -> dict:
    """
    Run the conditional workflow with proper error handling.

    Args:
        query: The input query to process

    Returns:
        Result dictionary with success status and response
    """
    ao = create_conditional_workflow()

    try:
        result = await ao.launch("conditional_chain", {"query": query})

        if result["success"]:
            final_response = result["context"]["data"].get("final_response", {})
            return {
                "success": True,
                "response": final_response.get("response", ""),
                "route": final_response.get("route_taken", ""),
                "type": final_response.get("processing_type", ""),
            }
        else:
            return {
                "success": False,
                "error": result.get("error", {}).get("message", "Unknown error"),
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def main():
    """CLI entry point with examples."""
    parser = argparse.ArgumentParser(
        description="Conditional Workflow Example",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Simple query (takes fast path)
    python conditional_workflow.py --query "What is Python?"

    # Complex query (takes deep analysis path)
    python conditional_workflow.py --query "Analyze the performance implications"

    # Invalid query (demonstrates error handling)
    python conditional_workflow.py --query ""
        """
    )
    parser.add_argument(
        "--query",
        default="How does AgentOrchestrator work?",
        help="Query to process"
    )
    args = parser.parse_args()

    # Show the DAG structure
    ao = create_conditional_workflow()
    print("\nDAG Structure (all steps listed, conditional execution at runtime):")
    ao.graph("conditional_chain")

    # Run the workflow
    print(f"\nProcessing query: '{args.query}'")
    print("-" * 50)

    result = asyncio.run(run_conditional_workflow(args.query))

    if result["success"]:
        print(f"Route taken: {result['route']}")
        print(f"Processing type: {result['type']}")
        print(f"\nResponse:\n{result['response']}")
    else:
        print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
