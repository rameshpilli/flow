"""Polecat pod entrypoint for role-based expert execution.

Pod lifecycle (GT-native):
  1. ``bd hook <bead-id>`` — attach worktree, mark bead as active
  2. Run the expert pipeline
  3. ``bd close <bead-id>`` — GT daemon detects closure and auto-dispatches
     any dependents whose deps are now fully satisfied

The pod does NOT manually sling the next expert.  GT's convoy scheduler
(``runEventPoll`` → ``feedNextReadyIssue``) owns all fan-out.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

from agentorchestrator.integrations.gastown import (
    BeadClient,
    BeadStateManager,
    delete_swarm_configmap,
    read_swarm_configmap,
)
from agentorchestrator.integrations.gastown.bead_state_manager import CompletionSummary
from examples.polecat_swarm.pipeline import run_expert_pipeline
from examples.polecat_swarm.swarm_log_bridge import SwarmLogBridge
from examples.polecat_swarm.swarm_logger import SwarmLogger, register_log_sink, unregister_log_sink
from examples.polecat_swarm.types import ExpertResult, TraceContext


def main() -> int:
    expert_role = os.environ.get("EXPERT_ROLE", "")
    bead_json = os.environ.get("GASTOWN_BEAD_JSON", "")
    bead_id_env = os.environ.get("GASTOWN_BEAD_ID", "")
    worktree = os.environ.get("WORKTREE_PATH", "/workspace")
    output_dir = os.environ.get("GASTOWN_OUTPUT_DIR", "/output")
    repo_root = os.environ.get("BEADS_REPO_ROOT", worktree)
    config_ref = os.environ.get("SWARM_CONFIG_REF", "")
    namespace = os.environ.get("POLECAT_NAMESPACE", "gastown-workers")
    mayor_ws_url = os.environ.get("MAYOR_WS_URL", "ws://mayor-api:8787/ws/swarm-events")
    is_custom_env = os.environ.get("IS_CUSTOM_AGENT", "").strip().lower()
    custom_module = os.environ.get("CUSTOM_PIPELINE_MODULE", "")

    bead_client = BeadClient(repo_root)
    state_manager = BeadStateManager(bead_client)

    bead = _load_bead(bead_json=bead_json, bead_id=bead_id_env, bead_client=bead_client)
    bead_id = str(bead.get("id") or bead_id_env)

    # ── Self-discover role from bead metadata if env var not set ───
    # GT's convoy launch dispatches pods without setting EXPERT_ROLE.
    # Mayor stores the role as a label on the bead (e.g. "pre", "ees")
    # and in the title prefix (e.g. "[PRE] Add slide fade animations").
    if not expert_role:
        expert_role = _infer_role_from_bead(bead)
    if not expert_role:
        _print_error("Cannot determine EXPERT_ROLE from env or bead metadata")
        return 1

    # ── Discover config_ref from bead labels if not in env ──────────
    # Mayor stores the ConfigMap name as a label on child beads
    # (e.g. "swarm-config-thirsty-pasteur-750").
    if not config_ref:
        for label in bead.get("labels", []) or []:
            if str(label).startswith("swarm-config-"):
                config_ref = str(label)
                break

    # ── Determine if this is a custom agent ────────────────────────
    # Check env first, then fall back to swarm_config pipeline entry.
    is_custom = is_custom_env == "true"

    swarm_config = read_swarm_configmap(config_ref, namespace=namespace) if config_ref else None

    # If custom agent info wasn't in env, check the ConfigMap pipeline.
    if swarm_config and not is_custom:
        for pipeline_entry in swarm_config.pipeline:
            if pipeline_entry.role == expert_role:
                is_custom = pipeline_entry.is_custom
                if pipeline_entry.pipeline_module and not custom_module:
                    custom_module = pipeline_entry.pipeline_module
                break

    trace = TraceContext(
        trace_id=swarm_config.trace_id if swarm_config else "",
        span_id=bead_id,
        expert_role=expert_role,
        repo_name=swarm_config.repo_name if swarm_config else "",
    )
    bridge = SwarmLogBridge(mayor_ws_url)
    bridge.start()
    register_log_sink(bridge.push_record)
    log = SwarmLogger(trace)

    log.info(
        "pod_started",
        bead_id=bead_id,
        commit_sha=swarm_config.commit_sha if swarm_config else "",
        config_ref=config_ref,
    )

    # ── 1. Hook the bead (GT-native pod lifecycle) ────────────────────
    try:
        state_manager.hook(bead_id)
    except Exception:
        # Fallback to legacy claim if bd hook is not available.
        try:
            state_manager.claim(bead_id)
        except Exception as exc:
            log.error("bead_hook_failed", bead_id=bead_id, reason=str(exc))
            unregister_log_sink(bridge.push_record)
            bridge.stop()
            return 1

    log.info("bead_hooked", bead_id=bead_id)

    if swarm_config and swarm_config.commit_sha:
        try:
            subprocess.run(
                ["git", "checkout", swarm_config.commit_sha],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            )
            log.info("repo_checked_out", commit_sha=swarm_config.commit_sha, worktree=worktree)
        except Exception as exc:
            log.error("repo_checkout_failed", commit_sha=swarm_config.commit_sha, reason=str(exc))
            state_manager.fail(bead_id, stage=expert_role, output=str(exc))
            unregister_log_sink(bridge.push_record)
            bridge.stop()
            return 1

    if swarm_config and swarm_config.skills.warnings:
        log.warn("skills_missing", missing_skills=swarm_config.skills.warnings)
        state_manager.annotate(
            bead_id,
            "⚠️ Skills declared but not found on disk (degraded mode): "
            f"{swarm_config.skills.warnings}",
        )

    try:
        if is_custom and custom_module:
            log.info("custom_agent_loaded", module_path=custom_module, role=expert_role)
            result = _run_custom_agent(custom_module, bead, swarm_config, worktree, repo_root)
        else:
            result = run_expert_pipeline(
                role=expert_role,
                bead=bead,
                swarm_config=swarm_config,
                worktree=worktree,
                output_dir=output_dir,
                repo_root=repo_root,
            )
    except Exception as exc:
        log.error("expert_exception", role=expert_role, exception=str(exc), elapsed_s=round(trace.elapsed(), 3))
        state_manager.fail(bead_id, stage=expert_role, output=str(exc))
        unregister_log_sink(bridge.push_record)
        bridge.stop()
        return 1

    _persist_result(output_dir=output_dir, bead=bead, role=expert_role, result=result)

    if result.status == "blocked":
        state_manager.block(bead_id, reason=result.notes)
        log.warn("pipeline_halted", role=expert_role, status=result.status, bead_id=bead_id)
        unregister_log_sink(bridge.push_record)
        bridge.stop()
        return 1

    if result.status == "failed":
        state_manager.fail(bead_id, stage=expert_role, output=result.notes, gate_scores=result.gate_scores)
        log.warn("pipeline_halted", role=expert_role, status=result.status, bead_id=bead_id)
        unregister_log_sink(bridge.push_record)
        bridge.stop()
        return 1

    # ── Success path ──────────────────────────────────────────────────
    # Close the bead.  GT's daemon (runEventPoll every 5s) detects the
    # closure and calls feedNextReadyIssue to dispatch any dependents
    # whose deps are now fully satisfied.  The pod does NOT manually
    # sling the next expert — GT owns all fan-out.
    if expert_role == "RE":
        summary = CompletionSummary(
            bead_id=bead_id,
            bead_title=str(bead.get("title") or bead_id),
            repo_name=swarm_config.repo_name if swarm_config else "unknown-repo",
            pipeline_run=[expert.role for expert in (swarm_config.pipeline if swarm_config else []) if expert.enabled]
            or [expert_role],
            duration_seconds=trace.elapsed(),
            pr_url=str(result.metadata.get("pr_url") or ""),
            what_was_built=result.notes,
            key_decisions=[str(item) for item in result.metadata.get("decisions", [])] or ["MVP release flow completed"],
            files_changed=[str(item) for item in result.metadata.get("files_changed", [])],
            services_used=list(swarm_config.services) if swarm_config else [],
            gate_results={expert_role: "✅ pass"},
            labels=[str(label) for label in (bead.get("labels") or [])],
            commit_sha=str(result.metadata.get("commit_sha") or (swarm_config.commit_sha if swarm_config else "")),
            trace_id=trace.trace_id,
        )
        state_manager.close_with_summary(bead_id, summary)
    else:
        state_manager.close(bead_id, note=result.notes)

    log.info("expert_completed", status=result.status, elapsed_s=round(trace.elapsed(), 3), gate_scores=result.gate_scores)

    # GT daemon handles fan-out — pod just logs and exits.
    log.info(
        "bead_closed",
        bead_id=bead_id,
        role=expert_role,
        message="GT daemon will dispatch dependents automatically",
    )

    if expert_role == "RE" and config_ref:
        delete_swarm_configmap(config_ref, namespace=namespace)

    unregister_log_sink(bridge.push_record)
    bridge.stop()
    return 0


def _load_bead(bead_json: str, bead_id: str, bead_client: BeadClient) -> dict:
    if bead_json.strip():
        payload = json.loads(bead_json)
        if isinstance(payload, dict):
            return payload
    if bead_id:
        return bead_client.show(bead_id)
    raise ValueError("Need GASTOWN_BEAD_JSON or GASTOWN_BEAD_ID")


def _run_custom_agent(module_path: str, bead: dict, swarm_config, worktree: str, repo_root: str) -> ExpertResult:
    spec = importlib.util.spec_from_file_location("custom_agent", module_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load custom agent module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.run(bead=bead, swarm_config=swarm_config, worktree=worktree, repo_root=repo_root)

    if isinstance(result, ExpertResult):
        return result

    if isinstance(result, dict):
        return ExpertResult(
            status=str(result.get("status", "failed")),
            notes=str(result.get("notes", "Custom agent returned dict payload")),
            artifacts=list(result.get("artifacts", [])),
            gate_scores=dict(result.get("gate_scores", {})),
            metadata=dict(result.get("metadata", {})),
        )

    raise RuntimeError("Custom agent returned unsupported result type")


def _persist_result(output_dir: str, bead: dict, role: str, result: ExpertResult) -> None:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "result.json")
    payload = {
        "bead_id": bead.get("id"),
        "role": role,
        "status": result.status,
        "notes": result.notes,
        "artifacts": result.artifacts,
        "gate_scores": result.gate_scores,
        "metadata": result.metadata,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


# ── Known platform roles (used for bead-label → role inference) ──────
_KNOWN_ROLES = {"PRE", "EES", "QES", "DE", "RE"}


def _infer_role_from_bead(bead: dict) -> str:
    """Infer EXPERT_ROLE from bead metadata.

    GT's ``convoy launch`` dispatches pods without setting env vars.
    Mayor stores the role in two places on each child bead:
      1. **Labels** — e.g. ``["pre", "polecat-swarm"]``
      2. **Title prefix** — e.g. ``[PRE] Add slide fade animations``

    This function checks both, labels first.
    """
    # 1. Check labels — Mayor sets expert.role.lower() as a label.
    for label in bead.get("labels", []) or []:
        normalized = str(label).strip().upper()
        if normalized in _KNOWN_ROLES:
            return normalized

    # 2. Check title prefix — Mayor formats as "[ROLE] title".
    title = str(bead.get("title") or "")
    if title.startswith("[") and "]" in title:
        bracket_content = title[1 : title.index("]")].strip().upper()
        if bracket_content in _KNOWN_ROLES:
            return bracket_content

    # 3. If a custom agent, check the swarm config for non-standard roles.
    # Custom roles won't be in _KNOWN_ROLES, so we match by label overlap
    # with the pipeline roles.
    for label in bead.get("labels", []) or []:
        label_str = str(label).strip()
        if label_str and label_str != "polecat-swarm" and not label_str.startswith("convoy-"):
            # Could be a custom role label — return it uppercased.
            return label_str.upper()

    return ""


def _print_error(message: str) -> None:
    print(json.dumps({"status": "failed", "error": message}), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
