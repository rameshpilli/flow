---
name: sql-database-mcp
description: Generate production-ready MCP servers for SQL databases (Databricks, Snowflake, PostgreSQL) using LangChain's SQLDatabaseToolkit. Complete with Redis caching, query validation, and Kubernetes deployment.
author: Platform Engineering
version: 1.0.0
tags:
  - mcp
  - sql
  - langchain
  - databricks
  - snowflake
  - postgresql
  - kubernetes
  - redis
---

# SQL Database MCP Server Generator

Generate production-ready MCP servers for **SQL databases** using **LangChain's battle-tested SQLDatabaseToolkit**. Natural language querying with safety validation and caching.

## When to Use This Skill

✅ **Use this skill for:**
- Databricks SQL warehouses
- Snowflake data warehouses
- PostgreSQL databases
- MySQL databases
- Any SQL database with SQLAlchemy support

❌ **Don't use for:**
- REST APIs → Use `rest-api-mcp-skill` instead
- GraphQL → Use `rest-api-mcp-skill` instead
- Non-SQL databases → Custom implementation needed

## Quick Start

**You provide:**
```
Database: Databricks / Snowflake / PostgreSQL
Host: your-db.cloud.provider.com
Catalog: main (or database name)
Schema: default (or schema name)
Warehouse ID: abc123 (if applicable)
```

**You get:**
- ✅ Complete MCP server wrapping LangChain SQLDatabaseToolkit
- ✅ 6 tools (list_tables, get_schema, execute_query, etc.)
- ✅ Read-only query validation (SELECT-only)
- ✅ Redis caching with intelligent TTLs
- ✅ Complete K8s deployment (Helm + Helios)
- ✅ Ready in **~10 minutes**

## Architecture

```
LLM Client (Claude/GPT)
    ↓ HTTP/MCP Protocol
MCP Tools Layer (FastMCP)
    ↓ Cache Check
Redis Cache Layer
    ↓ Validation
Custom Safety Layer (SELECT-only)
    ↓ Execute
LangChain SQLDatabaseToolkit ← Battle-tested!
    ↓ SQL
SQL Database (Databricks/Snowflake/PostgreSQL)
```

## Why LangChain SQLDatabaseToolkit?

✅ **Battle-tested** - Used by thousands in production  
✅ **Maintained** - Active community, security updates  
✅ **Feature-rich** - Query validation, schema inspection  
✅ **SQL dialects** - Handles database differences  
✅ **Less maintenance** - Let LangChain handle complexity

**Our value-add:**
- MCP protocol wrapper
- Additional safety validation (SELECT-only)
- Redis caching layer
- Enterprise K8s deployment
- JWT authentication

## Tools Generated (6 tools)

| Tool | LangChain Tool | Enhancement | TTL |
|------|----------------|-------------|-----|
| `{db}_list_tables` | `sql_db_list_tables` | + Redis cache | 1 hour |
| `{db}_get_schema` | `sql_db_schema` | + Redis cache | 2 hours |
| `{db}_execute_query` | `sql_db_query` | + Validation + Cache + LIMIT | 5 min |
| `{db}_query_checker` | `sql_db_query_checker` | + Custom validation | N/A |
| `{db}_clear_cache` | N/A (custom) | Cache management | N/A |
| `{db}_cache_stats` | N/A (custom) | Cache monitoring | N/A |

**Replace `{db}` with:** `databricks`, `snowflake`, `postgres`, etc.

## Reference Files

All working code is in the `reference/` folder.

### SQL-Specific Templates

| File | Lines | Purpose |
|------|-------|---------|
| `tools_template.py` | 289 | Complete MCP tools wrapping LangChain |
| `connector_template.py` | 85 | Database connector (SQLAlchemy) |
| `query_validator_template.py` | 80 | SQL safety validator (SELECT-only) |
| `config_template.py` | 115 | Database configuration |
| `langchain_pattern.md` | 350 | Complete LangChain integration guide |

### Shared Components

**Location:** `../mcp-server-shared/`

- `auth_templates/` - JWT authentication
- `utils_templates/` - Redis caching + diagnostics
- `helm_templates/` - Complete K8s deployment
- `Dockerfile_template` - Container with Redis
- `main_template.py` - FastMCP application

## Generation Workflow

### Step 1: Gather Information

Ask user for:
```yaml
Database type: Databricks / Snowflake / PostgreSQL / MySQL
Host: your-db.cloud.provider.com
Catalog: main (or database name)
Schema: default (or public)
Warehouse ID: abc123 (for Databricks/Snowflake)
Port: 5432 (for PostgreSQL)
App code: isa0 (for K8s deployment)
Namespace: isa0-dev (for K8s)
```

### Step 2: Read Reference Templates

```
1. Read reference/tools_template.py (LangChain wrapper)
2. Read reference/connector_template.py (SQLAlchemy)
3. Read reference/query_validator_template.py (Safety)
4. Read reference/config_template.py (Configuration)
5. Read reference/langchain_pattern.md (Integration guide)
6. Read ../mcp-server-shared/ (Reusable components)
```

### Step 3: Generate Project Structure

```
{database}-mcp/
├── app/
│   ├── auth/              # Copy from mcp-server-shared/auth_templates/
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connector.py   # From connector_template.py
│   │   └── query_validator.py  # From query_validator_template.py
│   ├── tools/
│   │   ├── __init__.py
│   │   └── {db}_tools.py  # From tools_template.py
│   ├── utils/             # Copy from mcp-server-shared/utils_templates/
│   ├── config.py          # From config_template.py
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

### Step 4: Customize Connection String

In `config.py`, update `get_connection_string()` based on database:

**Databricks:**
```python
f"databricks://token:{token}@{host}?http_path=/sql/1.0/warehouses/{warehouse_id}"
```

**Snowflake:**
```python
f"snowflake://{user}:{password}@{account}/{database}/{schema}?warehouse={warehouse}"
```

**PostgreSQL:**
```python
f"postgresql://{user}:{password}@{host}:{port}/{database}"
```

**MySQL:**
```python
f"mysql://{user}:{password}@{host}:{port}/{database}"
```

### Step 5: Update Dependencies

In `pyproject.toml`:

```toml
dependencies = [
  "fastmcp==2.11.3",
  "uvicorn>=0.23.2",
  "python-dotenv>=1.0.0",
  "pydantic>=2.11.0",
  "redis>=5.0.0",
  "langchain>=0.1.0",           # Core LangChain
  "langchain-community>=0.0.10", # SQLDatabaseToolkit
  "sqlalchemy>=2.0.0",           # Required by LangChain
  "{database}-connector>=3.0.0", # Database driver
  "PyJWT>=2.8.0",
  "rbc-security==2.3.0",
]
```

**Database drivers:**
- Databricks: `databricks-sql-connector>=3.0.0`
- Snowflake: `snowflake-connector-python>=3.0.0`
- PostgreSQL: `psycopg2-binary>=2.9.0`
- MySQL: `mysql-connector-python>=8.0.0`

### Step 6: Replace Placeholders

In all copied files:

| Placeholder | Replace With | Example |
|-------------|--------------|---------|
| `databricks` | User's database name | `snowflake`, `postgres` |
| `DATABRICKS_HOST` | User's env var | `SNOWFLAKE_ACCOUNT` |
| `DATABRICKS_TOKEN` | User's token var | `SNOWFLAKE_PASSWORD` |
| `DATABRICKS_CATALOG` | User's catalog | `SNOWFLAKE_DATABASE` |
| `DATABRICKS_SCHEMA` | User's schema | `SNOWFLAKE_SCHEMA` |
| `databricks-sql-connector` | User's driver | `snowflake-connector-python` |

### Step 7: Generate Configuration

#### `.env` Example:
```bash
# Database Connection
DATABASE_HOST=your-db.cloud.provider.com
DATABASE_TOKEN=your_token_here
DATABASE_WAREHOUSE_ID=abc123  # If applicable
DATABASE_CATALOG=main
DATABASE_SCHEMA=default

# Server
MCP_SERVER_PORT=8000
MAX_QUERY_ROWS=1000
QUERY_TIMEOUT_SECONDS=30

# Redis Cache
REDIS_HOST=localhost
REDIS_PORT=6379
ENABLE_CACHING=true
CACHE_TTL_TABLES_LIST=3600      # 1 hour
CACHE_TTL_TABLE_SCHEMA=7200     # 2 hours
CACHE_TTL_QUERY_RESULTS=300     # 5 minutes

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
  name: {app_code}-{database}-mcp
  tag: 0.1.0
  artifactoryRepo: docker-{app_code}-dev

configuration:
  DATABASE_HOST: ""
  DATABASE_TOKEN: ""
  DATABASE_CATALOG: "{catalog}"
  DATABASE_SCHEMA: "{schema}"
  
  MCP_SERVER_PORT: "8000"
  MAX_QUERY_ROWS: "1000"
  
  REDIS_HOST: "localhost"
  ENABLE_CACHING: "true"
  CACHE_TTL_TABLES_LIST: "3600"
  CACHE_TTL_TABLE_SCHEMA: "7200"
  CACHE_TTL_QUERY_RESULTS: "300"
  
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

## LangChain Integration Pattern

**Key pattern to preserve:**

```python
# Initialize LangChain toolkit once
def _get_langchain_toolkit():
    db = SQLDatabase(
        engine=db_connector.engine,
        schema=config.DATABASE_SCHEMA,
        include_tables=None,
        sample_rows_in_table_info=3,
    )
    return SQLDatabaseToolkit(db=db, llm=None)

_toolkit = _get_langchain_toolkit()
_langchain_tools = _toolkit.get_tools()

# Wrap each LangChain tool with MCP + caching
@mcp.tool()
def database_list_tables() -> str:
    # 1. Check cache
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    # 2. Execute via LangChain
    tool = next((t for t in _langchain_tools if t.name == "sql_db_list_tables"), None)
    result = tool.run("") if tool else "Error: Tool not found"
    
    # 3. Cache result
    cache.set(cache_key, result, config.CACHE_TTL_TABLES_LIST)
    
    return result
```

**See `reference/langchain_pattern.md` for complete details.**

## Examples

### Example 1: Databricks

**User:** "Create a Databricks MCP server for catalog 'sales', schema 'analytics', warehouse '2a3b4c5d', host 'my-workspace.cloud.databricks.com'"

**Generated:**
- Project: `databricks-sql-mcp/`
- Tools: `databricks_list_tables`, `databricks_get_schema`, etc.
- Connection: `databricks://token:...`
- Driver: `databricks-sql-connector`
- Ready in: ~10 minutes

### Example 2: Snowflake

**User:** "Create a Snowflake MCP server for database 'PROD_DB', schema 'PUBLIC', warehouse 'COMPUTE_WH', account 'abc123'"

**Generated:**
- Project: `snowflake-mcp/`
- Tools: `snowflake_list_tables`, `snowflake_get_schema`, etc.
- Connection: `snowflake://...`
- Driver: `snowflake-connector-python`
- Ready in: ~10 minutes

### Example 3: PostgreSQL

**User:** "Create a PostgreSQL MCP server for database 'customers', schema 'public', host 'db.example.com', port 5432'"

**Generated:**
- Project: `postgres-mcp/`
- Tools: `postgres_list_tables`, `postgres_get_schema`, etc.
- Connection: `postgresql://...`
- Driver: `psycopg2-binary`
- Ready in: ~10 minutes

## Success Criteria

Generated server must have:

- ✅ 6 working MCP tools wrapping LangChain
- ✅ Query validation (SELECT-only, no modifications)
- ✅ Redis caching (tables: 1h, schemas: 2h, queries: 5m)
- ✅ Automatic LIMIT clause enforcement
- ✅ Complete K8s deployment (Helm + Helios)
- ✅ Health check endpoints
- ✅ Comprehensive documentation
- ✅ Ready to deploy with one command

## Testing

### Local Testing:
```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r pyproject.toml

# Configure
cp .env.example .env
# Edit .env with database credentials

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
  DATABASE_HOST="..." \
  DATABASE_TOKEN="..."

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

**Location:** `/Users/rameshpilli/Developer/dbx-sql-mcp/`

- Databricks SQL MCP Server
- LangChain SQLDatabaseToolkit wrapper
- 6 tools, 11 dependencies
- Clean, optimized code
- Production-ready

## Time Savings

- **Manual creation**: ~4 hours
- **With this skill**: ~10 minutes
- **Savings**: 96%

## Related Skills

- **REST API MCP**: Use `rest-api-mcp-skill` for REST APIs
- **Shared Components**: See `mcp-server-shared/` for reusable parts

---

**Ready to generate a SQL database MCP server?**

Just say: "Create a [Database] MCP server for catalog '[catalog]', schema '[schema]', host '[host]'"
