"""
Parallel Steps Example
======================

Demonstrates parallel execution of independent steps.

Usage:
    python parallel_steps.py

What this example demonstrates:
    - Steps without dependencies run in parallel
    - Multiple data sources feeding into aggregation
    - Performance benefits of DAG-based execution

Expected output:
    Starting parallel fetches...
    [fetch_news] Starting (will take 1s)
    [fetch_stocks] Starting (will take 1s)
    [fetch_weather] Starting (will take 1s)
    [fetch_news] Complete
    [fetch_stocks] Complete
    [fetch_weather] Complete
    [combine] Aggregating results...

    Total time: ~1s (not 3s!)

Architecture:
    ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
    │ fetch_news  │  │ fetch_stocks │  │fetch_weather │
    └──────┬──────┘  └──────┬───────┘  └──────┬───────┘
           │                │                 │
           └────────────────┼─────────────────┘
                            │
                     ┌──────▼──────┐
                     │   combine   │
                     └─────────────┘
"""

from __future__ import annotations

import asyncio
import time

from agentorchestrator import AgentOrchestrator


def create_parallel_orchestrator() -> AgentOrchestrator:
    """
    Create an orchestrator with parallel steps.

    Three independent fetch steps run in parallel,
    then combine step aggregates the results.

    Returns:
        Configured AgentOrchestrator instance
    """
    ao = AgentOrchestrator(name="parallel_example", isolated=True)

    @ao.step(name="fetch_news", description="Fetch news headlines")
    async def fetch_news(ctx):
        """Fetch news data (simulated 1s latency)."""
        print("[fetch_news] Starting (will take 1s)")
        await asyncio.sleep(1)  # Simulate API latency

        news = [
            {"title": "Tech stocks rally", "sentiment": "positive"},
            {"title": "Market volatility continues", "sentiment": "neutral"},
        ]
        ctx.set("news", news)
        print("[fetch_news] Complete")

        return {"source": "news", "count": len(news)}

    @ao.step(name="fetch_stocks", description="Fetch stock prices")
    async def fetch_stocks(ctx):
        """Fetch stock data (simulated 1s latency)."""
        print("[fetch_stocks] Starting (will take 1s)")
        await asyncio.sleep(1)  # Simulate API latency

        stocks = {
            "AAPL": {"price": 150.25, "change": 2.5},
            "GOOGL": {"price": 140.00, "change": -1.2},
            "MSFT": {"price": 380.50, "change": 5.0},
        }
        ctx.set("stocks", stocks)
        print("[fetch_stocks] Complete")

        return {"source": "stocks", "count": len(stocks)}

    @ao.step(name="fetch_weather", description="Fetch weather data")
    async def fetch_weather(ctx):
        """Fetch weather data (simulated 1s latency)."""
        print("[fetch_weather] Starting (will take 1s)")
        await asyncio.sleep(1)  # Simulate API latency

        weather = {
            "temperature": 72,
            "condition": "sunny",
            "humidity": 45,
        }
        ctx.set("weather", weather)
        print("[fetch_weather] Complete")

        return {"source": "weather", "data": weather}

    @ao.step(
        name="combine",
        deps=["fetch_news", "fetch_stocks", "fetch_weather"],
        description="Combine all data sources",
    )
    async def combine(ctx):
        """
        Combine data from all sources.

        This step depends on all three fetch steps,
        so it runs only after they all complete.
        """
        print("[combine] Aggregating results...")

        news = ctx.get("news", [])
        stocks = ctx.get("stocks", {})
        weather = ctx.get("weather", {})

        # Create combined report
        report = {
            "news_count": len(news),
            "stocks_tracked": list(stocks.keys()),
            "weather_summary": f"{weather.get('temperature')}F, {weather.get('condition')}",
            "data_sources": 3,
        }

        return report

    @ao.chain(name="parallel_chain")
    class ParallelChain:
        """
        Chain with parallel data fetching.

        fetch_news, fetch_stocks, and fetch_weather have no
        dependencies on each other, so they run in parallel.
        combine waits for all three.
        """
        steps = ["fetch_news", "fetch_stocks", "fetch_weather", "combine"]

    return ao


async def run_parallel_example() -> dict:
    """
    Run the parallel execution example.

    Returns:
        Result dictionary with combined data
    """
    ao = create_parallel_orchestrator()

    print("Starting parallel fetches...")
    start_time = time.time()

    result = await ao.launch("parallel_chain", {})

    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed:.2f}s (would be 3s if sequential)")

    return result


def main():
    """CLI entry point."""
    result = asyncio.run(run_parallel_example())

    print("\nCombined Result:")
    print(f"  - News articles: {result.get('news_count')}")
    print(f"  - Stocks tracked: {result.get('stocks_tracked')}")
    print(f"  - Weather: {result.get('weather_summary')}")
    print(f"  - Data sources: {result.get('data_sources')}")


if __name__ == "__main__":
    main()
