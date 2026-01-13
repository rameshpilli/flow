"""
CMPT Chain - Supervisor-Style Implementation with Agent Squad Integration

This implementation demonstrates the supervisor pattern for agent orchestration,
where a lead agent dynamically decides which specialized agents to invoke based
on the query context.

Architecture:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                        SUPERVISOR PATTERN                                │
    │                                                                          │
    │  User Query ──► Lead Agent ──► Decides: "I need SEC + CapIQ data"       │
    │                     │                                                    │
    │                     ├──► SEC Agent ──────┐                               │
    │                     └──► CapIQ Agent ────┼──► Lead Synthesizes ──► Response
    │                                          │                               │
    │  (News Agent not called - not relevant to this query)                   │
    └─────────────────────────────────────────────────────────────────────────┘

Key Differences from chain.py:
    - chain.py: DAG-based, all agents execute based on static dependencies
    - chain_squad.py: Supervisor-based, lead agent dynamically routes queries

Execution Strategies:
    - CLASSIFIER: Route to single best agent (intelligent routing)
    - BROADCAST: Send to all agents in parallel (comprehensive)
    - SUPERVISOR: Lead agent decides which agents to invoke (dynamic)

Usage:
    from cmpt.chain_squad import execute_squad_chain, SquadChainConfig

    # Supervisor mode (recommended)
    result = await execute_squad_chain(
        request=request,
        agents={"sec": sec_agent, "capiq": capiq_agent},
        strategy="supervisor",
        llm=my_llm,
    )

    # Broadcast mode (all agents)
    result = await execute_squad_chain(
        request=request,
        agents=agents_dict,
        strategy="broadcast",
    )

    # Classifier mode (single best agent)
    result = await execute_squad_chain(
        request=request,
        agents=agents_dict,
        strategy="classifier",
    )
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agentorchestrator import AgentOrchestrator, ChainContext, ContextScope
from agentorchestrator.agents import (
    AgentResult,
    AgentSquadBridge,
    AgentSquadConfig,
    BaseAgent,
    ResponseStrategy,
    RoutingStrategy,
    SupervisorAgent,
    SupervisorConfig,
)

from cmpt.services.models import (
    ChainRequest,
    ChainRequestOverrides,
    CompanyInfo,
    PersonaInfo,
    TemporalContext,
)

logger = logging.getLogger(__name__)

# Create a separate orchestrator for supervisor-style execution
squad_ao = AgentOrchestrator(name="cmpt_squad")


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class SquadChainConfig:
    """Configuration for supervisor-style chain execution."""

    # Execution strategy
    strategy: str = "supervisor"  # supervisor, broadcast, classifier

    # Supervisor settings
    lead_model: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    lead_temperature: float = 0.3

    # Response handling
    response_strategy: str = "summarize"  # summarize, extract, truncate, raw
    max_tokens_per_agent: int = 2000
    preserve_citations: bool = True

    # Agent descriptions for routing
    agent_descriptions: dict[str, str] = field(default_factory=lambda: {
        "sec_agent": "SEC filing expert - retrieves and analyzes 10-K, 10-Q, 8-K filings",
        "capiq_agent": "S&P Capital IQ analyst - financial metrics, ratios, company data",
        "news_agent": "News and media analyst - recent articles, press releases, market sentiment",
        "earnings_agent": "Earnings call analyst - transcripts, guidance, analyst Q&A",
        "insider_agent": "Insider trading analyst - Form 4 filings, executive transactions",
    })

    # Timeouts
    timeout_seconds: float = 120.0
    continue_on_failure: bool = True


# =============================================================================
# STEP 1: CONTEXT EXTRACTION (Same as chain.py - reuse)
# =============================================================================


@squad_ao.step(name="extract_firm_temporal")
async def extract_firm_temporal(ctx: ChainContext) -> dict[str, Any]:
    """Extract company info and temporal context from Foundation Service APIs."""
    from cmpt.services._01_context_builder import ContextBuilderService

    request: ChainRequest = ctx.get("request")
    overrides: ChainRequestOverrides = ctx.get("overrides") or ChainRequestOverrides()

    if not request.corporate_company_name or overrides.skip_earnings_calendar_api:
        return {"company_info": None, "temporal_context": None}

    service = ContextBuilderService()
    result = await service._extract_firm_and_temporal(
        company_name=request.corporate_company_name,
        ticker=overrides.ticker,
        meeting_datetime=request.meeting_datetime,
        earnings_override=overrides.next_earnings_date,
    )

    (company_info, temporal_context), error, duration = result

    if error:
        logger.warning(f"Firm/temporal extraction error: {error}")
        return {"company_info": None, "temporal_context": None, "error": error}

    return {
        "company_info": company_info.model_dump() if company_info else None,
        "temporal_context": temporal_context.model_dump() if temporal_context else None,
    }


@squad_ao.step(name="extract_rbc_persona")
async def extract_rbc_persona(ctx: ChainContext) -> dict[str, Any]:
    """Extract RBC employee persona from LDAP."""
    from cmpt.services._01_context_builder import ContextBuilderService

    request: ChainRequest = ctx.get("request")

    if not request.rbc_employee_email:
        return {"rbc_persona": None}

    service = ContextBuilderService()
    result = await service._extract_rbc_persona(request.rbc_employee_email)

    persona, error, duration = result

    if error:
        logger.warning(f"RBC persona extraction error: {error}")
        return {"rbc_persona": None, "error": error}

    return {"rbc_persona": persona.model_dump() if persona else None}


@squad_ao.step(name="extract_client_persona")
async def extract_client_persona(ctx: ChainContext) -> dict[str, Any]:
    """Extract client persona from ZoomInfo."""
    from cmpt.services._01_context_builder import ContextBuilderService

    request: ChainRequest = ctx.get("request")

    if not (request.corporate_client_email or request.corporate_client_names):
        return {"client_personas": []}

    service = ContextBuilderService()
    result = await service._extract_client_persona(
        email=request.corporate_client_email,
        names=request.corporate_client_names,
        company_name=request.corporate_company_name,
    )

    personas, error, duration = result

    if error:
        logger.warning(f"Client persona extraction error: {error}")
        return {"client_personas": [], "error": error}

    return {"client_personas": [p.model_dump() for p in personas]}


@squad_ao.step(
    name="build_context",
    deps=["extract_firm_temporal", "extract_rbc_persona", "extract_client_persona"]
)
async def build_context(ctx: ChainContext) -> dict[str, Any]:
    """Aggregate extracted context and apply fallbacks/overrides."""
    from cmpt.services._01_context_builder import ContextBuilderService

    request: ChainRequest = ctx.get("request")
    overrides: ChainRequestOverrides = ctx.get("overrides") or ChainRequestOverrides()

    # Get results from parallel extractors
    firm_temporal = ctx.get_result("extract_firm_temporal")
    rbc_result = ctx.get_result("extract_rbc_persona")
    client_result = ctx.get_result("extract_client_persona")

    # Extract data (handle failures gracefully)
    company_info_dict = None
    temporal_context_dict = None
    rbc_persona_dict = None
    client_personas_list = []

    if firm_temporal and firm_temporal.success:
        company_info_dict = firm_temporal.output.get("company_info")
        temporal_context_dict = firm_temporal.output.get("temporal_context")

    if rbc_result and rbc_result.success:
        rbc_persona_dict = rbc_result.output.get("rbc_persona")

    if client_result and client_result.success:
        client_personas_list = client_result.output.get("client_personas", [])

    # Convert back to models
    company_info = CompanyInfo(**company_info_dict) if company_info_dict else None
    temporal_context = TemporalContext(**temporal_context_dict) if temporal_context_dict else None
    rbc_persona = PersonaInfo(**rbc_persona_dict) if rbc_persona_dict else None
    client_personas = [PersonaInfo(**p) for p in client_personas_list]

    # Apply fallbacks
    service = ContextBuilderService()

    if not company_info and request.corporate_company_name:
        company_info = CompanyInfo(
            name=request.corporate_company_name,
            ticker=overrides.ticker,
            cik=overrides.company_cik,
            industry=overrides.industry,
            sector=overrides.sector,
        )

    if not temporal_context:
        temporal_context = service._create_default_temporal(request.meeting_datetime, overrides)

    # Apply overrides
    if company_info:
        company_info = service._apply_company_overrides(company_info, overrides)
    if temporal_context:
        temporal_context = service._apply_temporal_overrides(temporal_context, overrides)

    # Store in context for next steps
    ctx.set("company_info", company_info, scope=ContextScope.CHAIN)
    ctx.set("temporal_context", temporal_context, scope=ContextScope.CHAIN)
    ctx.set("rbc_persona", rbc_persona, scope=ContextScope.CHAIN)
    ctx.set("client_personas", client_personas, scope=ContextScope.CHAIN)

    return {
        "company_name": company_info.name if company_info else None,
        "ticker": company_info.ticker if company_info else None,
        "company_info": company_info.model_dump() if company_info else None,
        "temporal_context": temporal_context.model_dump() if temporal_context else None,
        "rbc_persona": rbc_persona.model_dump() if rbc_persona else None,
        "client_personas": [p.model_dump() for p in client_personas],
    }


# =============================================================================
# STEP 2: INTELLIGENT CONTENT PRIORITIZATION
# =============================================================================


@squad_ao.step(name="prioritize_content", deps=["build_context"])
async def prioritize_content(ctx: ChainContext) -> dict[str, Any]:
    """
    Prioritize data sources and generate research query.

    In supervisor mode, we generate a unified research query that the
    lead agent will use to determine which specialists to invoke.
    """
    from cmpt.services._02_content_prioritization import ContentPrioritizationService
    from cmpt.services.models import ContextBuilderOutput

    # Get context from previous step
    company_info = ctx.get("company_info")
    temporal_context = ctx.get("temporal_context")
    rbc_persona = ctx.get("rbc_persona")
    client_personas = ctx.get("client_personas", [])

    # Build context output for the service
    context_output = ContextBuilderOutput(
        company_info=company_info,
        temporal_context=temporal_context,
        company_name=company_info.name if company_info else None,
        ticker=company_info.ticker if company_info else None,
        errors={},
        timing_ms={},
    )

    # Use existing service
    service = ContentPrioritizationService()
    result = await service.execute(context_output)

    # Build a unified research query for the supervisor
    research_query = _build_research_query(
        company_info=company_info,
        temporal_context=temporal_context,
        rbc_persona=rbc_persona,
        client_personas=client_personas,
        subqueries=result.subqueries,
    )

    # Store for next step
    ctx.set("prioritized_sources", result.prioritized_sources, scope=ContextScope.CHAIN)
    ctx.set("subqueries", result.subqueries, scope=ContextScope.CHAIN)
    ctx.set("research_query", research_query, scope=ContextScope.CHAIN)

    return {
        "prioritized_sources": [s.model_dump() for s in result.prioritized_sources],
        "subqueries": [sq.model_dump() for sq in result.subqueries],
        "priority_distribution": result.priority_distribution,
        "reasoning": result.prioritization_reasoning,
        "research_query": research_query,
    }


def _build_research_query(
    company_info: CompanyInfo | None,
    temporal_context: TemporalContext | None,
    rbc_persona: PersonaInfo | None,
    client_personas: list[PersonaInfo],
    subqueries: list[Any],
) -> str:
    """Build a comprehensive research query for the supervisor."""
    parts = []

    # Company context
    if company_info:
        company_desc = f"Company: {company_info.name}"
        if company_info.ticker:
            company_desc += f" ({company_info.ticker})"
        if company_info.industry:
            company_desc += f", Industry: {company_info.industry}"
        parts.append(company_desc)

    # Temporal context
    if temporal_context:
        if temporal_context.next_earnings_date:
            parts.append(f"Upcoming earnings: {temporal_context.next_earnings_date}")
        if temporal_context.fiscal_quarter:
            parts.append(f"Fiscal period: {temporal_context.fiscal_quarter}")

    # Meeting context
    if rbc_persona:
        parts.append(f"Meeting with: {rbc_persona.name} ({rbc_persona.title})")

    # Client context
    if client_personas:
        client_names = ", ".join([p.name for p in client_personas[:3]])
        parts.append(f"Client attendees: {client_names}")

    # Research objectives from subqueries
    if subqueries:
        objectives = [sq.query if hasattr(sq, "query") else str(sq) for sq in subqueries[:5]]
        parts.append(f"Research objectives: {'; '.join(objectives)}")

    return "\n".join(parts)


# =============================================================================
# STEP 3: SUPERVISOR-BASED AGENT EXECUTION
# =============================================================================


@squad_ao.step(name="execute_squad", deps=["prioritize_content"])
async def execute_squad(ctx: ChainContext) -> dict[str, Any]:
    """
    Execute agents using supervisor pattern.

    The supervisor (lead agent) analyzes the research query and decides
    which specialist agents to invoke. This is dynamic - not all agents
    are called for every query.
    """
    import time
    start = time.perf_counter()

    # Get configuration
    config: SquadChainConfig = ctx.get("squad_config") or SquadChainConfig()
    strategy = config.strategy
    agents: dict[str, BaseAgent] = ctx.get("agents", {})
    llm = ctx.get("llm")

    # Get research query
    research_query = ctx.get("research_query", "")
    company_info = ctx.get("company_info")

    if not agents:
        return {
            "agent_results": {},
            "error": "No agents provided",
            "strategy": strategy,
        }

    # Enhance query with company context
    full_query = research_query
    if company_info:
        full_query = f"Prepare meeting materials for {company_info.name}.\n\n{research_query}"

    # Execute based on strategy
    if strategy == "supervisor":
        result = await _execute_supervisor_strategy(
            query=full_query,
            agents=agents,
            config=config,
            llm=llm,
        )
    elif strategy == "broadcast":
        result = await _execute_broadcast_strategy(
            query=full_query,
            agents=agents,
            config=config,
            llm=llm,
        )
    elif strategy == "classifier":
        result = await _execute_classifier_strategy(
            query=full_query,
            agents=agents,
            config=config,
            llm=llm,
        )
    else:
        # Default to broadcast
        result = await _execute_broadcast_strategy(
            query=full_query,
            agents=agents,
            config=config,
            llm=llm,
        )

    duration_ms = (time.perf_counter() - start) * 1000

    # Store results
    ctx.set("squad_results", result, scope=ContextScope.CHAIN)

    return {
        "agent_results": result.get("data", {}),
        "citations": result.get("citations", []),
        "delegated_to": result.get("delegated_to", list(agents.keys())),
        "strategy": strategy,
        "duration_ms": duration_ms,
        "errors": result.get("errors", []),
    }


async def _execute_supervisor_strategy(
    query: str,
    agents: dict[str, BaseAgent],
    config: SquadChainConfig,
    llm: Any,
) -> dict[str, Any]:
    """Execute using supervisor pattern - lead agent decides delegation."""
    # Create supervisor
    supervisor = SupervisorAgent(
        team=list(agents.values()),
        config=SupervisorConfig(
            lead_model=config.lead_model,
            lead_temperature=config.lead_temperature,
            parallel_execution=True,
            response_strategy=ResponseStrategy(config.response_strategy),
            max_tokens_per_agent=config.max_tokens_per_agent,
            timeout_seconds=config.timeout_seconds,
            continue_on_agent_failure=config.continue_on_failure,
        ),
        llm=llm,
        name="cmpt_supervisor",
        description="Coordinates financial research agents for meeting preparation",
    )

    # Execute
    result = await supervisor.fetch(query)

    return {
        "data": result.data.get("team_results", {}) if result.data else {},
        "synthesis": result.data.get("synthesis", "") if result.data else "",
        "citations": result.citations,
        "delegated_to": result.metadata.get("delegated_to", []),
        "errors": [result.error] if result.error else [],
    }


async def _execute_broadcast_strategy(
    query: str,
    agents: dict[str, BaseAgent],
    config: SquadChainConfig,
    llm: Any,
) -> dict[str, Any]:
    """Execute using broadcast pattern - all agents in parallel."""
    # Create bridge
    bridge = AgentSquadBridge(
        config=AgentSquadConfig(
            default_strategy=RoutingStrategy.BROADCAST,
            response_strategy=ResponseStrategy(config.response_strategy),
            max_tokens_per_agent=config.max_tokens_per_agent,
            timeout_seconds=config.timeout_seconds,
        ),
        llm=llm,
    )

    # Add agents with descriptions
    for name, agent in agents.items():
        description = config.agent_descriptions.get(name, f"{name} agent")
        bridge.add_ao_agent(agent, name=name, description=description)

    # Execute broadcast
    result = await bridge.broadcast(query)

    return {
        "data": result.data or {},
        "citations": result.citations,
        "delegated_to": list(agents.keys()),
        "errors": [result.error] if result.error else [],
    }


async def _execute_classifier_strategy(
    query: str,
    agents: dict[str, BaseAgent],
    config: SquadChainConfig,
    llm: Any,
) -> dict[str, Any]:
    """Execute using classifier pattern - route to single best agent."""
    # Create bridge
    bridge = AgentSquadBridge(
        config=AgentSquadConfig(
            default_strategy=RoutingStrategy.CLASSIFIER,
            response_strategy=ResponseStrategy(config.response_strategy),
            max_tokens_per_agent=config.max_tokens_per_agent,
            timeout_seconds=config.timeout_seconds,
        ),
        llm=llm,
    )

    # Add agents with descriptions
    for name, agent in agents.items():
        description = config.agent_descriptions.get(name, f"{name} agent")
        bridge.add_ao_agent(agent, name=name, description=description)

    # Execute with classifier routing
    result = await bridge.route(query, strategy=RoutingStrategy.CLASSIFIER)

    routed_to = result.metadata.get("routed_to", "unknown")

    return {
        "data": {routed_to: result.data} if result.data else {},
        "citations": result.citations,
        "delegated_to": [routed_to],
        "errors": [result.error] if result.error else [],
    }


# =============================================================================
# STEP 4: RESPONSE BUILDING
# =============================================================================


@squad_ao.step(name="build_response", deps=["execute_squad"])
async def build_response(ctx: ChainContext) -> dict[str, Any]:
    """
    Build final meeting prep response from squad results.

    In supervisor mode, we may already have a synthesis from the lead agent.
    Otherwise, we perform synthesis here.
    """
    from cmpt.services._03_response_builder import ResponseBuilderService

    # Get data from context
    company_info = ctx.get("company_info")
    company_name = company_info.name if company_info else "Unknown"

    squad_result = ctx.get_result("execute_squad")
    agent_results = squad_result.output.get("agent_results", {}) if squad_result else {}
    synthesis = ctx.get("squad_results", {}).get("synthesis", "")

    # Get LLM from context
    llm = ctx.get("llm")

    # Combine agent results into chunks
    agent_chunks = {}
    for agent_name, result in agent_results.items():
        if isinstance(result, dict):
            agent_chunks[agent_name] = result.get("output", str(result))
        else:
            agent_chunks[agent_name] = str(result)

    # If we have a synthesis from supervisor, use it
    if synthesis:
        strategic_analysis = synthesis
    else:
        # Generate strategic analysis
        service = ResponseBuilderService(llm=llm)
        priority_distribution = ctx.get_result("prioritize_content").output.get("priority_distribution")
        strategic_analysis = await service._generate_strategic_analysis(
            company_name, agent_chunks, priority_distribution
        )

    # Extract financial metrics
    service = ResponseBuilderService(llm=llm)
    financial_metrics = await service._extract_financial_metrics(company_name, agent_chunks)

    # Build final content
    prepared_content = service._build_prepared_content(
        company_name, financial_metrics, strategic_analysis
    )

    # Collect all citations
    all_citations = ctx.get("squad_results", {}).get("citations", [])

    return {
        "financial_metrics": financial_metrics,
        "strategic_analysis": strategic_analysis,
        "prepared_content": prepared_content,
        "agent_results": agent_results,
        "company_name": company_name,
        "citations": all_citations,
        "timing_ms": ctx.timing_ms,
        "errors": ctx.errors,
        "strategy": ctx.get("squad_config", SquadChainConfig()).strategy,
    }


# =============================================================================
# CHAIN DEFINITION
# =============================================================================


@squad_ao.chain(name="cmpt_squad_chain")
class CMPTSquadChain:
    """
    CMPT Meeting Prep Chain - Supervisor/Squad Style

    Uses intelligent agent routing instead of static DAG execution.

    Steps:
    1. Extract context (parallel: firm_temporal, rbc_persona, client_persona)
    2. Build context (aggregate + fallbacks)
    3. Prioritize content & build research query
    4. Execute squad (supervisor/broadcast/classifier)
    5. Build response (synthesize results)
    """
    steps = [
        "extract_firm_temporal",
        "extract_rbc_persona",
        "extract_client_persona",
        "build_context",
        "prioritize_content",
        "execute_squad",
        "build_response",
    ]


# =============================================================================
# PUBLIC API
# =============================================================================


async def execute_squad_chain(
    request: ChainRequest,
    agents: dict[str, BaseAgent] | None = None,
    llm: Any | None = None,
    strategy: str = "supervisor",
    config: SquadChainConfig | None = None,
) -> dict[str, Any]:
    """
    Execute the CMPT meeting prep chain using supervisor pattern.

    Args:
        request: ChainRequest with meeting details
        agents: Dict of agent_name -> agent_instance
        llm: LLM instance for lead agent and response building
        strategy: Execution strategy - "supervisor", "broadcast", or "classifier"
        config: Optional SquadChainConfig for fine-tuning

    Returns:
        Dict with prepared_content, financial_metrics, strategic_analysis, etc.

    Example:
        from cmpt.chain_squad import execute_squad_chain, SquadChainConfig

        # Supervisor mode - lead agent decides which agents to call
        result = await execute_squad_chain(
            request=ChainRequest(
                corporate_company_name="Apple Inc",
                meeting_datetime="2025-02-01T10:00:00Z"
            ),
            agents={
                "sec_agent": SECAgent(),
                "capiq_agent": CapIQAgent(),
                "news_agent": NewsAgent(),
            },
            strategy="supervisor",
            llm=my_llm,
        )

        # Broadcast mode - all agents execute in parallel
        result = await execute_squad_chain(
            request=request,
            agents=agents,
            strategy="broadcast",
        )

        # Classifier mode - route to single best agent
        result = await execute_squad_chain(
            request=request,
            agents=agents,
            strategy="classifier",
        )
    """
    # Build config
    squad_config = config or SquadChainConfig()
    squad_config.strategy = strategy

    # Prepare initial context
    initial_data = {
        "request": request,
        "overrides": request.overrides or ChainRequestOverrides(),
        "agents": agents or {},
        "llm": llm,
        "squad_config": squad_config,
    }

    # Launch the chain
    result = await squad_ao.launch("cmpt_squad_chain", initial_data)

    # Extract final output
    results_list = result.get("results", [])
    final_output = results_list[-1] if results_list else {}

    return final_output


# Convenience functions for specific strategies


async def execute_supervisor_chain(
    request: ChainRequest,
    agents: dict[str, BaseAgent] | None = None,
    llm: Any | None = None,
    config: SquadChainConfig | None = None,
) -> dict[str, Any]:
    """Execute chain with supervisor strategy (lead agent decides routing)."""
    return await execute_squad_chain(
        request=request,
        agents=agents,
        llm=llm,
        strategy="supervisor",
        config=config,
    )


async def execute_broadcast_chain(
    request: ChainRequest,
    agents: dict[str, BaseAgent] | None = None,
    llm: Any | None = None,
    config: SquadChainConfig | None = None,
) -> dict[str, Any]:
    """Execute chain with broadcast strategy (all agents in parallel)."""
    return await execute_squad_chain(
        request=request,
        agents=agents,
        llm=llm,
        strategy="broadcast",
        config=config,
    )


async def execute_classifier_chain(
    request: ChainRequest,
    agents: dict[str, BaseAgent] | None = None,
    llm: Any | None = None,
    config: SquadChainConfig | None = None,
) -> dict[str, Any]:
    """Execute chain with classifier strategy (route to single best agent)."""
    return await execute_squad_chain(
        request=request,
        agents=agents,
        llm=llm,
        strategy="classifier",
        config=config,
    )


__all__ = [
    # Orchestrator
    "squad_ao",
    # Main API
    "execute_squad_chain",
    # Convenience functions
    "execute_supervisor_chain",
    "execute_broadcast_chain",
    "execute_classifier_chain",
    # Configuration
    "SquadChainConfig",
    # Chain class
    "CMPTSquadChain",
]
