# REST API MCP Server Pattern

This document describes the pattern for building MCP servers that wrap **backend REST APIs** (not databases).

## When to Use This Pattern

✅ Use REST API pattern for:
- Corporate REST APIs
- Microservices
- HTTP-based services
- Third-party APIs (Salesforce, ServiceNow, etc.)
- GraphQL endpoints

❌ Don't use for:
- SQL databases → Use LangChain SQLDatabaseToolkit pattern instead

## Architecture

```
LLM Client
    ↓ MCP Protocol
MCP Tools (FastMCP)
    ↓ Cache Check
Redis Cache
    ↓ If miss
HTTP Client Pool (httpx AsyncClient)
    ↓ Parallel execution (asyncio.gather)
Backend REST APIs
```

## Key Components

### 1. API Client Layer (`app/resources/`)
- **httpx AsyncClient** with connection pooling
- Per-API timeout configuration
- Shared client for connection reuse
- Basic Auth / Bearer Token support

### 2. Tools Layer (`app/tools/`)
- MCP tools that orchestrate API calls
- Input validation
- Error handling
- Response formatting

### 3. Processors (Optional) (`app/processors/`)
- Transform raw API responses
- Business logic
- Data aggregation
- Format for LLM consumption

### 4. Configuration (`app/config.py`)
- API endpoint URLs
- Authentication tokens
- Cache TTLs
- Timeout settings

---

## Implementation Pattern

### Step 1: API Client

```python
# app/resources/{service}_apis.py
import httpx
from typing import Dict, Any, Optional

# Per-API timeouts
API_TIMEOUTS = {
    "get_clients": httpx.Timeout(10.0, connect=5.0),
    "get_revenue": httpx.Timeout(15.0, connect=5.0),
    "get_coverage": httpx.Timeout(30.0, connect=10.0),  # Slow API
}

# Shared HTTP client (connection pooling)
_http_client: Optional[httpx.AsyncClient] = None

async def get_http_client() -> httpx.AsyncClient:
    """Get or create shared HTTP client"""
    global _http_client
    
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            verify=False,  # Or True for production
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(
                max_keepalive_connections=50,   # Reuse connections
                max_connections=100,
                keepalive_expiry=30.0
            ),
            follow_redirects=True
        )
    
    return _http_client

async def close_http_client():
    """Close shared client"""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


# API Functions
async def get_client_data(
    client_id: str,
    employee_id: int,
    currency: str = "USD"
) -> Dict[str, Any]:
    """Call backend API to get client data"""
    url = f"{config.API_BASE_URL}/api/clients/{client_id}"
    
    headers = {
        "Authorization": f"Bearer {config.API_TOKEN}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "employeeId": employee_id,
        "currency": currency
    }
    
    try:
        client = await get_http_client()
        response = await client.post(
            url,
            headers=headers,
            json=payload,
            timeout=API_TIMEOUTS["get_clients"]
        )
        response.raise_for_status()
        return response.json()
        
    except httpx.TimeoutException:
        return {"status": "error", "message": "Request timed out"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "message": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

### Step 2: MCP Tools

```python
# app/tools/{service}_tools.py
from app.mcp_singleton import get_mcp_instance
from app.resources import {service}_apis
from app.utils.cache import cache
from app.config import config

mcp = get_mcp_instance()

@mcp.tool()
async def get_client_overview(client_id: str, employee_id: int, currency: str = "USD") -> str:
    """
    Get comprehensive client overview from backend API.
    
    Args:
        client_id: Client identifier
        employee_id: Employee ID for authorization
        currency: Currency code (USD, CAD, etc.)
    
    Returns:
        Client overview data
    """
    try:
        # Check cache
        cache_key = cache._generate_key("client_overview", client_id, currency)
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        # Call API
        result = await {service}_apis.get_client_data(client_id, employee_id, currency)
        
        if result.get("status") == "error":
            return f"Error: {result.get('message')}"
        
        # Cache result
        cache.set(cache_key, result, config.CACHE_TTL_CLIENT_DATA)
        
        return result
        
    except Exception as e:
        return f"Error: {str(e)}"
```

### Step 3: Orchestrator (Optional, for Complex APIs)

```python
# app/tools/orchestrator.py
import asyncio
from typing import Dict, List, Any

class APIOrchestrator:
    """Orchestrate multiple API calls in parallel"""
    
    async def get_comprehensive_data(
        self,
        client_id: str,
        employee_id: int,
        apis: List[str]
    ) -> Dict[str, Any]:
        """Execute multiple APIs in parallel"""
        
        tasks = []
        if "revenue" in apis:
            tasks.append(self._get_revenue(client_id, employee_id))
        if "contacts" in apis:
            tasks.append(self._get_contacts(client_id, employee_id))
        if "coverage" in apis:
            tasks.append(self._get_coverage(client_id, employee_id))
        
        # Run all APIs in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results
        output = {}
        for i, api_name in enumerate(apis):
            if isinstance(results[i], Exception):
                output[api_name] = {"status": "error", "message": str(results[i])}
            else:
                output[api_name] = results[i]
        
        return output
```

### Step 4: Configuration

```python
# app/config.py
class Config:
    # API Endpoints
    API_BASE_URL: str = os.getenv("API_BASE_URL", "")
    API_TOKEN: str = os.getenv("API_TOKEN", "")
    
    # Secondary APIs
    CLIENT_SERVICE_URL: str = os.getenv("CLIENT_SERVICE_URL", "")
    COVERAGE_SERVICE_URL: str = os.getenv("COVERAGE_SERVICE_URL", "")
    
    # Cache TTLs
    CACHE_TTL_CLIENT_DATA: int = 300  # 5 minutes
    CACHE_TTL_CLIENT_LIST: int = 3600  # 1 hour
    CACHE_TTL_STATIC_DATA: int = 7200  # 2 hours
    
    @classmethod
    def validate_required_config(cls) -> list[str]:
        missing = []
        if not cls.API_BASE_URL:
            missing.append("API_BASE_URL")
        if not cls.API_TOKEN:
            missing.append("API_TOKEN")
        return missing
```

---

## Best Practices

### 1. Connection Pooling
✅ Use shared httpx.AsyncClient
✅ Configure keepalive connections (50+)
✅ Set max_connections appropriately (100)

### 2. Timeouts
✅ Per-API timeout configuration
✅ Fast APIs: 10-15 seconds
✅ Slow APIs: 30-45 seconds
✅ Always set connect timeout

### 3. Error Handling
✅ Catch httpx.TimeoutException
✅ Catch httpx.HTTPStatusError
✅ Return structured error responses
✅ Log errors for debugging

### 4. Caching
✅ Cache frequently accessed data
✅ Use appropriate TTLs:
   - Static data: 1-2 hours
   - Dynamic data: 5-15 minutes
   - Real-time data: No cache
✅ Provide cache_clear tool

### 5. Parallel Execution
✅ Use asyncio.gather for independent APIs
✅ Set return_exceptions=True
✅ Handle partial failures gracefully

### 6. Authentication
✅ Store tokens in environment variables
✅ Support multiple auth methods:
   - Bearer tokens
   - Basic auth
   - API keys
   - OAuth
✅ Never hardcode credentials

---

## Comparison: SQL vs REST API Patterns

| Aspect | SQL Pattern | REST API Pattern |
|--------|-------------|------------------|
| **Use Case** | Databases | HTTP services |
| **Client** | SQLAlchemy + LangChain | httpx AsyncClient |
| **Tools** | LangChain wrapped | Custom FastMCP tools |
| **Queries** | SQL queries | HTTP requests |
| **Caching** | Query results | API responses |
| **Parallelization** | N/A (single DB) | asyncio.gather |
| **Connection** | DB connection pool | HTTP connection pool |
| **Timeout** | Query timeout | Per-API timeouts |

---

## Example: Complete REST API MCP Server

See CF (Client-First) project for real-world example:
- `/Users/rameshpilli/Developer/CF copy/`
- 16 backend APIs
- Orchestrator pattern
- Parallel execution
- Connection pooling
- Per-API timeouts
- Redis caching

---

## Summary

**REST API Pattern = Best for HTTP-based services:**
- httpx AsyncClient with connection pooling
- Per-API timeout configuration
- Parallel execution with asyncio.gather
- Redis caching layer
- Graceful error handling
- MCP protocol wrapper

**Use this pattern when wrapping REST APIs, not databases!**
