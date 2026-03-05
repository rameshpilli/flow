"""
AgentOrchestrator Summarizer Middleware

Summarizes large text outputs to manage context size in LLM chains.
Supports stuff, map_reduce, and refine strategies via LangChain.

Domain-specific prompts should be registered at the application level,
not hardcoded in this package.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

from agentorchestrator.core.context import ChainContext, ContextScope, StepResult
from agentorchestrator.middleware.base import Middleware

logger = logging.getLogger(__name__)


# Token counting - shared utility
def count_tokens(text: str) -> int:
    """
    Count tokens using tiktoken if available, otherwise estimate (~4 chars/token).
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except (ImportError, Exception):
        # Fallback: estimate ~4 characters per token (conservative for English text)
        return len(text) // 4


class SummarizationStrategy(str, Enum):
    """
    Summarization strategies for handling large documents.

    Each strategy has different trade-offs:

    - STUFF: Single LLM call. Fast but limited by context window.
      Best for: Small documents under chunk_size tokens.

    - MAP_REDUCE: Parallel summarization then combine. Good parallelism.
      Best for: Medium documents (10K-50K tokens).

    - REFINE: Sequential refinement through chunks. High quality but slow.
      Best for: Documents where context continuity matters.

    - TREE: Hierarchical tree summarization. Most efficient for very large docs.
      Best for: Large documents (50K+ tokens), SEC filings, research reports.
      Example: 100K tokens -> Level 1 (25 summaries) -> Level 2 (5) -> Level 3 (1)
    """

    STUFF = "stuff"  # Single prompt (small docs)
    MAP_REDUCE = "map_reduce"  # Parallel chunks, then combine
    REFINE = "refine"  # Iterative refinement
    TREE = "tree"  # Hierarchical tree summarization (most efficient for large docs)


class LangChainSummarizer:
    """
    Summarizer using LangChain with stuff, map_reduce, refine, or tree strategies.
    Falls back to simple truncation if no LLM is provided.

    Domain-specific prompts can be registered via register_domain_prompts().

    Strategies:
    - STUFF: Single LLM call with all text (small documents)
    - MAP_REDUCE: Parallel chunk summarization then combine (medium documents)
    - REFINE: Sequential refinement (quality-critical documents)
    - TREE: Hierarchical tree summarization (large documents 50K+ tokens)
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
    DEFAULT_TREE_INTERMEDIATE_PROMPT = (
        "Summarize this content, preserving all key facts, numbers, dates, "
        "and named entities. This is an intermediate summary that will be "
        "combined with others:\n\n{text}\n\nIntermediate Summary:"
    )
    DEFAULT_TREE_FINAL_PROMPT = (
        "Create a comprehensive final summary from these intermediate summaries. "
        "Preserve all key facts, numbers, dates, and named entities from ALL summaries. "
        "Structure the output clearly:\n\n{text}\n\nFinal Comprehensive Summary:"
    )

    # Pluggable domain prompts (registered at application level)
    _domain_prompts: dict[str, dict[str, str]] = {}

    def __init__(
        self,
        llm: Any | None = None,
        strategy: SummarizationStrategy = SummarizationStrategy.MAP_REDUCE,
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        use_token_splitter: bool = False,  # Default to character splitter (no tiktoken dependency)
        domain: str | None = None,  # Default content type for domain-specific prompts
        map_prompt: str | None = None,
        reduce_prompt: str | None = None,
        refine_prompt: str | None = None,
        tree_intermediate_prompt: str | None = None,
        tree_final_prompt: str | None = None,
        tree_group_size: int = 4,  # Number of chunks/summaries to group at each tree level
        max_concurrent_chunks: int = 10,  # Limit parallel LLM calls to prevent rate limit issues
    ):
        self.llm = llm
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_concurrent_chunks = max_concurrent_chunks
        self.tree_group_size = tree_group_size
        self.domain = domain

        self.map_prompt = map_prompt or self.DEFAULT_MAP_PROMPT
        self.reduce_prompt = reduce_prompt or self.DEFAULT_REDUCE_PROMPT
        self.refine_prompt = refine_prompt or self.DEFAULT_REFINE_PROMPT
        self.tree_intermediate_prompt = tree_intermediate_prompt or self.DEFAULT_TREE_INTERMEDIATE_PROMPT
        self.tree_final_prompt = tree_final_prompt or self.DEFAULT_TREE_FINAL_PROMPT

        # Initialize text splitter
        self.text_splitter = self._create_splitter(use_token_splitter)

    @classmethod
    def register_domain_prompts(
        cls,
        domain: str,
        map_prompt: str,
        reduce_prompt: str | None = None,
    ) -> None:
        """
        Register domain-specific prompts for summarization.

        This should be called at the application level to customize
        summarization for your specific domain.

        Args:
            domain: Domain identifier (e.g., "order", "report", "document")
            map_prompt: Prompt template for initial summarization (must contain {text})
            reduce_prompt: Prompt template for combining summaries (must contain {text})

        Example:
            # At application startup
            LangChainSummarizer.register_domain_prompts(
                domain="order",
                map_prompt="Extract order details from this text:\\n{text}\\n\\nOrder Summary:",
                reduce_prompt="Combine order summaries:\\n{text}\\n\\nFinal Order Report:",
            )
        """
        cls._domain_prompts[domain] = {
            "map": map_prompt,
            "reduce": reduce_prompt or cls.DEFAULT_REDUCE_PROMPT,
        }
        logger.info(f"Registered domain prompts for: {domain}")

    @classmethod
    def get_domain_prompts(cls, domain: str) -> tuple[str, str]:
        """Get map/reduce prompts for a domain, or defaults if not found."""
        prompts = cls._domain_prompts.get(domain, {})
        return (
            prompts.get("map", cls.DEFAULT_MAP_PROMPT),
            prompts.get("reduce", cls.DEFAULT_REDUCE_PROMPT),
        )

    @classmethod
    def list_registered_domains(cls) -> list[str]:
        """List all registered domain types."""
        return list(cls._domain_prompts.keys())

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
            content_type: Domain type for specialized prompts (registered via register_domain_prompts)

        Returns:
            str: Summarized text

        Strategy Selection Guide:
            - STUFF: Text under chunk_size tokens
            - MAP_REDUCE: 10K-50K tokens, good parallelism
            - REFINE: Quality-critical, sequential
            - TREE: 50K+ tokens, most efficient for large docs
        """
        strategy = strategy or self.strategy
        if content_type is None and self.domain:
            content_type = self.domain

        # Apply domain-specific prompts if content_type provided
        original_map = self.map_prompt
        original_reduce = self.reduce_prompt
        if content_type and content_type in self._domain_prompts:
            self.map_prompt, self.reduce_prompt = self.get_domain_prompts(content_type)
            logger.info(f"Using domain prompts for: {content_type}")

        try:
            # Small text? Just use stuff strategy
            input_tokens = count_tokens(text)
            if input_tokens <= self.chunk_size:
                return await self._stuff_summarize(text, max_tokens)

            # Auto-select TREE for very large documents if using default strategy
            if strategy == SummarizationStrategy.MAP_REDUCE and input_tokens > 50000:
                logger.info(
                    f"Auto-selecting TREE strategy for large document "
                    f"({input_tokens} tokens > 50K threshold)"
                )
                strategy = SummarizationStrategy.TREE

            # Route to appropriate strategy
            handlers = {
                SummarizationStrategy.STUFF: self._stuff_summarize,
                SummarizationStrategy.MAP_REDUCE: self._map_reduce_summarize,
                SummarizationStrategy.REFINE: self._refine_summarize,
                SummarizationStrategy.TREE: self._tree_summarize,
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
            # Pass max_tokens via config if specified
            config = {"max_tokens": max_tokens} if max_tokens else {}
            return await chain.ainvoke({"text": text}, config=config)
        except Exception as e:
            logger.error(f"Stuff summarization failed: {e}")
            raise RuntimeError(f"Summarization failed: {e}") from e

    async def _map_reduce_summarize(self, text: str, max_tokens: int | None = None) -> str:
        """Summarize chunks in parallel (with concurrency limit), then combine."""
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
            logger.info(f"Map-Reduce: {len(chunks)} chunks (max concurrent: {self.max_concurrent_chunks})")

            # Map phase: summarize each chunk with concurrency limit
            map_chain = (
                ChatPromptTemplate.from_template(self.map_prompt) | self.llm | StrOutputParser()
            )
            config = {"max_tokens": max_tokens} if max_tokens else {}

            # Use semaphore to limit concurrent LLM calls and prevent rate limiting
            semaphore = asyncio.Semaphore(self.max_concurrent_chunks)

            async def summarize_chunk(chunk: str) -> str:
                async with semaphore:
                    return await map_chain.ainvoke({"text": chunk}, config=config)

            chunk_summaries = await asyncio.gather(
                *[summarize_chunk(chunk) for chunk in chunks]
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
            return await reduce_chain.ainvoke({"text": combined}, config=config)

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
            config = {"max_tokens": max_tokens} if max_tokens else {}

            # Start with first chunk
            initial_chain = (
                ChatPromptTemplate.from_template(self.map_prompt) | self.llm | StrOutputParser()
            )
            summary = await initial_chain.ainvoke({"text": chunks[0]}, config=config)

            # Refine with remaining chunks
            refine_chain = (
                ChatPromptTemplate.from_template(self.refine_prompt) | self.llm | StrOutputParser()
            )
            for chunk in chunks[1:]:
                summary = await refine_chain.ainvoke(
                    {
                        "existing_summary": summary,
                        "text": chunk,
                    },
                    config=config,
                )

            return summary

        except Exception as e:
            logger.error(f"Refine summarization failed: {e}")
            raise RuntimeError(f"Summarization failed: {e}") from e

    async def _tree_summarize(self, text: str, max_tokens: int | None = None) -> str:
        """
        Hierarchical tree summarization for very large documents.

        This is the most efficient strategy for documents over 50K tokens.
        It recursively groups and summarizes in a tree structure:

        Level 1: 16 chunks → 16 summaries (parallel)
        Level 2: 4 groups of 4 → 4 summaries (parallel)
        Level 3: 1 group of 4 → 1 final summary

        This reduces LLM calls compared to MAP_REDUCE for large documents
        while maintaining good parallelism.

        Args:
            text: Text to summarize
            max_tokens: Target maximum tokens for final output

        Returns:
            str: Final summarized text
        """
        if not self.llm:
            raise ValueError(
                "No LLM configured for summarization. "
                "Use create_openai_summarizer(), create_anthropic_summarizer(), "
                "or create_gateway_summarizer() to configure an LLM backend."
            )

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            # Split into initial chunks
            chunks = self.split_text(text)
            total_chunks = len(chunks)
            logger.info(
                f"Tree summarization: {total_chunks} chunks, "
                f"group_size={self.tree_group_size}, "
                f"max_concurrent={self.max_concurrent_chunks}"
            )

            # If only one chunk, just summarize it directly
            if len(chunks) == 1:
                chain = (
                    ChatPromptTemplate.from_template(self.tree_final_prompt)
                    | self.llm
                    | StrOutputParser()
                )
                return await chain.ainvoke({"text": chunks[0]})

            level = 1
            semaphore = asyncio.Semaphore(self.max_concurrent_chunks)

            # Keep processing until we have a single summary
            while len(chunks) > 1:
                # Group chunks
                groups = self._group_items(chunks, self.tree_group_size)
                logger.info(
                    f"Tree Level {level}: {len(chunks)} items → {len(groups)} groups"
                )

                # Determine if this is the final level
                is_final = len(groups) == 1

                # Select prompt based on level
                prompt_template = (
                    self.tree_final_prompt if is_final
                    else self.tree_intermediate_prompt
                )
                chain = (
                    ChatPromptTemplate.from_template(prompt_template)
                    | self.llm
                    | StrOutputParser()
                )

                # Summarize each group in parallel (with concurrency limit)
                async def summarize_group(group: list[str], group_idx: int) -> str:
                    async with semaphore:
                        combined = "\n\n---\n\n".join(group)
                        logger.debug(
                            f"Tree Level {level}, Group {group_idx}: "
                            f"{len(group)} items, {count_tokens(combined)} tokens"
                        )
                        return await chain.ainvoke({"text": combined})

                # Process all groups in parallel
                chunks = await asyncio.gather(*[
                    summarize_group(group, idx)
                    for idx, group in enumerate(groups)
                ])
                chunks = list(chunks)

                # Check if we're under target token count
                if max_tokens:
                    total_tokens = sum(count_tokens(c) for c in chunks)
                    if total_tokens <= max_tokens and len(chunks) <= self.tree_group_size:
                        # Can combine remaining chunks in final pass
                        logger.info(
                            f"Tree Level {level}: Under target ({total_tokens} <= {max_tokens}), "
                            f"proceeding to final combination"
                        )
                        if len(chunks) > 1:
                            final_chain = (
                                ChatPromptTemplate.from_template(self.tree_final_prompt)
                                | self.llm
                                | StrOutputParser()
                            )
                            combined = "\n\n---\n\n".join(chunks)
                            return await final_chain.ainvoke({"text": combined})
                        break

                level += 1

            final_summary = chunks[0]
            final_tokens = count_tokens(final_summary)
            logger.info(
                f"Tree summarization complete: {total_chunks} chunks → "
                f"{final_tokens} tokens in {level} levels"
            )
            return final_summary

        except Exception as e:
            logger.error(f"Tree summarization failed: {e}")
            raise RuntimeError(f"Summarization failed: {e}") from e

    def _group_items(self, items: list, group_size: int) -> list[list]:
        """Group items into batches of group_size."""
        return [items[i:i + group_size] for i in range(0, len(items), group_size)]

    async def summarize_with_query(
        self,
        text: str,
        query: str,
        max_tokens: int | None = None,
        strategy: SummarizationStrategy | None = None,
        content_type: str | None = None,
        relevance_threshold: float = 0.3,
    ) -> str:
        """
        Summarize text with query-aware filtering.

        This method first filters/extracts content relevant to the query,
        then summarizes. This is more efficient than summarizing everything
        when only query-relevant content is needed.

        Args:
            text: Text to summarize
            query: Query to filter relevance by
            max_tokens: Maximum tokens for output
            strategy: Summarization strategy
            content_type: Domain type for prompts
            relevance_threshold: Minimum relevance score (0-1) to include content

        Returns:
            str: Query-focused summary

        Example:
            >>> # Summarize SEC filing focusing on risk factors
            >>> summary = await summarizer.summarize_with_query(
            ...     text=sec_10k_filing,
            ...     query="What are the key risk factors?",
            ...     max_tokens=2000,
            ... )
        """
        if not self.llm:
            raise ValueError(
                "No LLM configured for summarization. "
                "Use create_openai_summarizer() or similar to configure an LLM backend."
            )

        logger.info(f"Query-aware summarization: '{query[:50]}...'")

        # Split into chunks
        chunks = self.split_text(text)
        logger.info(f"Query-aware: {len(chunks)} chunks to filter")

        # Filter chunks by query relevance
        relevant_chunks = await self._filter_by_relevance(
            chunks, query, relevance_threshold
        )

        if not relevant_chunks:
            logger.warning(
                f"Query-aware: No chunks passed relevance threshold ({relevance_threshold}), "
                "using all chunks"
            )
            relevant_chunks = chunks

        logger.info(
            f"Query-aware: {len(relevant_chunks)}/{len(chunks)} chunks relevant "
            f"(threshold: {relevance_threshold})"
        )

        # Combine relevant chunks
        filtered_text = "\n\n---\n\n".join(relevant_chunks)

        # Now summarize the filtered content with query focus
        return await self._query_focused_summarize(
            filtered_text, query, max_tokens, strategy, content_type
        )

    async def _filter_by_relevance(
        self,
        chunks: list[str],
        query: str,
        threshold: float,
    ) -> list[str]:
        """
        Filter chunks by relevance to query.

        Uses LLM to score each chunk's relevance (0-1).
        """
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            relevance_prompt = """Rate how relevant this text is to the query on a scale of 0.0 to 1.0.
Only output a single decimal number between 0.0 and 1.0.

Query: {query}

Text: {text}

Relevance Score (0.0-1.0):"""

            chain = (
                ChatPromptTemplate.from_template(relevance_prompt)
                | self.llm
                | StrOutputParser()
            )

            semaphore = asyncio.Semaphore(self.max_concurrent_chunks)

            async def score_chunk(chunk: str) -> tuple[str, float]:
                async with semaphore:
                    try:
                        # Truncate chunk if too long for scoring
                        truncated = chunk[:4000] if len(chunk) > 4000 else chunk
                        result = await chain.ainvoke({
                            "query": query,
                            "text": truncated,
                        })
                        # Parse score
                        score = float(result.strip())
                        return (chunk, min(1.0, max(0.0, score)))
                    except (ValueError, Exception) as e:
                        logger.debug(f"Failed to score chunk: {e}")
                        return (chunk, 0.5)  # Default to middle score

            # Score all chunks in parallel
            scored = await asyncio.gather(*[score_chunk(c) for c in chunks])

            # Filter by threshold
            relevant = [chunk for chunk, score in scored if score >= threshold]
            return relevant

        except Exception as e:
            logger.warning(f"Relevance filtering failed: {e}, using all chunks")
            return chunks

    async def _query_focused_summarize(
        self,
        text: str,
        query: str,
        max_tokens: int | None,
        strategy: SummarizationStrategy | None,
        content_type: str | None,
    ) -> str:
        """Summarize with query focus."""
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            query_prompt = """Summarize the following content, focusing specifically on information
relevant to this query: "{query}"

Preserve key facts, numbers, dates, and named entities that relate to the query.
Omit information that is not relevant to answering the query.

Content:
{text}

Query-Focused Summary:"""

            # If content is small enough, use single prompt
            if count_tokens(text) <= self.chunk_size * 2:
                chain = (
                    ChatPromptTemplate.from_template(query_prompt)
                    | self.llm
                    | StrOutputParser()
                )
                return await chain.ainvoke({"query": query, "text": text})

            # Otherwise, use the configured strategy but with query context
            # Store original prompts
            original_map = self.map_prompt
            original_reduce = self.reduce_prompt

            try:
                # Inject query into prompts
                self.map_prompt = f"""Summarize this content focusing on: "{query}"
Preserve facts relevant to the query.

Content:
{{text}}

Summary:"""

                self.reduce_prompt = f"""Combine these summaries into a final summary focused on: "{query}"
Preserve all facts relevant to answering the query.

Summaries:
{{text}}

Final Summary:"""

                return await self.summarize(
                    text, max_tokens, strategy, content_type
                )
            finally:
                self.map_prompt = original_map
                self.reduce_prompt = original_reduce

        except Exception as e:
            logger.error(f"Query-focused summarization failed: {e}")
            # Fallback to regular summarization
            return await self.summarize(text, max_tokens, strategy, content_type)


class SummarizerMiddleware(Middleware):
    """
    Middleware that summarizes large step outputs to manage context size.
    Triggers when output exceeds max_tokens threshold.

    Supports domain-specific summarization via step_content_types mapping.
    Register domain prompts at application level using LangChainSummarizer.register_domain_prompts().
    """

    def __init__(
        self,
        priority: int = 50,
        applies_to: list[str] | None = None,
        max_tokens: int = 4000,
        summarizer: LangChainSummarizer | Callable | None = None,
        preserve_original: bool = True,
        step_thresholds: dict[str, int] | None = None,
        step_max_tokens: dict[str, int] | None = None,  # Alias for step_thresholds
        step_strategies: dict[str, SummarizationStrategy] | None = None,
        step_content_types: dict[str, str] | None = None,
        strategy: SummarizationStrategy = SummarizationStrategy.MAP_REDUCE,
    ):
        """
        Args:
            priority: Middleware priority (lower runs first)
            applies_to: List of step names to apply to (None = all)
            max_tokens: Default token threshold for summarization
            summarizer: LangChainSummarizer instance or legacy callable
            preserve_original: Store original output in context before summarizing
            step_thresholds: Per-step token thresholds
            step_max_tokens: Alias for step_thresholds
            step_strategies: Per-step summarization strategy overrides
            step_content_types: Map step names to content types for domain-aware prompts.
                               Register prompts using LangChainSummarizer.register_domain_prompts()
            strategy: Default summarization strategy
        """
        super().__init__(priority=priority, applies_to=applies_to)
        self.max_tokens = max_tokens
        self.preserve_original = preserve_original
        combined_thresholds: dict[str, int] = {}
        if step_thresholds:
            combined_thresholds.update(step_thresholds)
        if step_max_tokens:
            combined_thresholds.update(step_max_tokens)
        self.step_thresholds = combined_thresholds
        self.step_strategies = step_strategies or {}
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

    def register_content_type(self, step_name: str, content_type: str) -> "SummarizerMiddleware":
        """
        Register a content type for a step.

        Args:
            step_name: Name of the step
            content_type: Domain type (must be registered via LangChainSummarizer.register_domain_prompts)

        Returns:
            self for chaining
        """
        self.step_content_types[step_name] = content_type
        return self

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """Summarize output if it exceeds token threshold."""
        if not result.success or result.output is None:
            return

        max_tokens = self.step_thresholds.get(step_name, self.max_tokens)
        content_type = self.step_content_types.get(step_name)
        strategy = self.step_strategies.get(step_name)
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
                output_str,
                max_tokens,
                strategy=strategy,
                content_type=content_type,
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
                    (strategy or self.summarizer.strategy).value if self.summarizer else "legacy"
                ),
                "content_type": content_type,
            }
        )

        # Update any context entries produced by this step
        updated_keys = ctx.update_step_outputs(step_name, result.output)
        if updated_keys:
            result.metadata["context_keys_updated"] = updated_keys

        logger.info(f"Step {step_name}: {token_count} -> {summarized_tokens} tokens")

    async def _run_legacy_summarizer(self, text: str, max_tokens: int) -> str:
        """Run legacy callable summarizer (sync or async)."""
        import inspect

        if inspect.iscoroutinefunction(self._legacy_summarizer):
            return await self._legacy_summarizer(text, max_tokens)
        return await asyncio.get_running_loop().run_in_executor(
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
    from agentorchestrator.services.llm_gateway import get_llm_client

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


def create_summarizer_middleware(
    llm: Any | None = None,
    max_tokens: int = 4000,
    step_content_types: dict[str, str] | None = None,
    **kwargs,
) -> SummarizerMiddleware:
    """
    Create a summarizer middleware.

    Domain-specific prompts should be registered at application level:

        # At application startup
        from agentorchestrator.middleware.summarizer import LangChainSummarizer

        LangChainSummarizer.register_domain_prompts(
            domain="report",
            map_prompt="Extract key data from this report:\\n{text}\\n\\nKey Data:",
            reduce_prompt="Combine report summaries:\\n{text}\\n\\nFinal Report:",
        )

        # Then create middleware with content type mapping
        middleware = create_summarizer_middleware(
            llm=my_llm,
            step_content_types={
                "generate_report": "report",
                "process_data": "report",
            }
        )

    Args:
        llm: LangChain-compatible LLM instance
        max_tokens: Default token threshold
        step_content_types: Map step names to registered domain types
        **kwargs: Additional SummarizerMiddleware arguments

    Returns:
        Configured SummarizerMiddleware
    """
    summarizer = LangChainSummarizer(llm=llm) if llm else None

    return SummarizerMiddleware(
        summarizer=summarizer,
        max_tokens=max_tokens,
        step_content_types=step_content_types or {},
        **kwargs,
    )


# Backward compatibility alias
LLMSummarizer = LangChainSummarizer
# Deprecated - use create_summarizer_middleware instead
create_domain_aware_middleware = create_summarizer_middleware