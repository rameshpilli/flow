"""ArchitectureAdvisor sub-agent for EES."""

from __future__ import annotations

from dataclasses import dataclass

from examples.polecat_swarm.tools.opencode_executor import ICodeExecutor
from examples.polecat_swarm.tools.service_registry import ServiceRegistry


@dataclass
class ArchitecturePlan:
    summary: str
    decisions: list[str]
    services_context: str
    artifact: str = "implementation_plan.md"


class ArchitectureAdvisor:
    def __init__(self, executor: ICodeExecutor, service_registry: ServiceRegistry, log):
        self.executor = executor
        self.service_registry = service_registry
        self.log = log

    def run(self, bead: dict, language: str, framework: str, services: list[str]) -> ArchitecturePlan:
        self.log.info("subagent_started", sub_agent="ArchitectureAdvisor")

        services_context = self.service_registry.fetch_many(services)
        prompt = (
            "Create a concise engineering implementation plan.\n"
            f"Language: {language}\n"
            f"Framework: {framework}\n"
            f"Task: {bead.get('title')}\n"
            f"Description: {bead.get('description', '')}\n"
            f"Services:\n{services_context}\n"
            "Return concrete implementation decisions and test strategy."
        )
        result = self.executor.plan(prompt)

        decisions = [
            "Use incremental file edits with tests before release.",
            "Apply internal service templates where relevant.",
            "Capture evidence artifacts for QA and release notes.",
        ]
        if result.success and result.output.strip():
            summary = result.output[:1200]
        else:
            summary = "Fallback plan: implement minimal changes, run tests, and capture artifacts."

        plan = ArchitecturePlan(summary=summary, decisions=decisions, services_context=services_context)
        self.log.info("subagent_completed", sub_agent="ArchitectureAdvisor", elapsed_s=0.0, status="success")
        return plan
