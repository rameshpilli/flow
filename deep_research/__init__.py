"""Deep Research Agent — AgentOrchestrator-based multi-source research service."""

from deep_research.chain import CHAIN_NAME, build_pipeline
from deep_research.config import settings

__all__ = ["build_pipeline", "CHAIN_NAME", "settings"]
