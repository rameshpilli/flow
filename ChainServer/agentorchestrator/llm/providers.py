"""
LLM Provider Configuration

Manages LLM provider instances (OpenAI, Anthropic, etc.) with
sensible defaults and easy configuration.
"""

import logging
import os
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Type alias for LangChain chat models
BaseChatModel = Any  # Actual type: langchain_core.language_models.chat_models.BaseChatModel


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


# Global default LLM instance
_default_llm: BaseChatModel | None = None


def get_openai_llm(
    model: str = "gpt-4o",
    temperature: float = 0,
    api_key: str | None = None,
    **kwargs,
) -> BaseChatModel:
    """
    Get an OpenAI chat model instance.

    Args:
        model: Model name (default: gpt-4o)
        temperature: Sampling temperature (default: 0 for deterministic)
        api_key: OpenAI API key (default: from OPENAI_API_KEY env var)
        **kwargs: Additional arguments passed to ChatOpenAI

    Returns:
        ChatOpenAI instance

    Raises:
        ImportError: If langchain-openai is not installed
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai is required for OpenAI support. "
            "Install with: pip install agentorchestrator[openai]"
        ) from e

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key or os.getenv("OPENAI_API_KEY"),
        **kwargs,
    )


def get_anthropic_llm(
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0,
    api_key: str | None = None,
    **kwargs,
) -> BaseChatModel:
    """
    Get an Anthropic chat model instance.

    Args:
        model: Model name (default: claude-sonnet-4-20250514)
        temperature: Sampling temperature (default: 0 for deterministic)
        api_key: Anthropic API key (default: from ANTHROPIC_API_KEY env var)
        **kwargs: Additional arguments passed to ChatAnthropic

    Returns:
        ChatAnthropic instance

    Raises:
        ImportError: If langchain-anthropic is not installed
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise ImportError(
            "langchain-anthropic is required for Anthropic support. "
            "Install with: pip install agentorchestrator[anthropic]"
        ) from e

    return ChatAnthropic(
        model=model,
        temperature=temperature,
        api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
        **kwargs,
    )


def set_default_llm(llm: BaseChatModel) -> None:
    """
    Set the default LLM instance used by chain builders.

    Args:
        llm: A LangChain chat model instance
    """
    global _default_llm
    _default_llm = llm
    logger.info(f"Default LLM set to: {type(llm).__name__}")


def get_default_llm(
    provider: LLMProvider | str = LLMProvider.OPENAI,
    **kwargs,
) -> BaseChatModel:
    """
    Get the default LLM instance, creating one if not set.

    Args:
        provider: Which provider to use if creating a new instance
        **kwargs: Arguments passed to provider constructor

    Returns:
        The default LLM instance
    """
    global _default_llm

    if _default_llm is not None:
        return _default_llm

    # Create a default instance based on provider
    provider = LLMProvider(provider) if isinstance(provider, str) else provider

    if provider == LLMProvider.OPENAI:
        _default_llm = get_openai_llm(**kwargs)
    elif provider == LLMProvider.ANTHROPIC:
        _default_llm = get_anthropic_llm(**kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    logger.info(f"Created default LLM: {type(_default_llm).__name__}")
    return _default_llm


def reset_default_llm() -> None:
    """Reset the default LLM instance (useful for testing)."""
    global _default_llm
    _default_llm = None
