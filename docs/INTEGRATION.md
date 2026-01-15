# Integration Guide: Mem0 + AgentOrchestrator

How to integrate the Mem0 service with your existing AgentOrchestrator workflows.

## Overview

The Mem0 provides persistent, semantic memory for your agents, allowing them to:
- Remember past interactions across sessions
- Retrieve relevant context based on semantic similarity
- Maintain agent-specific memory spaces
- Share memories across agent instances (same agent_id)

## Architecture Integration

```
┌───────────────────────────────────────────────────────────┐
│           AgentOrchestrator Workflow                       │
│                                                            │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐           │
│  │ Agent A  │───▶│ Agent B  │───▶│ Agent C  │           │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘           │
│       │               │               │                   │
│       │ Memory ops    │               │                   │
│       ▼               ▼               ▼                   │
│  ┌──────────────────────────────────────────┐            │
│  │      Mem0 Client                 │            │
│  └────────────────┬─────────────────────────┘            │
└───────────────────┼──────────────────────────────────────┘
                    │
                    │ HTTP/REST
                    ▼
        ┌────────────────────────┐
        │  Mem0 Service  │
        │  (Mem0 + Cohere + Qdrant)│
        └────────────────────────┘
```

## Installation

### Step 1: Deploy Mem0

Follow the [QUICKSTART.md](QUICKSTART.md) to deploy Mem0:

```bash
cd memory_store
docker-compose up -d
```

Verify it's running:
```bash
curl http://localhost:8000/health
```

### Step 2: Add Mem0 Client to Your Agent

Create a client class in your agent code:

```python
# In your agentorchestrator project
# File: agentorchestrator/clients/memory_store.py

import httpx
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MemoryStoreClient:
    """Client for Mem0 service integration."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        agent_id: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def add_memory(
        self,
        messages: str | list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Add a memory for the agent."""
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("agent_id is required")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/memories",
                json={
                    "agent_id": agent_id,
                    "messages": messages,
                    "metadata": metadata or {},
                },
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            raise
    
    async def search_memories(
        self,
        query: str,
        limit: int = 5,
        metadata: dict[str, Any] | None = None,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search memories for the agent."""
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("agent_id is required")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/memories/search",
                json={
                    "agent_id": agent_id,
                    "query": query,
                    "limit": limit,
                    "metadata": metadata,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("memories", [])
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
```

## Usage Patterns

### Pattern 1: Memory-Augmented Agent

Add memory retrieval and storage to an existing agent:

```python
from agentorchestrator import Agent
from agentorchestrator.clients.memory_store import MemoryStoreClient


class MemoryAwareAgent(Agent):
    """Agent with persistent memory capabilities."""
    
    def __init__(
        self,
        agent_id: str,
        memory_store_url: str = "http://localhost:8000",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self.memory = MemoryStoreClient(
            base_url=memory_store_url,
            agent_id=agent_id,
        )
    
    async def execute(self, context):
        """Execute with memory augmentation."""
        # 1. Retrieve relevant memories
        relevant_memories = await self.memory.search_memories(
            query=context.user_query,
            limit=5,
        )
        
        # 2. Add memories to context
        if relevant_memories:
            context.retrieved_memories = relevant_memories
            context.memory_summary = self._summarize_memories(relevant_memories)
        
        # 3. Execute agent logic
        result = await self._process_with_memory(context)
        
        # 4. Store new memory
        await self.memory.add_memory(
            messages=f"Query: {context.user_query}\nResult: {result}",
            metadata={
                "timestamp": context.timestamp,
                "success": True,
            },
        )
        
        return result
    
    def _summarize_memories(self, memories: list) -> str:
        """Create a summary of memories for context."""
        if not memories:
            return ""
        
        summary_parts = ["Relevant past context:"]
        for mem in memories[:3]:  # Top 3 memories
            summary_parts.append(f"- {mem.get('memory', '')}")
        
        return "\n".join(summary_parts)
    
    async def _process_with_memory(self, context):
        """Process request with memory context."""
        # Your agent logic here
        # Can access context.memory_summary
        pass
```

### Pattern 2: Chain with Memory

Integrate memory into a chain workflow:

```python
from agentorchestrator import ChainForge

# Define agents with memory
context_agent = MemoryAwareAgent(
    agent_id="context_builder",
    memory_store_url="http://mem0-service:8000",
)

analysis_agent = MemoryAwareAgent(
    agent_id="analyzer",
    memory_store_url="http://mem0-service:8000",
)

# Build chain
forge = ChainForge()
forge.step("retrieve_context", context_agent)
forge.step("analyze", analysis_agent, after=["retrieve_context"])

# Execute chain
result = await forge.execute(user_query="What's our revenue trend?")
```

### Pattern 3: Shared Team Memory

Multiple agents sharing a common memory space:

```python
class TeamAgent(Agent):
    """Agent that shares memory with team members."""
    
    def __init__(self, agent_id: str, team_id: str, **kwargs):
        super().__init__(**kwargs)
        self.agent_id = agent_id
        
        # Personal memory
        self.personal_memory = MemoryStoreClient(
            agent_id=agent_id,
            base_url="http://mem0-service:8000",
        )
        
        # Team shared memory
        self.team_memory = MemoryStoreClient(
            agent_id=f"team_{team_id}",
            base_url="http://mem0-service:8000",
        )
    
    async def execute(self, context):
        # Check both personal and team memories
        personal_memories = await self.personal_memory.search_memories(
            query=context.user_query
        )
        team_memories = await self.team_memory.search_memories(
            query=context.user_query
        )
        
        # Process with combined context
        result = await self._process(context, personal_memories, team_memories)
        
        # Store in personal memory
        await self.personal_memory.add_memory(result)
        
        # Optionally store important findings in team memory
        if self._is_important(result):
            await self.team_memory.add_memory(
                result,
                metadata={"shared_by": self.agent_id},
            )
        
        return result
```

### Pattern 4: Context Store Integration

Integrate with existing context store:

```python
from agentorchestrator.core.context import Context
from agentorchestrator.clients.memory_store import MemoryStoreClient


async def enrich_context_with_memories(
    context: Context,
    agent_id: str,
    memory_client: MemoryStoreClient,
) -> Context:
    """Enrich context with relevant memories."""
    
    # Build search query from context
    search_query = context.get("user_query", "")
    
    # Retrieve relevant memories
    memories = await memory_client.search_memories(
        query=search_query,
        limit=5,
        agent_id=agent_id,
    )
    
    # Add to context
    context.set("retrieved_memories", memories)
    context.set("memory_count", len(memories))
    
    return context


# Usage in your workflow
context = Context(user_query="Tell me about AAPL earnings")
memory_client = MemoryStoreClient(agent_id="finance_agent")

# Enrich before processing
context = await enrich_context_with_memories(
    context,
    agent_id="finance_agent",
    memory_client=memory_client,
)

# Now context has memories
print(context.get("retrieved_memories"))
```

## Configuration

### Environment Variables

Add to your AgentOrchestrator `.env`:

```bash
# Mem0 Configuration
MEMORY_STORE_URL=http://localhost:8000
MEMORY_STORE_TIMEOUT=30.0
MEMORY_STORE_ENABLED=true

# Agent-specific memory IDs (optional)
AGENT_CONTEXT_BUILDER_ID=context_builder_v1
AGENT_ANALYZER_ID=analyzer_v1
```

### Config Integration

Add to your `agentorchestrator/config.py`:

```python
@dataclass
class MemoryStoreConfig:
    """Mem0 configuration."""
    
    url: str = "http://localhost:8000"
    timeout: float = 30.0
    enabled: bool = True
    
    @classmethod
    def from_env(cls) -> "MemoryStoreConfig":
        return cls(
            url=_get_env("MEMORY_STORE_URL", "http://localhost:8000"),
            timeout=_get_env_float("MEMORY_STORE_TIMEOUT", 30.0),
            enabled=_get_env_bool("MEMORY_STORE_ENABLED", True),
        )


# Add to main Config class
@dataclass
class Config:
    # ... existing fields ...
    memory_store: MemoryStoreConfig = field(default_factory=MemoryStoreConfig)
```

## Kubernetes Deployment Integration

### Option 1: Same Namespace

Deploy Mem0 in the same namespace as AgentOrchestrator:

```bash
# Deploy to agentorchestrator namespace
kubectl apply -k memory_store/k8s/ -n agentorchestrator

# Agents can access via service name
# URL: http://mem0-service:8000
```

### Option 2: Separate Namespace

Deploy in separate namespace with cross-namespace access:

```bash
# Deploy Mem0
kubectl apply -k memory_store/k8s/

# Access from agents using FQDN
# URL: http://mem0-service.mem0.svc.cluster.local:8000
```

### Option 3: External Service

For cloud-hosted Mem0:

```bash
# Set in AgentOrchestrator deployment
env:
  - name: MEMORY_STORE_URL
    value: "https://mem0.yourdomain.com"
```

## Best Practices

### 1. Memory Lifecycle Management

```python
class MemoryManagedAgent(Agent):
    """Agent with explicit memory lifecycle."""
    
    async def setup(self):
        """Initialize memory client."""
        self.memory = MemoryStoreClient(agent_id=self.agent_id)
    
    async def teardown(self):
        """Clean up memory client."""
        await self.memory.close()
```

### 2. Error Handling

```python
async def safe_memory_operation(self, operation, *args, **kwargs):
    """Execute memory operation with fallback."""
    try:
        return await operation(*args, **kwargs)
    except Exception as e:
        logger.warning(f"Memory operation failed: {e}")
        # Continue without memory - don't fail the agent
        return None
```

### 3. Performance Optimization

```python
# Cache frequently accessed memories
from functools import lru_cache
from datetime import datetime, timedelta

class CachedMemoryClient(MemoryStoreClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}
        self._cache_ttl = timedelta(minutes=5)
    
    async def search_memories(self, query: str, **kwargs):
        cache_key = f"{query}:{kwargs.get('limit', 5)}"
        
        if cache_key in self._cache:
            cached, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < self._cache_ttl:
                return cached
        
        memories = await super().search_memories(query, **kwargs)
        self._cache[cache_key] = (memories, datetime.now())
        return memories
```

### 4. Monitoring

```python
import time
from agentorchestrator.middleware import Middleware

class MemoryMetricsMiddleware(Middleware):
    """Track memory operations."""
    
    async def before(self, context):
        context.memory_start_time = time.time()
    
    async def after(self, context, result):
        if hasattr(context, 'memory_start_time'):
            duration = time.time() - context.memory_start_time
            logger.info(f"Memory operations took {duration:.2f}s")
            
            # Emit metrics
            if hasattr(context, 'retrieved_memories'):
                logger.info(f"Retrieved {len(context.retrieved_memories)} memories")
```

## Testing

### Unit Tests with Mock Mem0

```python
import pytest
from unittest.mock import AsyncMock, Mock


@pytest.fixture
def mock_memory_client(mocker):
    """Mock memory store client."""
    client = Mock(spec=MemoryStoreClient)
    client.search_memories = AsyncMock(return_value=[
        {"memory": "Test memory 1", "score": 0.9},
        {"memory": "Test memory 2", "score": 0.8},
    ])
    client.add_memory = AsyncMock(return_value={"id": "mem_123"})
    return client


async def test_memory_aware_agent(mock_memory_client):
    """Test agent with mocked memory."""
    agent = MemoryAwareAgent(agent_id="test_agent")
    agent.memory = mock_memory_client
    
    context = Context(user_query="test query")
    result = await agent.execute(context)
    
    assert mock_memory_client.search_memories.called
    assert mock_memory_client.add_memory.called
```

### Integration Tests

```python
@pytest.mark.integration
async def test_memory_store_integration():
    """Test real Mem0 integration."""
    client = MemoryStoreClient(
        base_url="http://localhost:8000",
        agent_id="test_agent_integration",
    )
    
    # Add memory
    result = await client.add_memory(
        "Test memory for integration",
        metadata={"test": True},
    )
    assert result["success"]
    
    # Search
    memories = await client.search_memories("integration test")
    assert len(memories) > 0
    
    await client.close()
```

## Troubleshooting

### Connection Issues

```python
# Add retry logic
from tenacity import retry, stop_after_attempt, wait_exponential

class ResilientMemoryClient(MemoryStoreClient):
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def search_memories(self, *args, **kwargs):
        return await super().search_memories(*args, **kwargs)
```

### Debug Logging

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
export MEMORY_STORE_DEBUG=true
```

## Next Steps

1. **Performance Tuning**: Adjust memory search limits based on your use case
2. **Memory Pruning**: Implement strategies to manage memory growth
3. **Advanced Features**: Explore memory categorization and filtering
4. **Monitoring**: Set up dashboards for memory usage patterns
5. **Security**: Add authentication for production deployments

## Support

- Mem0 API: http://localhost:8000/docs
- AgentOrchestrator docs: See main README
- Issues: Open GitHub issues with both projects tagged
