"""Runtime and handoff tests for Gastown MVP entrypoint and supervisor flow."""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator

import pytest

from agentorchestrator.core.orchestrator import (
    AgentOrchestrator,
    get_orchestrator,
    set_orchestrator,
)
from examples.gastown_mvp.agents import build_runtime_supervisors
from examples.gastown_mvp.contracts import QAOutput, ResearchBrief, TaskContext


@pytest.fixture
def isolated_mvp_modules() -> Iterator[tuple[AgentOrchestrator, object, object]]:
    """Reload MVP modules against a fresh isolated orchestrator."""
    old_orchestrator = get_orchestrator()
    ao = AgentOrchestrator(name="mvp-runtime-test", isolated=True)
    set_orchestrator(ao)

    import agentorchestrator.integrations.gastown_mvp.entrypoint as entrypoint_module
    import examples.gastown_mvp.agents as agents_module
    import examples.gastown_mvp.pipeline as pipeline_module

    importlib.reload(agents_module)
    pipeline_module = importlib.reload(pipeline_module)
    entrypoint_module = importlib.reload(entrypoint_module)

    try:
        yield ao, pipeline_module, entrypoint_module
    finally:
        set_orchestrator(old_orchestrator)


def test_load_task_prefers_gastown_task_json(monkeypatch, isolated_mvp_modules):
    _, _, entrypoint_module = isolated_mvp_modules

    monkeypatch.setenv("WORKTREE_PATH", "/tmp/worktree")
    monkeypatch.setenv("GASTOWN_BEAD_ID", "BEAD-123")
    monkeypatch.setenv(
        "GASTOWN_TASK_JSON",
        json.dumps(
            {
                "id": "task-json-1",
                "description": "Fix docs for README.md",
                "labels": ["docs"],
                "priority": 1,
            }
        ),
    )

    task = entrypoint_module.load_task_from_env()

    assert task["task_id"] == "task-json-1"
    assert task["bead_id"] == "BEAD-123"
    assert task["repo_path"] == "/tmp/worktree"
    assert task["priority"] == 1


def test_load_task_falls_back_to_bead_payload(monkeypatch, isolated_mvp_modules):
    _, _, entrypoint_module = isolated_mvp_modules

    monkeypatch.setenv("WORKTREE_PATH", "/tmp/worktree")
    monkeypatch.setenv("GASTOWN_BEAD_ID", "BEAD-777")
    monkeypatch.delenv("GASTOWN_TASK_JSON", raising=False)

    monkeypatch.setattr(
        entrypoint_module,
        "_maybe_load_bead",
        lambda bead_id: {
            "id": bead_id,
            "description": "Implement QA docs handoff",
            "labels": ["qa", "docs"],
            "priority": 0,
        },
    )

    task = entrypoint_module.load_task_from_env()

    assert task["task_id"] == "BEAD-777"
    assert task["bead_id"] == "BEAD-777"
    assert task["description"] == "Implement QA docs handoff"
    assert task["labels"] == ["qa", "docs"]
    assert task["priority"] == 0


def test_bead_update_gracefully_skips_when_bd_unavailable(monkeypatch, isolated_mvp_modules):
    _, _, entrypoint_module = isolated_mvp_modules

    monkeypatch.setattr(entrypoint_module.shutil, "which", lambda _: None)
    outcome = entrypoint_module.maybe_update_bead(
        "BEAD-101",
        {"status": "success", "summary": "done"},
    )

    assert outcome["updated"] is False
    assert outcome["reason"] == "bd not installed"


@pytest.mark.asyncio
async def test_qa_docs_explicit_handoff_payload_shape():
    qa_runtime, docs_runtime, _ = build_runtime_supervisors()

    task = TaskContext(
        task_id="task-001",
        bead_id=None,
        description="Update behavior in agentorchestrator/core/orchestrator.py",
        repo_path="/tmp/worktree",
    )
    brief = ResearchBrief(
        summary="Research summary",
        impacted_files=["agentorchestrator/core/orchestrator.py"],
        risks=["Unexpected behavior regression"],
    )

    qa_output = await qa_runtime.run(task, brief)
    assert qa_output.handoff_requests
    qa_handoff = qa_output.handoff_requests[0]
    assert qa_handoff["target"] == "documentation"
    assert qa_handoff["response"]["ok"] is True
    assert "accepted_items" in qa_handoff["response"]

    docs_output = await docs_runtime.run(task, brief, QAOutput())
    assert docs_output.acknowledgements
    docs_clarification = docs_output.acknowledgements[0]
    assert docs_clarification["target"] == "qa"
    assert docs_clarification["response"]["ok"] is True
