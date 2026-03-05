"""
RAG with Chat History Example
=============================

RAG pipeline that maintains conversation context.

Usage:
    python rag_with_history.py

What this example demonstrates:
    - Combining RAG with chat storage
    - Context-aware retrieval
    - Multi-turn conversations with memory
    - History-enhanced prompts

Expected output:
    === RAG with Chat History Example ===

    Setting up knowledge base...

    --- Turn 1 ---
    User: How do I optimize API performance?

    [Retrieving context...]
    [Generating with history: 0 previous messages]

    Assistant: Based on the documentation, here are key optimizations:
    - Use async/await for I/O operations
    - Implement caching with Redis
    ...

    --- Turn 2 ---
    User: Tell me more about the caching part

    [Retrieving context for follow-up...]
    [Generating with history: 2 previous messages]

    Assistant: Building on our previous discussion about caching:
    - Redis is recommended for hot keys
    - Set appropriate TTLs based on data freshness needs
    ...
"""

from __future__ import annotations

import asyncio

from agentorchestrator import AgentOrchestrator
from agentorchestrator.services import VectorStoreService, VectorDocument
from agentorchestrator.squad.storage import InMemoryChatStorage
from agentorchestrator.squad.types import ConversationMessage


async def setup_knowledge_base(vs: VectorStoreService) -> int:
    """Populate vector store with sample documents."""
    documents = [
        VectorDocument(
            id="perf1",
            text="Use async/await for I/O-bound operations in Python APIs. "
                 "This enables concurrent request handling without blocking.",
            metadata={"topic": "async"},
        ),
        VectorDocument(
            id="cache1",
            text="Implement caching with Redis for frequently accessed data. "
                 "Cache database queries and API responses. Set TTLs based on "
                 "data freshness requirements.",
            metadata={"topic": "caching"},
        ),
        VectorDocument(
            id="cache2",
            text="Redis caching strategies: Use hash types for structured data, "
                 "sorted sets for leaderboards, and lists for queues. Consider "
                 "cache-aside or write-through patterns based on your needs.",
            metadata={"topic": "caching"},
        ),
        VectorDocument(
            id="db1",
            text="Database optimization: Use connection pooling, add indexes "
                 "for frequent queries, and consider read replicas for scaling.",
            metadata={"topic": "database"},
        ),
    ]
    await vs.upsert(documents)
    return len(documents)


def create_rag_with_history_orchestrator(
    vector_store: VectorStoreService,
    chat_storage: InMemoryChatStorage,
) -> AgentOrchestrator:
    """
    Create RAG orchestrator with chat history support.

    Args:
        vector_store: Vector store for document retrieval
        chat_storage: Chat storage for conversation history

    Returns:
        Configured AgentOrchestrator
    """
    ao = AgentOrchestrator(name="rag_with_history", isolated=True)

    @ao.step(name="load_history", description="Load conversation history")
    async def load_history(ctx):
        """Load previous conversation for context."""
        user_id = ctx.get("user_id", "default")
        session_id = ctx.get("session_id", "default")
        agent_id = "rag_assistant"

        history = await chat_storage.fetch_chat(user_id, session_id, agent_id)
        ctx.set("chat_history", history)

        return {"history_loaded": len(history)}

    @ao.step(name="retrieve", deps=["load_history"], description="Retrieve with history context")
    async def retrieve(ctx):
        """
        Retrieve relevant documents.

        Uses chat history to enhance retrieval for follow-up questions.
        """
        query = ctx.get("query", "")
        history = ctx.get("chat_history", [])

        print(f"\n[Retrieving context...]")

        # For follow-up questions, include recent context in search
        if history and len(query.split()) < 5:
            # Short query likely a follow-up - include last topic
            last_exchange = history[-2:] if len(history) >= 2 else history
            context_hint = " ".join([
                msg.get_text() if hasattr(msg, 'get_text') else str(msg)
                for msg in last_exchange
            ])
            enhanced_query = f"{query} {context_hint[:100]}"
        else:
            enhanced_query = query

        matches = await vector_store.query(enhanced_query, top_k=3)
        ctx.set("rag_context", matches)

        return {"retrieved": len(matches)}

    @ao.step(name="generate", deps=["retrieve"], description="Generate with history")
    async def generate(ctx):
        """Generate response using RAG context and chat history."""
        query = ctx.get("query", "")
        history = ctx.get("chat_history", [])
        rag_context = ctx.get("rag_context", [])

        print(f"[Generating with history: {len(history)} previous messages]")

        # Build context-aware prompt
        history_text = ""
        if history:
            history_text = "Previous conversation:\n"
            for msg in history[-4:]:  # Last 4 messages
                role = msg.role if hasattr(msg, 'role') else 'unknown'
                text = msg.get_text() if hasattr(msg, 'get_text') else str(msg)
                history_text += f"  {role}: {text}\n"

        rag_text = ""
        if rag_context:
            rag_text = "Relevant documentation:\n"
            for match in rag_context:
                rag_text += f"  - {match.text}\n"

        # Simulated response (in production, call LLM)
        if history:
            response = (
                f"Building on our previous discussion:\n\n"
                f"Based on the documentation:\n"
            )
        else:
            response = "Based on the documentation:\n"

        if rag_context:
            for match in rag_context:
                response += f"- {match.text[:100]}...\n"
        else:
            response += "I don't have specific information on that topic."

        return {
            "response": response,
            "context_used": len(rag_context),
            "history_used": len(history),
        }

    @ao.step(name="save_exchange", deps=["generate"], description="Save to chat history")
    async def save_exchange(ctx):
        """Save the current exchange to chat history."""
        user_id = ctx.get("user_id", "default")
        session_id = ctx.get("session_id", "default")
        agent_id = "rag_assistant"

        query = ctx.get("query", "")
        response = ctx.get("response", "")

        # Save user message
        await chat_storage.save_chat_message(
            user_id, session_id, agent_id,
            ConversationMessage(role="user", content=[{"text": query}])
        )

        # Save assistant response
        await chat_storage.save_chat_message(
            user_id, session_id, agent_id,
            ConversationMessage(role="assistant", content=[{"text": response}])
        )

        return {"saved": True}

    @ao.chain(name="rag_history_chain")
    class RAGHistoryChain:
        """RAG chain with chat history support."""
        steps = ["load_history", "retrieve", "generate", "save_exchange"]

    return ao


async def run_rag_with_history():
    """
    Run RAG with chat history example.

    Simulates a multi-turn conversation where the system
    maintains context between exchanges.
    """
    print("=== RAG with Chat History Example ===\n")

    # Setup
    vs = VectorStoreService()
    storage = InMemoryChatStorage()

    print("Setting up knowledge base...")
    await setup_knowledge_base(vs)

    ao = create_rag_with_history_orchestrator(vs, storage)

    # Conversation context
    user_id = "user-123"
    session_id = "session-demo"

    # Turn 1: Initial question
    print("\n--- Turn 1 ---")
    query1 = "How do I optimize API performance?"
    print(f"User: {query1}")

    result1 = await ao.launch("rag_history_chain", {
        "query": query1,
        "user_id": user_id,
        "session_id": session_id,
    })

    print(f"\nAssistant: {result1.get('response', '')[:200]}...")

    # Turn 2: Follow-up question
    print("\n--- Turn 2 ---")
    query2 = "Tell me more about caching"
    print(f"User: {query2}")

    result2 = await ao.launch("rag_history_chain", {
        "query": query2,
        "user_id": user_id,
        "session_id": session_id,
    })

    print(f"\nAssistant: {result2.get('response', '')[:200]}...")

    # Turn 3: Another follow-up
    print("\n--- Turn 3 ---")
    query3 = "What Redis data structures should I use?"
    print(f"User: {query3}")

    result3 = await ao.launch("rag_history_chain", {
        "query": query3,
        "user_id": user_id,
        "session_id": session_id,
    })

    print(f"\nAssistant: {result3.get('response', '')[:200]}...")

    print("\n--- Summary ---")
    print(f"Turn 1: {result1.get('context_used', 0)} docs, {result1.get('history_used', 0)} history")
    print(f"Turn 2: {result2.get('context_used', 0)} docs, {result2.get('history_used', 0)} history")
    print(f"Turn 3: {result3.get('context_used', 0)} docs, {result3.get('history_used', 0)} history")

    return {
        "turns": 3,
        "final_history_size": result3.get("history_used", 0) + 2,
    }


def main():
    """CLI entry point."""
    asyncio.run(run_rag_with_history())


if __name__ == "__main__":
    main()
