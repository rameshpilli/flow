"""
AgentOrchestrator Context Management

Provides shared context across chain steps with memory management,
token tracking, and automatic summarization support.

Thread-safety:
- Uses asyncio.Lock for concurrent access protection
- Uses contextvars for per-task step tracking (safe for parallel steps)
- Step-scoped data is isolated per step using namespaced keys
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
from typing import TYPE_CHECKING, Any, Optional, TypeVar

if TYPE_CHECKING:
    from agentorchestrator.core.serializers import ContextSerializer

logger = logging.getLogger(__name__)

__all__ = [
    "ChainContext",
    "ContextScope",
    "ContextEntry",
    "ContextManager",
    "StepResult",
    "ExecutionSummary",
]

T = TypeVar("T")

# Context variable for tracking current step per async task
# This is the async-safe equivalent of thread-local storage
_current_step_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_step", default=None
)


class ContextScope(Enum):
    """Defines the scope/lifetime of context data"""

    STEP = "step"  # Available only within current step
    CHAIN = "chain"  # Available throughout the chain execution
    GLOBAL = "global"  # Persists across multiple chain executions


@dataclass
class ContextEntry:
    """A single entry in the context store"""

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

    Attributes:
        step_name: Name of the executed step
        output: Output data from the step (None on failure)
        duration_ms: Execution time in milliseconds
        token_count: Token count for LLM calls
        metadata: Additional step metadata
        error: Exception if step failed
        error_type: Type of error (for structured logging)
        error_traceback: Full traceback string (for debugging)
        retry_count: Number of retries attempted
        skipped_reason: Reason if step was skipped
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
        return self.error is None and self.skipped_reason is None

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def skipped(self) -> bool:
        return self.skipped_reason is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization (errors as strings)."""
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
        """Percentage of steps that completed successfully."""
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100

    def add_result(self, result: StepResult) -> None:
        """Add a step result and update counters."""
        self.step_results.append(result)
        self.total_duration_ms += result.duration_ms

        if result.success:
            self.completed_steps += 1
        elif result.skipped:
            self.skipped_steps += 1
        else:
            self.failed_steps += 1

    def finalize(self) -> None:
        """Finalize the summary after execution."""
        self.success = self.failed_steps == 0 and self.skipped_steps == 0
        self.partial_success = (
            self.completed_steps > 0 and
            (self.failed_steps > 0 or self.skipped_steps > 0)
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
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
        """Get all failed step results."""
        return [r for r in self.step_results if r.failed]

    def get_skipped_steps(self) -> list[StepResult]:
        """Get all skipped step results."""
        return [r for r in self.step_results if r.skipped]

    def get_successful_steps(self) -> list[StepResult]:
        """Get all successful step results."""
        return [r for r in self.step_results if r.success]


class ChainContext:
    """
    Manages shared state and data flow between chain steps.

    Features:
    - Scoped storage (step, chain, global)
    - Token tracking for LLM context management
    - Automatic cleanup of step-scoped data
    - Thread-safe operations
    - Deep copy isolation between steps

    Usage:
        ctx = ChainContext(request_id="req_123")

        # Store data
        ctx.set("user_query", "Who is the CEO?", scope=ContextScope.CHAIN)

        # Retrieve data
        query = ctx.get("user_query")

        # Store step results
        ctx.add_result(StepResult(step_name="extractor", output={...}, duration_ms=150))
    """

    def __init__(
        self,
        request_id: str,
        initial_data: dict[str, Any] | None = None,
        max_tokens: int = 100000,
    ):
        self.request_id = request_id
        self.max_tokens = max_tokens
        self._store: dict[str, ContextEntry] = {}
        self._results: list[StepResult] = []
        self._step_stores: dict[str, dict[str, ContextEntry]] = {}  # Per-step isolated storage
        self._lock = asyncio.Lock()
        self._sync_lock = __import__("threading").RLock()  # For sync access
        self.created_at = datetime.utcnow()
        self.metadata: dict[str, Any] = {}

        # Initialize with any provided data
        if initial_data:
            for key, value in initial_data.items():
                self.set(key, value, scope=ContextScope.CHAIN)

    @property
    def current_step(self) -> str | None:
        """Get current step name (async-task-safe via contextvars)"""
        return _current_step_var.get()

    @property
    def total_tokens(self) -> int:
        """Total tokens currently stored in context"""
        with self._sync_lock:
            total = sum(entry.token_count for entry in self._store.values())
            # Include step-scoped tokens
            for step_store in self._step_stores.values():
                total += sum(entry.token_count for entry in step_store.values())
            return total

    @property
    def results(self) -> list[StepResult]:
        """All step results in execution order"""
        with self._sync_lock:
            return self._results.copy()

    @property
    def last_result(self) -> StepResult | None:
        """Most recent step result"""
        with self._sync_lock:
            return self._results[-1] if self._results else None

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

        Args:
            key: Unique identifier for the value
            value: The data to store
            scope: Lifetime scope of the data
            token_count: Estimated token count (for LLM context management)
            metadata: Additional metadata about this entry

        Note:
            STEP-scoped data is isolated per step - parallel steps cannot
            see or interfere with each other's step-scoped data.
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

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a value from the context.

        Args:
            key: The key to look up
            default: Value to return if key not found

        Returns:
            The stored value or default

        Note:
            First checks step-scoped storage (current step only),
            then falls back to chain/global storage.
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
        """Get the full context entry including metadata"""
        with self._sync_lock:
            # First check step-scoped storage
            current_step = self.current_step
            if current_step and current_step in self._step_stores:
                step_store = self._step_stores[current_step]
                if key in step_store:
                    return step_store[key]

            return self._store.get(key)

    def has(self, key: str) -> bool:
        """Check if a key exists in context"""
        with self._sync_lock:
            # Check step-scoped storage first
            current_step = self.current_step
            if current_step and current_step in self._step_stores:
                if key in self._step_stores[current_step]:
                    return True
            return key in self._store

    def delete(self, key: str) -> bool:
        """Remove a key from context"""
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
        """Get all keys, optionally filtered by scope"""
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

    def add_result(self, result: StepResult) -> None:
        """Add a step execution result (thread-safe)"""
        with self._sync_lock:
            self._results.append(result)
        logger.debug(f"Result added: {result.step_name} (success={result.success})")

    def get_result(self, step_name: str) -> StepResult | None:
        """Get result for a specific step (thread-safe)"""
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

        Returns:
            Token that must be passed to exit_step() to properly reset
            the contextvar (enables proper nesting if needed).
        """
        token = _current_step_var.set(step_name)
        logger.debug(f"Entering step: {step_name}")
        return token

    def exit_step(self, token: contextvars.Token | None = None) -> None:
        """
        Called when exiting a step - cleans up step-scoped data for THIS step only.

        Args:
            token: The token returned by enter_step(). If provided, uses it
                   to properly reset the contextvar. If not provided, just
                   resets to None (for backward compatibility).
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

        Usage:
            async with ctx.step_scope("my_step"):
                ctx.set("temp", value, scope=ContextScope.STEP)
                # ... step logic ...
            # Automatic cleanup on exit, even on exception

        Args:
            step_name: Name of the step being executed

        Yields:
            The context (self) for chaining
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

        Ensures step-scoped data is always cleaned up, even if the step
        raises an exception. This prevents data leaks between steps.

        Usage:
            with ctx.step_scope_sync("my_step"):
                ctx.set("temp", value, scope=ContextScope.STEP)
                # ... step logic ...
            # Automatic cleanup on exit, even on exception

        Args:
            step_name: Name of the step being executed

        Yields:
            The context (self) for chaining
        """
        token = self.enter_step(step_name)
        try:
            yield self
        finally:
            self.exit_step(token)

    def to_dict(
        self,
        serializer: "ContextSerializer | None" = None,
        include_data: bool = True,
    ) -> dict[str, Any]:
        """
        Export context as dictionary (for serialization).

        Args:
            serializer: Optional serializer for redacting/truncating large fields.
                       If None, uses default serialization (may be large!).
            include_data: Whether to include context data (False for lightweight summary)

        Returns:
            JSON-serializable dictionary

        Usage:
            # Default (may include huge payloads)
            ctx.to_dict()

            # With serializer for safe logging/API responses
            ctx.to_dict(serializer=TruncatingSerializer(max_size=1000))

            # Lightweight summary only
            ctx.to_dict(include_data=False)
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

            return result

    def clone(self) -> "ChainContext":
        """Create a deep copy of the context (thread-safe)"""
        with self._sync_lock:
            new_ctx = ChainContext(
                request_id=self.request_id,
                max_tokens=self.max_tokens,
            )
            new_ctx._store = copy.deepcopy(self._store)
            new_ctx._step_stores = copy.deepcopy(self._step_stores)
            new_ctx._results = copy.deepcopy(self._results)
            new_ctx.metadata = copy.deepcopy(self.metadata)
            return new_ctx

    def __repr__(self) -> str:
        return f"ChainContext(request_id={self.request_id}, keys={len(self._store)}, results={len(self._results)})"


class ContextManager:
    """
    Global context manager for managing multiple chain contexts.
    Useful for concurrent chain executions.
    """

    _instance: Optional["ContextManager"] = None

    def __new__(cls) -> "ContextManager":
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
        """Create and register a new chain context"""
        ctx = ChainContext(request_id=request_id, initial_data=initial_data)
        self._contexts[request_id] = ctx
        return ctx

    def get_context(self, request_id: str) -> ChainContext | None:
        """Get an existing context by request ID"""
        return self._contexts.get(request_id)

    def remove_context(self, request_id: str) -> bool:
        """Remove a context after chain completion"""
        if request_id in self._contexts:
            del self._contexts[request_id]
            return True
        return False

    def set_global(self, key: str, value: Any) -> None:
        """Set a global value available to all contexts"""
        self._global_store[key] = value

    def get_global(self, key: str, default: Any = None) -> Any:
        """Get a global value"""
        return self._global_store.get(key, default)
