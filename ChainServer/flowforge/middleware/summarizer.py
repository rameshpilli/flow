"""
FlowForge Summarizer Middleware

Summarizes large text outputs to manage context size in LLM chains.
Supports stuff, map_reduce, and refine strategies via LangChain.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

from flowforge.core.context import ChainContext, ContextScope, StepResult
from flowforge.middleware.base import Middleware

logger = logging.getLogger(__name__)


# Token counting - shared utility
def count_tokens(text: str) -> int:
    """Count tokens using tiktoken, or estimate (~4 chars/token)."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return len(text) // 4


class SummarizationStrategy(str, Enum):
    """Summarization strategies."""

    STUFF = "stuff"  # Single prompt (small docs)
    MAP_REDUCE = "map_reduce"  # Parallel chunks, then combine
    REFINE = "refine"  # Iterative refinement


# =============================================================================
# Domain-Specific Prompts - What to extract from each content type
# =============================================================================

DOMAIN_PROMPTS = {
    # SEC Filings: Focus on financials, risks, guidance
    "sec_filing": {
        "map": (
            "Extract key financial information from this SEC filing:\n"
            "- Revenue, earnings, margins (with exact numbers and dates)\n"
            "- Forward guidance and projections\n"
            "- Risk factors and material changes\n"
            "- Segment performance\n\n"
            "{text}\n\nKey Financial Data:"
        ),
        "reduce": (
            "Combine these SEC filing summaries into a financial overview:\n"
            "- Consolidate all revenue/earnings figures with periods\n"
            "- List all forward guidance statements\n"
            "- Highlight material risks\n\n"
            "{text}\n\nConsolidated Financial Summary:"
        ),
    },
    # Earnings: Focus on EPS, revenue beats/misses, guidance
    "earnings": {
        "map": (
            "Extract earnings data from this content:\n"
            "- EPS (actual vs estimate, beat/miss amount)\n"
            "- Revenue (actual vs estimate)\n"
            "- YoY and QoQ growth rates\n"
            "- Next quarter/year guidance\n"
            "- Key metrics mentioned by management\n\n"
            "{text}\n\nEarnings Data:"
        ),
        "reduce": (
            "Consolidate earnings information:\n"
            "- Create a timeline of quarterly results\n"
            "- Summarize beat/miss history\n"
            "- Highlight guidance changes\n\n"
            "{text}\n\nEarnings Summary:"
        ),
    },
    # News: Focus on events, sentiment, dates
    "news": {
        "map": (
            "Extract news highlights:\n"
            "- Event type (M&A, product launch, lawsuit, partnership)\n"
            "- Date of event/announcement\n"
            "- Impact (positive/negative/neutral)\n"
            "- Key parties involved\n"
            "- Price targets or analyst opinions if mentioned\n\n"
            "{text}\n\nNews Highlights:"
        ),
        "reduce": (
            "Create a news timeline:\n"
            "- Group by event type\n"
            "- Order chronologically\n"
            "- Note overall sentiment trend\n\n"
            "{text}\n\nNews Timeline:"
        ),
    },
    # Transcripts: Focus on management commentary, Q&A insights
    "transcripts": {
        "map": (
            "Extract key points from this earnings call/transcript:\n"
            "- Management's key statements and outlook\n"
            "- Specific numbers or targets mentioned\n"
            "- Analyst questions and management responses\n"
            "- Tone (confident, cautious, defensive)\n"
            "- Any surprises or notable quotes\n\n"
            "{text}\n\nTranscript Highlights:"
        ),
        "reduce": (
            "Synthesize transcript insights:\n"
            "- Main themes from management\n"
            "- Key concerns from analysts\n"
            "- Forward-looking statements\n"
            "- Overall sentiment\n\n"
            "{text}\n\nTranscript Summary:"
        ),
    },
    # Pricing/Valuation: Focus on multiples, targets, comparables
    "pricing": {
        "map": (
            "Extract valuation and pricing data:\n"
            "- Current price and date\n"
            "- P/E, P/S, EV/EBITDA multiples\n"
            "- Analyst price targets (low/median/high)\n"
            "- Comparable company valuations\n"
            "- Historical valuation ranges\n\n"
            "{text}\n\nValuation Data:"
        ),
        "reduce": (
            "Consolidate valuation metrics:\n"
            "- Current vs historical multiples\n"
            "- Price target consensus\n"
            "- Peer comparison\n\n"
            "{text}\n\nValuation Summary:"
        ),
    },
}


def get_domain_prompts(content_type: str) -> tuple:
    """Get map/reduce prompts for a content type, or defaults if not found."""
    prompts = DOMAIN_PROMPTS.get(content_type, {})
    return (
        prompts.get("map", LangChainSummarizer.DEFAULT_MAP_PROMPT),
        prompts.get("reduce", LangChainSummarizer.DEFAULT_REDUCE_PROMPT),
    )


class LangChainSummarizer:
    """
    Summarizer using LangChain with stuff, map_reduce, or refine strategies.
    Falls back to simple truncation if no LLM is provided.
    """

    # Default prompts
    DEFAULT_MAP_PROMPT = (
        "Summarize the following content, preserving key facts, metrics, "
        "dates, and important details:\n\n{text}\n\nSummary:"
    )
    DEFAULT_REDUCE_PROMPT = (
        "Combine these summaries into a cohesive final summary. "
        "Preserve all key metrics, facts, and insights:\n\n{text}\n\nFinal Summary:"
    )
    DEFAULT_REFINE_PROMPT = (
        "Here is an existing summary:\n{existing_summary}\n\n"
        "Refine it using this additional context:\n{text}\n\n"
        "Refined Summary:"
    )

    def __init__(
        self,
        llm: Any | None = None,
        strategy: SummarizationStrategy = SummarizationStrategy.MAP_REDUCE,
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        use_token_splitter: bool = True,
        map_prompt: str | None = None,
        reduce_prompt: str | None = None,
        refine_prompt: str | None = None,
    ):
        self.llm = llm
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.map_prompt = map_prompt or self.DEFAULT_MAP_PROMPT
        self.reduce_prompt = reduce_prompt or self.DEFAULT_REDUCE_PROMPT
        self.refine_prompt = refine_prompt or self.DEFAULT_REFINE_PROMPT

        # Initialize text splitter
        self.text_splitter = self._create_splitter(use_token_splitter)

    def _create_splitter(self, use_token_splitter: bool):
        """Create LangChain text splitter, or None if unavailable."""
        try:
            if use_token_splitter:
                from langchain_text_splitters import TokenTextSplitter

                return TokenTextSplitter(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                )
            else:
                from langchain_text_splitters import RecursiveCharacterTextSplitter

                return RecursiveCharacterTextSplitter(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                    separators=["\n\n", "\n", ". ", " ", ""],
                )
        except ImportError:
            logger.warning("langchain-text-splitters not installed, using simple split")
            return None

    def split_text(self, text: str) -> list[str]:
        """Split text into chunks."""
        if self.text_splitter:
            return self.text_splitter.split_text(text)

        # Simple fallback: split by estimated char size
        char_size = self.chunk_size * 4
        chunks = []
        for i in range(0, len(text), char_size):
            chunks.append(text[i : i + char_size])
        return chunks

    async def summarize(
        self,
        text: str,
        max_tokens: int | None = None,
        strategy: SummarizationStrategy | None = None,
        content_type: str | None = None,
    ) -> str:
        """
        Summarize text using the configured strategy.

        Args:
            text: Text to summarize
            max_tokens: Maximum tokens for output
            strategy: Override default strategy
            content_type: Domain type for specialized prompts
                         ("sec_filing", "earnings", "news", "transcripts", "pricing")
        """
        strategy = strategy or self.strategy

        # Apply domain-specific prompts if content_type provided
        original_map = self.map_prompt
        original_reduce = self.reduce_prompt
        if content_type and content_type in DOMAIN_PROMPTS:
            self.map_prompt, self.reduce_prompt = get_domain_prompts(content_type)
            logger.info(f"Using domain prompts for: {content_type}")

        try:
            # Small text? Just use stuff strategy
            if count_tokens(text) <= self.chunk_size:
                return await self._stuff_summarize(text, max_tokens)

            # Route to appropriate strategy
            handlers = {
                SummarizationStrategy.STUFF: self._stuff_summarize,
                SummarizationStrategy.MAP_REDUCE: self._map_reduce_summarize,
                SummarizationStrategy.REFINE: self._refine_summarize,
            }
            handler = handlers.get(strategy, self._map_reduce_summarize)
            return await handler(text, max_tokens)
        finally:
            # Restore original prompts
            self.map_prompt = original_map
            self.reduce_prompt = original_reduce

    async def _stuff_summarize(self, text: str, max_tokens: int | None = None) -> str:
        """Single LLM call with all text."""
        if not self.llm:
            raise ValueError(
                "No LLM configured for summarization. "
                "Use create_openai_summarizer(), create_anthropic_summarizer(), "
                "or create_gateway_summarizer() to configure an LLM backend."
            )

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            chain = ChatPromptTemplate.from_template(self.map_prompt) | self.llm | StrOutputParser()
            return await chain.ainvoke({"text": text})
        except Exception as e:
            logger.error(f"Stuff summarization failed: {e}")
            raise RuntimeError(f"Summarization failed: {e}") from e

    async def _map_reduce_summarize(self, text: str, max_tokens: int | None = None) -> str:
        """Summarize chunks in parallel, then combine."""
        if not self.llm:
            raise ValueError(
                "No LLM configured for summarization. "
                "Use create_openai_summarizer(), create_anthropic_summarizer(), "
                "or create_gateway_summarizer() to configure an LLM backend."
            )

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            chunks = self.split_text(text)
            logger.info(f"Map-Reduce: {len(chunks)} chunks")

            # Map phase: summarize each chunk in parallel
            map_chain = (
                ChatPromptTemplate.from_template(self.map_prompt) | self.llm | StrOutputParser()
            )
            chunk_summaries = await asyncio.gather(
                *[map_chain.ainvoke({"text": chunk}) for chunk in chunks]
            )

            # Combine summaries
            combined = "\n\n---\n\n".join(chunk_summaries)

            # Recursively reduce if still too large
            if count_tokens(combined) > self.chunk_size * 2:
                return await self._map_reduce_summarize(combined, max_tokens)

            # Final reduce step
            reduce_chain = (
                ChatPromptTemplate.from_template(self.reduce_prompt) | self.llm | StrOutputParser()
            )
            return await reduce_chain.ainvoke({"text": combined})

        except Exception as e:
            logger.error(f"Map-Reduce summarization failed: {e}")
            raise RuntimeError(f"Summarization failed: {e}") from e

    async def _refine_summarize(self, text: str, max_tokens: int | None = None) -> str:
        """Iteratively refine summary with each chunk (sequential)."""
        if not self.llm:
            raise ValueError(
                "No LLM configured for summarization. "
                "Use create_openai_summarizer(), create_anthropic_summarizer(), "
                "or create_gateway_summarizer() to configure an LLM backend."
            )

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            chunks = self.split_text(text)
            logger.info(f"Refine: {len(chunks)} chunks")

            # Start with first chunk
            initial_chain = (
                ChatPromptTemplate.from_template(self.map_prompt) | self.llm | StrOutputParser()
            )
            summary = await initial_chain.ainvoke({"text": chunks[0]})

            # Refine with remaining chunks
            refine_chain = (
                ChatPromptTemplate.from_template(self.refine_prompt) | self.llm | StrOutputParser()
            )
            for chunk in chunks[1:]:
                summary = await refine_chain.ainvoke(
                    {
                        "existing_summary": summary,
                        "text": chunk,
                    }
                )

            return summary

        except Exception as e:
            logger.error(f"Refine summarization failed: {e}")
            raise RuntimeError(f"Summarization failed: {e}") from e


class SummarizerMiddleware(Middleware):
    """
    Middleware that summarizes large step outputs to manage context size.
    Triggers when output exceeds max_tokens threshold.

    Supports domain-specific summarization via step_content_types mapping.
    """

    def __init__(
        self,
        priority: int = 50,
        applies_to: list[str] | None = None,
        max_tokens: int = 4000,
        summarizer: LangChainSummarizer | Callable | None = None,
        preserve_original: bool = True,
        step_thresholds: dict[str, int] | None = None,
        step_content_types: dict[str, str] | None = None,
        strategy: SummarizationStrategy = SummarizationStrategy.MAP_REDUCE,
    ):
        """
        Args:
            step_content_types: Map step names to content types for domain-aware prompts.
                               e.g., {"fetch_sec": "sec_filing", "fetch_news": "news"}
        """
        super().__init__(priority=priority, applies_to=applies_to)
        self.max_tokens = max_tokens
        self.preserve_original = preserve_original
        self.step_thresholds = step_thresholds or {}
        self.step_content_types = step_content_types or {}

        # Set up summarizer
        if summarizer is None:
            self.summarizer = LangChainSummarizer(llm=None, strategy=strategy)
        elif isinstance(summarizer, LangChainSummarizer):
            self.summarizer = summarizer
        else:
            # Support legacy callable summarizers
            self._legacy_summarizer = summarizer
            self.summarizer = None

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Summarize output if it exceeds token threshold."""
        if not result.success or result.output is None:
            return

        max_tokens = self.step_thresholds.get(step_name, self.max_tokens)
        content_type = self.step_content_types.get(step_name)
        output_str = self._to_string(result.output)
        token_count = count_tokens(output_str)

        if token_count <= max_tokens:
            result.token_count = token_count
            return

        logger.info(f"Step {step_name}: {token_count} > {max_tokens} tokens, summarizing...")
        if content_type:
            logger.info(f"Using domain-specific prompts for: {content_type}")

        # Summarize with domain-specific prompts if available
        if self.summarizer:
            summarized = await self.summarizer.summarize(
                output_str, max_tokens, content_type=content_type
            )
        elif hasattr(self, "_legacy_summarizer"):
            summarized = await self._run_legacy_summarizer(output_str, max_tokens)
        else:
            raise ValueError(
                f"Step '{step_name}' output exceeds {max_tokens} tokens but no summarizer configured. "
                "Use create_openai_summarizer(), create_anthropic_summarizer(), "
                "or create_gateway_summarizer() to configure an LLM backend, "
                "or use Redis offloading with RedisContextStore for large payloads."
            )

        summarized_tokens = count_tokens(summarized)

        # Preserve original if requested
        if self.preserve_original:
            ctx.set(
                f"_original_{step_name}_output",
                result.output,
                scope=ContextScope.CHAIN,
                token_count=token_count,
            )

        # Update result
        result.output = self._parse_summary(summarized, result.output)
        result.token_count = summarized_tokens
        result.metadata.update(
            {
                "summarized": True,
                "original_tokens": token_count,
                "summarized_tokens": summarized_tokens,
                "summarization_strategy": (
                    self.summarizer.strategy.value if self.summarizer else "legacy"
                ),
                "content_type": content_type,
            }
        )

        logger.info(f"Step {step_name}: {token_count} -> {summarized_tokens} tokens")

    async def _run_legacy_summarizer(self, text: str, max_tokens: int) -> str:
        """Run legacy callable summarizer (sync or async)."""
        import inspect

        if inspect.iscoroutinefunction(self._legacy_summarizer):
            return await self._legacy_summarizer(text, max_tokens)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._legacy_summarizer, text, max_tokens
        )

    def _to_string(self, output: Any) -> str:
        """Convert output to string."""
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            return json.dumps(output, indent=2, default=str)
        if hasattr(output, "model_dump"):
            return json.dumps(output.model_dump(), indent=2, default=str)
        return str(output)

    def _parse_summary(self, summarized: str, original: Any) -> Any:
        """Try to restore original type from summary."""
        if isinstance(original, str):
            return summarized
        if isinstance(original, dict):
            try:
                return json.loads(summarized)
            except json.JSONDecodeError:
                return {"summary": summarized, "_summarized": True}
        return summarized


# Factory functions
def create_openai_summarizer(
    model: str = "gpt-4",
    api_key: str | None = None,
    strategy: SummarizationStrategy = SummarizationStrategy.MAP_REDUCE,
    **kwargs,
) -> LangChainSummarizer:
    """Create a summarizer using OpenAI."""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)
    return LangChainSummarizer(llm=llm, strategy=strategy, **kwargs)


def create_anthropic_summarizer(
    model: str = "claude-3-sonnet-20240229",
    api_key: str | None = None,
    strategy: SummarizationStrategy = SummarizationStrategy.MAP_REDUCE,
    **kwargs,
) -> LangChainSummarizer:
    """Create a summarizer using Anthropic Claude."""
    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(model=model, api_key=api_key, temperature=0)
    return LangChainSummarizer(llm=llm, strategy=strategy, **kwargs)


def create_gateway_summarizer(
    server_url: str | None = None,
    model_name: str | None = None,
    oauth_endpoint: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    api_key: str | None = None,
    strategy: SummarizationStrategy = SummarizationStrategy.MAP_REDUCE,
    **kwargs,
) -> LangChainSummarizer:
    """
    Create a summarizer using the LLM Gateway client.

    Uses OAuth authentication for enterprise environments.

    Usage:
        # From environment variables
        summarizer = create_gateway_summarizer()

        # With explicit config
        summarizer = create_gateway_summarizer(
            server_url="https://llm.company.com/v1",
            model_name="gpt-4",
            oauth_endpoint="https://auth.company.com/oauth/token",
            client_id="my-client-id",
            client_secret="my-secret",
        )
    """
    from flowforge.services.llm_gateway import get_llm_client

    gateway_client = get_llm_client(
        server_url=server_url,
        model_name=model_name,
        oauth_endpoint=oauth_endpoint,
        client_id=client_id,
        client_secret=client_secret,
        api_key=api_key,
    )

    # Get LangChain-compatible LLM from gateway client
    llm = gateway_client.get_langchain_llm()
    return LangChainSummarizer(llm=llm, strategy=strategy, **kwargs)


def create_domain_aware_middleware(
    llm: Any | None = None,
    max_tokens: int = 4000,
    **kwargs,
) -> SummarizerMiddleware:
    """
    Create a summarizer middleware pre-configured for CMPT chain agents.

    Maps each agent step to its domain-specific prompts:
    - sec_filing: Extracts revenue, margins, guidance, risks
    - earnings: Extracts EPS, beats/misses, growth rates
    - news: Extracts events, dates, sentiment
    - transcripts: Extracts management commentary, Q&A insights
    - pricing: Extracts multiples, targets, comparisons

    Usage:
        middleware = create_domain_aware_middleware(llm=my_llm)
        forge.use(middleware)
    """
    summarizer = LangChainSummarizer(llm=llm) if llm else None

    return SummarizerMiddleware(
        summarizer=summarizer,
        max_tokens=max_tokens,
        step_content_types={
            # Map step names to content types
            "fetch_sec": "sec_filing",
            "fetch_sec_filings": "sec_filing",
            "sec_filing": "sec_filing",
            "fetch_earnings": "earnings",
            "earnings": "earnings",
            "fetch_news": "news",
            "news": "news",
            "fetch_transcripts": "transcripts",
            "transcripts": "transcripts",
            "fetch_pricing": "pricing",
            "pricing": "pricing",
        },
        **kwargs,
    )


# Backward compatibility alias
LLMSummarizer = LangChainSummarizer
