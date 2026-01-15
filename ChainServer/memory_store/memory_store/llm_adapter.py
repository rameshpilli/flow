"""
LLM Gateway Adapter for Mem0

This adapter integrates the existing LLM Gateway client with mem0's LLM interface.
It allows mem0 to use our centralized LLM gateway for generating embeddings and text.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LLMGatewayAdapter:
    """
    Adapter to use LLM Gateway with mem0.

    This provides a mem0-compatible interface while using our existing
    LLM Gateway infrastructure for authentication and routing.

    Note: Since mem0 primarily uses embeddings for vector search, and we're
    using Cohere Compass which has its own embedding model, this adapter
    is mainly used for optional LLM-based features in mem0.
    """

    def __init__(
        self,
        server_url: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        oauth_endpoint: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_key: str | None = None,
    ):
        """Initialize the LLM Gateway adapter."""
        self.server_url = server_url
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.api_key = api_key

        # OAuth settings
        self.oauth_endpoint = oauth_endpoint
        self.client_id = client_id
        self.client_secret = client_secret

        # Initialize the actual LLM Gateway client
        self._client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the LLM Gateway client."""
        try:
            # Import from the parent agentorchestrator package
            import sys
            from pathlib import Path

            # Add agentorchestrator to path if not already there
            parent_dir = Path(__file__).parent.parent
            if str(parent_dir) not in sys.path:
                sys.path.insert(0, str(parent_dir))

            from agentorchestrator.services.llm_gateway import LLMGatewayClient

            self._client = LLMGatewayClient(
                server_url=self.server_url,
                model_name=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
                oauth_endpoint=self.oauth_endpoint,
                client_id=self.client_id,
                client_secret=self.client_secret,
                api_key=self.api_key,
            )
            logger.info(
                f"LLM Gateway adapter initialized with model: {self.model_name}"
            )
        except ImportError as e:
            logger.warning(f"Could not import LLM Gateway client: {e}")
            self._client = None

    def _is_configured(self) -> bool:
        """Check if the adapter is properly configured."""
        return self._client is not None and self._client._is_configured()

    async def generate_async(
        self, prompt: str, system_prompt: str | None = None, **kwargs
    ) -> str:
        """
        Generate text from a prompt using the LLM Gateway.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            **kwargs: Additional generation parameters

        Returns:
            Generated text
        """
        if not self._is_configured():
            logger.warning("LLM Gateway not configured, returning stub response")
            return f"[Stub response for: {prompt[:50]}...]"

        try:
            response = await self._client.generate_async(
                prompt=prompt, system_prompt=system_prompt, **kwargs
            )
            return response
        except Exception as e:
            logger.error(f"LLM Gateway generation failed: {e}")
            raise

    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        """
        Synchronous wrapper for generate_async.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            **kwargs: Additional generation parameters

        Returns:
            Generated text
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.generate_async(prompt, system_prompt, **kwargs)
        )

    async def generate_embedding_async(self, text: str) -> list[float]:
        """
        Generate embeddings for text.

        Note: This is typically not used when Cohere Compass is configured,
        as Cohere provides its own embedding generation.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        if not self._is_configured():
            logger.warning("LLM Gateway not configured for embeddings")
            # Return a stub embedding (1024 dimensions for Cohere compatibility)
            return [0.0] * 1024

        # If the gateway supports embedding endpoints, call them
        # Otherwise, this is a placeholder
        logger.info("Embedding generation via LLM Gateway (placeholder)")
        return [0.0] * 1024

    def generate_embedding(self, text: str) -> list[float]:
        """
        Synchronous wrapper for generate_embedding_async.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.generate_embedding_async(text))


def create_llm_adapter_from_config(config: Any) -> LLMGatewayAdapter:
    """
    Create an LLM Gateway adapter from configuration.

    Args:
        config: MemoryStoreConfig instance

    Returns:
        Configured LLMGatewayAdapter
    """
    llm_config = config.llm
    return LLMGatewayAdapter(
        server_url=llm_config.server_url,
        model_name=llm_config.model_name,
        temperature=llm_config.temperature,
        max_tokens=llm_config.max_tokens,
        timeout=llm_config.timeout,
        oauth_endpoint=llm_config.oauth_endpoint,
        client_id=llm_config.client_id,
        client_secret=llm_config.client_secret,
        api_key=llm_config.api_key,
    )


__all__ = ["LLMGatewayAdapter", "create_llm_adapter_from_config"]
