"""Integration and smoke tests for the Gastown MVP Polecat flow."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from agentorchestrator.core.orchestrator import (
    AgentOrchestrator,
    get_orchestrator,
    set_orchestrator,
)


@pytest.fixture
def isolated_mvp_modules() -> Iterator[tuple[AgentOrchestrator, object, object]]:
    """Reload MVP modules against a fresh isolated orchestrator."""
    old_orchestrator = get_orchestrator()
    ao = AgentOrchestrator(name="mvp-integration-test", isolated=True)
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


def _init_fixture_repo(repo_path: Path) -> None:
    repo_path.mkdir(parents=True, exist_ok=True)
    (repo_path / "test_fixture.py").write_text(
        "def test_fixture_passes():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "polecat@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Polecat MVP"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )


def _create_mock_bd_cli(bin_dir: Path, log_path: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script_path = bin_dir / "bd"
    script = f"""#!/usr/bin/env bash
set -euo pipefail

echo "$@" >> "{log_path}"

if [[ "${{2:-}}" == "show" ]]; then
  bead_id="${{3:-unknown}}"
  echo "{{\"id\":\"${{bead_id}}\",\"description\":\"Fix behavior in agentorchestrator/core/orchestrator.py\",\"labels\":[\"qa\",\"docs\"],\"priority\":1}}"
fi
"""
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o755)


@pytest.mark.asyncio
async def test_mvp_flow_end_to_end_with_mocked_bd_cli(monkeypatch, tmp_path, isolated_mvp_modules):
    _, _, entrypoint_module = isolated_mvp_modules

    repo = tmp_path / "repo"
    _init_fixture_repo(repo)

    bd_log = tmp_path / "bd.log"
    mock_bin = tmp_path / "bin"
    _create_mock_bd_cli(mock_bin, bd_log)

    monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("WORKTREE_PATH", str(repo))
    monkeypatch.setenv("GASTOWN_BEAD_ID", "BEAD-900")
    monkeypatch.delenv("GASTOWN_TASK_JSON", raising=False)
    monkeypatch.setenv("DEEP_RESEARCH_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("POLECAT_TEST_CMD", "python -c \"print('integration')\"")
    monkeypatch.setenv("POLECAT_AUTOCOMMIT", "false")
    monkeypatch.setenv("GASTOWN_OUTPUT_DIR", str(repo / ".gastown"))

    outcome = await entrypoint_module.run_polecat_mvp()

    assert outcome["chain_success"] is True
    assert outcome["suite_result"]["status"] == "success"

    result_path = Path(outcome["result_path"])
    evidence_path = Path(outcome["evidence_path"])
    assert result_path.exists()
    assert evidence_path.exists()

    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert result_payload["task_id"] == "BEAD-900"
    assert "warnings" in result_payload
    assert any("Deep research unavailable" in warning for warning in result_payload["warnings"])

    evidence_text = evidence_path.read_text(encoding="utf-8")
    assert "Polecat MVP Evidence" in evidence_text
    assert "Exit code: `0`" in evidence_text

    bd_calls = bd_log.read_text(encoding="utf-8")
    assert "--sandbox show BEAD-900" in bd_calls
    assert "--sandbox update BEAD-900 --status completed" in bd_calls
    assert "--sandbox export" in bd_calls


def test_smoke_entrypoint_main_generates_result_artifacts(monkeypatch, tmp_path, isolated_mvp_modules):
    _, _, entrypoint_module = isolated_mvp_modules

    repo = tmp_path / "repo-smoke"
    _init_fixture_repo(repo)

    monkeypatch.setenv("WORKTREE_PATH", str(repo))
    monkeypatch.setenv(
        "GASTOWN_TASK_JSON",
        json.dumps(
            {
                "task_id": "smoke-1",
                "description": "Smoke run for docs/gastown_mvp.md",
            }
        ),
    )
    monkeypatch.delenv("GASTOWN_BEAD_ID", raising=False)
    monkeypatch.delenv("DEEP_RESEARCH_BASE_URL", raising=False)
    monkeypatch.setenv("POLECAT_TEST_CMD", "python -c \"print('smoke')\"")
    monkeypatch.setenv("POLECAT_AUTOCOMMIT", "false")
    monkeypatch.setenv("GASTOWN_OUTPUT_DIR", str(repo / ".gastown"))

    rc = entrypoint_module.main()
    assert rc == 0

    result_path = repo / ".gastown" / "result.json"
    evidence_path = repo / ".gastown" / "evidence.md"
    assert result_path.exists()
    assert evidence_path.exists()

    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert result_payload["status"] == "success"
