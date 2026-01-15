# Databricks SQL MCP Server

MCP server wrapping **LangChain's SQLDatabaseToolkit** for natural language SQL querying of Databricks SQL warehouses. Exposes battle-tested LangChain tools via MCP's HTTP transport.

## Features

- 🔗 **LangChain Integration** - Wraps LangChain's battle-tested SQLDatabaseToolkit
- 🔒 **Read-only** - SELECT queries only (validated before LangChain)
- ⚡ **Redis caching** - Layer on top of LangChain tools
- 🔑 **JWT auth** - Optional authentication support  
- ☸️ **K8s ready** - Complete Helm charts + Helios deployment
- 🏥 **Health checks** - Liveness and readiness probes
- 📊 **Monitoring** - Cache stats and diagnostics

## MCP Tools (Wrapping LangChain)

| Tool | LangChain Tool | Description |
|------|----------------|-------------|
| `databricks_list_tables` | `sql_db_list_tables` | List available tables via LangChain |
| `databricks_get_schema` | `sql_db_schema` | Get table schemas via LangChain |
| `databricks_execute_query` | `sql_db_query` | Execute SELECT queries via LangChain (with validation) |
| `databricks_query_checker` | `sql_db_query_checker` | Validate queries using LangChain |
| `databricks_clear_cache` | N/A (custom) | Clear Redis cache layer |
| `databricks_cache_stats` | N/A (custom) | View cache performance metrics |

**Architecture**: MCP tools → Cache layer → LangChain SQLDatabaseToolkit → Databricks SQL

## Quick Start

### Local Development

```bash
# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r pyproject.toml

# Configure (create .env file)
cat > .env << EOF
DATABRICKS_HOST=your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi_your_token
DATABRICKS_SQL_WAREHOUSE_ID=your_warehouse_id
DATABRICKS_CATALOG=main
DATABRICKS_SCHEMA=default
EOF

# Run Redis
redis-server &

# Start server
python -m app.main

# Test
curl http://localhost:8000/health
```

### Docker

```bash
docker build -t dbx-sql-mcp .
docker run -p 8000:8000 \
  -e DATABRICKS_HOST=... \
  -e DATABRICKS_TOKEN=... \
  -e DATABRICKS_SQL_WAREHOUSE_ID=... \
  dbx-sql-mcp
```

## Configuration

See `.env.example` for all options. Key variables:

```bash
# Required
DATABRICKS_HOST=your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi_xxx
DATABRICKS_SQL_WAREHOUSE_ID=xxx

# Optional
DATABRICKS_CATALOG=main           # Default catalog
DATABRICKS_SCHEMA=default         # Default schema
MAX_QUERY_ROWS=1000              # Query row limit
QUERY_TIMEOUT_SECONDS=30         # Query timeout

# Caching (seconds)
CACHE_TTL_TABLES_LIST=3600       # 1 hour
CACHE_TTL_TABLE_SCHEMA=7200      # 2 hours  
CACHE_TTL_QUERY_RESULTS=300      # 5 minutes

# Auth (optional)
AUTH_SERVER_SECRET=your_secret_key
```

## Deployment

### K8s via Helios

```bash
# 1. Store secrets in Vault
vault write appcodes/ISA0/DEV/DATABRICKS-SQL-MCP \
  DATABRICKS_HOST="..." \
  DATABRICKS_TOKEN="..." \
  DATABRICKS_SQL_WAREHOUSE_ID="..."

# 2. Update configuration
# - Edit helm/values.yaml (app code, image name)
# - Edit helios/env-config.yml (namespaces)
# - Edit helios/deploy.sh (Vault path)

# 3. Build and push
docker build -t your-registry/dbx-sql-mcp:0.1.0 .
docker push your-registry/dbx-sql-mcp:0.1.0

# 4. Deploy
helios deploy --environment dev
```

See [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) for detailed instructions.

## Usage Example

**User:** "How many orders did we have last month?"

```python
# 1. LLM discovers tables
databricks_list_tables()
→ "customers, orders, products"

# 2. LLM checks schema
databricks_get_schema(table_names="orders")
→ Shows: order_id, customer_id, order_date, total_amount

# 3. LLM executes query
databricks_execute_query(
  query="SELECT COUNT(*) FROM orders WHERE order_date >= '2025-12-01'"
)
→ "[(1523,)]"

# 4. LLM responds
"You had 1,523 orders last month."
```

## Architecture

```
┌──────────┐                                    
│   LLM    │                                    
└────┬─────┘                                    
     │ HTTP/MCP                                 
     ▼                                          
┌─────────────────────────────────┐                         
│  MCP Server + Redis Cache       │                         
│  ┌────────────────────────────┐ │                         
│  │ MCP Tools (FastMCP)        │ │                         
│  │   │                        │ │
│  │   ▼                        │ │                         
│  │ LangChain SQLDatabaseToolkit│ │
│  │ (battle-tested SQL tools)  │ │                         
│  └────────────┬───────────────┘ │                         
└───────────────┼─────────────────┘                         
                │ SQL                               
                ▼                                   
┌───────────────────────────────┐                         
│  Databricks SQL Warehouse     │                         
└───────────────────────────────┘                         

Flow: LLM → MCP → Cache Check → LangChain Tools → Databricks
```

## Project Structure

```
dbx-sql-mcp/
├── app/
│   ├── auth/              # JWT authentication
│   ├── db/                # Databricks connector + query validator
│   ├── tools/             # MCP tools implementation
│   ├── utils/             # Cache + diagnostics
│   ├── config.py          # Configuration
│   └── main.py            # FastMCP app
├── helm/                  # Kubernetes deployment
│   ├── templates/         # K8s resources
│   └── environments/      # Dev/QAT/Prod configs
├── helios/                # Deployment scripts
├── docs/                  # Documentation
├── Dockerfile             # Container with Redis sidecar
└── pyproject.toml         # Dependencies
```

## Security

- ✅ **Read-only** - Only SELECT queries allowed (validated)
- ✅ **Query limits** - Automatic LIMIT clause added
- ✅ **Timeouts** - Query timeout enforcement
- ✅ **SQL injection** - Query validation and sanitization
- ✅ **Secrets** - Stored in Vault, not in code

## Monitoring

### Health Check
```bash
curl http://localhost:8000/health
# → {"status":"healthy","database":"connected","cache":"enabled"}
```

### Cache Stats
Use the `databricks_cache_stats()` MCP tool or:
```bash
kubectl exec pod-name -- redis-cli INFO stats
```

### Logs
```bash
# Kubernetes
kubectl logs -f deployment/dbx-sql-mcp

# Docker
docker logs -f container-id
```

## Troubleshooting

**Pod not starting?**
```bash
kubectl describe pod pod-name
kubectl logs pod-name
```

**Redis issues?**
```bash
kubectl exec pod-name -- redis-cli PING
```

**Database connection?**
```bash
# Test from pod
kubectl exec pod-name -- python3 -c "
from app.db.connector import db_connector
print('Connected!' if db_connector.test_connection() else 'Failed')
"
```

## Development

### Run Tests
```bash
pytest tests/
```

### Code Quality
```bash
black app/      # Format
ruff check app/ # Lint
```

## Documentation

- [`DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) - Step-by-step deployment
- [`USAGE_EXAMPLES.md`](docs/USAGE_EXAMPLES.md) - Real-world examples

## Performance

### Cache TTL Guidelines

| Data Type | TTL | Reason |
|-----------|-----|--------|
| Table lists | 1-2 hours | Rarely changes |
| Schemas | 2-4 hours | Very stable |
| Query results | 5-10 minutes | Can change frequently |

### Resource Limits

```yaml
# Development
resources:
  requests: { cpu: 250m, memory: 256Mi }
  limits: { cpu: 1000m, memory: 1Gi }

# Production  
resources:
  requests: { cpu: 1000m, memory: 1Gi }
  limits: { cpu: 2000m, memory: 2Gi }
```

## License

Internal use - RBC proprietary

## Support

- Check [`docs/`](docs/) for detailed guides
- Review logs for error messages
- Contact Platform Engineering team

---

**Version**: 0.1.0  
**Created**: 2026-01-15
