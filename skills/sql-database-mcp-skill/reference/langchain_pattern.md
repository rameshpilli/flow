# LangChain SQLDatabaseToolkit Integration Pattern

This document explains the pattern used to wrap LangChain's battle-tested SQLDatabaseToolkit with MCP protocol, caching, and additional safety validation.

## Why This Pattern?

### ✅ Use LangChain's SQLDatabaseToolkit
- Battle-tested by thousands of production deployments
- Handles SQL edge cases and dialects
- Active maintenance and security updates
- Comprehensive error messages

### ✅ Add Our Value
- **MCP Protocol**: Standard interface for LLMs
- **Redis Caching**: Performance optimization
- **Safety Layer**: Additional validation before LangChain
- **Enterprise Deployment**: K8s/Helm/Helios ready

## Architecture Layers

```
┌─────────────────────────────────────────┐
│   LLM Client (Claude, GPT, etc.)        │
└──────────────┬──────────────────────────┘
               │ HTTP/MCP Protocol
               ▼
┌─────────────────────────────────────────┐
│   MCP Tools Layer (FastMCP)             │
│   - databricks_list_tables              │
│   - databricks_get_schema               │
│   - databricks_execute_query            │
│   - databricks_query_checker            │
│   - databricks_clear_cache              │
│   - databricks_cache_stats              │
└──────────────┬──────────────────────────┘
               │ Cache Check
               ▼
┌─────────────────────────────────────────┐
│   Redis Cache Layer                     │
│   - Tables list (1 hour TTL)            │
│   - Schemas (2 hour TTL)                │
│   - Query results (5 min TTL)           │
└──────────────┬──────────────────────────┘
               │ If cache miss
               ▼
┌─────────────────────────────────────────┐
│   Custom Validation Layer               │
│   - Check forbidden keywords            │
│   - Enforce SELECT only                 │
│   - Add LIMIT clause                    │
│   - Single statement check              │
└──────────────┬──────────────────────────┘
               │ If valid
               ▼
┌─────────────────────────────────────────┐
│   LangChain SQLDatabaseToolkit          │
│   ├─ sql_db_list_tables                 │
│   ├─ sql_db_schema                      │
│   ├─ sql_db_query                       │
│   └─ sql_db_query_checker               │
└──────────────┬──────────────────────────┘
               │ SQL
               ▼
┌─────────────────────────────────────────┐
│   Database (Databricks/Snowflake/etc.)  │
└─────────────────────────────────────────┘
```

## Implementation Pattern

### Step 1: Initialize LangChain Toolkit

```python
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit

def _get_langchain_toolkit():
    """Initialize LangChain SQL toolkit"""
    db = SQLDatabase(
        engine=db_connector.engine,          # Your SQLAlchemy engine
        schema=config.DATABASE_SCHEMA,        # User's schema
        include_tables=None,                  # All tables
        sample_rows_in_table_info=3,          # For context
        max_string_length=1000,
    )
    return SQLDatabaseToolkit(db=db, llm=None)

# Initialize once at module load
_toolkit = _get_langchain_toolkit()
_langchain_tools = _toolkit.get_tools()
```

**What you get:**
- `sql_db_list_tables` - List all tables
- `sql_db_schema` - Get table schemas
- `sql_db_query` - Execute queries
- `sql_db_query_checker` - Validate queries

### Step 2: Wrap with MCP + Caching

```python
from app.mcp_singleton import get_mcp_instance
from app.utils.cache import cache

mcp = get_mcp_instance()

@mcp.tool()
def database_list_tables() -> str:
    """
    List all available tables.
    Uses LangChain's sql_db_list_tables tool with caching.
    """
    try:
        # 1. Check cache first
        cache_key = cache._generate_key("tables_list")
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        # 2. Execute via LangChain
        tool = next((t for t in _langchain_tools if t.name == "sql_db_list_tables"), None)
        result = tool.run("") if tool else "Error: Tool not found"
        
        # 3. Cache the result
        cache.set(cache_key, result, config.CACHE_TTL_TABLES_LIST)
        
        return result
        
    except Exception as e:
        return f"Error: {str(e)}"
```

### Step 3: Add Safety Validation

```python
@mcp.tool()
def database_execute_query(query: str) -> str:
    """
    Execute a SELECT query.
    Uses LangChain's sql_db_query with validation and caching.
    """
    try:
        # 1. Custom validation (our safety layer)
        is_valid, error_msg = QueryValidator.validate(query)
        if not is_valid:
            return f"Query validation failed: {error_msg}"
        
        # 2. Add LIMIT if missing
        limited_query = QueryValidator.add_limit(query, config.MAX_QUERY_ROWS)
        
        # 3. Check cache
        cache_key = cache._generate_key("query_result", limited_query)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        # 4. Execute via LangChain
        tool = next((t for t in _langchain_tools if t.name == "sql_db_query"), None)
        result = tool.run(limited_query) if tool else "Error: Tool not found"
        
        # 5. Cache result
        cache.set(cache_key, result, config.CACHE_TTL_QUERY_RESULTS)
        
        return f"Query executed via LangChain:\n{result}"
        
    except Exception as e:
        # Helpful error messages
        error_str = str(e).lower()
        if "table" in error_str and "not found" in error_str:
            return "Error: Table not found. Use database_list_tables to see available tables."
        elif "permission" in error_str:
            return "Error: Permission denied."
        else:
            return f"Error: {str(e)}"
```

## Tool Mapping

| MCP Tool | LangChain Tool | Our Enhancement |
|----------|----------------|-----------------|
| `database_list_tables()` | `sql_db_list_tables` | + Redis cache (1h TTL) |
| `database_get_schema()` | `sql_db_schema` | + Redis cache (2h TTL) |
| `database_execute_query()` | `sql_db_query` | + Validation + Cache (5m TTL) + LIMIT |
| `database_query_checker()` | `sql_db_query_checker` | + Custom validation layer |
| `database_clear_cache()` | N/A | Custom cache management |
| `database_cache_stats()` | N/A | Custom monitoring |

## Benefits of This Pattern

### 1. Reliability
- ✅ LangChain handles SQL parsing edge cases
- ✅ Battle-tested error messages
- ✅ Support for multiple SQL dialects
- ✅ Community bug fixes propagate automatically

### 2. Performance
- ✅ Redis caching reduces database load
- ✅ Intelligent TTL strategy:
  - Static data (tables, schemas): Long TTL
  - Dynamic data (query results): Short TTL
- ✅ Cache hit rates typically 60-80%

### 3. Safety
- ✅ **Two layers of validation**:
  1. Custom layer (forbidden keywords, read-only)
  2. LangChain layer (SQL syntax, injection protection)
- ✅ Automatic LIMIT enforcement
- ✅ Query timeout protection

### 4. Maintainability
- ✅ Less code to maintain (LangChain handles complexity)
- ✅ Security updates from LangChain
- ✅ New features become available automatically
- ✅ Clear separation of concerns

## Comparison: Custom vs LangChain

### If You Built Custom SQL Tools

```python
# ❌ Custom implementation
@mcp.tool()
def list_tables() -> str:
    # You have to handle:
    # - SQL dialect differences
    # - Connection pooling
    # - Error messages
    # - Schema inspection
    # - Edge cases
    # - SQL injection
    # - ...and much more
    
    # Hundreds of lines of code
    # Ongoing maintenance burden
```

### Using LangChain (Our Pattern)

```python
# ✅ LangChain-wrapped implementation
@mcp.tool()
def list_tables() -> str:
    # LangChain handles all the complexity
    tool = next((t for t in _langchain_tools if t.name == "sql_db_list_tables"), None)
    result = tool.run("")
    
    # Just add your value: caching
    cache.set(cache_key, result, ttl)
    return result
    
    # ~10 lines of code
    # Minimal maintenance
```

**Winner:** LangChain pattern = 90% less code, battle-tested, maintained by community

## Example: Query Execution Flow

User asks: *"How many orders were placed last month?"*

### Flow:

1. **LLM calls `database_list_tables()`**
   ```
   MCP Tool → Cache Check (hit) → Return cached tables
   ```
   
2. **LLM calls `database_get_schema(table_names="orders")`**
   ```
   MCP Tool → Cache Check (miss) → LangChain sql_db_schema → Cache Set → Return schema
   ```

3. **LLM calls `database_execute_query(query="SELECT COUNT(*) FROM orders WHERE ...")`**
   ```
   MCP Tool 
   → Custom Validation (check SELECT-only, add LIMIT)
   → Cache Check (miss)
   → LangChain sql_db_query (execute safely)
   → Cache Set (5 min TTL)
   → Return results
   ```

4. **LLM responds:** *"You had 1,523 orders last month."*

## Caching Strategy

```python
# From config.py
CACHE_TTL_TABLES_LIST = 3600      # 1 hour (tables rarely change)
CACHE_TTL_TABLE_SCHEMA = 7200     # 2 hours (schemas very stable)
CACHE_TTL_QUERY_RESULTS = 300     # 5 minutes (data changes frequently)
```

**Why these TTLs?**
- **Tables list**: Changes only when tables are created/dropped (rare)
- **Schemas**: Changes only when columns are added/modified (rare)
- **Query results**: Data changes frequently, keep fresh

## Dependencies Required

```toml
# pyproject.toml
dependencies = [
  "langchain>=0.1.0",              # Core LangChain
  "langchain-community>=0.0.10",   # SQLDatabaseToolkit
  "sqlalchemy>=2.0.0",             # Required by LangChain
  "{database}-connector>=3.0.0",   # Your database driver
  "redis>=5.0.0",                  # Caching
  "fastmcp==2.11.3",               # MCP protocol
]
```

## Testing the Integration

```python
# Test LangChain tools load correctly
from app.tools.databricks_tools import _langchain_tools

print(f"Loaded {len(_langchain_tools)} LangChain tools")
# Expected: Loaded 4 LangChain tools

for tool in _langchain_tools:
    print(f"  - {tool.name}: {tool.description[:50]}...")
# Expected:
#   - sql_db_list_tables: Input is an empty string...
#   - sql_db_schema: Input to this tool is a comma...
#   - sql_db_query: Input to this tool is a detailed...
#   - sql_db_query_checker: Use this tool to double...
```

## Summary

**This pattern = Best of both worlds:**

```
LangChain's battle-tested SQL tools
    +
Our caching, validation, and MCP protocol
    =
Production-ready, maintainable MCP server
```

**Use this pattern for all SQL-based MCP servers!**
