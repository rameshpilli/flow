"""Mayor API for Polecat Swarm dynamic expert dispatch.

Production flow (GT available):
  1. Mayor creates a parent epic bead
  2. Mayor creates child beads with ``bd depend`` for DAG edges
  3. ``gt convoy stage <epic-id>`` validates the DAG / computes MEOW waves
  4. ``gt convoy launch <convoy-id>`` dispatches Wave 1 (roots)
  5. Mayor is **done** — GT daemon handles all fan-out from here
  6. Pods read bead metadata via ``bd show``, do work, call ``bd close``
  7. ``gt feed --problems`` for observability
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from examples.polecat_swarm.swarm_logger import SwarmLogger
from examples.polecat_swarm.types import TraceContext

from .agent_registry import AgentRegistry
from .bead_client import BeadClient
from .configmap_store import write_swarm_configmap
from .convoy_manager import ConvoyManager, compute_execution_groups
from .swarm_config import ExpertConfig, SwarmConfig, SwarmConfigLoader

logger = logging.getLogger(__name__)

BEADS_REPO_ROOT = os.getenv("BEADS_REPO_ROOT", ".")
GT_WORKSPACE = os.getenv("GT_WORKSPACE", os.path.expanduser("~/gt"))
POLECAT_NAMESPACE = os.getenv("POLECAT_NAMESPACE", "gastown-workers")
DEFAULT_RIG = os.getenv("DEFAULT_RIG", "myproject")
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000")
MAYOR_API_PORT = os.getenv("MAYOR_API_PORT", "8787")
MAYOR_WS_URL = os.getenv("MAYOR_WS_URL", f"ws://mayor-api:{MAYOR_API_PORT}/ws/swarm-events")

bead_client = BeadClient(BEADS_REPO_ROOT)
convoy_mgr = ConvoyManager(GT_WORKSPACE)
agent_reg = AgentRegistry()
config_loader = SwarmConfigLoader(agent_registry=agent_reg)


# In-memory live state for GUI subscribers.
_swarm_gui_clients: set[WebSocket] = set()
_convoy_cache: dict[str, dict[str, Any]] = {}


class ChatRequest(BaseModel):
    bead_id: str
    repo_url: str = ""
    rig: str = DEFAULT_RIG
    message: str = "Execute this bead"


app = FastAPI(title="Mayor API — Polecat Swarm", version="0.3.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/agents")
def list_agents() -> dict:
    return {"agents": agent_reg.list_agents()}


@app.get("/repos")
def list_repos() -> dict:
    return {"rigs": convoy_mgr.list_rigs()}


@app.get("/convoys")
def list_convoys() -> dict:
    return {"convoys": list(_convoy_cache.values())}


@app.get("/pipeline/{convoy_id}")
def get_pipeline(convoy_id: str) -> dict:
    cached = _convoy_cache.get(convoy_id)
    if cached:
        return cached

    # Fallback path after Mayor API restart.
    try:
        beads = bead_client.list(labels=[convoy_id])
        experts: dict[str, dict[str, Any]] = {}
        for bead in beads:
            role = "UNKNOWN"
            for label in bead.get("labels", []) or []:
                normalized = str(label).upper()
                if normalized in {"PRE", "EES", "QES", "DE", "RE"}:
                    role = normalized
                    break
            experts[role] = {
                "role": role,
                "status": bead.get("status", "unknown"),
                "bead_id": bead.get("id", ""),
            }
        return {"convoy_id": convoy_id, "experts": experts, "source": "bd_fallback"}
    except Exception as exc:
        return {"convoy_id": convoy_id, "experts": {}, "error": str(exc)}


@app.websocket("/ws/swarm-events")
async def swarm_events_ws(ws: WebSocket) -> None:
    await ws.accept()
    caller_type = ""

    try:
        async for raw in ws.iter_text():
            msg = json.loads(raw)
            msg_type = str(msg.get("type") or "")

            if msg_type == "register":
                caller_type = str(msg.get("caller") or "")
                if caller_type == "gui":
                    _swarm_gui_clients.add(ws)
                continue

            if msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong", "ts": round(time.time(), 3)}))
                continue

            if msg_type == "log_event":
                _update_convoy_cache(msg)
                await _fan_out(msg)
                continue

            if msg_type in {"convoy_update", "expert_update"} and caller_type == "pod":
                _update_convoy_cache(msg)
                await _fan_out(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _swarm_gui_clients:
            _swarm_gui_clients.remove(ws)


@app.post("/chat/plan")
async def preview_pipeline(req: ChatRequest) -> dict:
    try:
        bead = bead_client.show(req.bead_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to load bead {req.bead_id}: {exc}") from exc

    repo_url = req.repo_url or str(bead.get("repo_url") or "")
    if not repo_url:
        raise HTTPException(status_code=400, detail="repo_url missing in request and bead")

    plan_trace = TraceContext(trace_id="plan", span_id=req.bead_id, expert_role="")
    plan_log = SwarmLogger(plan_trace)
    plan_log.info("plan_started", bead_id=req.bead_id, repo_url=repo_url)

    with tempfile.TemporaryDirectory() as tmpdir:
        _clone_repo(repo_url=repo_url, target=tmpdir)
        commit_sha = _rev_parse_head(tmpdir)
        swarm_config = config_loader.load(tmpdir, repo_url, commit_sha=commit_sha, trace_id="plan")

    pipeline = [
        {
            "role": expert.role,
            "model": expert.model,
            "enabled": expert.enabled,
            "is_custom": expert.is_custom,
            "skills": swarm_config.skills.for_role(expert.role),
        }
        for expert in swarm_config.pipeline
        if expert.enabled
    ]

    plan_log.info(
        "plan_complete",
        pipeline_roles=[entry["role"] for entry in pipeline],
        skill_warnings=swarm_config.skills.warnings,
        commit_sha=commit_sha,
    )

    return {
        "repo_url": repo_url,
        "commit_sha": commit_sha,
        "pipeline": pipeline,
        "services": swarm_config.services,
        "skill_warnings": swarm_config.skills.warnings,
    }


@app.post("/chat")
async def dispatch_bead(req: ChatRequest) -> dict:
    try:
        bead = bead_client.show(req.bead_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to load bead {req.bead_id}: {exc}") from exc

    repo_url = req.repo_url or str(bead.get("repo_url") or "")
    if not repo_url:
        raise HTTPException(status_code=400, detail="repo_url missing in request and bead")

    dispatch_log = SwarmLogger(TraceContext(trace_id="dispatch", span_id=req.bead_id, expert_role=""))
    dispatch_log.info("dispatch_started", bead_id=req.bead_id, repo_url=repo_url)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            _clone_repo(repo_url=repo_url, target=tmpdir)
            commit_sha = _rev_parse_head(tmpdir)
            swarm_config = config_loader.load(
                tmpdir,
                repo_url,
                commit_sha=commit_sha,
                trace_id="pre-convoy",
            )

        # ── Build dependency graph from swarm.yaml depends_on ──
        dep_graph = swarm_config.to_dependency_graph()
        # Local execution groups — advisory only, GT computes its own MEOW waves
        execution_groups = compute_execution_groups(dep_graph)

        dispatch_log.info(
            "meow_plan",
            dependency_graph=dep_graph,
            execution_groups=execution_groups,
        )

        enabled_pipeline = [expert for expert in swarm_config.pipeline if expert.enabled]
        if not enabled_pipeline:
            raise HTTPException(status_code=500, detail="No enabled experts in resolved pipeline")

        # ── Step 1: Create sub-beads (one per expert) ──
        # ConfigMap name is deterministic so we can embed it in labels
        # before the ConfigMap actually exists.
        configmap_name = f"swarm-config-{req.bead_id}"
        parent_title = bead.get("title", req.bead_id)
        parent_desc = str(bead.get("description") or "")
        sub_bead_ids: dict[str, str] = {}
        for expert in enabled_pipeline:
            sub_id = bead_client.create(
                title=f"[{expert.role}] {parent_title}",
                description=_build_expert_description(
                    expert=expert,
                    parent_title=parent_title,
                    parent_description=parent_desc,
                    swarm_config=swarm_config,
                ),
                labels=[
                    expert.role.lower(),
                    "polecat-swarm",
                    configmap_name,  # Pod can discover ConfigMap from label
                ],
                parent=req.bead_id,
            )
            sub_bead_ids[expert.role] = sub_id

        # ── Step 2: Wire bead-level dependencies via bd depend ──
        # Each depends_on edge becomes: bd depend <this-bead> blocks <dep-bead>
        # GT's daemon uses these to determine dispatch order.
        for expert in enabled_pipeline:
            for dep_role in expert.depends_on:
                if dep_role in sub_bead_ids:
                    bead_client.depend(
                        bead_id=sub_bead_ids[expert.role],
                        dependency_type="blocks",
                        target_bead_id=sub_bead_ids[dep_role],
                    )

        dispatch_log.info(
            "dependencies_wired",
            edges=[(role, dep) for role, deps in dep_graph.items() for dep in deps],
            sub_bead_ids=sub_bead_ids,
        )

        # ── Step 3: gt convoy stage — validate DAG, compute MEOW waves ──
        stage_result = convoy_mgr.stage_convoy(req.bead_id)
        convoy_id = ""
        if stage_result.returncode == 0:
            try:
                stage_data = json.loads(stage_result.stdout)
                convoy_id = str(stage_data.get("convoy_id") or stage_data.get("id") or "")
            except Exception:
                convoy_id = stage_result.stdout.strip().splitlines()[-1].strip() if stage_result.stdout.strip() else ""

        if not convoy_id:
            # Fallback: create convoy manually (local mode or gt version mismatch)
            convoy_id = convoy_mgr.create_convoy(
                name=f"Swarm: {bead.get('title', req.bead_id)}",
                bead_ids=list(sub_bead_ids.values()),
            )

        dispatch_log.info("convoy_staged", convoy_id=convoy_id)

        # Update trace_id now that we have convoy_id.
        swarm_config = swarm_config.model_copy(update={"trace_id": convoy_id})

        # Store SwarmConfig so pods can read pipeline config.
        configmap_name = write_swarm_configmap(
            bead_id=req.bead_id,
            swarm_config=swarm_config,
            namespace=POLECAT_NAMESPACE,
        )

        _initialize_convoy_cache(
            convoy_id=convoy_id,
            repo=swarm_config.repo_name,
            bead_id=req.bead_id,
            commit_sha=commit_sha,
            configmap_name=configmap_name,
            pipeline=enabled_pipeline,
            sub_bead_ids=sub_bead_ids,
            execution_groups=execution_groups,
        )

        # ── Step 4: gt convoy launch — dispatch Wave 1 (roots) ──
        # GT daemon takes over from here.  Mayor is done.
        launch_result = convoy_mgr.launch_convoy(convoy_id)

        dispatch_log = SwarmLogger(TraceContext(trace_id=convoy_id, span_id=req.bead_id, expert_role=""))
        dispatch_log.info(
            "dispatch_complete",
            convoy_id=convoy_id,
            pipeline_roles=[expert.role for expert in enabled_pipeline],
            execution_groups=execution_groups,
            commit_sha=commit_sha,
            configmap_name=configmap_name,
            launch_ok=launch_result.returncode == 0,
        )

        return {
            "bead_id": req.bead_id,
            "repo_url": repo_url,
            "commit_sha": commit_sha,
            "convoy_id": convoy_id,
            "configmap_name": configmap_name,
            "pipeline": [expert.role for expert in enabled_pipeline],
            "execution_groups": execution_groups,
            "sub_beads": sub_bead_ids,
            "status": "launched",
        }
    except HTTPException:
        raise
    except Exception as exc:
        dispatch_log.error("dispatch_failed", bead_id=req.bead_id, reason=str(exc), exception=type(exc).__name__)
        raise HTTPException(status_code=500, detail=f"Dispatch failed: {exc}") from exc


async def _fan_out(message: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    encoded = json.dumps(message)
    for client in list(_swarm_gui_clients):
        try:
            await client.send_text(encoded)
        except Exception:
            dead.append(client)
    for client in dead:
        _swarm_gui_clients.discard(client)


def _initialize_convoy_cache(
    *,
    convoy_id: str,
    repo: str,
    bead_id: str,
    commit_sha: str,
    configmap_name: str,
    pipeline: list,
    sub_bead_ids: dict[str, str],
    execution_groups: list[list[str]] | None = None,
) -> None:
    # Build a group-index lookup so the GUI can show parallel lanes.
    group_of: dict[str, int] = {}
    for gidx, group in enumerate(execution_groups or []):
        for role in group:
            group_of[role] = gidx

    experts: dict[str, dict[str, Any]] = {}
    for idx, expert in enumerate(pipeline):
        experts[expert.role] = {
            "role": expert.role,
            "status": "pending",
            "model": expert.model,
            "is_custom": expert.is_custom,
            "bead_id": sub_bead_ids.get(expert.role, ""),
            "sequence": idx,
            "group": group_of.get(expert.role, idx),
            "gate_scores": {},
            "elapsed_s": None,
        }

    _convoy_cache[convoy_id] = {
        "convoy_id": convoy_id,
        "bead_id": bead_id,
        "repo": repo,
        "status": "running",
        "commit_sha": commit_sha,
        "configmap_name": configmap_name,
        "execution_groups": execution_groups or [],
        "started_at": round(time.time(), 3),
        "experts": experts,
    }


def _update_convoy_cache(msg: dict[str, Any]) -> None:
    payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
    trace_id = str(msg.get("trace_id") or payload.get("trace_id") or "")
    if not trace_id:
        return

    convoy = _convoy_cache.setdefault(
        trace_id,
        {
            "convoy_id": trace_id,
            "repo": str(payload.get("repo") or ""),
            "status": "running",
            "started_at": payload.get("ts"),
            "experts": {},
        },
    )

    role = str(payload.get("role") or "")
    event = str(payload.get("event") or "")

    if role:
        experts = convoy.setdefault("experts", {})
        if role not in experts:
            experts[role] = {
                "role": role,
                "status": "pending",
                "model": "",
                "gate_scores": {},
                "elapsed_s": None,
            }
        expert = experts[role]

        if event == "expert_started":
            expert["status"] = "in_progress"
            expert["model"] = payload.get("model", "")
            expert["started_at"] = payload.get("ts")
        elif event == "expert_completed":
            expert["status"] = payload.get("status", "done")
            expert["elapsed_s"] = payload.get("elapsed_s")
            expert["gate_scores"] = payload.get("gate_scores", {})
        elif event in {"pipeline_halted", "expert_exception"}:
            expert["status"] = "failed"

    if event == "convoy_complete":
        convoy["status"] = "complete"


def _clone_repo(repo_url: str, target: str) -> None:
    result = subprocess.run(
        ["git", "clone", "--depth=1", repo_url, target],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git clone failed")


def _rev_parse_head(cwd: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git rev-parse failed")
    return result.stdout.strip()


# ── Role-specific description templates ──────────────────────────────
# Each expert's bead gets a scoped description so the agent knows
# exactly what to do, what artifacts to produce, and what NOT to touch.

_ROLE_DESCRIPTIONS: dict[str, str] = {
    "PRE": (
        "Planning & Requirements Expert.\n\n"
        "TASK: Analyze the parent epic and produce a scoped requirements document.\n"
        "OUTPUT: requirements.md — acceptance criteria, constraints, scope boundaries, "
        "implementation approach.\n"
        "DO NOT: Write code, run tests, or create branches. Your job is planning only.\n"
        "READS: Parent bead description.\n"
        "FEEDS: EES (Engineering Expert) reads your requirements.md."
    ),
    "EES": (
        "Engineering Expert (Code Implementation).\n\n"
        "TASK: Implement the feature/fix based on PRE's requirements.md.\n"
        "OUTPUT: Working code changes, implementation_plan.md, code_review.md "
        "(self-review with gate scores).\n"
        "DO NOT: Run the full test suite (QES does that), write user-facing docs "
        "(DE does that), or handle releases (RE does that).\n"
        "READS: PRE's requirements.md from specs.\n"
        "FEEDS: QES (tests your code), RE (branches from your work), "
        "DE (documents after QES passes)."
    ),
    "QES": (
        "Quality Engineering Supervisor.\n\n"
        "TASK: Run the test suite against EES's implementation, analyze coverage, "
        "report gate scores.\n"
        "OUTPUT: qa_report.md — test results, coverage metrics, pass/fail gate decision.\n"
        "DO NOT: Fix failing tests yourself (that's EES's job on re-dispatch), "
        "write docs, or create releases.\n"
        "READS: EES's code changes and the repo test command from SwarmConfig.\n"
        "FEEDS: DE (reads your qa_report.md for documentation)."
    ),
    "DE": (
        "Documentation Expert.\n\n"
        "TASK: Generate project documentation based on the implementation and test results.\n"
        "OUTPUT: api_changes.md, release_notes.md, runbook.md, documentation_summary.md.\n"
        "DO NOT: Write code, run tests, or handle releases.\n"
        "READS: QES's qa_report.md and EES's code changes.\n"
        "FEEDS: Nothing — DE is a terminal node (unless a custom agent depends on it)."
    ),
    "RE": (
        "Release Expert.\n\n"
        "TASK: Prepare the release — create release branch, bump version, "
        "generate changelog, produce release summary.\n"
        "OUTPUT: release_summary.md, version bump, changelog entries.\n"
        "DO NOT: Write feature code, run tests, or generate API docs.\n"
        "READS: EES's git branch state.\n"
        "FEEDS: Nothing — RE is a terminal node."
    ),
}


def _build_expert_description(
    *,
    expert: ExpertConfig,
    parent_title: str,
    parent_description: str,
    swarm_config: SwarmConfig,
) -> str:
    """Build a scoped description for a child bead.

    Combines the role-specific instructions with the parent epic's
    context so the expert knows both *what* to do (role template) and
    *why* (the original task).
    """
    role_desc = _ROLE_DESCRIPTIONS.get(expert.role, "")
    if expert.is_custom and expert.description:
        role_desc = expert.description

    parts = []

    if role_desc:
        parts.append(role_desc)

    parts.append(f"--- Parent Epic ---\nTitle: {parent_title}")
    if parent_description:
        parts.append(f"Description: {parent_description}")

    parts.append(
        f"--- Repo Context ---\n"
        f"Repo: {swarm_config.repo_name}\n"
        f"Language: {swarm_config.language}\n"
        f"Test command: {swarm_config.test_command}"
    )

    if expert.depends_on:
        parts.append(
            f"--- Dependencies ---\n"
            f"Blocked by: {', '.join(expert.depends_on)}\n"
            f"This bead will only be dispatched after those experts close their beads."
        )

    return "\n\n".join(parts)
