# Deployment Architecture - Pod/Container Layout

Clear explanation of how services are deployed.

## Important Clarification

### What is mem0?

**mem0 is NOT a separate service** - it's a **Python library** that runs inside the Mem0 application code.

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
│  Container 1: mem0-service                     │
│  ├─ FastAPI application                               │
│  ├─ mem0 library (Python code)  ← Runs here!         │
│  ├─ Connects to: Qdrant (via network)                │
│  └─ Connects to: Memgraph (via network)              │
│                                                        │
│  Container 2: mem0-qdrant                      │
│  ├─ Qdrant vector database                            │
│  └─ Port 6333 (internal)                              │
│                                                        │
│  Container 3: mem0-memgraph (optional)         │
│  ├─ Memgraph graph database                           │
│  └─ Port 7687 (internal)                              │
│                                                        │
└────────────────────────────────────────────────────────┘

Communication:
  mem0 → http://qdrant:6333
  mem0 → bolt://memgraph:7687
```

### Kubernetes Deployment

```
┌─────────────────────────────────────────────────────────┐
│              Namespace: mem0                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Pod 1: mem0-xxx (Deployment, 3 replicas)      │
│  ├─ Container: mem0                            │
│  │  ├─ FastAPI application                             │
│  │  ├─ mem0 library (Python)  ← Runs here!            │
│  │  ├─ Connects to: qdrant-service                     │
│  │  └─ Connects to: memgraph-service                   │
│  └─ Resources: 512Mi-2Gi RAM, 250m-1000m CPU          │
│                                                         │
│  Pod 2: mem0-yyy (replica)                     │
│  └─ Same as Pod 1                                      │
│                                                         │
│  Pod 3: mem0-zzz (replica)                     │
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
  - mem0-service:8000 → Pods 1-3
  - qdrant-service:6333 → Pod 4
  - memgraph-service:7687 → Pod 5
```

## Why Separate Pods?

### 1. **Independent Scaling**
```bash
# Scale Mem0 service (stateless)
kubectl scale deployment mem0 --replicas=10

# Qdrant stays at 1 replica (stateful)
# Memgraph stays at 1 replica (stateful)
```

### 2. **Resource Isolation**
```yaml
# Mem0 pods
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
# Update Mem0 without affecting databases
kubectl set image deployment/mem0 \
  mem0=registry/mem0:v2

# Qdrant and Memgraph keep running!
```

### 4. **Failure Isolation**
```
If Mem0 crashes → Qdrant/Memgraph unaffected
If Qdrant crashes → Only vector search fails
If Memgraph crashes → Only graph queries fail
```

## Single Pod Architecture (NOT Recommended)

```
┌────────────────────────────────────────┐
│  Pod: mem0-all-in-one          │
├────────────────────────────────────────┤
│  Container 1: mem0             │
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
[mem0-service:8000] ← Kubernetes Service (ClusterIP)
     │
     ├→ Pod 1: mem0-xxx
     ├→ Pod 2: mem0-yyy
     └→ Pod 3: mem0-zzz
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
# mem0-service (exposed to cluster/ingress)
kind: Service
spec:
  type: ClusterIP
  ports:
    - port: 8000
  selector:
    app: mem0

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
# 3 Mem0 pods
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
- 3× t3.medium (Mem0): $75/month
- 1× t3.large (Qdrant): $60/month
- Load Balancer: $20/month
- **Total: ~$155/month**

**With GraphRAG:**
- 3× t3.medium (Mem0): $75/month
- 1× t3.large (Qdrant): $60/month
- 1× t3.large (Memgraph): $60/month
- Load Balancer: $20/month
- **Total: ~$215/month**

## Scaling Strategies

### Horizontal Scaling (Mem0)

```bash
# Manual
kubectl scale deployment mem0 --replicas=5

# Automatic (HPA)
kubectl autoscale deployment mem0 \
  --min=3 --max=10 \
  --cpu-percent=70
```

**Result:**
```
Mem0: 3 → 10 pods (scales up)
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

Mem0 Pods: NO storage (stateless)
```

**Why separate storage:**
- ✅ Pod can be deleted/restarted
- ✅ Data persists independently
- ✅ Can be backed up separately
- ✅ Can be resized without pod restart

## Health & Monitoring

### Pod Health Checks

**Mem0:**
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

Mem0 `/health` endpoint checks:
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
# - Namespace: mem0
# - ConfigMap: mem0-config
# - Secret: mem0-secrets
# - Deployment: mem0 (3 pods)
# - Deployment: qdrant (1 pod)
# - Deployment: memgraph (1 pod, if uncommented)
# - Service: mem0-service
# - Service: qdrant-service
# - Service: memgraph-service
# - HPA: mem0-hpa
```

### Check Deployment

```bash
# See all pods
kubectl get pods -n mem0

# Output:
# NAME                            READY   STATUS    RESTARTS
# mem0-abc123-xxx         1/1     Running   0
# mem0-abc123-yyy         1/1     Running   0
# mem0-abc123-zzz         1/1     Running   0
# qdrant-def456                   1/1     Running   0
# memgraph-ghi789                 1/1     Running   0
```

## Summary

**Deployment Architecture:**
- ✅ **3 separate pods** for Mem0 service (scalable)
- ✅ **1 separate pod** for Qdrant (stateful)
- ✅ **1 separate pod** for Memgraph (stateful, optional)
- ✅ **mem0 is a library**, not a pod (runs inside Mem0)

**Benefits:**
- ✅ Independent scaling
- ✅ Resource isolation
- ✅ Failure isolation
- ✅ Independent updates
- ✅ Standard Kubernetes patterns

**Your agents only connect to:**
- `http://mem0-service:8000`

**Internal communication (automatic):**
- Mem0 → Qdrant (via qdrant-service)
- Mem0 → Memgraph (via memgraph-service)

---

**Questions? Check [ARCHITECTURE.md](ARCHITECTURE.md) for more details.**
