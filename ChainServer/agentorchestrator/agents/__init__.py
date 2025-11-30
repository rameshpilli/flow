"""
AgentOrchestrator Agents Module

Provides base classes and pre-built agents for data fetching.

Base Classes:
    - BaseAgent: Abstract base for all agents
    - AgentResult: Standard result container
    - CompositeAgent: Combines multiple agents
    - ResilientAgent: Adds retry/circuit breaker to any agent

Pre-built Agents:
    - SECFilingAgent: Fetches SEC filings (10K, 10Q, 8K)
    - NewsAgent: Fetches news articles with sentiment
    - EarningsAgent: Fetches earnings data and estimates

Folder Structure:
    agents/
    ├── __init__.py          # This file - exports all agents
    ├── base.py              # BaseAgent, AgentResult, ResilientAgent
    ├── sec_agent.py         # SECFilingAgent
    ├── news_agent.py        # NewsAgent
    └── earnings_agent.py    # EarningsAgent

Usage:
    from agentorchestrator.agents import BaseAgent, AgentResult

    class MyAgent(BaseAgent):
        async def fetch(self, query: str, **kwargs) -> AgentResult:
            data = await self.call_api(query)
            return AgentResult(data=data, source="my_source", query=query)
"""

from agentorchestrator.agents.base import (
    AgentResult,
    BaseAgent,
    CompositeAgent,
    ResilienceConfig,  # Backward compatibility alias
    ResilientAgent,
    ResilientAgentConfig,
    ResilientCompositeAgent,
)

# Individual agent imports (split into separate files for clarity)
from agentorchestrator.agents.sec_agent import SECFilingAgent
from agentorchestrator.agents.news_agent import NewsAgent
from agentorchestrator.agents.earnings_agent import EarningsAgent

__all__ = [
    # Base classes
    "BaseAgent",
    "AgentResult",
    "CompositeAgent",
    # Resilient wrappers
    "ResilientAgent",
    "ResilientAgentConfig",
    "ResilienceConfig",  # Alias for ResilientAgentConfig
    "ResilientCompositeAgent",
    # Data agents
    "SECFilingAgent",
    "NewsAgent",
    "EarningsAgent",
]
