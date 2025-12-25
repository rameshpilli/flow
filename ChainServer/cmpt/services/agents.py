"""
CMPT Data Agents

Agents for fetching SEC filings, earnings transcripts, and news via MCP.
These extend AgentOrchestrator's MCPAgent with CMPT-specific logic.
"""

import logging
import time

from agentorchestrator.agents.base import (
    AgentResult,
    BaseAgent,
    ResilientAgent,
    ResilientAgentConfig,
)
from agentorchestrator.connectors.base import ConnectorConfig
from agentorchestrator.connectors.mcp import MCPAgent

from cmpt.services._02_content_prioritization import ToolName

logger = logging.getLogger(__name__)


class SECFilingAgent(MCPAgent):
    """Agent for fetching SEC filings (10-K, 10-Q, 8-K)."""

    _ao_name = ToolName.SEC_TOOL.value

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch SEC filings for a company using params from Subquery."""
        start = time.perf_counter()
        try:
            if self.connector:
                # Use params from Subquery (propagated from GRID config)
                args = {
                    "reporting_entity": kwargs.get("ticker") or query,
                    "retrieve": kwargs.get("quarters", 8),
                    "filing_types": kwargs.get("types", ["10-K", "10-Q"]),
                    "max_results": kwargs.get("max_results", 20),
                }
                result = await self.connector.call_tool("search_sec", args)
                return AgentResult(data=result, source=self._ao_name, query=query, duration_ms=(time.perf_counter() - start) * 1000)
            return AgentResult(data={"items": []}, source=self._ao_name, query=query, duration_ms=(time.perf_counter() - start) * 1000, error="No MCP connector")
        except Exception as e:
            logger.error(f"SEC agent failed: {e}")
            return AgentResult(data=None, source=self._ao_name, query=query, duration_ms=(time.perf_counter() - start) * 1000, error=str(e))


class EarningsAgent(MCPAgent):
    """Agent for fetching earnings transcripts."""

    _ao_name = ToolName.EARNINGS_TOOL.value

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch earnings transcripts for a company using params from Subquery."""
        start = time.perf_counter()
        # Use params from Subquery (propagated from temporal context)
        ticker = kwargs.get("ticker") or query
        fiscal_year = kwargs.get("fiscal_year", "2025")
        fiscal_quarter = kwargs.get("fiscal_quarter", "Q1")
        quarters = kwargs.get("quarters", 4)
        try:
            if self.connector:
                args = {
                    "ticker": ticker,
                    "fiscal_year": fiscal_year,
                    "fiscal_quarter": fiscal_quarter,
                    "quarters": quarters,
                    "include_estimates": kwargs.get("include_estimates", True),
                    "include_historical": kwargs.get("include_historical", True),
                }
                result = await self.connector.call_tool("get_transcript", args)
                return AgentResult(data=result, source=self._ao_name, query=query, duration_ms=(time.perf_counter() - start) * 1000)
            return AgentResult(data={"items": []}, source=self._ao_name, query=query, duration_ms=(time.perf_counter() - start) * 1000, error="No MCP connector")
        except Exception as e:
            logger.error(f"Earnings agent failed: {e}")
            return AgentResult(data=None, source=self._ao_name, query=query, duration_ms=(time.perf_counter() - start) * 1000, error=str(e))


class NewsAgent(MCPAgent):
    """Agent for fetching news articles."""

    _ao_name = ToolName.NEWS_TOOL.value

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch news articles for a company using params from Subquery."""
        start = time.perf_counter()
        # Use params from Subquery (propagated from GRID config)
        ticker = kwargs.get("ticker") or query
        days = kwargs.get("days", 30)
        max_results = kwargs.get("max_results", 50)
        try:
            if self.connector:
                args = {
                    "search_query": f"{ticker} news",
                    "entities": [ticker],
                    "days": days,
                    "max_results": max_results,
                    "sentiment": kwargs.get("sentiment", True),
                }
                result = await self.connector.call_tool("search_news", args)
                return AgentResult(data=result, source=self._ao_name, query=query, duration_ms=(time.perf_counter() - start) * 1000)
            return AgentResult(data={"items": []}, source=self._ao_name, query=query, duration_ms=(time.perf_counter() - start) * 1000, error="No MCP connector")
        except Exception as e:
            logger.error(f"News agent failed: {e}")
            return AgentResult(data=None, source=self._ao_name, query=query, duration_ms=(time.perf_counter() - start) * 1000, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
#                           FACTORY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def create_cmpt_agents(sec_url: str | None = None, earnings_url: str | None = None, news_url: str | None = None) -> dict[str, BaseAgent]:
    """Create all CMPT agents with optional MCP URLs."""
    agents = {}

    for AgentClass, url, tool_name, timeout in [
        (SECFilingAgent, sec_url, ToolName.SEC_TOOL, 30.0),
        (EarningsAgent, earnings_url, ToolName.EARNINGS_TOOL, 30.0),
        (NewsAgent, news_url, ToolName.NEWS_TOOL, 20.0),
    ]:
        agent = AgentClass()
        if url:
            agent.connector_config = ConnectorConfig(name=f"{tool_name.value}_mcp", base_url=url)
        agents[tool_name.value] = ResilientAgent(agent=agent, config=ResilientAgentConfig(timeout_seconds=timeout, max_retries=2))

    return agents


def create_composite_agent(sec_url: str | None = None, earnings_url: str | None = None, news_url: str | None = None) -> BaseAgent:
    """Create a composite agent that fetches from all sources in parallel."""
    from agentorchestrator.agents.base import ResilientCompositeAgent

    agents = create_cmpt_agents(sec_url, earnings_url, news_url)
    return ResilientCompositeAgent(
        agents=list(agents.values()),
        config=ResilientAgentConfig(timeout_seconds=30.0, max_retries=2),
        name="cmpt_composite",
    )
