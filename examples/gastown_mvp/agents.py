"""Supervisor/sub-agent runtime and metadata registrations for Gastown MVP."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.core.decorators import agent
from examples.gastown_mvp.contracts import DocsOutput, QAOutput, ResearchBrief, TaskContext

# ---------------------------------------------------------------------------
# Metadata-only data agents (for hierarchy definitions / discovery)
# ---------------------------------------------------------------------------


class _MetadataAgentBase(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        return AgentResult(
            data={"query": query, "ok": True, "kwargs": kwargs},
            source=self.__class__.__name__,
            query=query,
        )


@agent(name="qa_lead", description="Leads QA orchestration", capabilities=["qa_coordination"], version="1.0.0")
class QALeadMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="qa_scenario_designer", description="Designs explicit test scenarios", capabilities=["scenario_design"], version="1.0.0")
class QAScenarioDesignerMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="qa_code_reviewer", description="Reviews code changes for risk", capabilities=["code_review"], version="1.0.0")
class QACodeReviewerMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="qa_test_executor", description="Plans and executes tests", capabilities=["test_execution"], version="1.0.0")
class QATestExecutorMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="docs_lead", description="Leads documentation updates", capabilities=["documentation_coordination"], version="1.0.0")
class DocsLeadMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="docs_api_writer", description="Writes API documentation", capabilities=["api_docs"], version="1.0.0")
class DocsAPIWriterMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="docs_release_notes_writer", description="Produces release notes", capabilities=["release_notes"], version="1.0.0")
class DocsReleaseNotesMetadataAgent(_MetadataAgentBase):
    pass


@agent(name="docs_runbook_writer", description="Updates operational runbooks", capabilities=["runbook_updates"], version="1.0.0")
class DocsRunbookMetadataAgent(_MetadataAgentBase):
    pass


# ---------------------------------------------------------------------------
# Delegate seam (local implementation today, remote proxy later)
# ---------------------------------------------------------------------------


class DelegateClient(Protocol):
    """Abstraction seam for in-process vs remote handoff delegation."""

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


# ---------------------------------------------------------------------------
# QA runtime
# ---------------------------------------------------------------------------


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
        plan = [
            "Run focused unit tests for touched modules",
            "Run smoke/integration suite for impacted flow",
            "Record failures with reproduction hints",
        ]
        return plan


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


# ---------------------------------------------------------------------------
# Documentation runtime
# ---------------------------------------------------------------------------


class APIDocsWriterAgent:
    async def run(self, task: TaskContext, research: ResearchBrief, doc_impact: list[str]) -> list[str]:
        if not doc_impact:
            return ["No API contract changes identified"]
        return [f"Update API docs: {item}" for item in doc_impact[:5]]


class ReleaseNotesWriterAgent:
    async def run(self, task: TaskContext, qa_output: QAOutput) -> list[str]:
        return [
            f"Task {task.task_id}: {task.description}",
            f"QA scenarios covered: {len(qa_output.scenarios)}",
            f"Test plan items: {len(qa_output.test_plan)}",
        ]


class RunbookWriterAgent:
    async def run(self, research: ResearchBrief) -> list[str]:
        if not research.risks:
            return ["Runbook unchanged: no new operational risks detected"]
        return [f"Runbook update: monitor {risk}" for risk in research.risks]


class DocumentationSupervisorRuntime:
    def __init__(self, delegate_client: DelegateClient):
        self.delegate_client = delegate_client
        self.api_writer = APIDocsWriterAgent()
        self.release_notes_writer = ReleaseNotesWriterAgent()
        self.runbook_writer = RunbookWriterAgent()

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

        api_docs = await self.api_writer.run(task, research, qa_output.doc_impact)
        release_notes = await self.release_notes_writer.run(task, qa_output)
        runbook_updates = await self.runbook_writer.run(research)

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


def build_runtime_supervisors() -> tuple[QASupervisorRuntime, DocumentationSupervisorRuntime, InProcessDelegateClient]:
    """Factory to build a local in-process runtime with explicit handoff seam."""
    delegate = InProcessDelegateClient()
    qa = QASupervisorRuntime(delegate)
    docs = DocumentationSupervisorRuntime(delegate)
    delegate.register("documentation", docs.preview_doc_impact)
    delegate.register("qa", qa.clarify_doc_question)
    return qa, docs, delegate
