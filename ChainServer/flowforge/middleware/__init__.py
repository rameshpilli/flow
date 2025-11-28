"""FlowForge Middleware Module"""

from flowforge.middleware.base import Middleware
from flowforge.middleware.cache import CacheMiddleware
from flowforge.middleware.logger import LoggerMiddleware
from flowforge.middleware.summarizer import (
    DOMAIN_PROMPTS,
    LangChainSummarizer,
    LLMSummarizer,  # Legacy alias
    SummarizationStrategy,
    SummarizerMiddleware,
    create_anthropic_summarizer,
    create_domain_aware_middleware,
    create_gateway_summarizer,
    create_openai_summarizer,
    get_domain_prompts,
)
from flowforge.middleware.token_manager import TokenManagerMiddleware

__all__ = [
    # Base
    "Middleware",
    # Summarization (LangChain-powered)
    "SummarizerMiddleware",
    "LangChainSummarizer",
    "SummarizationStrategy",
    "create_openai_summarizer",
    "create_anthropic_summarizer",
    "create_gateway_summarizer",
    "create_domain_aware_middleware",
    "DOMAIN_PROMPTS",
    "get_domain_prompts",
    "LLMSummarizer",  # Legacy alias
    # Other middleware
    "CacheMiddleware",
    "LoggerMiddleware",
    "TokenManagerMiddleware",
]
