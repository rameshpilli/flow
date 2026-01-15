# Memory Store Service

A production-ready, Kubernetes-native memory management service built on [mem0](https://mem0.ai/) with Cohere Compass vector store. Designed for multi-agent systems where each agent maintains isolated memory spaces.

## Features

- **Multi-Agent Memory Isolation**: Each agent gets its own namespace with complete isolation
- **Semantic Search**: Powered by Cohere's embed-v3 embeddings for intelligent memory retrieval
- **Qdrant Vector Store**: High-performance vector database for scalable memory storage
- **LLM Gateway Integration**: Connects to your existing LLM infrastructure
- **Kubernetes-Ready**: Production-grade deployment configurations with health checks, autoscaling, and monitoring
- **RESTful API**: Clean, documented API for memory operations
- **Docker Support**: Both standalone and compose configurations

## Architecture

```
┌─────────────────┐
│   Agent 1       │
│   (agent_id_1)  │
└────────┬────────┘
         │
         ├─────────────┐
         │             │
┌────────▼─────────────▼────────┐
│   Memory Store API Service    │
│   (FastAPI + mem0)            │
└────────┬──────────────────────┘
         │
         ├──────────┬──────────┐
         │          │          │
    ┌────▼───┐  ┌──▼───┐  ┌──▼───────┐
    │ Cohere │  │Qdrant│  │   LLM    │
    │Embedder│  │Vector│  │ Gateway  │
    │        │  │ DB   │  │(Optional)│
    └────────┘  └──────┘  └──────────┘
```

## Important: Qdrant is Included!

**You don't need to deploy Qdrant separately.** When you deploy Memory Store, Qdrant is automatically included:

- ✅ Docker Compose: Qdrant starts automatically (see `docker-compose.yml`)
- ✅ Kubernetes: Qdrant deploys in the same namespace (see `k8s/qdrant-deployment.yaml`)

Your agents only connect to the Memory Store API. The service handles all communication with Qdrant internally.

## 📚 Documentation

| Document | Description |
|----------|-------------|
| **[docs/QUICKSTART.md](docs/QUICKSTART.md)** | Get started in 5 minutes |
| **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** | How to connect from your agents |
| **[docs/INTEGRATION.md](docs/INTEGRATION.md)** | AgentOrchestrator integration guide |
| **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** | Complete deployment guide |
| **[docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md)** | Pod/container layout explained |
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | Architecture and design details |
| **[docs/GRAPHRAG_GUIDE.md](docs/GRAPHRAG_GUIDE.md)** | GraphRAG setup (optional) |
| **[docs/FEATURES.md](docs/FEATURES.md)** | Complete feature list |
| **[docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md)** | Technical overview |
| **[examples/](examples/)** | Code examples |

## Quick Start

### Local Development with Docker Compose

1. **Copy environment variables**:
   ```bash
   cp env.example .env
   ```

2. **Edit `.env` and set required values**:
   ```bash
   COHERE_API_KEY=your_cohere_api_key_here
   ```

3. **Start the services**:
   ```bash
   docker-compose -f deployments/docker-compose.yml up -d
   ```

4. **Access the API**:
   - API: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - Health: http://localhost:8000/health
   - Qdrant UI: http://localhost:6333/dashboard

### Local Development without Docker

1. **Install dependencies**:
   ```bash
   pip install -e .
   ```

2. **Start Qdrant** (in a separate terminal):
   ```bash
   docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest
   ```

3. **Set environment variables**:
   ```bash
   export COHERE_API_KEY=your_key
   export QDRANT_URL=http://localhost:6333
   ```

4. **Run the service**:
   ```bash
   memory-store
   # or for development with auto-reload:
   memory-store --reload --log-level DEBUG
   ```

## API Usage

### Add a Memory

```bash
curl -X POST http://localhost:8000/memories \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_001",
    "messages": "The user prefers dark mode and likes Python programming.",
    "metadata": {
      "category": "preferences",
      "timestamp": "2026-01-14T10:00:00Z"
    }
  }'
```

### Search Memories

```bash
curl -X POST http://localhost:8000/memories/search \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_001",
    "query": "What programming language does the user like?",
    "limit": 5
  }'
```

### Get All Memories for an Agent

```bash
curl -X POST http://localhost:8000/memories/search \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_001",
    "limit": 10
  }'
```

### Update a Memory

```bash
curl -X PUT http://localhost:8000/memories \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_001",
    "memory_id": "mem_xyz",
    "data": "The user prefers dark mode and loves Python and Go programming."
  }'
```

### Delete a Memory

```bash
curl -X DELETE http://localhost:8000/memories \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_001",
    "memory_id": "mem_xyz"
  }'
```

### Delete All Memories for an Agent

```bash
curl -X DELETE http://localhost:8000/memories/all \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_001"
  }'
```

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (1.24+)
- kubectl configured
- Cohere API key
- (Optional) Cert-manager for TLS
- (Optional) NGINX Ingress Controller or AWS ALB

### Quick Deploy

1. **Create namespace**:
   ```bash
   kubectl apply -f k8s/namespace.yaml
   ```

2. **Create secrets**:
   ```bash
   kubectl create secret generic memory-store-secrets \
     --namespace=memory-store \
     --from-literal=COHERE_API_KEY='your_cohere_api_key' \
     --from-literal=LLM_CLIENT_SECRET='your_llm_secret'
   ```

3. **Deploy with Kustomize**:
   ```bash
   # Edit k8s/kustomization.yaml to set your image registry
   kubectl apply -k k8s/
   ```

   Or manually:
   ```bash
   kubectl apply -f k8s/configmap.yaml
   kubectl apply -f k8s/qdrant-deployment.yaml
   kubectl apply -f k8s/deployment.yaml
   kubectl apply -f k8s/ingress.yaml  # if using ingress
   ```

4. **Verify deployment**:
   ```bash
   kubectl get pods -n memory-store
   kubectl logs -n memory-store -l app=memory-store
   ```

5. **Port-forward to test** (optional):
   ```bash
   kubectl port-forward -n memory-store svc/memory-store-service 8000:8000
   ```

### Production Considerations

#### Scaling

The deployment includes a HorizontalPodAutoscaler (HPA) that scales between 3-10 replicas based on CPU and memory usage:

```bash
kubectl get hpa -n memory-store
```

#### Monitoring

Add Prometheus monitoring:

```yaml
# In deployment.yaml, add annotations:
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
```

#### Persistence

Qdrant uses a PersistentVolumeClaim. Configure storage class:

```yaml
# In k8s/qdrant-deployment.yaml
spec:
  storageClassName: fast-ssd  # your storage class
  resources:
    requests:
      storage: 100Gi  # adjust as needed
```

#### High Availability

For production:
- Run multiple Qdrant replicas (requires Qdrant clustering)
- Use external managed vector store (e.g., Qdrant Cloud)
- Deploy across multiple availability zones
- Configure pod disruption budgets

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COHERE_API_KEY` | Yes | - | Cohere API key for embeddings |
| `QDRANT_URL` | Yes | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_COLLECTION_NAME` | No | `memory_store` | Collection name |
| `QDRANT_VECTOR_SIZE` | No | `1024` | Vector dimension (Cohere v3) |
| `LLM_SERVER_URL` | No | - | Your LLM Gateway endpoint |
| `LLM_OAUTH_ENDPOINT` | No | - | OAuth token endpoint |
| `LLM_CLIENT_ID` | No | - | OAuth client ID |
| `LLM_CLIENT_SECRET` | No | - | OAuth client secret |
| `SERVICE_HOST` | No | `0.0.0.0` | Service bind host |
| `SERVICE_PORT` | No | `8000` | Service port |
| `SERVICE_WORKERS` | No | `4` | Number of workers |
| `SERVICE_LOG_LEVEL` | No | `INFO` | Log level |

See `env.example` for complete configuration options.

## Integration with Your Agents

### Python Client

The client is included in the package (`memory_store/client.py`):

```python
from memory_store.client import MemoryStoreClient

# Initialize
memory = MemoryStoreClient(
    base_url="http://memory-store-service:8000",
    agent_id="finance_agent"
)

# Add memory
await memory.add_memory(
    "User asked about Q4 earnings for AAPL",
    metadata={"topic": "finance", "ticker": "AAPL"}
)

# Search memory
results = await memory.search_memories("What did user ask about Apple?")

# Close when done
await memory.close()
```

### Connection URLs

| Environment | URL |
|-------------|-----|
| **Local (Docker Compose)** | `http://localhost:8000` |
| **K8s (same namespace)** | `http://memory-store-service:8000` |
| **K8s (different namespace)** | `http://memory-store-service.memory-store.svc.cluster.local:8000` |
| **Production (Ingress)** | `https://memory-store.yourdomain.com` |

**See [USER_GUIDE.md](USER_GUIDE.md)** for complete connection details and troubleshooting.

### Integration with AgentOrchestrator

```python
from memory_store import MemoryStoreClient
from agentorchestrator import Agent, ChainForge

class MemoryAwareAgent(Agent):
    def __init__(self, agent_id: str, memory_store_url: str):
        super().__init__()
        self.agent_id = agent_id
        self.memory = MemoryStoreClient(memory_store_url, agent_id)
    
    async def execute(self, context):
        # Retrieve relevant memories
        memories = await self.memory.search_memories(
            query=context.user_query,
            limit=5
        )
        
        # Add memories to context
        context.memories = memories
        
        # Process with memories
        result = await self.process_with_memory(context)
        
        # Store new memory
        await self.memory.add_memory(
            f"User query: {context.user_query}. Result: {result}"
        )
        
        return result
```

See **[docs/INTEGRATION.md](docs/INTEGRATION.md)** for more integration patterns and examples.

## Development

### Running Tests

```bash
pytest tests/
```

### Code Quality

```bash
# Format code
ruff format .

# Lint
ruff check .
```

### Building Docker Image

```bash
docker build -t your-registry/memory-store:latest .
docker push your-registry/memory-store:latest
```

## Troubleshooting

### Qdrant Connection Issues

```bash
# Check Qdrant is running
curl http://localhost:6333/healthz

# Check collections
curl http://localhost:6333/collections
```

### Memory Service Not Starting

```bash
# Check logs
docker-compose logs memory-store

# Or in Kubernetes
kubectl logs -n memory-store -l app=memory-store --tail=100
```

### Configuration Validation

```bash
# Test configuration
python -c "from memory_store.config import get_config; print(get_config().to_dict())"
```

## Architecture Decisions

### Why Cohere Compass?

- State-of-the-art embedding quality
- 1024-dimension vectors balance performance and accuracy
- Built-in reranking capabilities
- Production-ready at scale

### Why Qdrant?

- High-performance vector search
- Native Kubernetes support
- Excellent filtering capabilities
- Active development and community

### Why mem0?

- Purpose-built for AI agent memory
- Automatic memory updates and deduplication
- Version history tracking
- Growing ecosystem

## Optional: GraphRAG with Memgraph

Enable relationship-based memory for advanced use cases:

```bash
# Enable in .env
MEM0_GRAPH_STORE_ENABLED=true

# Start with Memgraph
docker-compose -f deployments/docker-compose.yml --profile graph up -d
```

**Benefits:**
- 🔗 Understand entity relationships
- 🧠 Multi-hop reasoning across memories
- 📊 Knowledge graph visualization
- 🔍 Complex pattern matching

See **[docs/GRAPHRAG_GUIDE.md](docs/GRAPHRAG_GUIDE.md)** for complete setup and use cases.

## Roadmap

- [x] GraphRAG support with Memgraph integration
- [ ] Memory analytics dashboard
- [ ] Memory pruning and archival strategies
- [ ] Multi-modal memory support (images, audio)
- [ ] Memory sharing between agents (with permissions)
- [ ] Advanced memory consolidation and summarization

## License

MIT

## Support

For issues and questions:
- Check the [API documentation](http://localhost:8000/docs)
- Review Kubernetes logs: `kubectl logs -n memory-store -l app=memory-store`
- Open an issue in the repository

## Related Projects

- [AgentOrchestrator](../agentorchestrator) - The orchestration framework this integrates with
- [mem0](https://mem0.ai/) - Memory layer for AI agents
- [Cohere](https://cohere.com/) - Embedding and reranking provider
- [Qdrant](https://qdrant.tech/) - Vector database
