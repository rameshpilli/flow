"""
Pitchbook Workflow Template using AgentOrchestrator

This template demonstrates how to implement the PowerPoint slide editing
and company profile generation workflows using the AgentOrchestrator framework.

Workflow 1: Edit Current Slide
- User selects agents (News, SEC Filing, Cap IQ, Insight, Practice, Earnings)
- System gathers context from multiple MCPs in parallel
- System pulls uploaded references from Cohere Compass (RAG)
- System generates text to replace/edit slide content

Workflow 2: Create Company Profile
- User selects company, layout, and provides instructions
- System gathers data from relevant sources
- System generates company profile

Memory Architecture:
- Session Memory (Redis): Current conversation, short-term, TTL-based
- Agent/Semantic Memory (Mem0): User preferences, patterns, long-term
- Reference Memory (RAG/Compass): Documents, knowledge base, citations
"""

import asyncio
from typing import Optional
from pydantic import BaseModel, Field

from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.context import ChainContext, ContextScope
from agentorchestrator.services import VectorStoreService, VectorStoreConfig
from agentorchestrator.services import Mem0Memory
from agentorchestrator.connectors.mcp import MCPConnector, MCPConfig
from agentorchestrator.squad import (
    Squad,
    SquadOptions,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)
from agentorchestrator.agents.base import BaseAgent, AgentResult


# ============================================================================
# STATE MODELS - Type-safe state management
# ============================================================================


class SlideEditRequest(BaseModel):
    """Input model for slide editing workflow"""
    slide_content: str = Field(..., description="Current slide content/text")
    company_name: str = Field(..., description="Target company (e.g., 'Apple')")
    special_instructions: str = Field(default="", description="User's special instructions")
    selected_agents: list[str] = Field(
        default_factory=list,
        description="Selected data agents: news, sec_filing, capiq, insight, practice, earnings"
    )
    document_ids: list[str] = Field(
        default_factory=list,
        description="IDs of uploaded reference documents"
    )
    session_id: str = Field(..., description="User session ID")
    user_id: str = Field(..., description="User ID")


class CompanyProfileRequest(BaseModel):
    """Input model for company profile creation"""
    company_name: str = Field(..., description="Company name")
    layout_type: str = Field(..., description="Layout type: small, medium, large")
    special_instructions: str = Field(default="", description="User's special instructions")
    selected_agents: list[str] = Field(default_factory=list)
    session_id: str = Field(...)
    user_id: str = Field(...)


class GlobalSettings(BaseModel):
    """
    Global Settings - persists across all sessions for a user.

    Phase 1 (Current): General info + Additional instructions -> Mem0
    Phase 2 (Later): + Reference material -> RAG
    """
    general_information: str = Field(default="", description="User's general info")
    additional_instructions: str = Field(default="", description="Persistent instructions")
    # Phase 2: reference_document_ids: list[str] = Field(default_factory=list)


class PitchbookState(BaseModel):
    """State model for pitchbook workflows"""
    company_identifier: Optional[str] = None  # Resolved Cap IQ identifier
    gathered_context: dict = Field(default_factory=dict)  # Context from all agents
    rag_context: list[str] = Field(default_factory=list)  # Context from uploaded docs
    mem0_context: str = ""  # Pre-fetched user preferences from Mem0
    generated_content: str = ""
    errors: list[str] = Field(default_factory=list)


# ============================================================================
# MCP CONNECTOR CONFIGURATION
# ============================================================================

MCP_CONFIGS = {
    "news": MCPConfig(
        name="news_mcp",
        base_url="http://news-mcp-server:8000",
    ),
    "sec_filing": MCPConfig(
        name="sec_filing_mcp",
        base_url="http://sec-mcp-server:8000",
    ),
    "capiq": MCPConfig(
        name="capiq_mcp",
        base_url="http://capiq-mcp-server:8000",
    ),
    "insight": MCPConfig(
        name="insight_mcp",
        base_url="http://insight-mcp-server:8000",
    ),
    "practice": MCPConfig(
        name="practice_mcp",
        base_url="http://practice-mcp-server:8000",
    ),
    "earnings": MCPConfig(
        name="earnings_mcp",
        base_url="http://earnings-mcp-server:8000",
    ),
}


# ============================================================================
# INITIALIZE ORCHESTRATOR
# ============================================================================

ao = AgentOrchestrator(name="pitchbook_orchestrator")


# ============================================================================
# SERVICES CONFIGURATION
# ============================================================================

# RAG Service (Cohere Compass) - for reference documents
rag_service = VectorStoreService(config=VectorStoreConfig(
    provider="cohere_compass",
    host="https://compass.corp.com",
    api_key="${COHERE_COMPASS_API_KEY}",
    namespace="pitchbook-references",
))

# Mem0 Service - for user preferences/instructions (semantic memory)
# mem0_service = Mem0Memory(client=mem0_client, default_user_id="user-123")


# ============================================================================
# GLOBAL SETTINGS SERVICE
# ============================================================================

class GlobalSettingsService:
    """
    Orchestrates global settings across Mem0 (preferences) and RAG (documents).

    Memory Architecture:
    - Mem0: General info + instructions (PRE-FETCHABLE at session start)
    - RAG: Reference documents (QUERY AT REQUEST TIME - need context)
    """

    def __init__(self, mem0: Mem0Memory, rag: VectorStoreService):
        self.mem0 = mem0
        self.rag = rag

    async def save_global_settings(self, user_id: str, settings: GlobalSettings) -> None:
        """Save global settings to Mem0 (long-term memory)"""
        # Store as searchable memories
        if settings.general_information:
            await self.mem0.add(
                f"User general information: {settings.general_information}",
                user_id=user_id,
                metadata={"type": "global_settings", "field": "general_info"}
            )
        if settings.additional_instructions:
            await self.mem0.add(
                f"User instructions: {settings.additional_instructions}",
                user_id=user_id,
                metadata={"type": "global_settings", "field": "instructions"}
            )

    async def initialize_session(self, user_id: str) -> dict:
        """
        Pre-fetch what CAN be pre-fetched (Mem0 preferences).
        Called at session start - before any specific request.

        Returns context to store in session memory (Redis/ChainContext).
        """
        # Pre-fetch from Mem0 - always relevant, doesn't need query context
        preferences = await self.mem0.get_context_for_query(
            query="global settings preferences instructions general information",
            user_id=user_id,
            max_tokens=2000,
        )

        return {
            "user_preferences": preferences,
            "user_id": user_id,
        }

    async def get_reference_context(
        self,
        query: str,
        user_id: str,
        document_ids: list[str] = None,
    ) -> list[str]:
        """
        Query RAG for reference documents - ONLY when we have query context.
        Called at request time when we know WHAT to search for.

        Cannot pre-fetch because we need: company name, slide context, action, etc.
        """
        filter_dict = {"user_id": user_id}
        if document_ids:
            filter_dict["document_id"] = {"$in": document_ids}

        results = await self.rag.query(
            query=query,
            top_k=10,
            filter=filter_dict,
        )
        return [r.text for r in results]


# ============================================================================
# DATA FETCHER AGENTS (Connect to MCPs)
# ============================================================================

class MCPDataAgent(BaseAgent):
    """Base agent for fetching data from MCP servers"""

    def __init__(self, name: str, mcp_config: MCPConfig, tool_name: str):
        super().__init__(name=name)
        self.connector = MCPConnector(mcp_config)
        self.tool_name = tool_name
        self._connected = False

    async def connect(self):
        if not self._connected:
            await self.connector.connect()
            self._connected = True

    async def disconnect(self):
        if self._connected:
            await self.connector.disconnect()
            self._connected = False

    async def fetch(self, company_id: str, query: str = "", **kwargs) -> AgentResult:
        """Fetch data from MCP server"""
        await self.connect()
        try:
            result = await self.connector.call_tool(
                tool_name=self.tool_name,
                arguments={"company_id": company_id, "query": query, **kwargs}
            )
            return AgentResult(
                data=result,
                source=self.name,
                query=query,
            )
        except Exception as e:
            return AgentResult(
                data=None,
                source=self.name,
                error=str(e),
            )


# Create MCP agents for each data source
NEWS_AGENT = MCPDataAgent("NewsAgent", MCP_CONFIGS["news"], "get_news")
SEC_AGENT = MCPDataAgent("SECFilingAgent", MCP_CONFIGS["sec_filing"], "get_filings")
CAPIQ_AGENT = MCPDataAgent("CapIQAgent", MCP_CONFIGS["capiq"], "get_company_data")
INSIGHT_AGENT = MCPDataAgent("InsightAgent", MCP_CONFIGS["insight"], "get_insights")
PRACTICE_AGENT = MCPDataAgent("PracticeAgent", MCP_CONFIGS["practice"], "get_practice_data")
EARNINGS_AGENT = MCPDataAgent("EarningsAgent", MCP_CONFIGS["earnings"], "get_earnings")

AGENT_MAP = {
    "news": NEWS_AGENT,
    "sec_filing": SEC_AGENT,
    "capiq": CAPIQ_AGENT,
    "insight": INSIGHT_AGENT,
    "practice": PRACTICE_AGENT,
    "earnings": EARNINGS_AGENT,
}


# ============================================================================
# WORKFLOW STEPS
# ============================================================================

@ao.step(
    name="load_session_context",
    produces=["mem0_context"],
    description="Load pre-fetched Mem0 context into workflow"
)
async def load_session_context(ctx: ChainContext):
    """
    Load user preferences from session context.
    These were pre-fetched at session start from Mem0.
    """
    # This would have been pre-fetched and stored in session/Redis
    mem0_context = ctx.get("user_preferences", "")

    async with ctx.edit_state() as state:
        state.mem0_context = mem0_context

    ctx.set("mem0_context", mem0_context)
    return {"mem0_context": mem0_context}


@ao.step(
    name="resolve_company_identifier",
    deps=["load_session_context"],
    produces=["company_identifier"],
    description="Resolve company name to Cap IQ identifier"
)
async def resolve_company_identifier(ctx: ChainContext):
    """Resolve company name to standardized identifier (Cap IQ)"""
    request: SlideEditRequest = ctx.get("request")

    # Call Cap IQ MCP to resolve identifier
    result = await CAPIQ_AGENT.fetch(
        company_id="",
        query=request.company_name,
        operation="resolve"
    )

    if result.error:
        async with ctx.edit_state() as state:
            state.errors.append(f"Failed to resolve company: {result.error}")
        return {"company_identifier": None}

    company_id = result.data.get("identifier", request.company_name)

    async with ctx.edit_state() as state:
        state.company_identifier = company_id

    ctx.set("company_identifier", company_id)
    return {"company_identifier": company_id}


@ao.step(
    name="gather_rag_context",
    deps=["resolve_company_identifier"],
    produces=["rag_context"],
    description="Fetch context from uploaded reference documents (RAG)"
)
async def gather_rag_context(ctx: ChainContext):
    """
    Query RAG (Cohere Compass) for uploaded document context.

    This happens at REQUEST TIME because we need:
    - Company name (to search for relevant docs)
    - Slide context (to find matching content)
    - Special instructions (to understand what to look for)

    Cannot pre-fetch - need query context!
    """
    request: SlideEditRequest = ctx.get("request")
    company_id = ctx.get("company_identifier")

    if not request.document_ids:
        return {"rag_context": []}

    # Build query combining company and instructions
    query = f"{request.company_name} {request.special_instructions} {request.slide_content[:500]}"

    # Query vector store - NOW we know what to search for
    results = await rag_service.query(
        query=query,
        top_k=10,
        filter={"document_id": {"$in": request.document_ids}}
    )

    rag_context = [r.text for r in results]

    async with ctx.edit_state() as state:
        state.rag_context = rag_context

    ctx.set("rag_context", rag_context)
    return {"rag_context": rag_context}


@ao.step(
    name="gather_mcp_context",
    deps=["resolve_company_identifier"],
    produces=["gathered_context"],
    description="Fetch data from selected MCP agents in PARALLEL"
)
async def gather_mcp_context(ctx: ChainContext):
    """
    Gather context from multiple MCPs in PARALLEL based on selected agents.
    This is the key parallelization step.
    """
    request: SlideEditRequest = ctx.get("request")
    company_id = ctx.get("company_identifier")

    if not company_id:
        return {"gathered_context": {}}

    # Build parallel fetch tasks for selected agents only
    tasks = {}
    for agent_key in request.selected_agents:
        if agent_key in AGENT_MAP:
            agent = AGENT_MAP[agent_key]
            tasks[agent_key] = agent.fetch(
                company_id=company_id,
                query=request.special_instructions
            )

    # Execute all fetches in PARALLEL
    if tasks:
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        gathered = {}
        for key, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                async with ctx.edit_state() as state:
                    state.errors.append(f"{key}: {str(result)}")
                gathered[key] = None
            elif result.error:
                async with ctx.edit_state() as state:
                    state.errors.append(f"{key}: {result.error}")
                gathered[key] = None
            else:
                gathered[key] = result.data
    else:
        gathered = {}

    async with ctx.edit_state() as state:
        state.gathered_context = gathered

    ctx.set("gathered_context", gathered)
    return {"gathered_context": gathered}


@ao.step(
    name="generate_slide_content",
    deps=["gather_mcp_context", "gather_rag_context"],
    produces=["generated_content"],
    description="Generate edited slide content using LLM"
)
async def generate_slide_content(ctx: ChainContext):
    """Generate the edited slide content using all gathered context"""
    request: SlideEditRequest = ctx.get("request")
    gathered_context = ctx.get("gathered_context")
    rag_context = ctx.get("rag_context")
    mem0_context = ctx.get("mem0_context", "")

    # Build prompt with all context
    context_text = "\n\n".join([
        f"## {source.upper()} DATA:\n{data}"
        for source, data in gathered_context.items()
        if data is not None
    ])

    rag_text = "\n".join(rag_context) if rag_context else ""

    prompt = f"""You are editing a PowerPoint slide for a pitchbook.

USER PREFERENCES (from global settings):
{mem0_context}

CURRENT SLIDE CONTENT:
{request.slide_content}

TARGET COMPANY: {request.company_name}

SPECIAL INSTRUCTIONS:
{request.special_instructions}

GATHERED DATA FROM AGENTS:
{context_text}

REFERENCE DOCUMENTS:
{rag_text}

Please generate the updated slide content that:
1. Replaces company-specific information with data for {request.company_name}
2. Maintains the original slide structure and formatting
3. Incorporates relevant data from the gathered sources
4. Follows the special instructions provided
5. Respects user preferences from global settings

Return ONLY the updated slide content text.
"""

    # Use LLM to generate content
    llm_client = ctx.get_resource("llm")
    response = await llm_client.generate(prompt)

    generated_content = response.content

    async with ctx.edit_state() as state:
        state.generated_content = generated_content

    ctx.set("generated_content", generated_content)
    return {"generated_content": generated_content}


# ============================================================================
# CHAIN DEFINITIONS
# ============================================================================

@ao.chain(
    name="slide_edit_chain",
    input_model=SlideEditRequest,
    state_model=PitchbookState,
    description="Complete workflow for editing a PowerPoint slide"
)
class SlideEditChain:
    """
    Chain for editing PowerPoint slides.

    Execution order:
    1. load_session_context (load pre-fetched Mem0 preferences)
    2. resolve_company_identifier (must run first for company ID)
    3. gather_rag_context + gather_mcp_context (PARALLEL - both depend on step 2)
    4. generate_slide_content (depends on steps 3)

    Memory Flow:
    - Mem0 (pre-fetched at session start) -> Already in session context
    - RAG (queried here) -> Needs company/slide context to search
    - MCPs (queried here) -> Needs company ID
    """
    steps = [
        "load_session_context",
        "resolve_company_identifier",
        "gather_rag_context",
        "gather_mcp_context",
        "generate_slide_content"
    ]

    # These two steps run in PARALLEL after resolve_company_identifier
    parallel_groups = [["gather_rag_context", "gather_mcp_context"]]


@ao.chain(
    name="company_profile_chain",
    input_model=CompanyProfileRequest,
    state_model=PitchbookState,
    description="Complete workflow for creating a company profile"
)
class CompanyProfileChain:
    """Chain for creating company profiles"""
    steps = [
        "load_session_context",
        "resolve_company_identifier",
        "gather_rag_context",
        "gather_mcp_context",
        "generate_company_profile"
    ]
    parallel_groups = [["gather_rag_context", "gather_mcp_context"]]


# ============================================================================
# ENTRY POINTS
# ============================================================================

async def initialize_user_session(user_id: str, mem0_service: Mem0Memory) -> dict:
    """
    Called at SESSION START - before any specific request.
    Pre-fetches what CAN be pre-fetched (Mem0 preferences).

    Store the result in Redis/session for use in all subsequent requests.
    """
    global_settings_service = GlobalSettingsService(mem0=mem0_service, rag=rag_service)
    session_context = await global_settings_service.initialize_session(user_id)

    # Store in Redis for the session
    # redis.set(f"session:{session_id}:context", json.dumps(session_context), ex=3600)

    return session_context


async def edit_slide(request: SlideEditRequest, session_context: dict) -> dict:
    """
    Main entry point for slide editing workflow.

    Args:
        request: The slide edit request
        session_context: Pre-fetched context from initialize_user_session()
    """
    # Merge session context (pre-fetched Mem0) with request
    initial_data = {
        "request": request.model_dump(),
        "user_preferences": session_context.get("user_preferences", ""),
    }

    result = await ao.launch(
        "slide_edit_chain",
        initial_data,
        session_id=request.session_id,
        user_id=request.user_id,
    )

    return {
        "generated_content": result.context.get("generated_content"),
        "errors": result.context.state.errors if result.context.state else [],
        "execution_time_ms": result.execution_time_ms,
    }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

async def main():
    """Example usage of the pitchbook workflow"""

    # =========================================
    # STEP 1: Session starts - Pre-fetch Mem0
    # =========================================
    user_id = "user_456"
    # session_context = await initialize_user_session(user_id, mem0_service)
    # In reality, store this in Redis with TTL
    session_context = {"user_preferences": "User prefers formal tone. Focus on last 5 years."}

    # =========================================
    # STEP 2: User makes request - NOW query RAG + MCPs
    # =========================================
    request = SlideEditRequest(
        slide_content="""
        Microsoft Overview
        - Founded: 1975
        - CEO: Satya Nadella
        - Market Cap: $2.8T
        - Revenue: $211B (FY2023)
        """,
        company_name="Apple",
        special_instructions="Focus on recent product launches and AI initiatives",
        selected_agents=["news", "sec_filing", "capiq", "earnings"],
        document_ids=["doc_001", "doc_002"],
        session_id="session_123",
        user_id=user_id,
    )

    result = await edit_slide(request, session_context)
    print("Generated Content:", result["generated_content"])


if __name__ == "__main__":
    asyncio.run(main())
