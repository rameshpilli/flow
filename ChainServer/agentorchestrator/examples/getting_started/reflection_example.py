"""
Self-Critique / Reflection Example
===================================

Demonstrates agent self-critique with quality scoring and automatic revision.

Usage:
    python reflection_example.py
    python reflection_example.py --low-quality   # Force low quality to trigger revision

What this example demonstrates:
    - Using ReflectionMiddleware for automatic quality review
    - Using @reflect decorator on specific steps
    - Quality scoring and revision cycles
    - Accessing reflection trace results

Expected output:
    Step 1: Generating initial report...
    [Reflection] Critiquing output...
    [Reflection] Quality score: 0.85 (threshold: 0.8)
    [Reflection] Output passed quality threshold

    Final Report:
    Executive Summary: ...

    Reflection Trace:
    - Quality Score: 0.85
    - Revisions: 0
    - Passed Threshold: True
"""

from __future__ import annotations

import argparse
import asyncio

from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware import (
    ReflectionMiddleware,
    ReflectionConfig,
    reflect,
)


# Simulated LLM client for demonstration
class MockLLMClient:
    """Mock LLM client that simulates critique and revision responses."""

    def __init__(self, force_low_quality: bool = False):
        self.force_low_quality = force_low_quality
        self.critique_count = 0

    async def generate_async(self, prompt: str, **kwargs) -> str:
        """Simulate LLM response based on prompt content."""
        if "critique" in prompt.lower() or "review" in prompt.lower():
            self.critique_count += 1
            # First critique returns low score if forced, otherwise good score
            if self.force_low_quality and self.critique_count == 1:
                return """
                Quality Assessment:
                - Clarity: 6/10 - Could be more concise
                - Completeness: 5/10 - Missing key details
                - Accuracy: 7/10 - Generally correct

                Overall Score: 0.6
                Recommendation: Revise to add more specific details and improve clarity.
                """
            else:
                return """
                Quality Assessment:
                - Clarity: 9/10 - Well structured and clear
                - Completeness: 8/10 - Covers main points
                - Accuracy: 9/10 - Factually correct

                Overall Score: 0.87
                Recommendation: Output meets quality standards.
                """
        elif "revise" in prompt.lower():
            return """
            REVISED Executive Summary:

            This comprehensive analysis examines key market trends with specific data points:
            - Market growth: 15% YoY increase
            - Key drivers: AI adoption, cloud migration
            - Risk factors: Economic uncertainty, regulatory changes

            The analysis is based on Q4 2024 data from industry reports.
            """
        else:
            return "Generated content based on the prompt."


def create_reflection_orchestrator(
    llm_client: MockLLMClient,
) -> AgentOrchestrator:
    """
    Create an orchestrator demonstrating reflection/self-critique.

    The ReflectionMiddleware automatically:
    1. Critiques step outputs using an LLM
    2. Scores the quality (0.0 - 1.0)
    3. Revises if below threshold
    4. Stores trace for debugging

    Returns:
        Configured AgentOrchestrator instance
    """
    ao = AgentOrchestrator(name="reflection_example", isolated=True)

    # Configure reflection middleware
    reflection_config = ReflectionConfig(
        quality_threshold=0.8,  # Minimum score to accept (0.0-1.0)
        max_revisions=2,  # Max revision attempts
        critique_prompt="""Review this output for:
        - Clarity: Is it easy to understand?
        - Completeness: Does it cover all key points?
        - Accuracy: Is the information correct?

        Provide a score from 0.0 to 1.0 and recommendations.""",
        revision_prompt="""Based on the critique, revise this output to improve:
        {critique_feedback}

        Original output:
        {original_output}""",
        store_trace=True,  # Store reflection trace in context
        applies_to=["generate_report"],  # Only apply to specific steps
    )

    # Add reflection middleware with the mock LLM
    ao.use(ReflectionMiddleware(
        config=reflection_config,
        llm_client=llm_client,
    ))

    @ao.step(name="gather_data", description="Gather research data")
    async def gather_data(ctx):
        """Step 1: Gather data (no reflection applied)."""
        print("Step 1: Gathering research data...")

        data = {
            "market_size": "$500B",
            "growth_rate": "15%",
            "key_players": ["Company A", "Company B", "Company C"],
            "trends": ["AI adoption", "Cloud migration", "Sustainability"],
        }

        ctx.set("research_data", data)
        return {"data_gathered": True, "records": 4}

    @ao.step(name="generate_report", deps=["gather_data"], description="Generate report with reflection")
    async def generate_report(ctx):
        """
        Step 2: Generate report (reflection IS applied).

        The ReflectionMiddleware will:
        1. Let this step run and produce output
        2. Critique the output using the LLM
        3. If score < 0.8, revise and re-critique
        4. Store the reflection trace in context
        """
        print("Step 2: Generating initial report...")

        data = ctx.get("research_data")

        # Generate initial report
        report = f"""
Executive Summary:

Market Analysis Report

The market is valued at {data['market_size']} with a growth rate of {data['growth_rate']}.

Key Players:
{chr(10).join(f'- {player}' for player in data['key_players'])}

Current Trends:
{chr(10).join(f'- {trend}' for trend in data['trends'])}

This analysis provides a foundation for strategic decision-making.
        """.strip()

        ctx.set("report", report)
        return {"report": report}

    # Alternative: Use @reflect decorator for per-step configuration
    @reflect(
        critique_prompt="Check this summary for accuracy and clarity.",
        quality_threshold=0.75,
        max_revisions=1,
    )
    @ao.step(name="summarize", deps=["generate_report"], description="Create executive summary")
    async def summarize(ctx):
        """
        Step 3: Summarize (using @reflect decorator).

        The @reflect decorator provides step-specific reflection config.
        """
        print("Step 3: Creating executive summary...")

        report = ctx.get("report")

        # Extract first paragraph as summary
        summary = report.split("\n\n")[0] if report else "No report available"

        ctx.set("summary", summary)
        return {"summary": summary}

    @ao.chain(name="report_chain")
    class ReportChain:
        """Report generation chain with reflection on key steps."""
        steps = ["gather_data", "generate_report", "summarize"]

    return ao


async def run_reflection_example(force_low_quality: bool = False) -> dict:
    """
    Run the reflection example.

    Args:
        force_low_quality: If True, simulate low-quality output to trigger revision

    Returns:
        Result dictionary with report and reflection traces
    """
    llm_client = MockLLMClient(force_low_quality=force_low_quality)
    ao = create_reflection_orchestrator(llm_client)

    print("=" * 60)
    print("Running Report Chain with Reflection")
    print("=" * 60)
    if force_low_quality:
        print("(Forcing low-quality output to demonstrate revision cycle)")
    print()

    result = await ao.launch("report_chain", {})

    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Reflection/Self-Critique Example")
    parser.add_argument(
        "--low-quality",
        action="store_true",
        help="Force low quality output to trigger revision",
    )
    args = parser.parse_args()

    result = asyncio.run(run_reflection_example(args.low_quality))

    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)

    if result["success"]:
        # Show the final report
        report = result["context"]["data"].get("report", "No report generated")
        print("\nFinal Report:")
        print("-" * 40)
        print(report)

        # Show reflection traces if available
        traces = result["context"]["data"].get("_reflection_trace", {})
        if traces:
            print("\n" + "=" * 60)
            print("Reflection Traces")
            print("=" * 60)
            for step_name, trace in traces.items():
                print(f"\nStep: {step_name}")
                print(f"  - Quality Score: {trace.get('quality_score', 'N/A')}")
                print(f"  - Revisions: {trace.get('revision_count', 0)}")
                print(f"  - Passed Threshold: {trace.get('passed_threshold', 'N/A')}")
                if trace.get('critique_feedback'):
                    print(f"  - Critique: {trace['critique_feedback'][:100]}...")
        else:
            print("\n(No reflection traces - middleware may not have LLM configured)")
            print("In production, configure ReflectionMiddleware with a real LLM client.")
    else:
        print(f"\nChain failed: {result.get('error')}")


if __name__ == "__main__":
    main()
