# MCP Server Shared Components

This folder contains **reusable components** used by both SQL database and REST API MCP server skills.

## What's Shared

These components work for **both** SQL and REST API MCP servers:

| Component | Purpose | Reusable? |
|-----------|---------|-----------|
| `auth_templates/` | JWT authentication | ✅ Yes, copy as-is |
| `utils_templates/` | Redis caching + diagnostics | ✅ Yes, copy as-is |
| `helm_templates/` | Complete K8s deployment | ✅ Yes, update values only |
| `Dockerfile_template` | Container with Redis sidecar | ✅ Yes, copy as-is |
| `main_template.py` | FastMCP application setup | ⚠️  Update tool imports |

## How to Use

### For SQL Database MCP Servers

```bash
# Copy shared components
cp -r ../mcp-server-shared/auth_templates app/auth/
cp -r ../mcp-server-shared/utils_templates app/utils/
cp -r ../mcp-server-shared/helm_templates helm/
cp ../mcp-server-shared/Dockerfile_template Dockerfile
cp ../mcp-server-shared/main_template.py app/main.py

# Update main.py to import SQL tools
sed -i 's/PLACEHOLDER_TOOLS_IMPORT/from app.tools import databricks_tools/' app/main.py
```

### For REST API MCP Servers

```bash
# Copy shared components
cp -r ../mcp-server-shared/auth_templates app/auth/
cp -r ../mcp-server-shared/utils_templates app/utils/
cp -r ../mcp-server-shared/helm_templates helm/
cp ../mcp-server-shared/Dockerfile_template Dockerfile
cp ../mcp-server-shared/main_template.py app/main.py

# Update main.py to import API tools
sed -i 's/PLACEHOLDER_TOOLS_IMPORT/from app.tools import client360_tools, orchestrator/' app/main.py
```

## Component Details

### 1. JWT Authentication (`auth_templates/`)

**Files:**
- `__init__.py`
- `auth.py` - JWT validation middleware

**Features:**
- Token validation
- User context extraction
- Optional authentication (can be disabled)

**Usage:**
```python
from app.auth import AuthBackend, AuthContextMiddleware

# In main.py
if config.AUTH_SERVER_SECRET:
    app.add_middleware(AuthContextMiddleware, backend=AuthBackend())
```

### 2. Redis Caching (`utils_templates/cache.py`)

**Features:**
- Automatic JSON serialization
- TTL support
- Cache hit/miss tracking
- Cache statistics

**Usage:**
```python
from app.utils.cache import cache

# Set with TTL
cache.set("key", value, ttl=3600)

# Get
result = cache.get("key")

# Clear
cache.clear_pattern("prefix_*")

# Stats
stats = cache.get_stats()
```

### 3. Startup Diagnostics (`utils_templates/startup_diagnostics.py`)

**Features:**
- Configuration validation
- Connection testing
- Service readiness checks
- Logging

**Usage:**
```python
from app.utils.startup_diagnostics import run_startup_diagnostics

# In main.py startup
run_startup_diagnostics()
```

### 4. Helm Charts (`helm_templates/`)

**Complete K8s deployment:**
- `Chart.yaml` - Chart metadata
- `values.yaml` - Default values
- `templates/` - K8s resources
  - `deployment.yaml` - Application deployment
  - `service.yaml` - Service exposure
  - `configmap.yaml` - Configuration
  - `serviceaccount.yaml` - Service account
  - `hpa.yaml` - Auto-scaling
  - `ingress.yaml` - Ingress rules
  - `_helpers.tpl` - Template helpers
  - `NOTES.txt` - Post-install notes
- `environments/` - Per-environment configs
  - `dev/values.yaml`
  - `qat/values.yaml`
  - `prod/values.yaml`

**Customization needed:**
- Update `values.yaml` with your app-specific config
- Update environment-specific values

### 5. Dockerfile (`Dockerfile_template`)

**Features:**
- Python 3.12 base image
- Redis server (sidecar pattern)
- UV for fast dependency installation
- Health check configuration
- Exposes ports 8000 (app) and 6379 (redis)

**Customization:**
- Usually works as-is
- May need to add system dependencies

### 6. Main Application (`main_template.py`)

**Features:**
- FastMCP setup
- Middleware configuration (Auth, CORS, GZip)
- Health check endpoints
- Graceful shutdown

**Customization needed:**
- Update tool imports
- Update tool names list
- Optional: Add custom middleware

## Configuration Pattern

All shared components use the same configuration pattern:

```python
# app/config.py
import os
from dotenv import load_dotenv

class Config:
    # Server
    MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", "8000"))
    MCP_SERVER_HOST: str = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    ENABLE_CACHING: bool = os.getenv("ENABLE_CACHING", "true").lower() == "true"
    
    # Auth (optional)
    AUTH_SERVER_SECRET: Optional[str] = os.getenv("AUTH_SERVER_SECRET")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

config = Config()
```

## Deployment Pattern

All MCP servers use the same deployment pattern:

### 1. Store Secrets in Vault
```bash
vault write appcodes/{APP_CODE}/{ENV}/{PROJECT} \
  DATABASE_TOKEN="..." \
  API_TOKEN="..." \
  AUTH_SERVER_SECRET="..."
```

### 2. Build Docker Image
```bash
docker build -t {registry}/{image}:{tag} .
docker push {registry}/{image}:{tag}
```

### 3. Deploy with Helios
```bash
cd helios
./deploy.sh --environment dev
```

### 4. Verify
```bash
kubectl get pods -n {namespace}
kubectl logs -f deployment/{chart-name}
curl http://{service-url}/health
```

## Health Checks

All MCP servers expose:

**`GET /health`** - Basic health check
```json
{
  "status": "healthy",
  "service": "{service}-mcp",
  "version": "0.1.0"
}
```

**`GET /mcp/health`** - MCP protocol health
```json
{
  "status": "ok",
  "tools_registered": 6,
  "cache_enabled": true
}
```

## Monitoring

All MCP servers include:

1. **Cache statistics**
   - Hit/miss rates
   - Memory usage
   - Key counts

2. **Health probes**
   - Liveness probe: `/health`
   - Readiness probe: `/health`

3. **Logging**
   - Structured JSON logs
   - Configurable log levels
   - Request/response logging

## Best Practices

### 1. Don't Modify Shared Components
✅ Copy as-is when possible  
✅ Only customize what's necessary  
✅ Keep shared components in sync

### 2. Use Configuration
✅ All customization via environment variables  
✅ No hardcoded values  
✅ Use .env for local, ConfigMap for K8s

### 3. Test Locally First
✅ Run with Docker Compose  
✅ Test health endpoints  
✅ Verify cache functionality  
✅ Test authentication

### 4. Follow Deployment Pattern
✅ Store secrets in Vault  
✅ Use Helios for deployment  
✅ Deploy to dev first  
✅ Monitor for 24 hours before promoting

## Directory Structure

```
mcp-server-shared/
├── README.md (this file)
├── auth_templates/
│   ├── __init__.py
│   └── auth.py
├── utils_templates/
│   ├── __init__.py
│   ├── cache.py
│   └── startup_diagnostics.py
├── helm_templates/
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── templates/
│   │   ├── _helpers.tpl
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   ├── serviceaccount.yaml
│   │   ├── hpa.yaml
│   │   ├── ingress.yaml
│   │   └── NOTES.txt
│   └── environments/
│       ├── dev/values.yaml
│       ├── qat/values.yaml
│       └── prod/values.yaml
├── Dockerfile_template
└── main_template.py
```

## Related Skills

- **SQL Database MCP**: `sql-database-mcp-skill/` - For SQL databases
- **REST API MCP**: `rest-api-mcp-skill/` - For REST APIs

---

**These components are production-ready and battle-tested. Use them for all MCP servers!**
