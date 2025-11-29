"""
FlowForge Services

Modular, Pydantic-based services for the Client Meeting Prep Chain.

Services:
- ContextBuilder: Extracts firm info, temporal context, personas
- ContentPrioritization: Prioritizes sources, generates subqueries
- ResponseBuilder: Executes agents, builds final response
- LLMGateway: Enterprise LLM client with OAuth support
"""

from flowforge.services.content_prioritization import ContentPrioritizationService
from flowforge.services.context_builder import ContextBuilderService
from flowforge.services.llm_gateway import (
    LLMGatewayClient,
    OAuthTokenManager,
    create_managed_client,
    get_default_llm_client,
    get_llm_client,
    init_default_llm_client,
    set_default_llm_client,
    timed_lru_cache,
)
from flowforge.services.models import (
    # Response Builder Models
    AgentResult,
    # Request/Response Models
    ChainRequest,
    ChainRequestOverrides,
    ChainResponse,
    # Context Builder Models
    CompanyInfo,
    ContentPrioritizationInput,
    ContentPrioritizationOutput,
    ContextBuilderInput,
    ContextBuilderOutput,
    PersonaInfo,
    # Content Prioritization Models
    PrioritizedSource,
    ResponseBuilderInput,
    ResponseBuilderOutput,
    Subquery,
    TemporalContext,
)
from flowforge.services.response_builder import ResponseBuilderService

__all__ = [
    # Models
    "ChainRequest",
    "ChainRequestOverrides",
    "ChainResponse",
    "CompanyInfo",
    "TemporalContext",
    "PersonaInfo",
    "ContextBuilderInput",
    "ContextBuilderOutput",
    "PrioritizedSource",
    "Subquery",
    "ContentPrioritizationInput",
    "ContentPrioritizationOutput",
    "AgentResult",
    "ResponseBuilderInput",
    "ResponseBuilderOutput",
    # Services
    "ContextBuilderService",
    "ContentPrioritizationService",
    "ResponseBuilderService",
    # LLM Gateway
    "LLMGatewayClient",
    "OAuthTokenManager",
    "get_llm_client",
    "get_default_llm_client",
    "set_default_llm_client",
    "init_default_llm_client",
    "create_managed_client",
    "timed_lru_cache",
]
