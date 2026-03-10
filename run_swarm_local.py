#!/usr/bin/env python3
"""
Polecat Swarm — Local End-to-End Runner (Mayor-Centric)
========================================================

Simulates the FULL production architecture locally:

  1. Mayor API starts as the central orchestrator
  2. A parent epic bead is created (simulating what a dev/PM would do)
  3. Mayor creates child beads + wires ``bd depend`` for DAG edges
  4. ``gt convoy stage`` validates DAG → ``gt convoy launch`` dispatches Wave 1
  5. GT daemon handles all fan-out (simulated locally via group execution)
  6. Pods call ``bd hook`` on startup, do work, then ``bd close``
  7. ``gt feed --problems`` for observability (shown in summary)

What's bypassed for local mode:
  - gt convoy stage/launch → replaced with local MEOW shim (Kahn's topo sort)
  - gt daemon (5s poll)   → replaced with sequential group execution
  - bd CLI                → replaced with JSONL-based LocalBeadStore
  - kubectl               → replaced with local file ConfigMap store
  - opencode              → replaced with DryRunExecutor (or real LLM if --live)
  - git clone             → uses local repo directly (no shallow clone)

Usage:
    python run_swarm_local.py                                 # Dry run
    python run_swarm_local.py --title "Add user auth to API"  # Custom bead
    python run_swarm_local.py --live                          # Real LLM calls
    python run_swarm_local.py --bead-id thirsty-pasteur-42d   # Existing bead
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── Bootstrap path ──────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Env setup for local mode ───────────────────────────────────────────────
os.environ.setdefault("SWARM_CONFIG_FORCE_LOCAL", "true")
os.environ.setdefault("BD_SANDBOX", "false")
os.environ.setdefault("BEADS_REPO_ROOT", str(ROOT))

# Load API key from local_llm/.env if present
for env_name in (".env", ".env.local"):
    env_file = ROOT / "local_llm" / env_name
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
        break

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("swarm_local")

# Silence ALL noisy loggers — we use our own step-by-step output
logging.getLogger().setLevel(logging.WARNING)
for lib in ("httpx", "httpcore", "anthropic._base_client", "asyncio", "websockets",
            "uvicorn", "uvicorn.error", "uvicorn.access", "fastapi",
            "agentorchestrator", "examples", "polecat_swarm"):
    logging.getLogger(lib).setLevel(logging.ERROR)

# ── Color helpers ───────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BG_BLUE = "\033[44m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"
BG_MAGENTA = "\033[45m"

ROLE_COLORS = {"PRE": BLUE, "EES": GREEN, "QES": YELLOW, "DE": MAGENTA, "RE": CYAN}


def banner(text: str) -> None:
    width = 72
    print(f"\n{BOLD}{'═' * width}{RESET}")
    print(f"  {BOLD}{text}{RESET}")
    print(f"{BOLD}{'═' * width}{RESET}")


def section(text: str) -> None:
    print(f"\n{DIM}{'─' * 60}{RESET}")
    print(f"  {text}")
    print(f"{DIM}{'─' * 60}{RESET}")


def step_header(step_num: int, title: str, subtitle: str = "") -> None:
    """Print a prominent step header — makes the flow easy to follow."""
    print(f"\n  {BOLD}{CYAN}┌─ Step {step_num}: {title}{RESET}")
    if subtitle:
        print(f"  {CYAN}│  {DIM}{subtitle}{RESET}")
    print(f"  {CYAN}│{RESET}")


def step_detail(text: str, indent: int = 1) -> None:
    pad = "  │  " + ("  " * indent)
    print(f"  {CYAN}{pad}{RESET}{text}")


def step_output(label: str, value: str) -> None:
    print(f"  {CYAN}│{RESET}    {DIM}{label}:{RESET} {value}")


def step_done(msg: str = "") -> None:
    extra = f" — {msg}" if msg else ""
    print(f"  {CYAN}└─{RESET} {GREEN}✓ Done{extra}{RESET}")


def role_tag(role: str) -> str:
    color = ROLE_COLORS.get(role, "")
    return f"{color}{BOLD}[{role}]{RESET}"


def status_icon(status: str) -> str:
    return {
        "success": f"{GREEN}✅{RESET}",
        "failed": f"{RED}❌{RESET}",
        "blocked": f"{YELLOW}🟡{RESET}",
        "skipped": f"{DIM}⏭️{RESET}",
        "running": f"{BLUE}🔄{RESET}",
        "pending": f"{DIM}⏳{RESET}",
    }.get(status, "⬜")


# ═══════════════════════════════════════════════════════════════════════════
# LOCAL BEAD STORE — reads/writes .beads/issues.jsonl directly (no bd CLI)
# ═══════════════════════════════════════════════════════════════════════════

class LocalBeadStore:
    """JSONL-based bead store that bypasses the bd CLI entirely."""

    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.jsonl_path = self.repo_root / ".beads" / "issues.jsonl"
        self._beads: dict[str, dict] = {}
        self._deps: dict[str, list[dict]] = {}  # bead_id -> [{type, target}]
        self._load()

    def _load(self) -> None:
        if not self.jsonl_path.exists():
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            self.jsonl_path.touch()
            return
        for line in self.jsonl_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                bead = json.loads(line)
                if isinstance(bead, dict) and bead.get("id"):
                    self._beads[bead["id"]] = bead
            except json.JSONDecodeError:
                pass

    def _flush(self) -> None:
        lines = [json.dumps(b, default=str) for b in self._beads.values()]
        self.jsonl_path.write_text("\n".join(lines) + "\n" if lines else "")

    def show(self, bead_id: str) -> dict:
        bead = self._beads.get(bead_id)
        if not bead:
            raise KeyError(f"Bead not found: {bead_id}")
        return dict(bead)

    def create(self, title: str, description: str = "", issue_type: str = "task",
               priority: int = 1, labels: list[str] | None = None,
               parent: str | None = None) -> str:
        prefix = self.repo_root.name or "local"
        bead_id = f"{prefix}-{uuid.uuid4().hex[:3]}"
        now = datetime.now(timezone.utc).isoformat()
        bead = {
            "id": bead_id, "title": title, "description": description,
            "status": "open", "priority": priority, "issue_type": issue_type,
            "labels": labels or [], "parent": parent or "",
            "notes": "", "created_at": now, "updated_at": now,
        }
        self._beads[bead_id] = bead
        self._flush()
        return bead_id

    def update(self, bead_id: str, **kwargs: Any) -> None:
        bead = self._beads.get(bead_id)
        if not bead:
            raise KeyError(f"Bead not found: {bead_id}")
        bead.update(kwargs)
        bead["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._flush()

    def hook(self, bead_id: str) -> None:
        """Simulate ``bd hook`` — mark bead as in_progress (worktree attached)."""
        self.update(bead_id, status="in_progress")

    def close(self, bead_id: str, reason: str = "") -> None:
        self.update(bead_id, status="closed", notes=reason)

    def depend(self, bead_id: str, dep_type: str, target_bead_id: str) -> None:
        """Simulate ``bd depend <bead-id> <type> <target-bead-id>``."""
        deps = self._deps.setdefault(bead_id, [])
        deps.append({"type": dep_type, "target": target_bead_id})

    def list_beads(self, status: str | None = None, labels: list[str] | None = None) -> list[dict]:
        results = []
        for bead in self._beads.values():
            if status and bead.get("status") != status:
                continue
            if labels:
                bead_labels = set(bead.get("labels") or [])
                if not all(lbl in bead_labels for lbl in labels):
                    continue
            results.append(dict(bead))
        return results


class LocalBeadClient:
    """Drop-in replacement for BeadClient that uses LocalBeadStore."""

    def __init__(self, repo_root: str):
        self.repo_root = repo_root
        self._store = LocalBeadStore(repo_root)

    def show(self, bead_id: str) -> dict:
        return self._store.show(bead_id)

    def update(self, bead_id: str, status: str | None = None,
               notes: str | None = None, append_notes: str | None = None,
               labels_add: list[str] | None = None) -> None:
        kwargs: dict[str, Any] = {}
        if status:
            kwargs["status"] = status
        if notes:
            kwargs["notes"] = notes
        if append_notes:
            bead = self._store.show(bead_id)
            existing = bead.get("notes") or ""
            kwargs["notes"] = f"{existing}\n\n{append_notes}".strip()
        if labels_add:
            bead = self._store.show(bead_id)
            existing_labels = list(bead.get("labels") or [])
            for lbl in labels_add:
                if lbl not in existing_labels:
                    existing_labels.append(lbl)
            kwargs["labels"] = existing_labels
        self._store.update(bead_id, **kwargs)

    def hook(self, bead_id: str) -> None:
        """Simulate ``bd hook`` — attach worktree to bead."""
        self._store.hook(bead_id)

    def claim(self, bead_id: str) -> None:
        """Legacy — falls back to hook."""
        self._store.hook(bead_id)

    def close(self, bead_id: str, reason: str = "") -> None:
        self._store.close(bead_id, reason)

    def depend(self, bead_id: str, dep_type: str, target_bead_id: str) -> None:
        """Simulate ``bd depend``."""
        self._store.depend(bead_id, dep_type, target_bead_id)

    def create(self, title: str, description: str = "", issue_type: str = "task",
               priority: int = 1, labels: list[str] | None = None,
               parent: str | None = None) -> str:
        return self._store.create(title, description, issue_type, priority, labels, parent)

    def list(self, status: str | None = None, labels: list[str] | None = None) -> list[dict]:
        return self._store.list_beads(status, labels)

    def export(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# DRY-RUN PATCHES
# ═══════════════════════════════════════════════════════════════════════════

def _patch_test_runner_for_dry_run():
    from examples.polecat_swarm.subagents import test_runner as tr_module
    from examples.polecat_swarm.agents import qa_supervisor as qes_module

    class DryRunTestRunner(tr_module.TestRunner):
        def run(self, command: str) -> tr_module.TestRunResult:
            self.log.info("subagent_started", sub_agent="TestRunner")
            self.log.info("subagent_completed", sub_agent="TestRunner",
                          elapsed_s=0.0, status="success", exit_code=0)
            return tr_module.TestRunResult(
                command=command, exit_code=0,
                output=f"[DRY RUN] Would execute: {command}\n8 passed in 0.5s",
            )

    tr_module.TestRunner = DryRunTestRunner
    qes_module.TestRunner = DryRunTestRunner


def _patch_git_tools_for_dry_run():
    from examples.polecat_swarm.tools import git_tools as gt_module
    from examples.polecat_swarm.agents import release as re_module

    _original = gt_module.create_branch

    def safe_create_branch(cwd: str, branch: str) -> None:
        try:
            _original(cwd, branch)
        except Exception:
            pass

    gt_module.create_branch = safe_create_branch
    re_module.create_branch = safe_create_branch


# ═══════════════════════════════════════════════════════════════════════════
# MAYOR API LAUNCHER
# ═══════════════════════════════════════════════════════════════════════════

def start_mayor_api(port: int = 8787) -> Optional[subprocess.Popen]:
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn",
             "agentorchestrator.integrations.gastown.mayor_api:app",
             "--host", "0.0.0.0", "--port", str(port), "--log-level", "warning"],
            cwd=str(ROOT),
            env={**os.environ, "BEADS_REPO_ROOT": str(ROOT)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        if proc.poll() is not None:
            print(f"    {RED}Failed to start Mayor API{RESET}")
            return None
        print(f"    {GREEN}Mayor API running at http://localhost:{port}{RESET}")
        print(f"    Endpoints: /health | /convoys | /pipeline/{{id}} | /ws/swarm-events")
        return proc
    except Exception as exc:
        print(f"    {RED}Mayor API failed: {exc}{RESET}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET EVENT PUSHER — streams events to Mayor in real-time
# ═══════════════════════════════════════════════════════════════════════════

class MayorEventStream:
    """Streams events to Mayor API WebSocket as they happen (like SwarmLogBridge)."""

    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._queue: list[dict] = []
        self._ws = None
        self._loop = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        time.sleep(0.3)  # let the WS connect

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._connect())

    async def _connect(self):
        try:
            import websockets
            self._ws = await websockets.connect(self._ws_url)
            await self._ws.send(json.dumps({"type": "register", "caller": "pod"}))
        except Exception:
            self._ws = None

    def push(self, event: dict):
        """Push a single event to Mayor WS immediately."""
        if not self._ws or not self._loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._ws.send(json.dumps(event)), self._loop
            )
        except Exception:
            pass

    def stop(self):
        if self._ws and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
# POD SIMULATOR — simulates what entrypoint.py does for a single expert
# ═══════════════════════════════════════════════════════════════════════════

def simulate_pod(
    *,
    role: str,
    sub_bead_id: str,
    parent_bead: dict,
    swarm_config,
    convoy_id: str,
    configmap_name: str,
    repo_root: str,
    bead_client: LocalBeadClient,
    dry_run: bool,
    event_stream: Optional[MayorEventStream],
) -> dict:
    """Simulate what entrypoint.py does inside a K8s pod for one expert.

    Returns: {"status": ..., "gate_scores": ..., "notes": ..., "artifacts": [...], "elapsed_s": ...}
    """
    from agentorchestrator import AgentOrchestrator
    from examples.polecat_swarm.gateway_router import GatewayConfig, GatewayRouter
    from examples.polecat_swarm.pipeline import ROLE_TO_EXPERT
    from examples.polecat_swarm.tools.opencode_executor import DryRunExecutor
    from examples.polecat_swarm.types import ExpertResult, TraceContext

    expert_cls = ROLE_TO_EXPERT.get(role)
    if not expert_cls:
        return {"status": "failed", "notes": f"Unknown role: {role}", "gate_scores": {},
                "artifacts": [], "elapsed_s": 0}

    sub_bead = bead_client.show(sub_bead_id)

    def emit(event_name: str, **extra):
        payload = {
            "ts": round(time.time(), 3), "level": "INFO", "event": event_name,
            "trace_id": convoy_id, "span_id": sub_bead_id, "sub_span_id": "",
            "role": role, "repo": swarm_config.repo_name, **extra,
        }
        if event_stream:
            event_stream.push({"type": "log_event", "trace_id": convoy_id, "payload": payload})

    # ── 1. Pod starts ───────────────────────────────────────────────────
    print(f"  {CYAN}│{RESET}    {DIM}Pod environment:{RESET}")
    print(f"  {CYAN}│{RESET}      EXPERT_ROLE={role}")
    print(f"  {CYAN}│{RESET}      SWARM_CONFIG_REF={configmap_name}")
    print(f"  {CYAN}│{RESET}      GASTOWN_BEAD_ID={sub_bead_id}")

    emit("pod_started", bead_id=sub_bead_id, commit_sha=swarm_config.commit_sha or "")

    # ── 2. Hook bead (GT-native lifecycle) ─────────────────────────────
    bead_client.hook(sub_bead_id)
    hooked = bead_client.show(sub_bead_id)
    print(f"  {CYAN}│{RESET}    {DIM}Bead hooked:{RESET} {sub_bead_id} -> status={hooked['status']}")
    print(f"  {CYAN}│{RESET}    {DIM}In production: bd hook {sub_bead_id}{RESET}")
    emit("bead_hooked", bead_id=sub_bead_id)

    # ── 3. Read bead metadata (bd show) ────────────────────────────────
    print(f"  {CYAN}│{RESET}    {DIM}Bead metadata read:{RESET} bd show {sub_bead_id} --json")

    # ── 4. Git checkout (simulated) ─────────────────────────────────────
    commit_sha = swarm_config.commit_sha or ""
    if commit_sha:
        print(f"  {CYAN}│{RESET}    {DIM}Git checkout:{RESET} {commit_sha[:12]} (simulated)")

    # ── 5. Run the expert ───────────────────────────────────────────────
    expert_model = "claude-sonnet-4-5"
    for e in swarm_config.pipeline:
        if e.role == role:
            expert_model = e.model
            break

    emit("expert_started", model=expert_model, elapsed_s=0,
         services=list(swarm_config.services), skills=swarm_config.skills.for_role(role))

    print(f"  {CYAN}│{RESET}    {DIM}Running expert:{RESET} {role} (model: {expert_model})")

    expert_start = time.time()

    try:
        fallback = GatewayConfig(
            name="local", server_url="", oauth_endpoint="",
            client_id="", client_secret="", default_model=expert_model,
        )
        gateway_router = GatewayRouter(gateway_a=fallback)
        ao = AgentOrchestrator(name=f"polecat-{role.lower()}", isolated=True)

        expert = expert_cls(
            ao=ao, bead=sub_bead, swarm_config=swarm_config,
            worktree=repo_root, repo_root=repo_root,
            gateway_router=gateway_router,
        )

        if dry_run:
            expert.opencode_executor = DryRunExecutor()
        expert.bead_client = bead_client
        from agentorchestrator.integrations.gastown.bead_state_manager import BeadStateManager
        expert.state_manager = BeadStateManager(bead_client)

        result = expert.execute()
    except Exception as exc:
        result = ExpertResult(status="failed", notes=str(exc))

    elapsed = round(time.time() - expert_start, 2)

    # ── 6. Emit completion ──────────────────────────────────────────────
    emit("expert_completed", status=result.status, elapsed_s=elapsed,
         gate_scores=result.gate_scores)

    # ── 7. Close bead — GT daemon handles fan-out ───────────────────────
    if result.succeeded:
        bead_client.close(sub_bead_id, reason=result.notes[:500])
        print(f"  {CYAN}│{RESET}    {DIM}bd close {sub_bead_id} — GT daemon dispatches dependents{RESET}")
    else:
        bead_client.update(sub_bead_id, status="failed", notes=result.notes[:500])

    final = bead_client.show(sub_bead_id)
    print(f"  {CYAN}│{RESET}    {DIM}Bead updated:{RESET} {sub_bead_id} -> status={final['status']}")

    return {
        "status": result.status,
        "notes": result.notes[:500],
        "gate_scores": result.gate_scores,
        "artifacts": result.artifacts,
        "elapsed_s": elapsed,
        "succeeded": result.succeeded,
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — Mayor-centric flow
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Polecat Swarm — Local End-to-End Runner (Mayor-Centric)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--title", default="Add slide fade transition animations",
                        help="Bead title for the test task")
    parser.add_argument("--description", default="",
                        help="Bead description")
    parser.add_argument("--bead-id", default="",
                        help="Use an existing bead ID")
    parser.add_argument("--live", action="store_true",
                        help="Use real LLM calls")
    parser.add_argument("--no-mayor", action="store_true",
                        help="Skip starting Mayor API (dry output only)")
    parser.add_argument("--mayor-port", type=int, default=8787,
                        help="Mayor API port (default: 8787)")
    parser.add_argument("--repo-root", default=str(ROOT),
                        help="Repository root path")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    dry_run = not args.live

    if dry_run:
        _patch_test_runner_for_dry_run()
        _patch_git_tools_for_dry_run()

    banner("Polecat Swarm — Local End-to-End Runner")
    print(f"  {DIM}Simulates the full Mayor-centric production architecture locally{RESET}")
    print(f"  {DIM}Mode: {'DRY RUN (no LLM calls)' if dry_run else 'LIVE (real LLM calls)'}{RESET}")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 0: Preflight
    # ══════════════════════════════════════════════════════════════════════
    step_header(0, "Preflight Checks", "Verify repo, config, tools")

    git_ok = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=repo_root,
                            capture_output=True, check=False).returncode == 0
    step_output("Git repo", f"{'OK' if git_ok else 'NOT FOUND'} ({repo_root})")

    swarm_yaml = Path(repo_root) / ".swarm" / "swarm.yaml"
    step_output(".swarm/swarm.yaml", f"{'EXISTS' if swarm_yaml.exists() else 'MISSING'}")

    beads_dir = Path(repo_root) / ".beads"
    if not beads_dir.exists():
        beads_dir.mkdir(parents=True, exist_ok=True)
        (beads_dir / "issues.jsonl").touch()
    step_output(".beads/ directory", "OK")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    has_key = bool(api_key and api_key.startswith("sk-ant-"))
    step_output("API key", f"{'SET' if has_key else 'not set (dry-run only)'}")

    if args.live and not has_key:
        print(f"\n  {RED}ERROR: --live requires ANTHROPIC_API_KEY{RESET}")
        return 1

    step_done()

    # ══════════════════════════════════════════════════════════════════════
    # STEP 1: Start Mayor API (the orchestrator)
    # ══════════════════════════════════════════════════════════════════════
    step_header(1, "Start Mayor API", "Central orchestrator — receives dispatch requests, streams events to GUI")

    mayor_proc = None
    event_stream = None
    if not args.no_mayor:
        mayor_proc = start_mayor_api(port=args.mayor_port)
        if mayor_proc:
            event_stream = MayorEventStream(f"ws://localhost:{args.mayor_port}/ws/swarm-events")
            event_stream.start()
            step_done("Mayor API ready for dispatch")
        else:
            print(f"    {YELLOW}Continuing without Mayor API (events won't stream to GUI){RESET}")
            step_done("Mayor API skipped")
    else:
        print(f"    {DIM}Skipped (--no-mayor flag){RESET}")
        step_done("output-only mode")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 2: Create parent epic bead
    # ══════════════════════════════════════════════════════════════════════
    step_header(2, "Create Parent Epic Bead", "Dev/PM creates epic via `bd create` — Mayor receives this bead_id")

    bead_store = LocalBeadStore(repo_root)

    if args.bead_id:
        try:
            parent_bead = bead_store.show(args.bead_id)
            step_output("Using existing bead", f"{parent_bead['id']} — {parent_bead.get('title', '')}")
        except KeyError:
            print(f"    {RED}Bead {args.bead_id} not found{RESET}")
            return 1
    else:
        desc = args.description or f"Local swarm test — verify full pipeline flow"
        parent_id = bead_store.create(
            title=args.title, description=desc,
            labels=["polecat-swarm", "local-test"],
        )
        parent_bead = bead_store.show(parent_id)

    step_output("Bead ID", parent_bead["id"])
    step_output("Title", parent_bead["title"])
    step_output("Status", parent_bead["status"])
    step_output("Description", parent_bead.get("description", "")[:80])
    print(f"  {CYAN}│{RESET}")
    print(f"  {CYAN}│{RESET}    {DIM}In production: bd create \"{parent_bead['title']}\" --type epic --priority 1{RESET}")
    step_done(f"epic bead {parent_bead['id']} ready for dispatch")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 3: Mayor receives POST /chat — resolves pipeline
    # ══════════════════════════════════════════════════════════════════════
    step_header(3, "Mayor: Resolve Pipeline", "POST /chat → clone repo, read .swarm/swarm.yaml, build SwarmConfig")

    from agentorchestrator.integrations.gastown.swarm_config import SwarmConfigLoader
    from agentorchestrator.integrations.gastown.agent_registry import AgentRegistry
    from agentorchestrator.integrations.gastown.convoy_manager import compute_execution_groups

    agent_reg = AgentRegistry()
    config_loader = SwarmConfigLoader(agent_registry=agent_reg)

    commit_sha = ""
    if git_ok:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root,
                                capture_output=True, text=True, check=False)
        commit_sha = result.stdout.strip() if result.returncode == 0 else ""

    convoy_id = f"convoy-{uuid.uuid4().hex[:8]}"

    print(f"  {CYAN}│{RESET}    {DIM}In production: git clone --depth=1 <repo_url> /tmp/xxx{RESET}")
    print(f"  {CYAN}│{RESET}    {DIM}Locally: using repo at {repo_root}{RESET}")

    swarm_config = config_loader.load(
        repo_root, f"file://{repo_root}",
        commit_sha=commit_sha, trace_id=convoy_id,
    )
    enabled = [e for e in swarm_config.pipeline if e.enabled]

    step_output("Repo", swarm_config.repo_name)
    step_output("Language", swarm_config.language)
    step_output("Framework", str(getattr(swarm_config, 'framework', 'n/a')))
    step_output("Test cmd", str(swarm_config.test_command))
    step_output("Commit SHA", commit_sha[:12] or "(none)")
    step_output("Convoy ID", convoy_id)
    step_output("Pipeline", " → ".join(e.role for e in enabled))
    step_output("Models", ", ".join(f"{e.role}={e.model}" for e in enabled))
    step_output("Services", str(swarm_config.services or "(none)"))
    step_done(f"pipeline resolved: {len(enabled)} experts")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 4: Mayor creates sub-beads + wires bd depend
    # ══════════════════════════════════════════════════════════════════════
    step_header(4, "Mayor: Create Sub-Beads + Wire Dependencies",
                "One child bead per expert, then bd depend for each DAG edge")

    bead_client = LocalBeadClient(repo_root)
    sub_bead_ids: dict[str, str] = {}

    # 4a. Create sub-beads with role-scoped descriptions
    from agentorchestrator.integrations.gastown.mayor_api import _build_expert_description

    # ConfigMap name is deterministic — embed in labels so pods can self-discover.
    configmap_name = f"swarm-config-{parent_bead['id']}"

    for expert_cfg in enabled:
        expert_desc = _build_expert_description(
            expert=expert_cfg,
            parent_title=parent_bead["title"],
            parent_description=parent_bead.get("description", ""),
            swarm_config=swarm_config,
        )
        sub_id = bead_client.create(
            title=f"[{expert_cfg.role}] {parent_bead['title']}",
            description=expert_desc,
            labels=[expert_cfg.role.lower(), "polecat-swarm", convoy_id, configmap_name],
            parent=parent_bead["id"],
        )
        sub_bead_ids[expert_cfg.role] = sub_id
        print(f"  {CYAN}│{RESET}    {role_tag(expert_cfg.role)} → bead {sub_id}")
        # Show first line of role description
        first_line = expert_desc.split("\n")[0]
        print(f"  {CYAN}│{RESET}      {DIM}{first_line}{RESET}")

    print(f"  {CYAN}│{RESET}")

    # 4b. Wire bead-level dependencies via bd depend
    dep_graph = swarm_config.to_dependency_graph()
    dep_count = 0
    print(f"  {CYAN}│{RESET}    {DIM}Wiring bead-level dependencies:{RESET}")
    for expert_cfg in enabled:
        for dep_role in expert_cfg.depends_on:
            if dep_role in sub_bead_ids:
                bead_client.depend(
                    sub_bead_ids[expert_cfg.role],
                    "blocks",
                    sub_bead_ids[dep_role],
                )
                dep_count += 1
                print(f"  {CYAN}│{RESET}      bd depend {sub_bead_ids[expert_cfg.role]} blocks {sub_bead_ids[dep_role]}"
                      f"  {DIM}({expert_cfg.role} blocked by {dep_role}){RESET}")

    if dep_count == 0:
        print(f"  {CYAN}│{RESET}      {DIM}(no explicit dependencies — sequential fallback){RESET}")

    print(f"  {CYAN}│{RESET}")
    print(f"  {CYAN}│{RESET}    {DIM}In production: bd create \"[PRE] ...\" --labels pre,polecat-swarm{RESET}")
    print(f"  {CYAN}│{RESET}    {DIM}               bd depend <ees-bead> blocks <pre-bead>{RESET}")
    step_done(f"{len(sub_bead_ids)} sub-beads, {dep_count} dependency edges")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 5: MEOW Planning — gt convoy stage (local shim)
    # ══════════════════════════════════════════════════════════════════════
    execution_groups = compute_execution_groups(dep_graph)
    has_parallel = any(len(g) > 1 for g in execution_groups)
    has_explicit_deps = any(e.depends_on for e in enabled)

    step_header(5, "gt convoy stage (MEOW Planning)",
                "Validate DAG, compute waves, check rig availability")

    print(f"  {CYAN}│{RESET}    {DIM}Dependency graph:{RESET}")
    for role, deps in dep_graph.items():
        dep_str = ", ".join(deps) if deps else "(root)"
        print(f"  {CYAN}│{RESET}      {role_tag(role)} depends on: {dep_str}")

    print(f"  {CYAN}│{RESET}")
    print(f"  {CYAN}│{RESET}    {DIM}MEOW waves (execution groups):{RESET}")
    for gidx, group in enumerate(execution_groups):
        parallel_tag = f" {YELLOW}← parallel!{RESET}" if len(group) > 1 else ""
        roles_str = " + ".join(role_tag(r) for r in group)
        print(f"  {CYAN}│{RESET}      Wave {gidx}: {roles_str}{parallel_tag}")

    print(f"  {CYAN}│{RESET}")
    if has_parallel:
        print(f"  {CYAN}│{RESET}    {GREEN}Parallel execution enabled{RESET} — "
              f"{'explicit depends_on' if has_explicit_deps else 'inferred from pipeline order'}")
    else:
        print(f"  {CYAN}│{RESET}    {DIM}Sequential execution — all waves have 1 expert{RESET}")
    print(f"  {CYAN}│{RESET}")
    print(f"  {CYAN}│{RESET}    {DIM}In production: gt convoy stage {parent_bead['id']}{RESET}")
    print(f"  {CYAN}│{RESET}    {DIM}GT validates the DAG, computes MEOW waves, checks rig prefixes{RESET}")
    step_done(f"{len(execution_groups)} waves, {'parallel' if has_parallel else 'sequential'}")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 6: gt convoy launch — dispatch Wave 1, Mayor is done
    # ══════════════════════════════════════════════════════════════════════
    root_group = execution_groups[0] if execution_groups else [enabled[0].role]
    root_desc = " + ".join(role_tag(r) for r in root_group)
    step_header(6, "gt convoy launch",
                f"Dispatch Wave 1: {root_desc} — GT daemon handles all fan-out from here")

    # Store SwarmConfig for pods
    from agentorchestrator.integrations.gastown.configmap_store import write_swarm_configmap
    configmap_name = write_swarm_configmap(
        bead_id=parent_bead["id"],
        swarm_config=swarm_config,
        namespace="local",
    )
    step_output("SwarmConfig stored", configmap_name)

    for root_role in root_group:
        print(f"  {CYAN}│{RESET}    Launching: {role_tag(root_role)} (bead: {sub_bead_ids[root_role]})")

    print(f"  {CYAN}│{RESET}")
    print(f"  {CYAN}│{RESET}    {DIM}In production: gt convoy launch {convoy_id}{RESET}")
    print(f"  {CYAN}│{RESET}    {DIM}GT dispatches Wave 1 roots — daemon polls every 5s for closures{RESET}")
    print(f"  {CYAN}│{RESET}")
    print(f"  {CYAN}│{RESET}    {YELLOW}Mayor's job is DONE after launch.{RESET}")
    print(f"  {CYAN}│{RESET}    {YELLOW}GT daemon (runEventPoll) handles all subsequent fan-out.{RESET}")
    step_done(f"Wave 1 launched — {len(root_group)} root expert(s)")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 7: Execution — GT daemon simulated as wave-by-wave execution
    # ══════════════════════════════════════════════════════════════════════
    banner("Pipeline Execution (GT Daemon Simulation)")
    if has_parallel:
        print(f"  {DIM}Experts in the same wave run in parallel (simulated via threads){RESET}")
        print(f"  {DIM}GT daemon detects bd close → feedNextReadyIssue → dispatch next wave{RESET}")
    else:
        print(f"  {DIM}Sequential execution — daemon dispatches each wave after previous completes{RESET}")

    pipeline_start = time.time()
    results: dict[str, dict] = {}
    halted = False

    for gidx, group in enumerate(execution_groups):
        is_last_group = (gidx == len(execution_groups) - 1)

        if len(group) > 1:
            section(f"Wave {gidx}: {' + '.join(group)} (PARALLEL)")
        else:
            section(f"Wave {gidx}: {group[0]}")

        def _run_one_pod(role: str) -> tuple[str, dict]:
            """Run a single pod and return (role, result)."""
            sub_bead_id = sub_bead_ids[role]
            print(f"  {status_icon('running')} {role_tag(role)} Pod booting...")
            print(f"  {CYAN}│{RESET}")

            pod_result = simulate_pod(
                role=role,
                sub_bead_id=sub_bead_id,
                parent_bead=parent_bead,
                swarm_config=swarm_config,
                convoy_id=convoy_id,
                configmap_name=configmap_name,
                repo_root=repo_root,
                bead_client=bead_client,
                dry_run=dry_run,
                event_stream=event_stream,
            )
            return (role, pod_result)

        # Run experts in this wave — parallel if >1, sequential if 1
        if len(group) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(group)) as pool:
                futures = {pool.submit(_run_one_pod, role): role for role in group}
                group_results = {}
                for future in concurrent.futures.as_completed(futures):
                    role, pod_result = future.result()
                    group_results[role] = pod_result
        else:
            role, pod_result = _run_one_pod(group[0])
            group_results = {role: pod_result}

        # Display results for this wave
        for role in group:
            pod_result = group_results[role]
            results[role] = pod_result
            icon = status_icon(pod_result["status"])
            print(f"  {CYAN}│{RESET}")
            print(f"  {icon} {role_tag(role)} {pod_result['status']} ({pod_result['elapsed_s']}s)")

            if pod_result.get("notes"):
                note = pod_result["notes"][:120].replace("\n", " ")
                print(f"  {CYAN}│{RESET}    {DIM}{note}{RESET}")

            if pod_result.get("gate_scores"):
                scores = ", ".join(f"{k}={v:.2f}" for k, v in pod_result["gate_scores"].items())
                print(f"  {CYAN}│{RESET}    Gate scores: {GREEN}{scores}{RESET}")

            if pod_result.get("artifacts"):
                for art in pod_result["artifacts"][:4]:
                    print(f"  {CYAN}│{RESET}    📄 {Path(art).name}")

        # Check for failures in this wave
        group_failed = [r for r in group if not group_results[r].get("succeeded")]
        if group_failed:
            print(f"  {CYAN}│{RESET}")
            print(f"  {CYAN}│{RESET}    {RED}{BOLD}Pipeline HALTED — "
                  f"{', '.join(group_failed)} failed in wave {gidx}{RESET}")
            halted = True
            break

        # GT daemon detects closures → dispatches next wave
        if not is_last_group:
            next_group = execution_groups[gidx + 1]
            next_desc = " + ".join(role_tag(r) for r in next_group)
            print(f"  {CYAN}│{RESET}")
            print(f"  {CYAN}│{RESET}    {BOLD}→ GT daemon: wave {gidx} complete, dispatching wave {gidx + 1}: {next_desc}{RESET}")
            print(f"  {CYAN}│{RESET}    {DIM}runEventPoll → CheckConvoysForIssue → feedNextReadyIssue{RESET}")
        else:
            print(f"  {CYAN}│{RESET}")
            print(f"  {CYAN}│{RESET}    {GREEN}{BOLD}Pipeline complete — all waves executed{RESET}")

            # Last-expert cleanup
            if "RE" in group:
                print(f"  {CYAN}│{RESET}    {DIM}Deleting ConfigMap: {configmap_name}{RESET}")

            if event_stream:
                event_stream.push({
                    "type": "log_event", "trace_id": convoy_id,
                    "payload": {"ts": round(time.time(), 3), "level": "INFO",
                                "event": "convoy_complete", "role": "",
                                "repo": swarm_config.repo_name, "trace_id": convoy_id,
                                "span_id": parent_bead["id"], "sub_span_id": "",
                                "elapsed_s": round(time.time() - pipeline_start, 2)},
                })

    total_elapsed = round(time.time() - pipeline_start, 2)

    # ══════════════════════════════════════════════════════════════════════
    # STEP 8: Final Summary + Observability
    # ══════════════════════════════════════════════════════════════════════
    banner("Pipeline Summary")

    overall = "HALTED" if halted else "COMPLETE"
    color = RED if halted else GREEN
    print(f"  Convoy:    {convoy_id}")
    print(f"  Duration:  {total_elapsed}s")
    print(f"  Status:    {color}{BOLD}{overall}{RESET}")
    print()

    for role, res in results.items():
        icon = status_icon(res["status"])
        elapsed_str = f'{res.get("elapsed_s", 0):.1f}s'
        gate = ""
        if res.get("gate_scores"):
            gate = f"  ({', '.join(f'{k}={v:.2f}' for k, v in res['gate_scores'].items())})"
        print(f"    {icon} {role_tag(role):30s}  {elapsed_str:>8s}  {res['status']}{gate}")

    # Observability hint
    section("Observability")
    print(f"    {DIM}In production:{RESET}")
    print(f"    {DIM}  gt feed --problems       # Live TUI — GUPP violations, stalled polecats{RESET}")
    print(f"    {DIM}  gt dashboard              # Web dashboard for convoy status{RESET}")
    print(f"    {DIM}  gt nudge <bead-id>        # Re-inject context for restarted pods{RESET}")

    # Artifacts
    specs_dir = Path(repo_root) / ".gastown" / "specs"
    if specs_dir.exists():
        new_artifacts = []
        for artifact in sorted(specs_dir.rglob("*")):
            if artifact.is_file():
                for sub_id in sub_bead_ids.values():
                    if sub_id in str(artifact):
                        new_artifacts.append(artifact)
                        break

        if new_artifacts:
            section("Artifacts Written (this run)")
            for art in new_artifacts:
                size = art.stat().st_size
                rel = art.relative_to(specs_dir)
                print(f"    📄 {rel}  ({size:,} bytes)")

    # Query Mayor API if running
    if mayor_proc:
        section("Mayor API State")
        try:
            import httpx
            resp = httpx.get(f"http://localhost:{args.mayor_port}/convoys", timeout=3)
            convoys_data = resp.json()
            print(f"    GET /convoys:")
            print(f"    {json.dumps(convoys_data, indent=4)}")
        except Exception as exc:
            print(f"    {YELLOW}Could not query Mayor API: {exc}{RESET}")

    # Final status
    banner("Run Complete")
    print(f"  Status:    {color}{BOLD}{overall}{RESET}")
    print(f"  Duration:  {total_elapsed}s")
    print(f"  Parent:    {parent_bead['id']} — {parent_bead['title']}")
    print(f"  Convoy:    {convoy_id}")

    final_parent = bead_store.show(parent_bead["id"])
    print(f"  Bead state: {final_parent.get('status', 'unknown')}")

    if mayor_proc:
        print(f"\n  {CYAN}Mayor API still running at http://localhost:{args.mayor_port}{RESET}")
        print(f"  GUI can connect to ws://localhost:{args.mayor_port}/ws/swarm-events")
        print(f"  Press Ctrl+C to stop...")
        try:
            mayor_proc.wait()
        except KeyboardInterrupt:
            mayor_proc.terminate()
            mayor_proc.wait()
            print(f"\n  Mayor API stopped.")

    if event_stream:
        event_stream.stop()

    return 1 if halted else 0


if __name__ == "__main__":
    raise SystemExit(main())
