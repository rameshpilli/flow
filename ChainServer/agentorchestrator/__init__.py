"""
AgentOrchestrator: A DAG-based Chain Orchestration Framework

Simple, decorator-driven chain orchestration with automatic dependency resolution.

Quick Start:
    from agentorchestrator import AgentOrchestrator

    ao = AgentOrchestrator(name="my_app")

    @ao.step(name="hello")
    async def hello(ctx):
        return {"message": "Hello!"}

    @ao.chain(name="hello_chain")
    class HelloChain:
        steps = ["hello"]

    result = await ao.launch("hello_chain", {})

For middleware, testing, and advanced features, import from submodules:
    from agentorchestrator.middleware import CacheMiddleware, LoggerMiddleware
    from agentorchestrator.testing import IsolatedOrchestrator, MockAgent
    from agentorchestrator.utils import CircuitBreaker, configure_logging
"""

# =============================================================================
# CORE - The essentials (what 90% of users need)
# =============================================================================

# Configuration
from agentorchestrator.config import Config, get_config
from agentorchestrator.core.context import ChainContext
from agentorchestrator.core.orchestrator import Context, AgentOrchestrator

# =============================================================================
# MIDDLEWARE - Import from submodule for full list
# =============================================================================
from agentorchestrator.middleware.base import Middleware
from agentorchestrator.middleware.cache import CacheMiddleware
from agentorchestrator.middleware.logger import LoggerMiddleware
from agentorchestrator.middleware.summarizer import (
    SummarizerMiddleware,
    create_anthropic_summarizer,
    create_gateway_summarizer,
    create_openai_summarizer,
)
from agentorchestrator.middleware.token_manager import TokenManagerMiddleware

# =============================================================================
# TESTING - For user tests
# =============================================================================
from agentorchestrator.testing import (
    IsolatedOrchestrator,
    MockAgent,
    create_test_context,
)

# =============================================================================
# UTILITIES - Common helpers
# =============================================================================
from agentorchestrator.utils import (
    CircuitBreaker,
    CircuitBreakerConfig,
    configure_logging,
    get_logger,
)

# =============================================================================
# LLM - LCEL chain builders (optional, requires langchain-core)
# =============================================================================
# Import lazily to avoid requiring langchain-core for all users
# Use: from agentorchestrator.llm import create_extraction_chain

__version__ = "0.1.0"

# Focused public API (~30 exports instead of 75+)
__all__ = [
    # Core (essential)
    "AgentOrchestrator",
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
    "IsolatedOrchestrator",
    "MockAgent",
    "create_test_context",
    # Utilities (common)
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "configure_logging",
    "get_logger",
]


# =============================================================================
# BACKWARD COMPATIBILITY - Lazy imports for deprecated top-level exports
# =============================================================================

def __getattr__(name: str):
    """Lazy import for backward compatibility with deprecated exports."""

    # Registries (use ao.step_registry, ao.agent_registry instead)
    if name in ("AgentRegistry", "StepRegistry", "ChainRegistry",
                "get_agent_registry", "get_step_registry", "get_chain_registry",
                "create_isolated_registries", "reset_global_registries"):
        from agentorchestrator.core import registry
        return getattr(registry, name)

    # Legacy decorators (use @ao.step, @ao.agent, @ao.chain instead)
    if name in ("agent", "step", "chain", "middleware"):
        from agentorchestrator.core import decorators
        return getattr(decorators, name)

    # Orchestrator factory functions
    if name in ("get_orchestrator", "set_orchestrator", "Definitions"):
        from agentorchestrator.core import orchestrator
        return getattr(orchestrator, name)

    # Config extras
    if name in ("set_config", "reload_config"):
        from agentorchestrator import config
        return getattr(config, name)

    # Summarizer extras
    if name in ("LangChainSummarizer", "SummarizationStrategy", "DOMAIN_PROMPTS",
                "create_domain_aware_middleware"):
        from agentorchestrator.middleware import summarizer
        return getattr(summarizer, name)

    # LLM module (LCEL chains)
    if name in ("create_extraction_chain", "create_text_chain", "ChainConfig",
                "get_default_llm", "get_openai_llm", "get_anthropic_llm",
                "set_default_llm", "LLMProvider"):
        from agentorchestrator import llm
        return getattr(llm, name)

    # Resources
    if name in ("Resource", "ResourceManager", "ResourceScope",
                "get_resource_manager", "reset_resource_manager"):
        from agentorchestrator.core import resources
        return getattr(resources, name)

    # Testing extras
    if name in ("MockMiddleware", "mock_step", "mock_chain",
                "assert_step_completed", "assert_chain_valid"):
        from agentorchestrator import testing
        return getattr(testing, name)

    # Utility extras
    if name in ("timed", "async_timed", "retry", "async_retry", "RetryPolicy",
                "CircuitBreakerError", "get_circuit_breaker",
                "LogContext", "ChainLogger",
                "configure_tracing", "get_tracer", "trace_span", "ChainTracer"):
        from agentorchestrator import utils
        return getattr(utils, name)

    raise AttributeError(f"module 'agentorchestrator' has no attribute '{name}'")
