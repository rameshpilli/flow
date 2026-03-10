from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentorchestrator.integrations.gastown.agent_registry import AgentRegistry
from agentorchestrator.integrations.gastown.swarm_config import (
    SwarmConfigError,
    SwarmConfigLoader,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_version_guard_rejects_unsupported_version(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_json(repo / ".swarm" / "swarm.yaml", {"version": 2})

    loader = SwarmConfigLoader(agent_registry=AgentRegistry(path=str(tmp_path / "registry")))
    with pytest.raises(SwarmConfigError, match="Unsupported swarm.yaml version"):
        loader.load(str(repo), "git@github.com:org/demo.git")


def test_loader_merges_defaults_and_inserts_custom_agents_in_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".swarm" / "agents" / "sec").mkdir(parents=True, exist_ok=True)
    (repo / ".swarm" / "agents" / "perf").mkdir(parents=True, exist_ok=True)
    (repo / ".swarm" / "agents" / "sec" / "pipeline.py").write_text("def run(**kwargs):\n    return {}\n")
    (repo / ".swarm" / "agents" / "perf" / "pipeline.py").write_text("def run(**kwargs):\n    return {}\n")
    (repo / ".swarm" / "skills").mkdir(parents=True, exist_ok=True)
    (repo / ".swarm" / "skills" / "repo-skill.md").write_text("# skill\n", encoding="utf-8")

    _write_json(
        repo / ".swarm" / "swarm.yaml",
        {
            "version": 1,
            "repo": {"name": "demo", "test_command": "pytest -q", "docs_path": "docs/"},
            "services": ["s3"],
            "experts": {
                "pipeline": [
                    {"role": "QES", "model": "claude-sonnet-4-5"},
                    {"role": "DE", "enabled": False},
                ]
            },
            "skills": {
                "platform": ["missing-skill"],
                "per_role": {"EES": ["repo-skill"]},
            },
            "custom_agents": [
                {
                    "role": "SEC_REVIEW",
                    "insert_after": "EES",
                    "pipeline": ".swarm/agents/sec/pipeline.py",
                    "model": "claude-sonnet-4-5",
                },
                {
                    "role": "PERF_REVIEW",
                    "insert_after": "EES",
                    "pipeline": ".swarm/agents/perf/pipeline.py",
                    "model": "claude-sonnet-4-5",
                },
            ],
        },
    )

    loader = SwarmConfigLoader(agent_registry=AgentRegistry(path=str(tmp_path / "registry")))
    config = loader.load(str(repo), "git@github.com:org/demo.git", commit_sha="abc123", trace_id="convoy-1")

    assert config.repo_name == "demo"
    assert config.test_command == "pytest -q"
    assert config.commit_sha == "abc123"
    assert config.services == ["s3"]

    roles = [entry.role for entry in config.pipeline]
    assert roles == ["PRE", "EES", "SEC_REVIEW", "PERF_REVIEW", "QES", "DE", "RE"]

    qes = next(entry for entry in config.pipeline if entry.role == "QES")
    assert qes.model == "claude-sonnet-4-5"

    de = next(entry for entry in config.pipeline if entry.role == "DE")
    assert de.enabled is False

    assert config.skills.for_role("EES")[-1].endswith("repo-skill.md")
    assert "missing-skill" in config.skills.warnings


def test_loader_rejects_custom_agent_path_outside_allowed_roots(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside.py"
    outside.write_text("print('x')\n", encoding="utf-8")

    _write_json(
        repo / ".swarm" / "swarm.yaml",
        {
            "version": 1,
            "custom_agents": [
                {
                    "role": "SEC_REVIEW",
                    "insert_after": "EES",
                    "pipeline": str(outside),
                    "model": "claude-sonnet-4-5",
                }
            ],
        },
    )

    loader = SwarmConfigLoader(agent_registry=AgentRegistry(path=str(tmp_path / "registry")))
    with pytest.raises(SwarmConfigError, match="outside allowed roots"):
        loader.load(str(repo), "git@github.com:org/demo.git")
