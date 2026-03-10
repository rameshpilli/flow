"""Coder Pad MVP supervisor/sub-agent runtime and metadata registrations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.core.decorators import agent
from examples.coder_pad_mvp.contracts import (
    CoderOutput,
    DocsOutput,
    QAOutput,
    ResearchBrief,
    TaskContext,
)


class _MetadataAgentBase(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        return AgentResult(
            data={"query": query, "ok": True, "kwargs": kwargs},
            source=self.__class__.__name__,
            query=query,
        )


@agent(name="cp_coder_lead", description="Leads coding orchestration", capabilities=["coding_coordination"], version="1.0.0")
class CoderLeadMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_code_planner", description="Plans code changes", capabilities=["planning"], version="1.0.0")
class CodePlannerMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_code_implementer", description="Implements code", capabilities=["implementation"], version="1.0.0")
class CodeImplementerMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_code_verifier", description="Validates implementation shape", capabilities=["verification"], version="1.0.0")
class CodeVerifierMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_qa_lead", description="Leads QA orchestration", capabilities=["qa_coordination"], version="1.0.0")
class QALeadMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_qa_scenario_designer", description="Designs explicit test scenarios", capabilities=["scenario_design"], version="1.0.0")
class QAScenarioDesignerMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_qa_code_reviewer", description="Reviews code changes for risk", capabilities=["code_review"], version="1.0.0")
class QACodeReviewerMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_qa_test_executor", description="Plans and executes tests", capabilities=["test_execution"], version="1.0.0")
class QATestExecutorMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_docs_lead", description="Leads documentation updates", capabilities=["documentation_coordination"], version="1.0.0")
class DocsLeadMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_docs_api_writer", description="Writes API documentation", capabilities=["api_docs"], version="1.0.0")
class DocsAPIWriterMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_docs_release_notes_writer", description="Produces release notes", capabilities=["release_notes"], version="1.0.0")
class DocsReleaseNotesMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="cp_docs_runbook_writer", description="Updates operational runbooks", capabilities=["runbook_updates"], version="1.0.0")
class DocsRunbookMetadataAgent(_MetadataAgentBase):
    pass


class DelegateClient(Protocol):
    async def delegate(self, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class InProcessDelegateClient:
    """MVP delegate implementation using in-memory handlers."""

    def __init__(self):
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {}

    def register(
        self,
        target: str,
        handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> None:
        self._handlers[target] = handler

    async def delegate(self, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(target)
        if not handler:
            return {
                "ok": False,
                "target": target,
                "message": "no delegate handler registered",
                "payload": payload,
            }
        return await handler(payload)


class CoderSupervisorRuntime:
    """Deterministic coder runtime for demo issue execution."""

    def _write_file(self, repo_path: str, relative_path: str, content: str) -> str:
        file_path = Path(repo_path) / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return relative_path

    async def run(self, task: TaskContext) -> CoderOutput:
        description = task.description.lower()
        changed_files: list[str] = []

        plan = [
            "Create calculator core module and tests",
            "Ensure import surface is stable",
            "Prepare docs-friendly API shape",
        ]

        core_py = '''"""Core calculator functions."""


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b
'''

        init_py = '''"""Calculator package exports."""

from calculator.core import add, divide, multiply, subtract

__all__ = ["add", "subtract", "multiply", "divide"]
'''

        test_py = """\
from calculator.core import add, divide, multiply, subtract


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(10, 4) == 6


def test_multiply():
    assert multiply(3, 7) == 21


def test_divide():
    assert divide(8, 2) == 4
"""

        changed_files.append(self._write_file(task.repo_path, "calculator/core.py", core_py))
        changed_files.append(self._write_file(task.repo_path, "calculator/__init__.py", init_py))
        changed_files.append(self._write_file(task.repo_path, "tests/test_calculator_core.py", test_py))

        if "cli" in description:
            cli_py = '''"""CLI entrypoint for calculator."""

import argparse

from calculator.core import add, divide, multiply, subtract


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculator CLI")
    parser.add_argument("operation", choices=["add", "subtract", "multiply", "divide"])
    parser.add_argument("a", type=float)
    parser.add_argument("b", type=float)
    args = parser.parse_args()

    ops = {
        "add": add,
        "subtract": subtract,
        "multiply": multiply,
        "divide": divide,
    }
    print(ops[args.operation](args.a, args.b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
            changed_files.append(self._write_file(task.repo_path, "calculator/cli.py", cli_py))
            plan.append("Add CLI command surface")

        notes = [
            "Coding step is deterministic for MVP demo",
            "Use this as scaffold before connecting model-driven patch generation",
        ]
        return CoderOutput(plan=plan, changed_files=changed_files, notes=notes)


class ScenarioDesignerAgent:
    async def run(self, task: TaskContext, research: ResearchBrief) -> list[str]:
        scenarios = [
            f"Validate acceptance criteria for: {task.description}",
            "Confirm regression coverage for modified paths",
        ]
        for path in research.impacted_files[:3]:
            scenarios.append(f"Add scenario for behavior touched in {path}")
        return scenarios


class CodeReviewAgent:
    async def run(self, task: TaskContext, research: ResearchBrief) -> list[str]:
        notes = [
            "Check boundary conditions and error handling",
            "Review test determinism and fixture isolation",
        ]
        if research.impacted_files:
            notes.append(f"Focus review on: {', '.join(research.impacted_files[:4])}")
        return notes


class TestExecutorAgent:
    async def run(self, task: TaskContext, research: ResearchBrief) -> list[str]:
        return [
            "Run focused unit tests for touched modules",
            "Run smoke/integration suite for impacted flow",
            "Record failures with reproduction hints",
        ]


class QASupervisorRuntime:
    def __init__(self, delegate_client: DelegateClient):
        self.delegate_client = delegate_client
        self.scenario_designer = ScenarioDesignerAgent()
        self.code_reviewer = CodeReviewAgent()
        self.test_executor = TestExecutorAgent()

    async def run(self, task: TaskContext, research: ResearchBrief) -> QAOutput:
        scenarios = await self.scenario_designer.run(task, research)
        review_notes = await self.code_reviewer.run(task, research)
        test_plan = await self.test_executor.run(task, research)

        doc_impact = [
            f"Document behavior changes in {path}"
            for path in research.impacted_files
            if path.endswith(".py")
        ]

        handoffs: list[dict[str, Any]] = []
        if doc_impact:
            payload = {
                "source": "qa_supervisor",
                "task_id": task.task_id,
                "doc_impact": doc_impact,
                "scenarios": scenarios[:3],
            }
            response = await self.delegate_client.delegate("documentation", payload)
            handoffs.append(
                {
                    "target": "documentation",
                    "payload": payload,
                    "response": response,
                }
            )

        return QAOutput(
            scenarios=scenarios,
            review_notes=review_notes,
            test_plan=test_plan,
            doc_impact=doc_impact,
            handoff_requests=handoffs,
        )

    async def clarify_doc_question(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "target": "qa",
            "message": "QA clarification provided",
            "clarification": {
                "risk_focus": "behavioral regression",
                "expected_validation": "unit + smoke",
            },
            "payload": payload,
        }


class DocumentationSupervisorRuntime:
    def __init__(self, delegate_client: DelegateClient):
        self.delegate_client = delegate_client

    def _write_file(self, repo_path: str, relative_path: str, content: str) -> str:
        file_path = Path(repo_path) / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return relative_path

    async def run(
        self,
        task: TaskContext,
        research: ResearchBrief,
        qa_output: QAOutput,
    ) -> DocsOutput:
        acknowledgements: list[dict[str, Any]] = []

        if not qa_output.doc_impact:
            clarify_payload = {
                "source": "documentation_supervisor",
                "task_id": task.task_id,
                "question": "Any behavior-level changes needing docs?",
            }
            clarify = await self.delegate_client.delegate("qa", clarify_payload)
            acknowledgements.append(
                {
                    "target": "qa",
                    "payload": clarify_payload,
                    "response": clarify,
                }
            )

        api_docs = [
            "Calculator API: add, subtract, multiply, divide",
            "Division raises ZeroDivisionError for zero denominator",
        ]
        release_notes = [
            f"Task {task.task_id}: {task.description}",
            f"QA scenarios covered: {len(qa_output.scenarios)}",
            f"Test plan items: {len(qa_output.test_plan)}",
        ]
        runbook_updates = [
            "Runbook: execute pytest -q for calculator validation",
            "Runbook: verify CLI behavior if calculator/cli.py is present",
        ]

        self._write_file(
            task.repo_path,
            "docs/api.md",
            "# API\n\n" + "\n".join(f"- {line}" for line in api_docs) + "\n",
        )
        self._write_file(
            task.repo_path,
            "docs/release_notes.md",
            "# Release Notes\n\n" + "\n".join(f"- {line}" for line in release_notes) + "\n",
        )
        self._write_file(
            task.repo_path,
            "docs/runbook.md",
            "# Runbook\n\n" + "\n".join(f"- {line}" for line in runbook_updates) + "\n",
        )
        self._write_file(
            task.repo_path,
            "docs/qa_report.md",
            "# QA Report\n\n"
            + "## Scenarios\n"
            + "\n".join(f"- {line}" for line in qa_output.scenarios)
            + "\n\n## Review Notes\n"
            + "\n".join(f"- {line}" for line in qa_output.review_notes)
            + "\n\n## Test Plan\n"
            + "\n".join(f"- {line}" for line in qa_output.test_plan)
            + "\n",
        )

        if qa_output.handoff_requests:
            acknowledgements.extend(qa_output.handoff_requests)

        return DocsOutput(
            api_docs=api_docs,
            release_notes=release_notes,
            runbook_updates=runbook_updates,
            acknowledgements=acknowledgements,
        )

    async def preview_doc_impact(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "target": "documentation",
            "message": "Documentation impact acknowledged",
            "accepted_items": list(payload.get("doc_impact", [])),
            "payload": payload,
        }


def build_runtime_supervisors() -> tuple[CoderSupervisorRuntime, QASupervisorRuntime, DocumentationSupervisorRuntime, InProcessDelegateClient]:
    """Factory to build local in-process runtime with explicit handoff seam."""
    delegate = InProcessDelegateClient()
    coder = CoderSupervisorRuntime()
    qa = QASupervisorRuntime(delegate)
    docs = DocumentationSupervisorRuntime(delegate)
    delegate.register("documentation", docs.preview_doc_impact)
    delegate.register("qa", qa.clarify_doc_question)
    return coder, qa, docs, delegate
