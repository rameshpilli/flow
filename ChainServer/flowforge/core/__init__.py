"""FlowForge Core Module"""

from flowforge.core.context import ChainContext
from flowforge.core.context_store import (
    ContextRef,
    ContextRefNotFoundError,
    ContextStore,
    InMemoryContextStore,
    RedisContextStore,
    create_context_store,
    is_context_ref,
    offload_to_redis,
    resolve_context_ref,
)
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
from flowforge.core.run_store import (
    FileRunStore,
    InMemoryRunStore,
    ResumableChainRunner,
    RunCheckpoint,
    RunStore,
    StepCheckpoint,
)
from flowforge.core.serializers import (
    CompositeSerializer,
    ContextRefSerializer,
    ContextSerializer,
    CustomSerializer,
    RedactingSerializer,
    SummarySerializer,
    TruncatingSerializer,
    create_safe_serializer,
    create_summary_serializer,
)
from flowforge.core.validation import ContractValidationError

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
    # Run Store (Resumability)
    "RunStore",
    "InMemoryRunStore",
    "FileRunStore",
    "RunCheckpoint",
    "StepCheckpoint",
    "ResumableChainRunner",
    # Context Store (Redis-based Large Payload Offload)
    "ContextStore",
    "InMemoryContextStore",
    "RedisContextStore",
    "ContextRef",
    "ContextRefNotFoundError",
    "create_context_store",
    "offload_to_redis",
    "resolve_context_ref",
    "is_context_ref",
    # Context Serializers
    "ContextSerializer",
    "TruncatingSerializer",
    "RedactingSerializer",
    "ContextRefSerializer",
    "SummarySerializer",
    "CompositeSerializer",
    "CustomSerializer",
    "create_safe_serializer",
    "create_summary_serializer",
    # Validation
    "ContractValidationError",
]
