"""Bead state transitions and structured notes for Polecat Swarm."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .bead_client import BeadClient

logger = logging.getLogger(__name__)

VALID_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress"},
    "in_progress": {"blocked", "failed", "done"},
    "blocked": {"open"},
    "failed": {"open"},
    "done": set(),
}


class InvalidTransitionError(RuntimeError):
    """Raised when bead transition violates the finite-state machine."""


@dataclass
class CompletionSummary:
    """Final bead summary persisted when a run reaches done."""

    bead_id: str
    bead_title: str
    repo_name: str
    pipeline_run: list[str]
    duration_seconds: float
    pr_url: str
    what_was_built: str
    key_decisions: list[str]
    files_changed: list[str]
    services_used: list[str]
    gate_results: dict[str, str]
    labels: list[str]
    commit_sha: str
    trace_id: str

    def render(self) -> str:
        decisions_md = "\n".join(f"- {d}" for d in self.key_decisions) or "- none"
        files_md = "\n".join(f"- {f}" for f in self.files_changed) or "- none"
        gates_md = "\n".join(f"- {role}: {result}" for role, result in self.gate_results.items()) or "- none"
        duration_str = f"{int(self.duration_seconds // 60)}m {int(self.duration_seconds % 60)}s"

        return f"""## Swarm Completion Summary

**Bead**: {self.bead_id} — {self.bead_title}
**Repo**: {self.repo_name}
**Commit**: {self.commit_sha}
**Pipeline run**: {' -> '.join(self.pipeline_run)}
**Duration**: {duration_str}
**PR**: {self.pr_url}
**Trace**: {self.trace_id}

---

### What was built
{self.what_was_built}

### Key decisions
{decisions_md}

### Files changed
{files_md}

### Services used
{', '.join(self.services_used) if self.services_used else 'none'}

### Gate results
{gates_md}

### Labels
{', '.join(self.labels)}
"""


@dataclass
class BlockedNote:
    reason: str
    child_bead_id: str = ""

    def render(self) -> str:
        child_line = f"\n**Child bead created**: {self.child_bead_id}" if self.child_bead_id else ""
        return f"""## Blocked

**Reason**: {self.reason}{child_line}

Re-queue this bead once the blocking issue is resolved.
"""


@dataclass
class FailedNote:
    stage: str
    output_tail: str
    gate_scores: dict[str, str | float] = field(default_factory=dict)

    def render(self) -> str:
        gate_line = ""
        if self.gate_scores:
            pairs = ", ".join(f"{k}={v}" for k, v in self.gate_scores.items())
            gate_line = f"\n**Gate scores**: {pairs}"
        return f"""## Failed — {self.stage} Gate
{gate_line}
**Output (last 30 lines)**:
```
{self.output_tail[-2000:]}
```

**Action**: Bead re-opened for manual review or re-dispatch.
"""


class BeadStateManager:
    """Single owner of all bead state transitions."""

    def __init__(self, bead_client: BeadClient):
        self._client = bead_client

    def claim(self, bead_id: str) -> None:
        """Legacy claim — prefer ``hook()`` for GT-native lifecycle."""
        self._client.claim(bead_id)

    def hook(self, bead_id: str) -> None:
        """Attach a worktree hook to the bead (GT-native pod lifecycle).

        Pods should call this on startup instead of ``claim()``.
        ``bd hook`` creates a persistent git worktree and marks the
        bead as actively worked on.
        """
        self._client.hook(bead_id)

    def block(self, bead_id: str, reason: str, child_bead_id: str = "") -> None:
        note = BlockedNote(reason=reason, child_bead_id=child_bead_id)
        self._transition(bead_id, "blocked", note.render())

    def fail(
        self,
        bead_id: str,
        stage: str,
        output: str,
        gate_scores: dict[str, str | float] | None = None,
    ) -> None:
        note = FailedNote(stage=stage, output_tail=output, gate_scores=gate_scores or {})
        self._transition(bead_id, "failed", note.render())

    def close_with_summary(self, bead_id: str, summary: CompletionSummary) -> None:
        self._transition(bead_id, "done", summary.render())

    def close(self, bead_id: str, note: str = "Completed") -> None:
        self._transition(bead_id, "done", note)

    def annotate(self, bead_id: str, note: str) -> None:
        current = self._client.show(bead_id)
        existing = str(current.get("notes", "") or "")
        merged = f"{existing}\n\n{note}".strip()
        self._client.update(bead_id, notes=merged)

    def _transition(self, bead_id: str, to_state: str, note: str) -> None:
        current = self._client.show(bead_id)
        from_state = str(current.get("status", "unknown"))
        allowed = VALID_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            logger.error(
                "bead_transition_invalid bead_id=%s from_state=%s to_state=%s allowed=%s",
                bead_id,
                from_state,
                to_state,
                sorted(allowed),
            )
            raise InvalidTransitionError(
                f"Cannot transition bead {bead_id} from '{from_state}' to '{to_state}'. "
                f"Allowed: {sorted(allowed)}"
            )

        self._client.update(bead_id, status=to_state, notes=note)
        logger.info(
            "bead_transition bead_id=%s from_state=%s to_state=%s",
            bead_id,
            from_state,
            to_state,
        )
