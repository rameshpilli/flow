"""EES expert supervisor implementation."""

from __future__ import annotations

from examples.polecat_swarm.agents.base_expert import BaseExpert
from examples.polecat_swarm.subagents.architecture_advisor import ArchitectureAdvisor
from examples.polecat_swarm.subagents.code_reviewer import CodeReviewer
from examples.polecat_swarm.subagents.code_writer import CodeWriter
from examples.polecat_swarm.tools.service_registry import ServiceRegistry
from examples.polecat_swarm.types import ExpertResult


class EngineeringSupervisorExpert(BaseExpert):
    role = "EES"

    def run(self) -> ExpertResult:
        service_registry = ServiceRegistry()

        arch = ArchitectureAdvisor(
            executor=self.opencode_executor,
            service_registry=service_registry,
            log=self._child_log("ArchitectureAdvisor"),
        )
        writer = CodeWriter(executor=self.opencode_executor, log=self._child_log("CodeWriter"))
        reviewer = CodeReviewer(
            executor=self.opencode_executor,
            threshold=0.8,
            log=self._child_log("CodeReviewer"),
        )

        plan = arch.run(
            bead=self.bead,
            language=self.swarm_config.language if self.swarm_config else "python",
            framework=self.swarm_config.framework if self.swarm_config else "",
            services=self.services,
        )
        plan_artifact = self.write_artifact("implementation_plan.md", plan.summary)

        write_result = writer.run(
            bead=self.bead,
            implementation_plan=plan.summary,
            language=self.swarm_config.language if self.swarm_config else "python",
        )

        review_result = reviewer.run(self.bead, write_result.notes)
        review_artifact = self.write_artifact("code_review.md", review_result.notes)

        if review_result.score < 0.8:
            return ExpertResult(
                status="failed",
                notes="Code review score below threshold",
                artifacts=[plan_artifact, review_artifact],
                gate_scores={"code_review": review_result.score},
                metadata={"decisions": plan.decisions},
            )

        return ExpertResult(
            status="success",
            notes="Engineering implementation and review completed",
            artifacts=[plan_artifact, review_artifact],
            gate_scores={"code_review": review_result.score},
            metadata={"decisions": plan.decisions},
        )

    def _child_log(self, name: str):
        from examples.polecat_swarm.swarm_logger import SwarmLogger

        return SwarmLogger(self.trace.child(name))
