# Enterprise MCP Server Skills

Production-ready skills for generating MCP servers with complete Kubernetes deployment. Organized following the [Anthropic skills pattern](https://github.com/anthropics/skills/tree/main/skills).

## 📚 Skills

### [SQL Database MCP](skills/sql-database-mcp-skill/)
Generate MCP servers for SQL databases using LangChain's SQLDatabaseToolkit.

**Supported:** Databricks, Snowflake, PostgreSQL, MySQL  
**Tools:** 6 (list_tables, get_schema, execute_query, query_checker, clear_cache, cache_stats)  
**Time:** ~10 minutes

### [REST API MCP](skills/rest-api-mcp-skill/)
Generate MCP servers for REST APIs using httpx AsyncClient with connection pooling.

**Supported:** Corporate APIs, Microservices, Third-party APIs  
**Tools:** 5-10 (endpoint-specific + orchestrator)  
**Time:** ~15 minutes

### [Shared Components](skills/shared/)
Reusable components for both SQL and REST API MCP servers.

**Includes:** Auth, Caching, K8s deployment, Docker

## 🚀 Installation

Clone the entire skills library:

```bash
git clone https://github.com/rameshpilli/flow.git --branch mcp-skills mcp-skills
cd mcp-skills
```

Install all skills to Claude:

```bash
cp -r skills/* ~/.claude/skills/
```

Or install individual skills:

```bash
# SQL Database skill only
cp -r skills/sql-database-mcp-skill ~/.claude/skills/

# REST API skill only
cp -r skills/rest-api-mcp-skill ~/.claude/skills/

# Shared components (required by both)
cp -r skills/shared ~/.claude/skills/mcp-server-shared/
```

## 💡 Usage

### SQL Database MCP Server

Ask Claude:
> "Create a Databricks MCP server for catalog 'sales', schema 'analytics', warehouse '2a3b4c5d'"

Claude generates complete SQL MCP server in ~10 minutes.

### REST API MCP Server

Ask Claude:
> "Create an MCP server for Client360 API at https://api.client360.com with endpoints: GET /clients, POST /clients/{id}/revenue"

Claude generates complete REST API MCP server in ~15 minutes.

## 📁 Repository Structure

```
mcp-skills/
├── README.md                      # This file
└── skills/
    ├── sql-database-mcp-skill/    # SQL databases (LangChain)
    │   ├── SKILL.md               # Skill definition
    │   ├── README.md              # Installation guide
    │   └── reference/             # Code templates
    │       ├── tools_template.py
    │       ├── connector_template.py
    │       ├── query_validator_template.py
    │       └── langchain_pattern.md
    │
    ├── rest-api-mcp-skill/        # REST APIs (httpx)
    │   ├── SKILL.md
    │   ├── README.md
    │   └── reference/
    │       ├── api_client_template.py
    │       ├── orchestrator_template.py
    │       └── README_API_PATTERN.md
    │
    └── shared/                     # Shared components
        ├── README.md
        ├── auth_templates/         # JWT authentication
        ├── utils_templates/        # Redis caching
        ├── helm_templates/         # K8s deployment
        ├── Dockerfile_template     # Container
        └── main_template.py        # FastMCP setup
```

## ✨ Benefits of This Structure

### vs. Separate Branches

| Aspect | Separate Branches | Single Branch (Ours) |
|--------|------------------|----------------------|
| Clone command | 3 separate clones | 1 clone |
| Maintenance | Update 3 branches | Update 1 branch |
| Version control | 3 separate versions | 1 unified version |
| Sharing | Send 3 links | Send 1 link |
| Industry standard | ❌ | ✅ (Anthropic pattern) |

### Why Single Branch?

✅ **Easy to clone** - One command gets everything  
✅ **Easy to maintain** - All skills versioned together  
✅ **Easy to share** - One repo, one branch  
✅ **Industry standard** - Follows [Anthropic pattern](https://github.com/anthropics/skills/tree/main/skills)  
✅ **Simpler git workflow** - No branch management  
✅ **Team-friendly** - Clear foundational skill library

## 📊 What's Included

| Skill | Files | Lines | Templates |
|-------|-------|-------|-----------|
| SQL Database MCP | 8 | ~1,500 | 6 |
| REST API MCP | 6 | ~3,400 | 4 |
| Shared Components | 21 | ~1,300 | Reusable |
| **Total** | **35** | **~6,200** | **10+** |

## 🎯 Use Cases

### SQL Database Servers
- Databricks SQL warehouses
- Snowflake data warehouses
- PostgreSQL databases
- MySQL databases
- Natural language SQL querying
- Read-only query validation

### REST API Servers
- Corporate internal APIs
- Microservices integration
- Third-party APIs (Salesforce, ServiceNow)
- Financial data aggregation
- CRM integrations
- Multi-API orchestration

## 🔗 Reference Projects

**SQL Pattern:** `/Users/rameshpilli/Developer/dbx-sql-mcp/`  
- Databricks SQL MCP Server
- LangChain SQLDatabaseToolkit
- Production-ready

**REST API Pattern:** `/Users/rameshpilli/Developer/CF copy/`  
- Client-First MCP Server
- 16 backend REST APIs
- Parallel execution with connection pooling
- Production-ready

## ⏱️ Time Savings

| Task | Manual | With Skills | Savings |
|------|--------|-------------|---------|
| SQL Database MCP | 4 hours | 10 minutes | 96% |
| REST API MCP | 6 hours | 15 minutes | 96% |

## 🤝 Contributing

When adding new skills:

1. Create folder under `skills/`
2. Follow naming: `{type}-mcp-skill/`
3. Include: `SKILL.md`, `README.md`, `reference/`
4. Use shared components from `skills/shared/`
5. Document in main README

## 📄 License

MIT

## 👥 Author

Platform Engineering Team

---

**Inspired by:** [Anthropic Skills Repository](https://github.com/anthropics/skills/tree/main/skills)
