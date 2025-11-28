"""
FlowForge DAG Executor

Provides DAG-based execution of chain steps with:
- Automatic dependency resolution
- Parallel execution of independent steps
- Error handling and retry logic
- Execution tracing
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from flowforge.core.context import ChainContext, StepResult
from flowforge.core.registry import (
    StepSpec,
    get_chain_registry,
    get_step_registry,
)

logger = logging.getLogger(__name__)


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

    @property
    def is_ready(self) -> bool:
        """Check if all dependencies are satisfied"""
        return self.state == StepState.PENDING and len(self.dependencies) == 0


@dataclass
class ExecutionPlan:
    """A compiled execution plan for a chain"""

    chain_name: str
    nodes: dict[str, DAGNode]
    execution_order: list[list[str]]  # Groups of parallel steps
    total_steps: int

    def get_ready_steps(self) -> list[str]:
        """Get steps that are ready to execute"""
        return [name for name, node in self.nodes.items() if node.is_ready]


class DAGBuilder:
    """Builds execution DAGs from chain definitions"""

    def __init__(self):
        self.step_registry = get_step_registry()
        self.chain_registry = get_chain_registry()

    def build(self, chain_name: str) -> ExecutionPlan:
        """Build an execution plan for a chain"""
        chain_spec = self.chain_registry.get_spec(chain_name)
        if not chain_spec:
            raise ValueError(f"Chain not found: {chain_name}")

        # Build nodes
        nodes: dict[str, DAGNode] = {}
        for step_name in chain_spec.steps:
            step_spec = self.step_registry.get_spec(step_name)
            if not step_spec:
                raise ValueError(f"Step not found: {step_name}")

            nodes[step_name] = DAGNode(
                name=step_name,
                spec=step_spec,
                dependencies=set(step_spec.dependencies),
            )

        # Build dependency graph (add dependents)
        for name, node in nodes.items():
            for dep in node.dependencies:
                if dep in nodes:
                    nodes[dep].dependents.add(name)

        # Compute execution order (topological sort with parallelization)
        execution_order = self._compute_execution_order(nodes)

        return ExecutionPlan(
            chain_name=chain_name,
            nodes=nodes,
            execution_order=execution_order,
            total_steps=len(nodes),
        )

    def _compute_execution_order(self, nodes: dict[str, DAGNode]) -> list[list[str]]:
        """Compute parallel execution groups using Kahn's algorithm"""
        # Clone dependencies to avoid mutation
        in_degree = {name: len(node.dependencies) for name, node in nodes.items()}
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
                    in_degree[dependent] -= 1

        return execution_order


class DAGExecutor:
    """
    Executes chains as DAGs with parallel step execution.

    Features:
    - Automatic dependency resolution
    - Parallel execution of independent steps
    - Configurable error handling
    - Retry logic for failed steps
    - Middleware support
    """

    def __init__(
        self,
        max_parallel: int = 10,
        default_timeout_ms: int = 30000,
    ):
        self.max_parallel = max_parallel
        self.default_timeout_ms = default_timeout_ms
        self.builder = DAGBuilder()
        self._middleware: list[Any] = []

    def add_middleware(self, middleware: Any) -> None:
        """Add middleware to the executor"""
        self._middleware.append(middleware)
        # Sort by priority
        self._middleware.sort(key=lambda m: getattr(m, "_flowforge_priority", 100))

    async def execute(
        self,
        chain_name: str,
        ctx: ChainContext,
        error_handling: str = "fail_fast",
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

        Returns:
            Updated chain context
        """
        plan = self.builder.build(chain_name)
        logger.info(f"Executing chain: {chain_name} ({plan.total_steps} steps)")

        chain_spec = self.chain_registry.get_spec(chain_name)

        for group in plan.execution_order:
            logger.debug(f"Executing group: {group}")

            # Execute steps in parallel within the group
            tasks = [
                self._execute_step(plan.nodes[name], ctx, error_handling)
                for name in group
                if plan.nodes[name].state == StepState.PENDING
            ]

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Handle results
                for i, name in enumerate(group):
                    if isinstance(results[i], Exception):
                        if error_handling == "fail_fast":
                            raise results[i]
                        logger.error(f"Step {name} failed: {results[i]}")

        logger.info(f"Chain {chain_name} completed")
        return ctx

    async def _execute_step(
        self,
        node: DAGNode,
        ctx: ChainContext,
        error_handling: str,
    ) -> StepResult:
        """Execute a single step"""
        node.state = StepState.RUNNING
        node.started_at = datetime.utcnow()
        ctx.enter_step(node.name)

        start_time = time.perf_counter()

        try:
            # Run before middleware
            for mw in self._middleware:
                if hasattr(mw, "before"):
                    applies = getattr(mw, "_flowforge_applies_to", None)
                    if applies is None or node.name in applies:
                        await mw.before(ctx, node.name)

            # Execute the step handler
            timeout_ms = node.spec.timeout_ms or self.default_timeout_ms
            handler = node.spec.handler

            if node.spec.is_async:
                result = await asyncio.wait_for(
                    handler(ctx),
                    timeout=timeout_ms / 1000,
                )
            else:
                result = handler(ctx)

            duration_ms = (time.perf_counter() - start_time) * 1000

            step_result = StepResult(
                step_name=node.name,
                output=result,
                duration_ms=duration_ms,
            )

            # Run after middleware
            for mw in self._middleware:
                if hasattr(mw, "after"):
                    applies = getattr(mw, "_flowforge_applies_to", None)
                    if applies is None or node.name in applies:
                        await mw.after(ctx, node.name, step_result)

            node.state = StepState.COMPLETED
            node.result = step_result
            ctx.add_result(step_result)

            logger.info(f"Step {node.name} completed in {duration_ms:.2f}ms")
            return step_result

        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error = TimeoutError(f"Step {node.name} timed out after {timeout_ms}ms")
            step_result = StepResult(
                step_name=node.name,
                output=None,
                duration_ms=duration_ms,
                error=error,
            )
            node.state = StepState.FAILED
            node.result = step_result
            ctx.add_result(step_result)
            logger.error(f"Step {node.name} timed out")
            raise error

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            step_result = StepResult(
                step_name=node.name,
                output=None,
                duration_ms=duration_ms,
                error=e,
            )
            node.state = StepState.FAILED
            node.result = step_result
            ctx.add_result(step_result)
            logger.error(f"Step {node.name} failed: {e}")

            # Handle retry logic
            if error_handling == "retry" and node.spec.retry_config:
                retry_count = node.spec.retry_config.get("count", 0)
                retry_delay = node.spec.retry_config.get("delay_ms", 1000)

                for attempt in range(retry_count):
                    logger.info(f"Retrying step {node.name} (attempt {attempt + 1}/{retry_count})")
                    await asyncio.sleep(retry_delay / 1000)
                    try:
                        node.state = StepState.RUNNING
                        return await self._execute_step(node, ctx, "fail_fast")
                    except Exception:
                        continue

            raise

        finally:
            node.completed_at = datetime.utcnow()
            ctx.exit_step()

    @property
    def chain_registry(self):
        return get_chain_registry()


class ChainRunner:
    """
    High-level API for running chains.

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
    ) -> dict[str, Any]:
        """
        Run a chain and return results.

        Args:
            chain_name: Name of the chain to run
            initial_data: Initial context data
            request_id: Optional request ID for tracing

        Returns:
            Dictionary with results and metadata
        """
        import uuid

        request_id = request_id or str(uuid.uuid4())

        ctx = ChainContext(
            request_id=request_id,
            initial_data=initial_data,
        )

        start_time = time.perf_counter()

        try:
            ctx = await self.executor.execute(chain_name, ctx)
            success = True
            error = None
        except Exception as e:
            success = False
            error = str(e)

        duration_ms = (time.perf_counter() - start_time) * 1000

        return {
            "request_id": request_id,
            "chain": chain_name,
            "success": success,
            "error": error,
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
