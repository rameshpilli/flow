"""Shared contracts for Polecat Swarm expert pipelines."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass
class ExpertResult:
    """Canonical result returned by every expert role."""

    status: Literal["success", "failed", "blocked"]
    notes: str
    artifacts: list[str] = field(default_factory=list)
    gate_scores: dict[str, float] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"


class ExpertAgent(Protocol):
    """Protocol every expert implementation should satisfy."""

    def execute(self) -> ExpertResult: ...


@dataclass
class TraceContext:
    """Trace metadata attached to all logs in a pipeline run."""

    trace_id: str
    span_id: str
    sub_span_id: str = ""
    expert_role: str = ""
    repo_name: str = ""
    started_at: float = 0.0

    def __post_init__(self) -> None:
        if self.started_at == 0.0:
            self.started_at = time.time()

    def prefix(self) -> str:
        sub = f"/{self.sub_span_id}" if self.sub_span_id else ""
        return f"[{self.trace_id}/{self.expert_role}{sub}/{self.span_id}]"

    def child(self, sub_agent_name: str) -> TraceContext:
        return TraceContext(
            trace_id=self.trace_id,
            span_id=self.span_id,
            sub_span_id=sub_agent_name,
            expert_role=self.expert_role,
            repo_name=self.repo_name,
            started_at=time.time(),
        )

    def elapsed(self) -> float:
        return time.time() - self.started_at
