# RAG Agent

**RAGAgent** is a specialized agent that combines vector search with LLM generation to provide grounded, factual answers. It retrieves relevant context from a vector store before generating responses.

## What is RAG?

Retrieval-Augmented Generation (RAG) addresses a key limitation of LLMs: their knowledge is fixed at training time. RAG agents:

1. **Retrieve** relevant documents from a vector store
2. **Augment** the prompt with retrieved context
3. **Generate** a grounded response

This enables answers based on your specific data, not just the model's training data.

## Quick Start

```python
from agentorchestrator.squad.agents.rag_agent import RAGAgent, RAGAgentOptions
from agentorchestrator.services.vector_store import VectorStoreConfig

# Configure the RAG agent
options = RAGAgentOptions(
    name="knowledge_agent",
    description="Answers questions using company knowledge base",
    model_id="gpt-4",
    vector_store_config=VectorStoreConfig(
        provider="chroma",
        collection_name="company_docs",
        persist_directory="./chroma_db",
    ),
    top_k=5,  # Retrieve top 5 most relevant documents
)

agent = RAGAgent(options)

# Process a question
response = await agent.process_request(
    input_text="What is our refund policy?",
    user_id="user_123",
    session_id="session_456",
    chat_history=[],
)
print(response.content)
```

## Configuration Options

`RAGAgentOptions` extends `LLMGatewayAgentOptions` with RAG-specific settings:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `vector_store_config` | `VectorStoreConfig` | `None` | Vector store configuration |
| `top_k` | `int` | `3` | Number of documents to retrieve |
| `context_prompt_template` | `str` | (see below) | Template for injecting context |

### Default Context Template

```python
context_prompt_template = (
    "Use the following pieces of retrieved context to answer the question. "
    "If you don't know the answer, just say that you don't know. "
    "\n\nContext:\n{context}\n\nQuestion: {query}"
)
```

### Custom Templates

You can customize how context is presented to the LLM:

```python
options = RAGAgentOptions(
    name="strict_rag",
    context_prompt_template="""
    Answer the question based ONLY on the following context.
    Do not use any external knowledge.
    If the context doesn't contain the answer, say "I don't have information about that."

    Context:
    {context}

    Question: {query}

    Answer:
    """,
    top_k=10,
)
```

## Vector Store Configuration

RAGAgent uses `VectorStoreService` for retrieval. Configure your vector store:

### Chroma (Local)

```python
from agentorchestrator.services.vector_store import VectorStoreConfig

config = VectorStoreConfig(
    provider="chroma",
    collection_name="documents",
    persist_directory="./data/chroma",
    embedding_model="text-embedding-ada-002",
)
```

### Pinecone (Cloud)

```python
config = VectorStoreConfig(
    provider="pinecone",
    index_name="production-docs",
    api_key=os.getenv("PINECONE_API_KEY"),
    environment="us-east-1-aws",
)
```

### Qdrant

```python
config = VectorStoreConfig(
    provider="qdrant",
    collection_name="knowledge_base",
    url="http://localhost:6333",
)
```

## Using RAGAgent in Multi-Agent Systems

RAGAgent integrates with the Squad system:

```python
from agentorchestrator.squad import Squad
from agentorchestrator.squad.agents.rag_agent import RAGAgent, RAGAgentOptions
from agentorchestrator.squad.agents.llm_gateway_agent import LLMGatewayAgent

# RAG agent for knowledge queries
rag_agent = RAGAgent(RAGAgentOptions(
    name="knowledge_agent",
    description="Answers questions using company documentation",
    vector_store_config=VectorStoreConfig(provider="chroma"),
    top_k=5,
))

# General chat agent
chat_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="chat_agent",
    description="General conversation and assistance",
    model_id="gpt-4",
))

# Create squad with both agents
squad = Squad(
    name="support_squad",
    agents=[rag_agent, chat_agent],
    default_agent="chat_agent",
)

# Squad automatically routes knowledge queries to RAG agent
response = await squad.process_request(
    input_text="What are the pricing tiers?",
    user_id="user_123",
    session_id="session_456",
)
```

## Integration with Steps

Use RAGAgent within an orchestrator step:

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="support_app")

rag_agent = RAGAgent(RAGAgentOptions(
    name="docs_agent",
    vector_store_config=VectorStoreConfig(provider="chroma"),
))

@ao.step(name="answer_question")
async def answer_question(ctx):
    question = ctx.get("question")

    response = await rag_agent.process_request(
        input_text=question,
        user_id=ctx.get("user_id", "anonymous"),
        session_id=ctx.request_id,
        chat_history=[],
    )

    ctx.set("answer", response.content)
    return {"answer": response.content}
```

## Error Handling

RAGAgent gracefully handles retrieval failures:

```python
# If vector store query fails, agent continues with fallback message
try:
    matches = await self.vector_store.query(input_text, top_k=self.rag_options.top_k)
    context_text = "\n".join([f"- {m.text}" for m in matches])
except Exception as e:
    logger.error(f"RAG Retrieval failed: {e}")
    context_text = "No context available (retrieval failed)."
```

The agent will still generate a response, but will acknowledge the missing context.

## Best Practices

### 1. Tune `top_k` for Your Use Case

- **Low `top_k` (1-3)**: Faster, more focused, less noise
- **High `top_k` (5-10)**: More context, better for complex queries
- **Very high `top_k` (10+)**: May exceed context limits, use with summarization

### 2. Optimize Your Vector Store

- Use appropriate chunk sizes (512-1024 tokens typically)
- Include metadata for filtering
- Re-index when documents change

### 3. Monitor Retrieval Quality

```python
# Log what was retrieved
@ao.step(name="debug_rag")
async def debug_rag(ctx):
    # Access retrieval results for debugging
    matches = await agent.vector_store.query(ctx.get("question"), top_k=5)
    for i, match in enumerate(matches):
        logger.info(f"Match {i+1}: score={match.score:.3f}, text={match.text[:100]}...")
```

### 4. Combine with Token Management

For large retrieval results, combine with TokenManagerMiddleware:

```python
from agentorchestrator.middleware.token_manager import TokenManagerMiddleware

ao.add_middleware(TokenManagerMiddleware(
    context_window=128000,
    reserved_output=8000,
))
```

## Comparison with Other Patterns

| Pattern | Use Case | Data Source |
|---------|----------|-------------|
| **RAGAgent** | Questions about specific documents | Vector store |
| **FunctionAgent** | Actions and API calls | Tools/functions |
| **LLMGatewayAgent** | General conversation | LLM only |
| **SupervisorAgent** | Coordinate multiple agents | Other agents |

## Next Steps

- [Multi-Agent Systems](multi_agent.md) - Combine RAG with other agents
- [Vector Store Service](../services/vector_store.md) - Configure vector stores
- [Context Management](../CONTEXT_MANAGEMENT.md) - Handle large contexts
