"""
AgentOrchestrator DAG Executor

Provides DAG-based execution of chain steps with:
- Automatic dependency resolution
- Parallel execution of independent steps
- Support for explicit parallel groups
- Per-step concurrency limits
- Error handling and retry logic
- Execution tracing (OpenTelemetry integration)
- Debug callbacks for per-step snapshots
"""

import asyncio
import logging
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from agentorchestrator.core.context import ChainContext, ContextScope, StepResult
from agentorchestrator.core.event_bus import Event, EventBus, get_event_bus
from agentorchestrator.core.registry import (
    ChainSpec,
    StepSpec,
    get_chain_registry,
    get_step_registry,
)
from agentorchestrator.core.validation import (
    ContractValidationError,
    is_pydantic_model,
    validate_chain_input,
    validate_output,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DAGBuilder",
    "DAGExecutor",
    "DAGNode",
    "ExecutionPlan",
    "ChainRunner",
    "DebugCallback",
    "resolve_state_model",
]


# Type for debug callback
class DebugCallback(Protocol):
    """Protocol for debug callbacks invoked after each step"""
    def __call__(
        self,
        ctx: ChainContext,
        step_name: str,
        result: dict[str, Any],
    ) -> None: ...


class StepState(Enum):
    """Execution state of a step"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DAGNode:
    """A node in the execution DAG"""

    name: str
    spec: StepSpec
    state: StepState = StepState.PENDING
    dependencies: set[str] = field(default_factory=set)
    dependents: set[str] = field(default_factory=set)
    result: StepResult | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Per-step concurrency limit (None = use global)
    max_concurrency: int | None = None
    # Lock for thread-safe state mutations during parallel execution
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def is_ready(self) -> bool:
        """Check if all dependencies are satisfied"""
        return self.state == StepState.PENDING and len(self.dependencies) == 0

    async def set_running(self) -> None:
        """Thread-safe transition to RUNNING state"""
        async with self._lock:
            self.state = StepState.RUNNING
            self.started_at = datetime.utcnow()

    async def set_completed(self, result: StepResult) -> None:
        """Thread-safe transition to COMPLETED state"""
        async with self._lock:
            self.state = StepState.COMPLETED
            self.result = result
            self.completed_at = datetime.utcnow()

    async def set_failed(self, result: StepResult) -> None:
        """Thread-safe transition to FAILED state"""
        async with self._lock:
            self.state = StepState.FAILED
            self.result = result
            self.completed_at = datetime.utcnow()

    async def set_skipped(self, reason: str) -> None:
        """Thread-safe transition to SKIPPED state"""
        async with self._lock:
            self.state = StepState.SKIPPED
            self.result = StepResult(
                step_name=self.name,
                output=None,
                duration_ms=0,
                error=None,  # Not an error, just skipped
                skipped_reason=reason,
            )
            self.completed_at = datetime.utcnow()


@dataclass
class ExecutionPlan:
    """A compiled execution plan for a chain"""

    chain_name: str
    nodes: dict[str, DAGNode]
    execution_order: list[list[str]]  # Groups of parallel steps
    total_steps: int
    # Whether this plan uses explicit parallel groups
    uses_explicit_groups: bool = False

    def get_ready_steps(self) -> list[str]:
        """Get steps that are ready to execute"""
        return [name for name, node in self.nodes.items() if node.is_ready]


class DAGBuilder:
    """
    Builds execution DAGs from chain definitions.

    Supports two modes:
    1. Automatic: Computes parallel groups from dependency graph (default)
    2. Explicit: Uses user-defined parallel_groups from ChainSpec

    When explicit parallel_groups are provided, they override the automatic
    computation but dependencies are still validated.
    """

    def __init__(self):
        self.step_registry = get_step_registry()
        self.chain_registry = get_chain_registry()

    def build(self, chain_name: str, existing_nodes: dict[str, DAGNode] | None = None) -> ExecutionPlan:
        """
        Build an execution plan for a chain.
        
        Args:
            chain_name: Name of the chain
            existing_nodes: Optional dict of existing nodes to preserve state
        """
        chain_spec = self.chain_registry.get_spec(chain_name)
        if not chain_spec:
            raise ValueError(f"Chain not found: {chain_name}")

        # Build nodes
        nodes: dict[str, DAGNode] = {}
        for step_name in chain_spec.steps:
            # Preserve existing node if available
            if existing_nodes and step_name in existing_nodes:
                nodes[step_name] = existing_nodes[step_name]
                continue

            step_spec = self.step_registry.get_spec(step_name)
            if not step_spec:
                raise ValueError(f"Step not found: {step_name}")

            nodes[step_name] = DAGNode(
                name=step_name,
                spec=step_spec,
                dependencies=set(step_spec.dependencies),
                max_concurrency=step_spec.max_concurrency,
            )

        # Build dependency graph (add dependents)
        for name, node in nodes.items():
            for dep in node.dependencies:
                if dep in nodes:
                    nodes[dep].dependents.add(name)

        # Determine execution order
        uses_explicit_groups = False
        if chain_spec.parallel_groups:
            # Use explicit parallel groups if provided
            execution_order = self._build_from_explicit_groups(
                chain_spec, nodes
            )
            uses_explicit_groups = True
        else:
            # Compute execution order automatically (topological sort)
            execution_order = self._compute_execution_order(nodes)

        return ExecutionPlan(
            chain_name=chain_name,
            nodes=nodes,
            execution_order=execution_order,
            total_steps=len(nodes),
            uses_explicit_groups=uses_explicit_groups,
        )

    def _build_from_explicit_groups(
        self,
        chain_spec: ChainSpec,
        nodes: dict[str, DAGNode],
    ) -> list[list[str]]:
        """
        Build execution order from explicit parallel groups.

        Validates that:
        1. All steps in groups exist in the chain
        2. Dependencies are satisfied by previous groups
        3. All chain steps are included in groups

        Args:
            chain_spec: Chain specification with parallel_groups
            nodes: DAG nodes

        Returns:
            Execution order (list of groups)
        """
        execution_order = []
        executed = set()
        all_steps = set(chain_spec.steps)
        grouped_steps = set()

        for group_idx, group in enumerate(chain_spec.parallel_groups):
            # Validate group steps exist
            valid_steps = []
            for step_name in group:
                if step_name not in nodes:
                    logger.warning(
                        f"Step '{step_name}' in parallel_groups[{group_idx}] "
                        f"not found in chain steps, skipping"
                    )
                    continue

                # Validate dependencies are satisfied
                node = nodes[step_name]
                unmet_deps = node.dependencies - executed
                if unmet_deps:
                    raise ValueError(
                        f"Step '{step_name}' in parallel_groups[{group_idx}] "
                        f"has unmet dependencies: {unmet_deps}. "
                        f"Move dependencies to earlier groups."
                    )

                valid_steps.append(step_name)
                grouped_steps.add(step_name)

            if valid_steps:
                execution_order.append(valid_steps)
                executed.update(valid_steps)

        # Check for ungrouped steps and add them at the end
        ungrouped = all_steps - grouped_steps
        if ungrouped:
            # Compute execution order for ungrouped steps
            ungrouped_nodes = {name: nodes[name] for name in ungrouped}
            ungrouped_order = self._compute_execution_order(
                ungrouped_nodes, already_executed=executed
            )
            execution_order.extend(ungrouped_order)
            logger.info(
                f"Added {len(ungrouped)} ungrouped steps to execution plan: {ungrouped}"
            )

        return execution_order

    def _compute_execution_order(
        self,
        nodes: dict[str, DAGNode],
        already_executed: set[str] | None = None,
    ) -> list[list[str]]:
        """
        Compute parallel execution groups using Kahn's algorithm.

        Args:
            nodes: DAG nodes to order
            already_executed: Steps that have already been executed
                             (their dependencies are considered satisfied)
        """
        already_executed = already_executed or set()
        node_names = set(nodes.keys())

        # Clone dependencies to avoid mutation, excluding already executed
        in_degree = {}
        for name, node in nodes.items():
            # Only count dependencies that are in this node set and not executed
            deps = node.dependencies - already_executed
            # Warn about deps that reference steps not in this chain
            missing_deps = deps - node_names - already_executed
            if missing_deps:
                logger.warning(
                    f"Step '{name}' has dependencies {missing_deps} that are not in the chain. "
                    f"These will be ignored. Use ao.check() to validate chain configuration."
                )
            deps = deps & node_names  # Only count deps within this set
            in_degree[name] = len(deps)

        dependents = {name: node.dependents.copy() for name, node in nodes.items()}

        execution_order = []
        remaining = set(nodes.keys())

        while remaining:
            # Find all nodes with no remaining dependencies
            ready = [name for name in remaining if in_degree[name] == 0]

            if not ready:
                # Circular dependency detected
                raise ValueError(f"Circular dependency detected in steps: {remaining}")

            execution_order.append(ready)

            # Remove ready nodes and update dependencies
            for name in ready:
                remaining.remove(name)
                for dependent in dependents[name]:
                    if dependent in in_degree:
                        in_degree[dependent] -= 1

        return execution_order


def resolve_state_model(
    chain_name: str,
    chain_registry: Any,
    step_registry: Any,
) -> type | None:
    """
    Resolve a single typed state model for a chain, if defined.

    Returns the unique state_model used by any step in the chain.
    Raises ValueError if multiple distinct models are found.
    """
    chain_spec = chain_registry.get_spec(chain_name)
    if not chain_spec:
        return None

    state_models: list[type] = []
    for step_name in chain_spec.steps:
        step_spec = step_registry.get_spec(step_name)
        if step_spec and getattr(step_spec, "state_model", None) is not None:
            state_models.append(step_spec.state_model)

    unique_models = {model for model in state_models}
    if len(unique_models) > 1:
        model_names = ", ".join(
            sorted(
                model.__name__ if hasattr(model, "__name__") else str(model)
                for model in unique_models
            )
        )
        raise ValueError(
            f"Chain '{chain_name}' uses multiple state models: {model_names}. "
            "Use a single shared state model per chain."
        )

    return next(iter(unique_models), None)


class DAGExecutor:
    """
    Executes chains as DAGs with parallel step execution.

    Features:
    - Automatic dependency resolution
    - Parallel execution of independent steps (bounded by max_parallel)
    - Support for explicit parallel groups (ChainSpec.parallel_groups)
    - Per-step concurrency limits (replaces global semaphore for better performance)
    - Configurable error handling
    - Retry logic for failed steps
    - Middleware support
    - Debug callbacks for per-step snapshots
    - OpenTelemetry tracing integration

    Concurrency Model:
    - max_parallel: Default limit for steps without explicit max_concurrency
    - Per-step max_concurrency: Overrides max_parallel for specific steps
    - No global semaphore: Reduces lock contention, per-group semaphores only
    """

    def __init__(
        self,
        max_parallel: int = 10,
        default_timeout_ms: int = 30000,
        enable_tracing: bool = True,
        event_bus: EventBus | None = None,
    ):
        self.max_parallel = max_parallel
        self.default_timeout_ms = default_timeout_ms
        self.enable_tracing = enable_tracing
        self.builder = DAGBuilder()
        self._middleware: list[Any] = []
        # Prefer Redis-backed bus if available; otherwise fall back to in-memory
        self.event_bus = event_bus or get_event_bus(prefer_redis=True)

    def add_middleware(self, middleware: Any) -> None:
        """Add middleware to the executor"""
        self._middleware.append(middleware)
        # Sort by priority
        self._middleware.sort(key=lambda m: getattr(m, "_ao_priority", 100))

    async def execute(
        self,
        chain_name: str,
        ctx: ChainContext,
        error_handling: str = "fail_fast",
        debug_callback: DebugCallback | None = None,
        precompleted_results: dict[str, StepResult] | None = None,
        skip_steps: set[str] | None = None,
    ) -> ChainContext:
        """
        Execute a chain.

        Args:
            chain_name: Name of the chain to execute
            ctx: Chain context
            error_handling: How to handle errors
                - "fail_fast": Stop on first error
                - "continue": Continue with other steps
                - "retry": Retry failed steps
            debug_callback: Optional callback invoked after each step for debugging.
                            Receives (ctx, step_name, result_dict) arguments.
            precompleted_results: Optional mapping of step_name -> StepResult to
                mark steps as already completed (e.g., on resume).
            skip_steps: Optional set of step names to skip (mark as skipped).

        Returns:
            Updated chain context
        """
        # Import tracing utilities (lazy to avoid circular imports)
        from agentorchestrator.utils.tracing import ChainTracer

        plan = self.builder.build(chain_name)

        group_type = "explicit" if plan.uses_explicit_groups else "automatic"
        logger.info(
            f"Executing chain: {chain_name} ({plan.total_steps} steps, "
            f"{len(plan.execution_order)} groups, {group_type})"
        )

        chain_spec = self.chain_registry.get_spec(chain_name)

        # Use chain-level error_handling if specified, otherwise use the parameter
        effective_error_handling = (
            chain_spec.error_handling if chain_spec and chain_spec.error_handling else error_handling
        )

        # Create tracer for this chain execution
        tracer = ChainTracer(chain_name, ctx.request_id) if self.enable_tracing else None
        # Tag context with chain name for downstream events
        ctx.set("_chain_name", chain_name, scope=ContextScope.CHAIN)

        # Apply precompleted results (e.g., resumability) before execution
        if precompleted_results:
            for group in plan.execution_order:
                for step_name in group:
                    if step_name not in precompleted_results:
                        continue
                    node = plan.nodes.get(step_name)
                    if not node or node.state != StepState.PENDING:
                        continue
                    result = precompleted_results[step_name]
                    await node.set_completed(result)
                    # Avoid duplicate results if caller already seeded context
                    if ctx.get_result(step_name) is None:
                        ctx.add_result(result)

        # Apply explicit skip list (mark as skipped with reason)
        if skip_steps:
            # Ensure we don't skip steps that are already precompleted
            remaining_skips = set(skip_steps) - set(precompleted_results or {})
            if remaining_skips:
                for group in plan.execution_order:
                    for step_name in group:
                        if step_name not in remaining_skips:
                            continue
                        node = plan.nodes.get(step_name)
                        if not node or node.state != StepState.PENDING:
                            continue
                        await node.set_skipped("skipped by executor")
                        if node.result and ctx.get_result(step_name) is None:
                            ctx.add_result(node.result)

        # Wrap execution in chain-level tracing span
        with self._chain_span(tracer, plan.total_steps):
            group_idx = 0
            while group_idx < len(plan.execution_order):
                group = plan.execution_order[group_idx]
                logger.debug(
                    f"Executing group {group_idx + 1}/{len(plan.execution_order)}: "
                    f"{group} (max_parallel={self.max_parallel})"
                )

                # Get pending steps in this group
                pending_steps = [
                    name for name in group
                    if plan.nodes[name].state == StepState.PENDING
                ]

                if pending_steps:
                    # Check for per-group concurrency limits
                    group_concurrency = self._get_group_concurrency(plan.nodes, pending_steps)

                    # Execute steps in parallel within the group
                    await self._execute_group(
                        plan.nodes,
                        pending_steps,
                        ctx,
                        effective_error_handling,
                        group_concurrency,
                        chain_name=chain_name,
                        debug_callback=debug_callback,
                        tracer=tracer,
                    )

                    # Check if any step requested a DAG rebuild
                    if ctx.get("__dag_needs_rebuild__"):
                        ctx.delete("__dag_needs_rebuild__")
                        
                        # ══════════════════════════════════════════════════════════════
                        # PERFORMANCE NOTE: Full DAG Rebuild
                        # ══════════════════════════════════════════════════════════════
                        # Currently, we rebuild the entire DAG when dynamic steps are
                        # injected. For large DAGs (100+ steps), this can be expensive.
                        #
                        # OPTIMIZATION OPPORTUNITY: Implement incremental DAG updates
                        # that only modify affected portions of the execution plan:
                        #
                        # 1. Track which nodes need recalculation based on new deps
                        # 2. Only recompute execution_order for affected subgraph
                        # 3. Use a dirty flag to avoid unnecessary rebuilds
                        # 4. Consider lazy rebuilding (defer until next group)
                        #
                        # For typical use cases (<50 steps), the current implementation
                        # is fast enough (~1-5ms rebuild time).
                        # ══════════════════════════════════════════════════════════════
                        
                        # Rebuild plan and execution order, preserving existing node states
                        plan = self.builder.build(chain_name, existing_nodes=plan.nodes)
                        # We stay at same group_idx but group content changed
                        # and len(execution_order) might have increased
                        logger.info(f"DAG rebuilt dynamically. New order: {plan.execution_order}")
                        # We don't increment group_idx here because we need to 
                        # process the newly built plan from the beginning of 
                        # what's now 'pending'
                        group_idx = 0 
                        continue

                    # In "continue" mode, propagate failures to dependents
                    # Skip dependents whose dependencies have failed
                    if effective_error_handling == "continue":
                        await self._propagate_failures_to_dependents(plan.nodes, ctx, chain_name)

                group_idx += 1

        logger.info(f"Chain {chain_name} completed")
        return ctx

    def _chain_span(self, tracer: Any, total_steps: int):
        """Create a chain-level tracing span (no-op context manager if tracing disabled)"""
        from contextlib import nullcontext
        if tracer is not None:
            return tracer.chain_span(total_steps=total_steps)
        return nullcontext()

    def _get_group_concurrency(
        self,
        nodes: dict[str, DAGNode],
        step_names: list[str],
    ) -> int:
        """
        Determine concurrency limit for a group of steps.

        Uses the minimum per-step limit if any steps have limits,
        otherwise uses the global max_parallel.
        """
        limits = [
            nodes[name].max_concurrency
            for name in step_names
            if nodes[name].max_concurrency is not None
        ]

        if limits:
            # Use the most restrictive limit
            return min(limits)
        return self.max_parallel

    async def _propagate_failures_to_dependents(
        self,
        nodes: dict[str, DAGNode],
        ctx: ChainContext,
        chain_name: str | None = None,
    ) -> None:
        """
        Mark dependents of failed steps as SKIPPED in continue mode.

        In "continue" mode, we want to:
        1. Continue executing steps that don't depend on failed steps
        2. Skip steps whose dependencies have failed (they can't run correctly)
        3. Record the skipped steps with a clear reason

        This prevents steps from running with missing dependency data,
        which would likely cause cryptic errors or incorrect results.
        """
        # Collect all failed and skipped step names
        failed_or_skipped = {
            name for name, node in nodes.items()
            if node.state in (StepState.FAILED, StepState.SKIPPED)
        }

        if not failed_or_skipped:
            return

        # Find all pending steps that have a failed dependency
        to_skip = []
        for name, node in nodes.items():
            if node.state != StepState.PENDING:
                continue

            # Check if any dependency is failed or skipped
            failed_deps = node.dependencies & failed_or_skipped
            if failed_deps:
                to_skip.append((name, failed_deps))

        # Mark as skipped with clear reason
        for step_name, failed_deps in to_skip:
            node = nodes[step_name]
            reason = f"dependency failed: {', '.join(sorted(failed_deps))}"
            await node.set_skipped(reason)
            ctx.add_result(node.result)
            await self._emit_event(
                "StepSkipped",
                chain_name,
                step_name,
                ctx.request_id,
                payload={"reason": reason},
            )
            logger.warning(
                f"Skipping step '{step_name}' because {reason}"
            )

    async def _execute_group(
        self,
        nodes: dict[str, DAGNode],
        step_names: list[str],
        ctx: ChainContext,
        error_handling: str,
        concurrency_limit: int,
        chain_name: str | None = None,
        debug_callback: DebugCallback | None = None,
        tracer: Any = None,
    ) -> list[StepResult]:
        """
        Execute a group of steps with bounded concurrency.

        For fail_fast mode, we cancel outstanding tasks immediately when
        one fails - this is TRUE fail-fast behavior that stops side effects.

        Concurrency is managed per-group only (no global semaphore) to reduce
        lock contention. The concurrency_limit is the minimum of:
        - The global max_parallel setting
        - Any per-step max_concurrency limits in this group
        """
        # Create semaphore for this group's concurrency limit
        # This is the only semaphore - no double-locking
        group_semaphore = asyncio.Semaphore(concurrency_limit)

        async def bounded_execute(step_name: str) -> StepResult:
            """Execute a step with semaphore-bounded concurrency"""
            async with group_semaphore:
                return await self._execute_step(
                    nodes[step_name], ctx, error_handling,
                    chain_name=chain_name,
                    debug_callback=debug_callback,
                    tracer=tracer,
                )

        if error_handling == "fail_fast" or error_handling == "retry":
            # TRUE fail-fast: cancel all tasks on first failure
            # "retry" mode: steps retry internally, but after exhausting retries,
            # failure should still stop the chain (fail-fast with retries)
            return await self._execute_group_fail_fast(
                step_names, bounded_execute, nodes, ctx, chain_name
            )
        else:
            # Continue mode: wait for all tasks, collect results
            return await self._execute_group_continue(
                step_names, bounded_execute
            )

    async def _execute_group_fail_fast(
        self,
        step_names: list[str],
        execute_fn: Callable[[str], Any],
        nodes: dict[str, DAGNode],
        ctx: ChainContext,
        chain_name: str | None = None,
    ) -> list[StepResult]:
        """
        Execute steps with TRUE fail-fast behavior.

        When any task fails, immediately cancel all outstanding tasks.
        This prevents side effects from continuing after a failure.
        """
        tasks: dict[str, asyncio.Task] = {}
        step_results: list[StepResult] = []
        first_exception: Exception | None = None
        cancelled_steps: set[str] = set()

        # Create all tasks
        for name in step_names:
            tasks[name] = asyncio.create_task(execute_fn(name), name=name)

        # Wait for tasks, cancelling on first failure
        pending = set(tasks.values())

        while pending:
            # Wait for the first task to complete
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )

            for task in done:
                try:
                    result = task.result()
                    step_results.append(result)
                except asyncio.CancelledError:
                    # Task was cancelled, skip it
                    step_name = task.get_name()
                    cancelled_steps.add(step_name)
                    logger.debug(f"Task {step_name} was cancelled")
                except Exception as e:
                    # First failure - cancel all pending tasks immediately
                    if first_exception is None:
                        first_exception = e
                        logger.error(
                            f"Step {task.get_name()} failed, cancelling "
                            f"{len(pending)} pending tasks"
                        )
                        for pending_task in pending:
                            cancelled_steps.add(pending_task.get_name())
                            pending_task.cancel()

        # Mark cancelled tasks as skipped for traceability
        if cancelled_steps:
            for step_name in cancelled_steps:
                node = nodes.get(step_name)
                if node and node.state in {StepState.PENDING, StepState.RUNNING}:
                    await node.set_skipped("cancelled due to fail_fast")
                    ctx.add_result(node.result)
                    await self._emit_event(
                        "StepSkipped",
                        chain_name,
                        step_name,
                        ctx.request_id,
                        payload={"reason": "cancelled due to fail_fast"},
                    )

        # If we had a failure, raise it after cleanup
        if first_exception is not None:
            raise first_exception

        return step_results

    async def _execute_group_continue(
        self,
        step_names: list[str],
        execute_fn: Callable[[str], Any],
    ) -> list[StepResult]:
        """
        Execute steps in continue mode - wait for all, collect results.

        Failed steps are logged but don't stop other tasks.
        """
        tasks = [execute_fn(name) for name in step_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        step_results = []
        for i, name in enumerate(step_names):
            if isinstance(results[i], Exception):
                logger.error(f"Step {name} failed: {results[i]}")
            else:
                step_results.append(results[i])

        return step_results

    async def _execute_step(
        self,
        node: DAGNode,
        ctx: ChainContext,
        error_handling: str,
        chain_name: str | None = None,
        debug_callback: DebugCallback | None = None,
        tracer: Any = None,
    ) -> StepResult:
        """Execute a single step with thread-safe state management, tracing, and debug callbacks"""
        from contextlib import nullcontext

        # Determine max attempts (1 + retry count for retry mode)
        retry_config = node.spec.retry_config
        max_attempts = 1 + retry_config.count if error_handling == "retry" else 1
        delay_ms = retry_config.delay_ms
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            if attempt > 0:
                logger.info(
                    f"Retrying step {node.name} "
                    f"(attempt {attempt}/{retry_config.count})"
                )
                # Add jitter to prevent thundering herd in high-concurrency scenarios
                # Jitter is ±25% of the delay to spread out retry attempts
                import random
                jitter_factor = 0.75 + random.random() * 0.5  # 0.75 to 1.25
                jittered_delay_ms = delay_ms * jitter_factor
                await asyncio.sleep(jittered_delay_ms / 1000)
                delay_ms = min(
                    int(delay_ms * retry_config.backoff_multiplier),
                    retry_config.max_delay_ms
                )

            # Thread-safe state transition to RUNNING
            await node.set_running()
            await self._emit_event(
                "StepStarted",
                chain_name,
                node.name,
                ctx.request_id,
                payload={"attempt": attempt},
            )

            start_time = time.perf_counter()

            # Create step-level tracing span
            step_span_ctx = (
                tracer.step_span(node.name) if tracer is not None else nullcontext()
            )

            # Use step_scope context manager for automatic cleanup
            # This ensures step-scoped data is cleaned up even on exceptions
            async with ctx.step_scope(node.name):
                with step_span_ctx as span:
                    try:
                        # Run before middleware with exception isolation
                        # Middleware failures should not crash the step
                        await self._run_before_middleware(ctx, node.name)

                        # Short-circuit if a middleware (e.g., CacheMiddleware) marked a cache hit
                        if ctx.get(f"_cache_hit_{node.name}"):
                            cached_result = ctx.get(f"_cache_result_{node.name}")
                            duration_ms = (time.perf_counter() - start_time) * 1000
                            step_result = StepResult(
                                step_name=node.name,
                                output=cached_result,
                                duration_ms=duration_ms,
                                retry_count=attempt,
                            )
                            step_result.metadata["cache_hit"] = True

                            # Run after middleware for consistency/cleanup
                            await self._run_after_middleware(ctx, node.name, step_result)

                            await node.set_completed(step_result)
                            ctx.add_result(step_result)
                            await self._emit_event(
                                "StepCompleted",
                                chain_name,
                                node.name,
                                ctx.request_id,
                                payload={
                                    "duration_ms": duration_ms,
                                    "retry_count": attempt,
                                    "cache_hit": True,
                                },
                            )

                            if debug_callback is not None:
                                self._invoke_debug_callback(
                                    debug_callback, ctx, node.name, step_result
                                )

                            logger.info(f"Step {node.name} completed from cache in {duration_ms:.2f}ms")
                            return step_result

                        # Execute the step handler
                        timeout_ms = node.spec.timeout_ms or self.default_timeout_ms
                        handler = node.spec.handler

                        if node.spec.is_async:
                            result = await asyncio.wait_for(
                                handler(ctx),
                                timeout=timeout_ms / 1000,
                            )
                        else:
                            # Run sync handlers in thread pool with timeout protection
                            # to prevent blocking the event loop indefinitely
                            result = await asyncio.wait_for(
                                asyncio.to_thread(handler, ctx),
                                timeout=timeout_ms / 1000,
                            )

                        # ══════════════════════════════════════════════════════
                        #              DYNAMIC STEP INJECTION
                        # ══════════════════════════════════════════════════════
                        # Check if result contains dynamic steps to be added to the DAG
                        if isinstance(result, dict) and "__dynamic_steps__" in result:
                            dynamic_steps = result.pop("__dynamic_steps__")
                            if isinstance(dynamic_steps, list):
                                await self._handle_dynamic_steps(
                                    dynamic_steps, node, ctx, chain_name
                                )

                        # ══════════════════════════════════════════════════════
                        #              OUTPUT CONTRACT VALIDATION
                        # ══════════════════════════════════════════════════════
                        if (
                            node.spec.output_model
                            and node.spec.validate_output
                            and is_pydantic_model(node.spec.output_model)
                        ):
                            result = validate_output(
                                step_name=node.name,
                                output_model=node.spec.output_model,
                                value=result,
                            )

                        duration_ms = (time.perf_counter() - start_time) * 1000

                        step_result = StepResult(
                            step_name=node.name,
                            output=result,
                            duration_ms=duration_ms,
                            retry_count=attempt,  # Record how many retries were needed
                        )

                        # Run after middleware with exception isolation
                        await self._run_after_middleware(ctx, node.name, step_result)

                        # Thread-safe state transition to COMPLETED
                        await node.set_completed(step_result)
                        ctx.add_result(step_result)
                        await self._emit_event(
                            "StepCompleted",
                            chain_name,
                            node.name,
                            ctx.request_id,
                            payload={
                                "duration_ms": duration_ms,
                                "retry_count": attempt,
                            },
                        )

                        # Add tracing attributes
                        if span and hasattr(span, 'set_attribute'):
                            span.set_attribute("step.duration_ms", duration_ms)
                            span.set_attribute("step.success", True)
                            span.set_attribute("step.retry_count", attempt)

                        # Invoke debug callback if provided
                        if debug_callback is not None:
                            self._invoke_debug_callback(
                                debug_callback, ctx, node.name, step_result
                            )

                        logger.info(f"Step {node.name} completed in {duration_ms:.2f}ms")
                        return step_result

                    except asyncio.TimeoutError:
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        last_error = TimeoutError(f"Step {node.name} timed out after {timeout_ms}ms")
                        logger.error(f"Step {node.name} timed out")

                        # Record error in span
                        if span and hasattr(span, 'record_exception'):
                            span.record_exception(last_error)

                        # If we have more attempts, continue the retry loop
                        if attempt < max_attempts - 1:
                            logger.warning(
                                f"Retry {attempt + 1} for {node.name} failed: {last_error}"
                            )
                            continue

                        # All retries exhausted or no retries allowed
                        step_result = StepResult(
                            step_name=node.name,
                            output=None,
                            duration_ms=duration_ms,
                            error=last_error,
                            error_type="TimeoutError",
                            error_traceback=traceback.format_exc(),
                            retry_count=attempt,
                        )

                        # Run after middleware for failed steps too (for metrics, logging)
                        await self._run_after_middleware(ctx, node.name, step_result)

                        await node.set_failed(step_result)
                        ctx.add_result(step_result)
                        await self._emit_event(
                            "StepFailed",
                            chain_name,
                            node.name,
                            ctx.request_id,
                            payload={
                                "error": str(last_error),
                                "error_type": "TimeoutError",
                                "duration_ms": duration_ms,
                                "retry_count": attempt,
                            },
                        )

                        if debug_callback is not None:
                            self._invoke_debug_callback(
                                debug_callback, ctx, node.name, step_result
                            )

                        if error_handling == "continue":
                            logger.warning(f"Step {node.name} timed out but continuing (error_handling=continue)")
                            return step_result

                        raise last_error

                    except Exception as e:
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        last_error = e
                        logger.error(f"Step {node.name} failed: {e}")

                        # Record error in span
                        if span and hasattr(span, 'record_exception'):
                            span.record_exception(e)

                        # If we have more attempts, continue the retry loop
                        if attempt < max_attempts - 1:
                            logger.warning(
                                f"Retry {attempt + 1} for {node.name} failed: {e}"
                            )
                            continue

                        # All retries exhausted or no retries allowed
                        if max_attempts > 1:
                            logger.error(
                                f"Step {node.name} failed after {retry_config.count} retries"
                            )

                        step_result = StepResult(
                            step_name=node.name,
                            output=None,
                            duration_ms=duration_ms,
                            error=e,
                            error_type=type(e).__name__,
                            error_traceback=traceback.format_exc(),
                            retry_count=attempt,
                        )

                        # Run after middleware for failed steps too (for metrics, logging)
                        await self._run_after_middleware(ctx, node.name, step_result)

                        await node.set_failed(step_result)
                        ctx.add_result(step_result)
                        await self._emit_event(
                            "StepFailed",
                            chain_name,
                            node.name,
                            ctx.request_id,
                            payload={
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "duration_ms": duration_ms,
                                "retry_count": attempt,
                            },
                        )

                        if debug_callback is not None:
                            self._invoke_debug_callback(
                                debug_callback, ctx, node.name, step_result
                            )

                        if error_handling == "continue":
                            logger.warning(
                                f"Step {node.name} failed but continuing (error_handling=continue)"
                            )
                            return step_result

                        raise

    def _invoke_debug_callback(
        self,
        callback: DebugCallback,
        ctx: ChainContext,
        step_name: str,
        step_result: StepResult,
    ) -> None:
        """Safely invoke debug callback, catching any exceptions"""
        try:
            result_dict = {
                "success": step_result.success,
                "output": step_result.output,
                "duration_ms": step_result.duration_ms,
                "error": str(step_result.error) if step_result.error else None,
                "error_type": step_result.error_type,
            }
            callback(ctx, step_name, result_dict)
        except Exception as e:
            logger.warning(f"Debug callback failed for step {step_name}: {e}")

    async def _emit_event(
        self,
        event_type: str,
        chain_name: str | None,
        step_name: str | None,
        run_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """
        Publish orchestration events to the configured event bus.

        Best-effort: failures are logged at debug and do not break execution.
        """
        if not self.event_bus:
            return
        try:
            await self.event_bus.publish(
                Event(
                    type=event_type,
                    payload=payload or {},
                    step=step_name,
                    run_id=run_id,
                    metadata={"chain": chain_name} if chain_name else {},
                )
            )
        except Exception as e:
            logger.debug("Event publish failed (%s): %s", event_type, e)

    async def _handle_dynamic_steps(
        self,
        dynamic_steps: list[Any],
        parent_node: DAGNode,
        ctx: ChainContext,
        chain_name: str | None,
    ) -> None:
        """
        Handle dynamic steps returned by a step handler.
        
        Dynamically adds new steps to the registry and EXECUTES them immediately.
        This provides true dynamic DAG capability where steps can spawn new steps.
        
        Args:
            dynamic_steps: List of step definitions or names to inject.
                Each can be:
                - dict with "handler", optional "name", "deps", "produces"
                - str name of an existing registered step
            parent_node: The node that returned the dynamic steps.
            ctx: Current execution context.
            chain_name: Name of the executing chain (for registration).
        
        Example return from a step handler:
            >>> return {
            ...     "result": "processed",
            ...     "__dynamic_steps__": [
            ...         {
            ...             "name": "extra_validation",
            ...             "handler": async_validate_func,
            ...             "deps": [],  # Will depend on parent automatically
            ...         },
            ...         "existing_cleanup_step",  # Reference existing step
            ...     ],
            ... }
        """
        from agentorchestrator.core.registry import StepSpec
        
        new_step_names = []
        for i, step_data in enumerate(dynamic_steps):
            if isinstance(step_data, dict) and "handler" in step_data:
                # It's a raw step definition
                name = step_data.get("name") or f"{parent_node.name}_dyn_{i}"
                handler = step_data["handler"]
                # Dynamic steps implicitly depend on parent unless specified
                deps = step_data.get("deps", [parent_node.name])
                # Register the new step dynamically
                self.builder.step_registry.register_step(
                    name=name,
                    handler=handler,
                    dependencies=deps,
                    produces=step_data.get("produces"),
                )
                new_step_names.append(name)
            elif isinstance(step_data, str):
                # It's an existing step name
                new_step_names.append(step_data)
        
        if new_step_names:
            logger.info(f"Step {parent_node.name} injected dynamic steps: {new_step_names}")
            
            # Emit event for observability
            await self._emit_event(
                "DynamicStepInjected",
                chain_name,
                parent_node.name,
                ctx.request_id,
                payload={
                    "injected_steps": new_step_names,
                    "parent_step": parent_node.name,
                },
            )
            
            # Update chain spec if we have a chain name
            if chain_name:
                chain_spec = self.builder.chain_registry.get_spec(chain_name)
                if chain_spec:
                    # Add new steps to chain if not already there
                    for name in new_step_names:
                        if name not in chain_spec.steps:
                            chain_spec.steps.append(name)
            
            # EXECUTE the dynamic steps immediately
            # Build nodes for the new steps and execute them
            for step_name in new_step_names:
                spec = self.builder.step_registry.get_spec(step_name)
                if spec:
                    # Create a node for the dynamic step
                    dynamic_node = DAGNode(name=step_name, spec=spec)
                    
                    # Execute the dynamic step
                    try:
                        logger.info(f"Executing dynamic step: {step_name}")
                        await self._execute_step(
                            dynamic_node,
                            ctx,
                            error_handling="fail_fast",
                            chain_name=chain_name,
                        )
                    except Exception as e:
                        logger.error(f"Dynamic step {step_name} failed: {e}")
                        # Re-raise to propagate failure
                        raise

    async def _run_before_middleware(self, ctx: ChainContext, step_name: str) -> None:
        """
        Run before middleware with exception isolation.

        Middleware failures are logged but don't crash the step execution.
        This ensures cross-cutting concerns (logging, metrics) don't break
        the core pipeline functionality.
        """
        for mw in self._middleware:
            if hasattr(mw, "before"):
                applies = getattr(mw, "_ao_applies_to", None)
                if applies is None or step_name in applies:
                    try:
                        await mw.before(ctx, step_name)
                    except Exception as e:
                        # Log but don't crash - middleware shouldn't break steps
                        logger.warning(
                            f"Before middleware {mw.__class__.__name__} failed for "
                            f"step {step_name}: {e}. Continuing execution."
                        )

    async def _run_after_middleware(
        self, ctx: ChainContext, step_name: str, result: StepResult
    ) -> None:
        """
        Run after middleware with exception isolation.

        Middleware failures are logged but don't crash the step execution.
        """
        for mw in self._middleware:
            if hasattr(mw, "after"):
                applies = getattr(mw, "_ao_applies_to", None)
                if applies is None or step_name in applies:
                    try:
                        await mw.after(ctx, step_name, result)
                    except Exception as e:
                        # Log but don't crash - middleware shouldn't break steps
                        logger.warning(
                            f"After middleware {mw.__class__.__name__} failed for "
                            f"step {step_name}: {e}. Continuing execution."
                        )

    @property
    def chain_registry(self):
        """Get the chain registry (uses builder's registry for isolation support)"""
        return self.builder.chain_registry


class ChainRunner:
    """
    High-level API for running chains with structured logging and OTel integration.

    Usage:
        runner = ChainRunner()
        result = await runner.run("meeting_prep", initial_data={"query": "..."})
    """

    def __init__(self, executor: DAGExecutor | None = None):
        self.executor = executor or DAGExecutor()

    async def run(
        self,
        chain_name: str,
        initial_data: dict[str, Any] | None = None,
        request_id: str | None = None,
        debug_callback: DebugCallback | None = None,
        skip_validation: bool = False,
    ) -> dict[str, Any]:
        """
        Run a chain and return results with structured error information.

        Args:
            chain_name: Name of the chain to run
            initial_data: Initial context data
            request_id: Optional request ID for tracing
            debug_callback: Optional callback invoked after each step for debugging.
                            Receives (ctx, step_name, result_dict) arguments.
            skip_validation: If True, skip input validation (use when caller
                            already validated, e.g., from orchestrator.launch()).

        Returns:
            Dictionary with results, metadata, and structured error info
        """
        import uuid

        request_id = request_id or str(uuid.uuid4())

        # ══════════════════════════════════════════════════════════════════
        #                    FAIL-FAST INPUT VALIDATION
        # ══════════════════════════════════════════════════════════════════
        # Validate input data against first step's input_model BEFORE execution
        # Skip if caller already validated (prevents double validation)
        if skip_validation:
            validated_data = initial_data
        else:
            validated_data = self._validate_chain_input(chain_name, initial_data)

        start_time = time.perf_counter()
        error_info: dict[str, Any] | None = None
        success = True
        ctx: ChainContext | None = None

        try:
            state_model = resolve_state_model(
                chain_name,
                self.executor.chain_registry,
                self.executor.builder.step_registry,
            )

            ctx = ChainContext(
                request_id=request_id,
                initial_data=validated_data,
                state_model=state_model,
            )
            ctx = await self.executor.execute(
                chain_name, ctx, debug_callback=debug_callback
            )
            # Check if any step failed (even in continue mode)
            if any(not r.success for r in ctx.results):
                success = False
        except ContractValidationError as e:
            # Special handling for validation errors - more user-friendly
            success = False
            error_info = {
                "type": "ContractValidationError",
                "message": str(e),
                "step_name": e.step_name,
                "contract_type": e.contract_type,
                "model_name": e.model_name,
                "errors": e.errors,
                "chain": chain_name,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            logger.error(
                f"Contract validation failed: {chain_name}",
                extra={
                    "otel.status_code": "ERROR",
                    "exception.type": "ContractValidationError",
                    "exception.message": str(e),
                    "chain.name": chain_name,
                    "request.id": request_id,
                    "validation.step": e.step_name,
                    "validation.contract_type": e.contract_type,
                },
            )
        except Exception as e:
            success = False
            # Capture structured error information for production debugging
            error_info = self._capture_error(e, chain_name, request_id)

            # Log with OTel-compliant structured attributes
            logger.error(
                f"Chain execution failed: {chain_name}",
                extra={
                    # OTel semantic conventions
                    "otel.status_code": "ERROR",
                    "exception.type": type(e).__name__,
                    "exception.message": str(e),
                    # AgentOrchestrator context
                    "chain.name": chain_name,
                    "request.id": request_id,
                    "error.traceback": error_info.get("traceback"),
                },
            )

        duration_ms = (time.perf_counter() - start_time) * 1000

        if ctx is None:
            ctx = ChainContext(
                request_id=request_id,
                initial_data=validated_data,
            )

        # Log completion with structured attributes
        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            f"Chain {'completed' if success else 'failed'}: {chain_name} "
            f"({duration_ms:.2f}ms)",
            extra={
                "chain.name": chain_name,
                "request.id": request_id,
                "chain.duration_ms": duration_ms,
                "chain.success": success,
                "chain.step_count": len(ctx.results),
            },
        )

        result = {
            "request_id": request_id,
            "chain": chain_name,
            "success": success,
            "duration_ms": duration_ms,
            "results": [
                {
                    "step": r.step_name,
                    "output": r.output,
                    "duration_ms": r.duration_ms,
                    "success": r.success,
                }
                for r in ctx.results
            ],
            "context": ctx.to_dict(),
        }

        # Include structured error info when failed
        if error_info:
            result["error"] = error_info

        return result

    def _validate_chain_input(
        self,
        chain_name: str,
        initial_data: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """
        Validate chain input against first step's input_model (fail-fast).

        Looks at the first step in the chain that has an input_model defined,
        and validates initial_data against it BEFORE execution starts.

        Args:
            chain_name: Name of the chain
            initial_data: Initial data passed to launch()

        Returns:
            Validated/updated initial_data (may contain Pydantic model instances)

        Raises:
            ContractValidationError: If validation fails
        """
        # Get chain spec and find first step with input_model
        chain_spec = self.executor.chain_registry.get_spec(chain_name)
        if not chain_spec:
            return initial_data

        step_registry = self.executor.builder.step_registry

        for step_name in chain_spec.steps:
            step_spec = step_registry.get_spec(step_name)
            if step_spec and step_spec.input_model and is_pydantic_model(step_spec.input_model):
                # Found first step with input contract
                input_key = step_spec.input_key or "request"
                logger.debug(
                    f"Validating chain input against {step_spec.input_model.__name__} "
                    f"(step: {step_name}, key: {input_key})"
                )
                return validate_chain_input(
                    chain_name=chain_name,
                    first_step_name=step_name,
                    input_model=step_spec.input_model,
                    initial_data=initial_data,
                    input_key=input_key,
                )

        # No input validation required
        return initial_data

    def _capture_error(
        self,
        exception: Exception,
        chain_name: str,
        request_id: str,
    ) -> dict[str, Any]:
        """
        Capture structured error information for production debugging.

        Returns OTel-compliant error structure with:
        - Exception type and message
        - Full traceback
        - Context (chain name, request ID)
        - Timestamp for correlation
        """
        import traceback as tb

        # Special handling for ContractValidationError
        if isinstance(exception, ContractValidationError):
            return exception.to_dict()

        return {
            # OTel semantic conventions for exceptions
            "type": type(exception).__name__,
            "message": str(exception),
            "traceback": tb.format_exc(),
            # Context for correlation
            "chain": chain_name,
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            # For backwards compatibility
            "summary": str(exception),
        }
