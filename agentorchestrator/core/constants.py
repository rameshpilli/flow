"""
AgentOrchestrator Constants and Enums
=====================================

Defines string constants and enums to replace magic strings throughout
the codebase. Using these constants provides:

1. IDE autocomplete and type checking
2. Single source of truth for valid values
3. Clear documentation of allowed options
4. Prevention of typos in configuration

Usage:
    from agentorchestrator.core.constants import (
        ErrorHandling,
        MergeMode,
        StorageBackend,
    )
    
    @ao.chain
    class MyChain:
        steps = ["step1", "step2"]
        error_handling = ErrorHandling.CONTINUE
    
    result = ao.subchain(
        "sub_chain",
        merge_mode=MergeMode.SELECTIVE,
        merge_map={"output": "sub_output"},
    )
"""

from enum import Enum
from typing import Literal


class ErrorHandling(str, Enum):
    """
    Error handling strategies for chain execution.
    
    Determines how the DAG executor responds to step failures.
    
    Attributes:
        FAIL_FAST: Stop execution immediately on first failure (default).
            - Cancels any pending parallel steps
            - Returns partial results from completed steps
            - Best for: pipelines where later steps depend on earlier ones
        
        CONTINUE: Continue executing independent steps after a failure.
            - Only skips steps that depend on the failed step
            - Collects all errors and returns them in results
            - Best for: parallel independent operations
        
        RETRY: Automatically retry failed steps.
            - Uses the step's retry configuration
            - After max retries, behavior depends on retry_fallback
            - Best for: transient failures (network, rate limits)
    
    Example:
        >>> @ao.chain
        ... class ResilientChain:
        ...     steps = ["step1", "step2", "step3"]
        ...     error_handling = ErrorHandling.CONTINUE
    """
    
    FAIL_FAST = "fail_fast"
    CONTINUE = "continue"
    RETRY = "retry"


class MergeMode(str, Enum):
    """
    Merge strategies for subchain results.
    
    Controls how subchain outputs are merged back into the parent context.
    
    Attributes:
        SAFE: Only merge new keys, never overwrite parent data (default).
            - Prevents accidental data loss
            - Logs a warning when keys are skipped
            - Best for: most use cases
        
        SELECTIVE: Only merge keys specified in merge_map.
            - Requires merge_map to be provided
            - Provides explicit control over what gets merged
            - Best for: complex pipelines with potential key conflicts
        
        ALL: Merge all subchain outputs, overwriting if necessary.
            - Can overwrite parent context data
            - Logs a warning when overwrites occur
            - Best for: when subchain output should replace parent data
        
        NONE: Don't merge any keys into parent context.
            - Subchain results available via _subchain_{name}_result
            - Best for: isolated subchain execution
    
    Example:
        >>> ao.subchain(
        ...     "data_processor",
        ...     merge_mode=MergeMode.SELECTIVE,
        ...     merge_map={"processed_data": "step2_data"},
        ... )
    """
    
    SAFE = "safe"
    SELECTIVE = "selective"
    ALL = "all"
    NONE = "none"


class StorageBackend(str, Enum):
    """
    Storage backend options for context store and other services.
    
    Attributes:
        MEMORY: In-memory storage (default for development).
            - Fast, no external dependencies
            - Data lost on restart
            - Not suitable for production distributed systems
        
        REDIS: Redis-backed storage.
            - Persistent, shared across processes
            - Requires Redis server
            - Recommended for production
        
        MEM0: Mem0 semantic memory storage.
            - Provides semantic search capabilities
            - Requires Mem0 service
            - Best for: long-term memory, RAG applications
    
    Example:
        >>> from agentorchestrator.core.constants import StorageBackend
        >>> config = Config(context_store_backend=StorageBackend.REDIS)
    """
    
    MEMORY = "memory"
    REDIS = "redis"
    MEM0 = "mem0"


class ResourceScope(str, Enum):
    """
    Resource lifecycle scope.
    
    Determines when resources are created and destroyed.
    
    Attributes:
        SINGLETON: One instance shared across all uses (default).
            - Created on first access
            - Lives until explicit cleanup
            - Best for: connections, caches, clients
        
        REQUEST: New instance per chain execution.
            - Created fresh for each launch() call
            - Cleaned up after chain completes
            - Best for: request-specific state
        
        STEP: New instance per step execution.
            - Created fresh for each step
            - Cleaned up after step completes
            - Best for: step-local resources
    
    Example:
        >>> ao.register_resource(
        ...     "db",
        ...     factory=create_db_pool,
        ...     scope=ResourceScope.SINGLETON,
        ...     cleanup=lambda p: p.close(),
        ... )
    """
    
    SINGLETON = "singleton"
    REQUEST = "request"
    STEP = "step"


class ContextScope(str, Enum):
    """
    Context data lifecycle scope.
    
    Determines how long context data persists.
    
    Attributes:
        STEP: Auto-cleaned after step completes.
            - Use for temporary step-local data
            - Prevents accidental data leakage
        
        CHAIN: Lives for entire chain execution (default).
            - Use for data shared between steps
            - Cleaned up when chain completes
        
        GLOBAL: Persists across chain executions.
            - Use for caches, configuration
            - Must be manually cleaned up
    
    Example:
        >>> ctx.set("temp_data", value, scope=ContextScope.STEP)
        >>> ctx.set("shared_data", value, scope=ContextScope.CHAIN)
    """
    
    STEP = "step"
    CHAIN = "chain"
    GLOBAL = "global"


class RunStatus(str, Enum):
    """
    Status of a resumable chain run.
    
    Attributes:
        PENDING: Run has been created but not started.
        RUNNING: Run is currently executing.
        COMPLETED: Run finished successfully.
        PARTIAL: Run stopped partway through (some steps completed).
        FAILED: Run encountered an unrecoverable error.
        CANCELLED: Run was manually cancelled.
    
    Example:
        >>> checkpoint = await ao.get_run(run_id)
        >>> if checkpoint.status == RunStatus.PARTIAL:
        ...     await ao.resume(run_id)
    """
    
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentCapability(str, Enum):
    """
    Standard agent capabilities for capability-based routing.
    
    Use these to classify what an agent can do, enabling the
    MultiAgentOrchestrator to route requests appropriately.
    
    Attributes:
        SEARCH: Web/database search capability.
        CALCULATE: Mathematical/computational capability.
        CODE: Code generation/analysis capability.
        SUMMARIZE: Text summarization capability.
        TRANSLATE: Language translation capability.
        ANALYZE: Data/document analysis capability.
        GENERATE: Content generation capability.
        RETRIEVE: RAG/document retrieval capability.
        TOOL_USE: General tool execution capability.
    
    Example:
        >>> @ao.agent(capabilities=[AgentCapability.SEARCH, AgentCapability.SUMMARIZE])
        ... class ResearchAgent:
        ...     pass
    """
    
    SEARCH = "search"
    CALCULATE = "calculate"
    CODE = "code"
    SUMMARIZE = "summarize"
    TRANSLATE = "translate"
    ANALYZE = "analyze"
    GENERATE = "generate"
    RETRIEVE = "retrieve"
    TOOL_USE = "tool_use"


# Type aliases for string literals (for backward compatibility)
ErrorHandlingLiteral = Literal["fail_fast", "continue", "retry"]
MergeModeLiteral = Literal["safe", "selective", "all", "none"]
StorageBackendLiteral = Literal["memory", "redis", "mem0"]
ResourceScopeLiteral = Literal["singleton", "request", "step"]
ContextScopeLiteral = Literal["step", "chain", "global"]
RunStatusLiteral = Literal["pending", "running", "completed", "partial", "failed", "cancelled"]


__all__ = [
    # Enums
    "ErrorHandling",
    "MergeMode",
    "StorageBackend",
    "ResourceScope",
    "ContextScope",
    "RunStatus",
    "AgentCapability",
    # Type aliases
    "ErrorHandlingLiteral",
    "MergeModeLiteral",
    "StorageBackendLiteral",
    "ResourceScopeLiteral",
    "ContextScopeLiteral",
    "RunStatusLiteral",
]