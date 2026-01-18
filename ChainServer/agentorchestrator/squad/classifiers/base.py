"""
Base Classifier interface for intent classification.

This module defines the abstract interface for classifying user
intents and routing them to appropriate agents.
"""

import re
from abc import ABC, abstractmethod
from typing import Optional, Any

from agentorchestrator.squad.types import (
    ClassifierResult,
    ConversationMessage,
)


# Type alias for template variables
TemplateVariables = dict[str, Any]


class Classifier(ABC):
    """
    Abstract base class for intent classifiers.

    Classifiers analyze user input and conversation history
    to determine which agent should handle the request.
    """

    # Default prompt template for classification
    DEFAULT_PROMPT_TEMPLATE = """
You are AgentMatcher, an intelligent assistant designed to analyze user queries and match them with
the most suitable agent. Your task is to understand the user's request,
identify key entities and intents, and determine which agent would be best equipped
to handle the query.

Important: The user's input may be a follow-up response to a previous interaction.
The conversation history, including the name of the previously selected agent, is provided.
If the user's input appears to be a continuation of the previous conversation
(e.g., "yes", "ok", "I want to know more", "1"), select the same agent as before.

Analyze the user's input and categorize it into one of the following agents:
<agents>
{{AGENT_DESCRIPTIONS}}
</agents>

If you are unable to select an agent, respond with "unknown".

Guidelines for classification:
- Agent Selection: Choose the most appropriate agent based on the nature of the query.
- For follow-up responses, use the same agent as the previous interaction.
- Confidence: Indicate how confident you are in the classification (0.0 to 1.0).
  - High (0.9+): Clear, straightforward requests or clear follow-ups
  - Medium (0.7-0.9): Requests with some ambiguity but likely classification
  - Low (<0.7): Vague or multi-faceted requests that could fit multiple categories
- Handle variations in user input, including different phrasings and synonyms.
- For short responses like "yes", "ok", or numerical answers, treat them as follow-ups.

Conversation history:
<history>
{{HISTORY}}
</history>

Respond in this exact format (no other text):
selected_agent: <agent_id>
confidence: <0.0-1.0>
"""

    def __init__(self):
        """Initialize the classifier with default settings."""
        self.agent_descriptions = ""
        self.history = ""
        self.custom_variables: TemplateVariables = {}
        self.prompt_template = self.DEFAULT_PROMPT_TEMPLATE
        self.system_prompt = ""
        self.agents: dict[str, Any] = {}  # Agent objects keyed by ID

    def set_agents(self, agents: dict[str, Any]) -> None:
        """
        Set the available agents for classification.

        Args:
            agents: Dictionary mapping agent IDs to Agent objects
        """
        self.agents = agents
        self.agent_descriptions = "\n\n".join(
            f"{agent.id}: {agent.description}"
            for agent in agents.values()
        )

    def set_history(self, messages: list[ConversationMessage]) -> None:
        """
        Set the conversation history for context.

        Args:
            messages: List of conversation messages
        """
        self.history = self.format_messages(messages)

    def set_system_prompt(
        self,
        template: Optional[str] = None,
        variables: Optional[TemplateVariables] = None
    ) -> None:
        """
        Set custom prompt template and/or variables.

        Args:
            template: Custom prompt template (uses default if None)
            variables: Custom variables to inject into template
        """
        if template:
            self.prompt_template = template
        if variables:
            self.custom_variables = variables
        self.update_system_prompt()

    @staticmethod
    def format_messages(messages: list[ConversationMessage]) -> str:
        """
        Format conversation messages as a string.

        Args:
            messages: List of conversation messages

        Returns:
            Formatted string representation
        """
        formatted = []
        for message in messages:
            text = message.get_text() if hasattr(message, 'get_text') else ""
            if not text and message.content:
                text = message.content[0].get("text", "")
            formatted.append(f"{message.role}: {text}")
        return "\n".join(formatted)

    async def classify(
        self,
        input_text: str,
        chat_history: list[ConversationMessage]
    ) -> ClassifierResult:
        """
        Classify user input and select appropriate agent.

        Args:
            input_text: User's input text
            chat_history: Conversation history

        Returns:
            ClassifierResult with selected agent and confidence
        """
        self.set_history(chat_history)
        self.update_system_prompt()
        return await self.process_request(input_text, chat_history)

    @abstractmethod
    async def process_request(
        self,
        input_text: str,
        chat_history: list[ConversationMessage]
    ) -> ClassifierResult:
        """
        Process the classification request.

        Subclasses must implement this to perform actual classification.

        Args:
            input_text: User's input text
            chat_history: Conversation history

        Returns:
            ClassifierResult with selected agent and confidence
        """
        pass

    def update_system_prompt(self) -> None:
        """Update the system prompt with current variables."""
        all_variables: TemplateVariables = {
            **self.custom_variables,
            "AGENT_DESCRIPTIONS": self.agent_descriptions,
            "HISTORY": self.history,
        }
        self.system_prompt = self.replace_placeholders(
            self.prompt_template, all_variables
        )

    @staticmethod
    def replace_placeholders(template: str, variables: TemplateVariables) -> str:
        """
        Replace {{PLACEHOLDER}} with variable values.

        Args:
            template: Template string with placeholders
            variables: Dictionary of variable values

        Returns:
            Template with placeholders replaced
        """
        def replacer(match):
            key = match.group(1)
            value = variables.get(key, match.group(0))
            if isinstance(value, list):
                return "\n".join(value)
            return str(value)

        return re.sub(r'\{\{(\w+)\}\}', replacer, template)

    def get_agent_by_id(self, agent_id: str) -> Optional[Any]:
        """
        Get an agent by its ID.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent object or None if not found
        """
        if not agent_id:
            return None
        # Handle cases where agent_id might have extra text
        clean_id = agent_id.split()[0].lower().strip()
        return self.agents.get(clean_id)

    def parse_classification_response(self, response: str) -> ClassifierResult:
        """
        Parse the LLM response into a ClassifierResult.

        Args:
            response: Raw LLM response text

        Returns:
            Parsed ClassifierResult
        """
        selected_agent = None
        confidence = 0.0

        # Parse selected_agent
        agent_match = re.search(r'selected_agent:\s*([^\n]+)', response, re.IGNORECASE)
        if agent_match:
            agent_id = agent_match.group(1).strip()
            if agent_id.lower() != "unknown":
                selected_agent = self.get_agent_by_id(agent_id)

        # Parse confidence
        confidence_match = re.search(r'confidence:\s*([\d.]+)', response, re.IGNORECASE)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
                confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
            except ValueError:
                confidence = 0.5

        return ClassifierResult(
            selected_agent=selected_agent,
            confidence=confidence
        )
