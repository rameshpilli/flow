"""
Tests for Run Store (Resumability)
===================================

Tests checkpoint storage and resumable execution.
"""

import asyncio
import os
import tempfile
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

try:
    from agentorchestrator.core.run_store import (
        RunStore,
        InMemoryRunStore,
        FileRunStore,
        RunCheckpoint,
        StepStatus,
        ResumableChainRunner,
    )
    from agentorchestrator.core.dag import DAGExecutor
    RUN_STORE_AVAILABLE = True
except ImportError:
    RUN_STORE_AVAILABLE = False


pytestmark = pytest.mark.skipif(not RUN_STORE_AVAILABLE, reason="Run store not available")


class TestInMemoryRunStore:
    """Tests for in-memory checkpoint storage."""

    @pytest.mark.asyncio
    async def test_save_and_load_checkpoint(self):
        """Test saving and loading checkpoints."""
        store = InMemoryRunStore()
        
        checkpoint = RunCheckpoint(
            run_id="test-run-1",
            chain_name="test_chain",
            status="running",
            step_statuses={"step1": StepStatus.COMPLETED},
            context_data={"key": "value"},
            created_at=datetime.utcnow(),
        )
        
        await store.save_checkpoint(checkpoint)
        loaded = await store.load_checkpoint("test-run-1")
        
        assert loaded is not None
        assert loaded.run_id == "test-run-1"
        assert loaded.chain_name == "test_chain"
        assert loaded.context_data == {"key": "value"}

    @pytest.mark.asyncio
    async def test_load_nonexistent_checkpoint(self):
        """Test loading nonexistent checkpoint returns None."""
        store = InMemoryRunStore()
        
        loaded = await store.load_checkpoint("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_checkpoint(self):
        """Test deleting checkpoints."""
        store = InMemoryRunStore()
        
        checkpoint = RunCheckpoint(
            run_id="test-run-1",
            chain_name="test_chain",
            status="completed",
        )
        
        await store.save_checkpoint(checkpoint)
        assert await store.load_checkpoint("test-run-1") is not None
        
        result = await store.delete_checkpoint("test-run-1")
        assert result is True
        assert await store.load_checkpoint("test-run-1") is None

    @pytest.mark.asyncio
    async def test_list_runs_by_status(self):
        """Test listing runs filtered by status."""
        store = InMemoryRunStore()
        
        # Create multiple checkpoints
        for i, status in enumerate(["completed", "failed", "completed"]):
            checkpoint = RunCheckpoint(
                run_id=f"run-{i}",
                chain_name="test_chain",
                status=status,
            )
            await store.save_checkpoint(checkpoint)
        
        # Filter by status
        failed = await store.list_runs(status="failed")
        assert len(failed) == 1
        assert failed[0].run_id == "run-1"

    @pytest.mark.asyncio
    async def test_list_runs_by_chain(self):
        """Test listing runs filtered by chain name."""
        store = InMemoryRunStore()
        
        # Create checkpoints for different chains
        for i, chain in enumerate(["chain_a", "chain_b", "chain_a"]):
            checkpoint = RunCheckpoint(
                run_id=f"run-{i}",
                chain_name=chain,
                status="completed",
            )
            await store.save_checkpoint(checkpoint)
        
        # Filter by chain
        chain_a_runs = await store.list_runs(chain_name="chain_a")
        assert len(chain_a_runs) == 2


class TestFileRunStore:
    """Tests for file-based checkpoint storage."""

    @pytest.mark.asyncio
    async def test_save_and_load_checkpoint(self):
        """Test file-based checkpoint persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileRunStore(tmpdir)
            
            checkpoint = RunCheckpoint(
                run_id="test-run-1",
                chain_name="test_chain",
                status="running",
                context_data={"key": "value"},
            )
            
            await store.save_checkpoint(checkpoint)
            
            # Verify file exists
            checkpoint_path = os.path.join(tmpdir, "test-run-1.json")
            assert os.path.exists(checkpoint_path)
            
            # Load and verify
            loaded = await store.load_checkpoint("test-run-1")
            assert loaded is not None
            assert loaded.context_data == {"key": "value"}

    @pytest.mark.asyncio
    async def test_persistence_across_instances(self):
        """Test checkpoints persist across store instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save with first instance
            store1 = FileRunStore(tmpdir)
            checkpoint = RunCheckpoint(
                run_id="persistent-run",
                chain_name="test_chain",
                status="partial",
            )
            await store1.save_checkpoint(checkpoint)
            
            # Load with new instance
            store2 = FileRunStore(tmpdir)
            loaded = await store2.load_checkpoint("persistent-run")
            
            assert loaded is not None
            assert loaded.run_id == "persistent-run"


class TestResumableChainRunner:
    """Tests for resumable chain execution."""

    @pytest.mark.asyncio
    async def test_creates_checkpoint_on_run(self):
        """Test checkpoint is created when running a chain."""
        store = InMemoryRunStore()
        
        # Mock executor
        mock_executor = MagicMock(spec=DAGExecutor)
        mock_executor.builder.chain_registry.get_spec = MagicMock(return_value=MagicMock(steps=["step1"]))
        mock_executor.execute = AsyncMock()
        
        runner = ResumableChainRunner(store=store, executor=mock_executor)
        
        await runner.run(
            chain_name="test_chain",
            initial_data={"input": "data"},
            run_id="test-run-1",
        )
        
        # Checkpoint should exist
        checkpoint = await store.load_checkpoint("test-run-1")
        assert checkpoint is not None

    @pytest.mark.asyncio
    async def test_resume_skips_completed_steps(self):
        """Test resume skips already completed steps."""
        store = InMemoryRunStore()
        
        # Create checkpoint with completed step
        checkpoint = RunCheckpoint(
            run_id="resumable-run",
            chain_name="test_chain",
            status="partial",
            step_statuses={"step1": StepStatus.COMPLETED},
            step_outputs={"step1": {"result": "done"}},
        )
        await store.save_checkpoint(checkpoint)
        
        # Mock executor
        mock_executor = MagicMock(spec=DAGExecutor)
        mock_executor.builder.chain_registry.get_spec = MagicMock(
            return_value=MagicMock(steps=["step1", "step2"])
        )
        mock_executor.execute = AsyncMock()
        
        runner = ResumableChainRunner(store=store, executor=mock_executor)
        
        result = await runner.resume("resumable-run", skip_completed=True)
        
        # Should have resumed
        assert result is not None


class TestRunCheckpoint:
    """Tests for checkpoint data structure."""

    def test_step_status_enum(self):
        """Test step status enumeration."""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"

    def test_checkpoint_defaults(self):
        """Test checkpoint default values."""
        checkpoint = RunCheckpoint(
            run_id="test",
            chain_name="chain",
            status="running",
        )
        
        assert checkpoint.step_statuses == {}
        assert checkpoint.step_outputs == {}
        assert checkpoint.context_data == {}
        assert checkpoint.error is None
