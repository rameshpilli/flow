"""
AgentOrchestrator Citation Middleware
=====================================

This module provides middleware for enforcing, validating, and tracking
citations in AI-generated outputs. It enables source attribution,
provenance tracking, and verification of claims against source documents.

The middleware supports:
- Automatic citation tracking from step outputs
- Validation of citations against source content
- Minimum coverage enforcement
- Detailed citation reports

Classes:
    CitationReport: Report of citation coverage and validation for a chain run.
    CitationMiddleware: Middleware for citation enforcement and validation.

Functions:
    add_citation(): Add a citation to the current context's collection.
    add_source_content(): Add source content for citation verification.
    get_citation_report(): Get the citation report from context.
    cite(): Convenience function to create a CitedValue with a single citation.

Usage:
    from agentorchestrator.middleware import CitationMiddleware
    from agentorchestrator.models import CitedValue, Citation

    ao = AgentOrchestrator(name="research_chain")

    # Add citation middleware with validation
    ao.use(CitationMiddleware(
        require_citations=True,
        validate_against_sources=True,
        min_coverage=0.8,
    ))

    # Steps that produce CitedValue outputs will be validated
    @ao.step
    async def extract_metrics(ctx):
        return CitedValue(value=394.3, citations=[...])

Example:
    >>> from agentorchestrator.middleware import CitationMiddleware, cite
    >>>
    >>> # Configure citation middleware
    >>> citation_mw = CitationMiddleware(
    ...     require_citations=True,
    ...     validate_against_sources=True,
    ...     min_coverage=0.8,
    ...     fail_on_missing=False,  # Warn but don't fail
    ... )
    >>> ao.use(citation_mw)
    >>>
    >>> # In a step, use cite() helper
    >>> @ao.step
    ... async def extract_revenue(ctx):
    ...     return cite(
    ...         value=394.3,
    ...         source_name="sec_filing_agent",
    ...         content="Total net sales were $394,328 million",
    ...         reasoning="Direct revenue figure from 10-K filing",
    ...     )
    >>>
    >>> # After chain execution, get report
    >>> result = await ao.run({"query": "Apple revenue"})
    >>> report = get_citation_report(ctx)
    >>> print(f"Coverage: {report['coverage_rate']:.1%}")

See Also:
    - agentorchestrator.models.citation: Citation and CitedValue models.
    - agentorchestrator.middleware.base: Base middleware class.
    - agentorchestrator.agents.base: AgentResult with citation support.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agentorchestrator.core.context import StepResult
from agentorchestrator.middleware.base import Middleware
from agentorchestrator.models.citation import (
    Citation,
    CitationCollection,
    CitationLevel,
    CitedValue,
)

if TYPE_CHECKING:
    from agentorchestrator.core.context import ChainContext

logger = logging.getLogger(__name__)

__all__ = [
    "CitationReport",
    "CitationMiddleware",
    "add_citation",
    "add_source_content",
    "get_citation_report",
    "cite",
]


@dataclass
class CitationReport:
    """
    Report of citation coverage and validation for a chain run.

    Provides detailed statistics about citations collected during chain
    execution, including coverage rates, verification status, and
    per-step/per-source breakdowns.

    Attributes:
        total_cited_values (int): Total number of CitedValue instances found.
        total_citations (int): Total number of Citation objects attached.
        verified_citations (int): Citations verified against source content.
        unverified_citations (int): Citations not verified (source unavailable).
        missing_citations (int): Values that should have citations but don't.
        by_step (dict[str, dict[str, int]]): Citation stats per step.
        by_source (dict[str, int]): Citation counts per source name.
        validation_errors (list[str]): List of validation error messages.

    Properties:
        coverage_rate (float): Percentage of values with citations (0-1).
        verification_rate (float): Percentage of citations verified (0-1).

    Methods:
        to_dict(): Convert report to dictionary format.

    Example:
        >>> report = CitationReport(
        ...     total_cited_values=10,
        ...     total_citations=15,
        ...     verified_citations=12,
        ...     unverified_citations=3,
        ...     missing_citations=2,
        ... )
        >>> print(f"Coverage: {report.coverage_rate:.1%}")  # "Coverage: 83.3%"
        >>> print(f"Verified: {report.verification_rate:.1%}")  # "Verified: 80.0%"
        >>>
        >>> # Export as dict
        >>> report_dict = report.to_dict()
        >>> print(report_dict["coverage_rate"])

    See Also:
        CitationMiddleware: Middleware that generates this report.
        CitedValue: Values that are tracked in this report.
    """

    total_cited_values: int = 0
    total_citations: int = 0
    verified_citations: int = 0
    unverified_citations: int = 0
    missing_citations: int = 0  # Values that should have citations but don't

    by_step: dict[str, dict[str, int]] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)

    @property
    def coverage_rate(self) -> float:
        """
        Calculate the percentage of values that have citations.

        Returns:
            float: Coverage rate between 0 and 1. Returns 1.0 if there
                are no values to cite (nothing missing).

        Example:
            >>> report = CitationReport(total_cited_values=8, missing_citations=2)
            >>> report.coverage_rate  # 0.8 (80%)
        """
        total = self.total_cited_values + self.missing_citations
        return self.total_cited_values / total if total > 0 else 1.0

    @property
    def verification_rate(self) -> float:
        """
        Calculate the percentage of citations that are verified.

        Returns:
            float: Verification rate between 0 and 1. Returns 0.0 if
                there are no citations.

        Example:
            >>> report = CitationReport(total_citations=10, verified_citations=8)
            >>> report.verification_rate  # 0.8 (80%)
        """
        return self.verified_citations / self.total_citations if self.total_citations > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the report to a dictionary format.

        Returns:
            dict[str, Any]: Dictionary containing all report fields plus
                computed coverage_rate and verification_rate.

        Example:
            >>> report_dict = report.to_dict()
            >>> print(f"Coverage: {report_dict['coverage_rate']:.1%}")
            >>> print(f"By source: {report_dict['by_source']}")
        """
        return {
            "total_cited_values": self.total_cited_values,
            "total_citations": self.total_citations,
            "verified_citations": self.verified_citations,
            "unverified_citations": self.unverified_citations,
            "missing_citations": self.missing_citations,
            "coverage_rate": self.coverage_rate,
            "verification_rate": self.verification_rate,
            "by_step": self.by_step,
            "by_source": self.by_source,
            "validation_errors": self.validation_errors,
        }


class CitationMiddleware(Middleware):
    """
    Middleware for enforcing and validating citations on step outputs.

    Automatically tracks CitedValue outputs from steps, validates citations
    against source content, enforces minimum coverage requirements, and
    generates detailed citation reports.

    Attributes:
        require_citations (bool): Whether citations are required.
        validate_against_sources (bool): Whether to verify citations.
        min_coverage (float): Minimum required coverage rate (0-1).
        fail_on_missing (bool): Whether to fail steps missing citations.
        collect_sources (bool): Whether to auto-collect source content.
        source_context_keys (list[str]): Context keys to check for sources.

    Methods:
        before_chain(): Initialize citation tracking for chain run.
        after_step(): Process step output for citations.
        after_chain(): Finalize citation report and store in context.

    Example:
        >>> from agentorchestrator.middleware import CitationMiddleware
        >>>
        >>> # Strict citation requirements
        >>> citation_mw = CitationMiddleware(
        ...     require_citations=True,
        ...     validate_against_sources=True,
        ...     min_coverage=0.9,        # 90% of values must be cited
        ...     fail_on_missing=True,    # Fail if coverage not met
        ...     collect_sources=True,    # Auto-collect from context
        ... )
        >>> ao.use(citation_mw)
        >>>
        >>> # Lenient mode (tracking only)
        >>> tracking_mw = CitationMiddleware(
        ...     require_citations=False,
        ...     validate_against_sources=False,
        ...     min_coverage=0.0,
        ...     fail_on_missing=False,
        ... )

    Configuration Options:
        - require_citations: If True, steps marked as requiring citations must
            provide them. Use with min_coverage for enforcement.
        - validate_against_sources: If True, verify citation content exists
            in the source documents. Requires source content in context.
        - min_coverage: Minimum percentage of values that must have citations.
            Range 0-1. Default: 0.0 (no minimum).
        - fail_on_missing: If True, fail steps that don't meet coverage.
            If False, just log warnings. Default: False.
        - collect_sources: If True, automatically collect source content
            from context keys for verification. Default: True.
        - source_context_keys: Context keys to check for source content.
            Default: ["agent_results", "source_chunks", "raw_content"].

    See Also:
        CitationReport: Report generated by this middleware.
        Citation: Citation model for source attribution.
        CitedValue: Value wrapper with citation support.
        cite(): Helper function to create cited values.
    """

    def __init__(
        self,
        require_citations: bool = False,
        validate_against_sources: bool = True,
        min_coverage: float = 0.0,
        fail_on_missing: bool = False,
        collect_sources: bool = True,
        source_context_keys: list[str] | None = None,
    ):
        """
        Initialize the citation middleware.

        Args:
            require_citations (bool): If True, enforce citation requirements.
                Works with min_coverage to ensure values are cited.
                Default: False.
            validate_against_sources (bool): If True, verify citation content
                exists in the source documents. Requires source content to be
                available in context. Default: True.
            min_coverage (float): Minimum percentage of values that must have
                citations (0.0 to 1.0). Only enforced if require_citations=True.
                Default: 0.0.
            fail_on_missing (bool): If True, fail steps that don't meet the
                min_coverage requirement. If False, log warnings only.
                Default: False.
            collect_sources (bool): If True, automatically collect source
                content from context for verification. Default: True.
            source_context_keys (list[str] | None): Context keys to check for
                source content. Default: ["agent_results", "source_chunks",
                "raw_content"].

        Example:
            >>> # Production configuration
            >>> middleware = CitationMiddleware(
            ...     require_citations=True,
            ...     validate_against_sources=True,
            ...     min_coverage=0.8,
            ...     fail_on_missing=False,  # Don't fail, just warn
            ...     source_context_keys=["agent_results", "documents"],
            ... )
        """
        self.require_citations = require_citations
        self.validate_against_sources = validate_against_sources
        self.min_coverage = min_coverage
        self.fail_on_missing = fail_on_missing
        self.collect_sources = collect_sources
        self.source_context_keys = source_context_keys or [
            "agent_results",
            "source_chunks",
            "raw_content",
        ]

        # Per-run state
        self._current_report: CitationReport | None = None
        self._source_chunks: dict[str, str] = {}

    @property
    def name(self) -> str:
        """
        Get the middleware name for identification.

        Returns:
            str: The middleware name "citation".
        """
        return "citation"

    async def before_chain(self, ctx: "ChainContext") -> None:
        """
        Initialize citation tracking for this chain run.

        Creates a new CitationReport and CitationCollection, storing them
        in context for use by steps and other middleware.

        Args:
            ctx (ChainContext): The chain execution context.

        Example:
            >>> # Called automatically at chain start
            >>> # After this, steps can access:
            >>> report = ctx.get("_citation_report")
            >>> collection = ctx.get("_citation_collection")
        """
        self._current_report = CitationReport()
        self._source_chunks = {}

        # Store the report in context for access by steps
        ctx.set("_citation_report", self._current_report)
        ctx.set("_citation_collection", CitationCollection())

    async def after_step(self, ctx: "ChainContext", result: StepResult) -> StepResult:
        """
        Process step output for citations.

        Analyzes the step's output for CitedValue instances, validates
        citations against source content if enabled, and updates the
        citation report with statistics.

        Args:
            ctx (ChainContext): The chain execution context.
            result (StepResult): The step's execution result.

        Returns:
            StepResult: The original or modified result (failed if coverage
                not met and fail_on_missing=True).

        Example:
            >>> # Called automatically after each step
            >>> # If step returns CitedValue, it will be tracked
            >>> @ao.step
            ... async def extract_data(ctx):
            ...     return CitedValue(value=100, citations=[...])
        """
        if not self._current_report:
            return result

        step_name = result.step_name
        step_stats = {"cited_values": 0, "citations": 0, "verified": 0}

        # Collect source content from context if enabled
        if self.collect_sources:
            self._collect_sources_from_context(ctx)

        # Analyze step output for citations
        if result.output:
            self._analyze_output(result.output, step_name, step_stats)

        # Record step stats
        self._current_report.by_step[step_name] = step_stats

        # Check coverage if required
        if self.require_citations and self.min_coverage > 0:
            if self._current_report.coverage_rate < self.min_coverage:
                error_msg = (
                    f"Step '{step_name}' citation coverage "
                    f"({self._current_report.coverage_rate:.1%}) "
                    f"below minimum ({self.min_coverage:.1%})"
                )
                self._current_report.validation_errors.append(error_msg)

                if self.fail_on_missing:
                    logger.error(error_msg)
                    return StepResult(
                        step_name=step_name,
                        success=False,
                        output=result.output,
                        error={"message": error_msg, "type": "CitationError"},
                        duration_ms=result.duration_ms,
                    )
                else:
                    logger.warning(error_msg)

        return result

    async def after_chain(self, ctx: "ChainContext", success: bool) -> None:
        """
        Finalize citation report and store in context.

        Called at the end of chain execution. Stores the final report
        in context as "citation_report" and logs a summary.

        Args:
            ctx (ChainContext): The chain execution context.
            success (bool): Whether the chain completed successfully.

        Example:
            >>> # After chain completes, get report from context
            >>> report = ctx.get("citation_report")
            >>> print(f"Total citations: {report['total_citations']}")
        """
        if self._current_report:
            # Store final report in context
            ctx.set("citation_report", self._current_report.to_dict())

            # Log summary
            logger.info(
                f"Citation Report: "
                f"{self._current_report.total_citations} citations, "
                f"{self._current_report.verification_rate:.1%} verified, "
                f"{self._current_report.coverage_rate:.1%} coverage"
            )

    def _collect_sources_from_context(self, ctx: "ChainContext") -> None:
        """
        Collect source content from context for citation verification.

        Scans the configured source_context_keys for content that can
        be used to verify citations.

        Args:
            ctx (ChainContext): The chain execution context.
        """
        for key in self.source_context_keys:
            value = ctx.get(key)
            if value is None:
                continue

            if isinstance(value, dict):
                for name, content in value.items():
                    if isinstance(content, str):
                        self._source_chunks[name] = content
                    elif isinstance(content, dict) and "content" in content:
                        self._source_chunks[name] = content["content"]
                    elif isinstance(content, dict) and "data" in content:
                        self._source_chunks[name] = str(content["data"])

    def _analyze_output(
        self, output: Any, step_name: str, step_stats: dict[str, int]
    ) -> None:
        """
        Recursively analyze output for CitedValue instances.

        Walks through the output structure (dict, list, Pydantic models)
        to find and process all CitedValue instances.

        Args:
            output (Any): The output to analyze.
            step_name (str): Name of the step (for logging).
            step_stats (dict[str, int]): Statistics to update.
        """
        if output is None:
            return

        # Handle CitedValue directly
        if isinstance(output, CitedValue):
            self._process_cited_value(output, step_stats)
            return

        # Handle dict - check values recursively
        if isinstance(output, dict):
            for value in output.values():
                self._analyze_output(value, step_name, step_stats)
            return

        # Handle list
        if isinstance(output, list):
            for item in output:
                self._analyze_output(item, step_name, step_stats)
            return

        # Handle Pydantic models with CitedValue fields
        if hasattr(output, "model_fields"):
            for field_name in output.model_fields:
                field_value = getattr(output, field_name, None)
                self._analyze_output(field_value, step_name, step_stats)

    def _process_cited_value(
        self, cited_value: CitedValue, step_stats: dict[str, int]
    ) -> None:
        """
        Process a CitedValue and update statistics.

        Counts citations, validates against sources if enabled, and
        updates both step-level and report-level statistics.

        Args:
            cited_value (CitedValue): The cited value to process.
            step_stats (dict[str, int]): Step-level statistics to update.
        """
        if not self._current_report:
            return

        step_stats["cited_values"] += 1
        self._current_report.total_cited_values += 1

        if not cited_value.citations:
            self._current_report.missing_citations += 1
            return

        for citation in cited_value.citations:
            step_stats["citations"] += 1
            self._current_report.total_citations += 1

            # Track by source
            source = citation.source_name
            self._current_report.by_source[source] = (
                self._current_report.by_source.get(source, 0) + 1
            )

            # Validate against sources if enabled
            if self.validate_against_sources:
                source_content = self._source_chunks.get(citation.source_name, "")
                if source_content and citation.verify_content_in(source_content):
                    step_stats["verified"] += 1
                    self._current_report.verified_citations += 1
                else:
                    self._current_report.unverified_citations += 1
            else:
                # If not validating, count as unverified
                self._current_report.unverified_citations += 1


def add_citation(
    ctx: "ChainContext",
    citation: Citation,
) -> None:
    """
    Add a citation to the current context's collection.

    Use this function within a step to manually add citations to the
    shared collection, which will be included in the citation report.

    Args:
        ctx (ChainContext): The chain execution context.
        citation (Citation): The citation to add.

    Example:
        >>> from agentorchestrator.middleware import add_citation
        >>> from agentorchestrator.models import Citation
        >>>
        >>> @ao.step
        ... async def process_data(ctx):
        ...     # Add citation for manual tracking
        ...     add_citation(ctx, Citation(
        ...         source_type="document",
        ...         source_name="annual_report",
        ...         content="Revenue increased 15% year-over-year",
        ...         document_id="AR-2024",
        ...     ))
        ...     return processed_data

    See Also:
        Citation: The citation model.
        CitationCollection: Collection that stores citations.
        add_source_content(): Add source content for verification.
    """
    collection = ctx.get("_citation_collection")
    if collection and isinstance(collection, CitationCollection):
        collection.add(citation)


def add_source_content(
    ctx: "ChainContext",
    source_name: str,
    content: str,
) -> None:
    """
    Add source content for citation verification.

    Use this function to provide raw source content that citations
    can be verified against. The source_name should match the
    citation.source_name for verification to work.

    Args:
        ctx (ChainContext): The chain execution context.
        source_name (str): Name of the source. Must match citation.source_name
            for citations to be verified against this content.
        content (str): Raw content from the source document.

    Example:
        >>> from agentorchestrator.middleware import add_source_content
        >>>
        >>> @ao.step
        ... async def fetch_documents(ctx):
        ...     doc_content = await fetch_document("annual_report.pdf")
        ...     # Make content available for citation verification
        ...     add_source_content(ctx, "annual_report", doc_content)
        ...     return {"annual_report": doc_content}

    See Also:
        add_citation(): Add citations to the collection.
        CitationCollection.add_source_chunk(): Underlying method.
    """
    collection = ctx.get("_citation_collection")
    if collection and isinstance(collection, CitationCollection):
        collection.add_source_chunk(source_name, content)


def get_citation_report(ctx: "ChainContext") -> dict[str, Any] | None:
    """
    Get the citation report from context.

    Retrieves the final citation report after chain execution completes.
    The report contains statistics about citations, coverage, and
    verification results.

    Args:
        ctx (ChainContext): The chain execution context.

    Returns:
        dict[str, Any] | None: Citation report dictionary containing:
            - total_cited_values: Number of CitedValue instances
            - total_citations: Total citation count
            - verified_citations: Citations verified against sources
            - unverified_citations: Citations not verified
            - missing_citations: Values without citations
            - coverage_rate: Percentage of values cited (0-1)
            - verification_rate: Percentage verified (0-1)
            - by_step: Per-step statistics
            - by_source: Per-source citation counts
            - validation_errors: List of error messages
        Returns None if no report is available.

    Example:
        >>> # After chain execution
        >>> report = get_citation_report(ctx)
        >>> if report:
        ...     print(f"Coverage: {report['coverage_rate']:.1%}")
        ...     print(f"Verified: {report['verification_rate']:.1%}")
        ...     for step, stats in report['by_step'].items():
        ...         print(f"  {step}: {stats['citations']} citations")

    See Also:
        CitationReport: The report class.
        CitationMiddleware.after_chain(): When report is generated.
    """
    return ctx.get("citation_report")


def cite(
    value: Any,
    source_name: str,
    content: str,
    source_type: str = "agent",
    reasoning: str | None = None,
    **kwargs: Any,
) -> CitedValue:
    """
    Create a CitedValue with a single citation.

    A convenience function for the common case of creating a value
    with one citation. For multiple citations, use CitedValue directly.

    Args:
        value (Any): The value to cite. Can be any type (number, string,
            dict, etc.).
        source_name (str): Name of the source (e.g., agent name, document
            title). Should match the source content key for verification.
        content (str): Verbatim quote or excerpt from the source that
            supports this value. Should be exact, not paraphrased.
        source_type (str): Type of source. Common values: "agent",
            "document", "api", "llm", "database", "user". Default: "agent".
        reasoning (str | None): Explanation of why this source supports
            the value. Optional but recommended for transparency.
        **kwargs: Additional Citation fields to set:
            - document_id (str): Unique document identifier
            - page_number (int): Page number in source
            - section (str): Section heading in source
            - url (str): URL to the source
            - confidence (float): Confidence score (0-1)

    Returns:
        CitedValue: A CitedValue wrapping the value with the citation attached.

    Example:
        >>> from agentorchestrator.middleware import cite
        >>>
        >>> # Simple citation
        >>> revenue = cite(
        ...     value=394.3,
        ...     source_name="sec_filing_agent",
        ...     content="Total net sales were $394,328 million",
        ...     reasoning="Direct revenue figure from 10-K filing",
        ... )
        >>>
        >>> # With additional metadata
        >>> metric = cite(
        ...     value=15.5,
        ...     source_name="financial_report",
        ...     content="Operating margin improved to 15.5%",
        ...     source_type="document",
        ...     document_id="Q4-2024-earnings",
        ...     page_number=12,
        ...     confidence=0.95,
        ... )
        >>>
        >>> # Access the value
        >>> print(revenue.value)  # 394.3
        >>> print(revenue.citations[0].content)

    See Also:
        CitedValue: The wrapper class for cited values.
        Citation: The citation model with all fields.
        add_citation(): Add citations to context collection.
    """
    citation = Citation(
        source_type=source_type,
        source_name=source_name,
        content=content,
        reasoning=reasoning,
        **kwargs,
    )
    return CitedValue(value=value, citations=[citation])
