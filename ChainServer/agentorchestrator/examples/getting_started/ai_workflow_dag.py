"""
AI Workflow DAG Example
=======================

Build a DAG-style AI workflow with four tiny steps:

    plan -> (search_web, retrieve_docs) -> synthesize

Steps with the same dependency run in parallel, and the DAG is inferred
from simple deps=... declarations.

Usage:
    python ai_workflow_dag.py

What this example demonstrates:
    - DAG-style AI workflow with parallel branches
    - Clean data flow via context
    - Zero external dependencies (LLM calls stubbed)
"""

from __future__ import annotations

import asyncio

from agentorchestrator import AgentOrchestrator


def fake_llm(prompt: str) -> str:
    """Stubbed LLM call for example purposes."""
    return f"Plan: gather web + docs for '{prompt}'"


def fake_search(query: str) -> list[str]:
    """Stubbed web search."""
    return [
        f"Web result: {query} - key point A",
        f"Web result: {query} - key point B",
    ]


def fake_retrieve(query: str) -> list[str]:
    """Stubbed document retrieval."""
    return [
        f"Doc snippet: {query} - internal note 1",
        f"Doc snippet: {query} - internal note 2",
    ]


def create_ai_workflow_orchestrator() -> AgentOrchestrator:
    """Create a small DAG-style AI workflow."""
    ao = AgentOrchestrator(name="ai_workflow", isolated=True)

    @ao.step(name="plan")
    async def plan(ctx):
        question = ctx.get("question", "What is AgentOrchestrator?")
        plan_text = fake_llm(question)
        ctx.set("research_query", question)
        ctx.set("plan", plan_text)
        return {"plan": plan_text}

    # These two steps run in parallel (same dependency: "plan")
    @ao.step(name="search_web", deps=["plan"])
    async def search_web(ctx):
        query = ctx.get("research_query")
        notes = fake_search(query)
        ctx.set("web_notes", notes)
        return {"web_notes": notes}

    @ao.step(name="retrieve_docs", deps=["plan"])
    async def retrieve_docs(ctx):
        query = ctx.get("research_query")
        notes = fake_retrieve(query)
        ctx.set("doc_notes", notes)
        return {"doc_notes": notes}

    @ao.step(name="synthesize", deps=["search_web", "retrieve_docs"])
    async def synthesize(ctx):
        plan_text = ctx.get("plan", "")
        web_notes = ctx.get("web_notes", [])
        doc_notes = ctx.get("doc_notes", [])
        summary = (
            f"{plan_text}\n"
            f"- Web: {web_notes[0] if web_notes else 'n/a'}\n"
            f"- Docs: {doc_notes[0] if doc_notes else 'n/a'}"
        )
        ctx.set("summary", summary)
        return {"summary": summary}

    @ao.chain(name="ai_workflow")
    class AIWorkflow:
        steps = ["plan", "search_web", "retrieve_docs", "synthesize"]

    return ao


async def run_ai_workflow(ao: AgentOrchestrator, question: str) -> dict:
    return await ao.launch("ai_workflow", {"question": question})


def main() -> None:
    question = "How does AgentOrchestrator make DAG workflows easy?"
    ao = create_ai_workflow_orchestrator()
    result = asyncio.run(run_ai_workflow(ao, question))

    # Pull final output from context (synthesize step writes it there)
    summary = result["context"]["data"]["summary"]

    print("\nDAG (auto-generated):")
    ao.graph("ai_workflow")

    print("\nSummary:")
    print(summary)


if __name__ == "__main__":
    main()
