"""
Usage Examples for AgentOrchestrator

Shows:
- Simple chain with optional RAG retrieval and chat history
- Multi-agent supervisor usage with optional vector store and chat storage
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agentorchestrator import AgentOrchestrator, Context
from agentorchestrator.services import (
    VectorDocument,
    VectorStoreService,
)
from agentorchestrator.squad.storage.memory import InMemoryChatStorage
from agentorchestrator.examples.supervisor_chain import create_supervisor_orchestrator

try:  # Optional Redis chat storage
    from agentorchestrator.squad.storage.redis import RedisChatStorage
except Exception:  # pragma: no cover - redis optional
    RedisChatStorage = None  # type: ignore

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                     SIMPLE CHAIN WITH OPTIONAL RAG + HISTORY
# ═══════════════════════════════════════════════════════════════════════════════


def create_simple_chain(
    vector_store: VectorStoreService | None = None,
    chat_storage: Any | None = None,
) -> AgentOrchestrator:
    """
    Create a simple chain that optionally uses RAG context and chat history.

    - If no vector_store is provided, retrieval is skipped.
    - If no chat_storage is provided, history is stored in-memory only.
    """
    vs = vector_store or VectorStoreService()
    storage = chat_storage or InMemoryChatStorage()

    ao = AgentOrchestrator(name="simple_rag_example", isolated=True)

    @ao.step(name="retrieve", description="Retrieve context (optional RAG)")
    async def retrieve(ctx: Context) -> dict[str, Any]:
        query = ctx.get("query", "")
        if not query or not vs:
            ctx.set("rag_context", [])
            return {"rag_context": []}
        matches = await vs.query(query, top_k=3)
        ctx.set("rag_context", matches)
        return {"rag_context": matches}

    @ao.step(name="answer", deps=["retrieve"])
    async def answer(ctx: Context) -> dict[str, Any]:
        # History can be stored by callers if desired; this step just reads context.
        snippets = ctx.get("rag_context", [])
        text = ctx.get("query", "No query")
        return {
            "answer": f"Response for: {text}",
            "context_used": len(snippets),
        }

    @ao.chain(name="simple_chain")
    class SimpleChain:
        steps = ["retrieve", "answer"]

    # Optionally, callers can persist history before/after launch using storage.
    ao.chat_storage = storage  # type: ignore[attr-defined]

    return ao


async def run_simple_chain_example():
    """Run the simple chain example."""
    vs = VectorStoreService()
    await vs.upsert([
        VectorDocument(id="doc1", text="Use async/await for I/O in Python APIs."),
        VectorDocument(id="doc2", text="Implement caching with Redis for hot keys."),
    ])

    ao = create_simple_chain(vector_store=vs)
    result = await ao.launch("simple_chain", {"query": "How do I optimize a Python API?"})

    print("Simple chain result:", result)


# ═══════════════════════════════════════════════════════════════════════════════
#                     MULTI-AGENT SUPERVISOR USAGE (DECORATOR PATH)
# ═══════════════════════════════════════════════════════════════════════════════


async def run_supervisor_example():
    """
    Run the decorator-based supervisor chain with optional RAG + chat storage.

    Notes:
    - Pass llm_client for real LLM calls; omit for mock responses.
    - If vector_store is None, retrieval is skipped.
    - If chat_storage is None, history is stored in-memory per agent.
    """
    vector_store = VectorStoreService()
    chat_storage = RedisChatStorage() if RedisChatStorage else InMemoryChatStorage()

    # Build supervisor orchestrator (imports agents/steps from supervisor_chain)
    ao = create_supervisor_orchestrator(
        llm_client=None,           # Replace with LLMGatewayClient for real calls
        vector_store=vector_store,
        chat_storage=chat_storage,
        agent_timeout_seconds=30.0,
    )

    # Seed some retrievable docs
    await vector_store.upsert([
        VectorDocument(id="api", text="Use async/await and connection pooling for APIs."),
        VectorDocument(id="sql", text="Use indexes and limit scans for SQL performance."),
    ])

    # Launch supervisor chain with user/session for history tracking
    result = await ao.launch("supervisor_chain", {
        "query": "How do I optimize my Python API that hits SQL?",
        "user_id": "user-123",
        "session_id": "session-abc",
    })

    print("Supervisor chain result:", result)


if __name__ == "__main__":
    asyncio.run(run_simple_chain_example())
    asyncio.run(run_supervisor_example())
