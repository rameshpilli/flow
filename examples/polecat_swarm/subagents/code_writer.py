"""CodeWriter sub-agent for EES."""

from __future__ import annotations

from dataclasses import dataclass

from examples.polecat_swarm.tools.opencode_executor import ICodeExecutor


@dataclass
class CodeWriterResult:
    notes: str
    changed_hint: list[str]


class CodeWriter:
    def __init__(self, executor: ICodeExecutor, log):
        self.executor = executor
        self.log = log

    def run(self, bead: dict, implementation_plan: str, language: str) -> CodeWriterResult:
        self.log.info("subagent_started", sub_agent="CodeWriter")
        prompt = (
            "Implement the requested changes in the repository.\n"
            f"Language: {language}\n"
            f"Task: {bead.get('title')}\n"
            f"Description: {bead.get('description', '')}\n"
            f"Plan:\n{implementation_plan[:4000]}\n"
            "Apply minimal changes and keep tests passing."
        )
        result = self.executor.run(prompt, mode="build")
        notes = result.output[:3000] if result.output else "No output from code writer"
        self.log.info(
            "subagent_completed",
            sub_agent="CodeWriter",
            elapsed_s=0.0,
            status="success" if result.success else "failed",
        )
        return CodeWriterResult(notes=notes, changed_hint=[])
