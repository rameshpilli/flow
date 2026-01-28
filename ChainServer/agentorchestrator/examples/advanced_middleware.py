"""
Advanced Middleware Examples
============================

This example demonstrates the enhanced middleware features:

1. Glob Pattern Matching - Apply middleware to steps using patterns
2. Token Budget Reservation - Explicit token allocation to prevent truncation
3. Tree Summarization - Hierarchical summarization for large documents
4. Rolling Summary - Incremental summarization for iterative data
5. Query-Aware Compression - Focus summarization on query-relevant content

Run this example:
    python -m agentorchestrator.examples.advanced_middleware
"""

import asyncio
import logging
from typing import Any

from agentorchestrator import AgentOrchestrator, ChainContext
from agentorchestrator.middleware import (
    BudgetStatus,
    Middleware,
    RollingSummaryMiddleware,
    SummarizationStrategy,
    SummarizerMiddleware,
    TokenBudget,
    TokenManagerMiddleware,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Example 1: Glob Pattern Matching
# =============================================================================


class LoggingMiddleware(Middleware):
    """Simple middleware that logs step execution with pattern matching."""

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        logger.info(f"[{self.__class__.__name__}] Starting: {step_name}")

    async def after(self, ctx: ChainContext, step_name: str, result: Any) -> None:
        logger.info(f"[{self.__class__.__name__}] Completed: {step_name}")


async def example_glob_patterns():
    """Demonstrate glob pattern matching for middleware."""
    print("\n" + "=" * 60)
    print("Example 1: Glob Pattern Matching")
    print("=" * 60)

    ao = AgentOrchestrator(name="glob_example", isolated=True)

    # Middleware that applies to all "gather_*" steps except "gather_final"
    ao.use(LoggingMiddleware(
        priority=10,
        applies_to=["gather_*"],  # Matches gather_news, gather_sec, etc.
        excludes=["gather_final"],  # But not gather_final
    ))

    # Middleware that applies to all steps with conditional logic
    ao.use(LoggingMiddleware(
        priority=20,
        applies_to=["process_*", "analyze_*"],
    ))

    # Define steps
    @ao.step(name="gather_news")
    async def gather_news(ctx: ChainContext):
        return {"articles": ["Article 1", "Article 2"]}

    @ao.step(name="gather_sec")
    async def gather_sec(ctx: ChainContext):
        return {"filings": ["10-K", "10-Q"]}

    @ao.step(name="gather_final")
    async def gather_final(ctx: ChainContext):
        # This step is excluded from the first middleware
        return {"summary": "Final gathered data"}

    @ao.step(name="process_data")
    async def process_data(ctx: ChainContext):
        return {"processed": True}

    @ao.step(name="analyze_results")
    async def analyze_results(ctx: ChainContext):
        return {"analysis": "Complete"}

    @ao.chain(name="pattern_chain")
    class PatternChain:
        steps = ["gather_news", "gather_sec", "gather_final", "process_data", "analyze_results"]

    # Run the chain
    result = await ao.launch("pattern_chain", {})
    print(f"\nChain completed: {result['success']}")
    print("Notice: gather_final was NOT logged by the first middleware (excluded)")


# =============================================================================
# Example 2: Token Budget Reservation
# =============================================================================


async def example_token_budget():
    """Demonstrate explicit token budget reservation."""
    print("\n" + "=" * 60)
    print("Example 2: Token Budget Reservation")
    print("=" * 60)

    # Create explicit budget allocation
    budget = TokenBudget(
        context_window=128000,      # GPT-4-turbo context
        reserved_output=8000,       # For model response
        reserved_system=3000,       # For system prompt
        reserved_history=15000,     # For chat history
        warning_threshold=0.8,
        critical_threshold=0.95,
    )

    print(f"Context window: {budget.context_window:,} tokens")
    print(f"Reserved for output: {budget.reserved_output:,} tokens")
    print(f"Reserved for system: {budget.reserved_system:,} tokens")
    print(f"Reserved for history: {budget.reserved_history:,} tokens")
    print(f"Available for content: {budget.available_for_content:,} tokens")

    # Test different usage levels
    test_cases = [
        (50000, "Normal usage"),
        (85000, "Approaching warning"),
        (95000, "Above warning"),
        (100000, "Critical"),
        (105000, "Overflow"),
    ]

    for tokens, description in test_cases:
        status = budget.get_status(tokens)
        report = budget.get_report(tokens)
        print(f"\n{description} ({tokens:,} tokens):")
        print(f"  Status: {status.value}")
        print(f"  Usage: {report['usage_percent']}%")
        print(f"  Action needed: {report['action_needed']}")
        if report['tokens_to_compress'] > 0:
            print(f"  Tokens to compress: {report['tokens_to_compress']:,}")


# =============================================================================
# Example 3: Tree Summarization
# =============================================================================


async def example_tree_summarization():
    """Demonstrate hierarchical tree summarization."""
    print("\n" + "=" * 60)
    print("Example 3: Tree Summarization")
    print("=" * 60)

    # Note: This example shows the structure. In production, you'd use:
    # summarizer = create_openai_summarizer(strategy=SummarizationStrategy.TREE)

    print("""
Tree summarization works hierarchically:

Input: 100K tokens (25 chunks of 4K each)
    │
    ├── Level 1: 25 chunks → 25 summaries (parallel)
    │   (Each 4K chunk → ~400 token summary)
    │
    ├── Level 2: Group into 7 sets of ~4 → 7 summaries
    │   (Each group of 4 summaries → ~300 token summary)
    │
    ├── Level 3: Group into 2 sets of ~4 → 2 summaries
    │
    └── Level 4: Final combination → 1 summary
        Output: ~800 tokens (99.2% reduction!)

Benefits over MAP_REDUCE:
- More efficient for very large documents (50K+ tokens)
- Better context preservation at each level
- Parallel execution at each level
    """)

    # Show strategy selection
    strategies = [
        (SummarizationStrategy.STUFF, "< 4K tokens", "Single prompt"),
        (SummarizationStrategy.MAP_REDUCE, "10K-50K tokens", "Parallel chunks, combine"),
        (SummarizationStrategy.REFINE, "Quality-critical", "Sequential refinement"),
        (SummarizationStrategy.TREE, "50K+ tokens", "Hierarchical tree"),
    ]

    print("\nStrategy Selection Guide:")
    print("-" * 60)
    print(f"{'Strategy':<15} {'Best For':<20} {'Description':<25}")
    print("-" * 60)
    for strategy, best_for, description in strategies:
        print(f"{strategy.value:<15} {best_for:<20} {description:<25}")


# =============================================================================
# Example 4: Rolling Summary
# =============================================================================


async def example_rolling_summary():
    """Demonstrate incremental rolling summarization."""
    print("\n" + "=" * 60)
    print("Example 4: Rolling Summary (Incremental Summarization)")
    print("=" * 60)

    print("""
Rolling Summary updates incrementally instead of re-summarizing everything:

Traditional approach (wasteful):
    Iteration 1: 15K tokens → summarize → 2K
    Iteration 2: 25K tokens (15K + 10K) → summarize ALL → 3K
    Iteration 3: 33K tokens (25K + 8K) → summarize ALL → 3.5K
    Total LLM calls process: 73K tokens

Rolling Summary approach (efficient):
    Iteration 1: 15K tokens → summarize → 2K
    Iteration 2: 10K NEW tokens → summarize NEW → merge → 3K
    Iteration 3: 8K NEW tokens → summarize NEW → merge → 3.5K
    Total LLM calls process: 33K tokens (55% reduction!)

Use cases:
- Pagination: Processing search results page by page
- Streaming: Accumulating real-time data
- Multi-source: Gathering from multiple APIs
    """)

    # Example configuration
    print("\nConfiguration example:")
    print("""
ao.use(RollingSummaryMiddleware(
    max_tokens=4000,                 # Max tokens for rolling summary
    summarizer=my_summarizer,        # LangChainSummarizer instance
    recent_buffer_tokens=1000,       # Keep last 1000 tokens in full
    applies_to=["gather_*"],         # Apply to all gather steps
))
    """)


# =============================================================================
# Example 5: Query-Aware Compression
# =============================================================================


async def example_query_aware():
    """Demonstrate query-focused summarization."""
    print("\n" + "=" * 60)
    print("Example 5: Query-Aware Compression")
    print("=" * 60)

    print("""
Query-aware compression filters content by relevance before summarizing:

Traditional summarization:
    Input: 100K token SEC filing
    Process: Summarize entire document
    Output: 4K token summary (all topics)

Query-aware summarization:
    Input: 100K token SEC filing
    Query: "What are the key risk factors?"

    Step 1: Split into chunks
    Step 2: Score each chunk's relevance to query (0.0-1.0)
    Step 3: Filter chunks below threshold (e.g., 0.3)
    Step 4: Summarize only relevant chunks with query focus

    Output: 2K token focused summary (just risks!)

Benefits:
- Smaller, more focused summaries
- Faster processing (fewer tokens to summarize)
- Better accuracy for specific questions
    """)

    # Example usage
    print("\nUsage example:")
    print("""
from agentorchestrator.middleware import create_openai_summarizer

summarizer = create_openai_summarizer(model="gpt-4")

# Summarize focusing on specific topic
summary = await summarizer.summarize_with_query(
    text=sec_10k_filing,
    query="What are the key risk factors and supply chain dependencies?",
    max_tokens=2000,
    relevance_threshold=0.3,  # Include chunks scoring >= 0.3
)
    """)


# =============================================================================
# Example 6: Combined Usage - Production Pattern
# =============================================================================


async def example_production_pattern():
    """Demonstrate combined middleware for production use."""
    print("\n" + "=" * 60)
    print("Example 6: Production Pattern (Combined Middleware)")
    print("=" * 60)

    print("""
Production-ready middleware stack for large document processing:

# 1. Token Budget with explicit reservations
budget = TokenBudget(
    context_window=128000,
    reserved_output=8000,
    reserved_system=3000,
    reserved_history=15000,
)

# 2. Summarizer with TREE strategy for large docs
summarizer = create_gateway_summarizer(
    strategy=SummarizationStrategy.TREE,
    tree_group_size=4,
)

# 3. Token Manager with auto-summarization
ao.use(TokenManagerMiddleware(
    budget=budget,
    auto_summarize=True,
    summarizer=summarizer,
    auto_offload=True,
    context_store=redis_store,
    target_ratio_after_compression=0.7,
    applies_to=["*"],
    excludes=["extract_*"],  # Don't manage extraction steps
))

# 4. Rolling summary for iterative gathering
ao.use(RollingSummaryMiddleware(
    max_tokens=4000,
    summarizer=summarizer,
    recent_buffer_tokens=1000,
    applies_to=["gather_*"],
))

# 5. Domain-specific summarization
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    max_tokens=4000,
    step_content_types={
        "gather_sec": "sec_filing",
        "gather_news": "news_article",
    },
    applies_to=["gather_*"],
    excludes=["gather_final"],
))

This stack ensures:
- Explicit token budget prevents context overflow
- Large documents use efficient TREE summarization
- Iterative data uses rolling summaries
- Domain-specific prompts for different content types
- Automatic offloading to Redis when needed
    """)


# =============================================================================
# Main
# =============================================================================


async def main():
    """Run all examples."""
    await example_glob_patterns()
    await example_token_budget()
    await example_tree_summarization()
    await example_rolling_summary()
    await example_query_aware()
    await example_production_pattern()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
