"""Minimal Mayor-style API for bead-first dispatch to Polecat jobs.

This service is intentionally thin:
- Uses `bd` as source of truth for bead creation/read/update.
- Dispatches a Kubernetes Job per bead (Polecat-compatible runtime).
- Optionally waits for completion and writes bead status/notes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def _run_cmd(
    cmd: list[str],
    *,
    cwd: str | None = None,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        input=stdin_text,
        capture_output=True,
        check=False,
    )


def _parse_issue_payload(raw: str) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
    except Exception:
        return None

    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _extract_last_json_object(raw: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for idx in range(len(raw) - 1, -1, -1):
        if raw[idx] != "{":
            continue
        snippet = raw[idx:]
        try:
            obj, end = decoder.raw_decode(snippet)
        except Exception:
            continue
        if isinstance(obj, dict) and snippet[end:].strip() == "":
            return obj
    return None


def _ensure_beads_initialized(repo_root: str) -> None:
    beads_dir = Path(repo_root) / ".beads"
    has_db = (beads_dir / "beads.db").exists()
    has_jsonl = (beads_dir / "issues.jsonl").exists()
    if has_db or has_jsonl:
        return

    init_result = _run_cmd(["bd", "--sandbox", "init"], cwd=repo_root)
    if init_result.returncode != 0:
        raise RuntimeError(f"bd init failed: {init_result.stderr.strip() or init_result.stdout.strip()}")


def _bd_export(repo_root: str) -> None:
    export_result = _run_cmd(
        ["bd", "--sandbox", "export", "-o", ".beads/issues.jsonl"],
        cwd=repo_root,
    )
    if export_result.returncode != 0:
        raise RuntimeError(
            f"bd export failed: {export_result.stderr.strip() or export_result.stdout.strip()}"
        )


def _bd_show(bead_id: str, repo_root: str) -> dict[str, Any]:
    show_result = _run_cmd(
        ["bd", "--sandbox", "show", bead_id, "--json"],
        cwd=repo_root,
    )
    if show_result.returncode != 0:
        raise RuntimeError(
            f"bd show failed for {bead_id}: {show_result.stderr.strip() or show_result.stdout.strip()}"
        )

    parsed = _parse_issue_payload(show_result.stdout)
    if not parsed:
        raise RuntimeError(f"Unable to parse bead payload for {bead_id}")
    return parsed


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^a-z0-9-]", "-", value.lower())
    safe = re.sub(r"-{2,}", "-", safe).strip("-")
    return safe[:35] or "bead"


def _build_job_manifest(
    *,
    job_name: str,
    namespace: str,
    image: str,
    bead: dict[str, Any],
    test_cmd: str,
    autocommit: bool,
) -> dict[str, Any]:
    bead_json = json.dumps(bead, separators=(",", ":"))
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name, "namespace": namespace},
        "spec": {
            "ttlSecondsAfterFinished": 600,
            "backoffLimit": 0,
            "template": {
                "metadata": {"labels": {"app": "coder-pad-polecat", "bead-id": _safe_name(str(bead.get("id", "")))}},
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "polecat",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "command": [
                                "python",
                                "-m",
                                "agentorchestrator.integrations.coder_pad_mvp.entrypoint",
                            ],
                            "env": [
                                {"name": "GASTOWN_BEAD_ID", "value": str(bead.get("id") or "")},
                                {"name": "GASTOWN_BEAD_JSON", "value": bead_json},
                                {"name": "WORKTREE_PATH", "value": "/app"},
                                {"name": "GASTOWN_OUTPUT_DIR", "value": "/app/.gastown"},
                                {"name": "POLECAT_TEST_CMD", "value": test_cmd},
                                {"name": "POLECAT_AUTOCOMMIT", "value": "true" if autocommit else "false"},
                            ],
                        }
                    ],
                },
            },
        },
    }


def _dispatch_job(manifest: dict[str, Any]) -> None:
    apply_result = _run_cmd(
        ["kubectl", "apply", "-f", "-"],
        stdin_text=json.dumps(manifest),
    )
    if apply_result.returncode != 0:
        raise RuntimeError(apply_result.stderr.strip() or apply_result.stdout.strip())


def _wait_for_job(job_name: str, namespace: str, timeout_seconds: int) -> None:
    wait_result = _run_cmd(
        [
            "kubectl",
            "-n",
            namespace,
            "wait",
            "--for=condition=complete",
            f"job/{job_name}",
            f"--timeout={timeout_seconds}s",
        ]
    )
    if wait_result.returncode != 0:
        raise RuntimeError(wait_result.stderr.strip() or wait_result.stdout.strip())


def _get_job_pod(job_name: str, namespace: str) -> str:
    pod_result = _run_cmd(
        [
            "kubectl",
            "-n",
            namespace,
            "get",
            "pods",
            "-l",
            f"job-name={job_name}",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
    )
    if pod_result.returncode != 0 or not pod_result.stdout.strip():
        raise RuntimeError(
            f"Unable to find pod for job {job_name}: {pod_result.stderr.strip() or pod_result.stdout.strip()}"
        )
    return pod_result.stdout.strip()


def _get_logs(pod_name: str, namespace: str) -> str:
    logs_result = _run_cmd(["kubectl", "-n", namespace, "logs", pod_name])
    if logs_result.returncode != 0:
        raise RuntimeError(logs_result.stderr.strip() or logs_result.stdout.strip())
    return logs_result.stdout


def _update_bead_status(bead_id: str, repo_root: str, status: str, notes: str) -> None:
    update_status = _run_cmd(
        ["bd", "--sandbox", "update", bead_id, "--status", status],
        cwd=repo_root,
    )
    update_status_out = (update_status.stdout + "\n" + update_status.stderr).strip()
    if update_status.returncode != 0 or "Error updating" in update_status_out:
        raise RuntimeError(
            f"bd update status failed: {update_status_out}"
        )

    update_notes = _run_cmd(
        ["bd", "--sandbox", "update", bead_id, "--notes", notes],
        cwd=repo_root,
    )
    update_notes_out = (update_notes.stdout + "\n" + update_notes.stderr).strip()
    if update_notes.returncode != 0 or "Error updating" in update_notes_out:
        raise RuntimeError(
            f"bd update notes failed: {update_notes_out}"
        )

    _bd_export(repo_root)
    refreshed = _bd_show(bead_id, repo_root)
    if refreshed.get("status") != status:
        raise RuntimeError(
            f"bd update status did not persist (expected={status}, actual={refreshed.get('status')})"
        )


class CreateBeadRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=3)
    issue_type: str = Field(default="task")
    priority: int = Field(default=2, ge=0, le=4)
    labels: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(default="")
    bead_id: str | None = None
    create_bead: CreateBeadRequest | None = None
    wait_for_completion: bool = True
    timeout_seconds: int = Field(default=240, ge=30, le=3600)
    test_cmd: str = Field(default="pytest tests/test_calculator_core.py -q")
    autocommit: bool = False


def _create_bead(req: CreateBeadRequest, repo_root: str) -> dict[str, Any]:
    cmd = [
        "bd",
        "--sandbox",
        "create",
        req.title,
        "--type",
        req.issue_type,
        "--priority",
        str(req.priority),
        "--description",
        req.description,
        "--json",
    ]
    if req.labels:
        cmd.extend(["--labels", ",".join(req.labels)])

    create_result = _run_cmd(cmd, cwd=repo_root)
    if create_result.returncode != 0:
        raise RuntimeError(create_result.stderr.strip() or create_result.stdout.strip())

    payload = _parse_issue_payload(create_result.stdout)
    if not payload:
        raise RuntimeError("Unable to parse bead create response")

    _bd_export(repo_root)
    return payload


def create_app() -> FastAPI:
    app = FastAPI(title="Coder Pad Mayor API", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/beads")
    async def create_bead(req: CreateBeadRequest) -> dict[str, Any]:
        repo_root = os.getenv("BEADS_REPO_ROOT", os.getcwd())
        _ensure_beads_initialized(repo_root)
        try:
            bead = _create_bead(req, repo_root)
            return {"ok": True, "bead": bead}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/beads/{bead_id}")
    async def show_bead(bead_id: str) -> dict[str, Any]:
        repo_root = os.getenv("BEADS_REPO_ROOT", os.getcwd())
        _ensure_beads_initialized(repo_root)
        try:
            bead = _bd_show(bead_id, repo_root)
            return {"ok": True, "bead": bead}
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/chat")
    async def chat(req: ChatRequest) -> dict[str, Any]:
        repo_root = os.getenv("BEADS_REPO_ROOT", os.getcwd())
        namespace = os.getenv("POLECAT_NAMESPACE", "default")
        image = os.getenv("POLECAT_IMAGE", "polecat-mvp:local")

        _ensure_beads_initialized(repo_root)

        try:
            if req.bead_id:
                bead = _bd_show(req.bead_id, repo_root)
            elif req.create_bead:
                bead = _create_bead(req.create_bead, repo_root)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Provide bead_id or create_bead payload",
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        bead_id = str(bead.get("id") or "")
        if not bead_id:
            raise HTTPException(status_code=500, detail="Bead payload missing id")

        job_name = f"polecat-{_safe_name(bead_id)}-{uuid.uuid4().hex[:6]}"
        manifest = _build_job_manifest(
            job_name=job_name,
            namespace=namespace,
            image=image,
            bead=bead,
            test_cmd=req.test_cmd,
            autocommit=req.autocommit,
        )

        try:
            _dispatch_job(manifest)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Dispatch failed: {exc}") from exc

        if not req.wait_for_completion:
            return {
                "ok": True,
                "bead_id": bead_id,
                "job_name": job_name,
                "namespace": namespace,
                "status": "dispatched",
            }

        pod_name = ""
        logs = ""
        outcome: dict[str, Any] | None = None
        try:
            _wait_for_job(job_name, namespace, req.timeout_seconds)
            pod_name = _get_job_pod(job_name, namespace)
            logs = _get_logs(pod_name, namespace)
            outcome = _extract_last_json_object(logs)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Execution failed: {exc}") from exc

        if not outcome:
            raise HTTPException(status_code=500, detail="Unable to parse polecat output JSON")

        suite_result = outcome.get("suite_result", {})
        status = str(suite_result.get("status", "failed")).lower()
        bead_status = "closed" if status == "success" else "open"
        summary = str(suite_result.get("summary") or "Polecat execution completed")

        try:
            _update_bead_status(bead_id, repo_root, bead_status, summary)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Polecat completed but bead update failed: {exc}",
            ) from exc

        return {
            "ok": True,
            "bead_id": bead_id,
            "job_name": job_name,
            "namespace": namespace,
            "pod_name": pod_name,
            "status": bead_status,
            "summary": summary,
            "outcome": outcome,
        }

    return app


app = create_app()


def main() -> int:
    import uvicorn

    host = os.getenv("MAYOR_API_HOST", "0.0.0.0")
    port = int(os.getenv("MAYOR_API_PORT", "8787"))
    uvicorn.run(
        "agentorchestrator.integrations.coder_pad_mvp.mayor_api:app",
        host=host,
        port=port,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
