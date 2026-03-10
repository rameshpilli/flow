"""IntegrationTestWriter sub-agent for QES."""

from __future__ import annotations

from examples.polecat_swarm.tools.opencode_executor import ICodeExecutor


class IntegrationTestWriter:
    def __init__(self, executor: ICodeExecutor, log):
        self.executor = executor
        self.log = log

    def run(self, bead: dict) -> str:
        self.log.info("subagent_started", sub_agent="IntegrationTestWriter")
        prompt = (
            "Add or update integration tests for this task.\n"
            f"Task: {bead.get('title')}\n"
            f"Description: {bead.get('description', '')}\n"
        )
        result = self.executor.run(prompt, mode="build")
        self.log.info(
            "subagent_completed",
            sub_agent="IntegrationTestWriter",
            elapsed_s=0.0,
            status="success" if result.success else "failed",
        )
        return result.output[:1200] if result.output else ""
