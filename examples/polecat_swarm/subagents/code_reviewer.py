"""CodeReviewer sub-agent for EES."""

from __future__ import annotations

from dataclasses import dataclass

from examples.polecat_swarm.tools.opencode_executor import ICodeExecutor


@dataclass
class ReviewResult:
    score: float
    notes: str


class CodeReviewer:
    def __init__(self, executor: ICodeExecutor, threshold: float, log):
        self.executor = executor
        self.threshold = threshold
        self.log = log

    def run(self, bead: dict, implementation_notes: str) -> ReviewResult:
        self.log.info("subagent_started", sub_agent="CodeReviewer")
        prompt = (
            "Review implemented changes for correctness and maintainability.\n"
            f"Task: {bead.get('title')}\n"
            f"Implementation notes:\n{implementation_notes[:4000]}\n"
            "Return concerns and confidence."
        )
        result = self.executor.plan(prompt)
        notes = result.output[:2000] if result.output else "No review output"

        # Deterministic lightweight score heuristic for MVP.
        score = 0.9 if result.success else 0.55
        self.log.info(
            "subagent_completed",
            sub_agent="CodeReviewer",
            elapsed_s=0.0,
            status="success" if score >= self.threshold else "failed",
        )
        return ReviewResult(score=score, notes=notes)
