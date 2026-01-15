# SQL Database MCP Server Skill

Generate production-ready MCP servers for SQL databases (Databricks, Snowflake, PostgreSQL) using LangChain's SQLDatabaseToolkit.

## Installation

Copy this skill to your Claude skills directory:

```bash
mkdir -p ~/.claude/skills/
cp -r sql-database-mcp-skill ~/.claude/skills/
```

## Usage

Ask Claude:
> "Create a Databricks MCP server for catalog 'sales', schema 'analytics', host 'my-workspace.cloud.databricks.com'"

Claude will generate a complete, production-ready MCP server in ~10 minutes.

## What You Get

- ✅ 6 MCP tools wrapping LangChain SQLDatabaseToolkit
- ✅ Read-only query validation (SELECT-only)
- ✅ Redis caching layer
- ✅ Complete Kubernetes deployment
- ✅ Health checks and monitoring

## Supported Databases

- Databricks SQL warehouses
- Snowflake data warehouses
- PostgreSQL
- MySQL
- Any SQL database with SQLAlchemy support

## Reference Files

- `reference/tools_template.py` - MCP tools wrapping LangChain
- `reference/connector_template.py` - Database connector
- `reference/query_validator_template.py` - SQL safety validator
- `reference/langchain_pattern.md` - Complete integration guide

## Shared Components

This skill uses shared components from `../mcp-server-shared/`:
- Authentication (JWT)
- Caching (Redis)
- Kubernetes deployment (Helm)
- Docker containerization

## Related Skills

- **REST API MCP**: Use `rest-api-mcp-skill` for REST APIs
- **Shared Components**: See `mcp-server-shared` for reusable parts

## Reference Project

Complete working example: `/Users/rameshpilli/Developer/dbx-sql-mcp/`

## Time Savings

- Manual: ~4 hours
- With skill: ~10 minutes
- Savings: 96%
