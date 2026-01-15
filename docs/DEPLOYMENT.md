# Mem0 - Deployment Guide

Complete deployment guide for the Mem0 service in various environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [Local Development](#local-development)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Production Considerations](#production-considerations)
- [Monitoring & Observability](#monitoring--observability)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Services

1. **Cohere API Key** (Required)
   - Sign up at https://cohere.com/
   - Get API key from dashboard
   - Supports pay-as-you-go pricing

2. **Qdrant Vector Database** (Required)
   - Local: Docker container
   - Cloud: https://qdrant.tech/cloud/
   - Self-hosted: Kubernetes deployment

3. **LLM Gateway** (Optional)
   - Your existing LLM Gateway infrastructure
   - OAuth or API key authentication

### System Requirements

- Python 3.10+
- Docker 20.10+ (for containerized deployment)
- Kubernetes 1.24+ (for K8s deployment)
- 2GB RAM minimum (4GB recommended)
- 10GB disk space (for Qdrant storage)

## Environment Configuration

### Step 1: Copy Environment Template

```bash
cp env.example .env
```

### Step 2: Configure Required Variables

```bash
# Required
COHERE_API_KEY=your_actual_cohere_api_key_here

# Qdrant (local development)
QDRANT_URL=http://localhost:6333

# Or Qdrant Cloud
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_cloud_api_key
```

### Step 3: Configure Optional LLM Gateway

```bash
# Your existing LLM Gateway
LLM_SERVER_URL=https://llm-gateway.yourcompany.com/v1/chat/completions
LLM_MODEL_NAME=gpt-4

# OAuth authentication
LLM_OAUTH_ENDPOINT=https://auth.yourcompany.com/oauth/token
LLM_CLIENT_ID=your_client_id
LLM_CLIENT_SECRET=your_client_secret

# Or API key authentication
LLM_API_KEY=your_api_key
```

## Local Development

### Option 1: Docker Compose (Recommended)

This is the easiest way to get started with all dependencies.

```bash
# 1. Ensure .env is configured
cat .env  # verify configuration

# 2. Start all services
docker-compose up -d

# 3. Check logs
docker-compose logs -f mem0

# 4. Test the API
curl http://localhost:8000/health

# 5. Open API docs
open http://localhost:8000/docs
```

Services started:
- Mem0 API: http://localhost:8000
- Qdrant: http://localhost:6333
- Qdrant Dashboard: http://localhost:6333/dashboard

### Option 2: Local Python

For active development without Docker.

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Start Qdrant in Docker
docker run -d -p 6333:6333 -p 6334:6334 \
  --name qdrant \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:latest

# 3. Export environment variables
export COHERE_API_KEY=your_key
export QDRANT_URL=http://localhost:6333

# 4. Run the service
mem0 --reload --log-level DEBUG

# Or run directly
python -m uvicorn memory_store.api:app --reload
```

### Verify Local Setup

```bash
# Health check
curl http://localhost:8000/health | jq

# Add a test memory
curl -X POST http://localhost:8000/memories \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test_agent",
    "messages": "This is a test memory",
    "metadata": {"source": "test"}
  }' | jq

# Search memories
curl -X POST http://localhost:8000/memories/search \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test_agent",
    "query": "test",
    "limit": 5
  }' | jq
```

## Docker Deployment

### Build and Run

```bash
# Build image
docker build -t mem0:latest .

# Run container
docker run -d \
  --name mem0 \
  -p 8000:8000 \
  --env-file .env \
  mem0:latest

# Check logs
docker logs -f mem0
```

### Push to Registry

```bash
# Tag image
docker tag mem0:latest your-registry/mem0:latest

# Push to registry
docker push your-registry/mem0:latest

# Or use Azure Container Registry
az acr build --registry yourregistry --image mem0:latest .

# Or use AWS ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin your-account.dkr.ecr.us-east-1.amazonaws.com
docker tag mem0:latest your-account.dkr.ecr.us-east-1.amazonaws.com/mem0:latest
docker push your-account.dkr.ecr.us-east-1.amazonaws.com/mem0:latest
```

## Kubernetes Deployment

### Prerequisites

```bash
# Verify kubectl access
kubectl cluster-info

# Verify context
kubectl config current-context
```

### Step-by-Step Deployment

#### 1. Create Namespace

```bash
kubectl apply -f k8s/namespace.yaml

# Verify
kubectl get namespace mem0
```

#### 2. Create Secrets

```bash
# Create secrets from literals
kubectl create secret generic mem0-secrets \
  --namespace=mem0 \
  --from-literal=COHERE_API_KEY='your_cohere_api_key' \
  --from-literal=LLM_CLIENT_SECRET='your_llm_secret' \
  --from-literal=LLM_SERVER_URL='https://your-llm-gateway.com/v1/chat/completions'

# Verify (values are hidden)
kubectl get secret mem0-secrets -n mem0 -o yaml
```

Or create from file:

```bash
# Create .env.k8s with secrets
cat > .env.k8s <<EOF
COHERE_API_KEY=your_key
LLM_CLIENT_SECRET=your_secret
EOF

# Create secret from file
kubectl create secret generic mem0-secrets \
  --namespace=mem0 \
  --from-env-file=.env.k8s

# Delete the file
rm .env.k8s
```

#### 3. Update Kustomization

Edit `k8s/kustomization.yaml` to set your registry:

```yaml
images:
  - name: your-registry/mem0
    newName: your-actual-registry/mem0  # <-- change this
    newTag: latest
```

#### 4. Deploy All Resources

```bash
# Deploy with kustomize
kubectl apply -k k8s/

# Or deploy manually
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/qdrant-deployment.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/ingress.yaml  # optional
```

#### 5. Verify Deployment

```bash
# Check all resources
kubectl get all -n mem0

# Check pods
kubectl get pods -n mem0 -w

# Check services
kubectl get svc -n mem0

# Check HPA (autoscaler)
kubectl get hpa -n mem0
```

#### 6. View Logs

```bash
# Mem0 logs
kubectl logs -n mem0 -l app=mem0 --tail=100 -f

# Qdrant logs
kubectl logs -n mem0 -l app=qdrant --tail=100 -f

# Specific pod
kubectl logs -n mem0 pod/mem0-xxxxx -f
```

#### 7. Test the Service

```bash
# Port-forward to local machine
kubectl port-forward -n mem0 svc/mem0-service 8000:8000

# In another terminal
curl http://localhost:8000/health | jq
```

### Using Ingress (Production)

#### NGINX Ingress Controller

```bash
# Install NGINX Ingress Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml

# Update k8s/ingress.yaml with your domain
# Then apply
kubectl apply -f k8s/ingress.yaml

# Get ingress IP
kubectl get ingress -n mem0
```

#### AWS ALB Ingress Controller

```bash
# Update k8s/ingress.yaml annotations:
kubernetes.io/ingress.class: alb
alb.ingress.kubernetes.io/scheme: internet-facing
alb.ingress.kubernetes.io/target-type: ip
alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:...

# Apply
kubectl apply -f k8s/ingress.yaml

# Get ALB DNS
kubectl get ingress -n mem0
```

### Scaling

```bash
# Manual scaling
kubectl scale deployment mem0 -n mem0 --replicas=5

# Check HPA status
kubectl get hpa -n mem0

# Describe HPA
kubectl describe hpa mem0-hpa -n mem0
```

## Production Considerations

### High Availability

1. **Multiple Replicas**
   ```yaml
   spec:
     replicas: 3  # minimum for HA
   ```

2. **Pod Disruption Budget**
   ```yaml
   apiVersion: policy/v1
   kind: PodDisruptionBudget
   metadata:
     name: mem0-pdb
   spec:
     minAvailable: 2
     selector:
       matchLabels:
         app: mem0
   ```

3. **Multi-AZ Deployment**
   ```yaml
   affinity:
     podAntiAffinity:
       preferredDuringSchedulingIgnoredDuringExecution:
         - weight: 100
           podAffinityTerm:
             labelSelector:
               matchLabels:
                 app: mem0
             topologyKey: topology.kubernetes.io/zone
   ```

### Storage

1. **Persistent Storage for Qdrant**
   ```yaml
   storageClassName: fast-ssd  # or your storage class
   resources:
     requests:
       storage: 100Gi
   ```

2. **Backup Strategy**
   ```bash
   # Create snapshot
   kubectl exec -n mem0 qdrant-xxx -- qdrant-backup create
   
   # Copy to S3
   kubectl cp mem0/qdrant-xxx:/qdrant/backups/snapshot.tar.gz ./
   aws s3 cp snapshot.tar.gz s3://your-bucket/backups/
   ```

### Security

1. **Network Policies**
   ```yaml
   apiVersion: networking.k8s.io/v1
   kind: NetworkPolicy
   metadata:
     name: mem0-netpol
   spec:
     podSelector:
       matchLabels:
         app: mem0
     policyTypes:
       - Ingress
       - Egress
   ```

2. **Pod Security Standards**
   ```yaml
   securityContext:
     runAsNonRoot: true
     runAsUser: 1000
     fsGroup: 1000
     seccompProfile:
       type: RuntimeDefault
   ```

3. **Secret Management**
   - Use External Secrets Operator
   - Or AWS Secrets Manager
   - Or HashiCorp Vault

## Monitoring & Observability

### Metrics

Add Prometheus monitoring:

```yaml
# In deployment.yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8000"
  prometheus.io/path: "/metrics"
```

### Logging

```bash
# Structured logging to stdout
kubectl logs -n mem0 -l app=mem0 | jq

# Or use log aggregation
# - ELK Stack
# - Grafana Loki
# - AWS CloudWatch
```

### Tracing

Add OpenTelemetry:

```python
# Install: pip install opentelemetry-instrumentation-fastapi
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

FastAPIInstrumentor.instrument_app(app)
```

### Dashboards

- Grafana dashboard for metrics
- Kibana for log analysis
- Qdrant dashboard for vector search metrics

## Troubleshooting

### Common Issues

1. **Pods not starting**
   ```bash
   kubectl describe pod -n mem0 mem0-xxx
   kubectl logs -n mem0 mem0-xxx --previous
   ```

2. **Cohere API errors**
   ```bash
   # Check secret
   kubectl get secret mem0-secrets -n mem0 -o yaml
   
   # Recreate secret
   kubectl delete secret mem0-secrets -n mem0
   kubectl create secret generic mem0-secrets --from-literal=COHERE_API_KEY=new_key
   
   # Restart pods
   kubectl rollout restart deployment mem0 -n mem0
   ```

3. **Qdrant connection issues**
   ```bash
   # Check Qdrant is running
   kubectl get pods -n mem0 -l app=qdrant
   
   # Test connection from mem0 pod
   kubectl exec -n mem0 mem0-xxx -- curl http://qdrant-service:6333/healthz
   ```

4. **OOM (Out of Memory) errors**
   ```bash
   # Increase memory limits
   kubectl edit deployment mem0 -n mem0
   # Update: resources.limits.memory: "4Gi"
   ```

### Debug Mode

```bash
# Run with debug logging
kubectl set env deployment/mem0 -n mem0 SERVICE_LOG_LEVEL=DEBUG

# Watch logs
kubectl logs -n mem0 -l app=mem0 -f --tail=100
```

### Health Checks

```bash
# Check health endpoint
kubectl port-forward -n mem0 svc/mem0-service 8000:8000
curl http://localhost:8000/health | jq

# Check from within cluster
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://mem0-service.mem0:8000/health
```

## Rollback

```bash
# View deployment history
kubectl rollout history deployment mem0 -n mem0

# Rollback to previous version
kubectl rollout undo deployment mem0 -n mem0

# Rollback to specific revision
kubectl rollout undo deployment mem0 -n mem0 --to-revision=2
```

## Cleanup

```bash
# Delete everything
kubectl delete -k k8s/

# Or delete namespace (removes everything)
kubectl delete namespace mem0
```

## Next Steps

- Set up monitoring with Prometheus/Grafana
- Configure backup automation
- Implement GitOps with ArgoCD or Flux
- Add CI/CD pipeline
- Configure auto-scaling policies
- Set up disaster recovery procedures
