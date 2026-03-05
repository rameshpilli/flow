"""
AgentOrchestrator Context Management
====================================

This module provides the context management system for chain execution in AgentOrchestrator.

ChainContext is the central data structure that flows through all steps in a chain,
providing shared state, scoped storage, token tracking, and citation support.
It enables data sharing between steps while maintaining isolation where needed.

Classes:
    ContextScope: Enum defining data lifetime scopes (STEP, CHAIN, GLOBAL).
    ContextEntry: Dataclass representing a single context entry with metadata.
    StepResult: Dataclass for step execution results with error tracking.
    ExecutionSummary: Summary of chain execution with partial success tracking.
    ChainContext: Main context class managing shared state between steps.
    ContextManager: Singleton manager for multiple concurrent chain contexts.

Usage:
    from agentorchestrator.core.context import ChainContext, ContextScope

    # Create a context for a chain execution
    ctx = ChainContext(request_id="req_123")

    # Store data with different scopes
    ctx.set("user_query", "Who is the CEO?", scope=ContextScope.CHAIN)
    ctx.set("temp_data", {...}, scope=ContextScope.STEP)  # Cleaned up after step

    # Retrieve data
    query = ctx.get("user_query")

    # Use step scope for automatic cleanup
    async with ctx.step_scope("my_step"):
        ctx.set("local_var", value, scope=ContextScope.STEP)
        # ... step logic ...
    # local_var is automatically cleaned up here

Example:
    >>> from agentorchestrator.core.context import ChainContext, ContextScope, StepResult
    >>>
    >>> # Create context with initial data
    >>> ctx = ChainContext(
    ...     request_id="req_abc123",
    ...     initial_data={"company": "Apple Inc"},
    ...     max_tokens=100000,
    ... )
    >>>
    >>> # Store step results
    >>> ctx.add_result(StepResult(
    ...     step_name="extract_company",
    ...     output={"ticker": "AAPL"},
    ...     duration_ms=150.5,
    ... ))
    >>>
    >>> # Check results
    >>> print(ctx.last_result.success)  # True
    >>> print(ctx.total_tokens)  # Token count for LLM context management

Thread-safety:
    - Uses asyncio.Lock for concurrent access protection
    - Uses contextvars for per-task step tracking (safe for parallel steps)
    - Step-scoped data is isolated per step using namespaced keys

See Also:
    - agentorchestrator.core.orchestrator: Uses ChainContext for execution.
    - agentorchestrator.core.decorators: Step decorators that work with context.
    - agentorchestrator.models.citation: Citation model for source tracking.
"""

import asyncio
import contextvars
import copy
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

if TYPE_CHECKING:
    from agentorchestrator.core.serializers import ContextSerializer
    from agentorchestrator.core.state import StateStore

logger = logging.getLogger(__name__)

__all__ = [
    "ChainContext",
    "Context",
    "ContextScope",
    "ContextEntry",
    "ContextManager",
    "StepResult",
    "ExecutionSummary",
    "ExecutionResult",
    "ResultStore",
    "CitationManager",
    "TokenTracker",
]

T = TypeVar("T")
StateModel = TypeVar("StateModel")

# Context variable for tracking current step per async task
# This is the async-safe equivalent of thread-local storage
_current_step_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_step", default=None
)


class ContextScope(Enum):
    """
    Defines the scope/lifetime of context data.

    Controls how long data persists and who can access it.
    Choose the appropriate scope based on data lifecycle needs.

    Attributes:
        STEP: Data available only within current step execution.
            Automatically cleaned up when step completes.
            Ideal for temporary calculations or intermediate results.
        CHAIN: Data available throughout the entire chain execution.
            Persists from first step to last, then cleaned up.
            Use for data that flows between steps.
        GLOBAL: Data persists across multiple chain executions.
            Use sparingly for truly global configuration.

    Example:
        >>> from agentorchestrator.core.context import ContextScope
        >>>
        >>> # Step-scoped data (cleaned up after step)
        >>> ctx.set("temp_result", data, scope=ContextScope.STEP)
        >>>
        >>> # Chain-scoped data (available to all steps)
        >>> ctx.set("company_info", info, scope=ContextScope.CHAIN)
        >>>
        >>> # Global data (persists across chains)
        >>> ctx.set("config", config, scope=ContextScope.GLOBAL)
    """

    STEP = "step"  # Available only within current step
    CHAIN = "chain"  # Available throughout the chain execution
    GLOBAL = "global"  # Persists across multiple chain executions


@dataclass
class ContextEntry:
    """
    A single entry in the context store.

    Wraps stored values with metadata for tracking, debugging,
    and token management.

    Attributes:
        key (str): Unique identifier for this entry.
        value (Any): The stored data value.
        scope (ContextScope): Lifetime scope of this entry.
        created_at (datetime): When the entry was first created.
        updated_at (datetime): When the entry was last modified.
        token_count (int): Estimated token count for LLM context tracking.
        source_step (str | None): Name of step that created this entry.
        metadata (dict[str, Any]): Additional entry metadata.

    Example:
        >>> entry = ContextEntry(
        ...     key="company_data",
        ...     value={"name": "Apple", "ticker": "AAPL"},
        ...     scope=ContextScope.CHAIN,
        ...     token_count=50,
        ...     source_step="extract_company",
        ... )
    """

    key: str
    value: Any
    scope: ContextScope
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    token_count: int = 0
    source_step: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    """
    Result from a step execution with rich error metadata.

    Captures comprehensive information about a step's execution,
    including output, timing, errors, and retry information.
    Used for debugging, logging, and partial success tracking.

    Attributes:
        step_name (str): Name of the executed step.
        output (Any): Output data from the step (None on failure).
        duration_ms (float): Execution time in milliseconds.
        token_count (int): Token count for LLM calls in this step.
        metadata (dict[str, Any]): Additional step metadata.
        error (Exception | None): Exception if step failed.
        error_type (str | None): Type of error (for structured logging).
        error_traceback (str | None): Full traceback string (for debugging).
        retry_count (int): Number of retries attempted.
        skipped_reason (str | None): Reason if step was skipped.

    Properties:
        success (bool): True if step completed without error or skip.
        failed (bool): True if step raised an exception.
        skipped (bool): True if step was skipped.

    Methods:
        to_dict(): Convert to dictionary for serialization.

    Example:
        >>> result = StepResult(
        ...     step_name="fetch_data",
        ...     output={"revenue": 394.3},
        ...     duration_ms=1250.5,
        ...     token_count=150,
        ...     metadata={"source": "sec_api"},
        ... )
        >>>
        >>> if result.success:
        ...     print(f"Step completed in {result.duration_ms}ms")
        ... elif result.failed:
        ...     print(f"Error: {result.error_type}: {result.error}")

    See Also:
        ExecutionSummary: Aggregates StepResults for chain summary.
        ChainContext.add_result(): Method to add results to context.
    """

    step_name: str
    output: Any
    duration_ms: float
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None
    error_type: str | None = None
    error_traceback: str | None = None
    retry_count: int = 0
    skipped_reason: str | None = None

    @property
    def success(self) -> bool:
        """
        Check if the step completed successfully.

        Returns:
            bool: True if no error occurred and step was not skipped.

        Example:
            >>> if result.success:
            ...     process_output(result.output)
        """
        return self.error is None and self.skipped_reason is None

    @property
    def failed(self) -> bool:
        """
        Check if the step failed with an exception.

        Returns:
            bool: True if an error occurred during execution.

        Example:
            >>> if result.failed:
            ...     logger.error(f"{result.error_type}: {result.error}")
        """
        return self.error is not None

    @property
    def skipped(self) -> bool:
        """
        Check if the step was skipped.

        Returns:
            bool: True if step was skipped (e.g., due to unmet conditions).

        Example:
            >>> if result.skipped:
            ...     print(f"Skipped: {result.skipped_reason}")
        """
        return self.skipped_reason is not None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization (errors as strings).

        Returns:
            dict[str, Any]: JSON-serializable dictionary representation.

        Example:
            >>> result_dict = result.to_dict()
            >>> json.dumps(result_dict)  # Safe for JSON serialization
        """
        return {
            "step_name": self.step_name,
            "success": self.success,
            "output": self.output,
            "duration_ms": self.duration_ms,
            "token_count": self.token_count,
            "metadata": self.metadata,
            "error": str(self.error) if self.error else None,
            "error_type": self.error_type,
            "error_traceback": self.error_traceback,
            "retry_count": self.retry_count,
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class ExecutionSummary:
    """
    Summary of chain execution with partial success tracking.

    Enables graceful degradation - know exactly what succeeded,
    what failed, and what was skipped, even in continue mode.
    Useful for reporting, debugging, and error recovery.

    Attributes:
        chain_name (str): Name of the executed chain.
        request_id (str): Unique request identifier.
        total_steps (int): Total number of steps in the chain.
        completed_steps (int): Number of successfully completed steps.
        failed_steps (int): Number of failed steps.
        skipped_steps (int): Number of skipped steps.
        total_duration_ms (float): Total execution time in milliseconds.
        success (bool): True if all steps completed successfully.
        partial_success (bool): True if some steps succeeded and some failed.
        error (str | None): Error message if chain failed.
        error_type (str | None): Type of error that caused failure.
        error_traceback (str | None): Full traceback for debugging.
        step_results (list[StepResult]): Detailed results for each step.

    Properties:
        completion_rate (float): Percentage of steps that completed.

    Methods:
        add_result(): Add a step result and update counters.
        finalize(): Finalize the summary after execution.
        to_dict(): Convert to dictionary for serialization.
        get_failed_steps(): Get all failed step results.
        get_skipped_steps(): Get all skipped step results.
        get_successful_steps(): Get all successful step results.

    Example:
        >>> summary = ExecutionSummary(
        ...     chain_name="data_pipeline",
        ...     request_id="req_123",
        ...     total_steps=5,
        ... )
        >>>
        >>> # Add results as steps execute
        >>> summary.add_result(StepResult(step_name="step1", output={}, duration_ms=100))
        >>> summary.add_result(StepResult(step_name="step2", output={}, duration_ms=200))
        >>>
        >>> # Finalize and check status
        >>> summary.finalize()
        >>> print(f"Completion rate: {summary.completion_rate}%")
        >>> if summary.partial_success:
        ...     print("Some steps failed - check get_failed_steps()")

    See Also:
        StepResult: Individual step result dataclass.
        ChainContext: Uses ExecutionSummary for chain tracking.
    """

    chain_name: str
    request_id: str
    total_steps: int
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    total_duration_ms: float = 0.0
    success: bool = False
    partial_success: bool = False
    error: str | None = None
    error_type: str | None = None
    error_traceback: str | None = None

    # Per-step details
    step_results: list[StepResult] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        """
        Percentage of steps that completed successfully.

        Returns:
            float: Completion rate as percentage (0.0 to 100.0).

        Example:
            >>> if summary.completion_rate < 50:
            ...     logger.warning("Less than half of steps completed")
        """
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100

    def add_result(self, result: StepResult) -> None:
        """
        Add a step result and update counters.

        Args:
            result (StepResult): The step result to add.

        Example:
            >>> summary.add_result(StepResult(
            ...     step_name="fetch_data",
            ...     output={"data": [...]},
            ...     duration_ms=500,
            ... ))
        """
        self.step_results.append(result)
        self.total_duration_ms += result.duration_ms

        if result.success:
            self.completed_steps += 1
        elif result.skipped:
            self.skipped_steps += 1
        else:
            self.failed_steps += 1

    def finalize(self) -> None:
        """
        Finalize the summary after execution.

        Sets success and partial_success flags based on step results.
        Call this after all steps have been added.

        Example:
            >>> summary.finalize()
            >>> if summary.success:
            ...     print("All steps completed successfully!")
        """
        self.success = self.failed_steps == 0 and self.skipped_steps == 0
        self.partial_success = (
            self.completed_steps > 0 and
            (self.failed_steps > 0 or self.skipped_steps > 0)
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            dict[str, Any]: JSON-serializable dictionary representation.

        Example:
            >>> summary_json = json.dumps(summary.to_dict(), indent=2)
        """
        return {
            "chain_name": self.chain_name,
            "request_id": self.request_id,
            "success": self.success,
            "partial_success": self.partial_success,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "completion_rate": f"{self.completion_rate:.1f}%",
            "total_duration_ms": self.total_duration_ms,
            "error": self.error,
            "error_type": self.error_type,
            "step_results": [r.to_dict() for r in self.step_results],
        }

    def get_failed_steps(self) -> list[StepResult]:
        """
        Get all failed step results.

        Returns:
            list[StepResult]: List of results for failed steps.

        Example:
            >>> for failed in summary.get_failed_steps():
            ...     print(f"{failed.step_name}: {failed.error}")
        """
        return [r for r in self.step_results if r.failed]

    def get_skipped_steps(self) -> list[StepResult]:
        """
        Get all skipped step results.

        Returns:
            list[StepResult]: List of results for skipped steps.

        Example:
            >>> for skipped in summary.get_skipped_steps():
            ...     print(f"{skipped.step_name}: {skipped.skipped_reason}")
        """
        return [r for r in self.step_results if r.skipped]

    def get_successful_steps(self) -> list[StepResult]:
        """
        Get all successful step results.

        Returns:
            list[StepResult]: List of results for successful steps.

        Example:
            >>> successful = summary.get_successful_steps()
            >>> print(f"{len(successful)} steps completed successfully")
        """
        return [r for r in self.step_results if r.success]


@dataclass
class ExecutionResult:
    """
    Clean result API for chain execution with easy access to output and context.

    This class wraps the traditional dict-based result format and provides
    a cleaner, more intuitive API for accessing chain execution results.
    Use this instead of digging through nested dictionaries.

    Attributes:
        success (bool): True if chain completed successfully.
        output (Any): Output from the last step in the chain.
        context (ChainContext): Full context object for debugging.
        duration_ms (float): Total execution time in milliseconds.
        step_results (list[StepResult]): Detailed results for each step.
        request_id (str): Unique identifier for this execution.
        chain_name (str): Name of the executed chain.
        error (Exception | None): Error object if chain failed.
        error_message (str | None): Error message if chain failed.
        error_type (str | None): Type of error that occurred.
        error_traceback (str | None): Full traceback for debugging.
        partial_success (bool): True if some steps succeeded and some failed.

    Properties:
        step_timings (dict[str, float]): Map of step names to duration in ms.
        failed (bool): True if chain failed.
        step_count (int): Total number of steps executed.
        completed_steps (int): Number of successfully completed steps.
        failed_steps (int): Number of failed steps.

    Methods:
        get_step_output(step_name): Get output from a specific step.
        get_step_result(step_name): Get full result for a specific step.
        to_dict(): Convert to dict format (for backward compatibility).

    Example:
        >>> result = await ao.launch("my_chain", {"query": "Apple"})
        >>>
        >>> # Clean, explicit API
        >>> if result.success:
        ...     output = result.output  # Output from last step
        ...     print(f"Completed in {result.duration_ms}ms")
        ...     print(f"Steps: {result.step_count}")
        ...
        ...     # Access specific step output
        ...     data = result.get_step_output("fetch_data")
        ... else:
        ...     print(f"Failed: {result.error_message}")
        ...     print(f"Failed at step: {result.error_type}")
        ...
        ... # Per-step timings
        ... for step_name, timing in result.step_timings.items():
        ...     print(f"{step_name}: {timing}ms")

    Backward Compatibility:
        >>> # Convert to old dict format
        >>> legacy_result = result.to_dict()
        >>> print(legacy_result["success"])

    See Also:
        StepResult: Individual step execution result.
        ExecutionSummary: Aggregated execution summary.
        ChainContext: Context object for accessing full execution state.
    """

    success: bool
    output: Any
    context: "ChainContext"  # Forward reference
    duration_ms: float
    step_results: list[StepResult]
    request_id: str
    chain_name: str
    error: Exception | None = None
    error_message: str | None = None
    error_type: str | None = None
    error_traceback: str | None = None
    partial_success: bool = False

    @property
    def step_timings(self) -> dict[str, float]:
        """
        Get timing for each step.

        Returns:
            dict[str, float]: Map of step names to execution duration in ms.

        Example:
            >>> timings = result.step_timings
            >>> print(timings)
            {'step1': 150.5, 'step2': 325.8, 'step3': 89.2}
        """
        return {r.step_name: r.duration_ms for r in self.step_results}

    @property
    def failed(self) -> bool:
        """True if chain failed."""
        return not self.success

    @property
    def step_count(self) -> int:
        """Total number of steps executed."""
        return len(self.step_results)

    @property
    def completed_steps(self) -> int:
        """Number of successfully completed steps."""
        return sum(1 for r in self.step_results if r.success)

    @property
    def failed_steps(self) -> int:
        """Number of failed steps."""
        return sum(1 for r in self.step_results if r.failed)

    def get_step_output(self, step_name: str) -> Any:
        """
        Get output from a specific step.

        Args:
            step_name (str): Name of the step.

        Returns:
            Any: Output from the step, or None if step not found.

        Example:
            >>> data = result.get_step_output("fetch_data")
            >>> analysis = result.get_step_output("analyze_data")
        """
        result = self.get_step_result(step_name)
        return result.output if result else None

    def get_step_result(self, step_name: str) -> StepResult | None:
        """
        Get full result for a specific step.

        Args:
            step_name (str): Name of the step.

        Returns:
            StepResult | None: The step result, or None if step not found.

        Example:
            >>> step_result = result.get_step_result("fetch_data")
            >>> if step_result and step_result.success:
            ...     print(f"Duration: {step_result.duration_ms}ms")
            ...     print(f"Tokens: {step_result.token_count}")
        """
        for r in self.step_results:
            if r.step_name == step_name:
                return r
        return None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary format (for backward compatibility).

        Returns a dict in the traditional format used by older code.
        Use this for backward compatibility with existing code that
        expects the dict-based result format.

        Returns:
            dict[str, Any]: Result in dict format.

        Example:
            >>> legacy_result = result.to_dict()
            >>> print(legacy_result["success"])
            >>> print(legacy_result["results"][0]["step"])
        """
        result_dict: dict[str, Any] = {
            "request_id": self.request_id,
            "chain": self.chain_name,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "results": [
                {
                    "step": r.step_name,
                    "output": r.output,
                    "duration_ms": r.duration_ms,
                    "success": r.success,
                    "token_count": r.token_count,
                }
                for r in self.step_results
            ],
            "context": {
                "request_id": self.context.request_id,
                "created_at": self.context.created_at.isoformat(),
                "total_tokens": self.context.total_tokens,
                "results": [r.to_dict() for r in self.step_results],
                "data": self.context.to_dict(),
            },
        }

        if self.error:
            result_dict["error"] = {
                "type": self.error_type,
                "message": self.error_message,
                "traceback": self.error_traceback,
                "chain": self.chain_name,
                "request_id": self.request_id,
            }

        return result_dict

    @classmethod
    def from_dict(
        cls, result_dict: dict[str, Any], context: "ChainContext"
    ) -> "ExecutionResult":
        """
        Create ExecutionResult from dict format (for backward compatibility).

        Args:
            result_dict (dict): Result in dict format.
            context (ChainContext): Context object.

        Returns:
            ExecutionResult: New result object.

        Example:
            >>> legacy_result = await old_api.launch("chain", data)
            >>> result = ExecutionResult.from_dict(legacy_result, ctx)
            >>> print(result.output)
        """
        step_results = [
            StepResult(
                step_name=r.get("step", ""),
                output=r.get("output"),
                duration_ms=r.get("duration_ms", 0),
                token_count=r.get("token_count", 0),
            )
            for r in result_dict.get("results", [])
        ]

        # Get output from last step
        output = step_results[-1].output if step_results else None

        error_dict = result_dict.get("error", {})

        return cls(
            success=result_dict.get("success", False),
            output=output,
            context=context,
            duration_ms=result_dict.get("duration_ms", 0),
            step_results=step_results,
            request_id=result_dict.get("request_id", ""),
            chain_name=result_dict.get("chain", ""),
            error_message=error_dict.get("message") if error_dict else None,
            error_type=error_dict.get("type") if error_dict else None,
            error_traceback=error_dict.get("traceback") if error_dict else None,
        )


class ResultStore:
    """
    Manages step execution results.

    Extracted from ChainContext to follow Single Responsibility Principle.
    Provides thread-safe storage and retrieval of step results.
    """

    def __init__(self):
        self._results: list[StepResult] = []
        self._lock = __import__("threading").RLock()

    def add(self, result: StepResult) -> None:
        """Add a step result (thread-safe)"""
        with self._lock:
            self._results.append(result)

    def get(self, step_name: str) -> StepResult | None:
        """Get result for a specific step (most recent if multiple)"""
        with self._lock:
            for result in reversed(self._results):
                if result.step_name == step_name:
                    return result
            return None

    def get_all(self) -> list[StepResult]:
        """Get all results (thread-safe copy)"""
        with self._lock:
            return self._results.copy()

    def get_last(self) -> StepResult | None:
        """Get the most recent result"""
        with self._lock:
            return self._results[-1] if self._results else None


class CitationManager:
    """
    Manages citations and source tracking.

    Extracted from ChainContext to follow Single Responsibility Principle.
    Handles citation storage, verification, and summary generation.
    """

    def __init__(self, ctx_storage: dict[str, Any]):
        """
        Initialize citation manager.

        Args:
            ctx_storage: Reference to ChainContext storage dict for backward compatibility
        """
        self._storage = ctx_storage

    def add_citation(
        self,
        content: str,
        source_name: str,
        source_type: str = "agent",
        reasoning: str | None = None,
        document_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a citation to the collection"""
        from agentorchestrator.models.citation import Citation, CitationCollection

        collection = self._storage.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            collection = CitationCollection()
            self._storage["_citation_collection"] = collection

        citation = Citation(
            source_type=source_type,
            source_name=source_name,
            content=content,
            reasoning=reasoning,
            document_id=document_id,
            **kwargs,
        )
        collection.add(citation)

    def add_source_content(self, source_name: str, content: str) -> None:
        """Add raw source content for verification"""
        from agentorchestrator.models.citation import CitationCollection

        collection = self._storage.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            collection = CitationCollection()
            self._storage["_citation_collection"] = collection

        collection.add_source_chunk(source_name, content)

    def get_citations(self, source_name: str | None = None) -> list[Any]:
        """Get citations, optionally filtered by source"""
        from agentorchestrator.models.citation import CitationCollection

        collection = self._storage.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            return []

        if source_name:
            return collection.get_by_source(source_name)
        return collection.citations

    def verify_all(self) -> dict[str, bool]:
        """Verify all citations against stored sources"""
        from agentorchestrator.models.citation import CitationCollection

        collection = self._storage.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            return {}

        return collection.verify_all()

    def get_summary(self) -> dict[str, Any]:
        """Get citation coverage and verification summary"""
        from agentorchestrator.models.citation import CitationCollection

        collection = self._storage.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            return {"total": 0, "verified": 0, "by_source": {}}

        return collection.get_verification_summary()


class TokenTracker:
    """
    Tracks token usage for LLM context management.

    Extracted from ChainContext to follow Single Responsibility Principle.
    Calculates token counts across all scopes and provides budget warnings.
    """

    def __init__(
        self,
        store: dict[str, ContextEntry],
        step_stores: dict[str, dict[str, ContextEntry]],
        lock: Any,
    ):
        """
        Initialize token tracker.

        Args:
            store: Reference to main context storage
            step_stores: Reference to step-scoped storage
            lock: Lock for thread-safe access
        """
        self._store = store
        self._step_stores = step_stores
        self._lock = lock

    def get_total(self) -> int:
        """Get total token count across all scopes"""
        with self._lock:
            total = sum(entry.token_count for entry in self._store.values())
            for step_store in self._step_stores.values():
                total += sum(entry.token_count for entry in step_store.values())
            return total

    def check_budget(self, max_tokens: int, threshold: float = 0.8) -> dict[str, Any]:
        """
        Check token budget status.

        Args:
            max_tokens: Maximum token budget
            threshold: Warning threshold (default 0.8 = 80%)

        Returns:
            Dict with status, total, max, percentage, and warning flag
        """
        total = self.get_total()
        percentage = (total / max_tokens) * 100 if max_tokens > 0 else 0
        return {
            "total": total,
            "max": max_tokens,
            "percentage": percentage,
            "warning": total > max_tokens * threshold,
            "exceeded": total > max_tokens,
        }


class ChainContext(Generic[StateModel]):
    """
    Manages shared state and data flow between chain steps.

    ChainContext is the central data structure that flows through all steps
    in a chain execution. It provides scoped storage, token tracking for
    LLM context management, automatic cleanup, and citation support.

    Security:
        **WARNING**: Do NOT store secrets (API keys, passwords, tokens) in
        context. Use SecretString wrappers or external secret management.
        If you must store sensitive data, use `to_dict(exclude_keys=[...])`
        to filter it from exports/logs. See docs for secret management best
        practices.

    Attributes:
        request_id (str): Unique identifier for this chain execution.
        max_tokens (int): Maximum token budget for LLM context.
        created_at (datetime): When the context was created.
        metadata (dict[str, Any]): Additional context metadata.

    Properties:
        current_step (str | None): Name of the currently executing step.
        total_tokens (int): Total tokens currently stored in context.
        results (list[StepResult]): All step results in execution order.
        last_result (StepResult | None): Most recent step result.

    Methods:
        set(): Store a value in the context with specified scope.
        get(): Retrieve a value from the context.
        get_entry(): Get the full context entry including metadata.
        has(): Check if a key exists in context.
        delete(): Remove a key from context.
        keys(): Get all keys, optionally filtered by scope.
        add_result(): Add a step execution result.
        get_result(): Get result for a specific step.
        enter_step(): Enter a step execution scope.
        exit_step(): Exit a step execution scope with cleanup.
        step_scope(): Async context manager for step execution.
        step_scope_sync(): Sync context manager for step execution.
        to_dict(): Export context as dictionary.
        clone(): Create a deep copy of the context.
        add_citation(): Add a citation for source tracking.
        add_source_content(): Add raw source content for verification.
        get_citations(): Get citations from the context.
        verify_citations(): Verify all citations against sources.
        get_citation_summary(): Get citation coverage summary.

    Example:
        >>> from agentorchestrator.core.context import ChainContext, ContextScope
        >>>
        >>> # Create context
        >>> ctx = ChainContext(
        ...     request_id="req_123",
        ...     initial_data={"query": "Apple revenue"},
        ...     max_tokens=100000,
        ... )
        >>>
        >>> # Store and retrieve data
        >>> ctx.set("company", "Apple Inc", scope=ContextScope.CHAIN)
        >>> company = ctx.get("company")  # "Apple Inc"
        >>>
        >>> # Use step scope for automatic cleanup
        >>> async with ctx.step_scope("process_data"):
        ...     ctx.set("temp", {...}, scope=ContextScope.STEP)
        ...     # temp is available here
        ... # temp is automatically cleaned up
        >>>
        >>> # Track step results
        >>> ctx.add_result(StepResult(
        ...     step_name="fetch",
        ...     output={"revenue": 394.3},
        ...     duration_ms=500,
        ... ))
        >>>
        >>> # Add citations for provenance
        >>> ctx.add_citation(
        ...     content="Total revenue was $394.3 billion",
        ...     source_name="sec_filing",
        ...     reasoning="Direct revenue figure from 10-K",
        ... )

    Thread-safety:
        ChainContext is designed for concurrent access:
        - Uses threading.RLock for all operations (works in both sync and async contexts)
        - Lock ordering issue fixed: consistent use of single lock type prevents deadlocks
        - Uses contextvars for per-task step tracking (safe for parallel steps)
        - STEP-scoped data is isolated per step (no cross-step interference)

    Race Conditions (Parallel Steps):
        When parallel steps modify the same CHAIN-scoped key, race conditions
        are possible. Mitigation strategies:

        1. **Use STEP-scoped data** for step-local temporary data:
           >>> ctx.set("temp", value, scope=ContextScope.STEP)

        2. **Use StateStore** for shared state with validation:
           >>> async with ctx.edit_state() as state:
           ...     state.counter += 1  # Atomic and validated

        3. **Use async_set()** for explicit atomic CHAIN-scoped updates:
           >>> await ctx.async_set("shared_key", new_value)

        4. **Avoid read-modify-write patterns** in parallel steps:
           # BAD: Race condition possible
           >>> value = ctx.get("counter")
           >>> ctx.set("counter", value + 1)

           # GOOD: Use StateStore or async_set with atomic updates
           >>> async with ctx.edit_state() as state:
           ...     state.counter += 1

    See Also:
        ContextScope: Enum for data lifetime scopes.
        StepResult: Dataclass for step execution results.
        ContextManager: Manager for multiple contexts.
    """

    def __init__(
        self,
        request_id: str,
        initial_data: dict[str, Any] | None = None,
        max_tokens: int = 100000,
        state_model: type[StateModel] | None = None,
        resource_manager: Any | None = None,
    ):
        """
        Initialize a new ChainContext.

        Args:
            request_id (str): Unique identifier for this chain execution.
                Used for tracing, logging, and context retrieval.
            initial_data (dict[str, Any] | None): Initial data to populate
                the context with. All keys are stored with CHAIN scope.
            max_tokens (int): Maximum token budget for LLM context management.
                Default: 100000. Used for tracking context size.
            state_model (type[StateModel] | None): Optional Pydantic model
                for type-safe state management. If provided, enables
                ctx.state and ctx.edit_state() for typed access.
            resource_manager (Any | None): Optional ResourceManager instance
                for resource injection. Enables ctx.get_resource() in steps.

        Example:
            >>> ctx = ChainContext(
            ...     request_id="req_abc123",
            ...     initial_data={"company": "Apple", "year": 2024},
            ...     max_tokens=50000,
            ... )
            >>>
            >>> # With Pydantic state model
            >>> from pydantic import BaseModel
            >>> class MyState(BaseModel):
            ...     counter: int = 0
            >>> ctx = ChainContext(
            ...     request_id="req_123",
            ...     state_model=MyState,
            ... )
        """
        self.request_id = request_id
        self.max_tokens = max_tokens
        self._store: dict[str, ContextEntry] = {}
        self._step_stores: dict[str, dict[str, ContextEntry]] = {}  # Per-step isolated storage
        # Use only threading.RLock for all locking - works in both sync and async contexts
        # This prevents deadlock issues from mixed lock ordering
        self._sync_lock = __import__("threading").RLock()
        self.created_at = datetime.utcnow()
        self.metadata: dict[str, Any] = {}

        # Initialize extracted components (following SRP)
        self._result_store = ResultStore()
        self._citation_manager = CitationManager(self._store)
        self._token_tracker = TokenTracker(self._store, self._step_stores, self._sync_lock)

        # Resource manager for dependency injection
        self._resource_manager = resource_manager

        # Type-safe state management (optional)
        self._state_store: "StateStore[StateModel] | None" = None
        if state_model is not None:
            try:
                from agentorchestrator.core.state import StateStore
                self._state_store = StateStore(state_model)
            except ImportError:
                logger.warning(
                    "Pydantic state model requested but pydantic not installed. "
                    "Install with: pip install pydantic"
                )

        # Initialize with any provided data
        if initial_data:
            for key, value in initial_data.items():
                self.set(key, value, scope=ContextScope.CHAIN)

    @property
    def current_step(self) -> str | None:
        """
        Get current step name (async-task-safe via contextvars).

        Returns:
            str | None: Name of the currently executing step, or None
                if not within a step scope.

        Example:
            >>> async with ctx.step_scope("my_step"):
            ...     print(ctx.current_step)  # "my_step"
            >>> print(ctx.current_step)  # None
        """
        return _current_step_var.get()

    @property
    def total_tokens(self) -> int:
        """
        Total tokens currently stored in context.

        Now delegated to TokenTracker for better separation of concerns.

        Returns:
            int: Total estimated token count.

        Example:
            >>> if ctx.total_tokens > ctx.max_tokens * 0.8:
            ...     logger.warning("Context approaching token limit")
        """
        return self._token_tracker.get_total()

    @property
    def results(self) -> list[StepResult]:
        """
        All step results in execution order.

        Now delegated to ResultStore for better separation of concerns.

        Returns:
            list[StepResult]: Copy of the results list (thread-safe).

        Example:
            >>> for result in ctx.results:
            ...     print(f"{result.step_name}: {result.duration_ms}ms")
        """
        return self._result_store.get_all()

    @property
    def last_result(self) -> StepResult | None:
        """
        Most recent step result.

        Now delegated to ResultStore for better separation of concerns.

        Returns:
            StepResult | None: The last added result, or None if empty.

        Example:
            >>> if ctx.last_result and ctx.last_result.success:
            ...     process(ctx.last_result.output)
        """
        return self._result_store.get_last()
    
    @property
    def state(self) -> StateModel:
        """
        Get type-safe state (read-only).
        
        Only available if context was created with state_model parameter.
        For modifications, use edit_state() context manager.
        
        Returns:
            StateModel: Current state instance with type hints.
        
        Raises:
            RuntimeError: If context was not created with a state_model.
        
        Example:
            >>> from pydantic import BaseModel
            >>> class MyState(BaseModel):
            ...     counter: int = 0
            >>> ctx = ChainContext("req_1", state_model=MyState)
            >>> count = ctx.state.counter  # Type-safe access!
        
        See Also:
            edit_state(): For atomic state modifications.
        """
        if self._state_store is None:
            raise RuntimeError(
                "Context was not created with a state_model. "
                "Create context with state_model parameter to use typed state."
            )
        return self._state_store.state

    def _is_async_context(self) -> bool:
        """Check if we're running inside an async event loop."""
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    def _warn_parallel_chain_scope_access(self, key: str, is_write: bool = True) -> None:
        """
        Warn when CHAIN-scoped data is accessed in parallel async context.

        This method detects potential race conditions when parallel steps
        modify shared CHAIN-scoped data without using async_set() or edit_state().
        """
        if not self._is_async_context():
            return

        # Check if key already exists (read-modify-write pattern risk)
        if is_write and key in self._store:
            current_step = self.current_step
            existing_entry = self._store[key]
            if existing_entry.source_step and existing_entry.source_step != current_step:
                logger.warning(
                    f"Potential race condition: Step '{current_step}' is modifying "
                    f"CHAIN-scoped key '{key}' that was set by step '{existing_entry.source_step}'. "
                    f"For parallel steps, use `await ctx.async_set()` or `async with ctx.edit_state()` "
                    f"to ensure atomic updates. See docs/understanding/context.md for details."
                )

    def set(
        self,
        key: str,
        value: Any,
        scope: ContextScope = ContextScope.CHAIN,
        token_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Store a value in the context.

        This method uses both sync and async locking to prevent race conditions
        in parallel step execution.

        Args:
            key (str): Unique identifier for the value.
            value (Any): The data to store (any JSON-serializable type).
            scope (ContextScope): Lifetime scope of the data.
                Default: ContextScope.CHAIN.
            token_count (int): Estimated token count for LLM tracking.
                Default: 0.
            metadata (dict[str, Any] | None): Additional metadata about
                this entry. Default: None.

        Note:
            STEP-scoped data is isolated per step - parallel steps cannot
            see or interfere with each other's step-scoped data.

            For CHAIN-scoped data modified by parallel async steps, consider
            using `await ctx.async_set()` for explicit async-safe operations,
            or use `async with ctx.edit_state()` for validated state updates.

        Example:
            >>> # Store chain-wide data
            >>> ctx.set("company", "Apple Inc", scope=ContextScope.CHAIN)
            >>>
            >>> # Store with token tracking
            >>> ctx.set(
            ...     "document",
            ...     long_text,
            ...     token_count=1500,
            ...     metadata={"source": "sec_filing"},
            ... )
            >>>
            >>> # Step-scoped temporary data
            >>> ctx.set("temp_calc", result, scope=ContextScope.STEP)
        """
        current_step = self.current_step

        entry = ContextEntry(
            key=key,
            value=value,
            scope=scope,
            token_count=token_count,
            source_step=current_step,
            metadata=metadata or {},
        )

        # Warn about potential race conditions in parallel async steps
        if scope == ContextScope.CHAIN:
            self._warn_parallel_chain_scope_access(key, is_write=True)

        # Use sync lock - this serializes access even from parallel async tasks
        # since they share the same thread. The lock prevents interleaving
        # of the read-check-write operations below.
        with self._sync_lock:
            if scope == ContextScope.STEP:
                # Step-scoped data goes into per-step isolated storage
                if current_step is None:
                    logger.warning(
                        f"Setting STEP-scoped key '{key}' outside of a step context. "
                        "It will be stored in a temporary namespace."
                    )
                    step_key = "__no_step__"
                else:
                    step_key = current_step

                if step_key not in self._step_stores:
                    self._step_stores[step_key] = {}

                step_store = self._step_stores[step_key]
                if key in step_store:
                    entry.created_at = step_store[key].created_at
                step_store[key] = entry
            elif scope == ContextScope.GLOBAL:
                # GLOBAL scoped data goes to the singleton ContextManager's global store
                # This allows it to persist across multiple chain executions
                manager = ContextManager()
                manager.set_global(key, entry)
            else:
                # CHAIN scoped data goes into per-context shared store
                if key in self._store:
                    entry.created_at = self._store[key].created_at
                self._store[key] = entry

        logger.debug(
            f"Context set: {key} (scope={scope.value}, step={current_step}, tokens={token_count})"
        )

    async def async_set(
        self,
        key: str,
        value: Any,
        scope: ContextScope = ContextScope.CHAIN,
        token_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Store a value in the context with async-safe locking.

        This method provides explicit async-safe atomic operations for
        concurrent coroutines. Use this when:
        - Multiple parallel steps may write to the same CHAIN-scoped key
        - You need guaranteed atomicity in async code
        - You're modifying shared state from parallel workers

        Args:
            key (str): Unique identifier for the value.
            value (Any): The data to store (any JSON-serializable type).
            scope (ContextScope): Lifetime scope of the data.
                Default: ContextScope.CHAIN.
            token_count (int): Estimated token count for LLM tracking.
                Default: 0.
            metadata (dict[str, Any] | None): Additional metadata about
                this entry. Default: None.

        Thread-Safety Note:
            Uses threading.RLock which is safe for both sync and async contexts.
            The RLock ensures atomic operations across concurrent tasks.

        Best Practices for Parallel Steps:
            1. Use STEP-scoped data for step-local temporary data (isolated per step)
            2. Use StateStore (ctx.edit_state()) for shared state with validation
            3. Use async_set() for explicit atomic CHAIN-scoped updates
            4. Avoid read-modify-write patterns on shared keys in parallel steps

        Example:
            >>> # In parallel steps that might race
            >>> await ctx.async_set("shared_counter", new_value)
            >>>
            >>> # For shared state, prefer StateStore
            >>> async with ctx.edit_state() as state:
            ...     state.counter += 1  # Atomic and validated
        """
        current_step = self.current_step

        entry = ContextEntry(
            key=key,
            value=value,
            scope=scope,
            token_count=token_count,
            source_step=current_step,
            metadata=metadata or {},
        )

        # Use threading.RLock for consistent locking across sync and async contexts
        # This prevents deadlock from inconsistent lock ordering
        with self._sync_lock:
            if scope == ContextScope.STEP:
                # Step-scoped data goes into per-step isolated storage
                if current_step is None:
                    logger.warning(
                        f"Setting STEP-scoped key '{key}' outside of a step context. "
                        "It will be stored in a temporary namespace."
                    )
                    step_key = "__no_step__"
                else:
                    step_key = current_step

                if step_key not in self._step_stores:
                    self._step_stores[step_key] = {}

                step_store = self._step_stores[step_key]
                if key in step_store:
                    entry.created_at = step_store[key].created_at
                step_store[key] = entry
            elif scope == ContextScope.GLOBAL:
                # GLOBAL scoped data goes to the singleton ContextManager's global store
                manager = ContextManager()
                manager.set_global(key, entry)
            else:
                # CHAIN scoped data goes into per-context shared store
                if key in self._store:
                    entry.created_at = self._store[key].created_at
                self._store[key] = entry

        logger.debug(
            f"Context async_set: {key} (scope={scope.value}, step={current_step}, tokens={token_count})"
        )

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a value from the context.

        Checks step-scoped storage first (current step only),
        then chain-scoped storage, then global storage.

        Args:
            key (str): The key to look up.
            default (Any): Value to return if key not found. Default: None.

        Returns:
            Any: The stored value or default.

        Example:
            >>> company = ctx.get("company")
            >>> timeout = ctx.get("timeout", default=30)
        """
        with self._sync_lock:
            # First check step-scoped storage for current step
            current_step = self.current_step
            if current_step and current_step in self._step_stores:
                step_store = self._step_stores[current_step]
                if key in step_store:
                    return step_store[key].value

            # Then check chain-scoped store
            entry = self._store.get(key)
            if entry is not None:
                return entry.value

            # Finally check global store (ContextManager singleton)
            manager = ContextManager()
            global_entry = manager.get_global(key)
            if global_entry is not None:
                # Global store contains ContextEntry objects
                if isinstance(global_entry, ContextEntry):
                    return global_entry.value
                return global_entry
            return default

    def get_entry(self, key: str) -> ContextEntry | None:
        """
        Get the full context entry including metadata.

        Unlike get(), this returns the ContextEntry wrapper with
        all metadata (scope, timestamps, token count, etc.).

        Args:
            key (str): The key to look up.

        Returns:
            ContextEntry | None: The entry or None if not found.

        Example:
            >>> entry = ctx.get_entry("company")
            >>> if entry:
            ...     print(f"Created by: {entry.source_step}")
            ...     print(f"Tokens: {entry.token_count}")
        """
        with self._sync_lock:
            # First check step-scoped storage
            current_step = self.current_step
            if current_step and current_step in self._step_stores:
                step_store = self._step_stores[current_step]
                if key in step_store:
                    return step_store[key]

            # Then check chain-scoped store
            entry = self._store.get(key)
            if entry is not None:
                return entry

            # Finally check global store
            manager = ContextManager()
            global_entry = manager.get_global(key)
            if isinstance(global_entry, ContextEntry):
                return global_entry
            return None

    def has(self, key: str) -> bool:
        """
        Check if a key exists in context.

        Checks step-scoped, chain-scoped, and global storage.

        Args:
            key (str): The key to check.

        Returns:
            bool: True if the key exists.

        Example:
            >>> if ctx.has("company"):
            ...     process_company(ctx.get("company"))
        """
        with self._sync_lock:
            # Check step-scoped storage first
            current_step = self.current_step
            if current_step and current_step in self._step_stores:
                if key in self._step_stores[current_step]:
                    return True
            # Check chain-scoped store
            if key in self._store:
                return True
            # Check global store
            manager = ContextManager()
            return manager.get_global(key) is not None

    def delete(self, key: str) -> bool:
        """
        Remove a key from context.

        Checks step-scoped storage first, then chain-scoped, then global storage.

        Args:
            key (str): The key to delete.

        Returns:
            bool: True if key was found and deleted.

        Example:
            >>> if ctx.delete("temp_data"):
            ...     print("Temporary data cleaned up")
        """
        with self._sync_lock:
            # Check step-scoped storage first
            current_step = self.current_step
            if current_step and current_step in self._step_stores:
                step_store = self._step_stores[current_step]
                if key in step_store:
                    del step_store[key]
                    return True

            # Check chain-scoped store
            if key in self._store:
                del self._store[key]
                return True

            # Check global store
            manager = ContextManager()
            if manager.get_global(key) is not None:
                manager.delete_global(key)
                return True
            return False

    def keys(self, scope: ContextScope | None = None) -> list[str]:
        """
        Get all keys, optionally filtered by scope.

        Args:
            scope (ContextScope | None): Filter by scope. If None, returns
                all keys from all scopes (step + chain + global).

        Returns:
            list[str]: List of keys matching the filter.

        Example:
            >>> # Get all keys
            >>> all_keys = ctx.keys()
            >>>
            >>> # Get only step-scoped keys
            >>> step_keys = ctx.keys(scope=ContextScope.STEP)
            >>>
            >>> # Get only chain-scoped keys
            >>> chain_keys = ctx.keys(scope=ContextScope.CHAIN)
            >>>
            >>> # Get only global keys
            >>> global_keys = ctx.keys(scope=ContextScope.GLOBAL)
        """
        with self._sync_lock:
            if scope == ContextScope.STEP:
                # Only return keys from current step's storage
                current_step = self.current_step
                if current_step and current_step in self._step_stores:
                    return list(self._step_stores[current_step].keys())
                return []
            elif scope == ContextScope.GLOBAL:
                # Return keys from the global store
                manager = ContextManager()
                return manager.global_keys()
            elif scope == ContextScope.CHAIN:
                # Only from chain-scoped store (filter out any misplaced entries)
                return [k for k, v in self._store.items() if v.scope == ContextScope.CHAIN]
            else:
                # None - Return all keys (step + chain + global)
                all_keys = list(self._store.keys())
                current_step = self.current_step
                if current_step and current_step in self._step_stores:
                    all_keys.extend(self._step_stores[current_step].keys())
                # Include global keys
                manager = ContextManager()
                all_keys.extend(manager.global_keys())
                return all_keys

    def keys_for_step(self, step_name: str) -> list[str]:
        """
        Get all CHAIN/GLOBAL keys produced by a specific step.

        Uses the source_step metadata recorded on ContextEntry.
        This is useful for middleware that needs to update or replace
        a step's outputs (e.g., summarization, offloading).
        """
        with self._sync_lock:
            return [
                key for key, entry in self._store.items()
                if entry.source_step == step_name
            ]

    def update_step_outputs(
        self,
        step_name: str,
        value: Any,
        keys: list[str] | None = None,
    ) -> list[str]:
        """
        Replace stored outputs for a step with a new value.

        Args:
            step_name: Name of the step.
            value: Replacement value to store.
            keys: Optional explicit list of keys to update. If None, uses
                keys_for_step(step_name).

        Returns:
            list[str]: Keys that were updated.
        """
        keys = keys or self.keys_for_step(step_name)
        updated: list[str] = []
        for key in keys:
            entry = self.get_entry(key)
            if entry is None:
                continue
            self.set(key, value, scope=entry.scope)
            updated.append(key)
        return updated

    def add_result(self, result: StepResult) -> None:
        """
        Add a step execution result.

        Now delegated to ResultStore for better separation of concerns.

        Args:
            result (StepResult): The step result to add.

        Example:
            >>> ctx.add_result(StepResult(
            ...     step_name="fetch_data",
            ...     output={"revenue": 394.3},
            ...     duration_ms=500,
            ...     token_count=100,
            ... ))
        """
        self._result_store.add(result)
        logger.debug(f"Result added: {result.step_name} (success={result.success})")

    def get_result(self, step_name: str) -> StepResult | None:
        """
        Get result for a specific step.

        Now delegated to ResultStore for better separation of concerns.

        Args:
            step_name (str): Name of the step.

        Returns:
            StepResult | None: The result or None if step not found.

        Example:
            >>> result = ctx.get_result("fetch_data")
            >>> if result and result.success:
            ...     print(f"Fetch completed in {result.duration_ms}ms")
        """
        return self._result_store.get(step_name)

    async def get_resource(self, name: str) -> Any:
        """
        Get a resource by name (async, lazy initialization).

        This is a convenience method for accessing resources registered
        with the orchestrator. Resources are lazily initialized on first access.

        Args:
            name (str): Resource identifier.

        Returns:
            Any: The resource instance.

        Raises:
            KeyError: If resource not registered or resource_manager not available.

        Example:
            >>> async def my_step(ctx: ChainContext):
            ...     db = await ctx.get_resource("db")
            ...     s3 = await ctx.get_resource("s3_client")
            ...     # Use resources...
        """
        if self._resource_manager is None:
            raise KeyError(
                f"Resource '{name}' not available: No resource manager configured for this context"
            )
        return await self._resource_manager.get(name)

    def get_resource_sync(self, name: str) -> Any:
        """
        Get a resource by name (sync version).

        For async resources, this will run in a new event loop if needed.

        Args:
            name (str): Resource identifier.

        Returns:
            Any: The resource instance.

        Raises:
            KeyError: If resource not registered or resource_manager not available.

        Example:
            >>> def my_step(ctx: ChainContext):
            ...     db = ctx.get_resource_sync("db")
            ...     # Use resource...
        """
        if self._resource_manager is None:
            raise KeyError(
                f"Resource '{name}' not available: No resource manager configured for this context"
            )
        return self._resource_manager.get_sync(name)

    def enter_step(self, step_name: str) -> contextvars.Token:
        """
        Called when entering a new step.

        Uses contextvars for async-task-safe step tracking, so parallel
        steps each have their own current_step value.

        Args:
            step_name (str): Name of the step being entered.

        Returns:
            contextvars.Token: Token that must be passed to exit_step()
                to properly reset the contextvar.

        Note:
            Prefer using step_scope() context manager instead of
            manually calling enter_step/exit_step.

        Example:
            >>> token = ctx.enter_step("my_step")
            >>> try:
            ...     # Step execution
            ...     pass
            ... finally:
            ...     ctx.exit_step(token)
        """
        token = _current_step_var.set(step_name)
        logger.debug(f"Entering step: {step_name}")
        return token

    def exit_step(self, token: contextvars.Token | None = None) -> None:
        """
        Called when exiting a step - cleans up step-scoped data.

        Cleans up only THIS step's storage, not other parallel steps.

        Args:
            token (contextvars.Token | None): The token returned by
                enter_step(). If provided, uses it to properly reset
                the contextvar. If not provided, resets to None.

        Note:
            Prefer using step_scope() context manager instead of
            manually calling enter_step/exit_step.

        Example:
            >>> token = ctx.enter_step("my_step")
            >>> try:
            ...     ctx.set("temp", value, scope=ContextScope.STEP)
            ... finally:
            ...     ctx.exit_step(token)  # temp is cleaned up
        """
        step_name = self.current_step

        # Clean up only this step's storage
        with self._sync_lock:
            if step_name and step_name in self._step_stores:
                cleaned_count = len(self._step_stores[step_name])
                del self._step_stores[step_name]
            else:
                cleaned_count = 0

            # Also clean up __no_step__ orphan entries to prevent memory leaks
            if "__no_step__" in self._step_stores:
                orphan_count = len(self._step_stores["__no_step__"])
                if orphan_count > 0:
                    logger.debug(f"Cleaning up {orphan_count} orphan __no_step__ entries")
                    del self._step_stores["__no_step__"]
                    cleaned_count += orphan_count

        # Reset the contextvar
        if token is not None:
            _current_step_var.reset(token)
        else:
            _current_step_var.set(None)

        logger.debug(f"Exiting step: {step_name}, cleaned {cleaned_count} step-scoped entries")

    @asynccontextmanager
    async def step_scope(self, step_name: str) -> AsyncIterator["ChainContext"]:
        """
        Async context manager for step execution with automatic cleanup.

        Ensures step-scoped data is always cleaned up, even if the step
        raises an exception. This prevents data leaks between steps.

        Cancellation Safety:
            Cleanup is guaranteed even during task cancellation or timeout.
            The finally block uses synchronous cleanup (exit_step) which
            cannot be interrupted by asyncio.CancelledError, ensuring
            step-scoped data is always removed from memory.

            Tested scenarios:
            - Task cancellation (task.cancel())
            - Asyncio timeout (asyncio.timeout)
            - Exception propagation
            - Multiple parallel cancellations
            - Nested scope cancellations

        Args:
            step_name (str): Name of the step being executed.

        Yields:
            ChainContext: The context (self) for chaining.

        Example:
            >>> async with ctx.step_scope("process_data"):
            ...     # Set step-scoped data
            ...     ctx.set("temp", intermediate_result, scope=ContextScope.STEP)
            ...
            ...     # Do processing
            ...     result = await process(ctx.get("temp"))
            ...
            ...     # Store chain-scoped result
            ...     ctx.set("result", result, scope=ContextScope.CHAIN)
            ...
            ... # temp is automatically cleaned up here, result persists

        See Also:
            step_scope_sync(): Synchronous version.
            enter_step(), exit_step(): Low-level step management.
        """
        token = self.enter_step(step_name)
        try:
            yield self
        finally:
            self.exit_step(token)

    @contextmanager
    def step_scope_sync(self, step_name: str) -> Iterator["ChainContext"]:
        """
        Sync context manager for step execution with automatic cleanup.

        Synchronous version of step_scope() for non-async code.

        Args:
            step_name (str): Name of the step being executed.

        Yields:
            ChainContext: The context (self) for chaining.

        Example:
            >>> with ctx.step_scope_sync("process_data"):
            ...     ctx.set("temp", value, scope=ContextScope.STEP)
            ...     # ... step logic ...
            ... # Automatic cleanup on exit

        See Also:
            step_scope(): Async version.
        """
        token = self.enter_step(step_name)
        try:
            yield self
        finally:
            self.exit_step(token)
    
    @asynccontextmanager
    async def edit_state(self) -> AsyncIterator[StateModel]:
        """
        Async context manager for atomic state updates.
        
        Provides type-safe, atomic modifications to the Pydantic state model.
        Changes are validated and committed atomically on exit.
        
        Only available if context was created with state_model parameter.
        
        Yields:
            StateModel: Mutable state for modification with type hints.
        
        Raises:
            RuntimeError: If context was not created with a state_model.
            ValidationError: If modified state fails Pydantic validation.
        
        Example:
            >>> from pydantic import BaseModel, Field
            >>> class PipelineState(BaseModel):
            ...     counter: int = 0
            ...     items: list[str] = Field(default_factory=list)
            >>>
            >>> ctx = ChainContext("req_1", state_model=PipelineState)
            >>>
            >>> async with ctx.edit_state() as state:
            ...     state.counter += 1  # Type-checked!
            ...     state.items.append("new_item")  # IDE autocomplete!
            ...     # Validated and committed atomically on exit
        
        Thread-safety:
            Uses asyncio.Lock to ensure only one edit at a time.
            Multiple concurrent edits will be serialized.
        
        See Also:
            state: Read-only state access.
            StateStore: Underlying state management.
        """
        if self._state_store is None:
            raise RuntimeError(
                "Context was not created with a state_model. "
                "Create context with state_model parameter to use typed state."
            )
        
        async with self._state_store.edit() as state:
            yield state

    def to_dict(
        self,
        serializer: "ContextSerializer | None" = None,
        include_data: bool = True,
        include_state: bool = True,
        exclude_keys: "set[str] | list[str] | None" = None,
    ) -> dict[str, Any]:
        """
        Export context as dictionary (for serialization).

        Args:
            serializer (ContextSerializer | None): Optional serializer for
                redacting/truncating large fields. If None, uses default
                serialization (may be large!).
            include_data (bool): Whether to include context data.
                Set False for lightweight summary. Default: True.
            include_state (bool): Whether to include typed state (if present).
                Set False to exclude Pydantic state from export. Default: True.
            exclude_keys (set[str] | list[str] | None): Keys to exclude from
                data export for security (e.g., API keys, passwords, tokens).
                Recommended to exclude sensitive data. Default: None.

        Returns:
            dict[str, Any]: JSON-serializable dictionary.

        Security:
            IMPORTANT: Do not store secrets in context. If you must store
            sensitive data, use exclude_keys to filter it from to_dict()
            exports, or use SecretString wrappers.

        Example:
            >>> # Full export (may be large)
            >>> full_dict = ctx.to_dict()
            >>>
            >>> # With truncation for logging
            >>> from agentorchestrator.core.serializers import TruncatingSerializer
            >>> safe_dict = ctx.to_dict(serializer=TruncatingSerializer(max_size=1000))
            >>>
            >>> # Lightweight summary only
            >>> summary = ctx.to_dict(include_data=False)
            >>>
            >>> # Exclude sensitive keys (RECOMMENDED for logging/serialization)
            >>> safe_export = ctx.to_dict(exclude_keys=["api_key", "password", "token"])
            >>>
            >>> # Include typed state for checkpointing
            >>> checkpoint = ctx.to_dict(include_state=True)
            >>> # checkpoint["typed_state"] = {"model": "MyState", "data": {...}}
        """
        with self._sync_lock:
            result = {
                "request_id": self.request_id,
                "created_at": self.created_at.isoformat(),
                "total_tokens": self.total_tokens,
                "results": [
                    {
                        "step": r.step_name,
                        "success": r.success,
                        "duration_ms": r.duration_ms,
                    }
                    for r in self._result_store.get_all()
                ],
            }

            if include_data:
                # Filter out excluded keys for security
                excluded = set(exclude_keys) if exclude_keys else set()
                filtered_store = {
                    k: v.value
                    for k, v in self._store.items()
                    if k not in excluded
                }

                if serializer:
                    result["data"] = serializer.serialize_context_data(filtered_store)
                else:
                    result["data"] = filtered_store

            # Include typed state if present and requested
            if include_state and self._state_store is not None:
                result["typed_state"] = {
                    "model": self._state_store.model_class.__name__,
                    "module": self._state_store.model_class.__module__,
                    "data": self._state_store.to_dict(),
                }

            return result

    def clone(self) -> "ChainContext":
        """
        Create a deep copy of the context (thread-safe).

        Useful for creating isolated context copies for parallel
        execution or testing.

        Returns:
            ChainContext: A new context with deep-copied data.

        Example:
            >>> ctx_copy = ctx.clone()
            >>> ctx_copy.set("new_key", "value")  # Doesn't affect original
        """
        with self._sync_lock:
            new_ctx = ChainContext(
                request_id=self.request_id,
                max_tokens=self.max_tokens,
            )
            new_ctx._store = copy.deepcopy(self._store)
            new_ctx._step_stores = copy.deepcopy(self._step_stores)
            new_ctx.metadata = copy.deepcopy(self.metadata)

            # Clone extracted components
            new_ctx._result_store = ResultStore()
            for result in self._result_store.get_all():
                new_ctx._result_store.add(copy.deepcopy(result))

            new_ctx._citation_manager = CitationManager(new_ctx._store)
            new_ctx._token_tracker = TokenTracker(
                new_ctx._store, new_ctx._step_stores, new_ctx._sync_lock
            )

            if self._state_store is not None:
                new_ctx._state_store = self._state_store.clone()

            return new_ctx

    def load_state_from_dict(
        self,
        typed_state_dict: dict[str, Any],
        state_model: type | None = None,
    ) -> None:
        """
        Restore typed state from dictionary (for checkpoint restoration).

        This method loads typed state that was exported via to_dict() with
        include_state=True. It reconstructs the StateStore and loads the data.

        Args:
            typed_state_dict: Dictionary with keys "model", "module", "data"
                as produced by to_dict(include_state=True).
            state_model: Optional Pydantic model class. If None, attempts
                to import the model using "module" and "model" from the dict.

        Raises:
            RuntimeError: If state model cannot be resolved.
            ValidationError: If data doesn't match the model schema.

        Example:
            >>> # Save checkpoint
            >>> checkpoint = ctx.to_dict(include_state=True)
            >>>
            >>> # Later, restore
            >>> new_ctx = ChainContext(request_id=checkpoint["request_id"])
            >>> if "typed_state" in checkpoint:
            ...     new_ctx.load_state_from_dict(
            ...         checkpoint["typed_state"],
            ...         state_model=MyState,  # Pass model class
            ...     )
        """
        if state_model is None:
            # Try to import the model dynamically
            model_name = typed_state_dict.get("model", "")
            module_name = typed_state_dict.get("module", "")
            if not model_name or not module_name:
                raise RuntimeError(
                    "Cannot restore typed state: missing 'model' or 'module' in dict. "
                    "Pass state_model explicitly."
                )
            try:
                import importlib
                module = importlib.import_module(module_name)
                state_model = getattr(module, model_name)
            except (ImportError, AttributeError) as e:
                raise RuntimeError(
                    f"Cannot import state model {module_name}.{model_name}: {e}. "
                    "Pass state_model explicitly."
                ) from e

        # Create state store with the model
        from agentorchestrator.core.state import StateStore
        self._state_store = StateStore(state_model)

        # Load the data
        state_data = typed_state_dict.get("data", {})
        if state_data:
            self._state_store.from_dict(state_data)

    # =========================================================================
    # Citation Support
    # =========================================================================

    # Citation methods now delegated to CitationManager

    def add_citation(
        self,
        content: str,
        source_name: str,
        source_type: str = "agent",
        reasoning: str | None = None,
        document_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Add a citation to the context's citation collection.

        Now delegated to CitationManager for better separation of concerns.

        See Also:
            get_citations(): Retrieve stored citations.
            verify_citations(): Verify citations against sources.
        """
        self._citation_manager.add_citation(
            content, source_name, source_type, reasoning, document_id, **kwargs
        )

    def add_source_content(self, source_name: str, content: str) -> None:
        """
        Add raw source content for citation verification.

        Now delegated to CitationManager for better separation of concerns.
        """
        self._citation_manager.add_source_content(source_name, content)

    def get_citations(self, source_name: str | None = None) -> list[Any]:
        """
        Get citations from the context.

        Now delegated to CitationManager for better separation of concerns.
        """
        return self._citation_manager.get_citations(source_name)

    def verify_citations(self) -> dict[str, bool]:
        """
        Verify all citations against stored source content.

        Now delegated to CitationManager for better separation of concerns.
        """
        return self._citation_manager.verify_all()

    def get_citation_summary(self) -> dict[str, Any]:
        """
        Get a summary of citation coverage and verification.

        Now delegated to CitationManager for better separation of concerns.
        """
        return self._citation_manager.get_summary()

    def __repr__(self) -> str:
        """Return string representation of the context."""
        state_info = f", state={type(self._state_store.state).__name__}" if self._state_store else ""
        return f"ChainContext(request_id={self.request_id}, keys={len(self._store)}, results={len(self._result_store.get_all())}{state_info})"


# Type alias for better ergonomics
Context = ChainContext


class ContextManager:
    """
    Global context manager for managing multiple chain contexts.

    Singleton pattern for tracking concurrent chain executions.
    Each chain execution gets its own ChainContext identified by request_id.

    Attributes:
        _contexts (dict[str, ChainContext]): Active contexts by request ID.
        _global_store (dict[str, Any]): Global values available to all contexts.

    Methods:
        create_context(): Create and register a new chain context.
        get_context(): Get an existing context by request ID.
        remove_context(): Remove a context after chain completion.
        set_global(): Set a global value available to all contexts.
        get_global(): Get a global value.

    Example:
        >>> manager = ContextManager()  # Singleton
        >>>
        >>> # Create context for a chain execution
        >>> ctx = manager.create_context("req_123", {"company": "Apple"})
        >>>
        >>> # Retrieve later
        >>> ctx = manager.get_context("req_123")
        >>>
        >>> # Cleanup after execution
        >>> manager.remove_context("req_123")
        >>>
        >>> # Set/get global values
        >>> manager.set_global("config", config_dict)
        >>> config = manager.get_global("config")

    Note:
        ContextManager is a singleton - all instances share state.
        Use this for managing contexts across concurrent chain executions.
    """

    _instance: Optional["ContextManager"] = None

    def __new__(cls) -> "ContextManager":
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._contexts: dict[str, ChainContext] = {}
            cls._instance._global_store: dict[str, Any] = {}
        return cls._instance

    def create_context(
        self,
        request_id: str,
        initial_data: dict[str, Any] | None = None,
    ) -> ChainContext:
        """
        Create and register a new chain context.

        Args:
            request_id (str): Unique identifier for the chain execution.
            initial_data (dict[str, Any] | None): Initial data for context.

        Returns:
            ChainContext: The newly created context.

        Example:
            >>> ctx = manager.create_context("req_123", {"query": "Apple"})
        """
        ctx = ChainContext(request_id=request_id, initial_data=initial_data)
        self._contexts[request_id] = ctx
        return ctx

    def get_context(self, request_id: str) -> ChainContext | None:
        """
        Get an existing context by request ID.

        Args:
            request_id (str): The request ID to look up.

        Returns:
            ChainContext | None: The context or None if not found.

        Example:
            >>> ctx = manager.get_context("req_123")
            >>> if ctx:
            ...     print(f"Found context with {len(ctx.results)} results")
        """
        return self._contexts.get(request_id)

    def remove_context(self, request_id: str) -> bool:
        """
        Remove a context after chain completion.

        Args:
            request_id (str): The request ID to remove.

        Returns:
            bool: True if context was found and removed.

        Example:
            >>> if manager.remove_context("req_123"):
            ...     print("Context cleaned up")
        """
        if request_id in self._contexts:
            del self._contexts[request_id]
            return True
        return False

    def set_global(self, key: str, value: Any) -> None:
        """
        Set a global value available to all contexts.

        Args:
            key (str): The key to store.
            value (Any): The value to store.

        Example:
            >>> manager.set_global("api_config", {"timeout": 30})
        """
        self._global_store[key] = value

    def get_global(self, key: str, default: Any = None) -> Any:
        """
        Get a global value.

        Args:
            key (str): The key to look up.
            default (Any): Value to return if not found.

        Returns:
            Any: The stored value or default.

        Example:
            >>> config = manager.get_global("api_config", {})
        """
        return self._global_store.get(key, default)

    def delete_global(self, key: str) -> bool:
        """
        Delete a global value.

        Args:
            key (str): The key to delete.

        Returns:
            bool: True if key was found and deleted.

        Example:
            >>> if manager.delete_global("api_config"):
            ...     print("Global config removed")
        """
        if key in self._global_store:
            del self._global_store[key]
            return True
        return False

    def global_keys(self) -> list[str]:
        """
        Get all keys in the global store.

        Returns:
            list[str]: List of all global keys.

        Example:
            >>> for key in manager.global_keys():
            ...     print(f"Global: {key}")
        """
        return list(self._global_store.keys())