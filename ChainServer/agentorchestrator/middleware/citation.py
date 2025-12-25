"""
Citation Middleware for AgentOrchestrator

Provides middleware for:
- Enforcing citation requirements on step outputs
- Validating citations against source content
- Tracking citation coverage across chains
- Generating citation reports

Example Usage:
    ao = AgentOrchestrator(name="my_chain")

    # Add citation middleware
    ao.use(CitationMiddleware(
        require_citations=True,
        validate_against_sources=True,
        min_coverage=0.8,
    ))

    # Steps that produce CitedValue outputs will be validated
    @ao.step
    async def extract_metrics(ctx):
        return CitedValue(value=394.3, citations=[...])
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


@dataclass
class CitationReport:
    """Report of citation coverage and validation for a chain run."""

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
        """Percentage of values that have citations."""
        total = self.total_cited_values + self.missing_citations
        return self.total_cited_values / total if total > 0 else 1.0

    @property
    def verification_rate(self) -> float:
        """Percentage of citations that are verified."""
        return self.verified_citations / self.total_citations if self.total_citations > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
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
    Middleware that enforces and validates citations on step outputs.

    Features:
    - Tracks CitedValue outputs from steps
    - Validates citations against source content (if available)
    - Enforces minimum citation coverage
    - Generates citation reports

    Configuration:
        require_citations: If True, steps marked as requiring citations must provide them
        validate_against_sources: If True, verify citation content exists in sources
        min_coverage: Minimum percentage of values that must have citations (0-1)
        fail_on_missing: If True, fail steps that are missing required citations
        collect_sources: If True, collect source chunks from context for validation
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
        Initialize citation middleware.

        Args:
            require_citations: Enforce citation requirements
            validate_against_sources: Verify citations against source content
            min_coverage: Minimum citation coverage (0-1)
            fail_on_missing: Fail if citations are missing
            collect_sources: Auto-collect source content from context
            source_context_keys: Context keys to check for source content
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
        return "citation"

    async def before_chain(self, ctx: "ChainContext") -> None:
        """Initialize citation tracking for this chain run."""
        self._current_report = CitationReport()
        self._source_chunks = {}

        # Store the report in context for access by steps
        ctx.set("_citation_report", self._current_report)
        ctx.set("_citation_collection", CitationCollection())

    async def after_step(self, ctx: "ChainContext", result: StepResult) -> StepResult:
        """Process step output for citations."""
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
        """Finalize citation report and store in context."""
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
        """Collect source content from context for validation."""
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
        """Recursively analyze output for CitedValue instances."""
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
        """Process a CitedValue and update statistics."""
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
    Helper function to add a citation to the current context's collection.

    Args:
        ctx: The chain context
        citation: Citation to add
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
    Helper function to add source content for citation verification.

    Args:
        ctx: The chain context
        source_name: Name of the source (should match citation.source_name)
        content: Raw content from the source
    """
    collection = ctx.get("_citation_collection")
    if collection and isinstance(collection, CitationCollection):
        collection.add_source_chunk(source_name, content)


def get_citation_report(ctx: "ChainContext") -> dict[str, Any] | None:
    """
    Get the citation report from context.

    Args:
        ctx: The chain context

    Returns:
        Citation report dict or None
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
    Convenience function to create a CitedValue with a single citation.

    Args:
        value: The value to cite
        source_name: Name of the source
        content: Verbatim content from source
        source_type: Type of source (default: "agent")
        reasoning: Why this source supports the value
        **kwargs: Additional Citation fields

    Returns:
        CitedValue with the citation attached

    Example:
        revenue = cite(
            value=394.3,
            source_name="sec_filing_agent",
            content="Total net sales were $394,328 million",
            reasoning="Direct revenue figure from 10-K",
        )
    """
    citation = Citation(
        source_type=source_type,
        source_name=source_name,
        content=content,
        reasoning=reasoning,
        **kwargs,
    )
    return CitedValue(value=value, citations=[citation])
