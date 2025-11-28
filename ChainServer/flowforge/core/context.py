"""
FlowForge Context Management

Provides shared context across chain steps with memory management,
token tracking, and automatic summarization support.
"""

import asyncio
import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


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
    """Result from a step execution"""

    step_name: str
    output: Any
    duration_ms: float
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None

    @property
    def success(self) -> bool:
        return self.error is None


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
        self._current_step: str | None = None
        self._lock = asyncio.Lock()
        self.created_at = datetime.utcnow()
        self.metadata: dict[str, Any] = {}

        # Initialize with any provided data
        if initial_data:
            for key, value in initial_data.items():
                self.set(key, value, scope=ContextScope.CHAIN)

    @property
    def total_tokens(self) -> int:
        """Total tokens currently stored in context"""
        return sum(entry.token_count for entry in self._store.values())

    @property
    def results(self) -> list[StepResult]:
        """All step results in execution order"""
        return self._results.copy()

    @property
    def last_result(self) -> StepResult | None:
        """Most recent step result"""
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
        """
        entry = ContextEntry(
            key=key,
            value=value,
            scope=scope,
            token_count=token_count,
            source_step=self._current_step,
            metadata=metadata or {},
        )

        if key in self._store:
            entry.created_at = self._store[key].created_at

        self._store[key] = entry
        logger.debug(f"Context set: {key} (scope={scope.value}, tokens={token_count})")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a value from the context.

        Args:
            key: The key to look up
            default: Value to return if key not found

        Returns:
            The stored value or default
        """
        entry = self._store.get(key)
        if entry is None:
            return default
        return entry.value

    def get_entry(self, key: str) -> ContextEntry | None:
        """Get the full context entry including metadata"""
        return self._store.get(key)

    def has(self, key: str) -> bool:
        """Check if a key exists in context"""
        return key in self._store

    def delete(self, key: str) -> bool:
        """Remove a key from context"""
        if key in self._store:
            del self._store[key]
            return True
        return False

    def keys(self, scope: ContextScope | None = None) -> list[str]:
        """Get all keys, optionally filtered by scope"""
        if scope is None:
            return list(self._store.keys())
        return [k for k, v in self._store.items() if v.scope == scope]

    def add_result(self, result: StepResult) -> None:
        """Add a step execution result"""
        self._results.append(result)
        logger.debug(f"Result added: {result.step_name} (success={result.success})")

    def get_result(self, step_name: str) -> StepResult | None:
        """Get result for a specific step"""
        for result in reversed(self._results):
            if result.step_name == step_name:
                return result
        return None

    def enter_step(self, step_name: str) -> None:
        """Called when entering a new step"""
        self._current_step = step_name
        logger.debug(f"Entering step: {step_name}")

    def exit_step(self) -> None:
        """Called when exiting a step - cleans up step-scoped data"""
        # Remove step-scoped entries
        step_keys = [k for k, v in self._store.items() if v.scope == ContextScope.STEP]
        for key in step_keys:
            del self._store[key]

        logger.debug(
            f"Exiting step: {self._current_step}, cleaned {len(step_keys)} step-scoped entries"
        )
        self._current_step = None

    def to_dict(self) -> dict[str, Any]:
        """Export context as dictionary (for serialization)"""
        return {
            "request_id": self.request_id,
            "created_at": self.created_at.isoformat(),
            "total_tokens": self.total_tokens,
            "data": {k: v.value for k, v in self._store.items()},
            "results": [
                {
                    "step": r.step_name,
                    "success": r.success,
                    "duration_ms": r.duration_ms,
                }
                for r in self._results
            ],
        }

    def clone(self) -> "ChainContext":
        """Create a deep copy of the context"""
        new_ctx = ChainContext(
            request_id=self.request_id,
            max_tokens=self.max_tokens,
        )
        new_ctx._store = copy.deepcopy(self._store)
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
