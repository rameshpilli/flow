"""
AgentOrchestrator Services Module

Core services for LLM integration, with optional CMPT example re-exports.

Usage:
    from agentorchestrator.services import LLMGatewayClient, get_llm_client
"""

# Core LLM services (always available)
from agentorchestrator.services.llm_gateway import (
    LLMGatewayClient,
    OAuthTokenManager,
    create_managed_client,
    get_default_llm_client,
    get_llm_client,
    init_default_llm_client,
    set_default_llm_client,
    timed_lru_cache,
)

# Optional: Re-export CMPT models/services if available
try:
    from cmpt.services import (
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
    )
    _CMPT_AVAILABLE = True
except ImportError:
    _CMPT_AVAILABLE = False

# Core exports (always available)
__all__ = [
    "LLMGatewayClient",
    "OAuthTokenManager",
    "get_llm_client",
    "get_default_llm_client",
    "set_default_llm_client",
    "init_default_llm_client",
    "create_managed_client",
    "timed_lru_cache",
]

# Add CMPT exports if available
if _CMPT_AVAILABLE:
    __all__.extend([
        "ChainRequest", "ChainRequestOverrides", "ChainResponse",
        "CompanyInfo", "TemporalContext", "PersonaInfo",
        "ContextBuilderInput", "ContextBuilderOutput",
        "PrioritizedSource", "Subquery",
        "ContentPrioritizationInput", "ContentPrioritizationOutput",
        "AgentResult", "ResponseBuilderInput", "ResponseBuilderOutput",
        "ContextBuilderService", "ContentPrioritizationService", "ResponseBuilderService",
    ])
