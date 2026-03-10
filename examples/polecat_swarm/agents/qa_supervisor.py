"""QES expert supervisor implementation."""

from __future__ import annotations

from examples.polecat_swarm.agents.base_expert import BaseExpert
from examples.polecat_swarm.subagents.integration_test_writer import IntegrationTestWriter
from examples.polecat_swarm.subagents.test_designer import TestDesigner
from examples.polecat_swarm.subagents.test_runner import TestRunner
from examples.polecat_swarm.subagents.unit_test_writer import UnitTestWriter
from examples.polecat_swarm.types import ExpertResult


class QASupervisorExpert(BaseExpert):
    role = "QES"

    def run(self) -> ExpertResult:
        designer = TestDesigner(log=self._child_log("TestDesigner"))
        unit_writer = UnitTestWriter(executor=self.opencode_executor, log=self._child_log("UnitTestWriter"))
        integration_writer = IntegrationTestWriter(
            executor=self.opencode_executor,
            log=self._child_log("IntegrationTestWriter"),
        )
        runner = TestRunner(worktree=self.worktree, log=self._child_log("TestRunner"))

        scenarios = designer.run(self.bead)
        unit_writer.run(self.bead)
        integration_writer.run(self.bead)

        run_result = runner.run(self.test_command)
        qa_report = "\n".join(
            [
                "# QA Report",
                "",
                "## Scenarios",
                *(f"- {scenario}" for scenario in scenarios),
                "",
                f"## Command\n`{run_result.command}`",
                f"\nExit: {run_result.exit_code}",
                "",
                "## Output",
                "```text",
                run_result.output[:6000],
                "```",
            ]
        )
        artifact = self.write_artifact("qa_report.md", qa_report)

        if not run_result.success:
            return ExpertResult(
                status="failed",
                notes="QA test gate failed",
                artifacts=[artifact],
                gate_scores={"tests": 0.0},
                metadata={"test_exit_code": run_result.exit_code},
            )

        return ExpertResult(
            status="success",
            notes="QA checks passed",
            artifacts=[artifact],
            gate_scores={"tests": 1.0},
            metadata={"test_exit_code": run_result.exit_code},
        )

    def _child_log(self, name: str):
        from examples.polecat_swarm.swarm_logger import SwarmLogger

        return SwarmLogger(self.trace.child(name))
