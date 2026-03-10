"""Polecat-compatible runtime entrypoint for Coder Pad MVP."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from agentorchestrator.core.event_bus import InMemoryEventBus
from agentorchestrator.core.orchestrator import AgentOrchestrator, set_orchestrator


def _run_cmd(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _parse_json(raw: str) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _parse_issue_payload(raw: str) -> dict[str, Any] | None:
    """Parse bead payload JSON from env/CLI output.

    Some `bd --json` commands return a single object, while others return
    a list with one object. We normalize both shapes here.
    """
    try:
        data = json.loads(raw)
    except Exception:
        return None

    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _maybe_load_bead(bead_id: str) -> dict[str, Any] | None:
    if not bead_id:
        return None
    if shutil.which("bd") is None:
        return None

    candidates = [
        ["bd", "--sandbox", "show", bead_id, "--json"],
        ["bd", "--sandbox", "show", bead_id],
    ]
    for cmd in candidates:
        result = _run_cmd(cmd)
        if result.returncode != 0 or not result.stdout.strip():
            continue
        parsed = _parse_issue_payload(result.stdout)
        if parsed:
            return parsed
    return None


def load_task_from_env() -> dict[str, Any]:
    """Resolve task payload strictly from bead context."""
    worktree_path = os.getenv("WORKTREE_PATH", "/workspace")
    bead_json = os.getenv("GASTOWN_BEAD_JSON", "").strip()
    bead_id = os.getenv("GASTOWN_BEAD_ID", "").strip() or None

    bead_data: dict[str, Any] | None = None
    if bead_json:
        bead_data = _parse_issue_payload(bead_json)

    if bead_data is None and bead_id:
        bead_data = _maybe_load_bead(bead_id)

    if bead_data is not None:
        resolved_bead_id = bead_data.get("id") or bead_id
        return {
            "task_id": resolved_bead_id,
            "bead_id": resolved_bead_id,
            "description": bead_data.get("description") or "Create calculator app",
            "repo_path": worktree_path,
            "labels": bead_data.get("labels", []),
            "priority": bead_data.get("priority", 2),
            "title": bead_data.get("title"),
            "raw": bead_data,
        }

    raise RuntimeError(
        "No bead context found. Provide GASTOWN_BEAD_JSON or GASTOWN_BEAD_ID."
    )


def write_outputs(output_dir: str, result_payload: dict[str, Any], evidence_md: str) -> tuple[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    result_path = root / "result.json"
    evidence_path = root / "evidence.md"

    result_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
    evidence_path.write_text(evidence_md, encoding="utf-8")
    return str(result_path), str(evidence_path)


def maybe_autocommit(worktree_path: str, task_id: str) -> dict[str, Any]:
    """Optional deterministic git commit for autonomous mode."""
    if not _env_bool("POLECAT_AUTOCOMMIT", False):
        return {"enabled": False, "committed": False, "message": "autocommit disabled"}

    if shutil.which("git") is None:
        return {"enabled": True, "committed": False, "message": "git not available"}

    status = _run_cmd(["git", "status", "--porcelain"], cwd=worktree_path)
    if status.returncode != 0:
        return {
            "enabled": True,
            "committed": False,
            "message": f"git status failed: {status.stderr.strip()}",
        }

    if not status.stdout.strip():
        return {"enabled": True, "committed": False, "message": "no changes to commit"}

    branch = f"polecat/{task_id}".replace(" ", "-")
    _run_cmd(["git", "checkout", "-B", branch], cwd=worktree_path)
    _run_cmd(["git", "add", "-A"], cwd=worktree_path)

    cached = _run_cmd(["git", "diff", "--cached", "--quiet"], cwd=worktree_path)
    if cached.returncode == 0:
        return {"enabled": True, "committed": False, "message": "no staged changes"}

    msg = f"Coder Pad MVP automated execution for {task_id}"
    commit = _run_cmd(["git", "commit", "-m", msg], cwd=worktree_path)
    return {
        "enabled": True,
        "committed": commit.returncode == 0,
        "message": commit.stdout.strip() or commit.stderr.strip(),
        "branch": branch,
    }


def maybe_update_bead(bead_id: str | None, result_payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort bead updates. Never fail runtime on bead command errors."""
    if not bead_id:
        return {"updated": False, "reason": "no bead id"}
    if shutil.which("bd") is None:
        return {"updated": False, "reason": "bd not installed"}

    status = "closed" if result_payload.get("status") == "success" else "open"
    summary = result_payload.get("summary", "Coder Pad MVP execution finished")

    cmds = [
        ["bd", "--sandbox", "update", bead_id, "--status", status],
        ["bd", "--sandbox", "update", bead_id, "--notes", summary],
        ["bd", "--sandbox", "export"],
    ]

    outcomes: list[dict[str, Any]] = []
    for cmd in cmds:
        result = _run_cmd(cmd)
        combined = (result.stdout + "\n" + result.stderr).strip()
        ok = result.returncode == 0 and "Error updating" not in combined
        outcomes.append(
            {
                "cmd": cmd,
                "returncode": result.returncode,
                "ok": ok,
                "stdout": result.stdout[-1000:],
                "stderr": result.stderr[-1000:],
            }
        )

    updated = all(item.get("ok") for item in outcomes[:2]) if len(outcomes) >= 2 else False
    return {
        "updated": updated,
        "outcomes": outcomes,
    }


def _build_runtime_orchestrator() -> tuple[AgentOrchestrator, str, Any]:
    """Build isolated orchestrator for Coder Pad runtime execution."""
    ao = AgentOrchestrator(
        name="coder_pad_mvp_runtime",
        isolated=True,
        event_bus=InMemoryEventBus(),
    )
    set_orchestrator(ao)

    import examples.coder_pad_mvp.agents as agents_module
    import examples.coder_pad_mvp.pipeline as pipeline_module

    importlib.reload(agents_module)
    pipeline_module = importlib.reload(pipeline_module)
    return ao, pipeline_module.CHAIN_NAME, pipeline_module.build_initial_data


async def run_coder_pad_mvp(task_override: dict[str, Any] | None = None) -> dict[str, Any]:
    task = dict(task_override or load_task_from_env())
    worktree_path = os.getenv("WORKTREE_PATH", "/workspace")
    test_cmd = os.getenv("POLECAT_TEST_CMD", "pytest -q")
    output_dir = os.getenv("GASTOWN_OUTPUT_DIR", "/workspace/.gastown")

    ao, chain_name, build_initial_data = _build_runtime_orchestrator()
    initial_data = build_initial_data(
        task=task,
        worktree_path=worktree_path,
        test_cmd=test_cmd,
    )

    result = await ao.launch(chain_name, data=initial_data)
    ctx_data = result.get("context", {}).get("data", {})

    suite_result = ctx_data.get("suite_result") or {
        "status": "failed" if not result.get("success") else "success",
        "task_id": task.get("task_id", "task-local"),
        "summary": "Coder Pad flow completed without suite_result payload",
        "coder": {},
        "qa": {},
        "docs": {},
        "execution": {},
        "warnings": [],
    }
    evidence_md = (
        ctx_data.get("evidence_markdown")
        or "# Coder Pad MVP Evidence\n\nNo evidence payload generated."
    )

    result_path, evidence_path = write_outputs(output_dir, suite_result, evidence_md)
    autocommit_result = maybe_autocommit(worktree_path, str(task.get("task_id", "task-local")))
    bead_result = maybe_update_bead(task.get("bead_id"), suite_result)

    return {
        "chain_success": bool(result.get("success")),
        "suite_result": suite_result,
        "result_path": result_path,
        "evidence_path": evidence_path,
        "autocommit": autocommit_result,
        "bead": bead_result,
    }


def main() -> int:
    try:
        outcome = asyncio.run(run_coder_pad_mvp())
        print(json.dumps(outcome, indent=2))
        suite_status = outcome.get("suite_result", {}).get("status", "failed")
        return 0 if suite_status == "success" else 1
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
