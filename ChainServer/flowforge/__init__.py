"""
FlowForge: A DAG-based Chain Orchestration Framework

Inspired by Dagster patterns. Provides decorator-driven registration,
automatic dependency resolution, and clean validation/execution APIs.

Usage:
    import flowforge as fg

    # Create instance (isolated by default)
    forge = fg.FlowForge(name="my_app")

    # Define agents (data sources)
    @forge.agent
    class NewsAgent:
        async def fetch(self, query: str) -> dict: ...

    # Define steps with dependencies
    @forge.step
    async def extract_company(ctx: fg.Context): ...

    @forge.step(deps=[extract_company])
    async def fetch_data(ctx: fg.Context): ...

    # Define chains
    @forge.chain
    class MeetingPrepChain:
        steps = [extract_company, fetch_data]

    # Validate & Run
    forge.check()                           # Validate definitions
    forge.list_defs()                       # List all definitions
    forge.graph("MeetingPrepChain")         # Show DAG visualization
    result = await forge.launch("MeetingPrepChain")  # Execute

CLI Usage:
    flowforge run cmpt_chain --company "Apple"
    flowforge check
    flowforge list
    flowforge graph cmpt_chain --format mermaid
    flowforge new agent MyAgent
    flowforge new chain MyChain
    flowforge dev --watch

CMPT Chain Usage:
    from flowforge.chains import CMPTChain

    chain = CMPTChain()
    chain.check()                           # Validate
    chain.graph()                           # Show DAG

    result = await chain.run(
        corporate_company_name="Apple Inc",
        meeting_datetime="2025-01-15T10:00:00Z",
    )
"""

# CMPT Chain
from flowforge.chains import CMPTChain, create_cmpt_chain

# Configuration
from flowforge.config import Config, get_config, reload_config, set_config
from flowforge.core.context import ChainContext

# For backward compatibility with old decorator imports
from flowforge.core.decorators import agent, chain, middleware, step
from flowforge.core.forge import Context, Definitions, FlowForge, get_forge, set_forge
from flowforge.core.registry import (
    AgentRegistry,
    ChainRegistry,
    StepRegistry,
    get_agent_registry,
    get_chain_registry,
    get_step_registry,
    create_isolated_registries,
    reset_global_registries,
)
from flowforge.middleware.base import Middleware
from flowforge.middleware.cache import CacheMiddleware
from flowforge.middleware.logger import LoggerMiddleware
from flowforge.middleware.summarizer import (
    DOMAIN_PROMPTS,
    LangChainSummarizer,
    SummarizationStrategy,
    SummarizerMiddleware,
    create_anthropic_summarizer,
    create_domain_aware_middleware,
    create_gateway_summarizer,
    create_openai_summarizer,
)
from flowforge.middleware.token_manager import TokenManagerMiddleware

# Resources
from flowforge.core.resources import (
    Resource,
    ResourceManager,
    ResourceScope,
    get_resource_manager,
    reset_resource_manager,
)

# Services (for direct usage)
from flowforge.services import (
    ChainRequest,
    ChainRequestOverrides,
    ChainResponse,
    ContentPrioritizationService,
    ContextBuilderService,
    LLMGatewayClient,
    ResponseBuilderService,
    get_llm_client,
    create_managed_client,
)

# Testing utilities (for user tests)
from flowforge.testing import (
    MockAgent,
    MockMiddleware,
    IsolatedForge,
    mock_step,
    mock_chain,
    create_test_context,
    assert_step_completed,
    assert_chain_valid,
)

# Utilities
from flowforge.utils import (
    # Timing
    timed,
    async_timed,
    # Retry
    retry,
    async_retry,
    RetryPolicy,
    # Circuit breaker
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    get_circuit_breaker,
    # Logging
    configure_logging,
    get_logger,
    LogContext,
    ChainLogger,
    # Tracing
    configure_tracing,
    get_tracer,
    trace_span,
    ChainTracer,
)

__version__ = "0.1.0"
__all__ = [
    # Main class
    "FlowForge",
    "Definitions",
    "Context",
    "ChainContext",
    # Configuration
    "Config",
    "get_config",
    "set_config",
    "reload_config",
    # Factory functions
    "get_forge",
    "set_forge",
    # Registries
    "AgentRegistry",
    "StepRegistry",
    "ChainRegistry",
    "get_agent_registry",
    "get_step_registry",
    "get_chain_registry",
    "create_isolated_registries",
    "reset_global_registries",
    # Middleware
    "Middleware",
    "SummarizerMiddleware",
    "LangChainSummarizer",
    "SummarizationStrategy",
    "create_openai_summarizer",
    "create_anthropic_summarizer",
    "create_gateway_summarizer",
    "create_domain_aware_middleware",
    "DOMAIN_PROMPTS",
    "CacheMiddleware",
    "LoggerMiddleware",
    "TokenManagerMiddleware",
    # Legacy decorators (use forge.agent/step/chain instead)
    "agent",
    "step",
    "chain",
    "middleware",
    # CMPT Chain
    "CMPTChain",
    "create_cmpt_chain",
    # Services
    "ChainRequest",
    "ChainRequestOverrides",
    "ChainResponse",
    "ContextBuilderService",
    "ContentPrioritizationService",
    "ResponseBuilderService",
    # LLM Gateway
    "LLMGatewayClient",
    "get_llm_client",
    "create_managed_client",
    # Resources
    "Resource",
    "ResourceManager",
    "ResourceScope",
    "get_resource_manager",
    "reset_resource_manager",
    # Utilities - Timing
    "timed",
    "async_timed",
    # Utilities - Retry
    "retry",
    "async_retry",
    "RetryPolicy",
    # Utilities - Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "get_circuit_breaker",
    # Utilities - Logging
    "configure_logging",
    "get_logger",
    "LogContext",
    "ChainLogger",
    # Utilities - Tracing
    "configure_tracing",
    "get_tracer",
    "trace_span",
    "ChainTracer",
    # Testing utilities
    "MockAgent",
    "IsolatedForge",
    "mock_step",
    "mock_chain",
    "MockMiddleware",
    "create_test_context",
    "assert_step_completed",
    "assert_chain_valid",
]
