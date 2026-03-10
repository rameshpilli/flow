"""Coder Pad MVP chain: code -> qa -> docs -> execute -> finalize."""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import uuid
from pathlib import Path
from typing import Any

from agentorchestrator.core.orchestrator import get_orchestrator
from examples.coder_pad_mvp import agents as _agents  # noqa: F401
from examples.coder_pad_mvp.agents import build_runtime_supervisors
from examples.coder_pad_mvp.contracts import (
    CoderOutput,
    DocsOutput,
    ExecutionEvidence,
    QAOutput,
    ResearchBrief,
    SuiteResult,
    TaskContext,
)

ao = get_orchestrator()
CHAIN_NAME = "coder_pad_flow"


@ao.supervisor(
    name="cp_coding_supervisor",
    description="Coordinates coding sub-agents",
    lead_agent="cp_coder_lead",
    team=["cp_code_planner", "cp_code_implementer", "cp_code_verifier"],
    max_concurrent_agents=3,
    agent_timeout_seconds=120.0,
    context_isolation=True,
)
class CodingSupervisorDefinition:
    pass


@ao.supervisor(
    name="cp_qa_supervisor",
    description="Coordinates QA sub-agents",
    lead_agent="cp_qa_lead",
    team=["cp_qa_scenario_designer", "cp_qa_code_reviewer", "cp_qa_test_executor"],
    max_concurrent_agents=3,
    agent_timeout_seconds=120.0,
    context_isolation=True,
)
class QASupervisorDefinition:
    pass


@ao.supervisor(
    name="cp_documentation_supervisor",
    description="Coordinates documentation sub-agents",
    lead_agent="cp_docs_lead",
    team=["cp_docs_api_writer", "cp_docs_release_notes_writer", "cp_docs_runbook_writer"],
    max_concurrent_agents=3,
    agent_timeout_seconds=120.0,
    context_isolation=True,
)
class DocumentationSupervisorDefinition:
    pass


async def _shell(cmd: str, cwd: str) -> tuple[int, str, str]:
    env = dict(os.environ)
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{cwd}:{current_pythonpath}" if current_pythonpath else cwd
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    return proc.returncode or 0, out_b.decode(errors="replace"), err_b.decode(errors="replace")


def _is_git_repo(repo_path: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


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
        if line.strip():
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
    runtime = ctx.get("_coder_pad_runtime")
    if runtime:
        return runtime
    coder, qa, docs, delegate = build_runtime_supervisors()
    runtime = {
        "coder": coder,
        "qa": qa,
        "docs": docs,
        "delegate": delegate,
    }
    ctx.set("_coder_pad_runtime", runtime)
    return runtime


@ao.step(name="ingest_task")
async def ingest_task(ctx: Any) -> dict[str, Any]:
    task_in = ctx.get("task") or {}
    if not isinstance(task_in, dict):
        task_in = {}

    task_id = str(task_in.get("task_id") or task_in.get("id") or f"task-{uuid.uuid4().hex[:8]}")
    bead_id = task_in.get("bead_id") or ctx.get("bead_id")
    description = str(task_in.get("description") or "Create calculator app")
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
    Path(repo_path).mkdir(parents=True, exist_ok=True)
    ctx.set("task_context", task.to_dict())
    return {"task_context": task.to_dict()}


@ao.step(name="run_coder_supervisor", deps=["ingest_task"])
async def run_coder_supervisor(ctx: Any) -> dict[str, Any]:
    runtime = _ensure_runtime(ctx)
    coder = runtime["coder"]
    task = TaskContext(**(ctx.get("task_context") or {}))

    coder_output = await coder.run(task)
    payload = coder_output.to_dict()
    ctx.set("coder_output", payload)
    return {"coder_output": payload}


@ao.step(name="build_context_from_code", deps=["run_coder_supervisor"])
async def build_context_from_code(ctx: Any) -> dict[str, Any]:
    task = TaskContext(**(ctx.get("task_context") or {}))
    coder_output = CoderOutput(**(ctx.get("coder_output") or {}))

    brief = ResearchBrief(
        summary="Code implementation context built from coder supervisor output.",
        impacted_files=list(coder_output.changed_files),
        risks=[
            "Behavioral regressions if edge cases are under-tested",
            "Documentation mismatch if API assumptions drift",
        ],
        assumptions=[
            "Generated calculator files are the intended implementation scope",
            "Pytest command is available in execution runtime",
        ],
        warnings=[],
    )

    # Auto-seed a README if missing for docs step continuity
    readme = Path(task.repo_path) / "README.md"
    if not readme.exists():
        readme.write_text("# Calculator App\n\nMVP generated by Coder Pad workflow.\n", encoding="utf-8")

    ctx.set("research_brief", brief.to_dict())
    return {"research_brief": brief.to_dict()}


@ao.step(name="run_qa_supervisor", deps=["build_context_from_code"])
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

    exit_code, stdout, stderr = await _shell(test_cmd, cwd=task.repo_path)
    evidence = ExecutionEvidence(
        command=test_cmd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        changed_files=_git_changed_files(task.repo_path),
        patch_summary=_git_patch_summary(task.repo_path),
    )

    ctx.set("execution_evidence", evidence.to_dict())
    return {"execution_evidence": evidence.to_dict()}


@ao.step(name="finalize_and_publish", deps=["execute_changes_and_tests"])
async def finalize_and_publish(ctx: Any) -> dict[str, Any]:
    task = TaskContext(**(ctx.get("task_context") or {}))
    coder_output = CoderOutput(**(ctx.get("coder_output") or {}))
    qa_output = QAOutput(**(ctx.get("qa_output") or {}))
    docs_output = DocsOutput(**(ctx.get("docs_output") or {}))
    brief = ResearchBrief(**(ctx.get("research_brief") or {}))
    evidence = ExecutionEvidence(**(ctx.get("execution_evidence") or {}))

    status = "success" if evidence.exit_code == 0 else "failed"
    summary = (
        f"Task {task.task_id}: status={status}, coded_files={len(coder_output.changed_files)}, "
        f"qa_scenarios={len(qa_output.scenarios)}, docs_items={len(docs_output.api_docs) + len(docs_output.release_notes)}, "
        f"test_exit={evidence.exit_code}"
    )

    suite_result = SuiteResult(
        status=status,
        task_id=task.task_id,
        summary=summary,
        coder=coder_output.to_dict(),
        qa=qa_output.to_dict(),
        docs=docs_output.to_dict(),
        execution=evidence.to_dict(),
        warnings=list(brief.warnings),
    )

    evidence_md = "\n".join(
        [
            f"# Coder Pad MVP Evidence ({task.task_id})",
            "",
            f"- Status: **{status}**",
            f"- Command: `{shlex.quote(evidence.command)}`",
            f"- Exit code: `{evidence.exit_code}`",
            f"- Coder changed files: `{len(coder_output.changed_files)}`",
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
class CoderPadFlow:
    steps = [
        "ingest_task",
        "run_coder_supervisor",
        "build_context_from_code",
        "run_qa_supervisor",
        "run_docs_supervisor",
        "execute_changes_and_tests",
        "finalize_and_publish",
    ]


@ao.suite(
    name="coder_pad_suite",
    version="1.0.0",
    root_supervisor="cp_coding_supervisor",
    entry_chain=CHAIN_NAME,
    capabilities=["coding", "qa", "documentation", "autonomous_execution"],
    handoff_targets=[],
    runtime={"timeout_seconds": 900, "mcp_port": 8081},
)
class CoderPadSuiteDefinition:
    pass


def build_initial_data(
    task: dict[str, Any],
    worktree_path: str,
    test_cmd: str = "pytest -q",
) -> dict[str, Any]:
    """Helper for entrypoint/tests to build chain input data."""
    return {
        "task": dict(task),
        "worktree_path": worktree_path,
        "test_cmd": test_cmd,
    }
