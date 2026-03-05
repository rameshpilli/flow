
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
import sys
import warnings
from datetime import datetime
from pathlib import Path

# Suppress MCP SDK async generator cleanup warnings
# These occur during garbage collection after event loop exits and are harmless
warnings.filterwarnings("ignore", message=".*cancel scope.*different task.*")
warnings.filterwarnings("ignore", message=".*coroutine.*was never awaited.*")


def _suppress_mcp_cleanup_errors():
    """Suppress MCP SDK cleanup errors that appear on stderr during exit."""
    import sys
    
    # Custom exception hook to suppress MCP cleanup errors
    def custom_excepthook(exc_type, exc_value, exc_tb):
        error_str = str(exc_value)
        # Suppress anyio/MCP cleanup errors
        if any(x in error_str for x in [
            "cancel scope", "different task", "streamablehttp_client",
            "GeneratorExit", "BaseExceptionGroup", "async_generator"
        ]):
            return  # Suppress silently
        
        # For BaseExceptionGroup from MCP SDK
        if exc_type.__name__ == "BaseExceptionGroup":
            return  # Suppress
        
        # Otherwise use default handler
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    
    sys.excepthook = custom_excepthook
    
    # Also suppress in logging
    class MCPCleanupFilter(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            if any(x in msg for x in [
                "streamablehttp_client", "async_generator", "cancel scope",
                "different task", "GeneratorExit", "BaseExceptionGroup"
            ]):
                return False
            return True
    
    logging.getLogger().addFilter(MCPCleanupFilter())
    logging.getLogger("asyncio").addFilter(MCPCleanupFilter())


_suppress_mcp_cleanup_errors()

# Load .env file before importing config
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from agentorchestrator import AgentOrchestrator
from agentorchestrator.services.llm_gateway import create_llm_client_from_env
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

    # Create LLM client from environment variables
    llm_client = create_llm_client_from_env()
    if llm_client._is_configured():
        print("LLM Client: Configured with OAuth")
        print(f"  Server: {llm_client.server_url}")
        print(f"  Model: {llm_client.model_name}")
    else:
        print("LLM Client: Not configured (will use stub mode)")
        print("  Set LLM_SERVER_URL, LLM_OAUTH_ENDPOINT, LLM_CLIENT_ID, LLM_CLIENT_SECRET")
    print()

    # Create orchestrator
    ao = AgentOrchestrator(name="cmpt", isolated=True)

    # Register the CMPT chain (defined in chain.py)
    mcp_config = None
    if use_mcp:
        from agentorchestrator.config import get_config
        config = get_config()

        # Get agent configs (loaded from AGENT_CONFIG JSON in .env)
        sec_agent = config.agents.get("sec")
        earnings_agent = config.agents.get("earnings")
        news_agent = config.agents.get("news")

        # Build MCP config with URLs AND bearer tokens
        mcp_config = {
            "sec_url": sec_agent.url if sec_agent else None,
            "earnings_url": earnings_agent.url if earnings_agent else None,
            "news_url": news_agent.url if news_agent else None,
            # Pass bearer tokens for MCP authentication
            "sec_token": sec_agent.api_key if sec_agent else None,
            "earnings_token": earnings_agent.api_key if earnings_agent else None,
            "news_token": news_agent.api_key if news_agent else None,
        }

        print("MCP Agent Config (from AGENT_CONFIG):")
        print(f"  sec_url: {mcp_config['sec_url'] or '(not configured)'}")
        print(f"  sec_token: {'***' if mcp_config['sec_token'] else '(not configured)'}")
        print(f"  earnings_url: {mcp_config['earnings_url'] or '(not configured)'}")
        print(f"  earnings_token: {'***' if mcp_config['earnings_token'] else '(not configured)'}")
        print(f"  news_url: {mcp_config['news_url'] or '(not configured)'}")
        print(f"  news_token: {'***' if mcp_config['news_token'] else '(not configured)'}")
        print()

    register_cmpt_chain(ao, use_mcp=use_mcp, mcp_config=mcp_config, llm_client=llm_client)

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

        # Get context data
        ctx = result.get("context", {})
        data = ctx.get("data", {}) if isinstance(ctx, dict) else {}

        # Get all stage outputs
        context_output = data.get("context_output")
        prioritization_output = data.get("prioritization_output")
        response_output = data.get("response_output")
        final_response = data.get("final_response")

        # ═══════════════════════════════════════════════════════════════════
        # STAGE 1: Context Builder Output
        # ═══════════════════════════════════════════════════════════════════
        if context_output:
            print("\n" + "=" * 80)
            print("STAGE 1: CONTEXT BUILDER OUTPUT")
            print("-" * 80)

            # Company Info
            company_name = getattr(context_output, 'company_name', None) or (context_output.get('company_name') if isinstance(context_output, dict) else None)
            ticker = getattr(context_output, 'ticker', None) or (context_output.get('ticker') if isinstance(context_output, dict) else None)
            print(f"  Company: {company_name or 'N/A'}")
            print(f"  Ticker: {ticker or 'N/A'}")

            # Company Info details
            company_info = getattr(context_output, 'company_info', None) or (context_output.get('company_info') if isinstance(context_output, dict) else None)
            if company_info:
                industry = getattr(company_info, 'industry', None) or (company_info.get('industry') if isinstance(company_info, dict) else None)
                # sector = getattr(company_info, 'sector', None) or (company_info.get('sector') if isinstance(company_info, dict) else None)
                # market_cap = getattr(company_info, 'market_cap', None) or (company_info.get('market_cap') if isinstance(company_info, dict) else None)
                # cik = getattr(company_info, 'cik', None) or (company_info.get('cik') if isinstance(company_info, dict) else None)
                print(f"  Industry: {industry or 'N/A'}")
                # print(f"  Sector: {sector or 'N/A'}")
                # print(f"  Market Cap: {market_cap or 'N/A'}")
                # print(f"  CIK: {cik or 'N/A'}")

            # Temporal Context
            temporal_context = getattr(context_output, 'temporal_context', None) or (context_output.get('temporal_context') if isinstance(context_output, dict) else None)
            if temporal_context:
                print("\n  Temporal Context:")
                meeting_date = getattr(temporal_context, 'meeting_date', None) or (temporal_context.get('meeting_date') if isinstance(temporal_context, dict) else None)
                event_dt = getattr(temporal_context, 'event_dt', None) or (temporal_context.get('event_dt') if isinstance(temporal_context, dict) else None)
                days_to_earnings = getattr(temporal_context, 'days_to_earnings', None) or (temporal_context.get('days_to_earnings') if isinstance(temporal_context, dict) else None)
                fiscal_quarter = getattr(temporal_context, 'fiscal_quarter', None) or (temporal_context.get('fiscal_quarter') if isinstance(temporal_context, dict) else None)
                fiscal_year = getattr(temporal_context, 'fiscal_year', None) or (temporal_context.get('fiscal_year') if isinstance(temporal_context, dict) else None)
                news_lookback = getattr(temporal_context, 'news_lookback_days', None) or (temporal_context.get('news_lookback_days') if isinstance(temporal_context, dict) else None)

                print(f"    Meeting Date: {meeting_date or 'N/A'}")
                print(f"    Next Earnings: {event_dt or 'N/A'}")
                print(f"    Days to Earnings: {days_to_earnings if days_to_earnings is not None else 'N/A'}")
                print(f"    Fiscal Period: Q{fiscal_quarter} {fiscal_year}" if fiscal_quarter and fiscal_year else "    Fiscal Period: N/A")
                print(f"    News Lookback: {news_lookback} days" if news_lookback else "    News Lookback: N/A")

            # Personas
            personas = getattr(context_output, 'personas', None) or (context_output.get('personas') if isinstance(context_output, dict) else None)
            if personas:
                print(f"\n  Personas: {len(personas)} found")
                for p in personas[:3]:  # Show first 3
                    name = getattr(p, 'name', None) or (p.get('name') if isinstance(p, dict) else None)
                    is_internal = getattr(p, 'is_internal', None) or (p.get('is_internal') if isinstance(p, dict) else None)
                    role_type = "RBC" if is_internal else "Client"
                    print(f"    - {name} ({role_type})")

            # Timing
            timing = getattr(context_output, 'timing_ms', None) or (context_output.get('timing_ms') if isinstance(context_output, dict) else None)
            if timing:
                print(f"\n  Timing: {timing}")

        # ═══════════════════════════════════════════════════════════════════
        # STAGE 2: Content Prioritization Output
        # ═══════════════════════════════════════════════════════════════════
        if prioritization_output:
            print("\n" + "=" * 80)
            print("STAGE 2: CONTENT PRIORITIZATION OUTPUT")
            print("-" * 80)

            # Priority Distribution
            priority_dist = getattr(prioritization_output, 'priority_distribution', None) or (prioritization_output.get('priority_distribution') if isinstance(prioritization_output, dict) else None)
            if priority_dist:
                print("  Priority Distribution (weights for strategic analysis):")
                for agent, weight in priority_dist.items():
                    bar = "█" * (weight // 5)  # Visual bar
                    print(f"    {agent}: {weight}% {bar}")

            # Prioritization Reasoning
            reasoning = getattr(prioritization_output, 'prioritization_reasoning', None) or (prioritization_output.get('prioritization_reasoning') if isinstance(prioritization_output, dict) else None)
            if reasoning:
                print(f"\n  Reasoning: {reasoning}")

            # Subqueries
            subqueries = getattr(prioritization_output, 'subqueries', None) or (prioritization_output.get('subqueries') if isinstance(prioritization_output, dict) else None)
            if subqueries:
                print(f"\n  Subqueries Generated: {len(subqueries)}")
                for sq in subqueries:
                    agent = getattr(sq, 'agent', None) or (sq.get('agent') if isinstance(sq, dict) else None)
                    priority = getattr(sq, 'priority', None) or (sq.get('priority') if isinstance(sq, dict) else None)
                    timeout = getattr(sq, 'timeout_ms', None) or (sq.get('timeout_ms') if isinstance(sq, dict) else None)
                    params = getattr(sq, 'params', None) or (sq.get('params') if isinstance(sq, dict) else None)

                    priority_str = str(priority).split('.')[-1] if priority else 'N/A'
                    print(f"    - {agent}: priority={priority_str}, timeout={timeout}ms")
                    if params:
                        # Show key params
                        param_preview = ", ".join(f"{k}={v}" for k, v in list(params.items())[:3])
                        print(f"      params: {param_preview}")

            # Prioritized Sources
            sources = getattr(prioritization_output, 'prioritized_sources', None) or (prioritization_output.get('prioritized_sources') if isinstance(prioritization_output, dict) else None)
            if sources:
                print(f"\n  Prioritized Sources: {len(sources)}")
                for src in sources:
                    source_name = getattr(src, 'source', None) or (src.get('source') if isinstance(src, dict) else None)
                    priority = getattr(src, 'priority', None) or (src.get('priority') if isinstance(src, dict) else None)
                    enabled = getattr(src, 'enabled', True) or (src.get('enabled', True) if isinstance(src, dict) else True)

                    source_str = str(source_name).split('.')[-1] if source_name else 'N/A'
                    priority_str = str(priority).split('.')[-1] if priority else 'N/A'
                    status = "✓" if enabled else "✗"
                    print(f"    {status} {source_str}: {priority_str}")

        # ═══════════════════════════════════════════════════════════════════
        # STAGE 3: Response Builder Output
        # ═══════════════════════════════════════════════════════════════════

        # Show detailed agent execution summary (like workflows version)
        if response_output:
            print("\n" + "=" * 80)
            print("STAGE 3: RESPONSE BUILDER OUTPUT")
            print("-" * 80)
            print("\nAGENT EXECUTION SUMMARY:")
            print("-" * 80)

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
                    data_obj = getattr(agent_result, 'data', {})
                elif isinstance(agent_result, dict):
                    success = agent_result.get('success', False)
                    duration = agent_result.get('duration_ms')
                    item_count = agent_result.get('item_count', 0)
                    error = agent_result.get('error')
                    data_obj = agent_result.get('data', {})
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
                print(msg)

                # Show data preview for successful agents
                if success and data_obj:
                    import json
                    data_preview = json.dumps(data_obj, indent=2, default=str)[:500]
                    if len(data_preview) >= 500:
                        data_preview = data_preview[:497] + "..."
                    for line in data_preview.split('\n')[:10]:  # Show first 10 lines
                        print(f"    {line}")
                    if data_preview.count('\n') > 10:
                        print(f"    ... (truncated)")

            # Show parsed agent chunks (what would go to LLM)
            parsed_chunks = None
            if hasattr(response_output, 'parsed_data_agent_chunks'):
                parsed_chunks = response_output.parsed_data_agent_chunks
            elif isinstance(response_output, dict):
                parsed_chunks = response_output.get('parsed_data_agent_chunks', {})

            if parsed_chunks:
                print("")
                print("AGENT DATA CHUNKS (for LLM):")
                print("-" * 80)
                for agent_name, chunk in parsed_chunks.items():
                    if chunk:
                        preview = chunk[:300] + "..." if len(chunk) > 300 else chunk
                        print(f"  [{agent_name}]: {len(chunk)} chars")
                        for line in preview.split('\n')[:5]:
                            print(f"    {line}")
                    else:
                        print(f"  [{agent_name}]: (empty)")

        # Show prepared content
        if final_response:
            prepared_content = None
            if hasattr(final_response, 'prepared_content'):
                prepared_content = final_response.prepared_content
            elif isinstance(final_response, dict):
                prepared_content = final_response.get('prepared_content')

            if prepared_content:
                print("")
                print("PREPARED CONTENT:")
                print("-" * 80)
                print(prepared_content)
                print("-" * 80)
            else:
                print("")
                print("(No prepared content generated - LLM client may not be configured)")

        # Show financial metrics if available
        if final_response:
            metrics = None
            if hasattr(final_response, 'financial_metrics'):
                metrics = final_response.financial_metrics
            elif isinstance(final_response, dict):
                metrics = final_response.get('financial_metrics')

            if metrics and isinstance(metrics, dict) and any(metrics.values()):
                print("")
                print("FINANCIAL METRICS:")
                print("-" * 80)
                for key, value in metrics.items():
                    if value is not None:
                        print(f"  {key}: {value}")
    else:
        print("❌ Chain failed")
        print(f"Error: {result.get('error')}")

    print("\n" + "═" * 60 + "\n")
    return result


def _suppress_stderr_on_exit():
    """Suppress MCP SDK async generator cleanup errors on exit."""
    import io

    class FilteredStderr(io.TextIOWrapper):
        """Stderr wrapper that filters out MCP cleanup errors."""
        def __init__(self, stream):
            super().__init__(stream.buffer, encoding=stream.encoding, errors='replace')
            self._original = stream

        def write(self, s):
            # Filter out the noisy MCP cleanup errors
            if "error occurred during closing of asynchronous generator" in s:
                return len(s)
            if "Attempted to exit cancel scope in a different task" in s:
                return len(s)
            if "streamablehttp_client" in s and ("GeneratorExit" in s or "BaseExceptionGroup" in s):
                return len(s)
            return super().write(s)

    sys.stderr = FilteredStderr(sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CMPT - Client Meeting Prep Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cmpt/run.py
  python cmpt/run.py --company "Microsoft"
  python cmpt/run.py --company "Apple" --use-mcp

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

    # Suppress noisy MCP SDK cleanup errors
    _suppress_stderr_on_exit()

    asyncio.run(main(args.company, args.meeting_date, args.use_mcp))