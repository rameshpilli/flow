# app/tools/databricks_tools.py
"""
MCP tools wrapping LangChain's SQLDatabaseToolkit for Databricks SQL.

This module exposes LangChain's battle-tested SQL tools via MCP's HTTP transport,
providing natural language querying capabilities for Databricks SQL warehouses.
"""
import logging
from typing import Optional
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit

from app.mcp_singleton import get_mcp_instance
from app.utils.cache import cache
from app.config import config
from app.db.query_validator import QueryValidator
from app.db.connector import db_connector

logger = logging.getLogger("dbx_sql_mcp.tools")
mcp = get_mcp_instance()

# Initialize LangChain SQLDatabase wrapper
def get_langchain_db():
    """Get LangChain SQLDatabase instance wrapping Databricks connection"""
    engine = db_connector.engine
    return SQLDatabase(
        engine=engine,
        schema=config.DATABRICKS_SCHEMA,
        include_tables=None,  # Include all tables
        sample_rows_in_table_info=3,  # Sample rows for context
        max_string_length=1000,
    )

# Initialize LangChain SQLDatabaseToolkit
def get_sql_toolkit():
    """Get LangChain SQL toolkit with Databricks connection"""
    db = get_langchain_db()
    toolkit = SQLDatabaseToolkit(db=db, llm=None)  # No LLM needed for direct tool use
    return toolkit

# Get LangChain tools
langchain_toolkit = get_sql_toolkit()
langchain_tools = langchain_toolkit.get_tools()

logger.info(f"Loaded {len(langchain_tools)} LangChain SQL tools: {[tool.name for tool in langchain_tools]}")


@mcp.tool()
def databricks_list_tables(catalog: Optional[str] = None, schema: Optional[str] = None) -> str:
    """
    List all available tables in the Databricks catalog/schema.
    Uses LangChain's sql_db_list_tables tool.
    
    Args:
        catalog: Optional catalog name (currently uses engine default)
        schema: Optional schema name (currently uses engine default)
    
    Returns:
        Comma-separated list of table names
    """
    try:
        # Use specified catalog/schema or defaults
        target_catalog = catalog or config.DATABRICKS_CATALOG or "default"
        target_schema = schema or config.DATABRICKS_SCHEMA or "default"
        
        cache_key = cache._generate_key("tables_list", target_catalog, target_schema)
        
        # Try cache first
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Returning cached table list for {target_catalog}.{target_schema}")
            return cached_result
        
        # Use LangChain's list tables tool
        list_tables_tool = next((t for t in langchain_tools if t.name == "sql_db_list_tables"), None)
        if not list_tables_tool:
            return "Error: LangChain sql_db_list_tables tool not found"
        
        # Execute LangChain tool
        result = list_tables_tool.run("")
        
        if not result or result.strip() == "":
            result = f"No tables found in {target_catalog}.{target_schema}"
        
        logger.info(f"Retrieved table list using LangChain: {result[:100]}...")
        
        # Cache the result
        cache.set(cache_key, result, config.CACHE_TTL_TABLES_LIST)
        
        return result
        
    except Exception as e:
        error_msg = f"Error listing tables: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"


@mcp.tool()
def databricks_get_schema(table_names: str, catalog: Optional[str] = None, schema: Optional[str] = None) -> str:
    """
    Get the schema (column names and types) for specified tables.
    Uses LangChain's sql_db_schema tool.
    
    Args:
        table_names: Comma-separated list of table names
        catalog: Optional catalog name
        schema: Optional schema name
    
    Returns:
        Schema information for each table including column names and data types
    """
    try:
        target_catalog = catalog or config.DATABRICKS_CATALOG or "default"
        target_schema = schema or config.DATABRICKS_SCHEMA or "default"
        
        cache_key = cache._generate_key("table_schema", target_catalog, target_schema, table_names)
        
        # Try cache first
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Returning cached schema for {table_names}")
            return cached_result
        
        # Use LangChain's schema tool
        schema_tool = next((t for t in langchain_tools if t.name == "sql_db_schema"), None)
        if not schema_tool:
            return "Error: LangChain sql_db_schema tool not found"
        
        # Execute LangChain tool
        result = schema_tool.run(table_names)
        
        if not result or result.strip() == "":
            result = f"No schema found for tables: {table_names}"
        
        logger.info(f"Retrieved schema using LangChain for {table_names}")
        
        # Cache the result
        cache.set(cache_key, result, config.CACHE_TTL_TABLE_SCHEMA)
        
        return result
        
    except Exception as e:
        error_msg = f"Error getting table schema: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"


@mcp.tool()
def databricks_execute_query(query: str, use_cache: bool = True) -> str:
    """
    Execute a SELECT query against Databricks SQL warehouse.
    Uses LangChain's sql_db_query tool with additional safety validation.
    
    IMPORTANT: Only SELECT queries are allowed. Any attempt to modify data will be rejected.
    
    Args:
        query: SQL SELECT query to execute
        use_cache: Whether to use cached results if available (default: True)
    
    Returns:
        Query results as a formatted string, or error message
    """
    try:
        # Our custom validation for extra safety (before LangChain)
        is_valid, error_msg = QueryValidator.validate(query)
        if not is_valid:
            logger.warning(f"Query validation failed: {error_msg}")
            return f"Query validation failed: {error_msg}"
        
        # Add LIMIT if not present
        limited_query = QueryValidator.add_limit(query, config.MAX_QUERY_ROWS)
        
        # Check cache if enabled
        if use_cache:
            cache_key = cache._generate_key("query_result", limited_query)
            cached_result = cache.get(cache_key)
            if cached_result:
                logger.info("Returning cached query result")
                return cached_result
        
        # Use LangChain's query execution tool
        query_tool = next((t for t in langchain_tools if t.name == "sql_db_query"), None)
        if not query_tool:
            return "Error: LangChain sql_db_query tool not found"
        
        logger.info(f"Executing query via LangChain: {limited_query[:100]}...")
        
        # Execute via LangChain
        result = query_tool.run(limited_query)
        
        if not result or result.strip() == "":
            result = "Query executed successfully but returned no rows."
        
        # Format result
        result_str = f"Query executed via LangChain:\n{result}"
        
        logger.info(f"Query successful via LangChain")
        
        # Cache the result
        if use_cache:
            cache.set(cache_key, result_str, config.CACHE_TTL_QUERY_RESULTS)
        
        return result_str
        
    except Exception as e:
        error_msg = f"Error executing query: {str(e)}"
        logger.error(error_msg)
        
        # Provide helpful error messages
        error_str = str(e).lower()
        if "table" in error_str and "not found" in error_str:
            return f"Error: Table or column not found. Use databricks_list_tables to see available tables."
        elif "permission" in error_str or "denied" in error_str:
            return f"Error: Permission denied. You may not have access to this table."
        elif "timeout" in error_str:
            return f"Error: Query timeout. Try simplifying your query or adding more filters."
        else:
            return f"Error: {error_msg}"


@mcp.tool()
def databricks_query_checker(query: str) -> str:
    """
    Check and validate a SQL query before execution.
    Uses LangChain's sql_db_query_checker tool if available.
    
    Args:
        query: SQL query to validate
    
    Returns:
        Validation result or corrected query
    """
    try:
        # First use our custom validator
        is_valid, error_msg = QueryValidator.validate(query)
        if not is_valid:
            return f"Validation failed: {error_msg}"
        
        # Try LangChain's query checker if available
        checker_tool = next((t for t in langchain_tools if "checker" in t.name.lower()), None)
        if checker_tool:
            result = checker_tool.run(query)
            return f"Query validation passed.\nLangChain checker result: {result}"
        else:
            return f"Query validation passed. Ready to execute."
        
    except Exception as e:
        error_msg = f"Error checking query: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"


@mcp.tool()
def databricks_clear_cache(pattern: Optional[str] = None) -> str:
    """
    Clear cached data. Useful when data has been updated and you want fresh results.
    
    Args:
        pattern: Optional pattern to match specific cache keys
    
    Returns:
        Success message
    """
    try:
        if pattern:
            cache.clear_pattern(pattern)
            return f"Cache cleared for pattern: {pattern}"
        else:
            # Clear all databricks caches
            cache.clear_pattern("tables_list")
            cache.clear_pattern("table_schema")
            cache.clear_pattern("query_result")
            return "All Databricks caches cleared successfully"
            
    except Exception as e:
        error_msg = f"Error clearing cache: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"


@mcp.tool()
def databricks_cache_stats() -> str:
    """
    Get cache statistics including hits, misses, and memory usage.
    
    Returns:
        Cache statistics as a formatted string
    """
    try:
        stats = cache.get_stats()
        
        if not stats.get("enabled"):
            return "Cache is disabled"
        
        if not stats.get("connected"):
            return f"Cache error: {stats.get('error', 'Unknown error')}"
        
        result = "Cache Statistics:\n"
        result += f"  Status: Connected\n"
        result += f"  Keys: {stats['keys']}\n"
        result += f"  Memory Used: {stats['memory_used']}\n"
        result += f"  Hits: {stats['hits']}\n"
        result += f"  Misses: {stats['misses']}\n"
        
        if stats['hits'] + stats['misses'] > 0:
            hit_rate = (stats['hits'] / (stats['hits'] + stats['misses'])) * 100
            result += f"  Hit Rate: {hit_rate:.2f}%\n"
        
        return result
        
    except Exception as e:
        error_msg = f"Error getting cache stats: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"


# Log available LangChain tools
logger.info("\n" + "="*80)
logger.info("LANGCHAIN SQL TOOLKIT INTEGRATION")
logger.info("="*80)
logger.info(f"LangChain tools loaded: {len(langchain_tools)}")
for tool in langchain_tools:
    logger.info(f"  - {tool.name}: {tool.description[:60]}...")
logger.info("MCP tools wrap LangChain's battle-tested SQL functionality")
logger.info("="*80 + "\n")
