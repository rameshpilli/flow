"""
AgentOrchestrator Integrations

Third-party framework integrations for AgentOrchestrator.

Available integrations:
- agent_squad: AWS Labs Agent Squad integration for intelligent multi-agent routing

Pluggable Interfaces:
- ConversationMemoryStore: Implement for custom conversation persistence (Redis, PostgreSQL, etc.)
- AgentClassifier: Implement for custom routing logic
- LLMGatewayClassifier: Uses your LLM Gateway with OAuth (no direct API keys needed)
- ResponseHandler: Configure response processing strategies

Usage:
    # Basic usage with LLM Gateway (behind proxy)
    from agentorchestrator.integrations import AgentSquadBridge, LLMGatewayClassifier
    from agentorchestrator.services.llm_gateway import LLMGatewayClient

    llm_client = LLMGatewayClient(
        server_url=Config.LLM_SERVER_URL,
        oauth_endpoint=Config.LLM_OAUTH_ENDPOINT,
        client_id=Config.LLM_CLIENT_ID,
        client_secret=Config.LLM_CLIENT_SECRET,
        model_name=Config.LLM_MODEL_NAME,
    )

    bridge = AgentSquadBridge(classifier=LLMGatewayClassifier(llm_client))
    bridge.add_ao_agent(my_agent, description="My agent")
    result = await bridge.route("user query")

    # With custom memory store
    from agentorchestrator.integrations import AgentSquadBridge, ConversationMemoryStore

    class RedisMemoryStore(ConversationMemoryStore):
        async def store(self, session_id, user_id, entry):
            await redis.rpush(f"conv:{session_id}:{user_id}", json.dumps(entry))

        async def retrieve(self, session_id, user_id, limit=10):
            return [json.loads(e) for e in await redis.lrange(...)]

    bridge = AgentSquadBridge(memory_store=RedisMemoryStore())
"""

from agentorchestrator.integrations.agent_squad import (
    # Core classes
    AgentSquadBridge,
    AgentSquadConfig,
    AOAgentAdapter,
    SupervisorAgent,
    SupervisorConfig,
    # Enums
    RoutingStrategy,
    ResponseStrategy,
    # Pluggable interfaces
    ConversationMemoryStore,
    InMemoryStore,
    AgentClassifier,
    KeywordClassifier,
    LLMClassifier,
    LLMGatewayClassifier,  # Uses your LLM Gateway with OAuth
    ResponseHandler,
    # Utilities
    create_squad_from_agents,
)

__all__ = [
    # Core integration classes
    "AgentSquadBridge",
    "AgentSquadConfig",
    "AOAgentAdapter",
    # Supervisor support
    "SupervisorAgent",
    "SupervisorConfig",
    # Enums
    "RoutingStrategy",
    "ResponseStrategy",
    # Pluggable interfaces (for custom implementations)
    "ConversationMemoryStore",
    "InMemoryStore",
    "AgentClassifier",
    "KeywordClassifier",
    "LLMClassifier",
    "LLMGatewayClassifier",  # Uses your LLM Gateway with OAuth
    "ResponseHandler",
    # Utilities
    "create_squad_from_agents",
]
