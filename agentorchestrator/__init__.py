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
from agentorchestrator.core.context import ChainContext, Context
from agentorchestrator.core.event_bus import (
    Event,
    EventBus,
    InMemoryEventBus,
    RedisEventBus,
    get_event_bus,
)
from agentorchestrator.dsl import Pipeline, StepDef, EventDef
from agentorchestrator.core.orchestrator import AgentOrchestrator

# =============================================================================
# MODELS - Citation and data models
# =============================================================================
from agentorchestrator.models.citation import (
    Citation,
    CitationLevel,
    CitedValue,
    CitationCollection,
    SourceReference,
)

# =============================================================================
# MIDDLEWARE - Import from submodule for full list
# =============================================================================
from agentorchestrator.middleware.base import Middleware
from agentorchestrator.middleware.cache import CacheMiddleware
from agentorchestrator.middleware.citation import CitationMiddleware, cite
from agentorchestrator.middleware.logger import LoggerMiddleware
from agentorchestrator.middleware.summarizer import (
    SummarizerMiddleware,
    create_anthropic_summarizer,
    create_gateway_summarizer,
    create_openai_summarizer,
)
from agentorchestrator.middleware.token_manager import TokenManagerMiddleware

# testing module removed in this branch — skip import gracefully
IsolatedOrchestrator = None
MockAgent = None
create_test_context = None

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
# LLM Gateway - For LLM calls in corporate environments
# =============================================================================
# Use: from agentorchestrator.services import LLMGatewayClient

# =============================================================================
# MCP SERVER - Expose chains/agents as MCP tools (opt-in)
# =============================================================================
from agentorchestrator.server.mcp import MCPServer, MCPToolDef

__version__ = "0.1.0"

# Focused public API (~30 exports instead of 75+)
__all__ = [
    # Core (essential)
    "AgentOrchestrator",
    "Context",
    "ChainContext",
    "Event",
    "EventBus",
    "InMemoryEventBus",
    "RedisEventBus",
    "get_event_bus",
    "Pipeline",
    "StepDef",
    "EventDef",
    # Config
    "Config",
    "get_config",
    # Models (citation tracking)
    "Citation",
    "CitationLevel",
    "CitedValue",
    "CitationCollection",
    "SourceReference",
    # Middleware (common)
    "Middleware",
    "CacheMiddleware",
    "CitationMiddleware",
    "LoggerMiddleware",
    "SummarizerMiddleware",
    "TokenManagerMiddleware",
    "cite",
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
    # MCP Server (opt-in — expose chains as MCP tools)
    "MCPServer",
    "MCPToolDef",
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
    # Also includes utility decorators: depends_on, produces, consumes
    if name in ("agent", "step", "chain", "supervisor", "suite", "middleware",
                "depends_on", "produces", "consumes"):
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
    if name in ("LangChainSummarizer", "SummarizationStrategy",
                "create_domain_aware_middleware"):
        from agentorchestrator.middleware import summarizer
        return getattr(summarizer, name)

    # LLM Gateway - redirect to services
    if name in ("LLMGatewayClient", "get_llm_client", "create_managed_client"):
        from agentorchestrator import services
        return getattr(services, name)

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
