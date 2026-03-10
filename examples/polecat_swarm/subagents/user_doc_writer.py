"""User doc writer for DE."""

from __future__ import annotations

from pathlib import Path


class UserDocWriter:
    def __init__(self, docs_path: str, worktree: str, log):
        self.docs_path = docs_path
        self.worktree = worktree
        self.log = log

    def run(self, bead: dict, summary: str) -> str:
        self.log.info("subagent_started", sub_agent="UserDocWriter")
        target = Path(self.worktree) / self.docs_path / "release_notes.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "# Release Notes\n\n"
            f"Task: {bead.get('title')}\n\n"
            "## Summary\n"
            f"{summary or 'No summary generated.'}\n"
        )
        target.write_text(content, encoding="utf-8")
        self.log.info("subagent_completed", sub_agent="UserDocWriter", elapsed_s=0.0, status="success")
        return str(target)
