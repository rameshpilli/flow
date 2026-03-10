"""Tests for Gastown MVP hierarchy metadata registration APIs."""

from __future__ import annotations

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.core.decorators import (
    agent as global_agent,
)
from agentorchestrator.core.decorators import (
    chain as global_chain,
)
from agentorchestrator.core.decorators import (
    step as global_step,
)
from agentorchestrator.core.decorators import (
    suite as global_suite,
)
from agentorchestrator.core.decorators import (
    supervisor as global_supervisor,
)
from agentorchestrator.core.orchestrator import (
    AgentOrchestrator,
    get_orchestrator,
    set_orchestrator,
)


class _StubAgent(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        return AgentResult(data={"query": query, "kwargs": kwargs}, source="stub", query=query)


def test_hierarchy_registration_and_agent_metadata_persistence():
    ao = AgentOrchestrator(name="hierarchy-test", isolated=True)

    @ao.agent(name="qa_lead", capabilities=["qa_coordination"], version="2.1.0")
    class QALead(_StubAgent):
        pass

    @ao.agent(name="qa_reviewer", capabilities=["code_review"], version="2.1.0")
    class QAReviewer(_StubAgent):
        pass

    @ao.supervisor(name="qa_supervisor", lead_agent="qa_lead", team=["qa_reviewer"])
    class QASupervisor:
        pass

    @ao.step(name="entry_step")
    async def entry_step(ctx):
        return {"ok": True}

    @ao.chain(name="entry_chain")
    class EntryChain:
        steps = ["entry_step"]

    @ao.suite(
        name="qa_suite",
        version="1.0.0",
        root_supervisor="qa_supervisor",
        entry_chain="entry_chain",
        capabilities=["qa"],
    )
    class QASuite:
        pass

    check = ao.check()
    assert check["valid"] is True
    assert check["hierarchy"]["stats"]["supervisors"] == 1
    assert check["hierarchy"]["stats"]["suites"] == 1

    agents = {item["name"]: item for item in ao.list_agents(detailed=True)}
    assert agents["qa_lead"]["capabilities"] == ["qa_coordination"]
    assert agents["qa_lead"]["version"] == "2.1.0"

    supervisor = ao.get_supervisor_spec("qa_supervisor")
    suite = ao.get_suite_spec("qa_suite")
    assert supervisor is not None
    assert suite is not None
    assert supervisor["lead_agent"] == "qa_lead"
    assert suite["entry_chain"] == "entry_chain"


def test_module_level_supervisor_and_suite_decorators_register_metadata():
    old_orchestrator = get_orchestrator()
    ao = AgentOrchestrator(name="global-wrapper-test", isolated=True)
    set_orchestrator(ao)

    try:
        @global_agent(name="docs_lead", capabilities=["docs"], version="3.0.0")
        class DocsLead(_StubAgent):
            pass

        @global_step(name="docs_entry")
        async def docs_entry(ctx):
            return {"ok": True}

        @global_chain(name="docs_chain")
        class DocsChain:
            steps = ["docs_entry"]

        @global_supervisor(name="docs_supervisor", lead_agent="docs_lead", team=["docs_lead"])
        class DocsSupervisor:
            pass

        @global_suite(name="docs_suite", root_supervisor="docs_supervisor", entry_chain="docs_chain")
        class DocsSuite:
            pass

        assert "docs_supervisor" in ao.list_supervisors()
        assert "docs_suite" in ao.list_suites()
        details = {item["name"]: item for item in ao.list_agents(detailed=True)}
        assert details["docs_lead"]["version"] == "3.0.0"
        assert details["docs_lead"]["capabilities"] == ["docs"]
    finally:
        set_orchestrator(old_orchestrator)
