"""
Supervisor Agent Chain Example

Demonstrates how to create a multi-agent supervisor pattern using
AgentOrchestrator's @ao decorators combined with the Squad module.

This example shows:
1. Defining specialist agents as @ao.agent classes
2. Creating a supervisor that coordinates specialist agents
3. Building a chain that routes through classification -> delegation -> aggregation

Architecture:
                    ┌─────────────────┐
                    │   User Query    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Classifier    │
                    │   (Route to     │
                    │    specialist)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───┐  ┌───────▼───┐  ┌───────▼────┐
     │ TechAgent  │  │FinanceAgent│  │ DataAgent  │
     │ (Python,   │  │(Stocks,    │  │(SQL, Data  │
     │  APIs)     │  │ Analysis)  │  │ Analysis)  │
     └────────────┘  └───────────┘  └────────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │   Supervisor    │
                    │   (Aggregate    │
                    │    responses)   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Response      │
                    └─────────────────┘

Usage:
    from agentorchestrator.examples.supervisor_chain import (
        create_supervisor_orchestrator,
        run_example,
    )

    # Quick start
    await run_example()

    # Or use programmatically
    ao = create_supervisor_orchestrator()
    result = await ao.launch("supervisor_chain", {
        "query": "How do I optimize my Python API for handling stock data?"
    })
"""

import asyncio
import logging
from typing import Any

from agentorchestrator import AgentOrchestrator, Context
from agentorchestrator.services.vector_store import VectorStoreService

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                              AGENT DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════


def create_supervisor_orchestrator(
    llm_client: Any = None,
    use_mock: bool = True,
    vector_store: VectorStoreService | None = None,
    agent_timeout_seconds: float = 30.0,
) -> AgentOrchestrator:
    """
    Create an AgentOrchestrator instance with supervisor pattern agents.

    Args:
        llm_client: Optional LLM client (e.g., LLMGatewayClient)
        use_mock: If True and no llm_client provided, use mock responses

    Returns:
        Configured AgentOrchestrator instance
    """
    ao = AgentOrchestrator(
        name="supervisor_example",
        version="1.0.0",
        isolated=True,  # Isolated registries for this example
    )

    # ═══════════════════════════════════════════════════════════════════════════
    #                         SPECIALIST AGENTS
    # ═══════════════════════════════════════════════════════════════════════════

    @ao.agent(
        name="tech_agent",
        description="Handles technical programming questions (Python, APIs, debugging)",
        group="specialists",
    )
    class TechAgent:
        """Technical specialist for programming questions."""

        def __init__(self, llm_client: Any = None):
            self.llm_client = llm_client
            self.system_prompt = """You are a senior software engineer specializing in:
            - Python development and best practices
            - API design and optimization
            - Code review and debugging
            - Performance optimization

            Provide concise, actionable technical guidance."""

        async def process(self, query: str, context: dict | None = None) -> str:
            """Process a technical query."""
            if self.llm_client:
                return await self.llm_client.generate_async(
                    system_prompt=self.system_prompt,
                    user_message=query,
                )
            # Mock response for testing
            return f"[TechAgent] To optimize your code: Use async/await for I/O operations, implement caching, and profile your bottlenecks. Query: {query[:50]}..."

    @ao.agent(
        name="finance_agent",
        description="Handles financial queries (stocks, market analysis, trading)",
        group="specialists",
    )
    class FinanceAgent:
        """Financial specialist for market and trading questions."""

        def __init__(self, llm_client: Any = None):
            self.llm_client = llm_client
            self.system_prompt = """You are a financial analyst specializing in:
            - Stock market analysis
            - Financial data interpretation
            - Trading strategies
            - Risk assessment

            Provide data-driven financial insights."""

        async def process(self, query: str, context: dict | None = None) -> str:
            """Process a financial query."""
            if self.llm_client:
                return await self.llm_client.generate_async(
                    system_prompt=self.system_prompt,
                    user_message=query,
                )
            return f"[FinanceAgent] For stock analysis: Consider using moving averages, RSI, and volume indicators. Query: {query[:50]}..."

    @ao.agent(
        name="data_agent",
        description="Handles data analysis queries (SQL, ETL, data pipelines)",
        group="specialists",
    )
    class DataAgent:
        """Data specialist for analytics and SQL questions."""

        def __init__(self, llm_client: Any = None):
            self.llm_client = llm_client
            self.system_prompt = """You are a data engineer specializing in:
            - SQL optimization and query design
            - Data pipeline architecture
            - ETL processes
            - Data modeling

            Provide efficient data solutions."""

        async def process(self, query: str, context: dict | None = None) -> str:
            """Process a data query."""
            if self.llm_client:
                return await self.llm_client.generate_async(
                    system_prompt=self.system_prompt,
                    user_message=query,
                )
            return f"[DataAgent] For data optimization: Use indexes, partitioning, and materialized views. Query: {query[:50]}..."

    # ═══════════════════════════════════════════════════════════════════════════
    #                         SUPERVISOR AGENT
    # ═══════════════════════════════════════════════════════════════════════════

    @ao.agent(
        name="supervisor",
        description="Coordinates specialist agents and aggregates responses",
        group="coordinators",
    )
    class SupervisorAgent:
        """
        Supervisor that coordinates specialist agents.

        The supervisor:
        1. Receives the user query and specialist responses
        2. Synthesizes responses into a coherent answer
        3. Adds meta-commentary on which specialists contributed
        """

        def __init__(self, llm_client: Any = None):
            self.llm_client = llm_client
            self.system_prompt = """You are a team coordinator that synthesizes responses
            from specialist agents into a coherent, comprehensive answer.

            Your job is to:
            1. Combine insights from different specialists
            2. Resolve any contradictions
            3. Present a unified, actionable response
            4. Credit which specialists contributed
            """

        async def synthesize(
            self,
            query: str,
            specialist_responses: dict[str, str],
        ) -> str:
            """Synthesize specialist responses into a unified answer."""
            if self.llm_client:
                # Format specialist responses for the LLM
                formatted_responses = "\n\n".join(
                    f"**{name}**: {response}"
                    for name, response in specialist_responses.items()
                )
                user_message = f"""Original Query: {query}

Specialist Responses:
{formatted_responses}

Please synthesize these responses into a comprehensive answer."""

                return await self.llm_client.generate_async(
                    system_prompt=self.system_prompt,
                    user_message=user_message,
                )

            # Mock synthesis for testing
            contributors = ", ".join(specialist_responses.keys())
            return f"""**Synthesized Response**

Based on input from: {contributors}

{chr(10).join(f'- {r}' for r in specialist_responses.values())}

**Summary**: Combine technical optimization with data best practices for optimal results."""

    # ═══════════════════════════════════════════════════════════════════════════
    #                              CHAIN STEPS
    # ═══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="retrieve_context",
        description="Optionally retrieve RAG context for the query",
        produces=["rag_context"],
    )
    async def retrieve_context(ctx: Context) -> dict[str, Any]:
        """
        Retrieve relevant context using an optional vector store.
        """
        query = ctx.get("query", "")
        if not query or not vector_store:
            ctx.set("rag_context", [])
            return {"rag_context": []}

        try:
            matches = await vector_store.query(query, top_k=3)
        except Exception as exc:  # Defensive: retrieval should not break the chain
            logger.warning(f"Vector store query failed: {exc}")
            ctx.set("rag_context", [])
            return {"rag_context": []}

        rag_context = [
            {
                "id": match.id,
                "text": match.text,
                "score": match.score,
                "metadata": match.metadata,
            }
            for match in matches
        ]

        ctx.set("rag_context", rag_context)
        return {"rag_context": rag_context}

    @ao.step(
        name="classify_intent",
        deps=["retrieve_context"],
        description="Classify user query to determine which specialists to involve",
        produces=["classification"],
    )
    async def classify_intent(ctx: Context) -> dict[str, Any]:
        """
        Classify the user query to determine which specialist agents to invoke.

        Returns:
            Dict with selected_agents list and confidence scores
        """
        query = ctx.get("query", "")
        query_lower = query.lower()

        # Simple keyword-based classification (replace with LLM in production)
        agents = []
        confidence = {}

        # Check for technical keywords
        tech_keywords = ["python", "api", "code", "debug", "optimize", "function", "class"]
        if any(kw in query_lower for kw in tech_keywords):
            agents.append("tech_agent")
            confidence["tech_agent"] = 0.8

        # Check for finance keywords
        finance_keywords = ["stock", "market", "trading", "price", "invest", "financial"]
        if any(kw in query_lower for kw in finance_keywords):
            agents.append("finance_agent")
            confidence["finance_agent"] = 0.8

        # Check for data keywords
        data_keywords = ["sql", "data", "query", "database", "etl", "pipeline"]
        if any(kw in query_lower for kw in data_keywords):
            agents.append("data_agent")
            confidence["data_agent"] = 0.8

        # Default to tech_agent if no match
        if not agents:
            agents = ["tech_agent"]
            confidence["tech_agent"] = 0.5

        result = {
            "selected_agents": agents,
            "confidence": confidence,
            "query": query,
        }

        ctx.set("classification", result)
        logger.info(f"Classified query to agents: {agents}")

        return result

    @ao.step(
        name="delegate_to_specialists",
        deps=["classify_intent"],
        description="Delegate query to selected specialist agents in parallel",
        produces=["specialist_responses"],
    )
    async def delegate_to_specialists(ctx: Context) -> dict[str, Any]:
        """
        Delegate the query to selected specialist agents.

        Runs specialist agents in parallel for efficiency.
        """
        classification = ctx.get("classification", {})
        selected_agents = classification.get("selected_agents", ["tech_agent"])
        query = classification.get("query", ctx.get("query", ""))
        context_payload = {
            "rag_context": ctx.get("rag_context", []),
            "history": ctx.get("history"),
            "metadata": ctx.metadata,
        }

        # Get agent instances
        agent_instances = {}
        for agent_name in selected_agents:
            try:
                agent_instances[agent_name] = ao.get_agent(agent_name)
            except Exception as e:
                logger.warning(f"Could not get agent {agent_name}: {e}")

        # Run agents in parallel
        async def run_agent(name: str, agent: Any) -> tuple[str, str]:
            try:
                response = await asyncio.wait_for(
                    agent.process(query, context=context_payload),
                    timeout=agent_timeout_seconds,
                )
                return name, response
            except asyncio.TimeoutError:
                logger.error(f"Agent {name} timed out after {agent_timeout_seconds}s")
                return name, f"[Error from {name}]: request timed out after {agent_timeout_seconds}s"
            except Exception as e:
                logger.error(f"Agent {name} failed: {e}")
                return name, f"[Error from {name}]: {str(e)}"

        tasks = [
            run_agent(name, agent)
            for name, agent in agent_instances.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect responses
        specialist_responses = {}
        for result in results:
            if isinstance(result, tuple):
                name, response = result
                specialist_responses[name] = response
            elif isinstance(result, Exception):
                logger.error(f"Task failed: {result}")

        ctx.set("specialist_responses", specialist_responses)
        logger.info(f"Got responses from {len(specialist_responses)} specialists")

        return {
            "specialist_responses": specialist_responses,
            "agents_called": list(specialist_responses.keys()),
        }

    @ao.step(
        name="supervisor_synthesize",
        deps=["delegate_to_specialists"],
        description="Supervisor synthesizes specialist responses",
        produces=["final_response"],
    )
    async def supervisor_synthesize(ctx: Context) -> dict[str, Any]:
        """
        Supervisor synthesizes responses from specialists.
        """
        query = ctx.get("query", "")
        specialist_responses = ctx.get("specialist_responses", {})

        # Get supervisor instance
        supervisor = ao.get_agent("supervisor")

        # Synthesize responses
        final_response = await supervisor.synthesize(query, specialist_responses)

        ctx.set("final_response", final_response)
        logger.info("Supervisor synthesized final response")

        return {
            "response": final_response,
            "specialists_used": list(specialist_responses.keys()),
        }

    @ao.step(
        name="format_response",
        deps=["supervisor_synthesize"],
        description="Format the final response with metadata",
        produces=["formatted_output"],
    )
    async def format_response(ctx: Context) -> dict[str, Any]:
        """
        Format the final response with metadata.
        """
        final_response = ctx.get("final_response", "")
        classification = ctx.get("classification", {})

        formatted = {
            "answer": final_response,
            "metadata": {
                "agents_used": classification.get("selected_agents", []),
                "confidence_scores": classification.get("confidence", {}),
            },
        }

        ctx.set("formatted_output", formatted)
        return formatted

    # ═══════════════════════════════════════════════════════════════════════════
    #                              CHAIN DEFINITION
    # ═══════════════════════════════════════════════════════════════════════════

    @ao.chain(
        name="supervisor_chain",
        description="Multi-agent supervisor chain with classification and delegation",
    )
    class SupervisorChain:
        """
        Chain that implements the supervisor pattern:
        1. Classify user intent
        2. Delegate to specialist agents
        3. Supervisor synthesizes responses
        4. Format and return
        """
        steps = [
            "retrieve_context",
            "classify_intent",
            "delegate_to_specialists",
            "supervisor_synthesize",
            "format_response",
        ]

        # Use best-effort error handling - continue even if a specialist fails
        error_handling = "best_effort"

    return ao


# ═══════════════════════════════════════════════════════════════════════════════
#                              EXAMPLE USAGE
# ═══════════════════════════════════════════════════════════════════════════════


async def run_example():
    """Run the supervisor chain example."""
    print("\n" + "=" * 70)
    print("  Supervisor Chain Example")
    print("=" * 70 + "\n")

    # Create orchestrator
    ao = create_supervisor_orchestrator(use_mock=True)

    # Validate the chain
    print("Validating chain...")
    ao.check("supervisor_chain")

    # Show the DAG
    print("\nChain DAG:")
    ao.graph("supervisor_chain")

    # Run example queries
    test_queries = [
        "How do I optimize my Python API for handling stock data?",
        "What SQL queries should I use for financial analysis?",
        "How do I implement async/await in Python?",
    ]

    for query in test_queries:
        print(f"\n{'─' * 70}")
        print(f"Query: {query}")
        print("─" * 70)

        result = await ao.launch("supervisor_chain", {"query": query})

        if result.get("success"):
            output = result.get("context", {}).get("data", {}).get("formatted_output", {})
            print(f"\nAnswer: {output.get('answer', 'No answer')[:200]}...")
            print(f"Agents used: {output.get('metadata', {}).get('agents_used', [])}")
        else:
            print(f"\nError: {result.get('error', {}).get('message', 'Unknown error')}")

    print("\n" + "=" * 70 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
#                              WITH SQUAD MODULE
# ═══════════════════════════════════════════════════════════════════════════════


def create_squad_supervisor_orchestrator(
    llm_client: Any = None,
) -> AgentOrchestrator:
    """
    Create a supervisor orchestrator using the Squad module with all enhancements.

    This shows how to integrate @ao decorators with the Squad's
    MultiAgentOrchestrator for production-ready multi-agent routing.

    Features demonstrated:
        - Context-aware LLM-based classification
        - Full chat history propagation to agents
        - RAG context injection
        - Supervisor with validation/judge
        - Guardrails for safety
        - OTEL tracing
        - Metrics collection
        - Dynamic team composition

    Args:
        llm_client: LLM client for the squad agents

    Returns:
        Configured AgentOrchestrator instance
    """
    from agentorchestrator.squad import (
        MultiAgentOrchestrator as SquadOrchestrator,
        LLMGatewayAgent,
        LLMGatewayAgentOptions,
        LLMGatewayClassifier,
        LLMGatewayClassifierOptions,
        SupervisorAgent,
        SupervisorAgentOptions,
        InMemoryChatStorage,
    )

    ao = AgentOrchestrator(
        name="squad_supervisor",
        version="2.0.0",
        isolated=True,
    )

    # Custom validator function for response quality
    def validate_response(
        query: str,
        response: str,
        agent_responses: dict[str, str]
    ) -> tuple[bool, str]:
        """
        Validate the synthesized response for quality.

        Args:
            query: Original user query
            response: Synthesized response from supervisor
            agent_responses: Individual agent responses

        Returns:
            Tuple of (is_valid, feedback)
        """
        # Check minimum response length
        if len(response) < 50:
            return False, "Response is too short. Please provide more detail."

        # Check that response addresses the query
        query_words = set(query.lower().split())
        response_words = set(response.lower().split())
        overlap = len(query_words & response_words)
        if overlap < 2:
            return False, "Response doesn't seem to address the query."

        # Check that agent contributions are synthesized
        if agent_responses:
            # Response should incorporate info from agents, not ignore them
            agent_keywords = set()
            for agent_response in agent_responses.values():
                agent_keywords.update(agent_response.lower().split()[:20])
            synthesis_overlap = len(agent_keywords & response_words)
            if synthesis_overlap < 3:
                return False, "Response should better incorporate specialist insights."

        return True, ""

    # Register the squad orchestrator as a resource
    @ao.resource("squad_orchestrator")
    def create_squad():
        """Create the squad orchestrator with enhanced agents."""
        # Create specialist agents using Squad with context support
        tech_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="TechAgent",
            description="Handles technical programming questions",
            llm_client=llm_client,
            system_prompt="""You are a senior software engineer specializing in:
- Python development and best practices
- API design and optimization
- Code review and debugging
- Performance optimization

Provide concise, actionable technical guidance.
Consider the conversation history and any RAG context provided.""",
            enable_tracing=True,
            max_history_messages=10,
            context_keys=["rag_context", "user_profile"],
            timeout_seconds=30.0,
        ))

        finance_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="FinanceAgent",
            description="Handles financial queries",
            llm_client=llm_client,
            system_prompt="""You are a financial analyst specializing in:
- Stock market analysis
- Financial data interpretation
- Trading strategies
- Risk assessment

Provide data-driven financial insights.
Consider the conversation history and any RAG context provided.""",
            enable_tracing=True,
            max_history_messages=10,
            context_keys=["rag_context", "user_profile"],
            timeout_seconds=30.0,
        ))

        data_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="DataAgent",
            description="Handles data analysis and SQL queries",
            llm_client=llm_client,
            system_prompt="""You are a data engineer specializing in:
- SQL optimization and query design
- Data pipeline architecture
- ETL processes
- Data modeling

Provide efficient data solutions.
Consider the conversation history and any RAG context provided.""",
            enable_tracing=True,
            max_history_messages=10,
            context_keys=["rag_context", "user_profile"],
            timeout_seconds=30.0,
        ))

        # Create supervisor lead agent
        lead_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
            name="SupervisorLead",
            description="Coordinates the team to answer complex questions",
            llm_client=llm_client,
            system_prompt="""You are a team coordinator that synthesizes responses
from specialist agents into a coherent, comprehensive answer.

Your job is to:
1. Analyze the user's question and delegate to appropriate specialists
2. Combine insights from different specialists
3. Resolve any contradictions
4. Present a unified, actionable response
5. Never make up information - only use what specialists provide""",
            enable_tracing=True,
            max_history_messages=10,
        ))

        # Create supervisor with validation and guardrails
        supervisor = SupervisorAgent(SupervisorAgentOptions(
            name="Supervisor",
            description="Coordinates specialist agents with validation",
            lead_agent=lead_agent,
            team=[tech_agent, finance_agent, data_agent],
            trace=True,
            enable_tracing=True,
            enable_validation=True,
            validator=validate_response,
            max_validation_retries=2,
            max_concurrent_agents=5,
            agent_timeout_seconds=30.0,
            guardrails=["no_pii", "max_length"],  # Safety guardrails
        ))

        # Create context-aware classifier
        classifier = LLMGatewayClassifier(
            LLMGatewayClassifierOptions(
                llm_client=llm_client,
                confidence_threshold=0.6,
                include_history=True,
                max_history_messages=5,
                enable_tracing=True,
            )
        )
        storage = InMemoryChatStorage()

        squad = SquadOrchestrator(
            classifier=classifier,
            storage=storage,
        )
        squad.add_agent(supervisor)
        squad.set_default_agent(supervisor)

        return squad

    # Step that uses the squad orchestrator with full context
    @ao.step(
        name="route_to_squad",
        resources=["squad_orchestrator"],
        description="Route query through squad multi-agent system with context",
        produces=["squad_response"],
    )
    async def route_to_squad(ctx: Context, squad_orchestrator) -> dict[str, Any]:
        """Route the query through the squad orchestrator with full context."""
        query = ctx.get("query", "")
        user_id = ctx.get("user_id", "default_user")
        session_id = ctx.get("session_id", ctx.request_id)

        # Build additional params with RAG context and user profile
        additional_params = {
            "rag_context": ctx.get("rag_context", ""),  # Retrieved docs
            "user_profile": ctx.get("user_profile", {}),  # User preferences
            "session_data": {
                "request_id": ctx.request_id,
                "metadata": ctx.metadata,
            },
        }

        response = await squad_orchestrator.route_request(
            user_input=query,
            user_id=user_id,
            session_id=session_id,
            additional_params=additional_params,
        )

        result = {
            "response": response.output.get_text() if response.output else "",
            "agent_id": response.metadata.agent_id if response.metadata else None,
            "streaming": response.streaming,
        }

        ctx.set("squad_response", result)
        return result

    @ao.step(
        name="collect_metrics",
        deps=["route_to_squad"],
        resources=["squad_orchestrator"],
        description="Collect and log metrics from the squad",
        produces=["metrics"],
    )
    async def collect_metrics(ctx: Context, squad_orchestrator) -> dict[str, Any]:
        """Collect metrics from the squad orchestrator."""
        # Get supervisor from squad
        supervisor = squad_orchestrator.get_agent("supervisor")
        if supervisor and hasattr(supervisor, 'get_metrics'):
            metrics = supervisor.get_metrics()
            ctx.set("metrics", metrics)
            logger.info(f"Squad metrics: {metrics}")
            return {"metrics": metrics}
        return {"metrics": {}}

    @ao.chain(name="squad_chain", description="Squad-based multi-agent routing with metrics")
    class SquadChain:
        steps = ["route_to_squad", "collect_metrics"]

    return ao


async def run_squad_example():
    """Run the enhanced squad supervisor example."""
    print("\n" + "=" * 70)
    print("  Enhanced Squad Supervisor Example")
    print("=" * 70 + "\n")

    # Create orchestrator (will use mock LLM in stub mode)
    ao = create_squad_supervisor_orchestrator(llm_client=None)

    # Run example query with context
    test_query = {
        "query": "How do I optimize my Python API for handling stock data?",
        "user_id": "developer-123",
        "session_id": "session-456",
        "user_profile": {
            "role": "developer",
            "expertise": ["python", "backend"],
            "preference": "detailed_explanations",
        },
        "rag_context": """
        Retrieved documentation snippets:
        1. Use async/await for I/O-bound operations
        2. Implement connection pooling for database access
        3. Consider using Redis for caching frequently accessed data
        """,
    }

    print(f"Query: {test_query['query']}")
    print(f"User Profile: {test_query['user_profile']}")
    print(f"RAG Context provided: Yes")
    print("─" * 70)

    result = await ao.launch("squad_chain", test_query)

    if result.get("success"):
        squad_response = result.get("context", {}).get("data", {}).get("squad_response", {})
        metrics = result.get("context", {}).get("data", {}).get("metrics", {})

        print(f"\nResponse: {squad_response.get('response', 'No response')[:300]}...")
        print(f"\nAgent ID: {squad_response.get('agent_id', 'N/A')}")

        if metrics:
            print(f"\nMetrics:")
            print(f"  - Requests: {metrics.get('request_count', 0)}")
            print(f"  - Avg Latency: {metrics.get('avg_latency_ms', 0):.1f}ms")
            print(f"  - Validation Failures: {metrics.get('validation_failures', 0)}")
    else:
        print(f"\nError: {result.get('error', {}).get('message', 'Unknown error')}")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_example())
