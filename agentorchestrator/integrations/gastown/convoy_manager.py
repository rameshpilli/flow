"""Gastown convoy/sling helpers.

All pod dispatches should route through ``gt sling``.
The MEOW planner lives in GT — dependencies are expressed at the bead
level via ``bd depend`` and the convoy lifecycle uses the two-phase
``gt convoy stage`` → ``gt convoy launch`` workflow.  GT's daemon
(``runEventPoll`` every 5 s) detects bead closures and automatically
dispatches dependents via ``feedNextReadyIssue``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommandOutput:
    returncode: int
    stdout: str
    stderr: str


def compute_execution_groups(
    dependency_graph: dict[str, list[str]],
) -> list[list[str]]:
    """Thin local shim: Kahn's topological sort into parallel groups.

    Used **only** when ``gt`` is not available (local dev / tests).
    In production GT's convoy scheduler performs the real MEOW planning.
    """
    in_degree: dict[str, int] = {role: 0 for role in dependency_graph}
    dependents: dict[str, list[str]] = {role: [] for role in dependency_graph}

    for role, deps in dependency_graph.items():
        for dep in deps:
            if dep not in in_degree:
                raise ValueError(
                    f"Expert '{role}' depends on '{dep}' which is not in the graph"
                )
            dependents[dep].append(role)
            in_degree[role] += 1

    groups: list[list[str]] = []
    queue = deque(role for role, deg in in_degree.items() if deg == 0)

    if not queue and dependency_graph:
        raise ValueError("Circular dependency detected — no root experts found")

    while queue:
        group = sorted(queue)  # deterministic order within a group
        groups.append(group)
        next_queue: deque[str] = deque()
        for role in group:
            for dependent in dependents[role]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_queue.append(dependent)
        queue = next_queue

    visited = {role for g in groups for role in g}
    if visited != set(dependency_graph):
        missing = set(dependency_graph) - visited
        raise ValueError(f"Circular dependency detected involving: {sorted(missing)}")

    return groups


class ConvoyManager:
    """Wrapper around ``gt convoy`` and ``gt sling`` commands.

    Production flow (GT available):
      1. Mayor creates sub-beads and wires ``bd depend`` for each edge
      2. ``gt convoy stage <epic-id>`` — validates the DAG, computes
         MEOW waves, checks rig prefixes
      3. ``gt convoy launch <convoy-id>`` — dispatches Wave 1 (roots)
      4. GT daemon takes over — polls every 5 s, detects bead closures,
         calls ``feedNextReadyIssue`` to sling unblocked dependents

    Local fallback (no ``gt``):
      Generates a local convoy id and the caller uses
      :func:`compute_execution_groups` for a lightweight shim.
    """

    def __init__(self, workspace: str):
        self.workspace = workspace

    def _run(self, cmd: list[str], *, extra_env: dict[str, str] | None = None) -> CommandOutput:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        process = subprocess.run(
            cmd,
            cwd=self.workspace,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        return CommandOutput(
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )

    def create_convoy(
        self,
        name: str,
        bead_ids: list[str],
    ) -> str:
        """Create convoy tracking the given bead IDs and return convoy_id.

        Dependencies are NOT embedded here — they live on beads via
        ``bd depend``.  This just groups beads into a convoy.
        """
        if shutil.which("gt") is None:
            return f"convoy-{uuid.uuid4().hex[:8]}"

        cmd = ["gt", "convoy", "create", name, *bead_ids]
        result = self._run(cmd)

        if result.returncode != 0:
            return f"convoy-{uuid.uuid4().hex[:8]}"

        stdout = result.stdout.strip()
        if not stdout:
            return f"convoy-{uuid.uuid4().hex[:8]}"

        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                convoy_id = data.get("id") or data.get("convoy_id")
                if convoy_id:
                    return str(convoy_id)
        except Exception:
            pass

        return stdout.splitlines()[-1].strip()

    def stage_convoy(self, epic_bead_id: str) -> CommandOutput:
        """Stage a convoy from a parent epic bead.

        ``gt convoy stage <epic-id>`` validates the dependency DAG
        (checking for cycles, missing deps, rig availability), computes
        MEOW waves (parallel execution groups), and returns the staged
        convoy plan for review.

        Returns the raw :class:`CommandOutput` so the caller can inspect
        or log the plan before launching.
        """
        if shutil.which("gt") is None:
            return CommandOutput(
                returncode=0,
                stdout=json.dumps({"convoy_id": f"local-convoy-{uuid.uuid4().hex[:8]}", "staged": True}),
                stderr="",
            )

        result = self._run(["gt", "convoy", "stage", epic_bead_id])
        if result.returncode != 0:
            logger.error(
                "gt convoy stage failed: %s",
                result.stderr.strip() or result.stdout.strip(),
            )
        return result

    def launch_convoy(self, convoy_id: str) -> CommandOutput:
        """Launch a previously staged convoy.

        ``gt convoy launch <convoy-id>`` dispatches Wave 1 (DAG roots).
        From here GT's daemon takes over — it polls every 5 s, detects
        bead closures, and auto-dispatches unblocked dependents via
        ``feedNextReadyIssue``.  Mayor is done after this call.

        Returns the raw :class:`CommandOutput`.
        """
        if shutil.which("gt") is None:
            return CommandOutput(
                returncode=0,
                stdout=json.dumps({"launched": True, "convoy_id": convoy_id}),
                stderr="",
            )

        result = self._run(["gt", "convoy", "launch", convoy_id])
        if result.returncode != 0:
            logger.error(
                "gt convoy launch failed: %s",
                result.stderr.strip() or result.stdout.strip(),
            )
        return result

    def sling(self, bead_id: str, rig: str, *, agent: str = "opencode", env: dict[str, str] | None = None) -> None:
        """Sling a bead to an expert pod via Gastown."""
        if shutil.which("gt") is None:
            return

        cmd = ["gt", "sling", bead_id, rig, "--agent", agent, "--force"]
        for key, value in (env or {}).items():
            if not value:
                continue
            cmd.extend(["--env", f"{key}={value}"])

        result = self._run(cmd)
        # Compatibility fallback for older/newer gt sling variants that do not support --env.
        if result.returncode != 0 and env and "unknown flag: --env" in (result.stderr or ""):
            fallback = ["gt", "sling", bead_id, rig, "--agent", agent, "--force"]
            filtered_env = {k: v for k, v in env.items() if v}
            result = self._run(fallback, extra_env=filtered_env)

        if result.returncode != 0:
            raise RuntimeError(
                f"gt sling failed for bead {bead_id}: {result.stderr.strip() or result.stdout.strip()}"
            )

    def list_rigs(self) -> list[str]:
        """Best-effort rig discovery."""
        if shutil.which("gt") is None:
            return []
        result = self._run(["gt", "rig", "list"])
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
