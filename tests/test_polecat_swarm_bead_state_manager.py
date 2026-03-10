from __future__ import annotations

import pytest

from agentorchestrator.integrations.gastown.bead_state_manager import (
    BeadStateManager,
    CompletionSummary,
    InvalidTransitionError,
)


class _FakeBeadClient:
    def __init__(self) -> None:
        self.data = {
            "bd-1": {
                "id": "bd-1",
                "title": "Demo",
                "status": "open",
                "notes": "",
                "labels": ["feature"],
            }
        }

    def show(self, bead_id: str) -> dict:
        return dict(self.data[bead_id])

    def update(self, bead_id: str, status: str | None = None, notes: str | None = None, **kwargs) -> None:
        if status is not None:
            self.data[bead_id]["status"] = status
        if notes is not None:
            self.data[bead_id]["notes"] = notes

    def claim(self, bead_id: str) -> None:
        self.data[bead_id]["status"] = "in_progress"


def test_valid_state_transitions_and_close_summary() -> None:
    client = _FakeBeadClient()
    manager = BeadStateManager(client)

    manager.claim("bd-1")
    assert client.data["bd-1"]["status"] == "in_progress"

    summary = CompletionSummary(
        bead_id="bd-1",
        bead_title="Demo",
        repo_name="demo-repo",
        pipeline_run=["PRE", "EES", "QES", "RE"],
        duration_seconds=12.4,
        pr_url="https://example.com/pr/1",
        what_was_built="Implemented calculator flow",
        key_decisions=["Used deterministic unit tests"],
        files_changed=["app.py"],
        services_used=["s3"],
        gate_results={"QES": "✅ pass"},
        labels=["feature"],
        commit_sha="abc123",
        trace_id="convoy-1",
    )

    manager.close_with_summary("bd-1", summary)
    assert client.data["bd-1"]["status"] == "done"
    assert "Swarm Completion Summary" in client.data["bd-1"]["notes"]


def test_invalid_transition_raises() -> None:
    client = _FakeBeadClient()
    manager = BeadStateManager(client)

    with pytest.raises(InvalidTransitionError):
        manager.close("bd-1", note="cannot close directly from open")


def test_annotate_appends_notes() -> None:
    client = _FakeBeadClient()
    manager = BeadStateManager(client)

    manager.annotate("bd-1", "note one")
    manager.annotate("bd-1", "note two")

    notes = client.data["bd-1"]["notes"]
    assert "note one" in notes
    assert "note two" in notes
