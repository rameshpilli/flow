"""
FlowForge Example: Client Meeting Prep Chain

This example demonstrates how to build the Client Meeting Prep Chain Server
using FlowForge's decorator-based approach.

This is the USER PERSPECTIVE - how someone would use FlowForge to build their chain.
"""

import asyncio
import logging
from typing import Any

# Import FlowForge
from flowforge import ChainContext, FlowForge
from flowforge.agents import AgentResult, BaseAgent
from flowforge.middleware import (
    CacheMiddleware,
    LoggerMiddleware,
    TokenManagerMiddleware,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 1. INITIALIZE FLOWFORGE
# ============================================================

forge = FlowForge(
    name="meeting_prep",
    version="1.0.0",
    max_parallel=5,
    default_timeout_ms=60000,
)

# Add middleware
forge.use_middleware(LoggerMiddleware(level=logging.INFO))
forge.use_middleware(CacheMiddleware(ttl_seconds=300))
forge.use_middleware(TokenManagerMiddleware(max_total_tokens=100000))


# ============================================================
# 2. DEFINE DATA AGENTS
# ============================================================


@forge.agent(
    name="sec_filing",
    version="1.0",
    capabilities=["10K", "10Q", "8K"],
)
class SECFilingAgent(BaseAgent):
    """Agent for fetching SEC filings from RavenPack"""

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        import time

        start = time.perf_counter()

        # Simulate fetching SEC filings
        await asyncio.sleep(0.1)  # Simulate API call

        data = {
            "company": query,
            "filings": [
                {"type": "10K", "date": "2024-02-15", "revenue": "394.33B"},
                {"type": "10Q", "date": "2024-05-01", "revenue": "94.8B"},
            ],
            "quarters": kwargs.get("quarters", 8),
        }

        duration = (time.perf_counter() - start) * 1000
        return AgentResult(
            data=data,
            source="sec_filing",
            query=query,
            duration_ms=duration,
        )


@forge.agent(
    name="news",
    version="1.0",
    capabilities=["search", "sentiment"],
)
class NewsAgent(BaseAgent):
    """Agent for fetching news from RavenPack"""

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        import time

        start = time.perf_counter()

        # Simulate fetching news
        await asyncio.sleep(0.1)

        data = {
            "company": query,
            "articles": [
                {"title": "Q4 Earnings Beat", "sentiment": 0.8},
                {"title": "New Product Launch", "sentiment": 0.7},
            ],
            "days": kwargs.get("days", 30),
        }

        duration = (time.perf_counter() - start) * 1000
        return AgentResult(
            data=data,
            source="news",
            query=query,
            duration_ms=duration,
        )


@forge.agent(
    name="earnings",
    version="1.0",
    capabilities=["earnings", "estimates"],
)
class EarningsAgent(BaseAgent):
    """Agent for fetching earnings from FactSet"""

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        import time

        start = time.perf_counter()

        # Simulate fetching earnings
        await asyncio.sleep(0.1)

        data = {
            "company": query,
            "latest_eps": 2.18,
            "estimate": 2.10,
            "beat": True,
        }

        duration = (time.perf_counter() - start) * 1000
        return AgentResult(
            data=data,
            source="earnings",
            query=query,
            duration_ms=duration,
        )


# ============================================================
# 3. DEFINE CHAIN STEPS
# ============================================================


@forge.step(
    name="customer_firm_extractor",
    produces=["company_info", "company_name"],
)
async def extract_customer_firm(ctx: ChainContext) -> dict[str, Any]:
    """
    Extract customer firm information from the request.
    This is the first step in Context Builder.
    """
    company_name = ctx.get("corporate_company_name", "Unknown")

    # Simulate LLM extraction
    company_info = {
        "name": company_name,
        "ticker": company_name[:4].upper(),
        "industry": "Technology",
        "market_cap": "3T",
    }

    ctx.set("company_info", company_info)
    ctx.set("company_name", company_name)

    return {"company_info": company_info}


@forge.step(
    name="temporal_context_extractor",
    produces=["temporal_context"],
)
async def extract_temporal_context(ctx: ChainContext) -> dict[str, Any]:
    """
    Extract temporal context from the meeting date.
    Part of Context Builder.
    """
    meeting_date = ctx.get("meeting_datetime", "2025-01-15")

    temporal_context = {
        "meeting_date": meeting_date,
        "quarter": "Q1 2025",
        "fiscal_year": "FY2025",
        "lookback_period": "12 months",
    }

    ctx.set("temporal_context", temporal_context)
    return {"temporal_context": temporal_context}


@forge.step(
    name="temporal_source_prioritizer",
    dependencies=["customer_firm_extractor", "temporal_context_extractor"],
    produces=["prioritized_sources"],
)
async def prioritize_sources(ctx: ChainContext) -> dict[str, Any]:
    """
    Prioritize data sources based on temporal context.
    Part of Content Prioritization Engine.
    """
    temporal = ctx.get("temporal_context", {})

    # Determine which sources to prioritize
    prioritized = {
        "primary": ["sec_filing", "earnings"],
        "secondary": ["news"],
        "lookback": temporal.get("lookback_period", "12 months"),
    }

    ctx.set("prioritized_sources", prioritized)
    return {"prioritized_sources": prioritized}


@forge.step(
    name="subquery_engine",
    dependencies=["temporal_source_prioritizer"],
    produces=["subqueries"],
)
async def generate_subqueries(ctx: ChainContext) -> dict[str, Any]:
    """
    Generate subqueries for each data agent.
    Part of Content Prioritization Engine.
    """
    company_name = ctx.get("company_name", "")
    sources = ctx.get("prioritized_sources", {})

    subqueries = {
        "sec_filing": {
            "query": company_name,
            "params": {"quarters": 8, "types": ["10K", "10Q"]},
        },
        "news": {
            "query": company_name,
            "params": {"days": 30, "sentiment": True},
        },
        "earnings": {
            "query": company_name,
            "params": {"include_estimates": True},
        },
    }

    ctx.set("subqueries", subqueries)
    return {"subqueries": subqueries}


@forge.step(
    name="agent_executor",
    dependencies=["subquery_engine"],
    produces=["agent_results"],
)
async def execute_agents(ctx: ChainContext) -> dict[str, Any]:
    """
    Execute data agents in parallel.
    Part of Response Builder & Generator.
    """
    subqueries = ctx.get("subqueries", {})
    company_name = ctx.get("company_name", "")

    # Get agent instances
    sec_agent = forge.get_agent("sec_filing")
    news_agent = forge.get_agent("news")
    earnings_agent = forge.get_agent("earnings")

    # Execute in parallel
    results = await asyncio.gather(
        sec_agent.fetch(company_name, **subqueries.get("sec_filing", {}).get("params", {})),
        news_agent.fetch(company_name, **subqueries.get("news", {}).get("params", {})),
        earnings_agent.fetch(company_name, **subqueries.get("earnings", {}).get("params", {})),
    )

    agent_results = {
        "sec_filing": results[0].data,
        "news": results[1].data,
        "earnings": results[2].data,
    }

    ctx.set("agent_results", agent_results)
    return {"agent_results": agent_results}


@forge.step(
    name="response_builder",
    dependencies=["agent_executor"],
    produces=["final_response"],
)
async def build_response(ctx: ChainContext) -> dict[str, Any]:
    """
    Build the final CMPT response.
    Part of Response Builder & Generator.
    """
    company_info = ctx.get("company_info", {})
    temporal = ctx.get("temporal_context", {})
    agent_results = ctx.get("agent_results", {})

    # Simulate LLM response generation
    final_response = {
        "company": company_info,
        "meeting_context": temporal,
        "data_summary": {
            "filings_count": len(agent_results.get("sec_filing", {}).get("filings", [])),
            "news_count": len(agent_results.get("news", {}).get("articles", [])),
            "earnings_beat": agent_results.get("earnings", {}).get("beat", False),
        },
        "prepared_content": f"Meeting prep for {company_info.get('name', 'Unknown')}...",
    }

    ctx.set("final_response", final_response)
    return {"final_response": final_response}


# ============================================================
# 4. DEFINE THE CHAIN
# ============================================================


@forge.chain(
    name="meeting_prep",
    version="1.0",
    description="Client Meeting Prep Chain for Aiden Banker",
)
class MeetingPrepChain:
    """
    Complete chain for preparing client meeting content.

    Flow:
    1. Context Builder: Extract firm info and temporal context
    2. Content Prioritization: Prioritize sources and generate subqueries
    3. Response Builder: Execute agents and build response
    """

    steps = [
        "customer_firm_extractor",
        "temporal_context_extractor",
        "temporal_source_prioritizer",
        "subquery_engine",
        "agent_executor",
        "response_builder",
    ]


# ============================================================
# 5. RUN THE CHAIN
# ============================================================


async def main():
    """Example of running the meeting prep chain"""

    print("\n" + "=" * 60)
    print("FlowForge: Client Meeting Prep Chain Demo")
    print("=" * 60 + "\n")

    # Show registered components
    print("Registered Components:")
    print(f"  Agents: {forge.list_agents()}")
    print(f"  Steps: {forge.list_steps()}")
    print(f"  Chains: {forge.list_chains()}")
    print()

    # Visualize the chain
    print("Chain DAG:")
    print(forge.visualize_chain("meeting_prep"))
    print()

    # Execute the chain
    print("Executing chain...")
    print("-" * 40)

    result = await forge.run(
        "meeting_prep",
        initial_data={
            "corporate_company_name": "Apple Inc.",
            "meeting_datetime": "2025-01-15",
            "corporate_client_email": "client@example.com",
        },
    )

    # Display results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Request ID: {result['request_id']}")
    print(f"Success: {result['success']}")
    print(f"Duration: {result['duration_ms']:.2f}ms")
    print()

    print("Step Results:")
    for step_result in result["results"]:
        status = "✓" if step_result["success"] else "✗"
        print(f"  {status} {step_result['step']}: {step_result['duration_ms']:.2f}ms")

    print()
    print("Final Response:")
    final = result["context"]["data"].get("final_response", {})
    print(f"  Company: {final.get('company', {}).get('name', 'N/A')}")
    print(f"  Filings: {final.get('data_summary', {}).get('filings_count', 0)}")
    print(f"  News: {final.get('data_summary', {}).get('news_count', 0)}")
    print(f"  Earnings Beat: {final.get('data_summary', {}).get('earnings_beat', False)}")


if __name__ == "__main__":
    asyncio.run(main())
