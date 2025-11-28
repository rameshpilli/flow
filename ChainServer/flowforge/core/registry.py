"""
FlowForge Registry System

Central registry for agents, steps, and chains.
Enables decorator-based registration and discovery.
"""

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

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
class StepSpec:
    """Specification for a registered step"""

    metadata: ComponentMetadata
    handler: Callable
    dependencies: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    retry_config: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000
    is_async: bool = True


@dataclass
class ChainSpec:
    """Specification for a registered chain"""

    metadata: ComponentMetadata
    steps: list[str]
    chain_class: type | None = None
    parallel_groups: list[list[str]] = field(default_factory=list)
    error_handling: str = "fail_fast"  # fail_fast, continue, retry


class BaseRegistry:
    """Base registry with common functionality"""

    def __init__(self):
        self._registry: dict[str, Any] = {}
        self._aliases: dict[str, str] = {}

    def _normalize_name(self, name: str) -> str:
        """Normalize component names"""
        return name.lower().replace("-", "_").replace(" ", "_")

    def register(self, name: str, spec: Any, aliases: list[str] | None = None) -> None:
        """Register a component"""
        normalized = self._normalize_name(name)
        self._registry[normalized] = spec

        if aliases:
            for alias in aliases:
                self._aliases[self._normalize_name(alias)] = normalized

        logger.info(f"Registered: {normalized} (type={type(spec).__name__})")

    def get(self, name: str) -> Any | None:
        """Get a registered component"""
        normalized = self._normalize_name(name)

        # Check direct registration
        if normalized in self._registry:
            return self._registry[normalized]

        # Check aliases
        if normalized in self._aliases:
            return self._registry[self._aliases[normalized]]

        return None

    def has(self, name: str) -> bool:
        """Check if a component is registered"""
        normalized = self._normalize_name(name)
        return normalized in self._registry or normalized in self._aliases

    def list(self, status: ComponentStatus | None = None) -> list[str]:
        """List all registered components"""
        if status is None:
            return list(self._registry.keys())

        return [
            name
            for name, spec in self._registry.items()
            if hasattr(spec, "metadata") and spec.metadata.status == status
        ]

    def remove(self, name: str) -> bool:
        """Remove a component from registry"""
        normalized = self._normalize_name(name)
        if normalized in self._registry:
            del self._registry[normalized]
            # Remove any aliases pointing to this component
            self._aliases = {k: v for k, v in self._aliases.items() if v != normalized}
            return True
        return False

    def clear(self) -> None:
        """Clear all registrations"""
        self._registry.clear()
        self._aliases.clear()


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
        self.register(name, spec, aliases)

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
        version: str = "1.0.0",
        description: str = "",
        timeout_ms: int = 30000,
        retry_config: dict[str, Any] | None = None,
        aliases: list[str] | None = None,
        group: str | None = None,
        retry_count: int = 0,
        **kwargs,  # Accept extra kwargs for forward compatibility
    ) -> None:
        """Register a new step"""
        metadata = ComponentMetadata(
            name=name,
            version=version,
            description=description,
            group=group or "",
        )
        spec = StepSpec(
            metadata=metadata,
            handler=handler,
            dependencies=dependencies or [],
            produces=produces or [],
            timeout_ms=timeout_ms,
            retry_config=retry_config or {"count": retry_count},
            is_async=inspect.iscoroutinefunction(handler),
        )
        self.register(name, spec, aliases)

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
        self.register(name, spec, aliases)

    def get_spec(self, name: str) -> ChainSpec | None:
        """Get chain specification"""
        return self.get(name)

    def get_steps(self, name: str) -> list[str]:
        """Get chain steps"""
        spec = self.get_spec(name)
        return spec.steps if spec else []


# Global registry instances
_agent_registry = AgentRegistry()
_step_registry = StepRegistry()
_chain_registry = ChainRegistry()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry"""
    return _agent_registry


def get_step_registry() -> StepRegistry:
    """Get the global step registry"""
    return _step_registry


def get_chain_registry() -> ChainRegistry:
    """Get the global chain registry"""
    return _chain_registry
