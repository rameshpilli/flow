---
name: rest-api-mcp
description: Generate production-ready MCP servers for REST APIs and microservices using httpx AsyncClient with connection pooling, parallel execution, and intelligent caching. Complete Kubernetes deployment included.
author: Platform Engineering
version: 1.0.0
tags:
  - mcp
  - rest-api
  - httpx
  - microservices
  - kubernetes
  - redis
  - async
---

# REST API MCP Server Generator

Generate production-ready MCP servers for **REST APIs and microservices** using **httpx AsyncClient** with connection pooling and parallel execution.

## When to Use This Skill

✅ **Use this skill for:**
- Corporate REST APIs
- Microservices (internal/external)
- Third-party APIs (Salesforce, ServiceNow, etc.)
- HTTP-based services
- GraphQL endpoints (via POST)

❌ **Don't use for:**
- SQL databases → Use `sql-database-mcp-skill` instead
- WebSocket services → Custom implementation needed

## How This Skill Works

**When user requests an MCP server for a REST API:**

1. **ASK these questions first** (don't assume!):
   - What is the service/API name?
   - What is the base URL?
   - What endpoints do you want to expose? (list them)
   - What HTTP methods? (GET, POST, PUT, DELETE)
   - What authentication type? (Bearer token, Basic auth, API Key, OAuth, None)
   - What should be cached and for how long?
   - Do you need an orchestrator for multi-API calls?
   - App code for deployment?
   - Kubernetes namespace?

2. **THEN generate based on their answers:**
   - ✅ Complete MCP server with httpx AsyncClient
   - ✅ 5-10 tools (customized for their endpoints)
   - ✅ Connection pooling (50 keepalive connections)
   - ✅ Per-API timeout configuration
   - ✅ Parallel execution (asyncio.gather)
   - ✅ Redis caching layer
   - ✅ Complete K8s deployment
   - ✅ Ready in **~15 minutes**

**IMPORTANT:** Always gather requirements first. Don't hardcode to Client360, Salesforce, or any specific API.

## Architecture

```
LLM Client (Claude/GPT)
    ↓ HTTP/MCP Protocol
MCP Tools Layer (FastMCP)
    ↓ Cache Check
Redis Cache Layer
    ↓ Parallel Execution
httpx AsyncClient Pool ← Connection pooling!
  ├─ 50 keepalive connections
  ├─ 100 max connections
  └─ Per-API timeouts
    ↓ HTTP Requests
Backend REST APIs
```

## Key Features

### 1. Connection Pooling (2.5x Faster)
```python
httpx.AsyncClient(
    limits=httpx.Limits(
        max_keepalive_connections=50,   # Reuse connections
        max_connections=100,
        keepalive_expiry=30.0
    )
)
```

### 2. Per-API Timeouts
```python
API_TIMEOUTS = {
    "get_clients": httpx.Timeout(10.0, connect=5.0),    # Fast
    "get_revenue": httpx.Timeout(15.0, connect=5.0),    # Medium
    "get_reports": httpx.Timeout(45.0, connect=10.0),   # Slow
}
```

### 3. Parallel Execution
```python
# Execute multiple APIs in parallel
results = await asyncio.gather(
    get_client_data(client_id),
    get_contacts(client_id),
    get_revenue(client_id),
    return_exceptions=True  # Graceful degradation
)
```

### 4. Multiple Auth Methods
- Bearer tokens
- Basic authentication
- API keys
- OAuth 2.0

## Tools Generated (5-10 tools)

Typical tool structure:

| Tool | Purpose | Cache TTL |
|------|---------|-----------|
| `search_{entity}` | Search/list entities | 1 hour |
| `get_{entity}_details` | Get detailed data | 5-15 min |
| `get_{entity}_aggregated` | Multi-API aggregation | 5 min |
| `orchestrator` | Execute multiple APIs (optional) | N/A |
| `clear_cache` | Cache management | N/A |
| `cache_stats` | Cache monitoring | N/A |

**Tools vary based on your API endpoints**

## Reference Files

All working code is in the `reference/` folder.

### REST API Templates

| File | Lines | Purpose |
|------|-------|---------|
| `api_client_template.py` | 1,232 | httpx AsyncClient implementation |
| `orchestrator_template.py` | 1,045 | Parallel API execution |
| `config_api_template.py` | 101 | REST API configuration |
| `README_API_PATTERN.md` | 450 | Complete REST API pattern guide |

### Shared Components

**Location:** `../mcp-server-shared/`

- `auth_templates/` - JWT authentication
- `utils_templates/` - Redis caching + diagnostics
- `helm_templates/` - Complete K8s deployment
- `Dockerfile_template` - Container with Redis
- `main_template.py` - FastMCP application

## Generation Workflow

### Step 1: Gather Information (ALWAYS DO THIS FIRST!)

**Ask the user these questions:**

1. **"What is the name of the API/service you're wrapping?"**
   - Example: "Salesforce", "GitHub", "Internal CRM", "Financial Services API"
   - This will be used for naming (e.g., `salesforce-mcp`, `github-mcp`)

2. **"What is the base URL for the API?"**
   - Example: `https://api.github.com`, `https://your-company.api.com`

3. **"What endpoints do you want to expose as MCP tools?"**
   - Ask for each endpoint:
     - Path (e.g., `/users`, `/repos/{owner}/{repo}`)
     - HTTP method (GET, POST, PUT, DELETE, PATCH)
     - Purpose/description
     - Path parameters (e.g., `{id}`, `{owner}`)
     - Query parameters (e.g., `?page=1&limit=100`)

4. **"What authentication does the API use?"**
   - Options: Bearer token, Basic auth, API Key, OAuth 2.0, Custom headers, None
   - If Bearer: Where to get the token?
   - If API Key: Header name? Query param?
   - If OAuth: Flow type?

5. **"What data should be cached?"**
   - For each endpoint, ask:
     - Should this be cached? (Yes/No)
     - If yes, for how long? (seconds)
     - Suggestions:
       - Static data: 3600-7200s (1-2 hours)
       - Dynamic data: 300-900s (5-15 minutes)
       - Real-time data: 0s (no cache)

6. **"Do you need parallel execution for multiple APIs?"**
   - If yes, will generate orchestrator
   - If no, will skip orchestrator

7. **"What is your app code for deployment?"** (e.g., `isa0`, `tb20`)

8. **"What Kubernetes namespace?"** (e.g., `isa0-dev`, `tb20-prod`)

**Store these answers and use them throughout generation. Do NOT use hardcoded examples.**

### Step 2: Read Reference Templates

```
1. Read reference/api_client_template.py (httpx implementation)
2. Read reference/orchestrator_template.py (parallel execution)
3. Read reference/config_api_template.py (API configuration)
4. Read reference/README_API_PATTERN.md (complete guide)
5. Read ../mcp-server-shared/ (reusable components)
```

### Step 3: Generate Project Structure

```
{service}-mcp/
├── app/
│   ├── auth/              # Copy from mcp-server-shared/auth_templates/
│   ├── resources/
│   │   ├── __init__.py
│   │   └── {service}_apis.py    # From api_client_template.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── {service}_tools.py   # Generated per endpoint
│   │   └── orchestrator.py      # From orchestrator_template.py (optional)
│   ├── processors/        # Optional: data transformation
│   │   └── {data}_processor.py
│   ├── utils/             # Copy from mcp-server-shared/utils_templates/
│   ├── config.py          # From config_api_template.py
│   ├── main.py            # From mcp-server-shared/main_template.py
│   └── mcp_singleton.py
├── helm/                  # Copy from mcp-server-shared/helm_templates/
├── helios/
│   ├── deploy.sh
│   └── env-config.yml
├── docs/
│   ├── DEPLOYMENT_GUIDE.md
│   └── USAGE_EXAMPLES.md
├── Dockerfile             # From mcp-server-shared/Dockerfile_template
├── pyproject.toml
└── README.md
```

### Step 4: Create API Client

In `app/resources/{service}_apis.py`:

```python
import httpx
from typing import Dict, Any, Optional

# Per-API timeouts
API_TIMEOUTS = {
    "get_clients": httpx.Timeout(10.0, connect=5.0),
    "get_client_data": httpx.Timeout(15.0, connect=5.0),
    "get_contacts": httpx.Timeout(10.0, connect=5.0),
}

# Shared HTTP client
_http_client: Optional[httpx.AsyncClient] = None

async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            verify=False,  # Or True for production
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(
                max_keepalive_connections=50,
                max_connections=100,
                keepalive_expiry=30.0
            ),
            follow_redirects=True
        )
    return _http_client

# API functions (one per endpoint)
async def get_clients(query: str = "") -> Dict[str, Any]:
    client = await get_http_client()
    response = await client.get(
        f"{config.API_BASE_URL}/clients",
        headers={"Authorization": f"Bearer {config.API_TOKEN}"},
        params={"query": query},
        timeout=API_TIMEOUTS["get_clients"]
    )
    response.raise_for_status()
    return response.json()

async def get_client_data(client_id: str) -> Dict[str, Any]:
    client = await get_http_client()
    response = await client.post(
        f"{config.API_BASE_URL}/clients/{client_id}/data",
        headers={"Authorization": f"Bearer {config.API_TOKEN}"},
        json={"include": ["revenue", "contacts"]},
        timeout=API_TIMEOUTS["get_client_data"]
    )
    response.raise_for_status()
    return response.json()
```

### Step 5: Create MCP Tools

In `app/tools/{service}_tools.py`:

```python
from app.mcp_singleton import get_mcp_instance
from app.resources import {service}_apis
from app.utils.cache import cache
from app.config import config

mcp = get_mcp_instance()

@mcp.tool()
async def search_clients(query: str) -> str:
    """Search for clients by name or ID"""
    try:
        # Check cache
        cache_key = cache._generate_key("search_clients", query)
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        # Call API
        result = await {service}_apis.get_clients(query)
        
        if result.get("status") == "error":
            return f"Error: {result.get('message')}"
        
        # Cache result
        cache.set(cache_key, result, config.CACHE_TTL_CLIENT_SEARCH)
        
        return result
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def get_client_overview(client_id: str) -> str:
    """Get comprehensive client data"""
    try:
        cache_key = cache._generate_key("client_overview", client_id)
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        result = await {service}_apis.get_client_data(client_id)
        cache.set(cache_key, result, config.CACHE_TTL_CLIENT_DATA)
        
        return result
    except Exception as e:
        return f"Error: {str(e)}"
```

### Step 6: Create Orchestrator (Optional, for Complex APIs)

In `app/tools/orchestrator.py`:

```python
import asyncio
from typing import Dict, List, Any

@mcp.tool()
async def get_comprehensive_data(client_id: str, endpoints: List[str]) -> str:
    """Execute multiple APIs in parallel"""
    try:
        tasks = []
        if "revenue" in endpoints:
            tasks.append({service}_apis.get_revenue(client_id))
        if "contacts" in endpoints:
            tasks.append({service}_apis.get_contacts(client_id))
        if "coverage" in endpoints:
            tasks.append({service}_apis.get_coverage(client_id))
        
        # Run all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results
        output = {}
        for i, endpoint in enumerate(endpoints):
            if isinstance(results[i], Exception):
                output[endpoint] = {"error": str(results[i])}
            else:
                output[endpoint] = results[i]
        
        return output
    except Exception as e:
        return f"Error: {str(e)}"
```

### Step 7: Update Dependencies

In `pyproject.toml`:

```toml
dependencies = [
  "fastmcp==2.11.3",
  "uvicorn>=0.23.2",
  "python-dotenv>=1.0.0",
  "pydantic>=2.11.0",
  "redis>=5.0.0",
  "httpx>=0.25.0",          # HTTP client with connection pooling
  "aiohttp>=3.8.6",         # Optional: alternative HTTP client
  "PyJWT>=2.8.0",
  "rbc-security==2.3.0",
]
```

### Step 8: Generate Configuration

#### `.env` Example:
```bash
# API Configuration
API_BASE_URL=https://api.yourservice.com
API_TOKEN=your_bearer_token

# Secondary APIs (if multiple services)
CLIENT_SERVICE_URL=https://clients.api.com
REVENUE_SERVICE_URL=https://revenue.api.com
COVERAGE_SERVICE_URL=https://coverage.api.com

# Server
MCP_SERVER_PORT=8000

# Redis Cache
REDIS_HOST=localhost
REDIS_PORT=6379
ENABLE_CACHING=true
CACHE_TTL_CLIENT_SEARCH=3600     # 1 hour (rarely changes)
CACHE_TTL_CLIENT_DATA=300        # 5 minutes (frequently updated)
CACHE_TTL_STATIC_DATA=7200       # 2 hours (very stable)

# Auth (optional)
AUTH_SERVER_SECRET=your_secret

# Logging
LOG_LEVEL=INFO
```

#### `helm/values.yaml`:
```yaml
rbc:
  appCode: {app_code}

image:
  name: {app_code}-{service}-mcp
  tag: 0.1.0
  artifactoryRepo: docker-{app_code}-dev

configuration:
  API_BASE_URL: "https://api.yourservice.com"
  API_TOKEN: ""  # From Vault
  
  MCP_SERVER_PORT: "8000"
  
  REDIS_HOST: "localhost"
  ENABLE_CACHING: "true"
  CACHE_TTL_CLIENT_SEARCH: "3600"
  CACHE_TTL_CLIENT_DATA: "300"
  
  LOG_LEVEL: "INFO"

resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "1000m"

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
```

## Example Conversations

### Example 1: User Doesn't Specify Details

**User:** "Create an MCP server for my API"

**Claude (YOU):** "I'll help you create an MCP server for your REST API. First, I need some information:

1. What is the name of the API/service? (e.g., 'GitHub', 'Salesforce', 'Internal CRM')
2. What is the base URL? (e.g., 'https://api.github.com')
3. What endpoints do you want to expose? (Please list them with HTTP methods)
4. What authentication does the API use?
5. What should be cached and for how long?
6. Do you need parallel execution for multiple APIs?
7. What app code for deployment?
8. What Kubernetes namespace?"

**Then generate based on answers.**

### Example 2: User Provides Some Details

**User:** "Create an MCP server for GitHub API"

**Claude (YOU):** "Great! I'll create a GitHub MCP server. I need more details:

1. ✓ Service name: GitHub
2. Base URL? (Is it 'https://api.github.com' or GitHub Enterprise?)
3. Which endpoints? For example:
   - GET /repos/{owner}/{repo} - Get repository info?
   - GET /users/{username} - Get user info?
   - GET /issues - List issues?
   - Others?
4. Authentication: Personal access token? OAuth app? GitHub App?
5. Caching preferences for each endpoint?
6. App code and namespace for deployment?"

**Wait for answers, then generate.**

### Example 3: User Provides Complete Details

**User:** "Create MCP server for 'WeatherAPI' at https://api.weather.com/v1 with endpoints: GET /current/{city} (cache 15min), GET /forecast/{city} (cache 1hour), POST /alerts/subscribe. Auth: API key in header 'X-API-Key'. App code 'wx01', namespace 'wx01-prod'"

**Claude (YOU):** "Perfect! I have all the details. Generating WeatherAPI MCP server with:
- Base URL: https://api.weather.com/v1
- Endpoints:
  * GET /current/{city} - cache 900s
  * GET /forecast/{city} - cache 3600s
  * POST /alerts/subscribe - no cache
- Auth: API Key header 'X-API-Key'
- App code: wx01
- Namespace: wx01-prod

[Proceed with generation using THESE values, not examples]"

## Success Criteria

Generated server must have:

- ✅ 5-10 MCP tools (endpoint-specific)
- ✅ httpx AsyncClient with connection pooling
- ✅ Per-API timeout configuration
- ✅ Redis caching (appropriate TTLs)
- ✅ Error handling (HTTP errors, timeouts)
- ✅ Complete K8s deployment
- ✅ Health check endpoints
- ✅ Comprehensive documentation
- ✅ Graceful degradation (partial failures)

## Testing

### Local Testing:
```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r pyproject.toml

# Configure
cp .env.example .env
# Edit .env with API credentials

# Run Redis
redis-server &

# Run server
python -m app.main

# Test
curl http://localhost:8000/health
```

### Deployment:
```bash
# Store secrets
vault write appcodes/{APPCODE}/{ENV}/{PROJECT} \
  API_TOKEN="..." \
  AUTH_SERVER_SECRET="..."

# Build and push
docker build -t {registry}/{image}:{tag} .
docker push {registry}/{image}:{tag}

# Deploy
cd helios
./deploy.sh --environment dev

# Verify
kubectl get pods -n {namespace}
```

## Reference Project

**Location:** `/Users/rameshpilli/Developer/CF copy/`

- Client-First MCP Server
- 16 backend REST APIs
- httpx AsyncClient with connection pooling
- Orchestrator with parallel execution
- 11 tools
- Production-ready

## Time Savings

- **Manual creation**: ~6 hours
- **With this skill**: ~15 minutes
- **Savings**: 96%

## Best Practices

### 1. Connection Pooling
✅ Always use shared httpx.AsyncClient  
✅ Configure 50+ keepalive connections  
✅ Set appropriate max_connections (100)

### 2. Timeouts
✅ Per-API timeout configuration  
✅ Fast APIs: 10-15 seconds  
✅ Slow APIs: 30-45 seconds  
✅ Always set connect timeout (5-10s)

### 3. Error Handling
✅ Catch httpx.TimeoutException  
✅ Catch httpx.HTTPStatusError  
✅ Return structured error responses  
✅ Log for debugging

### 4. Caching
✅ Cache frequently accessed data  
✅ Static data: 1-2 hours  
✅ Dynamic data: 5-15 minutes  
✅ Provide cache_clear tool

### 5. Parallel Execution
✅ Use asyncio.gather for independent APIs  
✅ Set return_exceptions=True  
✅ Handle partial failures gracefully

## Related Skills

- **SQL Database MCP**: Use `sql-database-mcp-skill` for SQL databases
- **Shared Components**: See `mcp-server-shared/` for reusable parts

---

**Ready to generate a REST API MCP server?**

Just say: "Create an MCP server for [Service] API at [Base URL] with endpoints: [list]"
