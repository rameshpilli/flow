"""
AgentOrchestrator Data Agents (Backward Compatibility)

This module re-exports agents from their individual files for backward compatibility.
New code should import directly from the specific agent files or from the agents package.

Recommended imports:
    from agentorchestrator.agents import SECFilingAgent, NewsAgent, EarningsAgent

Or import from individual files:
    from agentorchestrator.agents.sec_agent import SECFilingAgent
    from agentorchestrator.agents.news_agent import NewsAgent
    from agentorchestrator.agents.earnings_agent import EarningsAgent
"""

# Re-export for backward compatibility
from agentorchestrator.agents.sec_agent import SECFilingAgent
from agentorchestrator.agents.news_agent import NewsAgent
from agentorchestrator.agents.earnings_agent import EarningsAgent

__all__ = [
    "SECFilingAgent",
    "NewsAgent",
    "EarningsAgent",
]
