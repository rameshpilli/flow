"""
SEC Filing Agent

Fetches SEC filings (10K, 10Q, 8K, proxy) via data providers like RavenPack.

Usage:
    from agentorchestrator.agents import SECFilingAgent

    agent = SECFilingAgent(config={"api_key": "..."})
    result = await agent.fetch("Apple Inc", filing_type="10K", quarters=8)
"""

import logging
from typing import Any

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.core.decorators import agent

logger = logging.getLogger(__name__)


@agent(
    name="sec_filing_agent",
    version="1.0.0",
    description="Fetches SEC filings via RavenPack",
    capabilities=["10K", "10Q", "8K", "proxy"],
)
class SECFilingAgent(BaseAgent):
    """
    Agent for fetching SEC filings.

    Data source: RavenPack (or similar provider)
    Default period: Last 8 quarters (revenue), Latest (others)

    Configuration:
        api_key: API key for the data provider
        base_url: Base URL for the API (default: https://api.ravenpack.com)

    Example:
        agent = SECFilingAgent(config={"api_key": "your-api-key"})

        # Fetch 10K filings
        result = await agent.fetch("Apple Inc", filing_type="10K")

        # Fetch last 4 quarters of 10Q filings
        result = await agent.fetch("AAPL", filing_type="10Q", quarters=4)

        if result.success:
            for filing in result.data["filings"]:
                print(f"{filing['type']}: {filing['date']}")
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key")
        self.base_url = self.config.get("base_url", "https://api.ravenpack.com")

    async def initialize(self) -> None:
        """Initialize the agent (called once before first use)."""
        logger.info("SECFilingAgent initialized")
        await super().initialize()

    async def fetch(
        self,
        query: str,
        filing_type: str | None = None,
        quarters: int = 8,
        **kwargs,
    ) -> AgentResult:
        """
        Fetch SEC filings for a company.

        Args:
            query: Company name or ticker symbol
            filing_type: Type of filing to fetch:
                - "10K": Annual reports
                - "10Q": Quarterly reports
                - "8K": Current reports (material events)
                - "proxy": Proxy statements
                - None: All filing types
            quarters: Number of quarters to fetch (default: 8)
            **kwargs: Additional parameters for the provider

        Returns:
            AgentResult containing:
                - data: Dict with company info and filings list
                - source: "sec_filing"
                - metadata: Filing type, quarters, provider info
        """
        import time

        start = time.perf_counter()

        try:
            data = await self._fetch_from_provider(query, filing_type, quarters)

            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=data,
                source="sec_filing",
                query=query,
                duration_ms=duration,
                metadata={
                    "filing_type": filing_type,
                    "quarters": quarters,
                    "provider": "ravenpack",
                },
            )

        except Exception as e:
            logger.error(f"SEC filing fetch failed: {e}")
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source="sec_filing",
                query=query,
                duration_ms=duration,
                error=str(e),
            )

    async def _fetch_from_provider(
        self,
        query: str,
        filing_type: str | None,
        quarters: int,
    ) -> dict[str, Any]:
        """
        Fetch from the actual data provider.

        Override this method to implement your specific provider integration.
        """
        # TODO: Implement actual RavenPack API integration
        # This is a placeholder that returns mock data
        return {
            "company": query,
            "filings": [],
            "period": f"Last {quarters} quarters",
            "_mock": True,
        }

    async def health_check(self) -> bool:
        """Check if the SEC filing provider is accessible."""
        # TODO: Implement actual health check
        return True
