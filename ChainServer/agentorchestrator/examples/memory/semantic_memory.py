"""
Semantic Memory Example
=======================

Demonstrates Mem0 semantic memory for cross-session recall.

Usage:
    python semantic_memory.py

What this example demonstrates:
    - Storing memories with metadata
    - Semantic search across sessions
    - Cross-session memory recall
    - Getting context for LLM prompts

Note:
    Requires corporate MemoryStoreClient. This example uses a mock
    implementation for demonstration purposes.

Expected output:
    === Semantic Memory (Mem0) Example ===

    Adding memories...
      Added: User prefers technical explanations with code examples
      Added: User is working on a Python FastAPI project
      Added: User's timezone is PST

    Searching for 'coding preferences'...
    Found 2 relevant memories:
      1. User prefers technical explanations with code examples (score: 0.92)
      2. User is working on a Python FastAPI project (score: 0.78)

    Getting context for 'How should I format my response?'...
    Context for LLM:
    Relevant memories:
    - User prefers technical explanations with code examples
    - User is working on a Python FastAPI project
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# Mock MemoryStoreClient for demonstration
# In production, import from your corporate package:
# from your_app import MemoryStoreClient
@dataclass
class MockMemoryEntry:
    """Mock memory entry."""
    id: str
    memory: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0


class MockMemoryStoreClient:
    """
    Mock implementation of corporate MemoryStoreClient.

    In production, replace with actual corporate client:
        from your_app import MemoryStoreClient
    """

    def __init__(self, base_url: str, agent_id: str):
        self.base_url = base_url
        self.agent_id = agent_id
        self._memories: list[MockMemoryEntry] = []
        self._id_counter = 0

    def add(self, memory: str, metadata: dict | None = None) -> dict:
        """Add a memory."""
        self._id_counter += 1
        entry = MockMemoryEntry(
            id=f"mem_{self._id_counter}",
            memory=memory,
            metadata=metadata or {},
        )
        self._memories.append(entry)
        return {"id": entry.id}

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search memories semantically.

        This mock uses simple keyword matching.
        Production uses vector embeddings.
        """
        results = []
        query_words = set(query.lower().split())

        for mem in self._memories:
            # Simple relevance scoring based on word overlap
            mem_words = set(mem.memory.lower().split())
            overlap = len(query_words & mem_words)
            if overlap > 0:
                score = overlap / len(query_words)
                results.append({
                    "id": mem.id,
                    "memory": mem.memory,
                    "metadata": mem.metadata,
                    "score": min(score * 1.5, 1.0),  # Boost scores
                })

        # Sort by score and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def get_all(self) -> list[dict]:
        """Get all memories."""
        return [
            {"id": m.id, "memory": m.memory, "metadata": m.metadata}
            for m in self._memories
        ]

    def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        self._memories = [m for m in self._memories if m.id != memory_id]
        return True


async def run_semantic_memory_example():
    """
    Run the semantic memory example.

    Demonstrates how Mem0Memory enables:
    - Long-term memory across sessions
    - Semantic search for relevant context
    - Automatic context retrieval for LLM prompts
    """
    from agentorchestrator.services import Mem0Memory

    print("=== Semantic Memory (Mem0) Example ===\n")

    # Create mock client (replace with real client in production)
    client = MockMemoryStoreClient(
        base_url="https://mem0.corp.com",
        agent_id="demo-agent"
    )

    # Wrap with Mem0Memory
    memory = Mem0Memory(client=client, default_user_id="user-123")

    # Add memories
    print("Adding memories...")
    memories_to_add = [
        "User prefers technical explanations with code examples",
        "User is working on a Python FastAPI project",
        "User's timezone is PST",
        "User asked about async/await patterns last week",
    ]

    for text in memories_to_add:
        entry = await memory.add(text)
        print(f"  Added: {text}")

    # Semantic search
    print("\nSearching for 'coding preferences'...")
    results = await memory.search("coding preferences technical")

    if results:
        print(f"Found {len(results)} relevant memories:")
        for i, mem in enumerate(results, 1):
            score = getattr(mem, 'relevance_score', 0)
            print(f"  {i}. {mem.content} (score: {score:.2f})")
    else:
        print("  No relevant memories found")

    # Get context for LLM prompt
    print("\nGetting context for 'How should I format my response?'...")
    context = await memory.get_context_for_query(
        query="How should I format my response?",
        limit=3,
    )

    print("Context for LLM:")
    print(context)

    # Demonstrate cross-session recall
    print("\n--- Cross-Session Recall ---")
    print("Searching for 'async patterns' (from previous session)...")
    results = await memory.search("async patterns")
    if results:
        print(f"  Recalled: {results[0].content}")
    else:
        print("  No memories found")

    return {
        "memories_added": len(memories_to_add),
        "search_results": len(results) if results else 0,
    }


async def run_with_agent_example():
    """
    Demonstrate using Mem0Memory with an agent.

    Shows how memory integrates into agent workflows for
    personalized, context-aware responses.
    """
    from agentorchestrator.services import Mem0Memory

    print("\n=== Memory with Agent Workflow ===\n")

    # Setup (mock client)
    client = MockMemoryStoreClient(
        base_url="https://mem0.corp.com",
        agent_id="assistant"
    )
    memory = Mem0Memory(client=client)

    # Simulate agent workflow
    user_id = "client-123"

    # Session 1: User provides preferences
    print("Session 1: Learning user preferences...")
    await memory.add(
        "Client prefers bullet-point summaries over long paragraphs",
        user_id=user_id,
        session_id="session-1",
    )
    await memory.add(
        "Client is interested in AI/ML investments",
        user_id=user_id,
        session_id="session-1",
    )
    print("  Stored 2 preferences")

    # Session 2: Agent uses memories
    print("\nSession 2: Using stored preferences...")
    query = "Give me a market update"

    # Agent retrieves relevant context
    context = await memory.get_context_for_query(
        query=query,
        user_id=user_id,
        limit=3,
    )

    print(f"  Query: '{query}'")
    print(f"  Retrieved context:\n{context}")
    print("\n  Agent can now personalize response based on preferences!")


def main():
    """CLI entry point."""
    asyncio.run(run_semantic_memory_example())
    asyncio.run(run_with_agent_example())


if __name__ == "__main__":
    main()
