"""Thin `bd` CLI wrapper for Polecat Swarm integrations."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any


class BeadClientError(RuntimeError):
    """Raised when a `bd` command fails or returns invalid output."""


@dataclass
class CommandResult:
    """Captured command execution result for diagnostics."""

    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str


class BeadClient:
    """Shell-based Beads client.

    This intentionally shells out to `bd` (instead of importing internals) so
    runtime behavior matches operator pods and local CLI behavior.
    """

    def __init__(self, repo_root: str, sandbox: bool | None = None):
        self.repo_root = repo_root
        if sandbox is None:
            raw = os.getenv("BD_SANDBOX", "true").strip().lower()
            sandbox = raw in {"1", "true", "yes", "on"}
        self._sandbox = ["--sandbox"] if sandbox else []

    def _run(self, cmd: list[str]) -> CommandResult:
        process = subprocess.run(
            ["bd", *self._sandbox, *cmd],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        result = CommandResult(
            cmd=cmd,
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )
        if process.returncode != 0:
            raise BeadClientError(
                f"bd command failed: {' '.join(shlex.quote(c) for c in cmd)}\n"
                f"stdout:\n{process.stdout}\n"
                f"stderr:\n{process.stderr}"
            )
        return result

    @staticmethod
    def _parse_json_payload(raw: str) -> dict[str, Any] | list[dict[str, Any]]:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        raise BeadClientError("Unexpected JSON payload shape from bd")

    def show(self, bead_id: str) -> dict[str, Any]:
        payload = self._parse_json_payload(self._run(["show", bead_id, "--json"]).stdout)
        if isinstance(payload, list):
            if not payload:
                raise BeadClientError(f"No bead found for id {bead_id}")
            return payload[0]
        return payload

    def update(
        self,
        bead_id: str,
        status: str | None = None,
        notes: str | None = None,
        append_notes: str | None = None,
        labels_add: list[str] | None = None,
    ) -> None:
        cmd = ["update", bead_id]
        if status:
            cmd.extend(["--status", status])
        if notes:
            cmd.extend(["--notes", notes])
        if append_notes:
            cmd.extend(["--append-notes", append_notes])
        for label in labels_add or []:
            cmd.extend(["--label", label])
        self._run(cmd)

    def claim(self, bead_id: str) -> None:
        """Legacy claim — prefer ``hook()`` for GT-native pod lifecycle."""
        self._run(["update", bead_id, "--claim"])

    def hook(self, bead_id: str) -> None:
        """Attach a worktree hook to the bead (GT-native pod lifecycle).

        ``bd hook <bead-id>`` creates a persistent git worktree for the
        bead and marks it as actively worked on.  Pods should call this
        instead of ``claim()``.
        """
        self._run(["hook", bead_id])

    def close(self, bead_id: str, reason: str) -> None:
        """Close a bead — ``bd close <bead-id> -r <reason>``.

        In production GT's daemon detects this closure event and
        automatically dispatches any dependents whose deps are now
        fully satisfied (the convoy scheduler's ``feedNextReadyIssue``).
        """
        self._run(["close", bead_id, "-r", reason])

    def depend(
        self,
        bead_id: str,
        dependency_type: str,
        target_bead_id: str,
    ) -> None:
        """Declare a bead-level dependency.

        ``bd depend <bead-id> <type> <target-bead-id>``

        *dependency_type* is one of: ``blocks``, ``waits-for``,
        ``conditional-blocks``, ``merge-blocks``.

        Example: ``bd depend bead-ees blocks bead-pre`` means
        EES is blocked until PRE closes.
        """
        valid_types = {"blocks", "waits-for", "conditional-blocks", "merge-blocks"}
        if dependency_type not in valid_types:
            raise BeadClientError(
                f"Invalid dependency type '{dependency_type}'. "
                f"Valid: {sorted(valid_types)}"
            )
        self._run(["depend", bead_id, dependency_type, target_bead_id])

    def export(self) -> None:
        self._run(["export"])

    def create(
        self,
        title: str,
        description: str = "",
        issue_type: str = "task",
        priority: int = 1,
        labels: list[str] | None = None,
        parent: str | None = None,
    ) -> str:
        cmd = [
            "create",
            title,
            "--description",
            description,
            "--type",
            issue_type,
            "-p",
            str(priority),
            "--json",
        ]
        if parent:
            cmd.extend(["--parent", parent])
        for label in labels or []:
            cmd.extend(["--label", label])

        stdout = self._run(cmd).stdout.strip()
        if not stdout:
            raise BeadClientError("`bd create` returned empty output")

        try:
            payload = self._parse_json_payload(stdout)
            if isinstance(payload, list):
                if payload and payload[0].get("id"):
                    return str(payload[0]["id"])
            if isinstance(payload, dict) and payload.get("id"):
                return str(payload["id"])
        except Exception:
            pass

        # Fallback for non-json output shape in older bd versions.
        return stdout.splitlines()[-1].strip()

    def list(self, status: str | None = None, labels: list[str] | None = None) -> list[dict[str, Any]]:
        cmd = ["list", "--json"]
        if status:
            cmd.extend(["--status", status])
        for label in labels or []:
            cmd.extend(["--label", label])
        payload = self._parse_json_payload(self._run(cmd).stdout)
        if isinstance(payload, dict):
            return [payload]
        return payload
