# app/utils/startup_diagnostics.py
import logging
from app.config import config

logger = logging.getLogger("dbx_sql_mcp")


def run_startup_diagnostics(tool_count: int = 0):
    """Run diagnostics during server startup"""
    logger.info("\n" + "="*80)
    logger.info("STARTUP DIAGNOSTICS")
    logger.info("="*80)
    
    # Check required configuration
    missing_config = config.validate_required_config()
    if missing_config:
        logger.error(f"❌ Missing required configuration: {', '.join(missing_config)}")
        raise ValueError(f"Missing required configuration: {missing_config}")
    else:
        logger.info("✓ All required configuration present")
    
    # Databricks connection info
    logger.info(f"✓ Databricks Host: {config.DATABRICKS_HOST}")
    logger.info(f"✓ SQL Warehouse ID: {config.DATABRICKS_SQL_WAREHOUSE_ID}")
    if config.DATABRICKS_CATALOG:
        logger.info(f"✓ Default Catalog: {config.DATABRICKS_CATALOG}")
    if config.DATABRICKS_SCHEMA:
        logger.info(f"✓ Default Schema: {config.DATABRICKS_SCHEMA}")
    
    # Cache settings
    if config.ENABLE_CACHING:
        logger.info(f"✓ Redis Cache: Enabled ({config.REDIS_HOST}:{config.REDIS_PORT})")
        logger.info(f"  - Tables List TTL: {config.CACHE_TTL_TABLES_LIST}s")
        logger.info(f"  - Table Schema TTL: {config.CACHE_TTL_TABLE_SCHEMA}s")
        logger.info(f"  - Query Results TTL: {config.CACHE_TTL_QUERY_RESULTS}s")
    else:
        logger.info("⚠ Redis Cache: Disabled")
    
    # Query limits
    logger.info(f"✓ Max Query Rows: {config.MAX_QUERY_ROWS}")
    logger.info(f"✓ Query Timeout: {config.QUERY_TIMEOUT_SECONDS}s")
    
    logger.info("="*80 + "\n")


def log_tool_registration(tool_names: list[str]):
    """Log registered MCP tools"""
    logger.info(f"\n{'='*80}")
    logger.info(f"REGISTERED MCP TOOLS ({len(tool_names)})")
    logger.info(f"{'='*80}")
    for name in tool_names:
        logger.info(f"  ✓ {name}")
    logger.info(f"{'='*80}\n")


def log_startup_summary(tool_count: int):
    """Log startup summary"""
    logger.info("\n" + "="*80)
    logger.info("🚀 DATABRICKS SQL MCP SERVER READY")
    logger.info("="*80)
    logger.info(f"  Port: {config.MCP_SERVER_PORT}")
    logger.info(f"  Tools: {tool_count}")
    logger.info(f"  Cache: {'Enabled' if config.ENABLE_CACHING else 'Disabled'}")
    logger.info(f"  Environment: {'Development' if config.DEVELOPMENT else 'Production'}")
    logger.info("="*80 + "\n")
