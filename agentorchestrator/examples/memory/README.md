# Memory Examples

Demonstrates conversation storage and semantic memory capabilities.

## Storage Options

AgentOrchestrator provides multiple storage backends:

| Storage | Use Case | Persistence |
|---------|----------|-------------|
| `InMemoryChatStorage` | Development, testing | Process lifetime |
| `RedisChatStorage` | Production | Persistent |
| `Mem0Memory` | Semantic search | Persistent |

## Examples

### 1. Chat Storage

Basic conversation history with InMemory and Redis backends.

```bash
python chat_storage.py
```

**What you'll learn:**
- Saving and retrieving chat messages
- User/session/agent scoping
- Switching between InMemory and Redis

### 2. Semantic Memory (Mem0)

Semantic search over conversation history.

```bash
python semantic_memory.py
```

**What you'll learn:**
- Storing memories with metadata
- Semantic search across sessions
- Cross-session memory recall

## Prerequisites

### For Redis Storage

```bash
# Start Redis locally
docker run -d -p 6379:6379 redis:latest

# Or set environment variables for remote Redis
export REDIS_HOST=redis.corp.com
export REDIS_PORT=6379
```

### For Mem0 Memory

Requires corporate MemoryStoreClient:

```python
from your_app import MemoryStoreClient

client = MemoryStoreClient(
    base_url="https://mem0.corp.com",
    agent_id="my-agent"
)
```

## Quick Reference

### InMemoryChatStorage

```python
from agentorchestrator.squad.storage import InMemoryChatStorage

storage = InMemoryChatStorage()

# Save message
await storage.save_chat_message(
    user_id="user-123",
    session_id="session-abc",
    agent_id="assistant",
    new_message={"role": "user", "content": "Hello!"}
)

# Fetch history
history = await storage.fetch_chat("user-123", "session-abc", "assistant")
```

### RedisChatStorage

```python
from agentorchestrator.squad.storage.redis import RedisChatStorage

storage = RedisChatStorage(host="localhost", port=6379)

# Same API as InMemoryChatStorage
await storage.save_chat_message(...)
history = await storage.fetch_chat(...)
```

### Mem0Memory

```python
from agentorchestrator.services import Mem0Memory

memory = Mem0Memory(client=mem0_client)

# Store memory
await memory.add("User prefers technical explanations")

# Semantic search
results = await memory.search("What are user preferences?")
```
