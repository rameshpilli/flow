"""
Advanced Middleware Examples
============================

This example demonstrates the enhanced middleware features:

1. Glob Pattern Matching - Apply middleware to steps using patterns
2. Token Budget Reservation - Explicit token allocation to prevent truncation
3. Tree Summarization - Hierarchical summarization for large documents
4. Rolling Summary - Incremental summarization for iterative data
5. Query-Aware Compression - Focus summarization on query-relevant content
6. Namespace-Aware Budgets - Per-agent token allocation for multi-agent systems
7. ResultAggregator with Pre-Summarization - Auto-compress before aggregation
8. Middleware Metrics - Monitor token usage and compression stats

Run this example:
    python -m agentorchestrator.examples.advanced_middleware
"""

import asyncio
import logging
from typing import Any

from agentorchestrator import AgentOrchestrator, ChainContext
from agentorchestrator.middleware import (
    BudgetAllocationStrategy,
    BudgetStatus,
    Middleware,
    NamespaceBudgetManager,
    RollingSummaryMiddleware,
    SummarizationStrategy,
    SummarizerMiddleware,
    TokenBudget,
    TokenManagerMiddleware,
)
from agentorchestrator.squad.context import ResultAggregator, AggregationStrategy

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
# Example 7: Namespace-Aware Budgets (Multi-Agent)
# =============================================================================


async def example_namespace_budgets():
    """Demonstrate per-agent token budget allocation."""
    print("\n" + "=" * 60)
    print("Example 7: Namespace-Aware Budgets (Multi-Agent)")
    print("=" * 60)

    # Create global budget
    global_budget = TokenBudget(
        context_window=128000,
        reserved_output=8000,
        reserved_system=3000,
        reserved_history=15000,
    )

    print(f"Global budget available: {global_budget.available_for_content:,} tokens")

    # Create namespace manager with PRIORITY allocation
    manager = NamespaceBudgetManager(
        global_budget=global_budget,
        strategy=BudgetAllocationStrategy.PRIORITY,
        min_namespace_tokens=5000,
    )

    # Register agent namespaces with different priorities
    manager.register_namespace("research_agent", priority=3)  # Gets more tokens
    manager.register_namespace("news_agent", priority=2)
    manager.register_namespace("summary_agent", priority=1)  # Gets fewer tokens

    # Allocate budgets
    manager.allocate()

    # Show allocation
    print("\nNamespace Allocations (PRIORITY strategy):")
    print("-" * 50)
    report = manager.get_report()
    for ns_id, ns_data in report["namespaces"].items():
        print(f"  {ns_id}:")
        print(f"    Priority: {ns_data['priority']}")
        print(f"    Allocated: {ns_data['allocated']:,} tokens")
        print(f"    Status: {ns_data['status']}")

    # Simulate usage
    print("\nSimulating usage...")
    manager.update_usage("research_agent", 30000)
    manager.update_usage("news_agent", 15000)
    manager.update_usage("summary_agent", 5000)

    # Show updated report
    print("\nAfter usage:")
    report = manager.get_report()
    for ns_id, ns_data in report["namespaces"].items():
        print(f"  {ns_id}: {ns_data['used']:,} / {ns_data['allocated']:,} "
              f"({ns_data['usage_ratio']*100:.1f}%) - {ns_data['status']}")

    # Show different allocation strategies
    print("\n\nAllocation Strategies:")
    print("-" * 50)
    strategies = [
        (BudgetAllocationStrategy.EQUAL, "Split equally among all namespaces"),
        (BudgetAllocationStrategy.PROPORTIONAL, "Allocate based on historical usage"),
        (BudgetAllocationStrategy.PRIORITY, "Higher priority gets more tokens"),
        (BudgetAllocationStrategy.FIXED, "Use predefined per-namespace allocations"),
    ]
    for strategy, description in strategies:
        print(f"  {strategy.value:<15} - {description}")


# =============================================================================
# Example 8: ResultAggregator with Pre-Summarization
# =============================================================================


async def example_result_aggregator():
    """Demonstrate ResultAggregator with automatic pre-summarization."""
    print("\n" + "=" * 60)
    print("Example 8: ResultAggregator with Pre-Summarization")
    print("=" * 60)

    print("""
ResultAggregator can auto-summarize large results before aggregation:

Without pre-summarization:
    Agent 1: 50K tokens  ─┐
    Agent 2: 30K tokens  ─┼─► Synthesis prompt = 100K tokens (overflow!)
    Agent 3: 20K tokens  ─┘

With pre-summarization (threshold=10K):
    Agent 1: 50K → summarize → 3K  ─┐
    Agent 2: 30K → summarize → 2K  ─┼─► Synthesis prompt = 7K tokens ✓
    Agent 3: 20K → summarize → 2K  ─┘

Configuration:
    """)

    print("""
from agentorchestrator.squad.context import ResultAggregator, AggregationStrategy
from agentorchestrator.middleware.summarizer import LangChainSummarizer

# Create summarizer
summarizer = LangChainSummarizer(strategy=SummarizationStrategy.MAP_REDUCE)

# Create aggregator with pre-summarization
aggregator = ResultAggregator(
    strategy=AggregationStrategy.SYNTHESIZE,
    summarizer=summarizer,
    pre_summarize_threshold_tokens=10000,  # Summarize results > 10K tokens
    pre_summarize_target_tokens=2000,      # Target size after summarization
)

# Add large results
aggregator.add_result("research_agent", data=huge_data, confidence=0.9)
aggregator.add_result("news_agent", data=large_data, confidence=0.85)

# Aggregate - large results auto-summarized before synthesis
result = await aggregator.aggregate(llm=llm_client)

# Check metrics
metrics = aggregator.get_metrics()
print(f"Results summarized: {metrics['results_summarized']}")
print(f"Tokens saved: {metrics['tokens_saved']:,}")
print(f"Compression ratio: {metrics['compression_ratio']:.1%}")
    """)

    # Demonstrate without actual LLM (mock data)
    print("\nMock demonstration:")
    print("-" * 50)

    # Create aggregator (without actual summarizer for demo)
    aggregator = ResultAggregator(
        strategy=AggregationStrategy.MERGE,
        pre_summarize_threshold_tokens=10000,
    )

    # Add mock results
    aggregator.add_result("agent_1", data={"findings": "Result 1"}, confidence=0.9)
    aggregator.add_result("agent_2", data={"analysis": "Result 2"}, confidence=0.85)
    aggregator.add_result("agent_3", data={"summary": "Result 3"}, confidence=0.8)

    # Aggregate (without pre-summarization since no summarizer)
    result = await aggregator.aggregate(pre_summarize=False)

    print(f"Aggregated data: {result.data}")
    print(f"Strategy used: {result.strategy.value}")
    print(f"Overall confidence: {result.confidence:.0%}")

    # Show metrics
    metrics = aggregator.get_metrics()
    print(f"\nMetrics:")
    print(f"  Total results: {metrics['total_results']}")
    print(f"  Valid results: {metrics['valid_results']}")
    print(f"  Conflicts detected: {metrics['conflicts_detected']}")


# =============================================================================
# Example 9: Middleware Metrics
# =============================================================================


async def example_middleware_metrics():
    """Demonstrate middleware metrics for monitoring."""
    print("\n" + "=" * 60)
    print("Example 9: Middleware Metrics")
    print("=" * 60)

    ao = AgentOrchestrator(name="metrics_example", isolated=True)

    # Add middleware
    ao.use(TokenManagerMiddleware(
        priority=10,
        budget=TokenBudget(context_window=100000),
    ))

    ao.use(SummarizerMiddleware(
        priority=20,
        max_tokens=4000,
        applies_to=["gather_*"],
    ))

    # Define a simple step
    @ao.step(name="gather_data")
    async def gather_data(ctx: ChainContext):
        return {"data": "Sample data " * 100}

    @ao.step(name="process_data", deps=["gather_data"])
    async def process_data(ctx: ChainContext):
        return {"processed": True}

    @ao.chain(name="metrics_chain")
    class MetricsChain:
        steps = ["gather_data", "process_data"]

    # List middleware
    print("Registered Middleware:")
    print("-" * 50)
    for mw in ao.list_middleware():
        print(f"  {mw['type']}")
        print(f"    Priority: {mw['priority']}")
        print(f"    Applies to: {mw['applies_to']}")
        print(f"    Has metrics: {mw['has_metrics']}")

    # Run chain
    await ao.launch("metrics_chain", {})

    # Get all metrics
    print("\n\nMiddleware Metrics (after execution):")
    print("-" * 50)
    metrics = ao.get_middleware_metrics()
    for mw_name, mw_metrics in metrics.items():
        print(f"\n{mw_name}:")
        if isinstance(mw_metrics, dict):
            for key, value in mw_metrics.items():
                if isinstance(value, float):
                    print(f"    {key}: {value:.2f}")
                elif isinstance(value, list) and len(value) > 3:
                    print(f"    {key}: [{len(value)} items]")
                else:
                    print(f"    {key}: {value}")

    # Get specific middleware metrics
    print("\n\nGet specific middleware:")
    print("-" * 50)
    print('ao.get_middleware_metrics("token_manager")')
    token_metrics = ao.get_middleware_metrics("tokenmanager")
    print(f"  Result: {token_metrics}")


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
    await example_namespace_budgets()
    await example_result_aggregator()
    await example_middleware_metrics()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
