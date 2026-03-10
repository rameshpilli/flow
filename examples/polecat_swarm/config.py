"""Runtime config helpers for Polecat Swarm."""

from __future__ import annotations

import os


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def default_test_command() -> str:
    return os.getenv("POLECAT_TEST_CMD", "pytest -q")


def default_worktree() -> str:
    return os.getenv("WORKTREE_PATH", "/workspace")
