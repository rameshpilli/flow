"""
AgentOrchestrator Citation Models
=================================

This module provides structured citation tracking for AI-generated content,
enabling source attribution, provenance tracking, and verification of claims
against source documents.

Citations provide transparency and explainability in AI outputs by linking
generated content back to its original sources. This is essential for:
- Building trust in AI-generated insights
- Enabling fact-checking and verification
- Meeting compliance and audit requirements
- Supporting human review workflows

Classes:
    CitationLevel: Enum for citation confidence/verification levels.
    SourceReference: Minimal reference to locate a source.
    Citation: Full citation with source attribution and content.
    CitedValue: Generic value wrapper with attached citations.
    CitationCollection: Collection of citations with helper methods.

Usage:
    from agentorchestrator.models import Citation, CitedValue

    # Create a citation
    citation = Citation(
        source_type="agent",
        source_name="sec_filing_agent",
        content="Revenue was $394.3 billion for fiscal year 2024",
        document_id="AAPL-10K-2024",
    )

    # Attach citation to a value
    revenue = CitedValue(
        value=394.3,
        unit="billion USD",
        citations=[citation],
    )

Example:
    >>> from agentorchestrator.models import Citation, CitedValue, CitationCollection
    >>>
    >>> # Create citations from different sources
    >>> sec_citation = Citation(
    ...     source_type="document",
    ...     source_name="sec_filing_agent",
    ...     content="Total net sales were $394,328 million",
    ...     document_id="AAPL-10K-2024",
    ...     page_number=45,
    ... )
    >>>
    >>> news_citation = Citation(
    ...     source_type="api",
    ...     source_name="news_agent",
    ...     content="Apple reported record Q4 revenue of $394.3B",
    ...     url="https://example.com/news/apple-q4",
    ... )
    >>>
    >>> # Create cited value with multiple sources
    >>> revenue = CitedValue(
    ...     value=394.3,
    ...     unit="billion USD",
    ...     citations=[sec_citation, news_citation],
    ... )
    >>>
    >>> # Format with inline citations
    >>> print(revenue.format_with_inline_citations())
    >>> # "394.3 billion USD [1] [2]"
    >>>
    >>> # Verify citations against source content
    >>> source_text = "Total net sales were $394,328 million for fiscal 2024..."
    >>> sec_citation.verify_content_in(source_text)  # True

See Also:
    - agentorchestrator.middleware.citation: Citation enforcement middleware.
    - agentorchestrator.agents.base: AgentResult with citation support.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

__all__ = [
    "CitationLevel",
    "SourceReference",
    "Citation",
    "CitedValue",
    "CitationCollection",
]


class CitationLevel(str, Enum):
    """
    Level of citation confidence/verification.

    Indicates how confident we are in a citation's accuracy and whether
    it has been verified against the source content.

    Attributes:
        VERIFIED: Citation verified against source content. The cited
            content was found in the source document.
        UNVERIFIED: Citation provided but not verified. Source content
            not available or verification not performed.
        INFERRED: Value was inferred from context, not directly cited.
            Use when the value is derived rather than quoted.
        NONE: No citation available. The value has no source attribution.

    Example:
        >>> from agentorchestrator.models import CitationLevel, Citation
        >>>
        >>> citation = Citation(
        ...     source_type="agent",
        ...     source_name="data_agent",
        ...     content="Revenue was $100M",
        ...     level=CitationLevel.UNVERIFIED,
        ... )
        >>>
        >>> # After verification
        >>> if citation.verify_content_in(source_text):
        ...     print(f"Level: {citation.level}")  # "verified"

    See Also:
        Citation.level: Uses this enum.
        Citation.verify_content_in(): Updates level to VERIFIED on match.
    """

    VERIFIED = "verified"  # Citation verified against source
    UNVERIFIED = "unverified"  # Citation provided but not verified
    INFERRED = "inferred"  # Value inferred, not directly cited
    NONE = "none"  # No citation available


class SourceReference(BaseModel):
    """
    Minimal reference to a source document or data.

    A lightweight reference containing just enough information to locate
    the original source. Use Citation for full attribution with content.

    Attributes:
        source_type (str): Type of source. Values: "agent", "document",
            "api", "llm", "database".
        source_name (str): Name of the source (agent name, API name, etc.).
        document_id (str | None): Unique identifier for the document/record.
        url (str | None): URL to the source if available.
        timestamp (datetime | None): When the source was accessed.

    Example:
        >>> ref = SourceReference(
        ...     source_type="document",
        ...     source_name="annual_report",
        ...     document_id="AR-2024-Q4",
        ...     url="https://example.com/reports/ar-2024",
        ... )
        >>> print(str(ref))  # "document:annual_report [AR-2024-Q4]"

    Note:
        For full citations with content and reasoning, use Citation instead.
        SourceReference is useful for compact storage or when content is
        stored separately.

    See Also:
        Citation: Full citation with content.
        Citation.to_reference(): Convert Citation to SourceReference.
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
        """
        Format as human-readable string.

        Returns:
            str: Formatted reference like "document:annual_report [AR-2024]".
        """
        parts = [f"{self.source_type}:{self.source_name}"]
        if self.document_id:
            parts.append(f"[{self.document_id}]")
        return " ".join(parts)


class Citation(BaseModel):
    """
    Full citation with source attribution and content.

    A Citation provides complete provenance for a piece of information,
    including where it came from, what the original content was, and
    why it supports the claim. This is the primary class for tracking
    source attribution in AgentOrchestrator.

    Attributes:
        source_type (str): Type of source: "agent", "document", "api",
            "llm", "database", "user".
        source_name (str): Name of the source (agent name, document title).
        content (str): Verbatim quote or content from the source.
            Should be exact, not paraphrased.
        reasoning (str | None): Explanation of why this source supports
            the claim. Optional but recommended for transparency.
        document_id (str | None): Unique identifier for the document/record.
        page_number (int | None): Page number if applicable.
        section (str | None): Section or heading in the document.
        line_range (tuple[int, int] | None): Line range (start, end).
        url (str | None): URL to the source if available.
        timestamp (datetime | None): When the source was accessed.
        confidence (float | None): Confidence score (0-1) if available.
        level (CitationLevel): Verification level. Default: UNVERIFIED.
        metadata (dict[str, Any]): Additional metadata.

    Methods:
        to_reference(): Convert to minimal SourceReference.
        to_inline(): Format as inline citation like [1] or [SEC].
        to_footnote(): Format as footnote entry.
        matches_source(): Check if citation matches source filters.
        verify_content_in(): Verify content exists in given text.

    Example:
        >>> citation = Citation(
        ...     source_type="agent",
        ...     source_name="sec_filing_agent",
        ...     content="Total net sales were $394,328 million...",
        ...     reasoning="This directly states the annual revenue figure",
        ...     document_id="AAPL-10K-2024-Q4",
        ...     page_number=45,
        ... )
        >>>
        >>> # Format for display
        >>> print(citation.to_inline(1))  # "[1]"
        >>> print(citation.to_footnote(1))
        >>> # "[1] sec_filing_agent (AAPL-10K-2024-Q4) p.45: "Total net sales...""
        >>>
        >>> # Verify against source
        >>> source = "...Total net sales were $394,328 million for fiscal 2024..."
        >>> citation.verify_content_in(source)  # True

    See Also:
        CitedValue: Wrapper for values with citations.
        CitationCollection: Collection of multiple citations.
        SourceReference: Minimal reference for compact storage.
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
        """
        Convert to a minimal SourceReference.

        Creates a lightweight reference for compact storage or when
        full citation content is stored separately.

        Returns:
            SourceReference: Minimal reference with source identification.

        Example:
            >>> ref = citation.to_reference()
            >>> print(ref)  # "agent:sec_filing_agent [AAPL-10K-2024]"
        """
        return SourceReference(
            source_type=self.source_type,
            source_name=self.source_name,
            document_id=self.document_id,
            url=self.url,
            timestamp=self.timestamp,
        )

    def to_inline(self, index: int | None = None) -> str:
        """
        Format as inline citation marker.

        Creates a short citation marker for use in text, like [1] or [SEC].

        Args:
            index (int | None): Numeric index for the citation (e.g., [1]).
                If None, creates an abbreviation from source_name.

        Returns:
            str: Inline citation marker.

        Example:
            >>> citation.to_inline(1)  # "[1]"
            >>> citation.to_inline()   # "[SFA]" (from sec_filing_agent)
        """
        if index is not None:
            return f"[{index}]"
        # Create abbreviation from source_name
        abbrev = "".join(word[0].upper() for word in self.source_name.split("_")[:3])
        return f"[{abbrev}]"

    def to_footnote(self, index: int) -> str:
        """
        Format as footnote entry.

        Creates a formatted footnote with source information and
        truncated content preview.

        Args:
            index (int): Footnote number for the citation.

        Returns:
            str: Formatted footnote entry.

        Example:
            >>> print(citation.to_footnote(1))
            >>> # [1] sec_filing_agent (AAPL-10K-2024) p.45: "Total net sales..."
        """
        parts = [f"[{index}] {self.source_name}"]
        if self.document_id:
            parts.append(f"({self.document_id})")
        if self.page_number:
            parts.append(f"p.{self.page_number}")
        parts.append(f": \"{self.content[:100]}{'...' if len(self.content) > 100 else ''}\"")
        return " ".join(parts)

    def matches_source(self, source_type: str | None = None, source_name: str | None = None) -> bool:
        """
        Check if this citation matches the given source filters.

        Useful for filtering citations by source type or name.

        Args:
            source_type (str | None): Source type to match. None matches any.
            source_name (str | None): Source name to match. None matches any.

        Returns:
            bool: True if citation matches all provided filters.

        Example:
            >>> citation.matches_source(source_type="agent")  # True/False
            >>> citation.matches_source(source_name="sec_filing_agent")  # True/False
            >>> citation.matches_source(source_type="agent", source_name="news")  # True/False
        """
        if source_type and self.source_type != source_type:
            return False
        if source_name and self.source_name != source_name:
            return False
        return True

    def verify_content_in(self, text: str, threshold: float = 0.7) -> bool:
        """
        Verify that citation content exists in the given text.

        Uses fuzzy matching to account for minor differences like
        whitespace, capitalization, or small text variations.

        On successful verification, updates self.level to VERIFIED.

        Args:
            text (str): Text to search for the citation content.
            threshold (float): Minimum overlap ratio (0-1) for a match.
                Higher values require closer matches. Default: 0.7.

        Returns:
            bool: True if content is found in text, False otherwise.

        Example:
            >>> citation = Citation(
            ...     source_type="agent",
            ...     source_name="agent",
            ...     content="Revenue was $100 million",
            ... )
            >>> source = "The company reported that revenue was $100 million last year."
            >>> citation.verify_content_in(source)  # True
            >>> citation.level  # CitationLevel.VERIFIED
            >>>
            >>> # Partial match with threshold
            >>> citation.verify_content_in("Revenue was approximately $100M", threshold=0.5)

        Note:
            Verification uses multiple strategies:
            1. Exact substring match (case-insensitive)
            2. Partial substring match with threshold
            3. Word overlap ratio with threshold
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
    A value with associated citations for source tracking.

    CitedValue wraps any value (number, string, dict, etc.) and attaches
    one or more citations to track its provenance. This is the primary
    way to make values traceable to their sources.

    Attributes:
        value (Any): The actual value being cited.
        unit (str | None): Unit of measurement if applicable.
        citations (list[Citation]): Citations supporting this value.
        confidence (float | None): Overall confidence in this value (0-1).
        level (CitationLevel): Overall citation level.

    Properties:
        is_cited (bool): True if value has any citations.
        is_verified (bool): True if all citations are verified.
        primary_source (Citation | None): The first (primary) citation.

    Methods:
        add_citation(): Add a citation and return self for chaining.
        get_sources(): Get list of source names.
        to_dict_with_citations(): Export as dict including citation info.
        format_with_inline_citations(): Format value with citation markers.

    Example:
        >>> from agentorchestrator.models import CitedValue, Citation
        >>>
        >>> # Simple cited value
        >>> revenue = CitedValue[float](
        ...     value=394.3,
        ...     unit="billion USD",
        ...     citations=[
        ...         Citation(
        ...             source_type="agent",
        ...             source_name="sec_filing_agent",
        ...             content="Total net sales were $394,328 million",
        ...         )
        ...     ],
        ... )
        >>>
        >>> # Access value and citations
        >>> print(revenue.value)  # 394.3
        >>> print(revenue.is_cited)  # True
        >>> print(revenue.primary_source.source_name)  # "sec_filing_agent"
        >>>
        >>> # Format for display
        >>> print(revenue.format_with_inline_citations())
        >>> # "394.3 billion USD [1]"
        >>>
        >>> # Add more citations
        >>> revenue.add_citation(Citation(...))

    Type Parameter:
        T: The type of the wrapped value. Use CitedValue[float] for
            type-safe numeric values, CitedValue[str] for strings, etc.

    See Also:
        Citation: Citation model attached to values.
        CitationCollection: Collection for managing multiple citations.
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
        """
        Check if this value has any citations.

        Returns:
            bool: True if one or more citations are attached.

        Example:
            >>> if cited_value.is_cited:
            ...     print(f"Sources: {cited_value.get_sources()}")
        """
        return len(self.citations) > 0

    @property
    def is_verified(self) -> bool:
        """
        Check if all citations are verified.

        Returns:
            bool: True if the value has citations AND all are verified.

        Example:
            >>> if cited_value.is_verified:
            ...     print("All sources verified!")
        """
        return self.is_cited and all(c.level == CitationLevel.VERIFIED for c in self.citations)

    @property
    def primary_source(self) -> Citation | None:
        """
        Get the primary (first) citation.

        Useful when you want the main source without iterating.

        Returns:
            Citation | None: First citation if any, None otherwise.

        Example:
            >>> source = cited_value.primary_source
            >>> if source:
            ...     print(f"Primary: {source.source_name}")
        """
        return self.citations[0] if self.citations else None

    def add_citation(self, citation: Citation) -> "CitedValue":
        """
        Add a citation and return self for method chaining.

        Args:
            citation (Citation): Citation to add to this value.

        Returns:
            CitedValue: Self, enabling method chaining.

        Example:
            >>> cited_value.add_citation(citation1).add_citation(citation2)
        """
        self.citations.append(citation)
        return self

    def get_sources(self) -> list[str]:
        """
        Get list of source names from all citations.

        Returns:
            list[str]: List of source names.

        Example:
            >>> sources = cited_value.get_sources()
            >>> # ["sec_filing_agent", "news_agent"]
        """
        return [c.source_name for c in self.citations]

    def to_dict_with_citations(self) -> dict[str, Any]:
        """
        Export as dictionary including full citation information.

        Useful for serialization or API responses where citation
        details need to be included.

        Returns:
            dict[str, Any]: Dictionary with value, unit, citations,
                confidence, and level.

        Example:
            >>> data = cited_value.to_dict_with_citations()
            >>> # {
            >>> #     "value": 394.3,
            >>> #     "unit": "billion USD",
            >>> #     "citations": [...],
            >>> #     "confidence": 0.95,
            >>> #     "level": "verified",
            >>> # }
        """
        return {
            "value": self.value,
            "unit": self.unit,
            "citations": [c.model_dump() for c in self.citations],
            "confidence": self.confidence,
            "level": self.level.value,
        }

    def format_with_inline_citations(self) -> str:
        """
        Format value with inline citation markers.

        Creates a human-readable string with the value, unit, and
        numbered citation markers.

        Returns:
            str: Formatted string like "394.3 billion USD [1] [2]".

        Example:
            >>> print(revenue.format_with_inline_citations())
            >>> # "394.3 billion USD [1] [2]"
        """
        value_str = f"{self.value}"
        if self.unit:
            value_str = f"{self.value} {self.unit}"

        if self.citations:
            markers = [c.to_inline(i + 1) for i, c in enumerate(self.citations)]
            value_str = f"{value_str} {' '.join(markers)}"

        return value_str


class CitationCollection(BaseModel):
    """
    A collection of citations with helper methods for management.

    CitationCollection provides utilities for managing multiple citations
    from a single operation (like an agent call or LLM extraction),
    including filtering, verification, and formatting.

    Attributes:
        citations (list[Citation]): List of citations in the collection.
        source_chunks (dict[str, str]): Raw source content by source_name
            for verification purposes.

    Methods:
        add(): Add a citation to the collection.
        add_source_chunk(): Add raw source content for verification.
        get_by_source(): Get citations from a specific source.
        get_by_type(): Get citations of a specific type.
        verify_all(): Verify all citations against source chunks.
        get_verification_summary(): Get summary of verification status.
        to_footnotes(): Generate footnotes for all citations.
        merge(): Merge another collection into this one.

    Example:
        >>> from agentorchestrator.models import CitationCollection, Citation
        >>>
        >>> # Create collection
        >>> collection = CitationCollection()
        >>>
        >>> # Add citations
        >>> collection.add(Citation(
        ...     source_type="agent",
        ...     source_name="sec_agent",
        ...     content="Revenue was $394B",
        ... ))
        >>> collection.add(Citation(
        ...     source_type="agent",
        ...     source_name="news_agent",
        ...     content="Apple reported record earnings",
        ... ))
        >>>
        >>> # Add source content for verification
        >>> collection.add_source_chunk("sec_agent", "...Revenue was $394B in FY2024...")
        >>>
        >>> # Verify all citations
        >>> results = collection.verify_all()
        >>> # {"0": True, "1": False}
        >>>
        >>> # Get summary
        >>> summary = collection.get_verification_summary()
        >>> print(f"Verified: {summary['verified']}/{summary['total']}")
        >>>
        >>> # Filter by source
        >>> sec_citations = collection.get_by_source("sec_agent")
        >>>
        >>> # Generate footnotes
        >>> print(collection.to_footnotes())

    See Also:
        Citation: Individual citation model.
        CitedValue: Value wrapper with citations.
        CitationMiddleware: Middleware using collections.
    """

    citations: list[Citation] = Field(default_factory=list)
    source_chunks: dict[str, str] = Field(
        default_factory=dict,
        description="Raw source content by source_name for verification",
    )

    def add(self, citation: Citation) -> None:
        """
        Add a citation to the collection.

        Args:
            citation (Citation): Citation to add.

        Example:
            >>> collection.add(Citation(
            ...     source_type="agent",
            ...     source_name="my_agent",
            ...     content="Some quoted content",
            ... ))
        """
        self.citations.append(citation)

    def add_source_chunk(self, source_name: str, content: str) -> None:
        """
        Add raw source content for verification.

        The source_name should match citation.source_name for
        verification to work correctly.

        Args:
            source_name (str): Name matching citation source names.
            content (str): Raw content from the source.

        Example:
            >>> collection.add_source_chunk(
            ...     "sec_filing_agent",
            ...     "Full text of the SEC filing...",
            ... )
        """
        self.source_chunks[source_name] = content

    def get_by_source(self, source_name: str) -> list[Citation]:
        """
        Get all citations from a specific source.

        Args:
            source_name (str): Source name to filter by.

        Returns:
            list[Citation]: Citations from the specified source.

        Example:
            >>> sec_citations = collection.get_by_source("sec_filing_agent")
            >>> print(f"Found {len(sec_citations)} SEC citations")
        """
        return [c for c in self.citations if c.source_name == source_name]

    def get_by_type(self, source_type: str) -> list[Citation]:
        """
        Get all citations of a specific type.

        Args:
            source_type (str): Source type to filter by
                (e.g., "agent", "document", "api").

        Returns:
            list[Citation]: Citations of the specified type.

        Example:
            >>> agent_citations = collection.get_by_type("agent")
            >>> doc_citations = collection.get_by_type("document")
        """
        return [c for c in self.citations if c.source_type == source_type]

    def verify_all(self) -> dict[str, bool]:
        """
        Verify all citations against their source chunks.

        For each citation, attempts to verify its content against
        the source chunk with matching source_name.

        Returns:
            dict[str, bool]: Mapping of citation index (as string)
                to verification result.

        Example:
            >>> results = collection.verify_all()
            >>> for idx, verified in results.items():
            ...     status = "VERIFIED" if verified else "UNVERIFIED"
            ...     print(f"Citation {idx}: {status}")
        """
        results = {}
        for i, citation in enumerate(self.citations):
            source_content = self.source_chunks.get(citation.source_name, "")
            results[str(i)] = citation.verify_content_in(source_content)
        return results

    def get_verification_summary(self) -> dict[str, Any]:
        """
        Get summary of citation verification status.

        Provides an overview of how many citations are verified,
        unverified, and the verification rate.

        Returns:
            dict[str, Any]: Summary containing:
                - total: Total number of citations
                - verified: Number verified
                - unverified: Number unverified
                - verification_rate: Ratio of verified (0-1)
                - by_source: Citation counts per source

        Example:
            >>> summary = collection.get_verification_summary()
            >>> print(f"Verified: {summary['verified']}/{summary['total']}")
            >>> print(f"Rate: {summary['verification_rate']:.1%}")
        """
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
        """
        Generate footnotes for all citations.

        Creates a formatted string with all citations as numbered
        footnotes, suitable for display at the end of a document.

        Returns:
            str: Multi-line footnotes string.

        Example:
            >>> print(collection.to_footnotes())
            >>> # [1] sec_agent (AAPL-10K): "Revenue was..."
            >>> # [2] news_agent: "Apple reported..."
        """
        return "\n".join(c.to_footnote(i + 1) for i, c in enumerate(self.citations))

    def merge(self, other: "CitationCollection") -> "CitationCollection":
        """
        Merge another collection into this one.

        Combines citations and source chunks from both collections.
        Modifies this collection in place.

        Args:
            other (CitationCollection): Collection to merge.

        Returns:
            CitationCollection: Self, for method chaining.

        Example:
            >>> collection1.merge(collection2).merge(collection3)
            >>> # collection1 now has citations from all three
        """
        self.citations.extend(other.citations)
        self.source_chunks.update(other.source_chunks)
        return self