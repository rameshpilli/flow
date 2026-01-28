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


class ChainContext(Generic[StateModel]):
    """
    Manages shared state and data flow between chain steps.

    ChainContext is the central data structure that flows through all steps
    in a chain execution. It provides scoped storage, token tracking for
    LLM context management, automatic cleanup, and citation support.

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
        - Uses asyncio.Lock for async operations (async_set, edit_state)
        - Uses threading.RLock for sync operations (set, get)
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
        self._results: list[StepResult] = []
        self._step_stores: dict[str, dict[str, ContextEntry]] = {}  # Per-step isolated storage
        self._lock = asyncio.Lock()
        self._sync_lock = __import__("threading").RLock()  # For sync access
        self.created_at = datetime.utcnow()
        self.metadata: dict[str, Any] = {}
        
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

        Includes tokens from all scopes (step, chain, global).
        Use for LLM context budget management.

        Returns:
            int: Total estimated token count.

        Example:
            >>> if ctx.total_tokens > ctx.max_tokens * 0.8:
            ...     logger.warning("Context approaching token limit")
        """
        with self._sync_lock:
            total = sum(entry.token_count for entry in self._store.values())
            # Include step-scoped tokens
            for step_store in self._step_stores.values():
                total += sum(entry.token_count for entry in step_store.values())
            return total

    @property
    def results(self) -> list[StepResult]:
        """
        All step results in execution order.

        Returns:
            list[StepResult]: Copy of the results list (thread-safe).

        Example:
            >>> for result in ctx.results:
            ...     print(f"{result.step_name}: {result.duration_ms}ms")
        """
        with self._sync_lock:
            return self._results.copy()

    @property
    def last_result(self) -> StepResult | None:
        """
        Most recent step result.

        Returns:
            StepResult | None: The last added result, or None if empty.

        Example:
            >>> if ctx.last_result and ctx.last_result.success:
            ...     process(ctx.last_result.output)
        """
        with self._sync_lock:
            return self._results[-1] if self._results else None
    
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
            else:
                # CHAIN and GLOBAL scoped data goes into shared store
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
            The standard set() method uses a sync lock (threading.RLock) which
            is safe for most use cases. However, for CHAIN-scoped data modified
            by truly parallel async steps, this async_set() method provides
            stronger guarantees using asyncio.Lock.

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

        async with self._lock:
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
            else:
                # CHAIN and GLOBAL scoped data goes into shared store
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
        then falls back to chain/global storage.

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

            # Then check shared store (CHAIN and GLOBAL scoped)
            entry = self._store.get(key)
            if entry is None:
                return default
            return entry.value

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

            return self._store.get(key)

    def has(self, key: str) -> bool:
        """
        Check if a key exists in context.

        Checks both step-scoped and shared storage.

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
            return key in self._store

    def delete(self, key: str) -> bool:
        """
        Remove a key from context.

        Checks step-scoped storage first, then shared storage.

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

            if key in self._store:
                del self._store[key]
                return True
            return False

    def keys(self, scope: ContextScope | None = None) -> list[str]:
        """
        Get all keys, optionally filtered by scope.

        Args:
            scope (ContextScope | None): Filter by scope. If None, returns
                all keys from shared store plus current step's storage.

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
        """
        with self._sync_lock:
            if scope == ContextScope.STEP:
                # Only return keys from current step's storage
                current_step = self.current_step
                if current_step and current_step in self._step_stores:
                    return list(self._step_stores[current_step].keys())
                return []
            elif scope is None:
                # Return all keys (shared + current step's step-scoped)
                all_keys = list(self._store.keys())
                current_step = self.current_step
                if current_step and current_step in self._step_stores:
                    all_keys.extend(self._step_stores[current_step].keys())
                return all_keys
            else:
                # CHAIN or GLOBAL - only from shared store
                return [k for k, v in self._store.items() if v.scope == scope]

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
        Add a step execution result (thread-safe).

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
        with self._sync_lock:
            self._results.append(result)
        logger.debug(f"Result added: {result.step_name} (success={result.success})")

    def get_result(self, step_name: str) -> StepResult | None:
        """
        Get result for a specific step (thread-safe).

        Returns the most recent result if step was executed multiple times.

        Args:
            step_name (str): Name of the step.

        Returns:
            StepResult | None: The result or None if step not found.

        Example:
            >>> result = ctx.get_result("fetch_data")
            >>> if result and result.success:
            ...     print(f"Fetch completed in {result.duration_ms}ms")
        """
        with self._sync_lock:
            for result in reversed(self._results):
                if result.step_name == step_name:
                    return result
            return None

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

        Returns:
            dict[str, Any]: JSON-serializable dictionary.

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
                    for r in self._results
                ],
            }

            if include_data:
                if serializer:
                    result["data"] = serializer.serialize_context_data(
                        {k: v.value for k, v in self._store.items()}
                    )
                else:
                    result["data"] = {k: v.value for k, v in self._store.items()}

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
            new_ctx._results = copy.deepcopy(self._results)
            new_ctx.metadata = copy.deepcopy(self.metadata)
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

        Citations track data provenance and enable source verification.
        Use this to document where data came from and why it's relevant.

        Args:
            content (str): Verbatim quote from source.
            source_name (str): Name of the source (agent, document, etc.).
            source_type (str): Type of source. Default: "agent".
                Options: "agent", "document", "api", "llm".
            reasoning (str | None): Why this source supports the claim.
            document_id (str | None): Document identifier if applicable.
            **kwargs: Additional citation fields (page_number, etc.).

        Example:
            >>> ctx.add_citation(
            ...     content="Total net sales were $394,328 million",
            ...     source_name="sec_filing_agent",
            ...     source_type="document",
            ...     reasoning="Direct revenue figure from 10-K filing",
            ...     document_id="AAPL-10K-2024",
            ...     page_number=45,
            ... )

        See Also:
            get_citations(): Retrieve stored citations.
            verify_citations(): Verify citations against sources.
        """
        from agentorchestrator.models.citation import Citation, CitationCollection

        # Get or create citation collection
        collection = self.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            collection = CitationCollection()
            self.set("_citation_collection", collection, scope=ContextScope.CHAIN)

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
        """
        Add raw source content for citation verification.

        Store the raw content from sources so citations can be
        verified against the original text.

        Args:
            source_name (str): Name of the source (should match
                citation.source_name for verification).
            content (str): Raw content from the source.

        Example:
            >>> ctx.add_source_content(
            ...     "sec_filing",
            ...     raw_10k_text,
            ... )
            >>> # Later citations can be verified against this
        """
        from agentorchestrator.models.citation import CitationCollection

        collection = self.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            collection = CitationCollection()
            self.set("_citation_collection", collection, scope=ContextScope.CHAIN)

        collection.add_source_chunk(source_name, content)

    def get_citations(self, source_name: str | None = None) -> list[Any]:
        """
        Get citations from the context.

        Args:
            source_name (str | None): Filter by source name.
                If None, returns all citations.

        Returns:
            list[Citation]: List of Citation objects.

        Example:
            >>> # Get all citations
            >>> all_citations = ctx.get_citations()
            >>>
            >>> # Get citations from specific source
            >>> sec_citations = ctx.get_citations(source_name="sec_filing")
        """
        from agentorchestrator.models.citation import CitationCollection

        collection = self.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            return []

        if source_name:
            return collection.get_by_source(source_name)
        return collection.citations

    def verify_citations(self) -> dict[str, bool]:
        """
        Verify all citations against stored source content.

        Checks if each citation's content exists in the corresponding
        source's raw content.

        Returns:
            dict[str, bool]: Mapping of citation index to verification result.

        Example:
            >>> results = ctx.verify_citations()
            >>> for idx, verified in results.items():
            ...     status = "verified" if verified else "NOT FOUND"
            ...     print(f"Citation {idx}: {status}")
        """
        from agentorchestrator.models.citation import CitationCollection

        collection = self.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            return {}

        return collection.verify_all()

    def get_citation_summary(self) -> dict[str, Any]:
        """
        Get a summary of citation coverage and verification.

        Returns:
            dict[str, Any]: Statistics including total citations,
                verified count, and per-source breakdown.

        Example:
            >>> summary = ctx.get_citation_summary()
            >>> print(f"Total: {summary['total']}, Verified: {summary['verified']}")
        """
        from agentorchestrator.models.citation import CitationCollection

        collection = self.get("_citation_collection")
        if not isinstance(collection, CitationCollection):
            return {"total": 0, "verified": 0, "by_source": {}}

        return collection.get_verification_summary()

    def __repr__(self) -> str:
        """Return string representation of the context."""
        state_info = f", state={type(self._state_store.state).__name__}" if self._state_store else ""
        return f"ChainContext(request_id={self.request_id}, keys={len(self._store)}, results={len(self._results)}{state_info})"


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
