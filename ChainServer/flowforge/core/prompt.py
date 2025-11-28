"""
FlowForge Prompt Builder

Template-based prompt construction with support for:
- Variable substitution
- Data distribution weighting
- Prompt sanitization
- Multi-agent content aggregation
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """A reusable prompt template"""

    name: str
    template: str
    description: str = ""
    variables: list[str] = field(default_factory=list)
    sanitize: bool = False

    def render(self, **kwargs) -> str:
        """Render the template with variables"""
        result = self.template

        # Replace variables
        for key, value in kwargs.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value) if value else "")

        # Sanitize if needed
        if self.sanitize:
            result = PromptSanitizer.sanitize(result)

        return result


class PromptSanitizer:
    """
    Sanitizes prompts to avoid guardrail false positives.
    Pattern from existing ResponseBuilderAndGenerator.sanitize_prompt_for_guardrails
    """

    @staticmethod
    def sanitize(text: str) -> str:
        """Remove patterns that trigger false positive guardrail blocks"""
        # Remove chunk IDs that look like crypto addresses
        text = re.sub(r"chunk_id:\s*[A-Z0-9]{20,}", "chunk_id: REDACTED", text)
        text = re.sub(r"chunk_id=['\"][A-Z0-9]{20,}['\"]", "chunk_id='REDACTED'", text)

        # Remove document IDs
        text = re.sub(r"document_id:\s*[A-Z0-9]{15,}", "document_id: REDACTED", text)

        # Shorten URLs (keep domain but remove paths/parameters)
        text = re.sub(r"(https?://[^/\s]+)/[^\s]*", r"\1", text)

        # Remove long alphanumeric strings that look like account numbers
        text = re.sub(r"\b[A-Z0-9]{15,}\b", "REDACTED", text)

        return text


class PromptBuilder:
    """
    Builds prompts from templates and agent data.

    Features:
    - Template registration and reuse
    - Data distribution weighting
    - Agent content aggregation
    - Sanitization

    Usage:
        builder = PromptBuilder()

        builder.register_template(PromptTemplate(
            name="financial_metrics",
            template="Analyze {COMPANY_NAME}:\n{AGENT_DATA}",
        ))

        prompt = builder.build(
            "financial_metrics",
            agent_data={"sec_agent": "...", "news_agent": "..."},
            company_name="Apple Inc.",
            distribution={"sec_agent": 50, "news_agent": 30, "earnings_agent": 20},
        )
    """

    def __init__(self):
        self._templates: dict[str, PromptTemplate] = {}
        self._agent_formatters: dict[str, Callable] = {}

    def register_template(self, template: PromptTemplate) -> None:
        """Register a prompt template"""
        self._templates[template.name] = template
        logger.debug(f"Registered template: {template.name}")

    def register_agent_formatter(self, agent_name: str, formatter: Callable[[str], str]) -> None:
        """Register a custom formatter for agent content"""
        self._agent_formatters[agent_name] = formatter

    def build(
        self,
        template_name: str,
        agent_data: dict[str, str] | None = None,
        distribution: dict[str, int] | None = None,
        **kwargs,
    ) -> str:
        """
        Build a prompt from a template.

        Args:
            template_name: Name of registered template
            agent_data: Dict of agent_name -> content
            distribution: Dict of agent_name -> percentage weight
            **kwargs: Additional variables for template

        Returns:
            Rendered prompt string
        """
        template = self._templates.get(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")

        # Format agent data if provided
        if agent_data:
            formatted_data = self._format_agent_data(agent_data, distribution)
            kwargs["AGENT_DATA"] = formatted_data

            # Also add individual agent content
            for agent, content in agent_data.items():
                upper_agent = agent.upper().replace("_AGENT", "_AGENT_CONTENT")
                kwargs[upper_agent] = content

        # Add distribution percentages
        if distribution:
            for agent, pct in distribution.items():
                key = agent.upper().replace("_AGENT", "_percentage")
                kwargs[key] = pct

        return template.render(**kwargs)

    def _format_agent_data(
        self,
        agent_data: dict[str, str],
        distribution: dict[str, int] | None = None,
    ) -> str:
        """Format agent data with optional weighting"""
        parts = []

        for agent_name, content in agent_data.items():
            # Apply custom formatter if registered
            formatter = self._agent_formatters.get(agent_name)
            if formatter:
                content = formatter(content)

            # Build section
            pct = distribution.get(agent_name, 100) if distribution else 100
            section = f"[{agent_name.upper()}]\n"
            if distribution:
                section += f"Agent Guidance: Include {pct}% of response from this agent\n"
            section += content

            parts.append(section)

        return "\n\n".join(parts)


class ChunkFormatter:
    """
    Formats agent response chunks into structured text.
    Pattern from existing context_parser.
    """

    @staticmethod
    def format_chunks(raw_chunks: list[dict], agent_type: str = "default") -> str:
        """
        Format raw chunks into structured text.

        Args:
            raw_chunks: List of chunk dictionaries
            agent_type: Type of agent (affects parsing)

        Returns:
            Formatted string with CHUNK-N sections
        """
        formatted = []

        for idx, chunk in enumerate(raw_chunks, 1):
            # Extract text content
            text = chunk.get("text", "")
            if not text:
                continue

            # Build chunk header
            chunk_str = f"CHUNK-{idx}\n\n"

            # Build metadata section
            metadata = {k: v for k, v in chunk.items() if k != "text"}
            if metadata:
                chunk_str += "METADATA\n"
                for key, value in metadata.items():
                    if key.startswith("_"):  # Skip internal fields
                        continue
                    chunk_str += f"{key}: {value}\n"
                chunk_str += "\n"

            # Add content
            chunk_str += "CHUNK-CONTENT\n"
            chunk_str += text
            chunk_str += "\n\n"

            formatted.append(chunk_str)

        return "\n".join(formatted)

    @staticmethod
    def parse_earnings_format(text: str) -> list[dict]:
        """
        Parse earnings agent response format.
        Pattern from existing parse_earnings_agent_response.
        """
        chunks = []

        # Split by RetrievedChunkExtended
        chunk_strings = re.split(r"RetrievedChunkExtended\(", text)

        for chunk_str in chunk_strings:
            if not chunk_str.strip():
                continue

            try:
                chunk_data = {
                    "chunk_id": ChunkFormatter._extract(r"chunk_id='([^']*)'", chunk_str),
                    "score": ChunkFormatter._extract_float(r"score=([\d.]+)", chunk_str),
                    "text": ChunkFormatter._extract(r"'text':\s*['\"](.+?)['\"]", chunk_str),
                    "ticker": ChunkFormatter._extract(r"'TICKER':\s*'([^']*)'", chunk_str),
                    "event_date": ChunkFormatter._extract(r"'EVENT_DT':\s*'([^']*)'", chunk_str),
                    "title": ChunkFormatter._extract(r"'TITLE':\s*'([^']*)'", chunk_str),
                }
                if chunk_data.get("text"):
                    chunks.append(chunk_data)
            except Exception as e:
                logger.warning(f"Failed to parse chunk: {e}")
                continue

        return chunks

    @staticmethod
    def _extract(pattern: str, text: str) -> str | None:
        match = re.search(pattern, text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_float(pattern: str, text: str) -> float | None:
        match = re.search(pattern, text)
        return float(match.group(1)) if match else None


# Default prompt templates from existing code
DEFAULT_TEMPLATES = {
    "data_for_financial_metrics": PromptTemplate(
        name="data_for_financial_metrics",
        template="""[SEC_AGENT]
Agent Guidance:
- Primary source for all financial metrics
- Extract precise numbers from financial statements
- Look for year-over-year comparisons in financial statements
{SEC_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Use for forward guidance and quarterly commentary
- Extract YoY growth rates mentioned in management discussion
{EARNINGS_AGENT_CONTENT}

[NEWS_AGENT]
Agent Guidance:
- Extract current stock price and today's price movement if mentioned in recent articles
- Look for daily price changes (e.g., "stock up $1.39 or 0.56% today")
{NEWS_AGENT_CONTENT}
""",
    ),
    "data_for_strategic_analysis": PromptTemplate(
        name="data_for_strategic_analysis",
        template="""[NEWS_AGENT]
Agent Guidance:
- Include {NEWS_percentage}% of the response from this agent chunks
- Extract date, category, and source URL for each development
{NEWS_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Include {EARNINGS_percentage}% of the response from this agent chunks
{EARNINGS_AGENT_CONTENT}

[SEC_AGENT]
Agent Guidance:
- Include {SEC_percentage}% of the response from this agent chunks
{SEC_AGENT_CONTENT}
""",
        sanitize=True,
    ),
}


def get_default_prompt_builder() -> PromptBuilder:
    """Get a prompt builder with default templates"""
    builder = PromptBuilder()
    for template in DEFAULT_TEMPLATES.values():
        builder.register_template(template)
    return builder
