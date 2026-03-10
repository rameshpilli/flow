"""TestRunner sub-agent for QES."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class TestRunResult:
    command: str
    exit_code: int
    output: str

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class TestRunner:
    def __init__(self, worktree: str, log):
        self.worktree = worktree
        self.log = log

    def run(self, command: str) -> TestRunResult:
        self.log.info("subagent_started", sub_agent="TestRunner")
        proc = subprocess.run(
            command,
            cwd=self.worktree,
            shell=True,
            text=True,
            capture_output=True,
            check=False,
        )
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        self.log.info(
            "subagent_completed",
            sub_agent="TestRunner",
            elapsed_s=0.0,
            status="success" if proc.returncode == 0 else "failed",
            exit_code=proc.returncode,
        )
        return TestRunResult(command=command, exit_code=proc.returncode, output=output)
