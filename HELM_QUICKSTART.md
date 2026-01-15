# Helm/Helios Quick Reference

Quick reference for deploying Mem0 to corporate Kubernetes using Helm and Helios.

## 📋 Prerequisites Checklist

- [ ] Helm 3.x installed
- [ ] kubectl configured
- [ ] Access to corporate Kubernetes cluster
- [ ] Vault credentials
- [ ] Docker image built and pushed to Artifactory

## 🚀 Quick Deploy Commands

### 1. Lint Chart
```bash
make helm-lint
```

### 2. Template Chart (Test)
```bash
# DEV environment
make helm-template-dev

# QAT environment
make helm-template-qat

# PROD environment
make helm-template-prod
```

### 3. Deploy to DEV
```bash
# Install for first time
make helm-install ENVIRONMENT=dev

# Or upgrade existing
make helm-upgrade ENVIRONMENT=dev
```

### 4. Check Status
```bash
# Helm status
make helm-status

# Kubernetes status
kubectl get all -n isa0-dev
```

## 🔧 Configuration Files

### Helm Chart Structure
```
helm/
├── Chart.yaml                     # Chart metadata
├── values.yaml                    # Base configuration
├── environments/
│   ├── dev/values.yaml           # DEV overrides
│   ├── qat/values.yaml           # QAT overrides
│   └── prod/values.yaml          # PROD overrides
└── templates/
    ├── deployment.yaml           # Main application
    ├── qdrant-deployment.yaml    # Vector database
    ├── memgraph-deployment.yaml  # Graph database (optional)
    ├── service.yaml              # Service
    ├── ingress.yaml              # External access
    ├── hpa.yaml                  # Auto-scaling
    └── configmap.yaml            # Configuration
```

### Helios Configuration
```
helios/
├── env-config.yml    # Environment definitions (dev/qat/prod)
└── deploy.sh         # Deployment script with Vault integration
```

## 🎯 Environment-Specific Settings

### DEV
- **URL**: https://mem0.cfk.devfg.rbc.com
- **Namespace**: isa0-dev
- **Replicas**: 1-3 (auto-scaling)
- **Memgraph**: Disabled by default

### QAT
- **URL**: https://mem0.cfkqa.saifg.rbc.com
- **Namespace**: isa0-qat
- **Replicas**: 2-5 (auto-scaling)
- **Memgraph**: Enabled for testing

### PROD
- **URL**: https://mem0.cfkprod.fg.rbc.com
- **Namespace**: isa0-prod
- **Replicas**: 3-10 (auto-scaling)
- **Memgraph**: Enabled

## 🔐 Vault Secrets

### Path Structure
```
appcodes/ISA0/<ENV>/MEMORY-STORE/
├── COHERE_API_KEY
├── LLM_GATEWAY_CLIENT_ID
├── LLM_GATEWAY_CLIENT_SECRET
└── LLM_GATEWAY_API_KEY
```

### Required Secrets
```json
{
  "COHERE_API_KEY": "your_cohere_key",
  "LLM_GATEWAY_CLIENT_ID": "oauth_client_id",
  "LLM_GATEWAY_CLIENT_SECRET": "oauth_secret",
  "LLM_GATEWAY_API_KEY": "api_key_if_using_api_key_auth"
}
```

## 📦 Customization Checklist

If deploying as a different app:

- [ ] Update `rbc.appCode` in `helm/values.yaml`
- [ ] Update `image.name` in `helm/values.yaml`
- [ ] Update `image.artifactoryRepo` in environment values
- [ ] Update `imagePullSecrets` names in environment values
- [ ] Update ingress `host` in environment values
- [ ] Update `namespace` in `helios/env-config.yml`
- [ ] Update `VAULT_PATH` in `helios/deploy.sh`

## 🛠️ Common Commands

### Helm Operations
```bash
# Lint
helm lint ./helm/

# Template DEV
helm template memory-store ./helm/ \
  --values ./helm/environments/dev/values.yaml

# Install DEV
helm install memory-store ./helm/ \
  --values ./helm/environments/dev/values.yaml \
  --namespace isa0-dev \
  --create-namespace

# Upgrade DEV
helm upgrade memory-store ./helm/ \
  --values ./helm/environments/dev/values.yaml \
  --namespace isa0-dev

# Rollback
helm rollback memory-store --namespace isa0-dev

# Uninstall
helm uninstall memory-store --namespace isa0-dev

# View history
helm history memory-store --namespace isa0-dev

# Get values
helm get values memory-store --namespace isa0-dev
```

### Kubernetes Operations
```bash
# Get all resources
kubectl get all -n isa0-dev

# Get pods
kubectl get pods -l app.kubernetes.io/name=memory-store -n isa0-dev

# View logs
kubectl logs -f deployment/memory-store -n isa0-dev

# Describe deployment
kubectl describe deployment memory-store -n isa0-dev

# Port forward
kubectl port-forward svc/memory-store 8000:80 -n isa0-dev

# Exec into pod
kubectl exec -it <pod-name> -n isa0-dev -- /bin/bash

# Check HPA
kubectl get hpa memory-store -n isa0-dev

# Check ingress
kubectl get ingress memory-store -n isa0-dev

# Check ConfigMap
kubectl get configmap memory-store-cfgmap -n isa0-dev -o yaml
```

### Docker Operations
```bash
# Build corporate image
docker build -f deployments/Dockerfile.corporate \
  -t docker-isa0-dev.artifactory.fg.rbc.com/isa0-memory-store:0.1.0 .

# Push to Artifactory
docker push docker-isa0-dev.artifactory.fg.rbc.com/isa0-memory-store:0.1.0
```

## 🔍 Troubleshooting

### Check Deployment Status
```bash
# Overall status
kubectl rollout status deployment/memory-store -n isa0-dev

# Pod details
kubectl describe pod <pod-name> -n isa0-dev

# View events
kubectl get events -n isa0-dev --sort-by='.lastTimestamp'
```

### Check Dependencies
```bash
# Qdrant
kubectl get pod -l app.kubernetes.io/name=memory-store-qdrant -n isa0-dev

# Memgraph (if enabled)
kubectl get pod -l app.kubernetes.io/name=memory-store-memgraph -n isa0-dev
```

### Test Connectivity
```bash
# Health check
curl https://mem0.cfk.devfg.rbc.com/health

# Or via port-forward
kubectl port-forward svc/memory-store 8000:80 -n isa0-dev
curl http://localhost:8000/health
```

### View Configuration
```bash
# Get ConfigMap
kubectl get configmap memory-store-cfgmap -n isa0-dev -o yaml

# Get secrets (if any)
kubectl get secrets -n isa0-dev
```

## 📊 Verification Checklist

After deployment:

- [ ] All pods are running
- [ ] Health endpoint returns 200
- [ ] Qdrant pod is healthy
- [ ] Memgraph pod is healthy (if enabled)
- [ ] HPA is created (if enabled)
- [ ] Ingress is configured
- [ ] API docs accessible: `/docs`
- [ ] Can add a test memory
- [ ] Can search memories

## 🔗 Quick Links

- **Full Deployment Guide**: [docs/CORPORATE_DEPLOYMENT.md](docs/CORPORATE_DEPLOYMENT.md)
- **User Guide**: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- **Integration Guide**: [docs/INTEGRATION.md](docs/INTEGRATION.md)
- **Helios Docs**: https://rbcgithub.fg.rbc.com/pages/rbc-to/a0d0-helios-docs

## 💡 Pro Tips

1. **Always lint before deploying**: `make helm-lint`
2. **Test templates locally first**: `make helm-template-dev`
3. **Use Makefile targets**: They handle the complexity
4. **Check Vault secrets exist** before deploying
5. **Review ConfigMap** after deployment for correctness
6. **Monitor logs** during initial rollout
7. **Use port-forward** for local testing before exposing via ingress

## 🆘 Getting Help

1. Check logs: `kubectl logs -f deployment/memory-store -n isa0-dev`
2. Describe resources: `kubectl describe deployment memory-store -n isa0-dev`
3. Check events: `kubectl get events -n isa0-dev`
4. Review docs: [docs/CORPORATE_DEPLOYMENT.md](docs/CORPORATE_DEPLOYMENT.md)
5. Contact ChainServer team

---

**Version**: 0.1.0  
**Last Updated**: 2026-01-14
