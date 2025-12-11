"""
LCEL Chain Builders

Provides factory functions for creating reusable, resilient LLM chains
with built-in retry, fallback, and type-safe parsing.

This is the recommended way to make LLM calls in AgentOrchestrator.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Type variable for Pydantic response models
T = TypeVar("T", bound=BaseModel)

# Type alias for LangChain components
BaseChatModel = Any
Runnable = Any


@dataclass
class ChainConfig:
    """
    Configuration for LCEL chains.

    Attributes:
        retries: Number of retry attempts on failure (default: 3)
        retry_wait_seconds: Initial wait between retries (default: 1)
        retry_exponential: Use exponential backoff (default: True)
        timeout_seconds: Request timeout (default: 60)
    """
    retries: int = 3
    retry_wait_seconds: float = 1.0
    retry_exponential: bool = True
    timeout_seconds: float = 60.0
    # Additional kwargs to pass to LLM
    llm_kwargs: dict[str, Any] = field(default_factory=dict)


def create_extraction_chain(
    prompt_template: str,
    response_model: type[T],
    llm: BaseChatModel | None = None,
    system_prompt: str | None = None,
    fallback_llm: BaseChatModel | None = None,
    config: ChainConfig | None = None,
) -> Runnable:
    """
    Create a reusable LCEL chain for structured data extraction.

    This is the standard way to call LLMs for structured output in AgentOrchestrator.
    The chain handles:
    - Prompt formatting with variables
    - LLM invocation
    - Response parsing into Pydantic models
    - Automatic retries with exponential backoff
    - Fallback to alternative LLM on failure

    Args:
        prompt_template: The prompt template with {variable} placeholders
        response_model: Pydantic model class for the expected response
        llm: LangChain chat model (default: uses get_default_llm())
        system_prompt: Optional system prompt for context
        fallback_llm: Optional fallback LLM if primary fails
        config: Chain configuration (retries, timeouts, etc.)

    Returns:
        A LangChain Runnable that can be invoked with .ainvoke() or .invoke()

    Example:
        from agentorchestrator.llm import create_extraction_chain
        from pydantic import BaseModel

        class FinancialMetrics(BaseModel):
            revenue: float
            eps: float

        chain = create_extraction_chain(
            prompt_template="Extract metrics from: {data}",
            response_model=FinancialMetrics,
            system_prompt="You are a financial analyst.",
        )

        # Async usage (recommended)
        result = await chain.ainvoke({"data": "Revenue was $50B..."})
        print(result.revenue)  # 50.0 - typed!

        # Sync usage
        result = chain.invoke({"data": "Revenue was $50B..."})
    """
    try:
        from langchain_core.output_parsers import PydanticOutputParser
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError as e:
        raise ImportError(
            "langchain-core is required. Install with: pip install agentorchestrator[summarization]"
        ) from e

    from agentorchestrator.llm.providers import get_default_llm

    config = config or ChainConfig()

    # Get or create LLM
    if llm is None:
        llm = get_default_llm()

    # Create Pydantic output parser
    parser = PydanticOutputParser(pydantic_object=response_model)

    # Build prompt template with format instructions
    messages = []
    if system_prompt:
        # Include format instructions in system prompt for better compliance
        messages.append((
            "system",
            f"{system_prompt}\n\nYou must respond with valid JSON matching this schema:\n{{format_instructions}}"
        ))
    else:
        messages.append((
            "system",
            "You must respond with valid JSON matching this schema:\n{format_instructions}"
        ))

    messages.append(("human", prompt_template))

    prompt = ChatPromptTemplate.from_messages(messages).partial(
        format_instructions=parser.get_format_instructions()
    )

    # Build the chain with pipe operator
    chain_llm = llm

    # Add fallback if provided
    if fallback_llm is not None:
        chain_llm = llm.with_fallbacks([fallback_llm])
        logger.debug(f"Chain configured with fallback: {type(fallback_llm).__name__}")

    # Compose: prompt -> llm -> parser
    chain = prompt | chain_llm | parser

    # Add retry logic
    if config.retries > 0:
        chain = chain.with_retry(
            stop_after_attempt=config.retries,
            wait_exponential_jitter=config.retry_exponential,
        )
        logger.debug(f"Chain configured with {config.retries} retries")

    return chain


def create_text_chain(
    prompt_template: str,
    llm: BaseChatModel | None = None,
    system_prompt: str | None = None,
    fallback_llm: BaseChatModel | None = None,
    config: ChainConfig | None = None,
) -> Runnable:
    """
    Create a simple text generation chain (no structured output).

    Use this when you need free-form text responses rather than
    structured Pydantic models.

    Args:
        prompt_template: The prompt template with {variable} placeholders
        llm: LangChain chat model (default: uses get_default_llm())
        system_prompt: Optional system prompt for context
        fallback_llm: Optional fallback LLM if primary fails
        config: Chain configuration (retries, timeouts, etc.)

    Returns:
        A LangChain Runnable that returns str

    Example:
        chain = create_text_chain(
            prompt_template="Summarize this document: {text}",
            system_prompt="You are a helpful assistant.",
        )
        summary = await chain.ainvoke({"text": "Long document..."})
        print(summary)  # "The document discusses..."
    """
    try:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError as e:
        raise ImportError(
            "langchain-core is required. Install with: pip install agentorchestrator[summarization]"
        ) from e

    from agentorchestrator.llm.providers import get_default_llm

    config = config or ChainConfig()

    # Get or create LLM
    if llm is None:
        llm = get_default_llm()

    # Build prompt template
    messages = []
    if system_prompt:
        messages.append(("system", system_prompt))
    messages.append(("human", prompt_template))

    prompt = ChatPromptTemplate.from_messages(messages)

    # String output parser
    parser = StrOutputParser()

    # Build the chain
    chain_llm = llm

    # Add fallback if provided
    if fallback_llm is not None:
        chain_llm = llm.with_fallbacks([fallback_llm])

    # Compose: prompt -> llm -> parser
    chain = prompt | chain_llm | parser

    # Add retry logic
    if config.retries > 0:
        chain = chain.with_retry(
            stop_after_attempt=config.retries,
            wait_exponential_jitter=config.retry_exponential,
        )

    return chain


def create_chain_with_structured_output(
    prompt_template: str,
    response_model: type[T],
    llm: BaseChatModel | None = None,
    system_prompt: str | None = None,
    fallback_llm: BaseChatModel | None = None,
    config: ChainConfig | None = None,
) -> Runnable:
    """
    Create a chain using LLM's native structured output (if supported).

    This uses the LLM's built-in JSON mode or function calling for more
    reliable structured output. Falls back to PydanticOutputParser if
    the LLM doesn't support structured output.

    Args:
        prompt_template: The prompt template with {variable} placeholders
        response_model: Pydantic model class for the expected response
        llm: LangChain chat model (default: uses get_default_llm())
        system_prompt: Optional system prompt for context
        fallback_llm: Optional fallback LLM if primary fails
        config: Chain configuration (retries, timeouts, etc.)

    Returns:
        A LangChain Runnable that returns the response_model type
    """
    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError as e:
        raise ImportError(
            "langchain-core is required. Install with: pip install agentorchestrator[summarization]"
        ) from e

    from agentorchestrator.llm.providers import get_default_llm

    config = config or ChainConfig()

    # Get or create LLM
    if llm is None:
        llm = get_default_llm()

    # Build prompt template
    messages = []
    if system_prompt:
        messages.append(("system", system_prompt))
    messages.append(("human", prompt_template))

    prompt = ChatPromptTemplate.from_messages(messages)

    # Try to use native structured output
    try:
        structured_llm = llm.with_structured_output(response_model)
        logger.debug(f"Using native structured output for {response_model.__name__}")
    except (AttributeError, NotImplementedError):
        # Fall back to PydanticOutputParser
        logger.debug(f"LLM doesn't support structured output, using PydanticOutputParser")
        return create_extraction_chain(
            prompt_template=prompt_template,
            response_model=response_model,
            llm=llm,
            system_prompt=system_prompt,
            fallback_llm=fallback_llm,
            config=config,
        )

    # Build the chain
    chain_llm = structured_llm

    # Add fallback if provided
    if fallback_llm is not None:
        try:
            fallback_structured = fallback_llm.with_structured_output(response_model)
            chain_llm = structured_llm.with_fallbacks([fallback_structured])
        except (AttributeError, NotImplementedError):
            chain_llm = structured_llm.with_fallbacks([fallback_llm])

    # Compose: prompt -> structured_llm
    chain = prompt | chain_llm

    # Add retry logic
    if config.retries > 0:
        chain = chain.with_retry(
            stop_after_attempt=config.retries,
            wait_exponential_jitter=config.retry_exponential,
        )

    return chain
