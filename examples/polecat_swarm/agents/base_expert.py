"""Base class for Polecat Swarm experts."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

from agentorchestrator import AgentOrchestrator
from agentorchestrator.integrations.gastown import BeadClient, BeadStateManager
from examples.polecat_swarm.gateway_router import GatewayRouter
from examples.polecat_swarm.swarm_logger import SwarmLogger
from examples.polecat_swarm.tools.opencode_executor import build_executor_for_role
from examples.polecat_swarm.types import ExpertResult, TraceContext


class BaseExpert(ABC):
    role = ""

    def __init__(
        self,
        ao: AgentOrchestrator,
        bead: dict,
        swarm_config,
        worktree: str,
        repo_root: str,
        gateway_router: GatewayRouter,
        started_at: float | None = None,
    ):
        self.ao = ao
        self.bead = bead
        self.bead_id = str(bead.get("id") or "")
        self.swarm_config = swarm_config
        self.worktree = worktree
        self.repo_root = repo_root
        self.gateway_router = gateway_router
        self.started_at = started_at or time.time()

        self.artifact_dir = Path(worktree) / ".gastown" / "specs" / self.bead_id
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

        self.bead_client = BeadClient(repo_root)
        self.state_manager = BeadStateManager(self.bead_client)

        self.trace = TraceContext(
            trace_id=swarm_config.trace_id if swarm_config else "",
            span_id=self.bead_id,
            expert_role=self.role,
            repo_name=swarm_config.repo_name if swarm_config else "",
            started_at=self.started_at,
        )
        self.log = SwarmLogger(self.trace)

        self.opencode_executor = build_executor_for_role(
            role=self.role,
            worktree=worktree,
            swarm_config=swarm_config,
            model=self.model,
            log=self.log,
        )

    @property
    def model(self) -> str:
        if self.swarm_config:
            for expert in self.swarm_config.pipeline:
                if expert.role == self.role:
                    return expert.model
        return "claude-sonnet-4-5"

    @property
    def services(self) -> list[str]:
        return list(self.swarm_config.services) if self.swarm_config else []

    @property
    def test_command(self) -> str:
        return str(self.swarm_config.test_command) if self.swarm_config else "pytest"

    @property
    def docs_path(self) -> str:
        return str(self.swarm_config.docs_path) if self.swarm_config else "docs/"

    @property
    def main_branch(self) -> str:
        return str(self.swarm_config.main_branch) if self.swarm_config else "main"

    def write_artifact(self, filename: str, content: str) -> str:
        path = self.artifact_dir / filename
        path.write_text(content, encoding="utf-8")
        return str(path)

    def read_artifact(self, filename: str) -> str:
        path = self.artifact_dir / filename
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def execute(self) -> ExpertResult:
        self.log.info(
            "expert_started",
            role=self.role,
            model=self.model,
            services=self.services,
            skills=self.swarm_config.skills.for_role(self.role) if self.swarm_config else [],
        )

        try:
            result = self.run()
        except Exception as exc:
            self.log.error(
                "expert_exception",
                role=self.role,
                exception=str(exc),
                elapsed_s=round(self.trace.elapsed(), 3),
            )
            result = ExpertResult(status="failed", notes=str(exc), artifacts=[])

        self.log.info(
            "expert_completed",
            role=self.role,
            status=result.status,
            elapsed_s=round(self.trace.elapsed(), 3),
            gate_scores=result.gate_scores,
        )
        return result

    @abstractmethod
    def run(self) -> ExpertResult:
        """Role-specific execution implementation."""
        raise NotImplementedError
