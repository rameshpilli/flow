# Corporate Deployment Guide - Mem0

Complete guide for deploying Mem0 to RBC corporate Kubernetes environments using Helm and Helios.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Project Structure](#project-structure)
4. [Building the Docker Image](#building-the-docker-image)
5. [Helm Chart Configuration](#helm-chart-configuration)
6. [Helios Deployment](#helios-deployment)
7. [Environment-Specific Configuration](#environment-specific-configuration)
8. [Vault Secrets Management](#vault-secrets-management)
9. [Deployment Verification](#deployment-verification)
10. [Troubleshooting](#troubleshooting)

---

## Overview

Mem0 uses RBC corporate standards for Kubernetes deployment:

- **Helm**: For Kubernetes manifest templating
- **Helios**: For multi-environment deployment orchestration
- **Vault**: For secrets management
- **Artifactory**: For Docker image storage

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Mem0 Deployment                     │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Mem0 │  │   Qdrant     │  │  Memgraph    │  │
│  │   (API)      │  │ (Vector DB)  │  │ (Graph DB)   │  │
│  │  Pods: 1-10  │  │   Pods: 1    │  │   Pods: 1    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                 │                   │          │
│         └─────────────────┴───────────────────┘          │
│                           │                               │
│                   ┌───────▼────────┐                     │
│                   │   Ingress      │                     │
│                   │ (cert-manager) │                     │
│                   └────────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required Tools

- Helm 3.x
- kubectl
- Docker
- Access to RBC corporate Kubernetes clusters
- Vault access credentials

### Corporate Access

- [ ] Artifactory credentials
- [ ] Kubernetes cluster access (dev/qat/prod)
- [ ] Vault service account credentials
- [ ] GitHub access to RBC-TO Helios

### Required Secrets (to be stored in Vault)

```bash
# Path: appcodes/ISA0/<ENV>/MEMORY-STORE
COHERE_API_KEY=<your_cohere_key>
LLM_GATEWAY_CLIENT_ID=<oauth_client_id>
LLM_GATEWAY_CLIENT_SECRET=<oauth_client_secret>
LLM_GATEWAY_API_KEY=<gateway_api_key>  # if using API key auth
```

---

## Project Structure

```
memory_store/
├── helm/                           # Helm chart
│   ├── Chart.yaml                  # Chart metadata
│   ├── values.yaml                 # Base values
│   ├── .helmignore
│   ├── environments/
│   │   ├── dev/values.yaml        # DEV overrides
│   │   ├── qat/values.yaml        # QAT overrides
│   │   └── prod/values.yaml       # PROD overrides
│   └── templates/
│       ├── _helpers.tpl           # Template helpers
│       ├── deployment.yaml        # Mem0 deployment
│       ├── service.yaml           # Service definition
│       ├── configmap.yaml         # Configuration
│       ├── ingress.yaml           # External access
│       ├── hpa.yaml               # Auto-scaling
│       ├── serviceaccount.yaml    # Service account
│       ├── qdrant-deployment.yaml # Qdrant vector DB
│       ├── memgraph-deployment.yaml # Memgraph graph DB
│       └── NOTES.txt              # Post-install notes
│
├── helios/                         # Helios deployment
│   ├── env-config.yml             # Environment configuration
│   └── deploy.sh                  # Deployment script
│
└── deployments/
    ├── Dockerfile.corporate       # Corporate Dockerfile
    └── docker-compose.yml         # Local development
```

---

## Building the Docker Image

### 1. Corporate Dockerfile

The `deployments/Dockerfile.corporate` uses RBC standards:

```dockerfile
FROM innersource-docker.artifactory.fg.rbc.com/container-hub/python:3.11-linux-amd64
```

**Key Features:**
- Corporate Python base image
- Artifactory PyPI repository
- Non-root user for security
- Health checks
- UV for fast dependency installation

### 2. Build Command

```bash
# Build image
docker build \
  -f deployments/Dockerfile.corporate \
  -t docker-isa0-dev.artifactory.fg.rbc.com/isa0-mem0:0.1.0 \
  .

# Push to Artifactory
docker push docker-isa0-dev.artifactory.fg.rbc.com/isa0-mem0:0.1.0
```

### 3. CI/CD Integration

This is typically automated through your CI/CD pipeline which:
1. Builds the image
2. Tags with commit SHA or version
3. Pushes to environment-specific Artifactory repo
4. Triggers Helios deployment

---

## Helm Chart Configuration

### Base Values (`helm/values.yaml`)

Core configuration shared across environments:

```yaml
rbc:
  appCode: isa0
  artifactory:
    host: artifactory.fg.rbc.com

image:
  name: isa0-mem0
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80
  targetPort: 8000

qdrant:
  enabled: true

memgraph:
  enabled: false  # Override per environment
```

### Environment Overrides

Each environment has specific overrides in `helm/environments/<env>/values.yaml`:

#### DEV (`helm/environments/dev/values.yaml`)
- Minimal resources
- Debug logging
- Autoscaling: 1-3 replicas
- Ingress: `mem0.cfk.devfg.rbc.com`

#### QAT (`helm/environments/qat/values.yaml`)
- Medium resources
- Memgraph enabled for testing
- Autoscaling: 2-5 replicas
- Ingress: `mem0.cfkqa.saifg.rbc.com`

#### PROD (`helm/environments/prod/values.yaml`)
- Full resources
- Memgraph enabled
- Autoscaling: 3-10 replicas
- Pod anti-affinity for HA
- Ingress: `mem0.cfkprod.fg.rbc.com`

### Template Customization

To customize for your app code:

1. Update `helm/values.yaml`:
   ```yaml
   rbc:
     appCode: your-app-code  # Change from isa0
   ```

2. Update image names in environment files:
   ```yaml
   image:
     artifactoryRepo: docker-your-app-code-dev
   ```

3. Update ingress hosts:
   ```yaml
   ingress:
     host: mem0.your-domain.fg.rbc.com
   ```

---

## Helios Deployment

### Environment Configuration (`helios/env-config.yml`)

Defines deployment targets for each environment:

```yaml
compute-fabric:
  environments:
    - name: dev
      ucp:
        cluster: ucpdev01.fg.rbc.com
        namespace: isa0-dev
        k8s:
          processing:
            helm:
              command: |
                helm template ./helm/ \
                  --values ./helm/environments/dev/values.yaml \
                  --set ghActionInput.imageTag="${CUSTOM_APP_IMAGE_TAG}"
```

**Update for your app:**
- Change namespace from `isa0-dev` to `<your-app-code>-dev`
- Update cluster if deploying to different UCP

### Deployment Script (`helios/deploy.sh`)

The deployment script:
1. ✅ Retrieves Vault token
2. ✅ Fetches secrets from Vault
3. ✅ Writes secrets to vault_values.yaml
4. ✅ Runs Helm upgrade/install
5. ✅ Verifies deployment
6. ✅ Checks health endpoints

**Update for your app:**
- Change `VAULT_PATH` from `MEMORY-STORE` to your service name

---

## Environment-Specific Configuration

### DEV Environment

**Purpose**: Development and testing

**Configuration**:
```yaml
autoscaling:
  enabled: true
  minReplicas: 1
  maxReplicas: 3

resources:
  limits:
    cpu: 1000m
    memory: 2Gi
  requests:
    cpu: 250m
    memory: 512Mi

configuration:
  SERVICE_LOG_LEVEL: "DEBUG"
  SERVICE_WORKERS: "'2'"
```

**Storage**:
- Qdrant: 5Gi
- Memgraph: 2Gi (if enabled)

**Access**:
- URL: `https://mem0.cfk.devfg.rbc.com`

### QAT Environment

**Purpose**: Quality assurance and integration testing

**Configuration**:
```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 5

memgraph:
  enabled: true  # GraphRAG testing

configuration:
  SERVICE_LOG_LEVEL: "INFO"
  SERVICE_WORKERS: "'4'"
  MEM0_GRAPH_STORE_ENABLED: "'true'"
```

**Storage**:
- Qdrant: 10Gi
- Memgraph: 5Gi

**Access**:
- URL: `https://mem0.cfkqa.saifg.rbc.com`

### PROD Environment

**Purpose**: Production workloads

**Configuration**:
```yaml
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10

memgraph:
  enabled: true

resources:
  limits:
    cpu: 2000m
    memory: 4Gi
  requests:
    cpu: 1000m
    memory: 2Gi

affinity:
  podAntiAffinity:  # Spread across nodes
    preferredDuringSchedulingIgnoredDuringExecution: [...]
```

**Storage**:
- Qdrant: 50Gi
- Memgraph: 20Gi

**Access**:
- URL: `https://mem0.cfkprod.fg.rbc.com`

---

## Vault Secrets Management

### Vault Path Structure

```
appcodes/ISA0/
├── DEV/
│   └── MEMORY-STORE/
│       ├── COHERE_API_KEY
│       ├── LLM_GATEWAY_CLIENT_ID
│       └── LLM_GATEWAY_CLIENT_SECRET
├── SAI/  (QAT uses SAI)
│   └── MEMORY-STORE/
│       └── ...
└── PROD/
    └── MEMORY-STORE/
        └── ...
```

### Setting Up Secrets

1. **Access Vault UI**:
   ```
   https://vault.fg.rbc.com
   ```

2. **Navigate to your path**:
   ```
   appcodes/ISA0/<ENV>/MEMORY-STORE
   ```

3. **Add secrets** (key-value pairs):
   ```json
   {
     "COHERE_API_KEY": "your_cohere_api_key",
     "LLM_GATEWAY_CLIENT_ID": "your_oauth_client_id",
     "LLM_GATEWAY_CLIENT_SECRET": "your_oauth_secret",
     "LLM_GATEWAY_API_KEY": "your_gateway_api_key"
   }
   ```

### How Secrets Are Injected

During deployment, `helios/deploy.sh`:

1. Authenticates to Vault using service account
2. Fetches secrets from the environment-specific path
3. Writes them to `vault_values.yaml`
4. Passes them to Helm, which injects into ConfigMap
5. ConfigMap is mounted as environment variables in pods

**Example flow**:
```
Vault → deploy.sh → vault_values.yaml → Helm → ConfigMap → Pod Env Vars
```

---

## Deployment Verification

### Post-Deployment Checks

The `deploy.sh` script automatically verifies:

1. **Deployment rollout**:
   ```bash
   kubectl rollout status deployment/mem0 --timeout=5m
   ```

2. **Pod health**:
   ```bash
   kubectl get pods -l app.kubernetes.io/name=mem0
   ```

3. **Health endpoint**:
   ```bash
   curl https://mem0.cfk.devfg.rbc.com/health
   ```

4. **Qdrant status**:
   ```bash
   kubectl get pods -l app.kubernetes.io/name=mem0-qdrant
   ```

5. **Memgraph status** (if enabled):
   ```bash
   kubectl get pods -l app.kubernetes.io/name=mem0-memgraph
   ```

### Manual Verification

```bash
# Check all resources
kubectl get all -l app.kubernetes.io/name=mem0

# Check HPA
kubectl get hpa mem0

# Check ingress
kubectl get ingress mem0

# View logs
kubectl logs -f deployment/mem0

# Test API
kubectl port-forward svc/mem0 8000:80
curl http://localhost:8000/docs
```

### Health Check Response

Expected response from `/health`:

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "components": {
    "qdrant": "connected",
    "memgraph": "connected",
    "llm_gateway": "connected"
  }
}
```

---

## Troubleshooting

### Common Issues

#### 1. Image Pull Failures

**Symptom**:
```
Failed to pull image: unauthorized
```

**Solution**:
- Verify imagePullSecrets in values.yaml
- Check Artifactory credentials
- Ensure image exists in the repo

```bash
# Check secret
kubectl get secret artifactory-docker-isa0-dev-secret -o yaml

# Test image pull manually
docker pull docker-isa0-dev.artifactory.fg.rbc.com/isa0-mem0:0.1.0
```

#### 2. Vault Authentication Failures

**Symptom**:
```
[ERROR] Failed to retrieve Vault token
```

**Solution**:
- Verify service account credentials
- Check Vault path permissions
- Ensure environment variables are set correctly

```bash
# Test Vault access
curl -sk \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"${PASSWORD}\"}" \
  "https://vault.fg.rbc.com/v1/auth/fg/login/${USER_ID}"
```

#### 3. Qdrant Connection Issues

**Symptom**:
```
Failed to connect to Qdrant
```

**Solution**:
- Check Qdrant pod status
- Verify service DNS resolution
- Check network policies

```bash
# Check Qdrant pod
kubectl get pod -l app.kubernetes.io/name=mem0-qdrant

# Test connectivity from Mem0 pod
kubectl exec -it <mem0-pod> -- \
  curl http://mem0-qdrant:6333/
```

#### 4. Health Check Failures

**Symptom**:
```
Readiness probe failed: Get http://.../health: connection refused
```

**Solution**:
- Check application logs
- Verify port configuration
- Increase initialDelaySeconds

```bash
# View logs
kubectl logs <pod-name>

# Check port
kubectl exec <pod-name> -- netstat -tlnp | grep 8000
```

#### 5. Ingress Not Working

**Symptom**:
```
404 Not Found or SSL errors
```

**Solution**:
- Verify ingress is created
- Check cert-manager certificate
- Verify DNS resolution

```bash
# Check ingress
kubectl get ingress mem0 -o yaml

# Check certificate
kubectl get certificate mem0-cert-tls

# Test DNS
nslookup mem0.cfk.devfg.rbc.com
```

### Debugging Commands

```bash
# Describe deployment
kubectl describe deployment mem0

# Get events
kubectl get events --sort-by='.lastTimestamp'

# Check resource usage
kubectl top pods -l app.kubernetes.io/name=mem0

# Exec into pod
kubectl exec -it <pod-name> -- /bin/bash

# View all logs
kubectl logs -l app.kubernetes.io/name=mem0 --all-containers=true

# Check ConfigMap
kubectl get configmap mem0-cfgmap -o yaml
```

### Getting Help

1. **Check documentation**:
   - This guide
   - Helios docs: https://rbcgithub.fg.rbc.com/pages/rbc-to/a0d0-helios-docs
   - Kubernetes troubleshooting: docs/TROUBLESHOOTING.md

2. **Review logs**:
   - Application logs
   - Kubernetes events
   - Helios deployment logs

3. **Contact support**:
   - ChainServer team
   - RBC TO Helios support
   - Kubernetes platform team

---

## Next Steps

After successful deployment:

1. **Test API endpoints**: See [docs/USER_GUIDE.md](USER_GUIDE.md)
2. **Integrate with agents**: See [docs/INTEGRATION.md](INTEGRATION.md)
3. **Monitor performance**: Set up dashboards and alerts
4. **Scale as needed**: Adjust HPA settings

---

## Appendix: Quick Reference

### Useful Commands

```bash
# Template Helm chart locally
helm template mem0 ./helm/ \
  --values ./helm/environments/dev/values.yaml

# Install directly with Helm (without Helios)
helm install mem0 ./helm/ \
  --values ./helm/environments/dev/values.yaml \
  --namespace isa0-dev

# Upgrade release
helm upgrade mem0 ./helm/ \
  --values ./helm/environments/dev/values.yaml \
  --namespace isa0-dev

# Rollback
helm rollback mem0 1 --namespace isa0-dev

# Uninstall
helm uninstall mem0 --namespace isa0-dev
```

### Environment URLs

| Environment | URL |
|-------------|-----|
| DEV | https://mem0.cfk.devfg.rbc.com |
| QAT | https://mem0.cfkqa.saifg.rbc.com |
| PROD | https://mem0.cfkprod.fg.rbc.com |

### Resource Limits

| Environment | Min Pods | Max Pods | CPU (Req/Limit) | Memory (Req/Limit) |
|-------------|----------|----------|-----------------|---------------------|
| DEV | 1 | 3 | 250m/1000m | 512Mi/2Gi |
| QAT | 2 | 5 | 500m/1500m | 1Gi/3Gi |
| PROD | 3 | 10 | 1000m/2000m | 2Gi/4Gi |

---

**Last Updated**: 2026-01-14  
**Version**: 0.1.0  
**Maintainer**: ChainServer Team
