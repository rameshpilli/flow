"""Local LLM adapter — drop-in replacement for LLMGatewayClient using Anthropic Claude."""

from local_llm.client import ClaudeClient

__all__ = ["ClaudeClient"]
