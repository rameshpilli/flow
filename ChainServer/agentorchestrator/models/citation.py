"""
Citation Models for AgentOrchestrator

Provides structured citation tracking for AI-generated content, enabling:
- Source attribution and provenance tracking
- Verification of claims against source documents
- Transparency and explainability in AI outputs

Based on best practices from:
- LlamaIndex CitationQueryEngine patterns
- RAG citation techniques
- Academic citation standards

Example Usage:
    from agentorchestrator.models import Citation, CitedValue

    # Simple citation
    citation = Citation(
        source_type="agent",
        source_name="sec_filing_agent",
        content="Revenue was $394.3 billion for fiscal year 2024",
        document_id="AAPL-10K-2024",
    )

    # Value with citation
    revenue = CitedValue(
        value=394.3,
        unit="billion USD",
        citations=[citation],
    )
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class CitationLevel(str, Enum):
    """Level of citation confidence/verification."""

    VERIFIED = "verified"  # Citation verified against source
    UNVERIFIED = "unverified"  # Citation provided but not verified
    INFERRED = "inferred"  # Value inferred, not directly cited
    NONE = "none"  # No citation available


class SourceReference(BaseModel):
    """
    Reference to a source document or data.

    This is the minimal reference - just enough to locate the source.
    Use Citation for full attribution with content.
    """

    source_type: str = Field(
        description="Type of source: 'agent', 'document', 'api', 'llm', 'database'"
    )
    source_name: str = Field(description="Name of the source (agent name, API name, etc.)")
    document_id: str | None = Field(
        default=None, description="Unique identifier for the document/record"
    )
    url: str | None = Field(default=None, description="URL to the source if available")
    timestamp: datetime | None = Field(
        default=None, description="When the source was accessed"
    )

    def __str__(self) -> str:
        parts = [f"{self.source_type}:{self.source_name}"]
        if self.document_id:
            parts.append(f"[{self.document_id}]")
        return " ".join(parts)


class Citation(BaseModel):
    """
    Full citation with source attribution and content.

    A Citation provides complete provenance for a piece of information:
    - Where it came from (source_type, source_name)
    - What the original content was (content)
    - Why it supports the claim (reasoning)
    - When it was retrieved (timestamp)

    Example:
        citation = Citation(
            source_type="agent",
            source_name="sec_filing_agent",
            content="Total net sales were $394,328 million...",
            reasoning="This directly states the annual revenue figure",
            document_id="AAPL-10K-2024-Q4",
            page_number=45,
        )
    """

    # Source identification
    source_type: str = Field(
        description="Type of source: 'agent', 'document', 'api', 'llm', 'database', 'user'"
    )
    source_name: str = Field(description="Name of the source (agent name, document title, etc.)")

    # Content
    content: str = Field(
        description="Verbatim quote or content from the source. Should be exact, not paraphrased."
    )
    reasoning: str | None = Field(
        default=None,
        description="Explanation of why this source supports the claim",
    )

    # Location within source
    document_id: str | None = Field(
        default=None, description="Unique identifier for the document/record"
    )
    page_number: int | None = Field(default=None, description="Page number if applicable")
    section: str | None = Field(default=None, description="Section or heading in the document")
    line_range: tuple[int, int] | None = Field(
        default=None, description="Line range (start, end) if applicable"
    )

    # Metadata
    url: str | None = Field(default=None, description="URL to the source if available")
    timestamp: datetime | None = Field(
        default_factory=datetime.utcnow, description="When the source was accessed"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Confidence score (0-1) if available"
    )
    level: CitationLevel = Field(
        default=CitationLevel.UNVERIFIED, description="Verification level of this citation"
    )

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    def to_reference(self) -> SourceReference:
        """Convert to a minimal SourceReference."""
        return SourceReference(
            source_type=self.source_type,
            source_name=self.source_name,
            document_id=self.document_id,
            url=self.url,
            timestamp=self.timestamp,
        )

    def to_inline(self, index: int | None = None) -> str:
        """
        Format as inline citation like [1] or [SEC-10K].

        Args:
            index: Numeric index for the citation (e.g., [1])
                   If None, uses source_name abbreviation
        """
        if index is not None:
            return f"[{index}]"
        # Create abbreviation from source_name
        abbrev = "".join(word[0].upper() for word in self.source_name.split("_")[:3])
        return f"[{abbrev}]"

    def to_footnote(self, index: int) -> str:
        """Format as footnote entry."""
        parts = [f"[{index}] {self.source_name}"]
        if self.document_id:
            parts.append(f"({self.document_id})")
        if self.page_number:
            parts.append(f"p.{self.page_number}")
        parts.append(f": \"{self.content[:100]}{'...' if len(self.content) > 100 else ''}\"")
        return " ".join(parts)

    def matches_source(self, source_type: str | None = None, source_name: str | None = None) -> bool:
        """Check if this citation matches the given source filters."""
        if source_type and self.source_type != source_type:
            return False
        if source_name and self.source_name != source_name:
            return False
        return True

    def verify_content_in(self, text: str, threshold: float = 0.7) -> bool:
        """
        Verify that citation content exists in the given text.

        Uses fuzzy matching to account for minor differences.

        Args:
            text: Text to search for the citation content
            threshold: Minimum overlap ratio (0-1) for a match

        Returns:
            True if content is found in text
        """
        if not self.content or not text:
            return False

        # Normalize both strings
        content_clean = " ".join(self.content.lower().strip().split())
        text_clean = " ".join(text.lower().split())

        # Try exact substring match first
        if content_clean in text_clean:
            self.level = CitationLevel.VERIFIED
            return True

        # Try partial match
        min_match_length = int(len(content_clean) * threshold)
        for i in range(len(content_clean) - min_match_length + 1):
            substring = content_clean[i : i + min_match_length]
            if substring in text_clean:
                self.level = CitationLevel.VERIFIED
                return True

        # Word overlap fallback
        content_words = set(content_clean.split())
        text_words = set(text_clean.split())
        if content_words:
            overlap = len(content_words & text_words) / len(content_words)
            if overlap >= threshold:
                self.level = CitationLevel.VERIFIED
                return True

        return False


class CitedValue(BaseModel, Generic[T]):
    """
    A value with associated citations.

    This is the primary way to attach citations to extracted data.
    Use this for any value that should be traceable to its source.

    Example:
        revenue = CitedValue[float](
            value=394.3,
            unit="billion USD",
            citations=[
                Citation(
                    source_type="agent",
                    source_name="sec_filing_agent",
                    content="Total net sales were $394,328 million",
                )
            ],
        )
    """

    value: Any = Field(description="The actual value")
    unit: str | None = Field(default=None, description="Unit of measurement if applicable")
    citations: list[Citation] = Field(
        default_factory=list, description="Citations supporting this value"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Overall confidence in this value"
    )
    level: CitationLevel = Field(
        default=CitationLevel.UNVERIFIED, description="Overall citation level"
    )

    @property
    def is_cited(self) -> bool:
        """Check if this value has any citations."""
        return len(self.citations) > 0

    @property
    def is_verified(self) -> bool:
        """Check if all citations are verified."""
        return self.is_cited and all(c.level == CitationLevel.VERIFIED for c in self.citations)

    @property
    def primary_source(self) -> Citation | None:
        """Get the primary (first) citation."""
        return self.citations[0] if self.citations else None

    def add_citation(self, citation: Citation) -> "CitedValue":
        """Add a citation and return self for chaining."""
        self.citations.append(citation)
        return self

    def get_sources(self) -> list[str]:
        """Get list of source names."""
        return [c.source_name for c in self.citations]

    def to_dict_with_citations(self) -> dict[str, Any]:
        """Export as dict including citation info."""
        return {
            "value": self.value,
            "unit": self.unit,
            "citations": [c.model_dump() for c in self.citations],
            "confidence": self.confidence,
            "level": self.level.value,
        }

    def format_with_inline_citations(self) -> str:
        """Format value with inline citation markers."""
        value_str = f"{self.value}"
        if self.unit:
            value_str = f"{self.value} {self.unit}"

        if self.citations:
            markers = [c.to_inline(i + 1) for i, c in enumerate(self.citations)]
            value_str = f"{value_str} {' '.join(markers)}"

        return value_str


class CitationCollection(BaseModel):
    """
    A collection of citations with helper methods.

    Use this to manage multiple citations from a single operation,
    such as an agent call or LLM extraction.
    """

    citations: list[Citation] = Field(default_factory=list)
    source_chunks: dict[str, str] = Field(
        default_factory=dict,
        description="Raw source content by source_name for verification",
    )

    def add(self, citation: Citation) -> None:
        """Add a citation to the collection."""
        self.citations.append(citation)

    def add_source_chunk(self, source_name: str, content: str) -> None:
        """Add raw source content for verification."""
        self.source_chunks[source_name] = content

    def get_by_source(self, source_name: str) -> list[Citation]:
        """Get all citations from a specific source."""
        return [c for c in self.citations if c.source_name == source_name]

    def get_by_type(self, source_type: str) -> list[Citation]:
        """Get all citations of a specific type."""
        return [c for c in self.citations if c.source_type == source_type]

    def verify_all(self) -> dict[str, bool]:
        """
        Verify all citations against source chunks.

        Returns dict mapping citation index to verification result.
        """
        results = {}
        for i, citation in enumerate(self.citations):
            source_content = self.source_chunks.get(citation.source_name, "")
            results[str(i)] = citation.verify_content_in(source_content)
        return results

    def get_verification_summary(self) -> dict[str, Any]:
        """Get summary of citation verification."""
        verified = sum(1 for c in self.citations if c.level == CitationLevel.VERIFIED)
        return {
            "total": len(self.citations),
            "verified": verified,
            "unverified": len(self.citations) - verified,
            "verification_rate": verified / len(self.citations) if self.citations else 0,
            "by_source": {
                name: len(self.get_by_source(name)) for name in set(c.source_name for c in self.citations)
            },
        }

    def to_footnotes(self) -> str:
        """Generate footnotes for all citations."""
        return "\n".join(c.to_footnote(i + 1) for i, c in enumerate(self.citations))

    def merge(self, other: "CitationCollection") -> "CitationCollection":
        """Merge another collection into this one."""
        self.citations.extend(other.citations)
        self.source_chunks.update(other.source_chunks)
        return self
