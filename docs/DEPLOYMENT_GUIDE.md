# Databricks SQL MCP Server - Deployment Guide

This guide walks you through deploying the Databricks SQL MCP Server to your corporate Kubernetes environment using Helios.

## Prerequisites

- Access to RBC Helios deployment platform
- Databricks workspace with SQL warehouse
- Vault access for storing secrets
- Docker registry access (Artifactory)
- Kubernetes namespace provisioned

## Deployment Overview

```
1. Prepare Databricks credentials
2. Store secrets in Vault
3. Build and push Docker image
4. Configure Helm values per environment
5. Deploy using Helios
6. Verify deployment
```

## Step 1: Prepare Databricks Credentials

### Get SQL Warehouse ID

1. Log into your Databricks workspace
2. Navigate to SQL Warehouses
3. Click on your warehouse
4. Copy the warehouse ID from the URL or settings

### Generate Personal Access Token

1. User Settings → Developer → Access Tokens
2. Generate new token
3. Save token securely (you won't see it again)

### Determine Catalog and Schema

```sql
-- In Databricks SQL editor
SHOW CATALOGS;
SHOW SCHEMAS IN <catalog_name>;
```

## Step 2: Store Secrets in Vault

Secrets should be stored in Vault at path: `appcodes/<APPCODE>/<ENV>/DATABRICKS-SQL-MCP`

### Using Vault CLI

```bash
# Set environment
export VAULT_ADDR="https://vault.fg.rbc.com"
export VAULT_TOKEN="your_vault_token"

# Store secrets for DEV
vault write appcodes/ISA0/DEV/DATABRICKS-SQL-MCP \
  DATABRICKS_HOST="your-workspace.cloud.databricks.com" \
  DATABRICKS_TOKEN="dapi_your_token_here" \
  DATABRICKS_SQL_WAREHOUSE_ID="your_warehouse_id" \
  DATABRICKS_CATALOG="main" \
  DATABRICKS_SCHEMA="default" \
  AUTH_SERVER_SECRET="your_jwt_secret_here"

# Store secrets for QAT/SAI
vault write appcodes/ISA0/SAI/DATABRICKS-SQL-MCP \
  DATABRICKS_HOST="your-workspace.cloud.databricks.com" \
  DATABRICKS_TOKEN="dapi_your_token_here" \
  DATABRICKS_SQL_WAREHOUSE_ID="your_warehouse_id" \
  DATABRICKS_CATALOG="main" \
  DATABRICKS_SCHEMA="default" \
  AUTH_SERVER_SECRET="your_jwt_secret_here"

# Store secrets for PROD
vault write appcodes/ISA0/PROD/DATABRICKS-SQL-MCP \
  DATABRICKS_HOST="your-workspace.cloud.databricks.com" \
  DATABRICKS_TOKEN="dapi_your_token_here" \
  DATABRICKS_SQL_WAREHOUSE_ID="your_warehouse_id" \
  DATABRICKS_CATALOG="main" \
  DATABRICKS_SCHEMA="default" \
  AUTH_SERVER_SECRET="your_jwt_secret_here"
```

### Using Vault UI

1. Navigate to `https://vault.fg.rbc.com`
2. Authenticate
3. Navigate to: `appcodes/<APPCODE>/<ENV>/DATABRICKS-SQL-MCP`
4. Add key-value pairs for each secret

## Step 3: Build and Push Docker Image

### Update Configuration

1. **Update `helm/values.yaml`:**
```yaml
rbc:
  appCode: isa0  # Your app code
  
image:
  name: isa0-dbx-sql-mcp  # Your image name
  artifactoryRepo: docker-isa0-dev  # Your Artifactory repo
```

2. **Update `helios/env-config.yml`:**
```yaml
compute-fabric:
  environments:
    - name: dev
      ucp:
        cluster: ucpdev01.fg.rbc.com
        namespace: isa0-dev  # Your namespace
```

### Build Image

```bash
# Login to Artifactory
docker login docker-isa0-dev.artifactory.fg.rbc.com

# Build image
docker build -t docker-isa0-dev.artifactory.fg.rbc.com/isa0-dbx-sql-mcp:0.1.0 .

# Push image
docker push docker-isa0-dev.artifactory.fg.rbc.com/isa0-dbx-sql-mcp:0.1.0
```

## Step 4: Configure Environment-Specific Values

### Development (`helm/environments/dev/values.yaml`)

```yaml
replicaCount: 1

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 250m
    memory: 256Mi

configuration:
  LOG_LEVEL: "DEBUG"
  DEVELOPMENT: "true"
  MAX_QUERY_ROWS: "1000"
  
  # Cache settings
  ENABLE_CACHING: "true"
  CACHE_TTL_TABLES_LIST: "1800"
  CACHE_TTL_TABLE_SCHEMA: "3600"
  CACHE_TTL_QUERY_RESULTS: "180"
```

### QAT (`helm/environments/qat/values.yaml`)

```yaml
replicaCount: 2

resources:
  limits:
    cpu: 1500m
    memory: 1.5Gi
  requests:
    cpu: 500m
    memory: 512Mi

configuration:
  LOG_LEVEL: "INFO"
  DEVELOPMENT: "false"
  MAX_QUERY_ROWS: "1000"
  
  ENABLE_CACHING: "true"
  CACHE_TTL_TABLES_LIST: "3600"
  CACHE_TTL_TABLE_SCHEMA: "7200"
  CACHE_TTL_QUERY_RESULTS: "300"
```

### Production (`helm/environments/prod/values.yaml`)

```yaml
replicaCount: 3

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

resources:
  limits:
    cpu: 2000m
    memory: 2Gi
  requests:
    cpu: 1000m
    memory: 1Gi

configuration:
  LOG_LEVEL: "INFO"
  DEVELOPMENT: "false"
  MAX_QUERY_ROWS: "1000"
  
  ENABLE_CACHING: "true"
  CACHE_TTL_TABLES_LIST: "7200"
  CACHE_TTL_TABLE_SCHEMA: "14400"
  CACHE_TTL_QUERY_RESULTS: "600"

ingress:
  enabled: true
  className: "nginx"
  hosts:
    - host: dbx-sql-mcp.your-domain.com
      paths:
        - path: /
          pathType: Prefix
```

## Step 5: Deploy Using Helios

### Deploy to Development

```bash
# From project root
helios deploy --environment dev

# Monitor deployment
kubectl get pods -n isa0-dev -w
```

### Deploy to QAT

```bash
helios deploy --environment qat

kubectl get pods -n isa0-qat -w
```

### Deploy to Production

```bash
# Ensure you're on a protected branch
helios deploy --environment prod

kubectl get pods -n isa0-prod -w
```

## Step 6: Verify Deployment

### Check Pod Status

```bash
export NAMESPACE="isa0-dev"  # or qat, prod

# Check pods
kubectl get pods -n $NAMESPACE

# Check specific deployment
kubectl get deployment dbx-sql-mcp -n $NAMESPACE

# Check logs
kubectl logs -f deployment/dbx-sql-mcp -n $NAMESPACE
```

### Test Health Endpoint

```bash
# Port forward
kubectl port-forward -n $NAMESPACE deployment/dbx-sql-mcp 8000:8000

# Test health
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","database":"connected","cache":"enabled"}
```

### Verify Redis

```bash
POD_NAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=dbx-sql-mcp -o jsonpath='{.items[0].metadata.name}')

# Test Redis
kubectl exec -n $NAMESPACE $POD_NAME -- redis-cli PING

# Check Redis stats
kubectl exec -n $NAMESPACE $POD_NAME -- redis-cli INFO stats
```

### Test MCP Tools

```bash
# Using MCP client or test script
# This would typically be done through Claude Desktop or another MCP client

# Example test queries (execute through MCP client):
1. databricks_list_tables()
2. databricks_get_schema(table_names="your_table")
3. databricks_execute_query(query="SELECT COUNT(*) FROM your_table LIMIT 10")
```

## Troubleshooting

### Pod Not Starting

```bash
# Describe pod for events
kubectl describe pod $POD_NAME -n $NAMESPACE

# Check logs
kubectl logs $POD_NAME -n $NAMESPACE

# Common issues:
# - Image pull errors: Check Artifactory credentials
# - ConfigMap errors: Check Vault secrets retrieval
# - Crash loop: Check application logs for startup errors
```

### Database Connection Issues

```bash
# Check environment variables
kubectl exec -n $NAMESPACE $POD_NAME -- env | grep DATABRICKS

# Test connection from pod
kubectl exec -n $NAMESPACE $POD_NAME -- python3 -c "
from app.db.connector import db_connector
print('Testing connection...')
result = db_connector.test_connection()
print(f'Connection: {'SUCCESS' if result else 'FAILED'}')
"
```

### Redis Connection Issues

```bash
# Check Redis process
kubectl exec -n $NAMESPACE $POD_NAME -- ps aux | grep redis

# Check Redis connectivity
kubectl exec -n $NAMESPACE $POD_NAME -- redis-cli PING

# Restart Redis
kubectl exec -n $NAMESPACE $POD_NAME -- redis-server --daemonize yes
```

### Configuration Issues

```bash
# Check ConfigMap
kubectl get configmap dbx-sql-mcp-cfgmap -n $NAMESPACE -o yaml

# Update ConfigMap (if needed)
kubectl edit configmap dbx-sql-mcp-cfgmap -n $NAMESPACE

# Restart pods to pick up changes
kubectl rollout restart deployment/dbx-sql-mcp -n $NAMESPACE
```

## Monitoring

### Check HPA (Production)

```bash
kubectl get hpa dbx-sql-mcp -n $NAMESPACE
kubectl describe hpa dbx-sql-mcp -n $NAMESPACE
```

### View Metrics

```bash
# CPU and memory usage
kubectl top pod -n $NAMESPACE -l app.kubernetes.io/name=dbx-sql-mcp

# Cache statistics (via MCP tool)
databricks_cache_stats()
```

### Set Up Alerts

Configure alerts for:
- Pod restart count
- High memory/CPU usage
- Database connection failures
- High error rates in logs

## Rollback

```bash
# View deployment history
helm history dbx-sql-mcp -n $NAMESPACE

# Rollback to previous version
helm rollback dbx-sql-mcp -n $NAMESPACE

# Rollback to specific revision
helm rollback dbx-sql-mcp 2 -n $NAMESPACE
```

## Scaling

### Manual Scaling

```bash
# Scale up
kubectl scale deployment dbx-sql-mcp --replicas=5 -n $NAMESPACE

# Scale down
kubectl scale deployment dbx-sql-mcp --replicas=2 -n $NAMESPACE
```

### Auto-scaling (Production)

Configured via `helm/environments/prod/values.yaml`:

```yaml
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

## Maintenance

### Update Secrets

```bash
# Update in Vault
vault write appcodes/ISA0/DEV/DATABRICKS-SQL-MCP \
  DATABRICKS_TOKEN="new_token"

# Redeploy to pick up new secrets
helios deploy --environment dev
```

### Update Configuration

```bash
# Edit values
vim helm/environments/dev/values.yaml

# Redeploy
helios deploy --environment dev
```

### Clear Caches

```bash
# Via MCP tool
databricks_clear_cache()

# Or via Redis CLI
kubectl exec -n $NAMESPACE $POD_NAME -- redis-cli FLUSHDB
```

## Best Practices

1. **Always test in DEV first** before deploying to higher environments
2. **Use Vault for all secrets** - never hardcode credentials
3. **Monitor cache hit rates** and adjust TTLs accordingly
4. **Set appropriate resource limits** based on actual usage
5. **Enable HPA in production** for automatic scaling
6. **Use separate Databricks tokens** for each environment
7. **Implement proper logging** and alerting
8. **Regular security updates** for dependencies
9. **Document any environment-specific configuration**
10. **Test rollback procedures** regularly

## Support

For issues during deployment:
- Check application logs
- Review Kubernetes events
- Contact Platform Engineering team
- Refer to troubleshooting section above
