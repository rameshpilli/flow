#!/usr/bin/env python3
"""
CMPT - Client Meeting Prep Tool

USAGE:
    python cmpt/run.py
    python cmpt/run.py --company "Microsoft"
    python cmpt/run.py --company "Apple" --use-mcp
"""

import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path

# Load .env file before importing config
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from agentorchestrator import AgentOrchestrator
from cmpt.chain import register_cmpt_chain

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def main(company: str, meeting_date: str, use_mcp: bool = False):
    """Run the CMPT chain."""
    print("\n" + "═" * 60)
    print("  CMPT - Client Meeting Prep Tool")
    print("═" * 60)
    print("\nArchitecture:")
    print("  AgentOrchestrator → @ao.step(), @ao.chain(), BaseAgent")
    print("  CMPT chain.py     → 3 steps: context → prioritization → response")
    print("═" * 60 + "\n")

    # Create orchestrator
    ao = AgentOrchestrator(name="cmpt", isolated=True)

    # Register the CMPT chain (defined in chain.py)
    mcp_config = None
    if use_mcp:
        from agentorchestrator.config import get_config
        config = get_config()

        # Get agent URLs from config (loaded from AGENT_CONFIG JSON in .env)
        sec_agent = config.agents.get("sec")
        earnings_agent = config.agents.get("earnings")
        news_agent = config.agents.get("news")

        mcp_config = {
            "sec_url": sec_agent.url if sec_agent else None,
            "earnings_url": earnings_agent.url if earnings_agent else None,
            "news_url": news_agent.url if news_agent else None,
        }

        print("MCP Agent URLs (from AGENT_CONFIG):")
        for name, url in mcp_config.items():
            print(f"  {name}: {url or '(not configured)'}")
        print()

    register_cmpt_chain(ao, use_mcp=use_mcp, mcp_config=mcp_config)

    # Validate chain
    print("✓ Chain registered")
    print(f"  Steps: context_builder → content_prioritization → response_builder\n")

    # Build request
    request = {
        "corporate_company_name": company,
        "meeting_datetime": meeting_date,
    }

    print(f"Company: {company}")
    print(f"Meeting Date: {meeting_date}")
    print(f"Using MCP Agents: {use_mcp}")
    print("-" * 40 + "\n")

    # Run the chain
    print("Running chain...")
    result = await ao.launch("cmpt_chain", {"request": request})

    # Show results
    print("\n" + "-" * 40)
    if result.get("success"):
        print("✅ Chain completed successfully!")
        print(f"Duration: {result.get('duration_ms', 0):.0f}ms")

        # Show step results
        print("\nStep Results:")
        for step_name, step_result in result.get("step_results", {}).items():
            status = "✓" if step_result.get("success") else "✗"
            print(f"  {status} {step_name}")

        # Show prepared content if available
        ctx = result.get("context", {})
        final_response = ctx.get("final_response")
        if final_response:
            print("\n" + "=" * 40)
            print("PREPARED CONTENT:")
            print("=" * 40)
            content = getattr(final_response, 'prepared_content', None) or final_response.get('prepared_content')
            print(content or "(No content generated)")
    else:
        print("❌ Chain failed")
        print(f"Error: {result.get('error')}")

    print("\n" + "═" * 60 + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CMPT - Client Meeting Prep Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python examples/cmpt/run.py
  python examples/cmpt/run.py --company "Microsoft"
  python examples/cmpt/run.py --company "Apple" --use-mcp

Chain Pipeline:
  Step 1: context_builder        → Extract company, temporal, persona info
  Step 2: content_prioritization → Prioritize sources, generate subqueries
  Step 3: response_builder       → Execute agents, build final response
        """
    )
    parser.add_argument("--company", default="Apple Inc", help="Company name")
    parser.add_argument("--meeting-date", default=datetime.now().strftime("%Y-%m-%d"), help="Meeting date")
    parser.add_argument("--use-mcp", action="store_true", help="Use MCP agents (requires configured servers)")
    args = parser.parse_args()

    asyncio.run(main(args.company, args.meeting_date, args.use_mcp))
