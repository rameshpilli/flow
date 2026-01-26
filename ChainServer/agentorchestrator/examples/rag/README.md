# RAG Examples

Retrieval-Augmented Generation examples with VectorStoreService.

## Overview

RAG enhances LLM responses by retrieving relevant context from a knowledge base before generating answers.

```
User Query → Vector Search → Relevant Docs → LLM + Context → Response
```

## Examples

### 1. Simple RAG

Basic RAG pipeline with VectorStoreService.

```bash
python simple_rag.py
```

**What you'll learn:**
- Setting up VectorStoreService
- Upserting documents with embeddings
- Querying for relevant context
- Integrating with LLM responses

### 2. RAG with Chat History

RAG that maintains conversation context.

```bash
python rag_with_history.py
```

**What you'll learn:**
- Combining RAG with chat storage
- Context-aware retrieval
- Multi-turn conversations

## Quick Reference

### VectorStoreService

```python
from agentorchestrator.services import VectorStoreService, VectorDocument

# Create service
vs = VectorStoreService()

# Upsert documents
await vs.upsert([
    VectorDocument(id="doc1", text="Python async/await guide"),
    VectorDocument(id="doc2", text="FastAPI best practices"),
])

# Query for relevant docs
results = await vs.query("How do I use async?", top_k=3)
for match in results:
    print(f"{match.id}: {match.score:.2f} - {match.text[:50]}...")
```

### RAG in a Chain

```python
@ao.step(name="retrieve", description="Retrieve relevant context")
async def retrieve(ctx):
    query = ctx.get("query")
    matches = await vector_store.query(query, top_k=3)
    ctx.set("rag_context", matches)
    return {"retrieved": len(matches)}

@ao.step(name="generate", deps=["retrieve"])
async def generate(ctx):
    query = ctx.get("query")
    context = ctx.get("rag_context")

    # Format context for LLM
    context_text = "\n".join([m.text for m in context])

    response = await llm.generate(
        f"Context:\n{context_text}\n\nQuestion: {query}"
    )
    return {"response": response}
```

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        RAG Pipeline                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐  │
│  │ User Query  │────▶│ Vector Store │────▶│  Retrieved   │  │
│  └─────────────┘     │   Search     │     │   Context    │  │
│                      └──────────────┘     └──────┬───────┘  │
│                                                   │          │
│                                                   ▼          │
│                      ┌──────────────┐     ┌──────────────┐  │
│                      │     LLM      │◀────│   Prompt +   │  │
│                      │   Generate   │     │   Context    │  │
│                      └──────┬───────┘     └──────────────┘  │
│                             │                                │
│                             ▼                                │
│                      ┌──────────────┐                        │
│                      │   Response   │                        │
│                      └──────────────┘                        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Configuration

### Vector Store Options

| Option | Description | Default |
|--------|-------------|---------|
| `embedding_model` | Model for embeddings | `text-embedding-ada-002` |
| `similarity_metric` | Distance metric | `cosine` |
| `top_k` | Default results to return | `5` |

### Environment Variables

```bash
# For remote vector store
VECTOR_PROVIDER=cohere_compass # or 'redis', 'pinecone'
COHERE_COMPASS_URL=https://compass.corp.com
COHERE_COMPASS_API_KEY=your-key
COHERE_COMPASS_INDEX_NAME=my-index
```
