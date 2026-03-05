"""Deep Research Agent — AgentOrchestrator-based multi-source research service."""

from deep_research.config import settings
from deep_research.pipeline import CHAIN_NAME, build_pipeline

__all__ = ["build_pipeline", "CHAIN_NAME", "settings"]
