"""Anthropic Claude client — implements the same async interface as LLMGatewayClient.

Drop-in replacement for local testing. Set ANTHROPIC_API_KEY in your environment
or in local_llm/.env.local and call ClaudeClient.from_env().

Interface contract (matches LLMGatewayClient):
    await client.generate_async(prompt, max_tokens=2048, temperature=0.1) -> str
    await client.acomplete(prompt, **kwargs)                               -> str  (alias)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

# Load .env or .env.local if either exists (simple key=value parser, no dotenv dep)
for _env_name in (".env", ".env.local"):
    _env_file = Path(__file__).parent / _env_name
    if _env_file.exists():
        for line in _env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
        break


class ClaudeClient:
    """Anthropic Claude client wrapping the official SDK.

    Usage:
        client = ClaudeClient.from_env()
        text = await client.generate_async("What is 2+2?")
    """

    # Available models on this API key (confirmed):
    #   claude-haiku-4-5     — fastest, cheapest, good for search/ReAct steps
    #   claude-sonnet-4-5    — best quality/speed balance, ideal for reports  ← DEFAULT
    #   claude-sonnet-4-0    — slightly older sonnet
    #   claude-opus-4-5      — most powerful, slowest, use for very complex tasks
    #   claude-opus-4-0      — same family as above
    DEFAULT_MODEL = "claude-sonnet-4-5"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        default_system: str = "You are a helpful research assistant.",
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.default_system = default_system
        logger.info("ClaudeClient initialised — model=%s", self.model)

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_env(
        cls,
        model: str | None = None,
        default_system: str = "You are a helpful research assistant.",
    ) -> "ClaudeClient":
        """Create a client from ANTHROPIC_API_KEY in the environment."""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to local_llm/.env.local or export it in your shell."
            )
        chosen_model = model or os.environ.get("ANTHROPIC_MODEL", cls.DEFAULT_MODEL)
        return cls(api_key=api_key, model=chosen_model, default_system=default_system)

    # ── Core async call ───────────────────────────────────────────────────────

    async def generate_async(
        self,
        prompt: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        system: str | None = None,
        system_prompt: str | None = None,   # alias used by ReAct/ReflectionMiddleware
        **_kwargs: object,                   # absorb any other framework-specific kwargs
    ) -> str:
        """Generate text from a prompt string.

        Args:
            prompt:      The user prompt to send.
            max_tokens:  Maximum tokens to generate.
            temperature: Sampling temperature (0 = deterministic).
            system:      Override the system prompt for this call.

        Returns:
            The model's text response as a plain string.
        """
        sys_prompt = system or system_prompt or self.default_system
        logger.debug(
            "Claude call — model=%s max_tokens=%d temp=%.2f prompt_len=%d",
            self.model, max_tokens, temperature, len(prompt),
        )
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=sys_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        logger.debug("Claude response — %d chars, stop_reason=%s", len(text), response.stop_reason)
        return text

    # Alias so it also works if anything calls acomplete()
    async def acomplete(self, prompt: str, **kwargs: object) -> str:
        return await self.generate_async(prompt, **kwargs)

    # ── Usage info ────────────────────────────────────────────────────────────

    async def generate_with_usage(
        self,
        prompt: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> tuple[str, dict]:
        """Like generate_async but also returns token usage stats."""
        sys_prompt = self.default_system
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=sys_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "model": self.model,
        }
        return text, usage
