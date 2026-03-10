"""Code execution adapters for Polecat Swarm experts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000")

BASE_PROVIDER_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "autoapprove": True,
    "provider": {
        "litellm": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Corporate LLM Proxy",
            "options": {"baseURL": f"{LITELLM_PROXY_URL}/v1"},
            "models": {
                "claude-sonnet-4-5": {
                    "name": "Claude Sonnet (Gateway A)",
                    "limit": {"context": 200000, "output": 8192},
                },
                "gpt-4o": {
                    "name": "GPT-4o (Gateway B)",
                    "limit": {"context": 128000, "output": 4096},
                },
                "gpt-4-turbo": {
                    "name": "GPT-4 Turbo (Gateway B)",
                    "limit": {"context": 128000, "output": 4096},
                },
            },
        }
    },
}


@dataclass
class ExecResult:
    output: str
    exit_code: int
    success: bool


@runtime_checkable
class ICodeExecutor(Protocol):
    def run(self, prompt: str, mode: str = "build") -> ExecResult: ...

    def plan(self, prompt: str) -> ExecResult: ...


class DryRunExecutor:
    """No-op executor used by tests and `/chat/plan` workflows."""

    def run(self, prompt: str, mode: str = "build") -> ExecResult:
        return ExecResult(
            output=f"[DRY RUN] Would execute ({mode}): {prompt[:200]}",
            exit_code=0,
            success=True,
        )

    def plan(self, prompt: str) -> ExecResult:
        return self.run(prompt=prompt, mode="plan")


class OpencodeExecutor:
    def __init__(
        self,
        workdir: str,
        model: str | None = None,
        skill_paths: list[str] | None = None,
        timeout: int = 600,
        log=None,
    ):
        self.workdir = workdir
        self.model = model or os.getenv("OPENCODE_MODEL", "claude-sonnet-4-5")
        self.skill_paths = skill_paths or []
        self.timeout = timeout
        self._log = log

    def run(self, prompt: str, mode: str = "build") -> ExecResult:
        existing_skills = [path for path in self.skill_paths if os.path.exists(path)]

        if self._log:
            self._log.info(
                "opencode_started",
                mode=mode,
                model=self.model,
                skill_count=len(existing_skills),
                prompt_chars=len(prompt),
            )

        if shutil.which("opencode") is None:
            output = "opencode binary not found"
            if self._log:
                self._log.error("opencode_complete", exit_code=127, elapsed_s=0.0, output_chars=len(output))
            return ExecResult(output=output, exit_code=127, success=False)

        config = self._build_config(existing_skills)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(config, handle)
            config_path = handle.name

        command = ["opencode", "-p", prompt, "-q", "--no-auto-compact", "--config", config_path]
        env = {**os.environ, "OPENCODE_AGENT": "plan" if mode == "plan" else "build"}

        start = time.time()
        try:
            result = subprocess.run(
                command,
                cwd=self.workdir,
                capture_output=True,
                text=True,
                env=env,
                timeout=self.timeout,
                check=False,
            )
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            elapsed = round(time.time() - start, 3)
            if self._log:
                self._log.info(
                    "opencode_complete",
                    exit_code=result.returncode,
                    elapsed_s=elapsed,
                    output_chars=len(output),
                )
            return ExecResult(output=output, exit_code=result.returncode, success=result.returncode == 0)
        except subprocess.TimeoutExpired:
            elapsed = round(time.time() - start, 3)
            if self._log:
                self._log.error("opencode_timeout", timeout_s=self.timeout, model=self.model, elapsed_s=elapsed)
            return ExecResult(output="TIMEOUT", exit_code=-1, success=False)
        finally:
            try:
                os.unlink(config_path)
            except Exception:
                pass

    def plan(self, prompt: str) -> ExecResult:
        return self.run(prompt=prompt, mode="plan")

    def _build_config(self, existing_skills: list[str]) -> dict:
        config = json.loads(json.dumps(BASE_PROVIDER_CONFIG))
        config["model"] = f"litellm/{self.model}"
        if existing_skills:
            config["skills"] = existing_skills
        return config


def build_executor_for_role(
    role: str,
    worktree: str,
    swarm_config,
    model: str | None = None,
    timeout: int = 600,
    dry_run: bool = False,
    log=None,
) -> ICodeExecutor:
    if dry_run:
        return DryRunExecutor()

    skill_paths = swarm_config.skills.for_role(role) if swarm_config else []
    return OpencodeExecutor(
        workdir=worktree,
        model=model or os.getenv("OPENCODE_MODEL", "claude-sonnet-4-5"),
        skill_paths=skill_paths,
        timeout=timeout,
        log=log,
    )
