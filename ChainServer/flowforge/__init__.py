"""
FlowForge: A DAG-based Chain Orchestration Framework

Simple, decorator-driven chain orchestration with automatic dependency resolution.

Quick Start:
    from flowforge import FlowForge

    forge = FlowForge(name="my_app")

    @forge.step(name="hello")
    async def hello(ctx):
        return {"message": "Hello!"}

    @forge.chain(name="hello_chain")
    class HelloChain:
        steps = ["hello"]

    result = await forge.launch("hello_chain", {})

For middleware, testing, and advanced features, import from submodules:
    from flowforge.middleware import CacheMiddleware, LoggerMiddleware
    from flowforge.testing import IsolatedForge, MockAgent
    from flowforge.utils import CircuitBreaker, configure_logging
"""

# =============================================================================
# CORE - The essentials (what 90% of users need)
# =============================================================================

# =============================================================================
# CHAINS - Pre-built chains
# =============================================================================
from flowforge.chains import CMPTChain

# Configuration
from flowforge.config import Config, get_config
from flowforge.core.context import ChainContext
from flowforge.core.forge import Context, FlowForge

# =============================================================================
# MIDDLEWARE - Import from submodule for full list
# =============================================================================
from flowforge.middleware.base import Middleware
from flowforge.middleware.cache import CacheMiddleware
from flowforge.middleware.logger import LoggerMiddleware
from flowforge.middleware.summarizer import (
    SummarizerMiddleware,
    create_anthropic_summarizer,
    create_gateway_summarizer,
    create_openai_summarizer,
)
from flowforge.middleware.token_manager import TokenManagerMiddleware

# =============================================================================
# TESTING - For user tests
# =============================================================================
from flowforge.testing import (
    IsolatedForge,
    MockAgent,
    create_test_context,
)

# =============================================================================
# UTILITIES - Common helpers
# =============================================================================
from flowforge.utils import (
    CircuitBreaker,
    CircuitBreakerConfig,
    configure_logging,
    get_logger,
)

__version__ = "0.1.0"

# Focused public API (~30 exports instead of 75+)
__all__ = [
    # Core (essential)
    "FlowForge",
    "Context",
    "ChainContext",
    # Config
    "Config",
    "get_config",
    # Middleware (common)
    "Middleware",
    "CacheMiddleware",
    "LoggerMiddleware",
    "SummarizerMiddleware",
    "TokenManagerMiddleware",
    "create_openai_summarizer",
    "create_anthropic_summarizer",
    "create_gateway_summarizer",
    # Testing (common)
    "IsolatedForge",
    "MockAgent",
    "create_test_context",
    # Utilities (common)
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "configure_logging",
    "get_logger",
    # Pre-built chains
    "CMPTChain",
]


# =============================================================================
# BACKWARD COMPATIBILITY - Lazy imports for deprecated top-level exports
# =============================================================================

def __getattr__(name: str):
    """Lazy import for backward compatibility with deprecated exports."""

    # Registries (use forge.step_registry, forge.agent_registry instead)
    if name in ("AgentRegistry", "StepRegistry", "ChainRegistry",
                "get_agent_registry", "get_step_registry", "get_chain_registry",
                "create_isolated_registries", "reset_global_registries"):
        from flowforge.core import registry
        return getattr(registry, name)

    # Legacy decorators (use @forge.step, @forge.agent, @forge.chain instead)
    if name in ("agent", "step", "chain", "middleware"):
        from flowforge.core import decorators
        return getattr(decorators, name)

    # Forge factory functions
    if name in ("get_forge", "set_forge", "Definitions"):
        from flowforge.core import forge
        return getattr(forge, name)

    # Config extras
    if name in ("set_config", "reload_config"):
        from flowforge import config
        return getattr(config, name)

    # Summarizer extras
    if name in ("LangChainSummarizer", "SummarizationStrategy", "DOMAIN_PROMPTS",
                "create_domain_aware_middleware"):
        from flowforge.middleware import summarizer
        return getattr(summarizer, name)

    # Resources
    if name in ("Resource", "ResourceManager", "ResourceScope",
                "get_resource_manager", "reset_resource_manager"):
        from flowforge.core import resources
        return getattr(resources, name)

    # Services
    if name in ("ChainRequest", "ChainRequestOverrides", "ChainResponse",
                "ContextBuilderService", "ContentPrioritizationService",
                "ResponseBuilderService", "LLMGatewayClient",
                "get_llm_client", "create_managed_client"):
        from flowforge import services
        return getattr(services, name)

    # Testing extras
    if name in ("MockMiddleware", "mock_step", "mock_chain",
                "assert_step_completed", "assert_chain_valid"):
        from flowforge import testing
        return getattr(testing, name)

    # Utility extras
    if name in ("timed", "async_timed", "retry", "async_retry", "RetryPolicy",
                "CircuitBreakerError", "get_circuit_breaker",
                "LogContext", "ChainLogger",
                "configure_tracing", "get_tracer", "trace_span", "ChainTracer"):
        from flowforge import utils
        return getattr(utils, name)

    # CMPT extras
    if name == "create_cmpt_chain":
        from flowforge import chains
        return getattr(chains, name)

    raise AttributeError(f"module 'flowforge' has no attribute '{name}'")
