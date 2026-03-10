"""Gastown MVP chain: Deep research -> QA -> Docs -> Execute -> Finalize."""

from __future__ import annotations

import asyncio
import re
import shlex
import subprocess
import uuid
from pathlib import Path
from typing import Any

import httpx

from agentorchestrator.core.orchestrator import get_orchestrator
from examples.gastown_mvp import agents as _agents  # noqa: F401  # ensure metadata agents register
from examples.gastown_mvp.agents import build_runtime_supervisors
from examples.gastown_mvp.contracts import (
    DocsOutput,
    ExecutionEvidence,
    QAOutput,
    ResearchBrief,
    SuiteResult,
    TaskContext,
)

ao = get_orchestrator()
CHAIN_NAME = "polecat_mvp_flow"


@ao.supervisor(
    name="qa_supervisor",
    description="Coordinates QA sub-agents",
    lead_agent="qa_lead",
    team=["qa_scenario_designer", "qa_code_reviewer", "qa_test_executor"],
    max_concurrent_agents=3,
    agent_timeout_seconds=60.0,
    context_isolation=True,
)
class QASupervisorDefinition:
    pass


@ao.supervisor(
    name="documentation_supervisor",
    description="Coordinates documentation sub-agents",
    lead_agent="docs_lead",
    team=["docs_api_writer", "docs_release_notes_writer", "docs_runbook_writer"],
    max_concurrent_agents=3,
    agent_timeout_seconds=60.0,
    context_isolation=True,
)
class DocumentationSupervisorDefinition:
    pass


def _extract_path_like_tokens(text: str) -> list[str]:
    pat = re.compile(r"\b[\w./-]+\.(?:py|md|rst|txt|json|yaml|yml|toml|js|ts)\b")
    out: list[str] = []
    seen: set[str] = set()
    for m in pat.findall(text or ""):
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


async def _shell(cmd: str, cwd: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    return proc.returncode or 0, out_b.decode(errors="replace"), err_b.decode(errors="replace")


def _is_git_repo(repo_path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except Exception:
        return False


def _git_changed_files(repo_path: str) -> list[str]:
    if not _is_git_repo(repo_path):
        return []
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        files.append(line[3:])
    return files


def _git_patch_summary(repo_path: str) -> str:
    if not _is_git_repo(repo_path):
        return ""
    result = subprocess.run(
        ["git", "diff", "--stat"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def _ensure_runtime(ctx: Any):
    runtime = ctx.get("_mvp_runtime")
    if runtime:
        return runtime
    qa, docs, delegate = build_runtime_supervisors()
    runtime = {"qa": qa, "docs": docs, "delegate": delegate}
    ctx.set("_mvp_runtime", runtime)
    return runtime


@ao.step(name="ingest_task")
async def ingest_task(ctx: Any) -> dict[str, Any]:
    task_in = ctx.get("task") or {}
    if not isinstance(task_in, dict):
        task_in = {}

    task_id = str(task_in.get("task_id") or task_in.get("id") or f"task-{uuid.uuid4().hex[:8]}")
    bead_id = task_in.get("bead_id") or ctx.get("bead_id")
    description = str(task_in.get("description") or ctx.get("query") or "No task description provided")
    repo_path = str(task_in.get("repo_path") or ctx.get("worktree_path") or "/workspace")

    task = TaskContext(
        task_id=task_id,
        bead_id=bead_id,
        description=description,
        repo_path=repo_path,
        labels=list(task_in.get("labels") or []),
        priority=int(task_in.get("priority") or 2),
        raw=dict(task_in),
    )
    ctx.set("task_context", task.to_dict())
    return {"task_context": task.to_dict()}


@ao.step(name="deep_research_context", deps=["ingest_task"])
async def deep_research_context(ctx: Any) -> dict[str, Any]:
    task = TaskContext(**(ctx.get("task_context") or {}))
    base_url = str(ctx.get("deep_research_base_url") or "").strip()

    warnings: list[str] = []
    impacted_files = _extract_path_like_tokens(task.description)

    if base_url:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(f"{base_url.rstrip('/')}/health")
                if r.status_code >= 400:
                    warnings.append(f"Deep research health check returned {r.status_code}")
        except Exception as exc:
            warnings.append(f"Deep research unavailable: {exc}")
    else:
        warnings.append("DEEP_RESEARCH_BASE_URL not set; using heuristic research context")

    brief = ResearchBrief(
        summary=(
            "Heuristic research summary: prioritize quality and docs updates for the task, "
            "with explicit scenario coverage and regression focus."
        ),
        impacted_files=impacted_files,
        risks=[
            "Potential undocumented behavior changes",
            "Regression risk if tests do not cover boundary cases",
        ],
        assumptions=[
            "Task description is the current source of truth",
            "Repo test command is executable in worktree",
        ],
        warnings=warnings,
    )
    ctx.set("research_brief", brief.to_dict())
    return {"research_brief": brief.to_dict()}


@ao.step(name="run_qa_supervisor", deps=["deep_research_context"])
async def run_qa_supervisor(ctx: Any) -> dict[str, Any]:
    runtime = _ensure_runtime(ctx)
    qa = runtime["qa"]

    task = TaskContext(**(ctx.get("task_context") or {}))
    brief = ResearchBrief(**(ctx.get("research_brief") or {}))

    qa_output = await qa.run(task, brief)
    payload = qa_output.to_dict()
    ctx.set("qa_output", payload)
    return {"qa_output": payload}


@ao.step(name="run_docs_supervisor", deps=["run_qa_supervisor"])
async def run_docs_supervisor(ctx: Any) -> dict[str, Any]:
    runtime = _ensure_runtime(ctx)
    docs = runtime["docs"]

    task = TaskContext(**(ctx.get("task_context") or {}))
    brief = ResearchBrief(**(ctx.get("research_brief") or {}))
    qa_output = QAOutput(**(ctx.get("qa_output") or {}))

    docs_output = await docs.run(task, brief, qa_output)
    payload = docs_output.to_dict()
    ctx.set("docs_output", payload)
    return {"docs_output": payload}


@ao.step(name="execute_changes_and_tests", deps=["run_docs_supervisor"])
async def execute_changes_and_tests(ctx: Any) -> dict[str, Any]:
    task = TaskContext(**(ctx.get("task_context") or {}))
    test_cmd = str(ctx.get("test_cmd") or "pytest -q")

    repo_path = task.repo_path
    Path(repo_path).mkdir(parents=True, exist_ok=True)

    exit_code, stdout, stderr = await _shell(test_cmd, cwd=repo_path)
    evidence = ExecutionEvidence(
        command=test_cmd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        changed_files=_git_changed_files(repo_path),
        patch_summary=_git_patch_summary(repo_path),
    )

    ctx.set("execution_evidence", evidence.to_dict())
    return {"execution_evidence": evidence.to_dict()}


@ao.step(name="finalize_and_publish", deps=["execute_changes_and_tests"])
async def finalize_and_publish(ctx: Any) -> dict[str, Any]:
    task = TaskContext(**(ctx.get("task_context") or {}))
    brief = ResearchBrief(**(ctx.get("research_brief") or {}))
    qa_output = QAOutput(**(ctx.get("qa_output") or {}))
    docs_output = DocsOutput(**(ctx.get("docs_output") or {}))
    evidence = ExecutionEvidence(**(ctx.get("execution_evidence") or {}))

    status = "success" if evidence.exit_code == 0 else "failed"
    summary = (
        f"Task {task.task_id}: status={status}, scenarios={len(qa_output.scenarios)}, "
        f"docs_items={len(docs_output.api_docs) + len(docs_output.release_notes)}, "
        f"test_exit={evidence.exit_code}"
    )

    suite_result = SuiteResult(
        status=status,
        task_id=task.task_id,
        summary=summary,
        qa=qa_output.to_dict(),
        docs=docs_output.to_dict(),
        execution=evidence.to_dict(),
        warnings=list(brief.warnings),
    )

    evidence_md = "\n".join(
        [
            f"# Polecat MVP Evidence ({task.task_id})",
            "",
            f"- Status: **{status}**",
            f"- Command: `{shlex.quote(evidence.command)}`",
            f"- Exit code: `{evidence.exit_code}`",
            f"- QA scenarios: `{len(qa_output.scenarios)}`",
            f"- Docs outputs: `{len(docs_output.api_docs) + len(docs_output.release_notes) + len(docs_output.runbook_updates)}`",
            "",
            "## Patch Summary",
            evidence.patch_summary or "(none)",
            "",
            "## Stdout",
            "```text",
            (evidence.stdout or "")[:4000],
            "```",
            "",
            "## Stderr",
            "```text",
            (evidence.stderr or "")[:4000],
            "```",
        ]
    )

    result_payload = suite_result.to_dict()
    ctx.set("suite_result", result_payload)
    ctx.set("evidence_markdown", evidence_md)
    return {"suite_result": result_payload, "evidence_markdown": evidence_md}


@ao.chain(name=CHAIN_NAME)
class PolecatMVPFlow:
    steps = [
        "ingest_task",
        "deep_research_context",
        "run_qa_supervisor",
        "run_docs_supervisor",
        "execute_changes_and_tests",
        "finalize_and_publish",
    ]


@ao.suite(
    name="polecat_mvp_suite",
    version="1.0.0",
    root_supervisor="qa_supervisor",
    entry_chain=CHAIN_NAME,
    capabilities=["qa", "documentation", "autonomous_execution"],
    handoff_targets=[],
    runtime={"timeout_seconds": 600, "mcp_port": 8080},
)
class PolecatMVPSuiteDefinition:
    pass


def build_initial_data(
    task: dict[str, Any],
    worktree_path: str,
    deep_research_base_url: str = "",
    test_cmd: str = "pytest -q",
) -> dict[str, Any]:
    """Helper for entrypoint/tests to build chain input data."""
    return {
        "task": dict(task),
        "worktree_path": worktree_path,
        "deep_research_base_url": deep_research_base_url,
        "test_cmd": test_cmd,
    }
