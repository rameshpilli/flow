"""
LLM Gateway Classifier implementation.

Uses the existing LLMGatewayClient from agentorchestrator.services.llm_gateway
for intent classification, working behind corporate proxy with OAuth authentication.

Features:
    - LLM-based semantic classification (not keyword matching)
    - Session/context awareness via chat history
    - Confidence scoring with configurable thresholds
    - User profile/preference integration
    - Fallback routing support
    - OTEL tracing integration
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Any

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
# Import tracing for observability
from agentorchestrator.utils.tracing import trace_span, noop_context

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
        confidence_threshold: Minimum confidence to route (below = use default)
        include_history: Include chat history in classification context
        max_history_messages: Max history messages to include
        user_context_key: Key for user context/profile in additional_params
        enable_tracing: Enable OTEL tracing spans
    """
    llm_client: Optional[LLMGatewayClient] = None
    model_name: Optional[str] = None
    temperature: float = 0.1  # Low temperature for consistent classification
    max_tokens: int = 256  # Classification responses are short
    confidence_threshold: float = 0.6  # Minimum confidence to route
    include_history: bool = True  # Include chat history in context
    max_history_messages: int = 5  # Max history messages for context
    user_context_key: str = "user_profile"  # Key for user context
    enable_tracing: bool = True  # Enable OTEL tracing
    timeout_seconds: float = 30.0  # Timeout for LLM classification call


class LLMGatewayClassifier(Classifier):
    """
    Classifier that uses the existing LLMGatewayClient for intent classification.

    Works with the corporate LLM Gateway using OAuth authentication,
    bypassing direct calls to Anthropic/OpenAI APIs.

    Features:
        - Context-aware: Uses chat history for better classification
        - User-aware: Can incorporate user profile/preferences
        - Observable: OTEL tracing support
        - Configurable: Confidence thresholds, history limits

    Example:
        ```python
        from agentorchestrator.squad.classifiers import LLMGatewayClassifier
        from agentorchestrator.services.llm_gateway import LLMGatewayClient

        # Using default client (set via set_default_llm_client)
        classifier = LLMGatewayClassifier()

        # With context awareness
        classifier = LLMGatewayClassifier(
            options=LLMGatewayClassifierOptions(
                include_history=True,
                max_history_messages=10,
                confidence_threshold=0.7,
            )
        )

        # Classify with history and user context
        result = await classifier.classify(
            input_text="What about the API rate limits?",
            chat_history=history,
            additional_params={"user_profile": {"role": "developer"}}
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
        self.confidence_threshold = options.confidence_threshold
        self.include_history = options.include_history
        self.max_history_messages = options.max_history_messages
        self.user_context_key = options.user_context_key
        self.enable_tracing = options.enable_tracing
        self.timeout_seconds = options.timeout_seconds

        # Metrics tracking
        self._classification_count = 0
        self._total_latency_ms = 0.0
        self._error_count = 0

    def _build_context_prompt(
        self,
        input_text: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Build a context-aware prompt for classification.

        Args:
            input_text: Current user input
            chat_history: Conversation history
            additional_params: Additional context (user profile, etc.)

        Returns:
            Enriched prompt with context
        """
        context_parts = []

        # Add user profile/context if available
        if additional_params:
            user_profile = additional_params.get(self.user_context_key)
            if user_profile:
                context_parts.append(f"<user_context>\n{user_profile}\n</user_context>")

        # Add conversation history for context
        if self.include_history and chat_history:
            history_messages = chat_history[-self.max_history_messages:]
            history_text = []
            for msg in history_messages:
                role = msg.role
                text = msg.get_text() if hasattr(msg, 'get_text') else ""
                if text:
                    history_text.append(f"{role}: {text}")

            if history_text:
                context_parts.append(
                    f"<conversation_history>\n{chr(10).join(history_text)}\n</conversation_history>"
                )

        # Build final prompt
        if context_parts:
            context_section = "\n\n".join(context_parts)
            return f"{context_section}\n\n<current_query>\n{input_text}\n</current_query>"
        return input_text

    async def process_request(
        self,
        input_text: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]] = None,
    ) -> ClassifierResult:
        """
        Classify the user input using LLM Gateway with full context.

        Args:
            input_text: User's input text
            chat_history: Conversation history
            additional_params: Additional context (user profile, RAG results, etc.)

        Returns:
            ClassifierResult with selected agent and confidence
        """
        start_time = time.perf_counter()

        # Build trace attributes
        trace_attrs = {
            "classifier.type": "llm_gateway",
            "classifier.history_length": len(chat_history) if chat_history else 0,
            "classifier.has_user_context": bool(
                additional_params and additional_params.get(self.user_context_key)
            ),
        }

        try:
            with trace_span("classifier.classify", attributes=trace_attrs) if self.enable_tracing else noop_context():
                # Build context-aware prompt
                enriched_prompt = self._build_context_prompt(
                    input_text, chat_history, additional_params
                )

                # Call LLM for classification with timeout
                response = await asyncio.wait_for(
                    self.llm_client.generate_async(
                        prompt=enriched_prompt,
                        system_prompt=self.system_prompt,
                        max_tokens=self.max_tokens,
                    ),
                    timeout=self.timeout_seconds
                )

                logger.debug(f"Classifier raw response: {response}")

                # Parse the response
                result = self.parse_classification_response(response)

                # Apply confidence threshold
                if result.confidence < self.confidence_threshold:
                    logger.info(
                        f"Confidence {result.confidence:.2f} below threshold "
                        f"{self.confidence_threshold:.2f}, will use default agent"
                    )
                    # Don't nullify agent, let orchestrator handle default

                # Track metrics
                latency_ms = (time.perf_counter() - start_time) * 1000
                self._classification_count += 1
                self._total_latency_ms += latency_ms

                logger.info(
                    f"Classified intent: agent={result.selected_agent.id if result.selected_agent else 'None'}, "
                    f"confidence={result.confidence:.2f}, latency={latency_ms:.1f}ms"
                )

                return result

        except asyncio.TimeoutError:
            self._error_count += 1
            logger.error(f"Classification timed out after {self.timeout_seconds}s")
            return ClassifierResult(selected_agent=None, confidence=0.0)
        except Exception as e:
            self._error_count += 1
            logger.error(f"Classification failed: {e}")
            return ClassifierResult(selected_agent=None, confidence=0.0)

    async def classify(
        self,
        input_text: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]] = None,
    ) -> ClassifierResult:
        """
        Alias for process_request with additional_params support.

        This is the preferred method for context-aware classification.
        """
        return await self.process_request(input_text, chat_history, additional_params)

    def get_metrics(self) -> dict[str, Any]:
        """
        Get classifier metrics.

        Returns:
            Dict with classification count, avg latency, error count, etc.
        """
        avg_latency = (
            self._total_latency_ms / self._classification_count
            if self._classification_count > 0 else 0.0
        )
        return {
            "classification_count": self._classification_count,
            "error_count": self._error_count,
            "total_latency_ms": self._total_latency_ms,
            "avg_latency_ms": avg_latency,
            "confidence_threshold": self.confidence_threshold,
        }

    def reset_metrics(self) -> None:
        """Reset all metrics counters."""
        self._classification_count = 0
        self._total_latency_ms = 0.0
        self._error_count = 0

    def set_llm_client(self, client: LLMGatewayClient) -> None:
        """
        Set a new LLM client.

        Args:
            client: LLMGatewayClient instance from services/llm_gateway.py
        """
        self.llm_client = client
