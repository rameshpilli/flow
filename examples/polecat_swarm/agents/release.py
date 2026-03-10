"""RE expert implementation."""

from __future__ import annotations

import os
import shutil
import subprocess

from examples.polecat_swarm.agents.base_expert import BaseExpert
from examples.polecat_swarm.tools.git_tools import (
    changed_files,
    create_branch,
    current_commit,
    diff_stat,
    ensure_repo,
)
from examples.polecat_swarm.types import ExpertResult


class ReleaseExpert(BaseExpert):
    role = "RE"

    def run(self) -> ExpertResult:
        branch = f"swarm/{self.bead_id}"
        artifacts: list[str] = []

        if ensure_repo(self.worktree):
            create_branch(self.worktree, branch)
            commit_sha = current_commit(self.worktree)
            summary_path = self.write_artifact(
                "release_summary.md",
                "\n".join(
                    [
                        "# Release Summary",
                        f"- Branch: {branch}",
                        f"- Main branch target: {self.main_branch}",
                        f"- Commit: {commit_sha}",
                        "",
                        "## Diff Stat",
                        diff_stat(self.worktree) or "(no diff)",
                    ]
                ),
            )
            artifacts.append(summary_path)

            pr_url = self._maybe_create_pr(branch)
            if pr_url:
                artifacts.append(self.write_artifact("pr_url.txt", pr_url + "\n"))

            return ExpertResult(
                status="success",
                notes="Release branch prepared",
                artifacts=artifacts,
                metadata={
                    "branch": branch,
                    "main_branch": self.main_branch,
                    "commit_sha": commit_sha,
                    "files_changed": changed_files(self.worktree),
                    "pr_url": pr_url,
                },
            )

        return ExpertResult(
            status="success",
            notes="Release skipped: worktree is not a git repository",
            metadata={"branch": branch, "main_branch": self.main_branch, "pr_url": ""},
        )

    def _maybe_create_pr(self, branch: str) -> str:
        if shutil.which("gh") is None:
            return ""
        if os.getenv("POLECAT_CREATE_PR", "false").lower() not in {"1", "true", "yes", "on"}:
            return ""

        cmd = [
            "gh",
            "pr",
            "create",
            "--fill",
            "--base",
            self.main_branch,
            "--head",
            branch,
        ]
        result = subprocess.run(
            cmd,
            cwd=self.worktree,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip().splitlines()[-1].strip() if result.stdout.strip() else ""
