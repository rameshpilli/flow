"""
Supervisor Agent as a Chain Step Example
=========================================

This example demonstrates how to use a SupervisorAgent as a single step
within a larger DAG-based chain. This pattern is useful when you want:

1. Pre-processing steps before multi-agent coordination
2. Post-processing of agent outputs
3. Integration with existing DAG pipelines
4. Controlled agent execution within broader workflows

Architecture:
    ┌─────────────────┐
    │  prepare_input  │  DAG Step: Parse and validate
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  run_supervisor │  DAG Step wrapping SupervisorAgent
    │  ┌────────────┐ │
    │  │ Supervisor │ │
    │  │  ┌───┬───┐ │ │
    │  │  │R  │A  │ │ │  R=Researcher, A=Analyst
    │  │  └───┴───┘ │ │
    │  └────────────┘ │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  format_report  │  DAG Step: Format final output
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  save_results   │  DAG Step: Persist results
    └─────────────────┘

Usage:
    python supervisor_in_chain.py

This combines the best of both worlds:
- DAG's dependency management and parallel execution
- Supervisor's intelligent agent coordination
"""

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.context import ChainContext, ContextScope

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create orchestrator
ao = AgentOrchestrator(name="supervisor_chain")


# ═══════════════════════════════════════════════════════════════════════════════
#                         MOCK AGENTS (for demo)
# ═══════════════════════════════════════════════════════════════════════════════


class MockLLMGatewayAgent:
    """Mock agent for demonstration purposes."""
    
    def __init__(self, name: str, description: str, response: str):
        self.name = name
        self.description = description
        self._response = response
    
    async def process_request(
        self,
        input_text: str,
        user_id: str = "user",
        session_id: str = "session",
        **kwargs,
    ):
        """Simulate agent processing."""
        await asyncio.sleep(0.1)  # Simulate LLM latency
        
        # Return mock response
        return MagicMock(
            content=f"[{self.name}] {self._response} (Query: {input_text[:50]}...)",
            role="assistant",
        )


class MockSupervisorAgent:
    """Mock supervisor for demonstration purposes."""
    
    def __init__(self, name: str, team: list, **kwargs):
        self.name = name
        self.team = team
    
    async def process_request(
        self,
        input_text: str,
        user_id: str = "user",
        session_id: str = "session",
        chat_history: list = None,
        additional_params: dict = None,
    ):
        """Coordinate team and return combined result."""
        logger.info(f"Supervisor '{self.name}' coordinating {len(self.team)} agents")
        
        # Run all team members in parallel
        tasks = [
            agent.process_request(input_text, user_id, session_id)
            for agent in self.team
        ]
        results = await asyncio.gather(*tasks)
        
        # Combine results
        combined = "\n\n".join([
            f"### {agent.name}\n{result.content}"
            for agent, result in zip(self.team, results)
        ])
        
        return MagicMock(
            content=f"# Supervisor Summary\n\n{combined}\n\n## Conclusion\nBased on team analysis...",
            role="assistant",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                              STEP DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════


@ao.step(name="prepare_input", produces=["validated_query", "context_data"])
async def prepare_input(ctx: ChainContext) -> dict[str, Any]:
    """
    Pre-process and validate input before sending to agents.
    
    This step can:
    - Validate input format
    - Enrich with additional context (user preferences, history)
    - Extract entities and intent
    - Apply rate limiting or access control
    """
    query = ctx.get("query", "")
    user_id = ctx.get("user_id", "anonymous")
    
    logger.info(f"Preparing input for user {user_id}")
    
    # Validate and clean input
    if not query or len(query.strip()) < 3:
        raise ValueError("Query too short")
    
    validated_query = query.strip()
    
    # Add enrichment data (in production, fetch from user profile, etc.)
    context_data = {
        "user_id": user_id,
        "timestamp": "2025-01-25T10:00:00Z",
        "preferences": {
            "response_style": "detailed",
            "include_sources": True,
        },
    }
    
    ctx.set("validated_query", validated_query, scope=ContextScope.CHAIN)
    ctx.set("context_data", context_data, scope=ContextScope.CHAIN)
    
    return {
        "validated_query": validated_query,
        "context_data": context_data,
    }


@ao.step(name="run_supervisor", deps=["prepare_input"], produces=["agent_response"])
async def run_supervisor(ctx: ChainContext) -> dict[str, Any]:
    """
    Execute a SupervisorAgent as a DAG step.
    
    This step wraps a multi-agent supervisor, allowing it to be
    used within larger DAG pipelines with proper dependency management.
    """
    query = ctx.get("validated_query")
    context_data = ctx.get("context_data")
    user_id = context_data.get("user_id", "default")
    
    logger.info("Running supervisor agent within DAG step")
    
    # Create specialist agents
    researcher = MockLLMGatewayAgent(
        name="Researcher",
        description="Researches topics and gathers information",
        response="Found key insights about the topic including recent developments and trends.",
    )
    
    analyst = MockLLMGatewayAgent(
        name="Analyst", 
        description="Analyzes data and provides insights",
        response="Analysis indicates strong potential with some risks to consider.",
    )
    
    writer = MockLLMGatewayAgent(
        name="Writer",
        description="Writes clear, structured reports",
        response="Here's a well-structured summary of our findings.",
    )
    
    # Create and run supervisor
    supervisor = MockSupervisorAgent(
        name="ResearchSupervisor",
        team=[researcher, analyst, writer],
    )
    
    # Execute supervisor
    result = await supervisor.process_request(
        input_text=query,
        user_id=user_id,
        session_id=f"session_{ctx.request_id}",
        additional_params=context_data.get("preferences"),
    )
    
    ctx.set("agent_response", result.content, scope=ContextScope.CHAIN)
    
    return {
        "agent_response": result.content,
        "agents_used": ["Researcher", "Analyst", "Writer"],
    }


@ao.step(name="format_report", deps=["run_supervisor"], produces=["formatted_report"])
async def format_report(ctx: ChainContext) -> dict[str, Any]:
    """
    Post-process agent output into final report format.
    
    This step can:
    - Apply consistent formatting
    - Add headers, footers, metadata
    - Generate table of contents
    - Apply templates
    """
    agent_response = ctx.get("agent_response")
    context_data = ctx.get("context_data")
    
    logger.info("Formatting final report")
    
    # Format with metadata
    formatted = f"""
================================================================================
                           RESEARCH REPORT
================================================================================
User: {context_data.get('user_id', 'N/A')}
Generated: {context_data.get('timestamp', 'N/A')}
================================================================================

{agent_response}

================================================================================
                           END OF REPORT
================================================================================
"""
    
    ctx.set("formatted_report", formatted, scope=ContextScope.CHAIN)
    
    return {
        "formatted_report": formatted,
        "word_count": len(formatted.split()),
    }


@ao.step(name="save_results", deps=["format_report"])
async def save_results(ctx: ChainContext) -> dict[str, Any]:
    """
    Save results (to database, file, etc.).
    
    In production, this might:
    - Store in database
    - Upload to cloud storage
    - Send notifications
    - Update analytics
    """
    formatted_report = ctx.get("formatted_report")
    context_data = ctx.get("context_data")
    
    logger.info("Saving results")
    
    # Simulate save (in production, write to DB/storage)
    report_id = f"report_{ctx.request_id}"
    
    return {
        "report_id": report_id,
        "saved": True,
        "location": f"/reports/{report_id}.md",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#                              CHAIN DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════


@ao.chain(name="supervisor_pipeline")
class SupervisorPipeline:
    """
    A DAG chain that incorporates a SupervisorAgent as one of its steps.
    
    This pattern allows:
    1. Pre-processing before agent execution (validation, enrichment)
    2. Multi-agent coordination via supervisor
    3. Post-processing after agent execution (formatting, storage)
    4. Full DAG dependency management
    """
    steps = [
        "prepare_input",
        "run_supervisor",
        "format_report",
        "save_results",
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#                    PRODUCTION EXAMPLE WITH REAL AGENTS
# ═══════════════════════════════════════════════════════════════════════════════


def create_production_supervisor_step(ao: AgentOrchestrator):
    """
    Example of creating a supervisor step with real agents.
    
    This shows how you would wire up actual LLMGatewayAgents
    in a production environment.
    """
    # This is pseudo-code showing the pattern
    """
    from agentorchestrator.squad import (
        LLMGatewayAgent,
        LLMGatewayAgentOptions,
        SupervisorAgent,
        SupervisorAgentOptions,
    )
    from agentorchestrator.services import LLMGatewayClient
    
    # Get LLM client
    llm_client = LLMGatewayClient.from_env()
    
    # Create specialist agents
    researcher = LLMGatewayAgent(LLMGatewayAgentOptions(
        name="Researcher",
        description="Expert at finding and summarizing information",
        system_prompt="You are a research specialist...",
        llm_client=llm_client,
    ))
    
    analyst = LLMGatewayAgent(LLMGatewayAgentOptions(
        name="Analyst",
        description="Expert at analyzing data and trends",
        system_prompt="You are a data analyst...",
        llm_client=llm_client,
    ))
    
    # Create supervisor
    supervisor = SupervisorAgent(SupervisorAgentOptions(
        name="LeadResearcher",
        lead_agent=LLMGatewayAgent(LLMGatewayAgentOptions(
            name="Lead",
            llm_client=llm_client,
        )),
        team=[researcher, analyst],
    ))
    
    # Register as step
    @ao.step(name="run_agents", deps=["prepare_input"])
    async def run_agents(ctx):
        result = await supervisor.process_request(
            input_text=ctx.get("validated_query"),
            user_id=ctx.get("user_id"),
            session_id=ctx.request_id,
        )
        ctx.set("agent_response", result.content)
        return {"response": result.content}
    """
    pass


# ═══════════════════════════════════════════════════════════════════════════════
#                                    MAIN
# ═══════════════════════════════════════════════════════════════════════════════


async def main():
    """Run the supervisor-in-chain pipeline."""
    print("\n" + "="*60)
    print("Supervisor Agent in DAG Chain Example")
    print("="*60 + "\n")
    
    # Show the DAG structure
    print("Pipeline Structure:")
    print(ao.graph("supervisor_pipeline"))
    print()
    
    # Run the pipeline
    query = "What are the implications of quantum computing for cybersecurity?"
    
    result = await ao.launch(
        "supervisor_pipeline",
        data={
            "query": query,
            "user_id": "demo_user",
        },
    )
    
    if result["success"]:
        print("Pipeline completed successfully!\n")
        
        # Print the formatted report
        print(result["context"]["data"].get("formatted_report", "No report"))
        
        # Show step timings
        print("\nStep Timings:")
        print("-" * 40)
        for step_result in result.get("results", []):
            print(f"  {step_result['step_name']}: {step_result['duration_ms']:.0f}ms")
    else:
        print(f"Pipeline failed: {result.get('error', 'Unknown error')}")
    
    print(f"\nTotal duration: {result['duration_ms']:.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
