"""Contracts for the Coder Pad MVP autonomous issue flow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TaskContext:
    """Normalized task payload consumed by the workflow."""

    task_id: str
    bead_id: str | None
    description: str
    repo_path: str
    labels: list[str] = field(default_factory=list)
    priority: int = 2
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoderOutput:
    """Output from coding supervisor execution."""

    plan: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchBrief:
    """Lightweight context brief for QA/docs."""

    summary: str
    impacted_files: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QAOutput:
    """Output from QA supervisor stack."""

    scenarios: list[str] = field(default_factory=list)
    review_notes: list[str] = field(default_factory=list)
    test_plan: list[str] = field(default_factory=list)
    doc_impact: list[str] = field(default_factory=list)
    handoff_requests: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocsOutput:
    """Output from docs supervisor stack."""

    api_docs: list[str] = field(default_factory=list)
    release_notes: list[str] = field(default_factory=list)
    runbook_updates: list[str] = field(default_factory=list)
    acknowledgements: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionEvidence:
    """Captured execution evidence from worktree command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    changed_files: list[str] = field(default_factory=list)
    patch_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SuiteResult:
    """Top-level workflow output persisted by the entrypoint."""

    status: str
    task_id: str
    summary: str
    coder: dict[str, Any]
    qa: dict[str, Any]
    docs: dict[str, Any]
    execution: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
