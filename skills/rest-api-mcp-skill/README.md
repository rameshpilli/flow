# REST API MCP Server Skill

Generate production-ready MCP servers for REST APIs and microservices using httpx AsyncClient with connection pooling and parallel execution.

## Installation

Copy this skill to your Claude skills directory:

```bash
mkdir -p ~/.claude/skills/
cp -r rest-api-mcp-skill ~/.claude/skills/
```

## Usage

Ask Claude:
> "Create an MCP server for Client360 API at https://api.client360.com with endpoints: /clients, /revenue, /contacts"

Claude will generate a complete, production-ready MCP server in ~15 minutes.

## What You Get

- ✅ 5-10 MCP tools (endpoint-specific)
- ✅ httpx AsyncClient with connection pooling (50 keepalive connections)
- ✅ Per-API timeout configuration
- ✅ Parallel execution (asyncio.gather)
- ✅ Redis caching layer
- ✅ Complete Kubernetes deployment
- ✅ Graceful error handling

## Supported Services

- Corporate REST APIs
- Microservices (internal/external)
- Third-party APIs (Salesforce, ServiceNow, etc.)
- HTTP-based services
- GraphQL endpoints

## Reference Files

- `reference/api_client_template.py` - httpx AsyncClient implementation (1,232 lines)
- `reference/orchestrator_template.py` - Parallel API execution (1,045 lines)
- `reference/config_api_template.py` - REST API configuration
- `reference/README_API_PATTERN.md` - Complete pattern guide

## Shared Components

This skill uses shared components from `../mcp-server-shared/`:
- Authentication (JWT, Bearer, Basic, OAuth)
- Caching (Redis)
- Kubernetes deployment (Helm)
- Docker containerization

## Related Skills

- **SQL Database MCP**: Use `sql-database-mcp-skill` for SQL databases
- **Shared Components**: See `mcp-server-shared` for reusable parts

## Reference Project

Complete working example: `/Users/rameshpilli/Developer/CF copy/`
- 16 backend REST APIs
- Orchestrator with parallel execution
- 11 tools
- Production-ready

## Time Savings

- Manual: ~6 hours
- With skill: ~15 minutes
- Savings: 96%
