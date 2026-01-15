# Memory Store - User Connection Guide

Complete guide for connecting to the Memory Store service from your agents and applications.

## Table of Contents

- [Understanding the Deployment](#understanding-the-deployment)
- [Connection URLs by Environment](#connection-urls-by-environment)
- [Using the Python Client](#using-the-python-client)
- [Connection Examples](#connection-examples)
- [Troubleshooting Connections](#troubleshooting-connections)
- [Best Practices](#best-practices)

## Understanding the Deployment

### What Gets Deployed Together

When you deploy Memory Store, **Qdrant is automatically included**:

```
┌─────────────────────────────────────────────┐
│         Memory Store Stack                  │
│                                             │
│  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Memory Store   │  │     Qdrant      │ │
│  │    Service      │──│  Vector Store   │ │
│  │  (Port 8000)    │  │  (Port 6333)    │ │
│  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────┘
```

**You don't need to deploy Qdrant separately!** It's included in:
- ✅ Docker Compose (`docker-compose.yml`)
- ✅ Kubernetes deployment (`k8s/qdrant-deployment.yaml`)

### Architecture

```
Your Agent Code
       ↓
   (HTTP REST API)
       ↓
Memory Store Service (Port 8000)
       ↓
   (Internal Connection)
       ↓
Qdrant Vector Store (Port 6333)
```

**Key Point**: Your agents only connect to the Memory Store service. The Memory Store service handles all communication with Qdrant internally.

## Connection URLs by Environment

### 1. Local Development (Docker Compose)

```python
# Memory Store Service
base_url = "http://localhost:8000"

# Qdrant (if you need direct access)
qdrant_url = "http://localhost:6333"
```

**Setup:**
```bash
cd memory_store
docker-compose up -d
```

**Access:**
- Memory Store API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- Qdrant Dashboard: http://localhost:6333/dashboard

### 2. Kubernetes (Same Namespace)

If your agents run in the **same namespace** as Memory Store:

```python
# Service name resolution
base_url = "http://memory-store-service:8000"
```

**How it works:**
```bash
# Deploy Memory Store to same namespace as your agents
kubectl apply -k memory_store/k8s/ -n your-agent-namespace

# Your agents automatically resolve the service name
# No need for full DNS!
```

### 3. Kubernetes (Different Namespace)

If your agents run in a **different namespace**:

```python
# Full DNS name (FQDN)
base_url = "http://memory-store-service.memory-store.svc.cluster.local:8000"
```

**Format:**
```
http://<service-name>.<namespace>.svc.cluster.local:<port>
```

**Setup:**
```bash
# Deploy Memory Store to its own namespace
kubectl apply -k memory_store/k8s/

# Access from any namespace using FQDN
```

### 4. Kubernetes (External/Ingress)

If you configured Ingress:

```python
# Your domain
base_url = "https://memory-store.yourdomain.com"
```

**Setup:**
```bash
# Edit k8s/ingress.yaml with your domain
# Then apply
kubectl apply -f memory_store/k8s/ingress.yaml
```

### 5. Cloud Services / Production

```python
# Load balancer or public endpoint
base_url = "https://memory-store.yourcompany.com"

# Or AWS ALB
base_url = "https://memory-store-12345.us-east-1.elb.amazonaws.com"
```

## Using the Python Client

### Installation

The client is included in the memory_store package:

```bash
# Install from the package
pip install -e /path/to/memory_store

# Or copy the client file to your project
cp memory_store/client.py your_project/memory_client.py
```

### Basic Usage

```python
from memory_store.client import MemoryStoreClient

# Initialize client
memory = MemoryStoreClient(
    base_url="http://memory-store-service:8000",
    agent_id="my_agent"
)

# Add a memory
result = await memory.add_memory(
    "User prefers dark mode and likes Python programming",
    metadata={"category": "preferences", "timestamp": "2026-01-14"}
)

# Search memories
memories = await memory.search_memories(
    query="What programming language does user like?",
    limit=5
)

# Print results
for mem in memories:
    print(f"Memory: {mem.get('memory')}")
    print(f"Score: {mem.get('score')}")
```

### Context Manager Usage

```python
from memory_store.client import MemoryStoreClient

# Automatically closes connection
async with MemoryStoreClient(
    base_url="http://memory-store-service:8000",
    agent_id="my_agent"
) as memory:
    await memory.add_memory("Important information")
    results = await memory.search_memories("important")
```

### Using from Environment Variables

```python
import os
from memory_store.client import create_memory_client

# Read from environment
memory = create_memory_client(
    base_url=os.getenv("MEMORY_STORE_URL", "http://localhost:8000"),
    agent_id=os.getenv("AGENT_ID", "default_agent")
)
```

## Connection Examples

### Example 1: Simple Agent with Memory

```python
from memory_store.client import MemoryStoreClient

class SimpleAgent:
    def __init__(self, agent_id: str, memory_url: str):
        self.agent_id = agent_id
        self.memory = MemoryStoreClient(
            base_url=memory_url,
            agent_id=agent_id
        )
    
    async def process_query(self, query: str):
        # Search for relevant memories
        memories = await self.memory.search_memories(query, limit=5)
        
        # Use memories to inform response
        context = self._build_context(memories)
        
        # Generate response
        response = await self._generate_response(query, context)
        
        # Store new memory
        await self.memory.add_memory(
            f"Q: {query}\nA: {response}",
            metadata={"type": "qa_pair"}
        )
        
        return response

# Usage
agent = SimpleAgent(
    agent_id="finance_agent",
    memory_url="http://memory-store-service:8000"
)

response = await agent.process_query("What's AAPL's revenue?")
```

### Example 2: AgentOrchestrator Integration

```python
from agentorchestrator import Agent
from memory_store.client import MemoryStoreClient

class MemoryAwareAgent(Agent):
    def __init__(self, agent_id: str, memory_url: str, **kwargs):
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self.memory = MemoryStoreClient(
            base_url=memory_url,
            agent_id=agent_id
        )
    
    async def execute(self, context):
        # Enrich context with memories
        memories = await self.memory.search_memories(
            query=context.user_query,
            limit=5
        )
        context.memories = memories
        
        # Process
        result = await self._process(context)
        
        # Store result
        await self.memory.add_memory(
            result,
            metadata={"context_id": context.id}
        )
        
        return result

# Usage in chain
from agentorchestrator import ChainForge

forge = ChainForge()
forge.step(
    "analyzer",
    MemoryAwareAgent(
        agent_id="analyzer_v1",
        memory_url="http://memory-store-service:8000"
    )
)

result = await forge.execute(user_query="Analyze Q4 data")
```

### Example 3: Team Memory (Shared Between Agents)

```python
from memory_store.client import MemoryStoreClient

class TeamAgent:
    def __init__(self, agent_id: str, team_id: str, memory_url: str):
        # Personal memory
        self.personal_memory = MemoryStoreClient(
            base_url=memory_url,
            agent_id=agent_id
        )
        
        # Team shared memory
        self.team_memory = MemoryStoreClient(
            base_url=memory_url,
            agent_id=f"team_{team_id}"
        )
    
    async def process(self, query: str):
        # Search both personal and team memories
        personal_results = await self.personal_memory.search_memories(query)
        team_results = await self.team_memory.search_memories(query)
        
        # Combine results
        all_memories = personal_results + team_results
        
        # Process with combined context
        result = await self._process_with_memories(query, all_memories)
        
        # Store in personal memory
        await self.personal_memory.add_memory(result)
        
        # Optionally share with team
        if self._should_share(result):
            await self.team_memory.add_memory(
                result,
                metadata={"shared_by": self.agent_id}
            )
        
        return result

# Usage
agent1 = TeamAgent(
    agent_id="analyst_1",
    team_id="finance_team",
    memory_url="http://memory-store-service:8000"
)

agent2 = TeamAgent(
    agent_id="analyst_2",
    team_id="finance_team",  # Same team!
    memory_url="http://memory-store-service:8000"
)

# Agent 2 can see what Agent 1 shared with the team
```

### Example 4: Health Check Before Operations

```python
from memory_store.client import MemoryStoreClient

async def safe_memory_operations():
    memory = MemoryStoreClient(
        base_url="http://memory-store-service:8000",
        agent_id="my_agent"
    )
    
    # Check service health first
    try:
        health = await memory.health_check()
        if health.get("status") != "healthy":
            print(f"Warning: Memory Store unhealthy: {health}")
            return None
    except Exception as e:
        print(f"Cannot reach Memory Store: {e}")
        return None
    
    # Proceed with operations
    result = await memory.add_memory("Test memory")
    return result
```

## Troubleshooting Connections

### Problem: Cannot Connect to Service

**Symptoms:**
```
httpx.ConnectError: [Errno 111] Connection refused
```

**Solutions:**

1. **Check service is running:**
   ```bash
   # Docker Compose
   docker-compose ps
   docker-compose logs memory-store
   
   # Kubernetes
   kubectl get pods -n memory-store
   kubectl logs -n memory-store -l app=memory-store
   ```

2. **Verify URL:**
   ```python
   # Test connection
   import httpx
   async with httpx.AsyncClient() as client:
       response = await client.get("http://localhost:8000/health")
       print(response.json())
   ```

3. **Check port forwarding (K8s):**
   ```bash
   kubectl port-forward -n memory-store svc/memory-store-service 8000:8000
   ```

### Problem: Service Healthy but Operations Fail

**Symptoms:**
```
Status 500: Internal Server Error
```

**Solutions:**

1. **Check Cohere API key:**
   ```bash
   # Docker
   docker-compose exec memory-store env | grep COHERE
   
   # Kubernetes
   kubectl get secret memory-store-secrets -n memory-store -o yaml
   ```

2. **Check Qdrant connection:**
   ```bash
   # Docker
   docker-compose exec memory-store curl http://qdrant:6333/healthz
   
   # Kubernetes
   kubectl exec -n memory-store deployment/memory-store -- \
     curl http://qdrant-service:6333/healthz
   ```

3. **View detailed logs:**
   ```bash
   # Docker
   docker-compose logs memory-store --tail=100
   
   # Kubernetes
   kubectl logs -n memory-store -l app=memory-store --tail=100
   ```

### Problem: Timeout Errors

**Symptoms:**
```
httpx.ReadTimeout: timed out
```

**Solutions:**

1. **Increase client timeout:**
   ```python
   memory = MemoryStoreClient(
       base_url="http://memory-store-service:8000",
       agent_id="my_agent",
       timeout=60.0  # Increase from default 30s
   )
   ```

2. **Check resource limits (K8s):**
   ```bash
   kubectl describe pod -n memory-store -l app=memory-store
   # Look for CPU throttling or OOM issues
   ```

### Problem: DNS Resolution Failed (Kubernetes)

**Symptoms:**
```
httpx.ConnectError: [Errno -2] Name or service not known
```

**Solutions:**

1. **Use correct service name:**
   ```python
   # Same namespace
   base_url = "http://memory-store-service:8000"
   
   # Different namespace
   base_url = "http://memory-store-service.memory-store.svc.cluster.local:8000"
   ```

2. **Verify service exists:**
   ```bash
   kubectl get svc -n memory-store
   kubectl describe svc memory-store-service -n memory-store
   ```

3. **Test DNS from pod:**
   ```bash
   kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
     nslookup memory-store-service.memory-store.svc.cluster.local
   ```

## Best Practices

### 1. Connection Management

```python
# ✅ GOOD: Use context manager
async with MemoryStoreClient(...) as memory:
    await memory.add_memory("data")

# ✅ GOOD: Reuse client
class MyAgent:
    def __init__(self):
        self.memory = MemoryStoreClient(...)
    
    async def cleanup(self):
        await self.memory.close()

# ❌ BAD: Create new client for each operation
async def bad_example():
    memory = MemoryStoreClient(...)
    await memory.add_memory("data")
    # Never closed!
```

### 2. Error Handling

```python
# ✅ GOOD: Handle failures gracefully
async def robust_memory_search(memory, query):
    try:
        return await memory.search_memories(query)
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        return []  # Continue without memories

# ❌ BAD: Let memory failures crash the agent
async def fragile_search(memory, query):
    return await memory.search_memories(query)  # Crashes if fails
```

### 3. Configuration

```python
# ✅ GOOD: Use environment variables
import os

MEMORY_STORE_URL = os.getenv(
    "MEMORY_STORE_URL",
    "http://localhost:8000"
)

memory = MemoryStoreClient(
    base_url=MEMORY_STORE_URL,
    agent_id=os.getenv("AGENT_ID")
)

# ❌ BAD: Hardcode URLs
memory = MemoryStoreClient(
    base_url="http://localhost:8000",  # Won't work in production!
    agent_id="hardcoded_agent"
)
```

### 4. Agent ID Management

```python
# ✅ GOOD: Unique, descriptive agent IDs
agent_id = f"{agent_type}_{agent_version}_{instance_id}"
# Example: "finance_analyzer_v1_001"

# ✅ GOOD: Team-based IDs for shared memory
team_memory_id = f"team_{team_name}"
# Example: "team_finance"

# ❌ BAD: Generic IDs
agent_id = "agent1"  # Too generic, will conflict
```

### 5. Metadata Usage

```python
# ✅ GOOD: Rich metadata
await memory.add_memory(
    "User asked about AAPL Q4 earnings",
    metadata={
        "category": "user_query",
        "topic": "finance",
        "ticker": "AAPL",
        "quarter": "Q4",
        "timestamp": "2026-01-14T10:00:00Z",
        "importance": "high"
    }
)

# ❌ BAD: No metadata
await memory.add_memory("User asked about AAPL Q4 earnings")
```

### 6. Memory Limits

```python
# ✅ GOOD: Use reasonable limits
memories = await memory.search_memories(
    query="recent earnings",
    limit=5  # Just top results
)

# ❌ BAD: Request too many
memories = await memory.search_memories(
    query="recent earnings",
    limit=1000  # Slow and unnecessary
)
```

## Environment Variables Reference

Set these in your agent environment:

```bash
# Required
MEMORY_STORE_URL=http://memory-store-service:8000

# Optional
AGENT_ID=my_agent_v1
MEMORY_STORE_TIMEOUT=30.0
MEMORY_STORE_VERIFY_SSL=true

# For local development
MEMORY_STORE_URL=http://localhost:8000

# For Kubernetes (same namespace)
MEMORY_STORE_URL=http://memory-store-service:8000

# For Kubernetes (different namespace)
MEMORY_STORE_URL=http://memory-store-service.memory-store.svc.cluster.local:8000

# For production with ingress
MEMORY_STORE_URL=https://memory-store.yourdomain.com
```

## Next Steps

1. **Test Connection**: Start with a simple health check
2. **Add to One Agent**: Test with a single agent first
3. **Monitor Performance**: Watch response times and error rates
4. **Scale Up**: Roll out to all agents once stable
5. **Optimize**: Tune limits and caching based on usage

## Getting Help

- **API Documentation**: http://localhost:8000/docs (or your service URL)
- **Health Status**: http://localhost:8000/health
- **Service Logs**: `kubectl logs -n memory-store -l app=memory-store`
- **Qdrant Status**: http://localhost:6333/dashboard (local) or check K8s pod

## Summary

**Key Points:**
- ✅ Qdrant is included - no separate deployment needed
- ✅ Connect to Memory Store service only (it handles Qdrant)
- ✅ Use the Python client for easy integration
- ✅ Configure via environment variables
- ✅ Handle connection errors gracefully

**Connection URLs:**
- Local: `http://localhost:8000`
- K8s (same namespace): `http://memory-store-service:8000`
- K8s (different namespace): `http://memory-store-service.memory-store.svc.cluster.local:8000`
- Production: Your configured domain/load balancer

---

**Ready to connect? Use the Python client and you're good to go! 🚀**
