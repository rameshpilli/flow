"""
AgentOrchestrator Run Store - Persistence for Resumability

Provides checkpoint persistence for chain executions, enabling:
- Resume failed runs from where they stopped
- Re-run only failed steps
- Surface partial outputs instead of all-or-nothing
- Audit trail of execution history

Storage backends:
- InMemoryRunStore: For development/testing
- FileRunStore: JSON files on disk
- (Future: RedisRunStore, PostgresRunStore)
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from agentorchestrator.core.context import ChainContext, StepResult

logger = logging.getLogger(__name__)


@dataclass
class StepCheckpoint:
    """
    Checkpoint for a single step execution.

    Contains everything needed to understand what happened
    and whether to re-run the step.
    """
    step_name: str
    status: str  # "pending", "running", "completed", "failed", "skipped"
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float = 0.0
    output: Any = None
    error: str | None = None
    error_type: str | None = None
    error_traceback: str | None = None
    retry_count: int = 0
    skipped_reason: str | None = None

    @classmethod
    def from_step_result(cls, result: StepResult) -> "StepCheckpoint":
        """Create checkpoint from a StepResult."""
        if result.success:
            status = "completed"
        elif result.skipped:
            status = "skipped"
        else:
            status = "failed"

        return cls(
            step_name=result.step_name,
            status=status,
            duration_ms=result.duration_ms,
            output=result.output,
            error=str(result.error) if result.error else None,
            error_type=result.error_type,
            error_traceback=result.error_traceback,
            retry_count=result.retry_count,
            skipped_reason=result.skipped_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "step_name": self.step_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "output": self._serialize_output(self.output),
            "error": self.error,
            "error_type": self.error_type,
            "error_traceback": self.error_traceback,
            "retry_count": self.retry_count,
            "skipped_reason": self.skipped_reason,
        }

    @staticmethod
    def _serialize_output(output: Any) -> Any:
        """Serialize output for JSON storage."""
        if output is None:
            return None
        try:
            # Try to serialize to JSON to test serializability
            json.dumps(output)
            return output
        except (TypeError, ValueError):
            # Not directly serializable, try __dict__ or str
            if hasattr(output, "model_dump"):
                return output.model_dump()  # Pydantic v2
            if hasattr(output, "dict"):
                return output.dict()  # Pydantic v1
            if hasattr(output, "__dict__"):
                return {"_type": type(output).__name__, "data": str(output)}
            return {"_type": type(output).__name__, "data": str(output)}


@dataclass
class RunCheckpoint:
    """
    Complete checkpoint for a chain run.

    Contains all information needed to resume or analyze a run.
    """
    run_id: str
    chain_name: str
    status: str  # "pending", "running", "completed", "failed", "partial"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: str | None = None

    # Initial data passed to launch()
    initial_data: dict[str, Any] = field(default_factory=dict)

    # Context data at each checkpoint
    context_data: dict[str, Any] = field(default_factory=dict)

    # Step checkpoints (ordered)
    steps: list[StepCheckpoint] = field(default_factory=list)

    # Metadata
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    total_duration_ms: float = 0.0

    # For resumability
    last_completed_step: str | None = None
    next_step: str | None = None
    resumable: bool = True

    def update_from_context(self, ctx: ChainContext) -> None:
        """Update checkpoint from current context state."""
        self.context_data = ctx.to_dict().get("data", {})
        self.updated_at = datetime.utcnow().isoformat()

    def add_step_checkpoint(self, checkpoint: StepCheckpoint) -> None:
        """Add a step checkpoint and update counters."""
        self.steps.append(checkpoint)
        self.total_duration_ms += checkpoint.duration_ms
        self.updated_at = datetime.utcnow().isoformat()

        if checkpoint.status == "completed":
            self.completed_steps += 1
            self.last_completed_step = checkpoint.step_name
        elif checkpoint.status == "failed":
            self.failed_steps += 1
        elif checkpoint.status == "skipped":
            self.skipped_steps += 1

    def finalize(self, success: bool) -> None:
        """Finalize the run checkpoint."""
        self.completed_at = datetime.utcnow().isoformat()
        self.updated_at = self.completed_at

        if success:
            self.status = "completed"
        elif self.completed_steps > 0:
            self.status = "partial"
        else:
            self.status = "failed"

        self.resumable = self.status in ("failed", "partial")

    def get_failed_steps(self) -> list[str]:
        """Get names of failed steps."""
        return [s.step_name for s in self.steps if s.status == "failed"]

    def get_completed_steps(self) -> list[str]:
        """Get names of completed steps."""
        return [s.step_name for s in self.steps if s.status == "completed"]

    def get_pending_steps(self) -> list[str]:
        """Get names of steps that haven't run."""
        return [s.step_name for s in self.steps if s.status == "pending"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "run_id": self.run_id,
            "chain_name": self.chain_name,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "initial_data": self.initial_data,
            "context_data": self.context_data,
            "steps": [s.to_dict() for s in self.steps],
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "total_duration_ms": self.total_duration_ms,
            "last_completed_step": self.last_completed_step,
            "next_step": self.next_step,
            "resumable": self.resumable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunCheckpoint":
        """Reconstruct from dict."""
        steps = [
            StepCheckpoint(**s) for s in data.get("steps", [])
        ]
        return cls(
            run_id=data["run_id"],
            chain_name=data["chain_name"],
            status=data.get("status", "pending"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            completed_at=data.get("completed_at"),
            initial_data=data.get("initial_data", {}),
            context_data=data.get("context_data", {}),
            steps=steps,
            total_steps=data.get("total_steps", 0),
            completed_steps=data.get("completed_steps", 0),
            failed_steps=data.get("failed_steps", 0),
            skipped_steps=data.get("skipped_steps", 0),
            total_duration_ms=data.get("total_duration_ms", 0.0),
            last_completed_step=data.get("last_completed_step"),
            next_step=data.get("next_step"),
            resumable=data.get("resumable", True),
        )


class RunStore(ABC):
    """
    Abstract base class for run persistence.

    Implementations provide storage for run checkpoints.
    """

    @abstractmethod
    async def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        """Save or update a run checkpoint."""
        pass

    @abstractmethod
    async def load_checkpoint(self, run_id: str) -> RunCheckpoint | None:
        """Load a run checkpoint by ID."""
        pass

    @abstractmethod
    async def delete_checkpoint(self, run_id: str) -> bool:
        """Delete a run checkpoint."""
        pass

    @abstractmethod
    async def list_runs(
        self,
        chain_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[RunCheckpoint]:
        """List run checkpoints with optional filters."""
        pass

    async def get_resumable_runs(self, chain_name: str) -> list[RunCheckpoint]:
        """Get all resumable runs for a chain."""
        runs = await self.list_runs(chain_name=chain_name)
        return [r for r in runs if r.resumable]


class InMemoryRunStore(RunStore):
    """
    In-memory run store for development and testing.

    Data is lost when the process exits.
    """

    def __init__(self):
        self._store: dict[str, RunCheckpoint] = {}

    async def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        self._store[checkpoint.run_id] = checkpoint
        logger.debug(f"Saved checkpoint: {checkpoint.run_id}")

    async def load_checkpoint(self, run_id: str) -> RunCheckpoint | None:
        return self._store.get(run_id)

    async def delete_checkpoint(self, run_id: str) -> bool:
        if run_id in self._store:
            del self._store[run_id]
            return True
        return False

    async def list_runs(
        self,
        chain_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[RunCheckpoint]:
        runs = list(self._store.values())

        if chain_name:
            runs = [r for r in runs if r.chain_name == chain_name]
        if status:
            runs = [r for r in runs if r.status == status]

        # Sort by created_at descending
        runs.sort(key=lambda r: r.created_at, reverse=True)

        return runs[:limit]


class FileRunStore(RunStore):
    """
    File-based run store using JSON files.

    Each run is stored as a separate JSON file in the specified directory.
    """

    def __init__(self, directory: str | Path):
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileRunStore initialized at: {self._directory}")

    def _get_path(self, run_id: str) -> Path:
        """Get file path for a run ID."""
        # Sanitize run_id for filesystem
        safe_id = "".join(c for c in run_id if c.isalnum() or c in "-_")
        return self._directory / f"{safe_id}.json"

    async def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        path = self._get_path(checkpoint.run_id)
        try:
            with open(path, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2, default=str)
            logger.debug(f"Saved checkpoint to: {path}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise

    async def load_checkpoint(self, run_id: str) -> RunCheckpoint | None:
        path = self._get_path(run_id)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            return RunCheckpoint.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    async def delete_checkpoint(self, run_id: str) -> bool:
        path = self._get_path(run_id)
        if path.exists():
            path.unlink()
            return True
        return False

    async def list_runs(
        self,
        chain_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[RunCheckpoint]:
        runs = []
        for path in self._directory.glob("*.json"):
            try:
                checkpoint = await self.load_checkpoint(path.stem)
                if checkpoint:
                    if chain_name and checkpoint.chain_name != chain_name:
                        continue
                    if status and checkpoint.status != status:
                        continue
                    runs.append(checkpoint)
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")

        # Sort by created_at descending
        runs.sort(key=lambda r: r.created_at, reverse=True)

        return runs[:limit]


class ResumableChainRunner:
    """
    Chain runner with built-in resumability support.

    Wraps DAGExecutor to provide:
    - Automatic checkpointing after each step
    - Resume from failed runs
    - Re-run only failed steps
    - Partial output retrieval

    Usage:
        from agentorchestrator.core.run_store import ResumableChainRunner, FileRunStore

        store = FileRunStore("./run_checkpoints")
        runner = ResumableChainRunner(store=store)

        # Run a chain
        result = await runner.run("my_pipeline", data={"key": "value"})

        # If it fails, resume later
        result = await runner.resume(run_id="run_abc123")

        # Or re-run only failed steps
        result = await runner.retry_failed(run_id="run_abc123")
    """

    def __init__(
        self,
        store: RunStore | None = None,
        executor: Any = None,  # DAGExecutor
        auto_checkpoint: bool = True,
    ):
        """
        Initialize resumable runner.

        Args:
            store: Run store for persistence (default: InMemoryRunStore)
            executor: DAGExecutor instance (created if not provided)
            auto_checkpoint: Save checkpoint after each step
        """
        self._store = store or InMemoryRunStore()
        self._auto_checkpoint = auto_checkpoint

        # Import here to avoid circular imports
        if executor is None:
            from agentorchestrator.core.dag import DAGExecutor
            executor = DAGExecutor()
        self._executor = executor

    async def run(
        self,
        chain_name: str,
        initial_data: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run a chain with checkpointing.

        Args:
            chain_name: Name of the chain to run
            initial_data: Initial context data
            run_id: Optional run ID (generated if not provided)

        Returns:
            Execution result with checkpoint info
        """
        import uuid

        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"

        # Create initial checkpoint
        checkpoint = RunCheckpoint(
            run_id=run_id,
            chain_name=chain_name,
            status="running",
            initial_data=initial_data or {},
        )

        # Get chain spec to know total steps
        chain_spec = self._executor.chain_registry.get_spec(chain_name)
        if chain_spec:
            checkpoint.total_steps = len(chain_spec.steps)

        await self._store.save_checkpoint(checkpoint)

        # Create context
        ctx = ChainContext(
            request_id=run_id,
            initial_data=initial_data,
        )

        # Define step callback for checkpointing (must be sync as per DebugCallback protocol)
        def on_step_complete(ctx: ChainContext, step_name: str, result_dict: dict):
            """Sync callback that schedules async checkpoint save."""
            # Create step checkpoint from result dict
            step_cp = StepCheckpoint(
                step_name=step_name,
                status="completed" if result_dict.get("success") else "failed",
                started_at=datetime.utcnow().isoformat(),
                completed_at=datetime.utcnow().isoformat(),
                output=result_dict.get("output"),
                error=result_dict.get("error"),
                error_type=result_dict.get("error_type"),
            )
            checkpoint.add_step_checkpoint(step_cp)
            checkpoint.update_from_context(ctx)

            # Schedule async save without blocking (fire-and-forget)
            if self._auto_checkpoint:
                asyncio.create_task(self._store.save_checkpoint(checkpoint))

        # Execute with callback
        try:
            ctx = await self._executor.execute(
                chain_name,
                ctx,
                debug_callback=on_step_complete,
            )

            # Check success
            success = all(r.success for r in ctx.results)
            checkpoint.finalize(success)

        except Exception as e:
            checkpoint.status = "failed"
            checkpoint.resumable = True
            logger.error(f"Chain execution failed: {e}")
            raise
        finally:
            await self._store.save_checkpoint(checkpoint)

        return {
            "run_id": run_id,
            "chain_name": chain_name,
            "success": checkpoint.status == "completed",
            "status": checkpoint.status,
            "checkpoint": checkpoint.to_dict(),
            "context": ctx.to_dict(),
        }

    async def resume(
        self,
        run_id: str,
        skip_completed: bool = True,
    ) -> dict[str, Any]:
        """
        Resume a failed or partial run.

        Args:
            run_id: ID of the run to resume
            skip_completed: Skip steps that already completed

        Returns:
            Execution result
        """
        checkpoint = await self._store.load_checkpoint(run_id)
        if checkpoint is None:
            raise ValueError(f"Run not found: {run_id}")

        if not checkpoint.resumable:
            raise ValueError(f"Run is not resumable: {run_id}")

        # Restore context with completed step outputs
        initial_data = checkpoint.initial_data.copy()
        if skip_completed:
            # Add outputs from completed steps to context
            for step_cp in checkpoint.steps:
                if step_cp.status == "completed" and step_cp.output:
                    # Merge output dict into initial_data
                    if isinstance(step_cp.output, dict):
                        initial_data.update(step_cp.output)

        # Get steps to run
        completed_steps = set(checkpoint.get_completed_steps())

        # Update checkpoint for resume
        checkpoint.status = "running"
        checkpoint.updated_at = datetime.utcnow().isoformat()
        await self._store.save_checkpoint(checkpoint)

        # Create context with restored data
        ctx = ChainContext(
            request_id=run_id,
            initial_data=initial_data,
        )

        # Execute remaining steps
        # Note: This requires DAGExecutor to support skip_steps parameter
        # For now, we'll re-run the full chain but with restored context
        try:
            ctx = await self._executor.execute(
                checkpoint.chain_name,
                ctx,
            )

            success = all(r.success for r in ctx.results)
            checkpoint.finalize(success)

        except Exception as e:
            checkpoint.status = "failed"
            logger.error(f"Resume failed: {e}")
            raise
        finally:
            await self._store.save_checkpoint(checkpoint)

        return {
            "run_id": run_id,
            "chain_name": checkpoint.chain_name,
            "resumed": True,
            "success": checkpoint.status == "completed",
            "status": checkpoint.status,
            "checkpoint": checkpoint.to_dict(),
            "context": ctx.to_dict(),
        }

    async def retry_failed(self, run_id: str) -> dict[str, Any]:
        """
        Re-run only failed steps from a previous run.

        Args:
            run_id: ID of the run with failed steps

        Returns:
            Execution result
        """
        checkpoint = await self._store.load_checkpoint(run_id)
        if checkpoint is None:
            raise ValueError(f"Run not found: {run_id}")

        failed_steps = checkpoint.get_failed_steps()
        if not failed_steps:
            return {
                "run_id": run_id,
                "message": "No failed steps to retry",
                "status": checkpoint.status,
            }

        # This would require DAGExecutor to support running specific steps
        # For now, use resume which re-runs from last checkpoint
        return await self.resume(run_id)

    async def get_partial_output(self, run_id: str) -> dict[str, Any]:
        """
        Get partial outputs from a failed or partial run.

        Args:
            run_id: ID of the run

        Returns:
            Dict with outputs from completed steps
        """
        checkpoint = await self._store.load_checkpoint(run_id)
        if checkpoint is None:
            raise ValueError(f"Run not found: {run_id}")

        outputs = {}
        for step_cp in checkpoint.steps:
            if step_cp.status == "completed" and step_cp.output:
                if isinstance(step_cp.output, dict):
                    outputs[step_cp.step_name] = step_cp.output
                else:
                    outputs[step_cp.step_name] = {"_output": step_cp.output}

        return {
            "run_id": run_id,
            "chain_name": checkpoint.chain_name,
            "status": checkpoint.status,
            "completed_steps": len(checkpoint.get_completed_steps()),
            "total_steps": checkpoint.total_steps,
            "outputs": outputs,
        }

    async def list_resumable(self, chain_name: str | None = None) -> list[dict]:
        """
        List runs that can be resumed.

        Args:
            chain_name: Filter by chain name

        Returns:
            List of resumable run summaries
        """
        runs = await self._store.get_resumable_runs(chain_name) if chain_name else []
        if not chain_name:
            # Get all resumable runs
            all_runs = await self._store.list_runs()
            runs = [r for r in all_runs if r.resumable]

        return [
            {
                "run_id": r.run_id,
                "chain_name": r.chain_name,
                "status": r.status,
                "completed_steps": r.completed_steps,
                "failed_steps": r.failed_steps,
                "total_steps": r.total_steps,
                "created_at": r.created_at,
                "last_completed_step": r.last_completed_step,
            }
            for r in runs
        ]