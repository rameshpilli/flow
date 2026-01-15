# Deployment Architecture - Pod/Container Layout

Clear explanation of how services are deployed.

## Important Clarification

### What is mem0?

**mem0 is NOT a separate service** - it's a **Python library** that runs inside the Memory Store application code.

```python
# In memory_store/service.py
from mem0 import Memory  # ← Python library, not a service

memory_client = Memory.from_config(config)  # ← Runs in-process
```

**mem0 is like:**
- A Python library (like `requests`, `pandas`)
- Runs in the same process as your application
- No separate container/pod needed

## Actual Deployment Architecture

### Docker Compose (Local Development)

```
┌────────────────────────────────────────────────────────┐
│              Docker Compose Stack                      │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Container 1: memory-store-service                     │
│  ├─ FastAPI application                               │
│  ├─ mem0 library (Python code)  ← Runs here!         │
│  ├─ Connects to: Qdrant (via network)                │
│  └─ Connects to: Memgraph (via network)              │
│                                                        │
│  Container 2: memory-store-qdrant                      │
│  ├─ Qdrant vector database                            │
│  └─ Port 6333 (internal)                              │
│                                                        │
│  Container 3: memory-store-memgraph (optional)         │
│  ├─ Memgraph graph database                           │
│  └─ Port 7687 (internal)                              │
│                                                        │
└────────────────────────────────────────────────────────┘

Communication:
  memory-store → http://qdrant:6333
  memory-store → bolt://memgraph:7687
```

### Kubernetes Deployment

```
┌─────────────────────────────────────────────────────────┐
│              Namespace: memory-store                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Pod 1: memory-store-xxx (Deployment, 3 replicas)      │
│  ├─ Container: memory-store                            │
│  │  ├─ FastAPI application                             │
│  │  ├─ mem0 library (Python)  ← Runs here!            │
│  │  ├─ Connects to: qdrant-service                     │
│  │  └─ Connects to: memgraph-service                   │
│  └─ Resources: 512Mi-2Gi RAM, 250m-1000m CPU          │
│                                                         │
│  Pod 2: memory-store-yyy (replica)                     │
│  └─ Same as Pod 1                                      │
│                                                         │
│  Pod 3: memory-store-zzz (replica)                     │
│  └─ Same as Pod 1                                      │
│                                                         │
│  ────────────────────────────────────────────────────  │
│                                                         │
│  Pod 4: qdrant-abc (StatefulSet, 1 replica)           │
│  ├─ Container: qdrant                                  │
│  │  └─ Qdrant vector database                          │
│  ├─ PVC: qdrant-data-pvc (10Gi)                       │
│  └─ Resources: 1Gi-2Gi RAM, 500m-2000m CPU            │
│                                                         │
│  ────────────────────────────────────────────────────  │
│                                                         │
│  Pod 5: memgraph-def (Deployment, 1 replica) [OPTIONAL]│
│  ├─ Container: memgraph                                │
│  │  └─ Memgraph graph database                         │
│  ├─ PVC: memgraph-data-pvc (20Gi)                     │
│  └─ Resources: 1Gi-4Gi RAM, 500m-2000m CPU            │
│                                                         │
└─────────────────────────────────────────────────────────┘

Services (Internal ClusterIP):
  - memory-store-service:8000 → Pods 1-3
  - qdrant-service:6333 → Pod 4
  - memgraph-service:7687 → Pod 5
```

## Why Separate Pods?

### 1. **Independent Scaling**
```bash
# Scale Memory Store service (stateless)
kubectl scale deployment memory-store --replicas=10

# Qdrant stays at 1 replica (stateful)
# Memgraph stays at 1 replica (stateful)
```

### 2. **Resource Isolation**
```yaml
# Memory Store pods
resources:
  limits:
    memory: "2Gi"
    cpu: "1000m"

# Qdrant pod (needs more memory for vectors)
resources:
  limits:
    memory: "4Gi"
    cpu: "2000m"

# Memgraph pod (needs more memory for graph)
resources:
  limits:
    memory: "8Gi"
    cpu: "2000m"
```

### 3. **Independent Updates**
```bash
# Update Memory Store without affecting databases
kubectl set image deployment/memory-store \
  memory-store=registry/memory-store:v2

# Qdrant and Memgraph keep running!
```

### 4. **Failure Isolation**
```
If Memory Store crashes → Qdrant/Memgraph unaffected
If Qdrant crashes → Only vector search fails
If Memgraph crashes → Only graph queries fail
```

## Single Pod Architecture (NOT Recommended)

```
┌────────────────────────────────────────┐
│  Pod: memory-store-all-in-one          │
├────────────────────────────────────────┤
│  Container 1: memory-store             │
│  Container 2: qdrant (sidecar)         │
│  Container 3: memgraph (sidecar)       │
└────────────────────────────────────────┘
```

**Why we DON'T do this:**
- ❌ Can't scale components independently
- ❌ One failure affects everything
- ❌ Wastes resources (all containers in every replica)
- ❌ Complex orchestration
- ❌ Difficult to update individual components
- ❌ No persistent storage benefits

## Communication Flow

### Request Flow

```
Your Agent Code
     │
     │ POST /memories
     ↓
[Ingress / Load Balancer]
     │
     ↓
[memory-store-service:8000] ← Kubernetes Service (ClusterIP)
     │
     ├→ Pod 1: memory-store-xxx
     ├→ Pod 2: memory-store-yyy
     └→ Pod 3: memory-store-zzz
         │
         │ (Inside Pod 1)
         ├─→ mem0 library processes request
         │
         ├─→ http://qdrant-service:6333 ← Internal network
         │       └→ Pod 4: qdrant
         │
         └─→ bolt://memgraph-service:7687 ← Internal network
                 └→ Pod 5: memgraph
```

### Network Configuration

**Kubernetes Services:**
```yaml
# memory-store-service (exposed to cluster/ingress)
kind: Service
spec:
  type: ClusterIP
  ports:
    - port: 8000
  selector:
    app: memory-store

# qdrant-service (internal only)
kind: Service
spec:
  type: ClusterIP  # NOT exposed externally
  ports:
    - port: 6333
  selector:
    app: qdrant

# memgraph-service (internal only)
kind: Service
spec:
  type: ClusterIP  # NOT exposed externally
  ports:
    - port: 7687
  selector:
    app: memgraph
```

## Resource Allocation

### Typical Production Setup

```yaml
# 3 Memory Store pods
3 pods × 2Gi RAM = 6Gi RAM
3 pods × 1 CPU = 3 CPUs

# 1 Qdrant pod
1 pod × 4Gi RAM = 4Gi RAM
1 pod × 2 CPUs = 2 CPUs

# 1 Memgraph pod (optional)
1 pod × 4Gi RAM = 4Gi RAM
1 pod × 2 CPUs = 2 CPUs

Total: 14Gi RAM, 7 CPUs (with GraphRAG)
Total: 10Gi RAM, 5 CPUs (without GraphRAG)
```

### Cost Estimation (AWS EKS example)

**Without GraphRAG:**
- 3× t3.medium (Memory Store): $75/month
- 1× t3.large (Qdrant): $60/month
- Load Balancer: $20/month
- **Total: ~$155/month**

**With GraphRAG:**
- 3× t3.medium (Memory Store): $75/month
- 1× t3.large (Qdrant): $60/month
- 1× t3.large (Memgraph): $60/month
- Load Balancer: $20/month
- **Total: ~$215/month**

## Scaling Strategies

### Horizontal Scaling (Memory Store)

```bash
# Manual
kubectl scale deployment memory-store --replicas=5

# Automatic (HPA)
kubectl autoscale deployment memory-store \
  --min=3 --max=10 \
  --cpu-percent=70
```

**Result:**
```
Memory Store: 3 → 10 pods (scales up)
Qdrant: 1 pod (unchanged)
Memgraph: 1 pod (unchanged)
```

### Vertical Scaling (Databases)

```yaml
# Increase Qdrant resources
resources:
  limits:
    memory: "8Gi"  # Was 4Gi
    cpu: "4000m"   # Was 2000m
```

### Database Clustering (Advanced)

**Qdrant Clustering:**
```yaml
# Multiple Qdrant pods with replication
replicas: 3
env:
  - name: QDRANT_CLUSTER_ENABLED
    value: "true"
```

**Memgraph HA:**
- Vertical scaling recommended
- Or use Memgraph Cloud (managed)

## Storage Architecture

### Persistent Volumes

```
Pod: qdrant-abc
  └─ PVC: qdrant-data-pvc (10Gi)
      └─ PV: aws-ebs-volume-xxx

Pod: memgraph-def
  └─ PVC: memgraph-data-pvc (20Gi)
      └─ PV: aws-ebs-volume-yyy

Memory Store Pods: NO storage (stateless)
```

**Why separate storage:**
- ✅ Pod can be deleted/restarted
- ✅ Data persists independently
- ✅ Can be backed up separately
- ✅ Can be resized without pod restart

## Health & Monitoring

### Pod Health Checks

**Memory Store:**
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
readinessProbe:
  httpGet:
    path: /health
    port: 8000
```

**Qdrant:**
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 6333
```

**Memgraph:**
```yaml
livenessProbe:
  tcpSocket:
    port: 7687
```

### Dependency Health

Memory Store `/health` endpoint checks:
```json
{
  "service": "memory_store",
  "status": "healthy",
  "components": {
    "qdrant": {
      "status": "healthy",
      "url": "http://qdrant-service:6333"
    },
    "memgraph": {
      "status": "healthy",
      "host": "memgraph-service"
    },
    "cohere": {
      "status": "healthy",
      "model": "embed-english-v3.0"
    }
  }
}
```

## Deployment Commands

### Deploy All Components

```bash
# Deploy everything at once
kubectl apply -k k8s/

# This creates:
# - Namespace: memory-store
# - ConfigMap: memory-store-config
# - Secret: memory-store-secrets
# - Deployment: memory-store (3 pods)
# - Deployment: qdrant (1 pod)
# - Deployment: memgraph (1 pod, if uncommented)
# - Service: memory-store-service
# - Service: qdrant-service
# - Service: memgraph-service
# - HPA: memory-store-hpa
```

### Check Deployment

```bash
# See all pods
kubectl get pods -n memory-store

# Output:
# NAME                            READY   STATUS    RESTARTS
# memory-store-abc123-xxx         1/1     Running   0
# memory-store-abc123-yyy         1/1     Running   0
# memory-store-abc123-zzz         1/1     Running   0
# qdrant-def456                   1/1     Running   0
# memgraph-ghi789                 1/1     Running   0
```

## Summary

**Deployment Architecture:**
- ✅ **3 separate pods** for Memory Store service (scalable)
- ✅ **1 separate pod** for Qdrant (stateful)
- ✅ **1 separate pod** for Memgraph (stateful, optional)
- ✅ **mem0 is a library**, not a pod (runs inside Memory Store)

**Benefits:**
- ✅ Independent scaling
- ✅ Resource isolation
- ✅ Failure isolation
- ✅ Independent updates
- ✅ Standard Kubernetes patterns

**Your agents only connect to:**
- `http://memory-store-service:8000`

**Internal communication (automatic):**
- Memory Store → Qdrant (via qdrant-service)
- Memory Store → Memgraph (via memgraph-service)

---

**Questions? Check [ARCHITECTURE.md](ARCHITECTURE.md) for more details.**
