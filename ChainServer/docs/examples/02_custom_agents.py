"""
================================================================================
02_CUSTOM_AGENTS.PY - Creating Custom Data Agents
================================================================================

PURPOSE:
    Learn how to create your own custom agents that fetch data from
    external sources (APIs, databases, MCP servers, etc.)

WHAT YOU'LL LEARN:
    1. Creating a custom agent class with @ao.agent decorator
    2. Implementing the BaseAgent interface (fetch method)
    3. Connecting to MCP servers
    4. Using agents in chain steps
    5. Agent capabilities and versioning

PREREQUISITES:
    - Complete 01_quickstart.py first

NEXT STEPS:
    After this, go to: 03_chain_composition.py

RUN THIS EXAMPLE:
    python examples/02_custom_agents.py
"""

import asyncio
from typing import Any

from agentorchestrator import ChainContext, AgentOrchestrator
from agentorchestrator.agents import AgentResult, BaseAgent
from agentorchestrator.connectors.base import ConnectorConfig
from agentorchestrator.connectors.mcp import MCPAgent, create_mcp_agent

# ============================================================
# SCENARIO 1: Simple Custom Agent
# ============================================================

ao = AgentOrchestrator(name="custom_demo")


@ao.agent(
    name="my_custom_data_source",
    version="1.0",
    description="My company's internal data API",
    capabilities=["search", "analytics"],
)
class MyCustomDataAgent(BaseAgent):
    """
    Example of a custom agent that wraps your own data source.

    Users can create agents for any data source by:
    1. Subclassing BaseAgent
    2. Implementing the fetch() method
    3. Decorating with @ao.agent()
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.api_url = config.get("api_url", "https://api.mycompany.com") if config else ""

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        import time

        start = time.perf_counter()

        # Your custom data fetching logic here
        data = {
            "query": query,
            "results": [
                {"id": 1, "name": "Result 1"},
                {"id": 2, "name": "Result 2"},
            ],
            "source": "internal_api",
        }

        duration = (time.perf_counter() - start) * 1000
        return AgentResult(
            data=data,
            source="my_custom_data_source",
            query=query,
            duration_ms=duration,
        )


# ============================================================
# SCENARIO 2: MCP Server Integration
# ============================================================


@ao.agent(
    name="my_mcp_server",
    version="1.0",
    description="Integration with external MCP server",
)
class MyMCPServerAgent(MCPAgent):
    """
    Example of integrating an external MCP server as a AgentOrchestrator agent.

    This allows users to bring their own MCP servers into AgentOrchestrator chains.
    """

    connector_config = ConnectorConfig(
        name="my_mcp",
        base_url="http://localhost:8000",  # Your MCP server URL
        api_key="your-api-key",
    )

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        import time

        start = time.perf_counter()

        try:
            # Call the MCP server's tool
            if self.connector:
                result = await self.connector.call_tool("search", {"query": query})
            else:
                result = {"_mock": True, "query": query}

            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=result,
                source="my_mcp_server",
                query=query,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source="my_mcp_server",
                query=query,
                duration_ms=duration,
                error=str(e),
            )


# ============================================================
# SCENARIO 3: Dynamic Agent Creation (Factory Pattern)
# ============================================================

# Create agents dynamically using the factory function
CRMAgent = create_mcp_agent(
    name="crm_agent",
    base_url="http://crm-server:8000",
    tool_name="get_customer",
    api_key="crm-api-key",
)


# ============================================================
# SCENARIO 4: Chain Custom Agents with Built-in Steps
# ============================================================


@ao.step(
    name="fetch_custom_data",
    produces=["custom_data"],
)
async def fetch_custom_data(ctx: ChainContext) -> dict[str, Any]:
    """Step that uses our custom agent"""
    query = ctx.get("query", "")

    agent = ao.get_agent("my_custom_data_source")
    result = await agent.fetch(query)

    ctx.set("custom_data", result.data)
    return {"custom_data": result.data}


@ao.step(
    name="enrich_with_mcp",
    deps=["fetch_custom_data"],
    produces=["enriched_data"],
)
async def enrich_with_mcp(ctx: ChainContext) -> dict[str, Any]:
    """Step that enriches data using MCP server"""
    custom_data = ctx.get("custom_data", {})

    # Use MCP agent for enrichment
    agent = ao.get_agent("my_mcp_server")
    if agent:
        await agent.initialize()
        result = await agent.fetch(str(custom_data))
        await agent.cleanup()
        enriched = {**custom_data, "enrichment": result.data}
    else:
        enriched = custom_data

    ctx.set("enriched_data", enriched)
    return {"enriched_data": enriched}


@ao.step(
    name="process_results",
    deps=["enrich_with_mcp"],
    produces=["final_output"],
)
async def process_results(ctx: ChainContext) -> dict[str, Any]:
    """Final processing step"""
    enriched = ctx.get("enriched_data", {})

    final_output = {
        "status": "processed",
        "data": enriched,
        "timestamp": "2025-01-15T10:00:00Z",
    }

    ctx.set("final_output", final_output)
    return {"final_output": final_output}


@ao.chain(
    name="custom_data_pipeline",
    version="1.0",
)
class CustomDataPipeline:
    """Chain that combines custom agents with processing steps"""

    steps = [
        "fetch_custom_data",
        "enrich_with_mcp",
        "process_results",
    ]


# ============================================================
# RUN DEMO
# ============================================================


async def main():
    print("\n" + "=" * 60)
    print("AgentOrchestrator: Custom Agent Demo")
    print("=" * 60 + "\n")

    # Show what's registered
    print("Registered Agents:", ao.list_agents())
    print("Registered Steps:", ao.list_steps())
    print("Registered Chains:", ao.list_chains())
    print()

    # Run the custom pipeline
    print("Running custom_data_pipeline...")
    print("-" * 40)

    result = await ao.run(
        "custom_data_pipeline",
        initial_data={"query": "customer_123"},
    )

    print(f"\nSuccess: {result['success']}")
    print(f"Duration: {result['duration_ms']:.2f}ms")

    for step in result["results"]:
        status = "✓" if step["success"] else "✗"
        print(f"  {status} {step['step']}: {step['duration_ms']:.2f}ms")


if __name__ == "__main__":
    asyncio.run(main())
