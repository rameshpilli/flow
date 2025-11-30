"""
News Agent

Fetches news articles and sentiment analysis via data providers like RavenPack.

Usage:
    from agentorchestrator.agents import NewsAgent

    agent = NewsAgent(config={"api_key": "..."})
    result = await agent.fetch("Apple Inc", days=30, include_sentiment=True)
"""

import logging
from typing import Any

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.core.decorators import agent

logger = logging.getLogger(__name__)


@agent(
    name="news_agent",
    version="1.0.0",
    description="Fetches news articles via RavenPack",
    capabilities=["search", "sentiment", "topics"],
)
class NewsAgent(BaseAgent):
    """
    Agent for fetching news articles.

    Data source: RavenPack
    Default period: 1 year (market cap), 30 days (others)

    Configuration:
        api_key: API key for the data provider
        base_url: Base URL for the API (default: https://api.ravenpack.com)

    Example:
        agent = NewsAgent(config={"api_key": "your-api-key"})

        # Fetch recent news with sentiment
        result = await agent.fetch("Apple Inc", days=30, include_sentiment=True)

        # Fetch news filtered by topics
        result = await agent.fetch(
            "AAPL",
            days=7,
            topics=["earnings", "product_launch"]
        )

        if result.success:
            print(f"Found {len(result.data['articles'])} articles")
            print(f"Overall sentiment: {result.data['sentiment']['score']}")
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key")
        self.base_url = self.config.get("base_url", "https://api.ravenpack.com")

    async def initialize(self) -> None:
        """Initialize the agent (called once before first use)."""
        logger.info("NewsAgent initialized")
        await super().initialize()

    async def fetch(
        self,
        query: str,
        days: int = 30,
        include_sentiment: bool = True,
        topics: list[str] | None = None,
        **kwargs,
    ) -> AgentResult:
        """
        Fetch news articles for a company.

        Args:
            query: Company name or ticker symbol
            days: Number of days to look back (default: 30)
            include_sentiment: Include sentiment analysis (default: True)
            topics: Filter by specific topics. Common topics include:
                - "earnings": Earnings-related news
                - "product_launch": Product announcements
                - "merger_acquisition": M&A news
                - "legal": Lawsuits, regulatory actions
                - "management": Executive changes
                - "analyst": Analyst ratings, price targets
            **kwargs: Additional parameters for the provider

        Returns:
            AgentResult containing:
                - data: Dict with articles list and sentiment scores
                - source: "news"
                - metadata: Days, sentiment flag, topics, provider info
        """
        import time

        start = time.perf_counter()

        try:
            data = await self._fetch_from_provider(query, days, include_sentiment, topics)

            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=data,
                source="news",
                query=query,
                duration_ms=duration,
                metadata={
                    "days": days,
                    "include_sentiment": include_sentiment,
                    "topics": topics,
                    "provider": "ravenpack",
                },
            )

        except Exception as e:
            logger.error(f"News fetch failed: {e}")
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source="news",
                query=query,
                duration_ms=duration,
                error=str(e),
            )

    async def _fetch_from_provider(
        self,
        query: str,
        days: int,
        include_sentiment: bool,
        topics: list[str] | None,
    ) -> dict[str, Any]:
        """
        Fetch from the actual data provider.

        Override this method to implement your specific provider integration.
        """
        # TODO: Implement actual RavenPack API integration
        # This is a placeholder that returns mock data
        return {
            "company": query,
            "articles": [],
            "period": f"Last {days} days",
            "sentiment": None if not include_sentiment else {"score": 0.0},
            "_mock": True,
        }

    async def health_check(self) -> bool:
        """Check if the news provider is accessible."""
        # TODO: Implement actual health check
        return True
