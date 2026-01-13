"""
Agent Squad Integration for AgentOrchestrator

Provides seamless integration with AWS Labs' Agent Squad framework for:
- Intelligent multi-agent routing
- Supervisor-based agent coordination
- Parallel agent execution with response aggregation
- Context persistence across conversations

This module implements a bridge pattern that allows:
1. Using AgentOrchestrator agents within Agent Squad
2. Using Agent Squad's routing/supervisor within AO chains
3. Mixing both frameworks' strengths

Installation:
    pip install "agent-squad[anthropic]"  # or [aws], [openai], [all]

Usage:
    from agentorchestrator.integrations import AgentSquadBridge, SupervisorAgent

    # Wrap existing AO agents for use in Agent Squad
    bridge = AgentSquadBridge()
    bridge.add_ao_agent(my_sec_agent, description="SEC filing expert")

    # Use Agent Squad's intelligent routing
    result = await bridge.route(query, user_id, session_id)

    # Or use supervisor pattern for team coordination
    supervisor = SupervisorAgent(
        lead_model="anthropic.claude-3-sonnet",
        team=[sec_agent, capiq_agent, news_agent],
    )
    result = await supervisor.coordinate(query)

Apache 2.0 License - Compatible with Agent Squad's license
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from agentorchestrator.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    # Core classes
    "AgentSquadBridge",
    "AgentSquadConfig",
    "AOAgentAdapter",
    "SupervisorAgent",
    "SupervisorConfig",
    # Enums
    "RoutingStrategy",
    "ResponseStrategy",
    # Pluggable interfaces
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


# =============================================================================
# ENUMS AND CONFIGURATION
# =============================================================================


class RoutingStrategy(str, Enum):
    """Agent routing strategies."""

    CLASSIFIER = "classifier"      # Intelligent routing to single best agent
    BROADCAST = "broadcast"        # Send to all agents, aggregate results
    SUPERVISOR = "supervisor"      # Lead agent decides which agents to call
    ROUND_ROBIN = "round_robin"   # Distribute queries across agents


class ResponseStrategy(str, Enum):
    """Strategy for handling large agent responses."""

    SUMMARIZE = "summarize"        # Summarize each response before aggregation
    EXTRACT = "extract"            # Extract structured data via Pydantic model
    TRUNCATE = "truncate"          # Truncate to max tokens
    MAP_REDUCE = "map_reduce"      # Two-phase: map (extract) then reduce (synthesize)
    RAW = "raw"                    # Pass through unchanged (use with caution)


@dataclass
class AgentSquadConfig:
    """Configuration for Agent Squad integration."""

    # Routing
    default_strategy: RoutingStrategy = RoutingStrategy.CLASSIFIER

    # Response handling
    response_strategy: ResponseStrategy = ResponseStrategy.SUMMARIZE
    max_tokens_per_agent: int = 2000
    preserve_citations: bool = True
    store_raw_responses: bool = True

    # Timeouts and retries
    timeout_seconds: float = 60.0
    max_retries: int = 2

    # Context persistence
    enable_memory: bool = True
    memory_window: int = 10  # Number of conversation turns to retain

    # Classifier settings (for CLASSIFIER strategy)
    classifier_model: str = "anthropic.claude-3-haiku-20240307-v1:0"
    classifier_temperature: float = 0.0


@dataclass
class SupervisorConfig:
    """Configuration for supervisor-based coordination."""

    # Lead agent settings
    lead_model: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    lead_temperature: float = 0.3
    lead_max_tokens: int = 4096

    # Team coordination
    parallel_execution: bool = True
    max_delegation_depth: int = 2  # Prevent infinite delegation loops

    # Response handling
    response_strategy: ResponseStrategy = ResponseStrategy.SUMMARIZE
    max_tokens_per_agent: int = 2000
    synthesis_prompt: str | None = None  # Custom synthesis instructions

    # Resilience
    timeout_seconds: float = 120.0
    continue_on_agent_failure: bool = True


# =============================================================================
# PLUGGABLE INTERFACES - Memory Store & Classifier
# =============================================================================


class ConversationMemoryStore:
    """
    Abstract interface for conversation memory persistence.

    Implement this interface to provide custom storage backends for
    conversation history (Redis, PostgreSQL, MongoDB, etc.).

    Usage:
        class RedisMemoryStore(ConversationMemoryStore):
            def __init__(self, redis_client):
                self.redis = redis_client

            async def store(self, session_id, user_id, entry):
                key = f"conv:{session_id}:{user_id}"
                await self.redis.rpush(key, json.dumps(entry))

            async def retrieve(self, session_id, user_id, limit=10):
                key = f"conv:{session_id}:{user_id}"
                entries = await self.redis.lrange(key, -limit, -1)
                return [json.loads(e) for e in entries]

        # Use with bridge
        bridge = AgentSquadBridge(memory_store=RedisMemoryStore(redis))
    """

    async def store(
        self,
        session_id: str,
        user_id: str,
        entry: dict[str, Any],
    ) -> None:
        """
        Store a conversation entry.

        Args:
            session_id: Session identifier
            user_id: User identifier
            entry: Conversation entry with query, response, timestamp, agent, etc.
        """
        raise NotImplementedError("Subclasses must implement store()")

    async def retrieve(
        self,
        session_id: str,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Retrieve recent conversation history.

        Args:
            session_id: Session identifier
            user_id: User identifier
            limit: Maximum entries to retrieve

        Returns:
            List of conversation entries, most recent last
        """
        raise NotImplementedError("Subclasses must implement retrieve()")

    async def clear(self, session_id: str, user_id: str) -> None:
        """Clear conversation history for a session."""
        raise NotImplementedError("Subclasses must implement clear()")

    async def get_context_summary(
        self,
        session_id: str,
        user_id: str,
    ) -> str | None:
        """
        Get a summarized context from conversation history.

        Override for custom summarization logic.
        """
        return None


class InMemoryStore(ConversationMemoryStore):
    """Default in-memory conversation store (not persistent)."""

    def __init__(self, max_entries: int = 100):
        self._store: dict[str, list[dict[str, Any]]] = {}
        self._max_entries = max_entries

    def _key(self, session_id: str, user_id: str) -> str:
        return f"{session_id}:{user_id}"

    async def store(
        self,
        session_id: str,
        user_id: str,
        entry: dict[str, Any],
    ) -> None:
        key = self._key(session_id, user_id)
        if key not in self._store:
            self._store[key] = []

        self._store[key].append({
            **entry,
            "timestamp": entry.get("timestamp", datetime.utcnow().isoformat()),
        })

        # Trim to max entries
        if len(self._store[key]) > self._max_entries:
            self._store[key] = self._store[key][-self._max_entries:]

    async def retrieve(
        self,
        session_id: str,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        key = self._key(session_id, user_id)
        entries = self._store.get(key, [])
        return entries[-limit:] if limit else entries

    async def clear(self, session_id: str, user_id: str) -> None:
        key = self._key(session_id, user_id)
        self._store.pop(key, None)


class AgentClassifier:
    """
    Abstract interface for agent routing/classification.

    Implement this interface to provide custom classification logic
    for routing queries to appropriate agents.

    Usage:
        class LLMClassifier(AgentClassifier):
            def __init__(self, llm):
                self.llm = llm

            async def classify(self, query, agents, context=None):
                prompt = f"Given agents: {agents}, which best handles: {query}"
                response = await self.llm.ainvoke(prompt)
                return {"agent": response.content, "confidence": 0.9}

        # Use with bridge
        bridge = AgentSquadBridge(classifier=LLMClassifier(llm))
    """

    async def classify(
        self,
        query: str,
        agents: dict[str, str],  # name -> description
        context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Classify a query to determine the best agent.

        Args:
            query: User query to classify
            agents: Dict of agent_name -> description
            context: Optional conversation history for context

        Returns:
            Dict with 'agent' (selected agent name) and 'confidence' (0-1)
        """
        raise NotImplementedError("Subclasses must implement classify()")


class KeywordClassifier(AgentClassifier):
    """Default keyword-based classifier (no LLM required)."""

    async def classify(
        self,
        query: str,
        agents: dict[str, str],
        context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Simple keyword matching classification."""
        query_lower = query.lower()
        scores: dict[str, float] = {}

        for name, description in agents.items():
            desc_lower = description.lower()
            score = 0.0

            # Word overlap scoring
            query_words = set(query_lower.split())
            desc_words = set(desc_lower.split())
            overlap = len(query_words & desc_words)

            if overlap > 0:
                score = overlap / max(len(query_words), 1)

            # Boost for exact phrase matches
            for word in query_words:
                if len(word) > 3 and word in desc_lower:
                    score += 0.2

            scores[name] = min(score, 1.0)

        if scores:
            best_agent = max(scores, key=scores.get)
            return {
                "agent": best_agent,
                "confidence": scores[best_agent],
                "all_scores": scores,
            }

        # Fallback to first agent
        return {
            "agent": next(iter(agents.keys())) if agents else None,
            "confidence": 0.0,
            "all_scores": scores,
        }


class LLMClassifier(AgentClassifier):
    """LLM-based classifier for intelligent routing."""

    def __init__(self, llm: Any, temperature: float = 0.0):
        self.llm = llm
        self.temperature = temperature

    async def classify(
        self,
        query: str,
        agents: dict[str, str],
        context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Use LLM to classify query to best agent."""
        if not self.llm:
            # Fallback to keyword classifier
            fallback = KeywordClassifier()
            return await fallback.classify(query, agents, context)

        # Build agent list for prompt
        agent_list = "\n".join([
            f"- {name}: {desc}" for name, desc in agents.items()
        ])

        # Build context summary if available
        context_summary = ""
        if context:
            recent = context[-3:]  # Last 3 turns
            context_summary = "\n".join([
                f"User: {c.get('query', '')}\nAgent: {c.get('agent', '')}"
                for c in recent
            ])
            context_summary = f"\nRecent conversation:\n{context_summary}\n"

        prompt = f"""You are a query router. Select the best agent to handle the user's query.

Available agents:
{agent_list}
{context_summary}
User query: {query}

Respond with ONLY the agent name (exactly as listed above) that best handles this query.
Agent name:"""

        try:
            if hasattr(self.llm, "ainvoke"):
                response = await self.llm.ainvoke(prompt)
                agent_name = response.content.strip() if hasattr(response, "content") else str(response).strip()
            elif hasattr(self.llm, "invoke"):
                response = self.llm.invoke(prompt)
                agent_name = response.content.strip() if hasattr(response, "content") else str(response).strip()
            else:
                raise ValueError("LLM must have invoke or ainvoke method")

            # Validate agent name
            if agent_name in agents:
                return {"agent": agent_name, "confidence": 0.9}

            # Try fuzzy match
            agent_name_lower = agent_name.lower()
            for name in agents:
                if name.lower() in agent_name_lower or agent_name_lower in name.lower():
                    return {"agent": name, "confidence": 0.7}

            # Fallback to keyword
            fallback = KeywordClassifier()
            return await fallback.classify(query, agents, context)

        except Exception as e:
            logger.warning(f"LLM classification failed: {e}, falling back to keyword")
            fallback = KeywordClassifier()
            return await fallback.classify(query, agents, context)


class LLMGatewayClassifier(AgentClassifier):
    """
    LLM Gateway-based classifier for intelligent routing.

    Uses your existing LLMGatewayClient with OAuth authentication,
    so you don't need direct Anthropic/OpenAI API keys.

    Usage:
        from agentorchestrator.services.llm_gateway import LLMGatewayClient
        from agentorchestrator.integrations import AgentSquadBridge, LLMGatewayClassifier

        # Create LLM Gateway client (uses your existing OAuth config)
        llm_client = LLMGatewayClient(
            server_url=Config.LLM_SERVER_URL,
            oauth_endpoint=Config.LLM_OAUTH_ENDPOINT,
            client_id=Config.LLM_CLIENT_ID,
            client_secret=Config.LLM_CLIENT_SECRET,
            model_name=Config.LLM_MODEL_NAME,
        )

        # Use with Agent Squad bridge
        bridge = AgentSquadBridge(
            classifier=LLMGatewayClassifier(llm_client),
        )
    """

    def __init__(self, llm_gateway_client: Any):
        """
        Initialize with LLMGatewayClient.

        Args:
            llm_gateway_client: Instance of LLMGatewayClient from
                agentorchestrator.services.llm_gateway
        """
        self.client = llm_gateway_client

    async def classify(
        self,
        query: str,
        agents: dict[str, str],
        context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Use LLM Gateway to classify query to best agent."""
        if not self.client:
            fallback = KeywordClassifier()
            return await fallback.classify(query, agents, context)

        # Build agent list for prompt
        agent_list = "\n".join([
            f"- {name}: {desc}" for name, desc in agents.items()
        ])

        # Build context summary if available
        context_summary = ""
        if context:
            recent = context[-3:]  # Last 3 turns
            context_summary = "\n".join([
                f"User: {c.get('query', '')}\nAgent: {c.get('agent', '')}"
                for c in recent
            ])
            context_summary = f"\nRecent conversation:\n{context_summary}\n"

        prompt = f"""You are a query router. Select the best agent to handle the user's query.

Available agents:
{agent_list}
{context_summary}
User query: {query}

Respond with ONLY the agent name (exactly as listed above) that best handles this query.
Agent name:"""

        try:
            # Use LLMGatewayClient's generate_async method
            response = await self.client.generate_async(prompt)
            agent_name = response.strip()

            # Validate agent name
            if agent_name in agents:
                return {"agent": agent_name, "confidence": 0.9}

            # Try fuzzy match
            agent_name_lower = agent_name.lower()
            for name in agents:
                if name.lower() in agent_name_lower or agent_name_lower in name.lower():
                    return {"agent": name, "confidence": 0.7}

            # Fallback to keyword
            fallback = KeywordClassifier()
            return await fallback.classify(query, agents, context)

        except Exception as e:
            logger.warning(f"LLM Gateway classification failed: {e}, falling back to keyword")
            fallback = KeywordClassifier()
            return await fallback.classify(query, agents, context)


@dataclass
class ResponseHandler:
    """Handles response processing strategies."""

    strategy: ResponseStrategy = ResponseStrategy.SUMMARIZE
    max_tokens: int = 2000
    extraction_model: type | None = None  # Pydantic model for EXTRACT strategy
    summarizer: Callable[[str], str] | None = None  # Custom summarizer

    async def process(
        self,
        response: str,
        agent_name: str,
        llm: Any | None = None,
    ) -> dict[str, Any]:
        """
        Process an agent response according to the configured strategy.

        Returns:
            Dict with 'processed' (handled content) and 'raw' (original) keys
        """
        result = {
            "raw": response,
            "processed": response,
            "agent": agent_name,
            "strategy": self.strategy.value,
            "truncated": False,
        }

        if self.strategy == ResponseStrategy.RAW:
            return result

        if self.strategy == ResponseStrategy.TRUNCATE:
            # Simple truncation (rough estimate: 1 token ≈ 4 chars)
            max_chars = self.max_tokens * 4
            if len(response) > max_chars:
                result["processed"] = response[:max_chars] + "..."
                result["truncated"] = True
            return result

        if self.strategy == ResponseStrategy.SUMMARIZE:
            if self.summarizer:
                result["processed"] = await self._async_call(
                    self.summarizer, response
                )
            elif llm:
                result["processed"] = await self._summarize_with_llm(
                    response, agent_name, llm
                )
            else:
                # Fallback to truncation if no summarizer available
                max_chars = self.max_tokens * 4
                if len(response) > max_chars:
                    result["processed"] = response[:max_chars] + "..."
                    result["truncated"] = True
            return result

        if self.strategy == ResponseStrategy.EXTRACT:
            if self.extraction_model and llm:
                result["processed"] = await self._extract_with_model(
                    response, llm
                )
            return result

        return result

    async def _async_call(self, func: Callable, *args) -> Any:
        """Call a function, handling both sync and async."""
        if asyncio.iscoroutinefunction(func):
            return await func(*args)
        return func(*args)

    async def _summarize_with_llm(
        self,
        content: str,
        agent_name: str,
        llm: Any,
    ) -> str:
        """Summarize content using an LLM."""
        prompt = f"""Summarize the following content from {agent_name} in a concise manner.
Focus on key facts, figures, and actionable insights.
Keep the summary under {self.max_tokens} tokens.

Content:
{content}

Summary:"""

        try:
            if hasattr(llm, "ainvoke"):
                response = await llm.ainvoke(prompt)
                return response.content if hasattr(response, "content") else str(response)
            elif hasattr(llm, "invoke"):
                response = llm.invoke(prompt)
                return response.content if hasattr(response, "content") else str(response)
            else:
                # Fallback - just truncate
                max_chars = self.max_tokens * 4
                return content[:max_chars] if len(content) > max_chars else content
        except Exception as e:
            logger.warning(f"Summarization failed: {e}, falling back to truncation")
            max_chars = self.max_tokens * 4
            return content[:max_chars] if len(content) > max_chars else content

    async def _extract_with_model(self, content: str, llm: Any) -> dict[str, Any]:
        """Extract structured data using a Pydantic model."""
        if not self.extraction_model:
            return {"content": content}

        try:
            # Use LangChain's with_structured_output if available
            if hasattr(llm, "with_structured_output"):
                structured_llm = llm.with_structured_output(self.extraction_model)
                result = await structured_llm.ainvoke(
                    f"Extract the following information from this content:\n\n{content}"
                )
                return result.model_dump() if hasattr(result, "model_dump") else result
        except Exception as e:
            logger.warning(f"Extraction failed: {e}")

        return {"content": content}


# =============================================================================
# AGENT ADAPTERS
# =============================================================================


class AOAgentAdapter:
    """
    Adapts an AgentOrchestrator BaseAgent to work with Agent Squad.

    This allows your existing AO agents to be used within Agent Squad's
    routing and supervisor systems.

    Usage:
        from agentorchestrator.integrations import AOAgentAdapter

        # Wrap an AO agent
        adapted = AOAgentAdapter(
            agent=MySECAgent(),
            name="SEC Filing Expert",
            description="Retrieves and analyzes SEC filings (10-K, 10-Q, 8-K)"
        )

        # Use with Agent Squad
        squad.add_agent(adapted)
    """

    def __init__(
        self,
        agent: BaseAgent,
        name: str | None = None,
        description: str = "",
        response_handler: ResponseHandler | None = None,
    ):
        self.agent = agent
        self.name = name or getattr(agent, "_ao_name", agent.__class__.__name__)
        self.description = description
        self.response_handler = response_handler or ResponseHandler()

        # Track for Agent Squad compatibility
        self._conversation_history: list[dict[str, Any]] = []

    async def process_request(
        self,
        query: str,
        user_id: str = "default",
        session_id: str = "default",
        **kwargs,
    ) -> dict[str, Any]:
        """
        Process a request using the wrapped AO agent.

        This method signature matches Agent Squad's agent interface.
        """
        import time
        start = time.perf_counter()

        try:
            # Initialize if needed
            if not self.agent._initialized:
                await self.agent.initialize()

            # Call the AO agent
            result: AgentResult = await self.agent.fetch(query, **kwargs)

            duration_ms = (time.perf_counter() - start) * 1000

            # Convert to Agent Squad format
            output = {
                "output": result.data,
                "success": result.success,
                "error": result.error,
                "metadata": {
                    "agent_name": self.name,
                    "source": result.source,
                    "duration_ms": duration_ms,
                    "citations": [c.__dict__ if hasattr(c, "__dict__") else c
                                  for c in result.citations],
                    "ao_metadata": result.metadata,
                },
            }

            # Store in conversation history
            self._conversation_history.append({
                "query": query,
                "response": output,
                "timestamp": datetime.utcnow().isoformat(),
            })

            return output

        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            return {
                "output": None,
                "success": False,
                "error": str(e),
                "metadata": {"agent_name": self.name},
            }

    def get_conversation_history(self) -> list[dict[str, Any]]:
        """Get conversation history for this agent."""
        return self._conversation_history.copy()

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history.clear()


# =============================================================================
# AGENT SQUAD BRIDGE
# =============================================================================


class AgentSquadBridge:
    """
    Bridge between AgentOrchestrator and Agent Squad.

    Provides:
    - Intelligent routing using pluggable classifiers (or Agent Squad's if installed)
    - Broadcast execution to multiple agents
    - Pluggable conversation memory (Redis, PostgreSQL, in-memory, etc.)
    - Response aggregation and processing

    Usage:
        from agentorchestrator.integrations import (
            AgentSquadBridge,
            AgentSquadConfig,
            LLMClassifier,
            InMemoryStore,
        )

        # Create bridge with pluggable components
        bridge = AgentSquadBridge(
            config=AgentSquadConfig(
                default_strategy=RoutingStrategy.CLASSIFIER,
                response_strategy=ResponseStrategy.SUMMARIZE,
            ),
            classifier=LLMClassifier(llm=my_llm),  # Pluggable classifier
            memory_store=InMemoryStore(),          # Pluggable memory
            llm=my_llm,
        )

        # Add AO agents
        bridge.add_ao_agent(sec_agent, description="SEC filing expert")
        bridge.add_ao_agent(capiq_agent, description="Financial data analyst")

        # Route a query (uses classifier to pick best agent)
        result = await bridge.route("What was Apple's revenue last quarter?")

        # Or broadcast to all agents
        results = await bridge.broadcast("Analyze Apple's financial health")

    With Redis memory (example):
        from agentorchestrator.integrations import ConversationMemoryStore

        class RedisMemoryStore(ConversationMemoryStore):
            def __init__(self, redis_client):
                self.redis = redis_client

            async def store(self, session_id, user_id, entry):
                key = f"conv:{session_id}:{user_id}"
                await self.redis.rpush(key, json.dumps(entry))
                await self.redis.ltrim(key, -100, -1)  # Keep last 100

            async def retrieve(self, session_id, user_id, limit=10):
                key = f"conv:{session_id}:{user_id}"
                entries = await self.redis.lrange(key, -limit, -1)
                return [json.loads(e) for e in entries]

        bridge = AgentSquadBridge(memory_store=RedisMemoryStore(redis))
    """

    def __init__(
        self,
        config: AgentSquadConfig | None = None,
        llm: Any | None = None,
        classifier: AgentClassifier | None = None,
        memory_store: ConversationMemoryStore | None = None,
    ):
        self.config = config or AgentSquadConfig()
        self.llm = llm
        self._agents: dict[str, AOAgentAdapter] = {}
        self._squad = None  # Lazy-loaded Agent Squad instance

        # Pluggable classifier - default to LLM if provided, else keyword
        if classifier:
            self._classifier = classifier
        elif llm:
            self._classifier = LLMClassifier(llm=llm)
        else:
            self._classifier = KeywordClassifier()

        # Pluggable memory store - default to in-memory
        self._memory_store = memory_store or InMemoryStore(
            max_entries=self.config.memory_window * 10
        )

    def add_ao_agent(
        self,
        agent: BaseAgent,
        name: str | None = None,
        description: str = "",
    ) -> "AgentSquadBridge":
        """
        Add an AgentOrchestrator agent to the bridge.

        Args:
            agent: BaseAgent instance
            name: Display name for routing
            description: Description for classifier routing

        Returns:
            Self for chaining
        """
        adapter = AOAgentAdapter(
            agent=agent,
            name=name,
            description=description,
            response_handler=ResponseHandler(
                strategy=self.config.response_strategy,
                max_tokens=self.config.max_tokens_per_agent,
            ),
        )
        self._agents[adapter.name] = adapter

        # Invalidate cached squad
        self._squad = None

        return self

    def add_agents(
        self,
        agents: dict[str, BaseAgent],
        descriptions: dict[str, str] | None = None,
    ) -> "AgentSquadBridge":
        """
        Add multiple agents at once.

        Args:
            agents: Dict of name -> agent
            descriptions: Optional dict of name -> description
        """
        descriptions = descriptions or {}
        for name, agent in agents.items():
            self.add_ao_agent(
                agent=agent,
                name=name,
                description=descriptions.get(name, ""),
            )
        return self

    @property
    def agents(self) -> dict[str, AOAgentAdapter]:
        """Get all registered agents."""
        return self._agents.copy()

    def _get_or_create_squad(self):
        """Lazy-load Agent Squad instance."""
        if self._squad is not None:
            return self._squad

        try:
            from agent_squad import AgentSquad
            from agent_squad.classifiers import BedrockClassifier

            # Create squad with classifier
            classifier = BedrockClassifier(
                model_id=self.config.classifier_model,
            )
            self._squad = AgentSquad(classifier=classifier)

            # Add adapted agents
            for adapter in self._agents.values():
                # Agent Squad expects a specific interface
                self._squad.add_agent(adapter)

            return self._squad

        except ImportError:
            logger.warning(
                "agent-squad package not installed. "
                "Install with: pip install 'agent-squad[anthropic]'"
            )
            return None

    async def route(
        self,
        query: str,
        user_id: str = "default",
        session_id: str = "default",
        strategy: RoutingStrategy | None = None,
    ) -> AgentResult:
        """
        Route a query to the best agent(s) based on strategy.

        Args:
            query: User query
            user_id: User identifier for context
            session_id: Session identifier for context
            strategy: Override default routing strategy

        Returns:
            AgentResult with response data
        """
        strategy = strategy or self.config.default_strategy

        if strategy == RoutingStrategy.BROADCAST:
            return await self.broadcast(query, user_id, session_id)

        if strategy == RoutingStrategy.CLASSIFIER:
            return await self._route_with_classifier(query, user_id, session_id)

        if strategy == RoutingStrategy.ROUND_ROBIN:
            return await self._route_round_robin(query, user_id, session_id)

        if strategy == RoutingStrategy.SUPERVISOR:
            raise ValueError(
                "SUPERVISOR strategy requires SupervisorAgent. "
                "Use SupervisorAgent class directly."
            )

        # Default to first agent
        if self._agents:
            first_agent = next(iter(self._agents.values()))
            result = await first_agent.process_request(query, user_id, session_id)
            return self._to_agent_result(result, query)

        return AgentResult(
            data=None,
            source="agent_squad_bridge",
            query=query,
            error="No agents registered",
        )

    async def _route_with_classifier(
        self,
        query: str,
        user_id: str,
        session_id: str,
    ) -> AgentResult:
        """Route using pluggable classifier (or Agent Squad's if installed)."""
        # Try Agent Squad's native routing first if installed
        squad = self._get_or_create_squad()

        if squad:
            try:
                response = await squad.route_request(
                    query, user_id, session_id
                )
                result = AgentResult(
                    data=response.output if hasattr(response, "output") else response,
                    source=f"squad:{getattr(response, 'agent_name', 'unknown')}",
                    query=query,
                    metadata={
                        "routed_to": getattr(response, "agent_name", None),
                        "confidence": getattr(response, "confidence", None),
                        "strategy": "agent_squad_native",
                    },
                )

                # Store in memory
                await self._store_conversation(
                    session_id, user_id, query, result
                )
                return result

            except Exception as e:
                logger.warning(f"Agent Squad routing failed: {e}, using pluggable classifier")

        # Use our pluggable classifier with conversation context
        context = await self._memory_store.retrieve(
            session_id, user_id, limit=self.config.memory_window
        )

        # Build agent descriptions dict
        agent_descriptions = {
            name: adapter.description
            for name, adapter in self._agents.items()
        }

        # Classify using pluggable classifier
        classification = await self._classifier.classify(
            query=query,
            agents=agent_descriptions,
            context=context,
        )

        best_agent = classification.get("agent")
        confidence = classification.get("confidence", 0.0)

        if best_agent and best_agent in self._agents:
            adapter = self._agents[best_agent]
            response = await adapter.process_request(query, user_id, session_id)
            result = self._to_agent_result(response, query)
            result.metadata["strategy"] = "pluggable_classifier"
            result.metadata["routed_to"] = best_agent
            result.metadata["confidence"] = confidence

            # Store in memory
            await self._store_conversation(
                session_id, user_id, query, result, agent_name=best_agent
            )
            return result

        # Final fallback
        return await self._route_heuristic(query, user_id, session_id)

    async def _store_conversation(
        self,
        session_id: str,
        user_id: str,
        query: str,
        result: AgentResult,
        agent_name: str | None = None,
    ) -> None:
        """Store conversation in memory store."""
        if not self.config.enable_memory:
            return

        entry = {
            "query": query,
            "agent": agent_name or result.source,
            "response_summary": str(result.data)[:500] if result.data else None,
            "success": result.success,
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            await self._memory_store.store(session_id, user_id, entry)
        except Exception as e:
            logger.warning(f"Failed to store conversation: {e}")

    async def _route_heuristic(
        self,
        query: str,
        user_id: str,
        session_id: str,
    ) -> AgentResult:
        """Simple keyword-based routing fallback."""
        query_lower = query.lower()

        # Score each agent based on description keyword matches
        scores: dict[str, int] = {}
        for name, adapter in self._agents.items():
            score = 0
            desc_lower = adapter.description.lower()

            # Simple keyword matching
            for word in query_lower.split():
                if word in desc_lower:
                    score += 1

            scores[name] = score

        # Pick highest scoring agent
        if scores:
            best_agent = max(scores, key=scores.get)
            adapter = self._agents[best_agent]
            result = await adapter.process_request(query, user_id, session_id)
            agent_result = self._to_agent_result(result, query)
            agent_result.metadata["strategy"] = "heuristic"
            agent_result.metadata["routed_to"] = best_agent
            return agent_result

        return AgentResult(
            data=None,
            source="agent_squad_bridge",
            query=query,
            error="No suitable agent found",
        )

    async def _route_round_robin(
        self,
        query: str,
        user_id: str,
        session_id: str,
    ) -> AgentResult:
        """Distribute queries across agents in round-robin fashion."""
        if not self._agents:
            return AgentResult(
                data=None,
                source="agent_squad_bridge",
                query=query,
                error="No agents registered",
            )

        # Track round-robin state
        if not hasattr(self, "_rr_index"):
            self._rr_index = 0

        agent_names = list(self._agents.keys())
        agent_name = agent_names[self._rr_index % len(agent_names)]
        self._rr_index += 1

        adapter = self._agents[agent_name]
        result = await adapter.process_request(query, user_id, session_id)
        agent_result = self._to_agent_result(result, query)
        agent_result.metadata["strategy"] = "round_robin"
        agent_result.metadata["routed_to"] = agent_name
        return agent_result

    async def broadcast(
        self,
        query: str,
        user_id: str = "default",
        session_id: str = "default",
    ) -> AgentResult:
        """
        Broadcast query to ALL agents and aggregate results.

        Returns combined results from all agents, with per-agent
        response processing applied.
        """
        import time
        start = time.perf_counter()

        if not self._agents:
            return AgentResult(
                data={},
                source="agent_squad_bridge",
                query=query,
                error="No agents registered",
            )

        # Execute all agents in parallel
        tasks = [
            adapter.process_request(query, user_id, session_id)
            for adapter in self._agents.values()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        combined_data = {}
        all_citations = []
        errors = []
        agent_status = {}

        for adapter, result in zip(self._agents.values(), results):
            agent_name = adapter.name

            if isinstance(result, Exception):
                errors.append(f"{agent_name}: {result}")
                agent_status[agent_name] = {"success": False, "error": str(result)}
            elif result.get("success", False):
                # Process response
                processed = await adapter.response_handler.process(
                    str(result.get("output", "")),
                    agent_name,
                    self.llm,
                )
                combined_data[agent_name] = processed["processed"]

                # Collect citations
                citations = result.get("metadata", {}).get("citations", [])
                all_citations.extend(citations)

                agent_status[agent_name] = {
                    "success": True,
                    "truncated": processed.get("truncated", False),
                }
            else:
                errors.append(f"{agent_name}: {result.get('error', 'Unknown error')}")
                agent_status[agent_name] = {
                    "success": False,
                    "error": result.get("error"),
                }

        duration_ms = (time.perf_counter() - start) * 1000

        return AgentResult(
            data=combined_data,
            source="agent_squad_bridge",
            query=query,
            duration_ms=duration_ms,
            error="; ".join(errors) if errors else None,
            citations=all_citations,
            metadata={
                "strategy": "broadcast",
                "agent_count": len(self._agents),
                "success_count": sum(1 for s in agent_status.values() if s["success"]),
                "agent_status": agent_status,
            },
        )

    def _to_agent_result(self, result: dict[str, Any], query: str) -> AgentResult:
        """Convert Agent Squad result format to AgentResult."""
        return AgentResult(
            data=result.get("output"),
            source=result.get("metadata", {}).get("agent_name", "unknown"),
            query=query,
            error=result.get("error"),
            duration_ms=result.get("metadata", {}).get("duration_ms", 0),
            citations=result.get("metadata", {}).get("citations", []),
            metadata=result.get("metadata", {}),
        )

    def get_conversation_memory(self) -> list[dict[str, Any]]:
        """Get aggregated conversation memory from all agents."""
        memory = []
        for adapter in self._agents.values():
            memory.extend(adapter.get_conversation_history())
        return sorted(memory, key=lambda x: x.get("timestamp", ""))

    def clear_memory(self) -> None:
        """Clear conversation memory for all agents."""
        for adapter in self._agents.values():
            adapter.clear_history()


# =============================================================================
# SUPERVISOR AGENT
# =============================================================================


class SupervisorAgent(BaseAgent):
    """
    Supervisor agent that coordinates multiple team agents.

    Implements Agent Squad's supervisor pattern where a lead agent
    dynamically decides which team agents to invoke based on the query.

    Features:
    - Dynamic agent selection by lead agent
    - Parallel execution of selected agents
    - Response aggregation and synthesis
    - Conversation context management

    Usage:
        from agentorchestrator.integrations import SupervisorAgent, SupervisorConfig

        supervisor = SupervisorAgent(
            team=[sec_agent, capiq_agent, news_agent],
            config=SupervisorConfig(
                lead_model="anthropic.claude-3-sonnet-20240229-v1:0",
                response_strategy=ResponseStrategy.SUMMARIZE,
            ),
            llm=my_llm,  # LangChain LLM for lead agent
        )

        result = await supervisor.fetch("What are the key risks for Apple?")
    """

    _ao_agent = True
    _ao_name = "supervisor"
    _ao_version = "1.0.0"

    def __init__(
        self,
        team: list[BaseAgent],
        config: SupervisorConfig | None = None,
        llm: Any | None = None,
        name: str = "supervisor",
        description: str = "Coordinates team of specialized agents",
    ):
        super().__init__()
        self._ao_name = name
        self.description = description
        self.config = config or SupervisorConfig()
        self.llm = llm

        # Wrap team agents
        self._team: dict[str, AOAgentAdapter] = {}
        for agent in team:
            adapter = AOAgentAdapter(
                agent=agent,
                response_handler=ResponseHandler(
                    strategy=self.config.response_strategy,
                    max_tokens=self.config.max_tokens_per_agent,
                ),
            )
            self._team[adapter.name] = adapter

        # Response handler for final synthesis
        self._response_handler = ResponseHandler(
            strategy=self.config.response_strategy,
            max_tokens=self.config.max_tokens_per_agent,
        )

        # Conversation tracking
        self._conversation_history: list[dict[str, Any]] = []

    @property
    def team(self) -> dict[str, AOAgentAdapter]:
        """Get team agents."""
        return self._team.copy()

    @property
    def team_names(self) -> list[str]:
        """Get list of team agent names."""
        return list(self._team.keys())

    def _build_system_prompt(self) -> str:
        """Build system prompt for lead agent with team descriptions."""
        team_list = "\n".join([
            f"- {name}: {adapter.description}"
            for name, adapter in self._team.items()
        ])

        return f"""You are a supervisor agent coordinating a team of specialized agents.

Your team members:
{team_list}

Your job is to:
1. Analyze the user's query
2. Decide which team member(s) should handle it
3. Delegate to appropriate agent(s)
4. Synthesize their responses into a coherent answer

To delegate to a team member, respond with JSON in this format:
{{"delegate": ["agent_name1", "agent_name2"], "instructions": "specific instructions"}}

If you can answer directly without delegation, respond normally.
If multiple agents are needed, list all of them - they will run in parallel.

{self.config.synthesis_prompt or ''}"""

    def _build_send_messages_tool(self) -> dict[str, Any]:
        """Build the send_messages tool definition for the lead agent."""
        return {
            "name": "send_messages",
            "description": "Send messages to team agents for processing",
            "input_schema": {
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "recipient": {
                                    "type": "string",
                                    "description": "Name of the team agent",
                                    "enum": list(self._team.keys()),
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Message/query to send to the agent",
                                },
                            },
                            "required": ["recipient", "content"],
                        },
                        "description": "List of messages to send to team agents",
                    },
                },
                "required": ["messages"],
            },
        }

    async def _execute_delegation(
        self,
        delegates: list[str],
        query: str,
        instructions: str | None = None,
    ) -> dict[str, Any]:
        """Execute delegation to team agents."""
        import time
        start = time.perf_counter()

        # Filter to valid team members
        valid_delegates = [d for d in delegates if d in self._team]

        if not valid_delegates:
            return {
                "results": {},
                "errors": ["No valid team members found for delegation"],
            }

        # Build query with instructions if provided
        full_query = query
        if instructions:
            full_query = f"{instructions}\n\nQuery: {query}"

        # Execute in parallel or sequentially
        if self.config.parallel_execution:
            tasks = [
                self._team[name].process_request(full_query)
                for name in valid_delegates
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = []
            for name in valid_delegates:
                try:
                    result = await self._team[name].process_request(full_query)
                    results.append(result)
                except Exception as e:
                    results.append(e)

        # Aggregate results
        aggregated = {}
        errors = []

        for name, result in zip(valid_delegates, results):
            if isinstance(result, Exception):
                if not self.config.continue_on_agent_failure:
                    raise result
                errors.append(f"{name}: {result}")
            elif result.get("success", False):
                # Process response
                processed = await self._response_handler.process(
                    str(result.get("output", "")),
                    name,
                    self.llm,
                )
                aggregated[name] = {
                    "output": processed["processed"],
                    "raw": processed["raw"] if self.config.response_strategy != ResponseStrategy.RAW else None,
                    "citations": result.get("metadata", {}).get("citations", []),
                }
            else:
                errors.append(f"{name}: {result.get('error', 'Unknown error')}")

        duration_ms = (time.perf_counter() - start) * 1000

        return {
            "results": aggregated,
            "errors": errors,
            "duration_ms": duration_ms,
            "delegated_to": valid_delegates,
        }

    async def _synthesize_responses(
        self,
        query: str,
        delegation_results: dict[str, Any],
    ) -> str:
        """Synthesize team responses into a final answer."""
        if not self.llm:
            # No LLM - just concatenate results
            parts = []
            for agent_name, result in delegation_results.get("results", {}).items():
                parts.append(f"**{agent_name}:**\n{result.get('output', 'No output')}")
            return "\n\n".join(parts)

        # Build synthesis prompt
        results_text = "\n\n".join([
            f"**{agent_name}:**\n{result.get('output', 'No output')}"
            for agent_name, result in delegation_results.get("results", {}).items()
        ])

        synthesis_prompt = f"""Based on the following team responses, synthesize a comprehensive answer to the user's query.

User Query: {query}

Team Responses:
{results_text}

{self.config.synthesis_prompt or 'Provide a clear, organized synthesis that combines insights from all relevant team members.'}

Synthesized Response:"""

        try:
            if hasattr(self.llm, "ainvoke"):
                response = await self.llm.ainvoke(synthesis_prompt)
                return response.content if hasattr(response, "content") else str(response)
            elif hasattr(self.llm, "invoke"):
                response = self.llm.invoke(synthesis_prompt)
                return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")

        # Fallback to concatenation
        return results_text

    async def _determine_delegation(self, query: str) -> tuple[list[str], str | None]:
        """Use lead agent to determine which team members to delegate to."""
        if not self.llm:
            # No LLM - delegate to all team members
            return list(self._team.keys()), None

        system_prompt = self._build_system_prompt()

        try:
            # Try to get structured delegation decision
            if hasattr(self.llm, "ainvoke"):
                response = await self.llm.ainvoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ])
                response_text = response.content if hasattr(response, "content") else str(response)
            elif hasattr(self.llm, "invoke"):
                response = self.llm.invoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ])
                response_text = response.content if hasattr(response, "content") else str(response)
            else:
                # Fallback - delegate to all
                return list(self._team.keys()), None

            # Parse delegation response
            import json
            import re

            # Try to extract JSON
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                try:
                    delegation = json.loads(json_match.group())
                    delegates = delegation.get("delegate", [])
                    instructions = delegation.get("instructions")
                    if delegates:
                        return delegates, instructions
                except json.JSONDecodeError:
                    pass

            # Fallback - check if any team names mentioned
            mentioned = [
                name for name in self._team.keys()
                if name.lower() in response_text.lower()
            ]
            if mentioned:
                return mentioned, None

            # Last resort - delegate to all
            return list(self._team.keys()), None

        except Exception as e:
            logger.warning(f"Delegation decision failed: {e}, delegating to all")
            return list(self._team.keys()), None

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Process a query through the supervisor pattern.

        1. Lead agent analyzes query and decides delegation
        2. Selected team agents process in parallel
        3. Lead agent synthesizes responses
        """
        import time
        start = time.perf_counter()

        try:
            # Step 1: Determine delegation
            delegates, instructions = await self._determine_delegation(query)

            # Step 2: Execute delegation
            delegation_results = await self._execute_delegation(
                delegates, query, instructions
            )

            # Step 3: Synthesize responses
            synthesized = await self._synthesize_responses(query, delegation_results)

            duration_ms = (time.perf_counter() - start) * 1000

            # Collect all citations
            all_citations = []
            for result in delegation_results.get("results", {}).values():
                all_citations.extend(result.get("citations", []))

            # Build result
            result = AgentResult(
                data={
                    "synthesis": synthesized,
                    "team_results": delegation_results.get("results", {}),
                },
                source=self._ao_name,
                query=query,
                duration_ms=duration_ms,
                citations=all_citations,
                error="; ".join(delegation_results.get("errors", [])) or None,
                metadata={
                    "delegated_to": delegation_results.get("delegated_to", []),
                    "team_count": len(self._team),
                    "delegation_instructions": instructions,
                    "strategy": "supervisor",
                },
            )

            # Store in history
            self._conversation_history.append({
                "query": query,
                "response": result.data,
                "delegates": delegation_results.get("delegated_to", []),
                "timestamp": datetime.utcnow().isoformat(),
            })

            return result

        except Exception as e:
            logger.error(f"Supervisor fetch failed: {e}")
            duration_ms = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=query,
                duration_ms=duration_ms,
                error=str(e),
            )

    async def coordinate(
        self,
        query: str,
        user_id: str = "default",
        session_id: str = "default",
    ) -> AgentResult:
        """
        Alias for fetch() with user/session tracking.

        This matches Agent Squad's SupervisorAgent interface.
        """
        return await self.fetch(
            query,
            user_id=user_id,
            session_id=session_id,
        )

    def get_conversation_history(self) -> list[dict[str, Any]]:
        """Get supervisor conversation history."""
        return self._conversation_history.copy()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def create_squad_from_agents(
    agents: dict[str, BaseAgent],
    descriptions: dict[str, str] | None = None,
    config: AgentSquadConfig | None = None,
    llm: Any | None = None,
) -> AgentSquadBridge:
    """
    Create an AgentSquadBridge from a dictionary of agents.

    Convenience function for quick setup.

    Usage:
        from agentorchestrator.integrations import create_squad_from_agents

        squad = create_squad_from_agents(
            agents={
                "sec": SECAgent(),
                "capiq": CapIQAgent(),
                "news": NewsAgent(),
            },
            descriptions={
                "sec": "SEC filing expert",
                "capiq": "Financial data analyst",
                "news": "News and media analyst",
            },
        )

        result = await squad.route("What was Apple's revenue?")
    """
    bridge = AgentSquadBridge(config=config, llm=llm)
    bridge.add_agents(agents, descriptions)
    return bridge
