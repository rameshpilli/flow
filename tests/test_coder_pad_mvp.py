"""Tests for Coder Pad MVP issue-to-code autonomous flow."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
from collections.abc import Iterator

import pytest

from agentorchestrator.core.orchestrator import (
    AgentOrchestrator,
    get_orchestrator,
    set_orchestrator,
)
from examples.coder_pad_mvp.agents import CoderSupervisorRuntime
from examples.coder_pad_mvp.contracts import TaskContext


@pytest.fixture
def isolated_coder_pad_modules() -> Iterator[tuple[AgentOrchestrator, object, object]]:
    """Reload coder-pad modules against a fresh isolated orchestrator."""
    old_orchestrator = get_orchestrator()
    ao = AgentOrchestrator(name="coder-pad-test", isolated=True)
    set_orchestrator(ao)

    import agentorchestrator.integrations.coder_pad_mvp.entrypoint as entrypoint_module
    import examples.coder_pad_mvp.agents as agents_module
    import examples.coder_pad_mvp.pipeline as pipeline_module

    agents_module = importlib.reload(agents_module)
    pipeline_module = importlib.reload(pipeline_module)
    entrypoint_module = importlib.reload(entrypoint_module)

    try:
        yield ao, agents_module, entrypoint_module
    finally:
        set_orchestrator(old_orchestrator)


@pytest.mark.asyncio
async def test_coder_runtime_creates_calculator_files(tmp_path):
    runtime = CoderSupervisorRuntime()
    task = TaskContext(
        task_id="calc-1",
        bead_id=None,
        description="Create calculator app with CLI support",
        repo_path=str(tmp_path),
    )

    output = await runtime.run(task)

    assert "calculator/core.py" in output.changed_files
    assert "tests/test_calculator_core.py" in output.changed_files
    assert "calculator/cli.py" in output.changed_files

    assert (tmp_path / "calculator" / "core.py").exists()
    assert (tmp_path / "calculator" / "__init__.py").exists()
    assert (tmp_path / "tests" / "test_calculator_core.py").exists()


@pytest.mark.asyncio
async def test_coder_pad_entrypoint_end_to_end(tmp_path, monkeypatch, isolated_coder_pad_modules):
    _, _, entrypoint_module = isolated_coder_pad_modules

    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "coderpad@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Coder Pad"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    monkeypatch.setenv("WORKTREE_PATH", str(repo))
    monkeypatch.setenv(
        "GASTOWN_BEAD_JSON",
        json.dumps(
            {
                "id": "calc-bead-1",
                "title": "Calculator bead",
                "description": "Create calculator app with CLI, tests, and docs",
                "labels": ["coder-pad", "calculator"],
                "priority": 1,
            }
        ),
    )
    monkeypatch.delenv("GASTOWN_BEAD_ID", raising=False)
    monkeypatch.setenv("POLECAT_TEST_CMD", "pytest tests/test_calculator_core.py -q")
    monkeypatch.setenv("GASTOWN_OUTPUT_DIR", str(repo / ".gastown"))
    monkeypatch.setenv("POLECAT_AUTOCOMMIT", "false")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))

    outcome = await entrypoint_module.run_coder_pad_mvp()

    assert outcome["chain_success"] is True
    assert outcome["suite_result"]["status"] == "success"

    assert (repo / "calculator" / "core.py").exists()
    assert (repo / "tests" / "test_calculator_core.py").exists()
    assert (repo / "docs" / "api.md").exists()
    assert (repo / "docs" / "release_notes.md").exists()
    assert (repo / "docs" / "qa_report.md").exists()
    assert (repo / ".gastown" / "result.json").exists()
    assert (repo / ".gastown" / "evidence.md").exists()


def test_load_task_requires_bead_context(monkeypatch, isolated_coder_pad_modules):
    _, _, entrypoint_module = isolated_coder_pad_modules

    monkeypatch.delenv("GASTOWN_BEAD_JSON", raising=False)
    monkeypatch.delenv("GASTOWN_BEAD_ID", raising=False)

    with pytest.raises(RuntimeError, match="No bead context found"):
        entrypoint_module.load_task_from_env()
