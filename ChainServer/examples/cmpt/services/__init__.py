"""
CMPT Services

Modular, Pydantic-based services for the Client Meeting Prep Chain.

Services:
- ContextBuilder: Extracts firm info, temporal context, personas
- ContentPrioritization: Prioritizes sources, generates subqueries
- ResponseBuilder: Executes agents, builds final response
- LLMGateway: Enterprise LLM client with OAuth support
"""

from examples.cmpt.services.content_prioritization import ContentPrioritizationService
from examples.cmpt.services.context_builder import ContextBuilderService
from examples.cmpt.services.llm_gateway import (
    LLMGatewayClient,
    OAuthTokenManager,
    create_managed_client,
    get_default_llm_client,
    get_llm_client,
    init_default_llm_client,
    set_default_llm_client,
    timed_lru_cache,
)
from examples.cmpt.services.models import (
    AgentResult,
    ChainRequest,
    ChainRequestOverrides,
    ChainResponse,
    CompanyInfo,
    ContentPrioritizationInput,
    ContentPrioritizationOutput,
    ContextBuilderInput,
    ContextBuilderOutput,
    PersonaInfo,
    PrioritizedSource,
    ResponseBuilderInput,
    ResponseBuilderOutput,
    Subquery,
    TemporalContext,
)
from examples.cmpt.services.response_builder import ResponseBuilderService

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
