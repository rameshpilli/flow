"""
CMPT Data Agents - SEC filings, earnings transcripts, and news via MCP.
"""

import logging
import os
import time
from enum import Enum
from typing import Any

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.plugins.mcp_adapter import MCPAdapterAgent, MCPAdapterConfig
from agentorchestrator.testing import testable

logger = logging.getLogger(__name__)


class ToolName(Enum):
    """Data agent tool names."""
    EARNINGS_TOOL = "earnings_agent"
    NEWS_TOOL = "news_agent"
    SEC_TOOL = "sec_filing_agent"


def _create_mcp_config(name: str, url: str, token: str | None, timeout: float = 30.0) -> MCPAdapterConfig:
    """Create MCP adapter config with auth header if token provided."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return MCPAdapterConfig(
        name=name,
        server_url=url,
        transport="http",
        headers=headers,
        timeout_seconds=timeout,
        verify_ssl=False,  # Corporate self-signed certs
    )


def _agent_result(source: str, query: str, start: float, data: Any = None, error: str | None = None) -> AgentResult:
    """Helper to create AgentResult with timing."""
    return AgentResult(
        data=data or {"items": []},
        source=source,
        query=query,
        duration_ms=(time.perf_counter() - start) * 1000,
        error=error,
    )


class SECFilingAgent(MCPAdapterAgent):
    """Fetches SEC filings (10-K, 10-Q, 8-K) via MCP."""

    _ao_name = ToolName.SEC_TOOL.value

    def __init__(self, mcp_url: str | None = None, bearer_token: str | None = None, **kwargs):
        config = (_create_mcp_config("sec_mcp", mcp_url, bearer_token) 
                  if mcp_url else MCPAdapterConfig(name="sec_mcp"))
        super().__init__(config)

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch SEC filings for a company."""
        start = time.perf_counter()
        
        if not self._config.server_url:
            return _agent_result(self._ao_name, query, start, error="No MCP server configured")
        
        # Lazy initialization - connect if not already connected
        if not self._mcp_session:
            try:
                await self.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize SEC agent: {e}")
                return _agent_result(self._ao_name, query, start, error=f"Initialization failed: {e}")
        
        try:
            ticker = kwargs.get("ticker", query)
            filing_types = kwargs.get("types", ["10-K", "10-Q"])

            # Build args matching MCP tool schema:
            # reporting_entity (required), search_queries (required), keywords (required),
            # retrieve (required), filing_type_filters (default: [])
            args = {
                "reporting_entity": ticker,
                "search_queries": kwargs.get("search_queries", []),  # Required but can be empty
                "keywords": kwargs.get("keywords", []),  # Required but can be empty
                "retrieve": kwargs.get("quarters", 8),
                "filing_type_filters": [f"RNS-SEC-{t}" for t in filing_types] if filing_types else [],
            }
            result = await self.call_tool("sec_filing_retrieval_tool", args)
            return _agent_result(self._ao_name, query, start, data=result)
            
        except Exception as e:
            logger.error(f"SEC agent failed: {e}")
            return _agent_result(self._ao_name, query, start, error=str(e))


class EarningsAgent(MCPAdapterAgent):
    """Fetches earnings transcripts via MCP."""

    _ao_name = ToolName.EARNINGS_TOOL.value

    def __init__(self, mcp_url: str | None = None, bearer_token: str | None = None, **kwargs):
        config = (_create_mcp_config("earnings_mcp", mcp_url, bearer_token) 
                  if mcp_url else MCPAdapterConfig(name="earnings_mcp"))
        super().__init__(config)

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch earnings transcripts for a company."""
        start = time.perf_counter()
        
        if not self._config.server_url:
            return _agent_result(self._ao_name, query, start, error="No MCP server configured")
        
        # Lazy initialization - connect if not already connected
        if not self._mcp_session:
            try:
                await self.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize Earnings agent: {e}")
                return _agent_result(self._ao_name, query, start, error=f"Initialization failed: {e}")
        
        try:
            ticker = kwargs.get("ticker", query)
            fiscal_year = kwargs.get("fiscal_year", "2025")
            fiscal_quarter = kwargs.get("fiscal_quarter", "Q1")

            # Build args matching MCP tool schema:
            # query (required) - The tool expects a natural language query string
            earnings_query = f"{ticker} {fiscal_quarter} {fiscal_year} earnings call summary"

            args = {
                "query": earnings_query,
            }
            result = await self.call_tool("_earnings_call_analyzer_with_docs", args)
            return _agent_result(self._ao_name, query, start, data=result)
            
        except Exception as e:
            logger.error(f"Earnings agent failed: {e}")
            return _agent_result(self._ao_name, query, start, error=str(e))


class NewsAgent(MCPAdapterAgent):
    """Fetches news articles via MCP."""

    _ao_name = ToolName.NEWS_TOOL.value

    def __init__(self, mcp_url: str | None = None, bearer_token: str | None = None, **kwargs):
        config = (_create_mcp_config("news_mcp", mcp_url, bearer_token, timeout=20.0) 
                  if mcp_url else MCPAdapterConfig(name="news_mcp"))
        super().__init__(config)

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch news articles for a company."""
        start = time.perf_counter()
        
        if not self._config.server_url:
            return _agent_result(self._ao_name, query, start, error="No MCP server configured")
        
        # Lazy initialization - connect if not already connected
        if not self._mcp_session:
            try:
                await self.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize News agent: {e}")
                return _agent_result(self._ao_name, query, start, error=f"Initialization failed: {e}")
        
        try:
            ticker = kwargs.get("ticker", query)
            days = kwargs.get("days", 30)

            # Build args matching MCP tool schema:
            # search_query (string), entities (array), topics (array),
            # relative_date_range (any), absolute_date_range (any), news_source (any)
            args = {
                "search_query": f"{ticker} news",
                "entities": [ticker],
                "topics": kwargs.get("topics", []),
                "relative_date_range": f"last_{days}_days",  # e.g., "last_30_days"
            }
            result = await self.call_tool("news_retrieval_tool", args)
            return _agent_result(self._ao_name, query, start, data=result)
            
        except Exception as e:
            logger.error(f"News agent failed: {e}")
            return _agent_result(self._ao_name, query, start, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
#                           AGENT REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

def _load_mcp_configs_from_env() -> dict[str, dict[str, Any]]:
    """Load MCP configs from AGENT_CONFIG environment variable."""
    import json
    
    agent_configs_json = os.getenv("AGENT_CONFIG", "[]")
    agent_configs_list = json.loads(agent_configs_json)
    
    # Map by agent name
    config_map = {}
    for config in agent_configs_list:
        name = config.get("name")
        if name == "sec":
            config_map["sec_filing_agent"] = {
                "mcp_url": config.get("mcp_url"),
                "bearer_token": config.get("mcp_bearer_token"),
            }
        elif name == "earnings":
            config_map["earnings_agent"] = {
                "mcp_url": config.get("mcp_url"),
                "bearer_token": config.get("mcp_bearer_token"),
            }
        elif name == "news":
            config_map["news_agent"] = {
                "mcp_url": config.get("mcp_url"),
                "bearer_token": config.get("mcp_bearer_token"),
            }
    
    return config_map


@testable(
    agent_configs=_load_mcp_configs_from_env(),
    test_query="AAPL",
    test_params={"ticker": "AAPL", "max_results": 5}
)
def register_cmpt_agents(ao: Any) -> None:
    """
    Register CMPT agents with resilience configuration.
    
    Call ao.get_agent(name, mcp_url=..., bearer_token=...) to get instances.
    
    To test: await register_cmpt_agents.test(ao)
    """
    ao.agent(
        name=ToolName.SEC_TOOL.value,
        group="cmpt",
        description="Fetches SEC filings (10-K, 10-Q, 8-K)",
        resilient=True,
        resilient_config={"timeout_seconds": 30.0, "max_retries": 2},
    )(SECFilingAgent)
    
    ao.agent(
        name=ToolName.EARNINGS_TOOL.value,
        group="cmpt",
        description="Fetches earnings transcripts",
        resilient=True,
        resilient_config={"timeout_seconds": 30.0, "max_retries": 2},
    )(EarningsAgent)
    
    ao.agent(
        name=ToolName.NEWS_TOOL.value,
        group="cmpt",
        description="Fetches news articles",
        resilient=True,
        resilient_config={"timeout_seconds": 20.0, "max_retries": 2},
    )(NewsAgent)
    
    logger.info("Registered CMPT agents with resilience: SEC, Earnings, News")


def get_cmpt_agents(
    ao: Any,
    sec_url: str | None = None,
    earnings_url: str | None = None,
    news_url: str | None = None,
    sec_token: str | None = None,
    earnings_token: str | None = None,
    news_token: str | None = None,
) -> dict[str, BaseAgent]:
    """
    Get configured CMPT agent instances.
    
    Returns dict of {agent_name: agent_instance}.
    If URLs provided, creates real MCP agents. Otherwise creates mock agents.
    
    Note: MCP agents will auto-connect on first fetch() call.
    """
    # If MCP URLs provided, create real agents directly
    if sec_url or earnings_url or news_url:
        agents = {
            ToolName.SEC_TOOL.value: SECFilingAgent(mcp_url=sec_url, bearer_token=sec_token) if sec_url else SECFilingAgent(),
            ToolName.EARNINGS_TOOL.value: EarningsAgent(mcp_url=earnings_url, bearer_token=earnings_token) if earnings_url else EarningsAgent(),
            ToolName.NEWS_TOOL.value: NewsAgent(mcp_url=news_url, bearer_token=news_token) if news_url else NewsAgent(),
        }
        return agents
    
    # Otherwise, try to get registered agents from orchestrator
    return {
        ToolName.SEC_TOOL.value: ao.get_agent(ToolName.SEC_TOOL.value),
        ToolName.EARNINGS_TOOL.value: ao.get_agent(ToolName.EARNINGS_TOOL.value),
        ToolName.NEWS_TOOL.value: ao.get_agent(ToolName.NEWS_TOOL.value),
    }