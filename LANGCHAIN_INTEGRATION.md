# LangChain SQLDatabaseToolkit Integration

## Overview

This MCP server **wraps LangChain's battle-tested SQLDatabaseToolkit**, providing natural language SQL querying capabilities for Databricks SQL warehouses via MCP's HTTP transport.

## Architecture

```
┌──────────────────┐
│   LLM (Claude)   │
└────────┬─────────┘
         │ MCP/HTTP
         ▼
┌────────────────────────────────────┐
│  MCP Server (FastMCP)              │
│  ┌──────────────────────────────┐  │
│  │  MCP Tools Layer             │  │
│  │  - databricks_list_tables    │  │
│  │  - databricks_get_schema     │  │
│  │  - databricks_execute_query  │  │
│  │  - databricks_query_checker  │  │
│  └────────────┬─────────────────┘  │
│               │                     │
│  ┌────────────▼─────────────────┐  │
│  │  Redis Cache Layer           │  │
│  │  (Optional caching)          │  │
│  └────────────┬─────────────────┘  │
│               │                     │
│  ┌────────────▼─────────────────┐  │
│  │  Custom Validation Layer     │  │
│  │  (Query safety checks)       │  │
│  └────────────┬─────────────────┘  │
│               │                     │
│  ┌────────────▼─────────────────┐  │
│  │  LangChain SQLDatabaseToolkit│  │
│  │  - sql_db_list_tables        │  │
│  │  - sql_db_schema             │  │
│  │  - sql_db_query              │  │
│  │  - sql_db_query_checker      │  │
│  └────────────┬─────────────────┘  │
└───────────────┼─────────────────────┘
                │ SQL
                ▼
┌───────────────────────────────────┐
│  Databricks SQL Warehouse         │
└───────────────────────────────────┘
```

## Why Use LangChain's SQLDatabaseToolkit?

### Battle-Tested
- ✅ Used in production by thousands of applications
- ✅ Handles edge cases and SQL dialects
- ✅ Actively maintained and improved
- ✅ Comprehensive error handling

### Rich Functionality
- ✅ Table listing and discovery
- ✅ Schema inspection
- ✅ Query execution
- ✅ Query validation and checking
- ✅ Sample data generation

### Our Value-Add
We wrap LangChain tools with:
- ✅ **MCP protocol** - Standard interface for LLMs
- ✅ **Redis caching** - Performance optimization
- ✅ **Additional validation** - Safety layer before LangChain
- ✅ **JWT authentication** - Enterprise security
- ✅ **K8s deployment** - Production infrastructure

## Implementation Details

### Tool Mapping

| MCP Tool | LangChain Tool | Enhancement |
|----------|----------------|-------------|
| `databricks_list_tables` | `sql_db_list_tables` | + Redis caching |
| `databricks_get_schema` | `sql_db_schema` | + Redis caching |
| `databricks_execute_query` | `sql_db_query` | + Validation + Caching + LIMIT enforcement |
| `databricks_query_checker` | `sql_db_query_checker` | + Custom validation layer |
| `databricks_clear_cache` | N/A | Custom cache management |
| `databricks_cache_stats` | N/A | Custom cache monitoring |

### Code Structure

```python
# Initialize LangChain SQLDatabase
db = SQLDatabase(
    engine=databricks_engine,
    schema=schema,
    include_tables=None,
    sample_rows_in_table_info=3,
)

# Initialize LangChain SQLDatabaseToolkit
toolkit = SQLDatabaseToolkit(db=db, llm=None)
langchain_tools = toolkit.get_tools()

# Wrap LangChain tools with MCP + caching
@mcp.tool()
def databricks_execute_query(query: str) -> str:
    # 1. Check cache
    cached = get_from_cache(query)
    if cached:
        return cached
    
    # 2. Custom validation (our safety layer)
    validate_query_safe(query)
    
    # 3. Execute via LangChain
    langchain_query_tool = get_langchain_tool("sql_db_query")
    result = langchain_query_tool.run(query)
    
    # 4. Cache result
    cache_result(query, result)
    
    return result
```

## Benefits of This Approach

### 1. Reliability
Using LangChain's proven SQL tools means:
- Fewer bugs
- Better error messages
- Comprehensive SQL dialect support
- Community-tested functionality

### 2. Maintainability
When LangChain improves, we improve:
- Security patches propagate automatically
- New features become available
- Bug fixes are inherited
- No need to maintain SQL parsing logic

### 3. Performance
Our caching layer adds value:
- Table lists cached (rarely change)
- Schemas cached (very stable)
- Query results cached (frequently repeated)
- Reduces Databricks warehouse load

### 4. Safety
Multiple layers of protection:
- Custom validation (our layer)
- LangChain's validation
- Query timeout enforcement
- Automatic LIMIT clause
- Read-only enforcement

## Configuration

### LangChain Setup

```python
# app/tools/databricks_tools.py
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit

# Create LangChain database wrapper
db = SQLDatabase(
    engine=databricks_engine,
    schema=config.DATABRICKS_SCHEMA,
    include_tables=None,  # All tables
    sample_rows_in_table_info=3,  # Sample rows for context
    max_string_length=1000,
)

# Create toolkit
toolkit = SQLDatabaseToolkit(db=db, llm=None)
tools = toolkit.get_tools()
```

### Available LangChain Tools

When you initialize the toolkit, you get these tools:

1. **sql_db_list_tables** - List all tables
2. **sql_db_schema** - Get schema for specific tables
3. **sql_db_query** - Execute SQL queries
4. **sql_db_query_checker** - Validate and check queries

Our MCP tools wrap these with caching and additional validation.

## Example Flow

### User Request
> "How many orders did we have last month?"

### Execution Flow

1. **MCP Tool Called**: `databricks_list_tables()`
   - Checks Redis cache
   - Calls LangChain's `sql_db_list_tables`
   - Returns: "customers, orders, products"
   - Caches result (1 hour TTL)

2. **MCP Tool Called**: `databricks_get_schema(table_names="orders")`
   - Checks Redis cache
   - Calls LangChain's `sql_db_schema`
   - Returns: Schema with columns
   - Caches result (2 hour TTL)

3. **MCP Tool Called**: `databricks_execute_query(query="SELECT COUNT(*) FROM orders WHERE...")`
   - Checks Redis cache
   - **Custom validation** (our layer): Checks if query is SELECT-only
   - **Adds LIMIT** clause if missing
   - Calls LangChain's `sql_db_query`
   - Returns: Query results
   - Caches result (5 min TTL)

## Testing LangChain Integration

### Verify LangChain Tools Load

```python
# Should log at startup:
# Loaded 4 LangChain SQL tools: ['sql_db_list_tables', 'sql_db_schema', 'sql_db_query', 'sql_db_query_checker']
```

### Test Individual Tools

```python
# Test list tables
from app.tools.databricks_tools import langchain_toolkit
tools = langchain_toolkit.get_tools()

list_tool = next(t for t in tools if t.name == "sql_db_list_tables")
result = list_tool.run("")
print(f"Tables: {result}")

# Test schema
schema_tool = next(t for t in tools if t.name == "sql_db_schema")
result = schema_tool.run("orders")
print(f"Schema: {result}")

# Test query
query_tool = next(t for t in tools if t.name == "sql_db_query")
result = query_tool.run("SELECT COUNT(*) FROM orders LIMIT 10")
print(f"Result: {result}")
```

## Dependencies

### Required Packages

```toml
# pyproject.toml
dependencies = [
  "langchain>=0.1.0",              # Core LangChain
  "langchain-community>=0.0.10",   # Community tools (SQLDatabaseToolkit)
  "sqlalchemy>=2.0.0",             # SQL engine (required by LangChain)
  "databricks-sql-connector>=3.0.0", # Databricks connection
]
```

### Why These Versions?

- **langchain**: Core framework
- **langchain-community**: Contains SQLDatabaseToolkit
- **sqlalchemy**: Required by LangChain for database connections
- **databricks-sql-connector**: Databricks-specific driver

## Comparison: Custom vs LangChain

### If We Built Custom Tools

❌ **Cons:**
- Reinventing the wheel
- More bugs to fix
- SQL dialect quirks
- No community testing
- Maintenance burden
- Missing edge cases

✅ **Pros:**
- Full control
- Simpler dependencies

### Wrapping LangChain (Current Approach)

✅ **Pros:**
- Battle-tested code
- Community support
- Automatic improvements
- Better error handling
- Comprehensive features
- Less maintenance

❌ **Cons:**
- Additional dependency
- Slightly more complex setup

**Verdict**: Wrapping LangChain is the right choice for production.

## Future Enhancements

### Potential Improvements

1. **LangChain Agents** - Use full agent capabilities for complex queries
2. **More Tools** - Expose additional LangChain SQL tools
3. **Custom Validators** - Add more domain-specific validation
4. **Query Optimization** - Use LangChain's query optimization features
5. **Multi-Database** - Extend to other databases using same toolkit

## Troubleshooting

### LangChain Tools Not Loading

Check logs for:
```
ERROR: Could not import langchain_community
```

Solution:
```bash
pip install langchain-community
```

### SQLAlchemy Version Issues

LangChain requires SQLAlchemy 2.0+:
```bash
pip install "sqlalchemy>=2.0.0"
```

### Databricks Connection Issues

Ensure databricks-sql-connector is installed:
```bash
pip install databricks-sql-connector
```

## References

- **LangChain SQL Tools**: https://python.langchain.com/docs/integrations/toolkits/sql_database
- **SQLDatabaseToolkit**: https://api.python.langchain.com/en/latest/agent_toolkits/langchain_community.agent_toolkits.sql.toolkit.SQLDatabaseToolkit.html
- **Databricks Connector**: https://docs.databricks.com/dev-tools/python-sql-connector.html

---

**Summary**: This MCP server successfully wraps LangChain's battle-tested SQLDatabaseToolkit, adding caching, validation, and MCP protocol support for production-ready natural language SQL querying of Databricks SQL warehouses.
