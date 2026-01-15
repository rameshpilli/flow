# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-01-15

### Added
- Initial release of Databricks SQL MCP Server
- 5 MCP tools for natural language SQL querying
  - `databricks_list_tables` - List tables in catalog/schema
  - `databricks_get_schema` - Get table schemas
  - `databricks_execute_query` - Execute SELECT queries
  - `databricks_clear_cache` - Clear cached data
  - `databricks_cache_stats` - View cache statistics
- Redis caching with configurable TTLs
- Query validation (SELECT-only, no data modification)
- JWT authentication support
- Complete Kubernetes deployment via Helm
- Helios deployment integration
- Health check endpoints
- Comprehensive documentation

### Security
- Query validation prevents data modification
- Automatic query limits (max rows, timeout)
- SQL injection protection
- Vault secrets management

### Performance
- Redis caching for tables, schemas, and query results
- Configurable TTLs per data type
- Connection pooling for Databricks SQL

### Deployment
- Docker image with Redis sidecar
- Helm charts for dev/qat/prod environments
- Auto-scaling configuration (HPA)
- Health checks (liveness/readiness probes)
- Environment-specific configurations
