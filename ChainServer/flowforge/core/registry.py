"""
FlowForge Registry System

Central registry for agents, steps, and chains.
Enables decorator-based registration and discovery.

Thread-safety: All registry operations are protected by a threading.RLock
to ensure safe concurrent access from multiple threads.
"""

import inspect
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

__all__ = [
    # Registries
    "AgentRegistry",
    "StepRegistry",
    "ChainRegistry",
    # Specs
    "AgentSpec",
    "StepSpec",
    "ChainSpec",
    "RetryConfig",
    "ComponentMetadata",
    "ComponentStatus",
    # Global accessors
    "get_agent_registry",
    "get_step_registry",
    "get_chain_registry",
    "create_isolated_registries",
    "reset_global_registries",
]

T = TypeVar("T")


class ComponentStatus(Enum):
    """Status of a registered component"""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


@dataclass
class ComponentMetadata:
    """Metadata for registered components"""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    group: str = ""  # For grouping components (like Dagster's group_name)
    tags: list[str] = field(default_factory=list)
    status: ComponentStatus = ComponentStatus.ACTIVE
    registered_at: datetime = field(default_factory=datetime.utcnow)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSpec:
    """Specification for a registered agent"""

    metadata: ComponentMetadata
    agent_class: type
    instance: Any | None = None
    capabilities: list[str] = field(default_factory=list)
    input_schema: dict | None = None
    output_schema: dict | None = None

    def get_instance(self, **kwargs) -> Any:
        """Get or create agent instance"""
        if self.instance is None:
            self.instance = self.agent_class(**kwargs)
        return self.instance


@dataclass
class RetryConfig:
    """Configuration for step retry behavior"""

    count: int = 0  # Number of retry attempts
    delay_ms: int = 1000  # Delay between retries in milliseconds
    backoff_multiplier: float = 1.0  # Exponential backoff multiplier
    max_delay_ms: int = 30000  # Maximum delay cap


@dataclass
class StepSpec:
    """Specification for a registered step"""

    metadata: ComponentMetadata
    handler: Callable
    dependencies: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)  # Resource dependencies
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    max_concurrency: int | None = None  # Max parallel instances (None = unlimited)
    timeout_ms: int = 30000
    is_async: bool = True
    # Input/Output contracts for validation
    input_model: type | None = None  # Pydantic model for input validation
    output_model: type | None = None  # Pydantic model for output validation
    input_key: str | None = None  # Key in context to validate as input (default: "request")
    validate_output: bool = True  # Whether to validate output against output_model


@dataclass
class ChainSpec:
    """Specification for a registered chain"""

    metadata: ComponentMetadata
    steps: list[str]
    chain_class: type | None = None
    parallel_groups: list[list[str]] = field(default_factory=list)
    error_handling: str = "fail_fast"  # fail_fast, continue, retry
    # Chain composition support
    is_subchain: bool = False  # Whether this chain is used as a subchain
    parent_chain: str | None = None  # Parent chain name if this is a subchain


class BaseRegistry:
    """
    Base registry with common functionality.

    Thread-safe: All operations are protected by a reentrant lock.
    """

    def __init__(self):
        self._registry: dict[str, Any] = {}
        self._aliases: dict[str, str] = {}
        self._lock = threading.RLock()
        # Cache for normalized names to avoid repeated computation
        self._name_cache: dict[str, str] = {}

    def _normalize_name(self, name: str) -> str:
        """Normalize component names (cached for performance)"""
        if name in self._name_cache:
            return self._name_cache[name]
        normalized = name.lower().replace("-", "_").replace(" ", "_")
        self._name_cache[name] = normalized
        return normalized

    def register(
        self,
        name: str,
        spec: Any,
        aliases: list[str] | None = None,
        strict: bool = False,
    ) -> None:
        """
        Register a component (thread-safe).

        Args:
            name: Component name
            spec: Component specification
            aliases: Alternative names for the component
            strict: If True, raise error if component already exists
        """
        normalized = self._normalize_name(name)
        with self._lock:
            if strict and normalized in self._registry:
                raise ValueError(
                    f"Component '{name}' already registered. "
                    "Use strict=False to overwrite."
                )
            self._registry[normalized] = spec

            if aliases:
                for alias in aliases:
                    self._aliases[self._normalize_name(alias)] = normalized

        logger.info(f"Registered: {normalized} (type={type(spec).__name__})")

    def get(self, name: str) -> Any | None:
        """Get a registered component (thread-safe)"""
        normalized = self._normalize_name(name)
        with self._lock:
            # Check direct registration
            if normalized in self._registry:
                return self._registry[normalized]

            # Check aliases
            if normalized in self._aliases:
                return self._registry[self._aliases[normalized]]

        return None

    def has(self, name: str) -> bool:
        """Check if a component is registered (thread-safe)"""
        normalized = self._normalize_name(name)
        with self._lock:
            return normalized in self._registry or normalized in self._aliases

    def list(self, status: ComponentStatus | None = None) -> list[str]:
        """List all registered components (thread-safe)"""
        with self._lock:
            if status is None:
                return list(self._registry.keys())

            return [
                name
                for name, spec in self._registry.items()
                if hasattr(spec, "metadata") and spec.metadata.status == status
            ]

    def remove(self, name: str) -> bool:
        """Remove a component from registry (thread-safe)"""
        normalized = self._normalize_name(name)
        with self._lock:
            if normalized in self._registry:
                del self._registry[normalized]
                # Remove any aliases pointing to this component
                self._aliases = {k: v for k, v in self._aliases.items() if v != normalized}
                return True
        return False

    def clear(self) -> None:
        """Clear all registrations (thread-safe)"""
        with self._lock:
            self._registry.clear()
            self._aliases.clear()
            self._name_cache.clear()


class AgentRegistry(BaseRegistry):
    """Registry for data agents"""

    def register_agent(
        self,
        name: str,
        agent_class: type,
        version: str = "1.0.0",
        description: str = "",
        capabilities: list[str] | None = None,
        config: dict[str, Any] | None = None,
        aliases: list[str] | None = None,
        group: str | None = None,
        strict: bool = False,
        **kwargs,  # Accept extra kwargs for forward compatibility
    ) -> None:
        """Register a new agent"""
        metadata = ComponentMetadata(
            name=name,
            version=version,
            description=description,
            group=group or "",
            config=config or {},
        )
        spec = AgentSpec(
            metadata=metadata,
            agent_class=agent_class,
            capabilities=capabilities or [],
        )
        self.register(name, spec, aliases, strict=strict)

    def get_agent(self, name: str, **init_kwargs) -> Any | None:
        """Get an agent instance"""
        spec: AgentSpec | None = self.get(name)
        if spec:
            return spec.get_instance(**init_kwargs)
        return None

    def get_spec(self, name: str) -> AgentSpec | None:
        """Get agent specification"""
        return self.get(name)


class StepRegistry(BaseRegistry):
    """Registry for chain steps"""

    def register_step(
        self,
        name: str,
        handler: Callable,
        dependencies: list[str] | None = None,
        produces: list[str] | None = None,
        resources: list[str] | None = None,
        version: str = "1.0.0",
        description: str = "",
        timeout_ms: int = 30000,
        retry_count: int = 0,
        retry_delay_ms: int = 1000,
        retry_backoff: float = 1.0,
        retry_max_delay_ms: int = 30000,
        max_concurrency: int | None = None,
        aliases: list[str] | None = None,
        group: str | None = None,
        retry_config: RetryConfig | dict[str, Any] | None = None,
        strict: bool = False,
        input_model: type | None = None,
        output_model: type | None = None,
        input_key: str | None = None,
        validate_output: bool = True,
        **kwargs,  # Accept extra kwargs for forward compatibility
    ) -> None:
        """
        Register a new step.

        Args:
            name: Step name (used for dependencies and chain definitions)
            handler: Async or sync function to execute
            dependencies: List of step names this step depends on
            produces: List of context keys this step produces
            resources: List of resource names to inject
            version: Step version
            description: Step description
            timeout_ms: Execution timeout in milliseconds
            retry_count: Number of retry attempts (shorthand)
            retry_delay_ms: Delay between retries in ms (shorthand)
            retry_backoff: Backoff multiplier (shorthand)
            retry_max_delay_ms: Maximum retry delay cap
            max_concurrency: Max parallel instances of this step
            aliases: Alternative names for this step
            group: Step group for organization
            retry_config: RetryConfig instance or dict (overrides shorthand params)
        """
        metadata = ComponentMetadata(
            name=name,
            version=version,
            description=description,
            group=group or "",
        )

        # Build RetryConfig - unified handling
        if isinstance(retry_config, RetryConfig):
            # Already a RetryConfig instance
            rc = retry_config
        elif isinstance(retry_config, dict):
            # Legacy dict format - convert to RetryConfig with deprecation warning
            logger.warning(
                f"Step '{name}': retry_config as dict is deprecated. "
                "Use RetryConfig dataclass or individual retry_* parameters."
            )
            rc = RetryConfig(
                count=retry_config.get("count", retry_count),
                delay_ms=retry_config.get("delay_ms", retry_delay_ms),
                backoff_multiplier=retry_config.get("backoff_multiplier", retry_backoff),
                max_delay_ms=retry_config.get("max_delay_ms", retry_max_delay_ms),
            )
            # Extract max_concurrency from legacy config if present
            if max_concurrency is None:
                max_concurrency = retry_config.get("max_concurrency")
        else:
            # Use shorthand parameters
            rc = RetryConfig(
                count=retry_count,
                delay_ms=retry_delay_ms,
                backoff_multiplier=retry_backoff,
                max_delay_ms=retry_max_delay_ms,
            )

        spec = StepSpec(
            metadata=metadata,
            handler=handler,
            dependencies=dependencies or [],
            produces=produces or [],
            resources=resources or [],
            retry_config=rc,
            max_concurrency=max_concurrency,
            timeout_ms=timeout_ms,
            is_async=inspect.iscoroutinefunction(handler),
            input_model=input_model,
            output_model=output_model,
            input_key=input_key,
            validate_output=validate_output,
        )
        self.register(name, spec, aliases, strict=strict)

    def get_handler(self, name: str) -> Callable | None:
        """Get step handler function"""
        spec: StepSpec | None = self.get(name)
        if spec:
            return spec.handler
        return None

    def get_spec(self, name: str) -> StepSpec | None:
        """Get step specification"""
        return self.get(name)

    def get_dependencies(self, name: str) -> list[str]:
        """Get step dependencies"""
        spec = self.get_spec(name)
        return spec.dependencies if spec else []


class ChainRegistry(BaseRegistry):
    """Registry for chains"""

    def register_chain(
        self,
        name: str,
        steps: list[str],
        chain_class: type | None = None,
        parallel_groups: list[list[str]] | None = None,
        error_handling: str = "fail_fast",
        version: str = "1.0.0",
        description: str = "",
        aliases: list[str] | None = None,
        group: str | None = None,
        strict: bool = False,
        **kwargs,  # Accept extra kwargs for forward compatibility
    ) -> None:
        """Register a new chain"""
        metadata = ComponentMetadata(
            name=name,
            version=version,
            description=description,
            group=group or "",
        )
        spec = ChainSpec(
            metadata=metadata,
            steps=steps,
            chain_class=chain_class,
            parallel_groups=parallel_groups or [],
            error_handling=error_handling,
        )
        self.register(name, spec, aliases, strict=strict)

    def get_spec(self, name: str) -> ChainSpec | None:
        """Get chain specification"""
        return self.get(name)

    def get_steps(self, name: str) -> list[str]:
        """Get chain steps"""
        spec = self.get_spec(name)
        return spec.steps if spec else []

    def is_chain(self, name: str) -> bool:
        """Check if a name refers to a registered chain."""
        return self.has(name)


# Global registry instances (default shared registries)
_agent_registry: AgentRegistry | None = None
_step_registry: StepRegistry | None = None
_chain_registry: ChainRegistry | None = None
_registry_lock = threading.Lock()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry (lazy initialization, thread-safe)"""
    global _agent_registry
    if _agent_registry is None:
        with _registry_lock:
            if _agent_registry is None:
                _agent_registry = AgentRegistry()
    return _agent_registry


def get_step_registry() -> StepRegistry:
    """Get the global step registry (lazy initialization, thread-safe)"""
    global _step_registry
    if _step_registry is None:
        with _registry_lock:
            if _step_registry is None:
                _step_registry = StepRegistry()
    return _step_registry


def get_chain_registry() -> ChainRegistry:
    """Get the global chain registry (lazy initialization, thread-safe)"""
    global _chain_registry
    if _chain_registry is None:
        with _registry_lock:
            if _chain_registry is None:
                _chain_registry = ChainRegistry()
    return _chain_registry


def create_isolated_registries() -> tuple[AgentRegistry, StepRegistry, ChainRegistry]:
    """
    Create a new isolated set of registries.

    Use this for testing or when you need multiple independent FlowForge
    instances in the same process without cross-talk.

    Returns:
        Tuple of (AgentRegistry, StepRegistry, ChainRegistry)

    Example:
        agent_reg, step_reg, chain_reg = create_isolated_registries()
        forge = FlowForge(
            agent_registry=agent_reg,
            step_registry=step_reg,
            chain_registry=chain_reg,
        )
    """
    return AgentRegistry(), StepRegistry(), ChainRegistry()


def reset_global_registries() -> None:
    """
    Reset all global registries to fresh instances.

    Useful for test cleanup to ensure test isolation.
    """
    global _agent_registry, _step_registry, _chain_registry
    with _registry_lock:
        _agent_registry = AgentRegistry()
        _step_registry = StepRegistry()
        _chain_registry = ChainRegistry()
