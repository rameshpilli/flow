"""FlowForge Core Module"""

from flowforge.core.context import ChainContext
from flowforge.core.dag import DAGExecutor
from flowforge.core.decorators import agent, chain, middleware, step
from flowforge.core.forge import FlowForge
from flowforge.core.registry import AgentRegistry, ChainRegistry, StepRegistry
from flowforge.core.resources import (
    Resource,
    ResourceManager,
    ResourceScope,
    get_resource_manager,
    reset_resource_manager,
    resource,
)

__all__ = [
    "FlowForge",
    "agent",
    "step",
    "chain",
    "middleware",
    "ChainContext",
    "AgentRegistry",
    "StepRegistry",
    "ChainRegistry",
    "DAGExecutor",
    # Resources
    "Resource",
    "ResourceManager",
    "ResourceScope",
    "get_resource_manager",
    "reset_resource_manager",
    "resource",
]
