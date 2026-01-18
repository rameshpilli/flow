"""
LLM Gateway Classifier implementation.

Uses the existing LLMGatewayClient from agentorchestrator.services.llm_gateway
for intent classification, working behind corporate proxy with OAuth authentication.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from agentorchestrator.squad.classifiers.base import Classifier
from agentorchestrator.squad.types import (
    ClassifierResult,
    ConversationMessage,
)
# Import the existing LLMGatewayClient from services
from agentorchestrator.services.llm_gateway import (
    LLMGatewayClient,
    get_default_llm_client,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMGatewayClassifierOptions:
    """
    Configuration options for LLMGatewayClassifier.

    Attributes:
        llm_client: Pre-configured LLMGatewayClient (uses default if None)
        model_name: Override model name for classification
        temperature: Temperature for classification (lower = more deterministic)
        max_tokens: Max tokens for classification response
    """
    llm_client: Optional[LLMGatewayClient] = None
    model_name: Optional[str] = None
    temperature: float = 0.1  # Low temperature for consistent classification
    max_tokens: int = 256  # Classification responses are short


class LLMGatewayClassifier(Classifier):
    """
    Classifier that uses the existing LLMGatewayClient for intent classification.

    Works with the corporate LLM Gateway using OAuth authentication,
    bypassing direct calls to Anthropic/OpenAI APIs.

    Example:
        ```python
        from agentorchestrator.squad.classifiers import LLMGatewayClassifier
        from agentorchestrator.services.llm_gateway import LLMGatewayClient

        # Using default client (set via set_default_llm_client)
        classifier = LLMGatewayClassifier()

        # Using custom client
        client = LLMGatewayClient(
            server_url="https://llm-gateway/v1/chat/completions",
            oauth_endpoint="https://auth/token",
            client_id="...",
            client_secret="...",
        )
        classifier = LLMGatewayClassifier(
            options=LLMGatewayClassifierOptions(llm_client=client)
        )
        ```
    """

    def __init__(self, options: Optional[LLMGatewayClassifierOptions] = None):
        """
        Initialize the classifier.

        Args:
            options: Configuration options
        """
        super().__init__()

        options = options or LLMGatewayClassifierOptions()

        # Use provided client or fall back to default from services/llm_gateway.py
        self.llm_client = options.llm_client or get_default_llm_client()
        if not self.llm_client:
            # Create a stub client if none available
            logger.warning(
                "No LLMGatewayClient provided and no default set. "
                "Classification will run in stub mode."
            )
            self.llm_client = LLMGatewayClient()

        self.model_name = options.model_name
        self.temperature = options.temperature
        self.max_tokens = options.max_tokens

    async def process_request(
        self,
        input_text: str,
        chat_history: list[ConversationMessage]
    ) -> ClassifierResult:
        """
        Classify the user input using LLM Gateway.

        Args:
            input_text: User's input text
            chat_history: Conversation history

        Returns:
            ClassifierResult with selected agent and confidence
        """
        try:
            # Call LLM for classification using existing LLMGatewayClient
            response = await self.llm_client.generate_async(
                prompt=input_text,
                system_prompt=self.system_prompt,
                max_tokens=self.max_tokens,
            )

            logger.debug(f"Classifier raw response: {response}")

            # Parse the response
            result = self.parse_classification_response(response)

            logger.info(
                f"Classified intent: agent={result.selected_agent.id if result.selected_agent else 'None'}, "
                f"confidence={result.confidence:.2f}"
            )

            return result

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            # Return empty result on error
            return ClassifierResult(selected_agent=None, confidence=0.0)

    def set_llm_client(self, client: LLMGatewayClient) -> None:
        """
        Set a new LLM client.

        Args:
            client: LLMGatewayClient instance from services/llm_gateway.py
        """
        self.llm_client = client
