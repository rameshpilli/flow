"""API doc writer for DE."""

from __future__ import annotations

from pathlib import Path


class APIDocWriter:
    def __init__(self, docs_path: str, worktree: str, log):
        self.docs_path = docs_path
        self.worktree = worktree
        self.log = log

    def run(self, bead: dict, qa_notes: str) -> str:
        self.log.info("subagent_started", sub_agent="APIDocWriter")
        target = Path(self.worktree) / self.docs_path / "api_changes.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "# API Changes\n\n"
            f"Task: {bead.get('title')}\n\n"
            "## QA Notes\n"
            f"{qa_notes or 'No QA notes captured.'}\n"
        )
        target.write_text(content, encoding="utf-8")
        self.log.info("subagent_completed", sub_agent="APIDocWriter", elapsed_s=0.0, status="success")
        return str(target)
