from __future__ import annotations

from agentorchestrator.integrations.gastown import mayor_api


def setup_function() -> None:
    mayor_api._convoy_cache.clear()


def test_initialize_convoy_cache_sets_pending_experts() -> None:
    class _Expert:
        def __init__(self, role: str, model: str, is_custom: bool = False):
            self.role = role
            self.model = model
            self.is_custom = is_custom

    pipeline = [_Expert("PRE", "claude-sonnet-4-5"), _Expert("EES", "gpt-4o")]

    mayor_api._initialize_convoy_cache(
        convoy_id="convoy-1",
        repo="demo",
        bead_id="bd-1",
        commit_sha="abc123",
        configmap_name="swarm-config-bd-1",
        pipeline=pipeline,
        sub_bead_ids={"PRE": "bd-pre", "EES": "bd-ees"},
    )

    cache = mayor_api._convoy_cache["convoy-1"]
    assert cache["status"] == "running"
    assert set(cache["experts"].keys()) == {"PRE", "EES"}
    assert cache["experts"]["PRE"]["status"] == "pending"
    assert cache["experts"]["EES"]["bead_id"] == "bd-ees"


def test_update_convoy_cache_tracks_expert_state_changes() -> None:
    mayor_api._convoy_cache["convoy-2"] = {
        "convoy_id": "convoy-2",
        "repo": "demo",
        "status": "running",
        "experts": {},
    }

    mayor_api._update_convoy_cache(
        {
            "type": "log_event",
            "trace_id": "convoy-2",
            "payload": {
                "event": "expert_started",
                "role": "QES",
                "model": "claude-sonnet-4-5",
                "ts": 1.0,
            },
        }
    )

    mayor_api._update_convoy_cache(
        {
            "type": "log_event",
            "trace_id": "convoy-2",
            "payload": {
                "event": "expert_completed",
                "role": "QES",
                "status": "success",
                "elapsed_s": 42.7,
                "gate_scores": {"tests": 1.0},
            },
        }
    )

    mayor_api._update_convoy_cache(
        {
            "type": "log_event",
            "trace_id": "convoy-2",
            "payload": {
                "event": "convoy_complete",
                "role": "",
            },
        }
    )

    qes = mayor_api._convoy_cache["convoy-2"]["experts"]["QES"]
    assert qes["status"] == "success"
    assert qes["elapsed_s"] == 42.7
    assert qes["gate_scores"] == {"tests": 1.0}
    assert mayor_api._convoy_cache["convoy-2"]["status"] == "complete"
