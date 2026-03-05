"""AgentOrchestrator Server — expose agents and chains as MCP servers.

Quick start
───────────
    from agentorchestrator.server import MCPServer

    mcp = MCPServer(secret="your-shared-secret")

    # Bind an AgentOrchestrator chain (primary path — streaming included)
    mcp.bind_chain(
        ao=ao,
        chain_name="deep_research",
        tool_name="deep_research",
        description="Multi-source financial research agent",
        input_schema={"query": {"type": "string"}},
        context_builder=lambda args: {"query": args["query"]},
    )

    # Register a plain async function (escape hatch for simple tools)
    @mcp.tool(name="get_date", description="Get today's date", input_schema={})
    async def get_date() -> str:
        from datetime import datetime
        return datetime.now().isoformat()

    # Mount on any FastAPI app
    app.include_router(mcp.router, prefix="/mcp")
"""

from agentorchestrator.server.mcp import MCPServer, MCPToolDef

__all__ = ["MCPServer", "MCPToolDef"]
