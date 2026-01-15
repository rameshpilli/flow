# Memory Store - Architecture Details

Complete architecture documentation explaining how all components work together.

## Overview

The Memory Store is a complete, self-contained service that includes **all required dependencies**. When you deploy Memory Store, you get:

1. ✅ **Memory Store Service** - FastAPI-based REST API
2. ✅ **Qdrant Vector Store** - Automatically deployed alongside
3. ✅ **Cohere Integration** - Embeddings via API key
4. ✅ **LLM Gateway Adapter** - Connects to your existing infrastructure

**Important**: You do NOT need to deploy Qdrant separately. It's included!

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Your Application/Agents                       │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Agent 1  │  │ Agent 2  │  │ Agent 3  │  │ Agent N  │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │             │             │             │              │
│       └─────────────┴─────────────┴─────────────┘              │
└───────────────────────┼──────────────────────────────────────────┘
                        │
                        │ HTTP REST API (Port 8000)
                        │ - POST /memories (add)
                        │ - POST /memories/search
                        │ - PUT /memories (update)
                        │ - DELETE /memories
                        │
┌───────────────────────▼──────────────────────────────────────────┐
│                  Memory Store Service                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              FastAPI Application                        │    │
│  │  - Request validation (Pydantic)                       │    │
│  │  - Authentication/CORS                                  │    │
│  │  - Health checks                                        │    │
│  │  - Error handling                                       │    │
│  └────────────────────┬───────────────────────────────────┘    │
│                       │                                          │
│  ┌────────────────────▼───────────────────────────────────┐    │
│  │                Mem0 Core Layer                         │    │
│  │  - Memory management                                    │    │
│  │  - Deduplication logic                                  │    │
│  │  - Version tracking                                     │    │
│  │  - Agent isolation (via user_id)                       │    │
│  └────┬───────────────────────────────────────────┬───────┘    │
│       │                                            │             │
│       │ Embeddings                                 │ Storage     │
└───────┼────────────────────────────────────────────┼─────────────┘
        │                                            │
        │                                            │
┌───────▼────────────────┐              ┌───────────▼─────────────┐
│   Cohere Compass       │              │    Qdrant Vector DB     │
│                        │              │                         │
│  - Text → Embeddings   │              │  - Vector storage       │
│  - embed-v3.0 model    │◀─────────────│  - Similarity search   │
│  - 1024 dimensions     │  Vectors     │  - Filtering           │
│  - Reranking (optional)│              │  - Persistence         │
└────────────────────────┘              └─────────────────────────┘
         │                                           │
         │ API Key Auth                              │ Direct Connection
         │                                           │
┌────────▼─────────────────────────────────────────────────────────┐
│                    External Services                              │
│                                                                   │
│  ┌──────────────────┐              ┌────────────────────────┐   │
│  │  Cohere Cloud    │              │  LLM Gateway (Optional)│   │
│  │  API Service     │              │  - OAuth               │   │
│  │  (SaaS)          │              │  - Your existing       │   │
│  └──────────────────┘              └────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

## How Qdrant is Deployed

### Docker Compose Deployment

When you run `docker-compose up`, **both services start together**:

```yaml
# From docker-compose.yml
services:
  # Qdrant - starts automatically
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"  # HTTP API
    volumes:
      - qdrant_data:/qdrant/storage
  
  # Memory Store - connects to qdrant above
  memory-store:
    build: .
    ports:
      - "8000:8000"
    environment:
      - QDRANT_URL=http://qdrant:6333  # Internal connection
    depends_on:
      - qdrant  # Waits for Qdrant to be ready
```

**Key Points:**
- ✅ Qdrant is in the same Docker Compose file
- ✅ Memory Store automatically connects to it
- ✅ They communicate via internal Docker network
- ✅ Only Memory Store port (8000) needs to be exposed to your apps

### Kubernetes Deployment

When you run `kubectl apply -k k8s/`, **both are deployed**:

```
memory-store namespace
│
├── Qdrant Deployment (k8s/qdrant-deployment.yaml)
│   ├── Pod: qdrant-xxx
│   │   └── Container: qdrant:latest
│   ├── Service: qdrant-service (ClusterIP)
│   │   └── Port 6333 (internal only)
│   └── PersistentVolumeClaim: qdrant-pvc (10GB)
│
└── Memory Store Deployment (k8s/deployment.yaml)
    ├── Pods: memory-store-xxx (3 replicas)
    │   └── Container: memory-store:latest
    │       └── Env: QDRANT_URL=http://qdrant-service:6333
    ├── Service: memory-store-service (ClusterIP)
    │   └── Port 8000 (exposed to cluster)
    └── HPA: Scales 3-10 replicas
```

**Key Points:**
- ✅ Both deployed to same namespace
- ✅ Qdrant service is ClusterIP (internal only)
- ✅ Memory Store connects via Kubernetes service DNS
- ✅ Only Memory Store service is exposed (via Ingress if configured)

## Data Flow

### 1. Adding a Memory

```
Agent Code
   │
   └─→ POST /memories
       {
         "agent_id": "agent_001",
         "messages": "User likes Python",
         "metadata": {"category": "preferences"}
       }
       │
       ▼
Memory Store API
   │
   ├─→ Validate request (Pydantic)
   │
   └─→ Mem0.add()
       │
       ├─→ Cohere API: Generate embedding
       │   └─→ Returns: [0.123, -0.456, ..., 0.789] (1024 dims)
       │
       └─→ Qdrant: Store vector + metadata
           └─→ Collection: memory_store
               └─→ Point ID: generated_uuid
                   ├─→ Vector: [embedding]
                   ├─→ Payload: {
                   │       "user_id": "agent_001",
                   │       "memory": "User likes Python",
                   │       "metadata": {...}
                   │   }
                   └─→ Stored on disk
       
Response: {"id": "mem_xyz", "status": "success"}
```

### 2. Searching Memories

```
Agent Code
   │
   └─→ POST /memories/search
       {
         "agent_id": "agent_001",
         "query": "What does user like?",
         "limit": 5
       }
       │
       ▼
Memory Store API
   │
   └─→ Mem0.search()
       │
       ├─→ Cohere API: Embed query
       │   └─→ Returns: [0.111, -0.222, ..., 0.333]
       │
       └─→ Qdrant: Vector similarity search
           ├─→ Find nearest vectors (cosine similarity)
           ├─→ Filter by user_id="agent_001"
           └─→ Return top 5 matches with scores
       
       │
       ├─→ Mem0: Rank and deduplicate
       │
       └─→ Response: [
             {
               "memory": "User likes Python",
               "score": 0.89,
               "metadata": {...}
             },
             ...
           ]
```

## Storage Details

### Qdrant Storage

**Location:**
- Docker: `./qdrant_storage/` (bind mount)
- Kubernetes: PersistentVolume (defined in qdrant-deployment.yaml)

**Data Structure:**
```
Collection: memory_store
├── Points (vectors):
│   ├── ID: uuid-1
│   │   ├── Vector: [1024 floats]
│   │   └── Payload:
│   │       ├── user_id: "agent_001"
│   │       ├── memory: "text content"
│   │       ├── metadata: {custom fields}
│   │       └── timestamp: "..."
│   ├── ID: uuid-2
│   └── ...
└── Index: HNSW (for fast similarity search)
```

**Why Qdrant?**
- ✅ Open source (Apache 2.0 license)
- ✅ High performance (Rust-based)
- ✅ Native Kubernetes support
- ✅ Rich filtering capabilities
- ✅ Easy to deploy and manage

### Persistence

**Docker Compose:**
```bash
# Data persisted in Docker volume
docker-compose down  # Service stops
docker-compose up    # Data still there!

# To remove data
docker-compose down -v  # Removes volumes
```

**Kubernetes:**
```bash
# Data persisted in PVC
kubectl delete deployment qdrant  # Pod deleted
# But PVC remains, data safe

# New pod mounts same PVC
# Data automatically available
```

## Scaling Considerations

### Memory Store Service

**Horizontal Scaling:**
```yaml
# Kubernetes HPA (automatic)
replicas: 3-10  # Based on CPU/memory
```

**Vertical Scaling:**
```yaml
# Increase resources per pod
resources:
  limits:
    memory: "4Gi"
    cpu: "2000m"
```

### Qdrant Scaling

**Single Instance (Current Default):**
- ✅ Good for: Development, small-medium deployments
- ✅ Handles: Millions of vectors, thousands of queries/sec
- ⚠️ Limitation: Single point of failure

**Clustered Setup (Production):**
```yaml
# Multiple Qdrant replicas with replication
replicas: 3
replication_factor: 2
```

**Qdrant Cloud (Managed):**
- ✅ Automatic scaling
- ✅ Built-in HA
- ✅ Managed backups
- 💰 Paid service

## Network Communication

### Internal Communication (Service ↔ Qdrant)

**Docker Compose:**
```
memory-store container
   │
   └─→ http://qdrant:6333  (Docker network)
       └─→ qdrant container
```

**Kubernetes:**
```
memory-store pod
   │
   └─→ http://qdrant-service:6333  (K8s service DNS)
       └─→ qdrant pod(s)
```

### External Communication (Agents ↔ Service)

**Docker Compose:**
```
Your agent code
   │
   └─→ http://localhost:8000  (exposed port)
       └─→ memory-store container
```

**Kubernetes (Same Namespace):**
```
Your agent pod
   │
   └─→ http://memory-store-service:8000  (K8s service)
       └─→ memory-store pods
```

**Kubernetes (Different Namespace):**
```
Your agent pod (namespace: agents)
   │
   └─→ http://memory-store-service.memory-store.svc.cluster.local:8000
       └─→ memory-store pods (namespace: memory-store)
```

## Security Architecture

### Network Isolation

```
┌─────────────────────────────────────────┐
│          Public Internet                │
└──────────────┬──────────────────────────┘
               │
        ┌──────▼──────┐
        │   Ingress   │ (HTTPS/TLS)
        └──────┬──────┘
               │
   ┌───────────▼───────────────┐
   │  memory-store-service     │ (ClusterIP)
   └───────────┬───────────────┘
               │
   ┌───────────▼───────────────┐
   │  Memory Store Pods        │
   └───┬───────────────────┬───┘
       │                   │
       │              ┌────▼────────┐
       │              │ Qdrant Pods │ (Not exposed)
       │              └─────────────┘
       │
   ┌───▼──────────────┐
   │  Cohere API      │ (HTTPS)
   │  (Internet)      │
   └──────────────────┘
```

**Key Points:**
- ✅ Qdrant is NOT exposed to internet
- ✅ Only Memory Store service is accessible
- ✅ All internal communication is within cluster
- ✅ External APIs use HTTPS

### Authentication

**Agents → Memory Store:**
- Currently: Network-level (Kubernetes NetworkPolicies)
- Future: API keys, OAuth, mTLS

**Memory Store → Qdrant:**
- Internal network only
- Optional: Qdrant API key (for Qdrant Cloud)

**Memory Store → Cohere:**
- API key authentication
- Stored in Kubernetes Secret

## Monitoring Points

### Health Checks

```
┌──────────────────┐
│  /health         │ Check all components
│                  │
│  ├─ API Server   │ FastAPI healthy?
│  ├─ Qdrant       │ Vector DB responding?
│  ├─ Cohere       │ API configured?
│  └─ LLM Gateway  │ Gateway accessible?
└──────────────────┘
```

### Metrics to Monitor

**Memory Store Service:**
- Request rate (req/sec)
- Response time (p50, p95, p99)
- Error rate (4xx, 5xx)
- Memory usage
- CPU usage

**Qdrant:**
- Vector count
- Storage usage
- Query latency
- Index rebuild status

**Cohere API:**
- API call count
- Rate limit status
- Error rate
- Cost tracking

## Cost Breakdown

### Infrastructure Costs

**Docker Compose (Local):**
- 💰 $0 (runs on your machine)
- CPU: ~2 cores
- RAM: ~4GB
- Storage: ~10GB

**Kubernetes (Self-Hosted):**
- Memory Store: 3 pods × $25/month = $75
- Qdrant: 1 pod × $60/month = $60
- Load Balancer: $20/month
- Storage: $10/month
- **Total: ~$165/month**

### API Costs

**Cohere:**
- Embeddings: ~$0.10 per 1M tokens
- Example: 1000 memories/day ≈ $3/month

**Qdrant Cloud (Alternative):**
- Starts at $25/month (1GB)
- Scales with data volume
- Includes HA and backups

## Design Decisions

### Why This Architecture?

1. **Self-Contained**: Everything in one deployment
2. **Simple**: Minimal external dependencies
3. **Scalable**: Each component scales independently
4. **Reliable**: Persistent storage, health checks
5. **Production-Ready**: Used in real deployments

### Why Not Alternative Designs?

**Alternative 1: External Qdrant**
- ❌ More complex to deploy
- ❌ Network latency
- ❌ Separate management
- ✅ But: Shared across services

**Alternative 2: Embedded Vector Store**
- ✅ Simpler deployment
- ❌ Limited scalability
- ❌ No HA options
- ❌ Performance limitations

**Alternative 3: Managed Services Only**
- ✅ Easiest to manage
- ❌ Higher cost
- ❌ Vendor lock-in
- ❌ Less control

## Future Enhancements

### Planned

- [ ] Multi-region Qdrant replication
- [ ] Built-in authentication/authorization
- [x] GraphRAG with Memgraph (implemented!)
- [ ] Memory analytics dashboard
- [ ] Automatic backup/restore

### Possible

- [ ] Multi-cloud deployment
- [ ] Alternative vector stores (Pinecone, Weaviate)
- [ ] Advanced caching layer
- [ ] Memory consolidation/summarization

## Summary

**Key Takeaways:**

1. **Qdrant is included** - No separate deployment needed
2. **Internal communication** - Qdrant not exposed externally
3. **Simple connection** - Agents connect only to Memory Store API
4. **Scales together** - Both services deployed as a unit
5. **Production-ready** - Persistence, HA, monitoring built-in

**Your agents only need to know:**
```python
from memory_store.client import MemoryStoreClient

memory = MemoryStoreClient(
    base_url="http://memory-store-service:8000",
    agent_id="my_agent"
)
```

Everything else (Qdrant, Cohere, embeddings, storage) is handled internally!

---

**Questions? See [USER_GUIDE.md](USER_GUIDE.md) for connection details.**
