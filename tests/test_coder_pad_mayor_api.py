"""Unit tests for the Coder Pad Mayor API helpers."""

from __future__ import annotations

import json

from agentorchestrator.integrations.coder_pad_mvp import mayor_api


def test_extract_last_json_object_from_logs():
    logs = "\n".join(
        [
            "warn: startup detail",
            '{"ok": false}',
            '{"chain_success": true, "suite_result": {"status": "success"}}',
        ]
    )
    parsed = mayor_api._extract_last_json_object(logs)
    assert parsed is not None
    assert parsed["chain_success"] is True
    assert parsed["suite_result"]["status"] == "success"


def test_build_job_manifest_contains_bead_context():
    bead = {
        "id": "bead-123",
        "title": "Test bead",
        "description": "Do the thing",
        "priority": 1,
        "labels": ["qa"],
    }
    manifest = mayor_api._build_job_manifest(
        job_name="polecat-bead-123-a1b2c3",
        namespace="default",
        image="polecat-mvp:local",
        bead=bead,
        test_cmd="pytest -q",
        autocommit=False,
    )

    env_entries = manifest["spec"]["template"]["spec"]["containers"][0]["env"]
    env_map = {item["name"]: item["value"] for item in env_entries}

    assert env_map["GASTOWN_BEAD_ID"] == "bead-123"
    assert json.loads(env_map["GASTOWN_BEAD_JSON"])["id"] == "bead-123"
    assert env_map["POLECAT_AUTOCOMMIT"] == "false"

