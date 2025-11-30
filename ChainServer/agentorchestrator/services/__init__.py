"""
AgentOrchestrator Services Module

Re-exports CMPT services for backward compatibility.
The actual implementations live in examples/cmpt/services/.

Usage:
    from agentorchestrator.services import ChainRequest, ContextBuilderService
"""

# Re-export from examples.cmpt.services for backward compatibility
from examples.cmpt.services import (
    # Models
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
    # Services
    ContentPrioritizationService,
    ContextBuilderService,
    ResponseBuilderService,
    # LLM Gateway
    LLMGatewayClient,
    OAuthTokenManager,
    create_managed_client,
    get_default_llm_client,
    get_llm_client,
    init_default_llm_client,
    set_default_llm_client,
    timed_lru_cache,
)

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
