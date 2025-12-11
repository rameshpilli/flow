"""
AgentOrchestrator LLM Module

Provides LCEL (LangChain Expression Language) chain builders for structured
LLM interactions with built-in retry, fallback, and type-safe parsing.

Quick Start:
    from agentorchestrator.llm import create_extraction_chain
    from pydantic import BaseModel

    class MyResponse(BaseModel):
        name: str
        score: float

    chain = create_extraction_chain(
        prompt_template="Extract info from: {text}",
        response_model=MyResponse,
    )
    result = await chain.ainvoke({"text": "..."})
    # result is MyResponse instance, not dict

Features:
    - Type-safe extraction with Pydantic models
    - Built-in retry with exponential backoff
    - Fallback LLM support (e.g., OpenAI -> Claude)
    - Automatic JSON parsing from LLM responses
    - Streaming support via .astream()
"""

from agentorchestrator.llm.chains import (
    create_extraction_chain,
    create_text_chain,
    ChainConfig,
)
from agentorchestrator.llm.providers import (
    get_default_llm,
    get_openai_llm,
    get_anthropic_llm,
    set_default_llm,
    LLMProvider,
)

__all__ = [
    # Chain builders
    "create_extraction_chain",
    "create_text_chain",
    "ChainConfig",
    # Provider utilities
    "get_default_llm",
    "get_openai_llm",
    "get_anthropic_llm",
    "set_default_llm",
    "LLMProvider",
]
