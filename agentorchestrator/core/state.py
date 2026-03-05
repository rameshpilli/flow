"""
Type-Safe State Management with Pydantic Models
================================================

Provides Pydantic-based state management for ChainContext, enabling
type-safe state access with IDE autocomplete and validation.

Classes:
    StateStore: Generic state store with Pydantic model support.
    
Usage:
    from pydantic import BaseModel, Field
    from agentorchestrator import AgentOrchestrator, Context
    from agentorchestrator.core.state import StateStore
    
    class PipelineState(BaseModel):
        counter: int = Field(default=0)
        items: list[str] = Field(default_factory=list)
        processed: bool = False
    
    ao = AgentOrchestrator()
    
    @ao.step(name="process", state_model=PipelineState)
    async def process(ctx: Context[PipelineState]):
        # Type-safe access with IDE autocomplete
        async with ctx.edit_state() as state:
            state.counter += 1
            state.items.append("new_item")
        
        # Read-only access
        count = ctx.state.counter  # Typed!
        return {"count": count}

Example:
    >>> from pydantic import BaseModel
    >>> from agentorchestrator.core.state import StateStore
    >>>
    >>> class MyState(BaseModel):
    ...     count: int = 0
    ...     name: str = "default"
    >>>
    >>> store = StateStore(MyState)
    >>> async with store.edit() as state:
    ...     state.count += 1
    ...     state.name = "updated"
    >>>
    >>> print(store.state.count)  # 1
    >>> print(store.state.name)  # "updated"

Thread-safety:
    StateStore uses asyncio.Lock for atomic updates via edit() context manager.
    Direct state access is not thread-safe - always use edit() for modifications.

See Also:
    ChainContext: Uses StateStore for typed state management.
    Context: Type alias for ChainContext with generic state type.
"""

import asyncio
import copy
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Generic, TypeVar

try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    BaseModel = None  # type: ignore
    ValidationError = None  # type: ignore

logger = logging.getLogger(__name__)

__all__ = [
    "StateStore",
    "StateModel",
]

# Type variable for state models
StateModel = TypeVar("StateModel", bound="BaseModel")


class StateStore(Generic[StateModel]):
    """
    Generic state store with Pydantic model support.
    
    Provides type-safe state management with atomic updates via
    context manager. State is validated on every update.
    
    Attributes:
        state (StateModel): Current state (read-only access).
        model_class (type[StateModel]): Pydantic model class.
    
    Methods:
        edit(): Async context manager for atomic state updates.
        reset(): Reset state to initial values.
        to_dict(): Export state as dictionary.
        from_dict(): Load state from dictionary.
    
    Example:
        ```python
        from pydantic import BaseModel
        
        class CounterState(BaseModel):
            count: int = 0
            items: list[str] = []
        
        store = StateStore(CounterState)
        
        # Atomic update
        async with store.edit() as state:
            state.count += 1
            state.items.append("item1")
        
        # Read-only access
        print(store.state.count)  # 1
        ```
    
    Thread-safety:
        Uses asyncio.Lock for atomic updates. Always use edit()
        for modifications to ensure thread-safety.
    """
    
    def __init__(self, model_class: type[StateModel], initial_state: StateModel | None = None):
        """
        Initialize state store with a Pydantic model.
        
        Args:
            model_class: Pydantic BaseModel class for state.
            initial_state: Optional initial state instance.
                If None, creates instance with default values.
        
        Raises:
            TypeError: If model_class is not a Pydantic BaseModel.
            ValidationError: If initial_state fails validation.
        
        Example:
            >>> class MyState(BaseModel):
            ...     count: int = 0
            >>> store = StateStore(MyState)
            >>> store2 = StateStore(MyState, MyState(count=10))
        """
        if BaseModel is None:
            raise ImportError(
                "pydantic is required for type-safe state management. "
                "Install with: pip install pydantic"
            )
        
        if not issubclass(model_class, BaseModel):
            raise TypeError(
                f"model_class must be a Pydantic BaseModel, got {type(model_class)}"
            )
        
        self.model_class = model_class
        self._state = initial_state or model_class()
        self._lock = asyncio.Lock()
        self._initial_state = self._copy_state(self._state)

    def _copy_state(self, state: StateModel | None) -> StateModel:
        """
        Deep copy a Pydantic model across v1/v2.

        Pydantic v2: model_copy(deep=True)
        Pydantic v1: copy(deep=True)
        Fallback: copy.deepcopy

        Args:
            state: The state model to copy

        Raises:
            ValueError: If state is None
        """
        if state is None:
            raise ValueError(
                "Cannot copy None state. State must be initialized with a valid "
                "Pydantic model instance."
            )
        if hasattr(state, "model_copy"):
            return state.model_copy(deep=True)
        if hasattr(state, "copy"):
            return state.copy(deep=True)
        return copy.deepcopy(state)
    
    @property
    def state(self) -> StateModel:
        """
        Get current state (read-only).
        
        For modifications, use edit() context manager to ensure
        atomicity and validation.
        
        Returns:
            StateModel: Current state instance.
        
        Example:
            >>> count = store.state.count
            >>> items = store.state.items
        
        Warning:
            Modifying the returned state directly is NOT thread-safe
            and bypasses validation. Always use edit() for updates.
        """
        return self._state
    
    @asynccontextmanager
    async def edit(self) -> AsyncIterator[StateModel]:
        """
        Async context manager for atomic state updates.
        
        Creates a copy of the state, yields it for modification,
        validates the changes, and commits atomically. If an
        exception occurs, changes are rolled back.
        
        Yields:
            StateModel: Mutable state copy for modification.
        
        Raises:
            ValidationError: If modified state fails Pydantic validation.
        
        Example:
            >>> async with store.edit() as state:
            ...     state.count += 1
            ...     state.items.append("new")
            ...     # Validated and committed on exit
        
        Thread-safety:
            Uses asyncio.Lock to ensure only one edit at a time.
            Multiple concurrent edits will be serialized.
        """
        async with self._lock:
            # Create a deep copy for modification
            state_copy = self._copy_state(self._state)
            
            try:
                yield state_copy
                
                # Validate the modified state
                # Pydantic v2: model_validate
                # Pydantic v1: parse_obj
                if hasattr(self.model_class, "model_validate"):
                    # Pydantic v2
                    validated = self.model_class.model_validate(state_copy.model_dump())
                else:
                    # Pydantic v1
                    validated = self.model_class.parse_obj(state_copy.dict())
                
                # Commit the changes
                self._state = validated
                logger.debug(f"State updated successfully: {type(self._state).__name__}")
                
            except Exception as e:
                logger.error(f"State update failed, rolling back: {e}")
                # State remains unchanged on error
                raise
    
    def reset(self) -> None:
        """
        Reset state to initial values.
        
        Restores state to the values it had when the store was created.
        
        Example:
            >>> async with store.edit() as state:
            ...     state.count = 100
            >>> store.reset()
            >>> print(store.state.count)  # 0 (back to initial)
        """
        self._state = self._copy_state(self._initial_state)
        logger.debug("State reset to initial values")
    
    def to_dict(self) -> dict[str, Any]:
        """
        Export state as dictionary.
        
        Returns:
            dict[str, Any]: State as JSON-serializable dictionary.
        
        Example:
            >>> state_dict = store.to_dict()
            >>> print(state_dict)  # {"count": 1, "items": ["item1"]}
        """
        # Pydantic v2: model_dump
        # Pydantic v1: dict
        if hasattr(self._state, "model_dump"):
            return self._state.model_dump()
        else:
            return self._state.dict()
    
    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Load state from dictionary.
        
        Validates the data against the model schema before loading.
        
        Args:
            data: Dictionary with state data.
        
        Raises:
            ValidationError: If data doesn't match model schema.
        
        Example:
            >>> store.from_dict({"count": 5, "items": ["a", "b"]})
            >>> print(store.state.count)  # 5
        """
        # Validate and create new state
        if hasattr(self.model_class, "model_validate"):
            # Pydantic v2
            self._state = self.model_class.model_validate(data)
        else:
            # Pydantic v1
            self._state = self.model_class.parse_obj(data)
        
        logger.debug(f"State loaded from dict: {type(self._state).__name__}")
    
    def clone(self) -> "StateStore[StateModel]":
        """
        Create a deep copy of this state store.
        
        Returns:
            StateStore[StateModel]: New store with copied state.
        
        Example:
            >>> store2 = store.clone()
            >>> async with store2.edit() as state:
            ...     state.count += 1
            >>> # Original store is unchanged
        """
        return StateStore(
            self.model_class,
            initial_state=self._copy_state(self._state)
        )
    
    def __repr__(self) -> str:
        """String representation of the state store."""
        model_name = self.model_class.__name__
        state_preview = str(self.to_dict())[:50]
        return f"StateStore[{model_name}]({state_preview}...)"