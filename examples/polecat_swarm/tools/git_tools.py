"""Git helper functions for experts."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(args: list[str], cwd: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=check)


def checkout_commit(cwd: str, commit_sha: str) -> None:
    if not commit_sha:
        return
    run_git(["checkout", commit_sha], cwd=cwd, check=True)


def create_branch(cwd: str, branch: str) -> None:
    run_git(["checkout", "-B", branch], cwd=cwd, check=True)


def changed_files(cwd: str) -> list[str]:
    result = run_git(["status", "--porcelain"], cwd=cwd)
    if result.returncode != 0:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        files.append(text[3:])
    return files


def diff_stat(cwd: str) -> str:
    result = run_git(["diff", "--stat"], cwd=cwd)
    return result.stdout.strip()


def ensure_repo(path: str) -> bool:
    repo = run_git(["rev-parse", "--is-inside-work-tree"], cwd=path)
    return repo.returncode == 0 and repo.stdout.strip() == "true"


def current_commit(cwd: str) -> str:
    result = run_git(["rev-parse", "HEAD"], cwd=cwd)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def file_exists(cwd: str, relative_path: str) -> bool:
    return (Path(cwd) / relative_path).exists()
