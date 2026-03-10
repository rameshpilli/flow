"""Polecat-compatible runtime entrypoint for Gastown MVP."""

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
        parsed = _parse_json(result.stdout)
        if parsed:
            return parsed
    return None


def load_task_from_env() -> dict[str, Any]:
    """Resolve task payload from env vars with bead fallback."""
    worktree_path = os.getenv("WORKTREE_PATH", "/workspace")
    task_json = os.getenv("GASTOWN_TASK_JSON", "").strip()
    bead_id = os.getenv("GASTOWN_BEAD_ID", "").strip() or None

    if task_json:
        parsed = _parse_json(task_json)
        if parsed:
            task = dict(parsed)
            task.setdefault("bead_id", bead_id)
            task.setdefault("repo_path", worktree_path)
            task.setdefault("task_id", task.get("id") or bead_id or "task-local")
            task.setdefault("description", "Task from GASTOWN_TASK_JSON")
            task.setdefault("labels", [])
            task.setdefault("priority", 2)
            return task

    bead_data = _maybe_load_bead(bead_id) if bead_id else None
    if bead_data:
        task = {
            "task_id": bead_data.get("id") or bead_id,
            "bead_id": bead_id,
            "description": bead_data.get("description") or "Task from bead",
            "repo_path": worktree_path,
            "labels": bead_data.get("labels", []),
            "priority": bead_data.get("priority", 2),
            "raw": bead_data,
        }
        return task

    return {
        "task_id": bead_id or "task-local",
        "bead_id": bead_id,
        "description": os.getenv("GASTOWN_TASK_DESC", "Task from environment fallback"),
        "repo_path": worktree_path,
        "labels": [],
        "priority": 2,
    }


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

    msg = f"Polecat MVP automated execution for {task_id}"
    commit = _run_cmd(["git", "commit", "-m", msg], cwd=worktree_path)
    return {
        "enabled": True,
        "committed": commit.returncode == 0,
        "message": commit.stdout.strip() or commit.stderr.strip(),
        "branch": branch,
    }


def maybe_update_bead(bead_id: str | None, result_payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort bead updates. Never fail the runtime on bead command errors."""
    if not bead_id:
        return {"updated": False, "reason": "no bead id"}
    if shutil.which("bd") is None:
        return {"updated": False, "reason": "bd not installed"}

    status = "completed" if result_payload.get("status") == "success" else "failed"
    summary = result_payload.get("summary", "Polecat MVP execution finished")

    cmds = [
        ["bd", "--sandbox", "update", bead_id, "--status", status],
        ["bd", "--sandbox", "update", bead_id, "--append-notes", summary],
        ["bd", "--sandbox", "export"],
    ]

    outcomes: list[dict[str, Any]] = []
    for cmd in cmds:
        result = _run_cmd(cmd)
        outcomes.append(
            {
                "cmd": cmd,
                "returncode": result.returncode,
                "stdout": result.stdout[-1000:],
                "stderr": result.stderr[-1000:],
            }
        )

    return {
        "updated": any(item["returncode"] == 0 for item in outcomes),
        "outcomes": outcomes,
    }


def _build_runtime_orchestrator() -> tuple[AgentOrchestrator, str, Any]:
    """
    Build an isolated orchestrator for MVP runtime execution.

    Entrypoint runtime should not depend on external Redis connectivity.
    We force an in-memory event bus and reload the MVP suite registration
    modules against this orchestrator.
    """
    ao = AgentOrchestrator(
        name="gastown_mvp_runtime",
        isolated=True,
        event_bus=InMemoryEventBus(),
    )
    set_orchestrator(ao)

    import examples.gastown_mvp.agents as agents_module
    import examples.gastown_mvp.pipeline as pipeline_module

    importlib.reload(agents_module)
    pipeline_module = importlib.reload(pipeline_module)
    return ao, pipeline_module.CHAIN_NAME, pipeline_module.build_initial_data


async def run_polecat_mvp(task_override: dict[str, Any] | None = None) -> dict[str, Any]:
    task = dict(task_override or load_task_from_env())
    worktree_path = os.getenv("WORKTREE_PATH", "/workspace")
    deep_research_base_url = os.getenv("DEEP_RESEARCH_BASE_URL", "")
    test_cmd = os.getenv("POLECAT_TEST_CMD", "pytest -q")
    output_dir = os.getenv("GASTOWN_OUTPUT_DIR", "/workspace/.gastown")

    ao, chain_name, build_initial_data = _build_runtime_orchestrator()
    initial_data = build_initial_data(
        task=task,
        worktree_path=worktree_path,
        deep_research_base_url=deep_research_base_url,
        test_cmd=test_cmd,
    )

    result = await ao.launch(chain_name, data=initial_data)
    ctx_data = result.get("context", {}).get("data", {})

    suite_result = ctx_data.get("suite_result") or {
        "status": "failed" if not result.get("success") else "success",
        "task_id": task.get("task_id", "task-local"),
        "summary": "MVP flow completed without suite_result payload",
        "qa": {},
        "docs": {},
        "execution": {},
        "warnings": [],
    }
    evidence_md = ctx_data.get("evidence_markdown") or "# Polecat MVP Evidence\n\nNo evidence payload generated."

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
        outcome = asyncio.run(run_polecat_mvp())
        print(json.dumps(outcome, indent=2))
        suite_status = outcome.get("suite_result", {}).get("status", "failed")
        return 0 if suite_status == "success" else 1
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
