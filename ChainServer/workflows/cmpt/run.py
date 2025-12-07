#!/usr/bin/env python3
"""
CMPT - Client Meeting Prep Tool Runner

Entry point for running the CMPT chain.

Usage:
    cd workflows/cmpt
    python run.py
    python run.py --company "Microsoft"
    python run.py --company "Apple" --use-mcp
"""

import argparse
import asyncio
import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Suppress asyncio cleanup warnings from MCP SDK's streamablehttp_client
# These occur during garbage collection after the event loop exits and are harmless
warnings.filterwarnings("ignore", message=".*cancel scope.*different task.*")
warnings.filterwarnings("ignore", message=".*coroutine.*was never awaited.*")


def _setup_async_exception_handler():
    """Set up custom exception handler to suppress MCP SDK cleanup errors."""
    import sys

    # Suppress the BaseExceptionGroup errors from MCP SDK's streamablehttp_client
    # These occur during async generator cleanup and are harmless
    def custom_excepthook(exc_type, exc_value, exc_tb):
        # Suppress anyio/MCP cleanup errors
        error_str = str(exc_value)
        if any(x in error_str for x in [
            "cancel scope", "different task", "streamablehttp_client",
            "GeneratorExit", "BaseExceptionGroup"
        ]):
            return  # Suppress silently

        # For BaseExceptionGroup, check if all sub-exceptions are cleanup-related
        if exc_type.__name__ == "BaseExceptionGroup":
            return  # Suppress MCP cleanup exception groups

        # Otherwise use default handler
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = custom_excepthook


_setup_async_exception_handler()


def _suppress_mcp_cleanup_logging():
    """Suppress MCP SDK cleanup error logging."""
    import logging

    # Create a filter to suppress MCP cleanup errors
    class MCPCleanupFilter(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            # Suppress async generator cleanup errors from MCP
            if any(x in msg for x in [
                "streamablehttp_client", "async_generator", "cancel scope",
                "different task", "GeneratorExit", "BaseExceptionGroup"
            ]):
                return False
            return True

    # Add filter to root logger and asyncio logger
    logging.getLogger().addFilter(MCPCleanupFilter())
    logging.getLogger("asyncio").addFilter(MCPCleanupFilter())


_suppress_mcp_cleanup_logging()

# Load environment variables from .env file
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Ensure cmpt package can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentorchestrator import AgentOrchestrator

# Import from workflows.cmpt package
import workflows.cmpt.chain as cmpt_chain
import workflows.cmpt.config as cmpt_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def run_cmpt(company: str, meeting_date: str, use_mcp: bool = False) -> dict:
    """
    Run the CMPT chain.
    
    Args:
        company: Company name
        meeting_date: Meeting date (YYYY-MM-DD)
        use_mcp: Whether to use MCP agents (auto-detected if not specified)
        
    Returns:
        Chain execution result
    """
    # Auto-detect MCP agents if available
    if not use_mcp and cmpt_config.Config.has_mcp_agents():
        use_mcp = True
        logger.info("Auto-detected MCP agent configuration - enabling MCP mode")
    
    logger.info("=" * 80)
    logger.info("CMPT - Client Meeting Prep Tool")
    logger.info("=" * 80)
    logger.info(f"Company: {company}")
    logger.info(f"Meeting Date: {meeting_date}")
    logger.info(f"MCP Mode: {use_mcp}")
    logger.info("=" * 80)

    # Create orchestrator
    ao = AgentOrchestrator(name="cmpt", isolated=True)

    # Get MCP configuration if needed
    mcp_config = None
    if use_mcp:
        sec_agent = cmpt_config.Config.get_agent("sec")
        earnings_agent = cmpt_config.Config.get_agent("earnings")
        news_agent = cmpt_config.Config.get_agent("news")
        
        mcp_config = {
            "sec_url": sec_agent.get("mcp_url") if sec_agent else None,
            "earnings_url": earnings_agent.get("mcp_url") if earnings_agent else None,
            "news_url": news_agent.get("mcp_url") if news_agent else None,
            "sec_token": sec_agent.get("mcp_bearer_token") if sec_agent else None,
            "earnings_token": earnings_agent.get("mcp_bearer_token") if earnings_agent else None,
            "news_token": news_agent.get("mcp_bearer_token") if news_agent else None,
        }
        logger.info(f"MCP Config loaded: {sum(1 for v in [mcp_config['sec_url'], mcp_config['earnings_url'], mcp_config['news_url']] if v)} agent(s)")


    # Register chain
    cmpt_chain.register_cmpt_chain(ao, use_mcp=use_mcp, mcp_config=mcp_config)
    logger.info("Chain registered: context_builder -> content_prioritization -> response_builder")

    # Build request
    request = {
        "corporate_company_name": company,
        "meeting_datetime": meeting_date,
    }

    # Execute chain
    logger.info("Executing chain...")
    result = await ao.launch("cmpt_chain", {"request": request})

    # Log results
    logger.info("=" * 80)
    if result.get("success"):
        logger.info("RESULT: Success")
        logger.info(f"Duration: {result.get('duration_ms', 0):.0f}ms")

        # Log step results
        for step_name, step_result in result.get("step_results", {}).items():
            status = "PASS" if step_result.get("success") else "FAIL"
            logger.info(f"  [{status}] {step_name}")

        # Get context data - the chain stores outputs in context
        ctx = result.get("context", {})
        data = ctx.get("data", {}) if isinstance(ctx, dict) else {}

        # Get the final_response (ChainResponse object)
        final_response = data.get("final_response")
        response_output = data.get("response_output")

        # Show agent execution summary with data preview
        if response_output:
            logger.info("")
            logger.info("AGENT EXECUTION SUMMARY:")
            logger.info("-" * 80)

            # Get agent_results - could be object or dict
            agent_results = {}
            if hasattr(response_output, 'agent_results'):
                agent_results = response_output.agent_results
            elif isinstance(response_output, dict):
                agent_results = response_output.get('agent_results', {})

            for agent_name, agent_result in agent_results.items():
                # Handle both object and dict formats
                if hasattr(agent_result, 'success'):
                    success = agent_result.success
                    duration = getattr(agent_result, 'duration_ms', None)
                    item_count = getattr(agent_result, 'item_count', 0)
                    error = getattr(agent_result, 'error', None)
                    data = getattr(agent_result, 'data', {})
                elif isinstance(agent_result, dict):
                    success = agent_result.get('success', False)
                    duration = agent_result.get('duration_ms')
                    item_count = agent_result.get('item_count', 0)
                    error = agent_result.get('error')
                    data = agent_result.get('data', {})
                else:
                    continue

                status = "SUCCESS" if success else "FAILED"
                msg = f"  {agent_name}: {status}"
                if duration:
                    msg += f" ({duration:.0f}ms)"
                if item_count:
                    msg += f" - {item_count} items"
                if not success and error:
                    msg += f" - {error}"
                logger.info(msg)

                # Show data preview for successful agents
                if success and data:
                    import json
                    data_preview = json.dumps(data, indent=2, default=str)[:500]
                    if len(data_preview) >= 500:
                        data_preview = data_preview[:497] + "..."
                    for line in data_preview.split('\n')[:10]:  # Show first 10 lines
                        logger.info(f"    {line}")
                    if data_preview.count('\n') > 10:
                        logger.info(f"    ... (truncated)")

            # Show parsed agent chunks (what would go to LLM)
            parsed_chunks = None
            if hasattr(response_output, 'parsed_data_agent_chunks'):
                parsed_chunks = response_output.parsed_data_agent_chunks
            elif isinstance(response_output, dict):
                parsed_chunks = response_output.get('parsed_data_agent_chunks', {})

            if parsed_chunks:
                logger.info("")
                logger.info("AGENT DATA CHUNKS (for LLM):")
                logger.info("-" * 80)
                for agent_name, chunk in parsed_chunks.items():
                    if chunk:
                        preview = chunk[:300] + "..." if len(chunk) > 300 else chunk
                        logger.info(f"  [{agent_name}]: {len(chunk)} chars")
                        for line in preview.split('\n')[:5]:
                            logger.info(f"    {line}")
                    else:
                        logger.info(f"  [{agent_name}]: (empty)")

        # Show prepared content
        if final_response:
            prepared_content = None
            if hasattr(final_response, 'prepared_content'):
                prepared_content = final_response.prepared_content
            elif isinstance(final_response, dict):
                prepared_content = final_response.get('prepared_content')

            if prepared_content:
                logger.info("")
                logger.info("PREPARED CONTENT:")
                logger.info("-" * 80)
                print(prepared_content)  # Use print for better formatting
                logger.info("-" * 80)
            else:
                logger.info("")
                logger.info("(No prepared content generated - LLM client may not be configured)")

        # Show financial metrics if available
        if final_response:
            metrics = None
            if hasattr(final_response, 'financial_metrics'):
                metrics = final_response.financial_metrics
            elif isinstance(final_response, dict):
                metrics = final_response.get('financial_metrics')

            if metrics and isinstance(metrics, dict) and any(metrics.values()):
                logger.info("")
                logger.info("FINANCIAL METRICS:")
                logger.info("-" * 80)
                for key, value in metrics.items():
                    if value is not None:
                        logger.info(f"  {key}: {value}")
    else:
        logger.error("RESULT: Failed")
        logger.error(f"Error: {result.get('error')}")

    logger.info("=" * 80)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CMPT - Client Meeting Prep Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py
  python run.py --company "Microsoft"
  python run.py --company "Apple" --use-mcp

Pipeline:
  1. context_builder        - Extract company, temporal, persona info
  2. content_prioritization - Prioritize sources, generate subqueries
  3. response_builder       - Execute agents, build final response
        """,
    )
    parser.add_argument("--company", default="Apple Inc", help="Company name (default: Apple Inc)",)
    parser.add_argument("--meeting-date", default=datetime.now().strftime("%Y-%m-%d"), help="Meeting date in YYYY-MM-DD format (default: today)",)
    parser.add_argument("--use-mcp", action="store_true", help="Use MCP agents instead of mocks (requires MCP server configuration)",)

    args = parser.parse_args()
    asyncio.run(run_cmpt(args.company, args.meeting_date, args.use_mcp))