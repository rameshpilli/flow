# app/tools/databricks_tools.py
import logging
from typing import List, Optional
from sqlalchemy import text, inspect
from app.db.connector import db_connector
from app.db.query_validator import QueryValidator
from app.utils.cache import cache, cached
from app.config import config
from app.mcp_singleton import get_mcp_instance

logger = logging.getLogger("dbx_sql_mcp.tools")

mcp = get_mcp_instance()


@mcp.tool()
def databricks_list_tables(catalog: Optional[str] = None, schema: Optional[str] = None) -> str:
    """
    List all available tables in the Databricks catalog/schema.
    
    Args:
        catalog: Optional catalog name. If not provided, uses default from config.
        schema: Optional schema name. If not provided, uses default from config.
    
    Returns:
        Comma-separated list of table names
    """
    try:
        # Use provided catalog/schema or fall back to config defaults
        target_catalog = catalog or config.DATABRICKS_CATALOG or "default"
        target_schema = schema or config.DATABRICKS_SCHEMA or "default"
        
        cache_key = cache._generate_key("tables_list", target_catalog, target_schema)
        
        # Try cache first
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Returning cached table list for {target_catalog}.{target_schema}")
            return cached_result
        
        # Query for tables
        engine = db_connector.engine
        inspector = inspect(engine)
        
        # Get tables from the specified schema
        tables = inspector.get_table_names(schema=target_schema)
        
        if not tables:
            result = f"No tables found in {target_catalog}.{target_schema}"
        else:
            result = ", ".join(sorted(tables))
            logger.info(f"Found {len(tables)} tables in {target_catalog}.{target_schema}")
        
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
        
        # Parse table names
        tables = [t.strip() for t in table_names.split(",")]
        
        engine = db_connector.engine
        inspector = inspect(engine)
        
        results = []
        
        for table in tables:
            cache_key = cache._generate_key("table_schema", target_catalog, target_schema, table)
            
            # Try cache first
            cached_result = cache.get(cache_key)
            if cached_result:
                results.append(cached_result)
                logger.info(f"Returning cached schema for {table}")
                continue
            
            try:
                # Get columns for the table
                columns = inspector.get_columns(table, schema=target_schema)
                
                if not columns:
                    table_result = f"\nTable: {target_catalog}.{target_schema}.{table}\n  Error: Table not found"
                else:
                    table_result = f"\nTable: {target_catalog}.{target_schema}.{table}\nColumns:"
                    for col in columns:
                        col_name = col['name']
                        col_type = str(col['type'])
                        nullable = "NULL" if col.get('nullable', True) else "NOT NULL"
                        table_result += f"\n  - {col_name}: {col_type} ({nullable})"
                    
                    logger.info(f"Retrieved schema for {table}: {len(columns)} columns")
                
                # Cache the result
                cache.set(cache_key, table_result, config.CACHE_TTL_TABLE_SCHEMA)
                results.append(table_result)
                
            except Exception as e:
                error_result = f"\nTable: {target_catalog}.{target_schema}.{table}\n  Error: {str(e)}"
                results.append(error_result)
                logger.error(f"Error getting schema for {table}: {e}")
        
        return "\n".join(results)
        
    except Exception as e:
        error_msg = f"Error getting table schema: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"


@mcp.tool()
def databricks_execute_query(query: str, use_cache: bool = True) -> str:
    """
    Execute a SELECT query against Databricks SQL warehouse.
    
    IMPORTANT: Only SELECT queries are allowed. Any attempt to modify data will be rejected.
    
    Args:
        query: SQL SELECT query to execute
        use_cache: Whether to use cached results if available (default: True)
    
    Returns:
        Query results as a formatted string, or error message
    """
    try:
        # Validate query is read-only
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
        
        # Execute query
        logger.info(f"Executing query: {limited_query[:100]}...")
        engine = db_connector.engine
        
        with engine.connect() as conn:
            result = conn.execute(text(limited_query))
            rows = result.fetchall()
            columns = result.keys()
            
            if not rows:
                result_str = "Query executed successfully but returned no rows."
            else:
                # Format results
                result_str = f"Query returned {len(rows)} row(s):\n\n"
                result_str += "Columns: " + ", ".join(columns) + "\n\n"
                result_str += "Results:\n"
                result_str += str(rows)
                
                logger.info(f"Query successful: {len(rows)} rows returned")
        
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
def databricks_clear_cache(pattern: Optional[str] = None) -> str:
    """
    Clear cached data. Useful when data has been updated and you want fresh results.
    
    Args:
        pattern: Optional pattern to match specific cache keys. If not provided, clears all Databricks caches.
    
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
