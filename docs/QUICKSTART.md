# Mem0 - Quick Start Guide

Get the Mem0 service running in under 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Cohere API key (get one free at https://cohere.com/)

## Step 1: Get Your Cohere API Key

1. Go to https://cohere.com/
2. Sign up or log in
3. Navigate to API Keys section
4. Copy your API key

## Step 2: Configure Environment

```bash
# Navigate to memory_store directory
cd memory_store

# Copy environment template
cp env.example .env

# Edit .env and set your Cohere API key
# Replace 'your_cohere_api_key_here' with your actual key
nano .env  # or use your preferred editor
```

Required configuration:
```bash
COHERE_API_KEY=your_actual_cohere_api_key_here
```

## Step 3: Start Services

```bash
# Start all services with Docker Compose
docker-compose up -d

# Check services are running
docker-compose ps
```

You should see:
- `mem0-service` - Running on port 8000
- `mem0-qdrant` - Running on port 6333

**Optional: Enable GraphRAG** (relationship-based memory)
```bash
# Start with Memgraph graph store
docker-compose --profile graph up -d

# Or edit docker-compose.yml and remove "profiles: - graph" from memgraph service
```

See [GRAPHRAG_GUIDE.md](GRAPHRAG_GUIDE.md) for details.

## Step 4: Verify Installation

```bash
# Check health
curl http://localhost:8000/health

# Expected output:
# {
#   "service": "memory_store",
#   "status": "healthy",
#   "components": { ... }
# }
```

## Step 5: Test the API

### Open Interactive API Docs

Open your browser to: http://localhost:8000/docs

You'll see the Swagger UI with all available endpoints.

### Or Test with curl

```bash
# Add a memory
curl -X POST http://localhost:8000/memories \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "demo_agent",
    "messages": "The user prefers dark mode and likes Python programming.",
    "metadata": {"category": "preferences"}
  }'

# Search memories
curl -X POST http://localhost:8000/memories/search \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "demo_agent",
    "query": "What does the user like?",
    "limit": 5
  }'
```

## Step 6: Integrate with Your Agents

### Python Example

```python
import httpx
import asyncio

async def demo():
    base_url = "http://localhost:8000"
    agent_id = "my_agent"
    
    async with httpx.AsyncClient() as client:
        # Add memory
        response = await client.post(
            f"{base_url}/memories",
            json={
                "agent_id": agent_id,
                "messages": "User asked about quarterly revenue for AAPL",
                "metadata": {"topic": "finance", "ticker": "AAPL"}
            }
        )
        print("Added memory:", response.json())
        
        # Search memories
        response = await client.post(
            f"{base_url}/memories/search",
            json={
                "agent_id": agent_id,
                "query": "What did the user ask about Apple?",
                "limit": 5
            }
        )
        print("Found memories:", response.json())

# Run demo
asyncio.run(demo())
```

### JavaScript/TypeScript Example

```typescript
const BASE_URL = 'http://localhost:8000';
const AGENT_ID = 'my_agent';

async function addMemory(text: string, metadata: any = {}) {
  const response = await fetch(`${BASE_URL}/memories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      agent_id: AGENT_ID,
      messages: text,
      metadata
    })
  });
  return response.json();
}

async function searchMemories(query: string, limit: number = 5) {
  const response = await fetch(`${BASE_URL}/memories/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      agent_id: AGENT_ID,
      query,
      limit
    })
  });
  return response.json();
}

// Usage
await addMemory('User prefers TypeScript over JavaScript');
const memories = await searchMemories('What language does user prefer?');
console.log(memories);
```

## Common Commands

```bash
# View logs
docker-compose logs -f mem0

# Stop services
docker-compose down

# Restart services
docker-compose restart

# Rebuild after code changes
docker-compose up -d --build

# Remove all data (WARNING: deletes all memories)
docker-compose down -v
```

## Next Steps

### For Development

1. **Run locally without Docker** (for faster iteration):
   ```bash
   pip install -e ".[dev]"
   docker run -d -p 6333:6333 qdrant/qdrant  # Just Qdrant
   mem0 --reload --log-level DEBUG
   ```

2. **Run tests**:
   ```bash
   pytest tests/
   ```

### For Production

1. **Deploy to Kubernetes**: See [DEPLOYMENT.md](DEPLOYMENT.md)
2. **Configure monitoring**: Add Prometheus/Grafana
3. **Set up backups**: Qdrant snapshot automation
4. **Enable SSL/TLS**: Use ingress with cert-manager

## Troubleshooting

### Service won't start

```bash
# Check logs
docker-compose logs mem0

# Common issues:
# 1. Invalid Cohere API key - check .env file
# 2. Port 8000 already in use - change SERVICE_PORT in .env
# 3. Qdrant not ready - wait 30 seconds and check again
```

### Can't connect to Qdrant

```bash
# Check Qdrant is running
curl http://localhost:6333/healthz

# Restart Qdrant
docker-compose restart qdrant
```

### Memory operations failing

```bash
# Check configuration
curl http://localhost:8000/health | jq

# Verify Cohere API key is valid
# Check logs for specific errors
docker-compose logs mem0 | tail -50
```

## Getting Help

- API Documentation: http://localhost:8000/docs
- Full Documentation: [README.md](README.md)
- Deployment Guide: [DEPLOYMENT.md](DEPLOYMENT.md)
- Configuration: Check `env.example` for all options

## What's Next?

You now have a fully functional memory store! Here are some ideas:

1. **Multi-Agent Testing**: Create multiple agents with different IDs
2. **Metadata Filtering**: Add rich metadata to organize memories
3. **Integration**: Connect with your AgentOrchestrator workflows
4. **Production Deploy**: Follow [DEPLOYMENT.md](DEPLOYMENT.md) for Kubernetes

---

**Happy Building! 🚀**
