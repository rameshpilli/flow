"""
AgentOrchestrator Services Module (CMPT example exports)

These classes are provided as a convenience bridge to the CMPT example implementation.
They are not part of the minimal core; if the CMPT example code is not present, imports
will fail with a clear error so you can vendor your own services instead.

Usage (when CMPT example is available):
    from agentorchestrator.services import ChainRequest, ContextBuilderService
"""

try:
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
except ImportError as exc:  # pragma: no cover - executed only when example is absent
    raise ImportError(
        "The CMPT example services are not available. "
        "These re-exports rely on examples/cmpt/services for illustrative purposes. "
        "If you need production services, copy or implement your own instead of importing "
        "agentorchestrator.services."
    ) from exc

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
