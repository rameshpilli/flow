"""
FlowForge: A DAG-based Chain Orchestration Framework

Inspired by Dagster patterns. Provides decorator-driven registration,
automatic dependency resolution, and clean validation/execution APIs.

Usage:
    import flowforge as fg

    # Create instance
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
    create_openai_summarizer,
)
from flowforge.middleware.token_manager import TokenManagerMiddleware

# Services (for direct usage)
from flowforge.services import (
    ChainRequest,
    ChainResponse,
    ContentPrioritizationService,
    ContextBuilderService,
    ResponseBuilderService,
)

__version__ = "0.1.0"
__all__ = [
    # Main class
    "FlowForge",
    "Definitions",
    "Context",
    "ChainContext",
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
    # Middleware
    "Middleware",
    "SummarizerMiddleware",
    "LangChainSummarizer",
    "SummarizationStrategy",
    "create_openai_summarizer",
    "create_anthropic_summarizer",
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
    "ChainResponse",
    "ContextBuilderService",
    "ContentPrioritizationService",
    "ResponseBuilderService",
]
