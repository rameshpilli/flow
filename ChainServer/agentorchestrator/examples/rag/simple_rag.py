"""
Simple RAG Example
==================

Basic Retrieval-Augmented Generation pipeline.

Usage:
    python simple_rag.py

    # With custom query
    python simple_rag.py --query "How do I optimize API performance?"

What this example demonstrates:
    - Setting up VectorStoreService
    - Upserting documents with embeddings
    - Retrieving relevant context
    - Building a RAG chain

Expected output:
    === Simple RAG Example ===

    Upserting knowledge base documents...
    Upserted 4 documents

    Query: How do I optimize my Python API?

    Step 1: Retrieving relevant context...
    Found 3 relevant documents:
      1. [score: 0.92] Use async/await for I/O-bound operations in Python APIs...
      2. [score: 0.85] Implement caching with Redis for frequently accessed data...
      3. [score: 0.78] Use connection pooling for database connections...

    Step 2: Generating response with context...

    Response:
    Based on the retrieved context, here are recommendations for optimizing
    your Python API:
    1. Use async/await for I/O operations
    2. Implement Redis caching
    3. Use connection pooling for databases
"""

from __future__ import annotations

import asyncio
import argparse

from agentorchestrator import AgentOrchestrator
from agentorchestrator.services import VectorStoreService, VectorDocument


async def setup_knowledge_base(vs: VectorStoreService) -> int:
    """
    Populate the vector store with sample documents.

    In production, this would be your actual knowledge base
    (documentation, FAQs, policies, etc.)

    Args:
        vs: VectorStoreService instance

    Returns:
        Number of documents upserted
    """
    documents = [
        VectorDocument(
            id="doc1",
            text="Use async/await for I/O-bound operations in Python APIs. "
                 "This allows handling multiple requests concurrently without "
                 "blocking, significantly improving throughput.",
            metadata={"topic": "python", "category": "performance"},
        ),
        VectorDocument(
            id="doc2",
            text="Implement caching with Redis for frequently accessed data. "
                 "Cache database queries, API responses, and computed results "
                 "to reduce latency and database load.",
            metadata={"topic": "caching", "category": "performance"},
        ),
        VectorDocument(
            id="doc3",
            text="Use connection pooling for database connections. "
                 "Creating new connections is expensive; pools maintain "
                 "reusable connections for better performance.",
            metadata={"topic": "database", "category": "performance"},
        ),
        VectorDocument(
            id="doc4",
            text="Implement rate limiting to protect your API from abuse. "
                 "Use token buckets or sliding windows to control request rates "
                 "per client or globally.",
            metadata={"topic": "security", "category": "api-design"},
        ),
    ]

    await vs.upsert(documents)
    return len(documents)


def create_rag_orchestrator(
    vector_store: VectorStoreService | None = None,
) -> AgentOrchestrator:
    """
    Create a RAG orchestrator.

    Args:
        vector_store: Optional vector store (creates new if None)

    Returns:
        Configured AgentOrchestrator with RAG chain
    """
    vs = vector_store or VectorStoreService()

    ao = AgentOrchestrator(name="simple_rag", isolated=True)

    @ao.step(name="retrieve", description="Retrieve relevant context from vector store")
    async def retrieve(ctx):
        """
        Step 1: Retrieve relevant documents.

        Queries the vector store and stores matches in context.
        """
        query = ctx.get("query", "")
        top_k = ctx.get("top_k", 3)

        if not query:
            ctx.set("rag_context", [])
            return {"retrieved": 0, "error": "No query provided"}

        print(f"\nStep 1: Retrieving relevant context...")
        matches = await vs.query(query, top_k=top_k)

        # Store in context for generate step
        ctx.set("rag_context", matches)

        if matches:
            print(f"Found {len(matches)} relevant documents:")
            for i, match in enumerate(matches, 1):
                score = getattr(match, 'score', 0.0)
                text_preview = match.text[:60] + "..." if len(match.text) > 60 else match.text
                print(f"  {i}. [score: {score:.2f}] {text_preview}")
        else:
            print("  No relevant documents found")

        return {"retrieved": len(matches)}

    @ao.step(name="generate", deps=["retrieve"], description="Generate response with context")
    async def generate(ctx):
        """
        Step 2: Generate response using retrieved context.

        In production, this would call an LLM with the context.
        This example simulates the response.
        """
        print(f"\nStep 2: Generating response with context...")

        query = ctx.get("query", "")
        rag_context = ctx.get("rag_context", [])

        # Format context for response
        if rag_context:
            context_texts = [match.text for match in rag_context]
            context_summary = "\n- ".join(context_texts)

            # Simulated LLM response (in production, call actual LLM)
            response = (
                f"Based on the retrieved context, here are recommendations:\n\n"
                f"- {context_summary}\n\n"
                f"These practices address: {query}"
            )
        else:
            response = f"I don't have specific information about: {query}"

        return {
            "response": response,
            "context_used": len(rag_context),
            "query": query,
        }

    @ao.chain(name="rag_chain")
    class RAGChain:
        """
        Two-step RAG chain:
        1. retrieve - Get relevant context
        2. generate - Create response with context
        """
        steps = ["retrieve", "generate"]

    # Attach vector store for external access
    ao.vector_store = vs  # type: ignore

    return ao


async def run_simple_rag(query: str = "How do I optimize my Python API?") -> dict:
    """
    Run the simple RAG example.

    Args:
        query: User question to answer

    Returns:
        Result with response and metadata
    """
    print("=== Simple RAG Example ===\n")

    # Setup vector store
    vs = VectorStoreService()

    print("Upserting knowledge base documents...")
    doc_count = await setup_knowledge_base(vs)
    print(f"Upserted {doc_count} documents")

    print(f"\nQuery: {query}")

    # Create and run RAG chain
    ao = create_rag_orchestrator(vector_store=vs)
    result = await ao.launch("rag_chain", {"query": query, "top_k": 3})

    print(f"\nResponse:\n{result.get('response', 'No response')}")

    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Simple RAG example")
    parser.add_argument(
        "--query",
        default="How do I optimize my Python API?",
        help="Question to answer using RAG",
    )
    args = parser.parse_args()

    asyncio.run(run_simple_rag(args.query))


if __name__ == "__main__":
    main()
