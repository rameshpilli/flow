from __future__ import annotations

from pathlib import Path

from agentorchestrator.integrations.gastown.configmap_store import (
    delete_swarm_configmap,
    read_swarm_configmap,
    write_swarm_configmap,
)
from agentorchestrator.integrations.gastown.swarm_config import ExpertConfig, SwarmConfig


def test_local_configmap_fallback_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SWARM_CONFIG_FORCE_LOCAL", "true")
    monkeypatch.setenv("SWARM_CONFIG_LOCAL_STORE", str(tmp_path))

    config = SwarmConfig(
        repo_name="demo",
        repo_url="git@github.com:org/demo.git",
        commit_sha="abc123",
        pipeline=[ExpertConfig(role="PRE", model="claude-sonnet-4-5")],
        trace_id="convoy-1",
    )

    name = write_swarm_configmap("bd-1", config)
    loaded = read_swarm_configmap(name)

    assert loaded.repo_name == "demo"
    assert loaded.commit_sha == "abc123"
    assert loaded.pipeline[0].role == "PRE"

    delete_swarm_configmap(name)
    assert not (tmp_path / f"{name}.json").exists()
