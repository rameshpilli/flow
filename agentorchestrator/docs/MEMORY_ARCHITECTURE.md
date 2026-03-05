# Memory Architecture Guide

This guide explains the different memory systems in AgentOrchestrator and when to use each.

## Overview

AgentOrchestrator supports a **three-layer memory architecture** designed for production AI applications:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MEMORY ARCHITECTURE                                   │
├─────────────────────┬─────────────────────┬─────────────────────────────────┤
│   SESSION MEMORY    │   AGENTIC MEMORY    │   RAG / REFERENCE MEMORY        │
│   (Redis)           │   (Mem0)            │   (Cohere Compass)              │
├─────────────────────┼─────────────────────┼─────────────────────────────────┤
│ Retention: Hours    │ Retention: Forever  │ Retention: Project lifetime     │
│ (configurable TTL)  │ (persistent)        │                                 │
├─────────────────────┼─────────────────────┼─────────────────────────────────┤
│ • Current convo     │ • User preferences  │ • Documents                     │
│ • Working drafts    │ • Learned patterns  │ • Knowledge base                │
│ • Undo/redo states  │ • Past decisions    │ • Reference materials           │
│ • Session context   │ • Cross-session     │ • Citations                     │
│                     │   knowledge         │                                 │
├─────────────────────┼─────────────────────┼─────────────────────────────────┤
│ "What just happened"│ "What do I know     │ "What's in the documents?"      │
│                     │  about this user?"  │                                 │
└─────────────────────┴─────────────────────┴─────────────────────────────────┘
```

---

## Memory Types Explained

### 1. Session Memory (Redis)

**Purpose**: Store temporary, session-scoped data that expires after a configurable time.

**Technology**: Redis with configurable TTL

**Use Cases**:
- Current conversation history
- Working drafts and intermediate results
- Undo/redo states
- Temporary context during a session

**Characteristics**:
- Fast read/write
- Automatic expiration (TTL)
- Per-user, per-session isolation
- NOT persistent across long time periods

```python
from agentorchestrator.squad.storage.redis import RedisChatStorage

# Users can configure their own retention period
session_storage = RedisChatStorage(
    ttl_seconds=86400,  # 24 hours (configurable!)
)

# Or shorter for quick sessions
session_storage = RedisChatStorage(ttl_seconds=3600)  # 1 hour

# Or longer for extended projects
session_storage = RedisChatStorage(ttl_seconds=604800)  # 7 days
```

---

### 2. Agentic Memory (Mem0)

**Purpose**: Store long-term knowledge that agents learn about users and contexts.

**Technology**: Mem0 (semantic memory service)

**Use Cases**:
- User preferences ("prefers technical explanations")
- Learned patterns ("usually asks about financials first")
- Past decisions and their rationale
- Cross-session knowledge ("last time discussed Tesla...")
- Agent learning and personalization

**Characteristics**:
- **Permanent storage** (NOT short-term!)
- Semantic search capability
- User/agent scoping
- Automatic consolidation of related memories
- Importance scoring

```python
from agentorchestrator.services import Mem0Memory

# Long-term agentic memory
agent_memory = Mem0Memory(
    client=mem0_client,
    user_id="user123",
)

# Store learned knowledge
await agent_memory.add("User prefers conservative financial projections")
await agent_memory.add("User's company is in the healthcare sector")

# Recall later (even in future sessions)
memories = await agent_memory.search("user preferences")
# Returns: ["User prefers conservative...", "User's company is..."]
```

**Important**: Mem0 is for **LONG-TERM** memory, not short-term. It's where agents store what they "learn" about users.

---

### 3. RAG / Reference Memory (Cohere Compass)

**Purpose**: Store and retrieve documents for Retrieval-Augmented Generation.

**Technology**: Cohere Compass (vector database)

**Use Cases**:
- Company documents and knowledge bases
- Reference materials (reports, research)
- Source documents for citations
- Any content you want to "search" semantically

**Characteristics**:
- Document-oriented (not memory-oriented)
- Semantic search with similarity scoring
- Chunking and parsing built-in
- Citation tracking
- High-performance enterprise retrieval

```python
from agentorchestrator.services import VectorStoreService, VectorDocument

# Reference document storage
reference_store = VectorStoreService(
    provider="cohere_compass",
    index_name="company_knowledge_base",
)

# Add documents
await reference_store.add_documents([
    VectorDocument(id="doc1", text="Q4 earnings report...", metadata={"type": "financial"}),
    VectorDocument(id="doc2", text="Market analysis...", metadata={"type": "research"}),
])

# Search for relevant content
results = await reference_store.search("Q4 revenue projections", top_k=5)
for match in results:
    print(f"Score: {match.score}, Text: {match.text[:100]}...")
```

---

## Comparison Table

| Aspect | Session (Redis) | Agentic (Mem0) | RAG (Compass) |
|--------|-----------------|----------------|---------------|
| **Purpose** | Temp session data | Agent learning | Document retrieval |
| **Retention** | Hours (TTL) | **Permanent** | Project lifetime |
| **Content Type** | Conversations, drafts | Preferences, patterns | Documents, KB |
| **Search Type** | Key-based | Semantic | Semantic |
| **Use When** | "Remember this session" | "Learn about user" | "Find in documents" |
| **Example Query** | Get last 10 messages | "What does user prefer?" | "Find Q4 earnings" |

---

## Common Misconceptions

### ❌ "Mem0 is for short-term memory"

**Wrong.** Mem0 is for **long-term persistent memory**. It's where agents store what they "learn" that should persist across sessions.

### ❌ "Compass can replace Mem0"

**Partially true, but not ideal.** Compass is designed for documents, not agent memories. You *could* store memories as documents, but you'd lose:
- Automatic consolidation
- Importance scoring
- Memory-specific operations (add/update/delete memories)
- User/session scoping patterns

### ❌ "I need pgvector for agent memory"

**Not necessarily.** Mem0 provides this functionality. If you don't have Mem0, you could build a custom solution on:
- Compass (treating memories as documents)
- Redis with vector search
- pgvector (if you prefer PostgreSQL)

---

## When to Use What

### Use Session Memory (Redis) when:
- Storing current conversation history
- Need fast read/write with automatic expiration
- Data should NOT persist beyond the session
- Building undo/redo functionality

### Use Agentic Memory (Mem0) when:
- Agent should "remember" user preferences
- Building personalized experiences
- Need cross-session knowledge
- Want automatic memory consolidation

### Use RAG Memory (Compass) when:
- Searching documents or knowledge bases
- Need citation tracking
- Building Q&A over documents
- Enterprise document retrieval

---

## Hybrid Architecture Example

For sophisticated applications, use all three:

```python
from agentorchestrator.squad.storage.redis import RedisChatStorage
from agentorchestrator.services import Mem0Memory, VectorStoreService

# Layer 1: Session Memory (24-hour retention)
session = RedisChatStorage(ttl_seconds=86400)

# Layer 2: Agentic Memory (permanent)
agent_memory = Mem0Memory(client=mem0_client, user_id="user123")

# Layer 3: RAG Memory (document search)
documents = VectorStoreService(provider="cohere_compass", index_name="kb")

# Example workflow:
# 1. Check session for recent context
recent = await session.fetch_chat(user_id, session_id, agent_id)

# 2. Check agent memory for user preferences
preferences = await agent_memory.search("user preferences")

# 3. Search documents for relevant content
references = await documents.search("Q4 earnings", top_k=5)

# 4. Combine all context for the LLM
context = {
    "recent_conversation": recent,
    "user_preferences": preferences,
    "relevant_documents": references,
}
```

---

## FAQ

### Q: Can I use Compass instead of Mem0?

**A:** Technically yes, but it's not recommended. Compass is optimized for document retrieval, not agent memory. If you don't have access to Mem0, consider:
1. Using Compass with memory-specific metadata
2. Building a custom memory layer on Redis
3. Using the `MemoryLifecycleMiddleware` to manage memory promotion

### Q: What if I only have Compass?

**A:** You can use Compass for basic memory storage by treating memories as documents:

```python
# Store "memories" as documents in Compass
await compass.add_documents([
    VectorDocument(
        id=f"memory_{uuid4()}",
        text="User prefers technical explanations",
        metadata={
            "type": "memory",
            "user_id": "user123",
            "created_at": datetime.now().isoformat(),
        }
    )
])

# Search memories
results = await compass.search(
    "user preferences",
    filter={"type": "memory", "user_id": "user123"},
)
```

### Q: How do I migrate from pgvector to this architecture?

**A:**
1. **For documents**: Move to Compass (better enterprise support)
2. **For agent memories**: Move to Mem0 (purpose-built for this)
3. **For session data**: Use Redis with TTL

### Q: What's the cost comparison?

| System | Hosting | Best For |
|--------|---------|----------|
| Redis | Self-host or managed | Session data, fast access |
| Mem0 | Managed service | Agent memory, learning |
| Compass | Cohere managed | Enterprise RAG |

---

## See Also

- [Hybrid Memory Example](../examples/hybrid_memory_pitchbook.py)
- [Memory Lifecycle Middleware](../middleware/memory_lifecycle.py)
- [Context Management](CONTEXT_MANAGEMENT.md)
