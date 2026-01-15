# app/config.py
import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional

load_dotenv()


def _parse_int(value: str, default: int) -> int:
    """Parse int from env var, stripping any surrounding quotes."""
    if not value:
        return default
    # Strip surrounding single or double quotes (from Helm ConfigMap)
    cleaned = value.strip().strip("'").strip('"')
    try:
        return int(cleaned)
    except ValueError:
        return default


def _parse_bool(value: str, default: bool) -> bool:
    """Parse bool from env var, stripping any surrounding quotes."""
    if not value:
        return default
    # Strip surrounding single or double quotes (from Helm ConfigMap)
    cleaned = value.strip().strip("'").strip('"').lower()
    return cleaned == "true"


class Config:
    BASE_DIR = Path(__file__).resolve().parent.parent

    # Databricks Connection
    DATABRICKS_HOST: str = os.getenv("DATABRICKS_HOST", "")
    DATABRICKS_TOKEN: str = os.getenv("DATABRICKS_TOKEN", "")
    DATABRICKS_SQL_WAREHOUSE_ID: str = os.getenv("DATABRICKS_SQL_WAREHOUSE_ID", "")
    
    # Optional: Scope to specific catalog/schema
    DATABRICKS_CATALOG: Optional[str] = os.getenv("DATABRICKS_CATALOG")
    DATABRICKS_SCHEMA: Optional[str] = os.getenv("DATABRICKS_SCHEMA")

    # Server Configuration
    MCP_SERVER_PORT: int = _parse_int(os.getenv("MCP_SERVER_PORT", ""), 8000)
    MCP_SERVER_HOST: str = os.getenv("MCP_SERVER_HOST", "0.0.0.0")

    # Query limits
    MAX_QUERY_ROWS: int = _parse_int(os.getenv("MAX_QUERY_ROWS", ""), 1000)
    QUERY_TIMEOUT_SECONDS: int = _parse_int(os.getenv("QUERY_TIMEOUT_SECONDS", ""), 30)

    # Redis Cache settings
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = _parse_int(os.getenv("REDIS_PORT", ""), 6379)
    REDIS_DB: int = _parse_int(os.getenv("REDIS_DB", ""), 0)
    ENABLE_CACHING: bool = _parse_bool(os.getenv("ENABLE_CACHING", ""), True)

    # Cache TTL settings (in seconds)
    CACHE_TTL_TABLES_LIST: int = _parse_int(os.getenv("CACHE_TTL_TABLES_LIST", ""), 3600)  # 1 hour
    CACHE_TTL_TABLE_SCHEMA: int = _parse_int(os.getenv("CACHE_TTL_TABLE_SCHEMA", ""), 7200)  # 2 hours
    CACHE_TTL_QUERY_RESULTS: int = _parse_int(os.getenv("CACHE_TTL_QUERY_RESULTS", ""), 300)  # 5 minutes

    # Authentication
    AUTH_SERVER_SECRET: Optional[str] = os.getenv("AUTH_SERVER_SECRET")

    # Logging
    LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_TO_STDOUT: bool = os.getenv("LOG_TO_STDOUT", "true").lower() == "true"

    # Development mode
    DEVELOPMENT: bool = os.getenv("DEVELOPMENT", "false").lower() == "true"

    @classmethod
    def validate_required_config(cls) -> list[str]:
        """Check for missing required configuration values"""
        missing = []
        if not cls.DATABRICKS_HOST:
            missing.append("DATABRICKS_HOST")
        if not cls.DATABRICKS_TOKEN:
            missing.append("DATABRICKS_TOKEN")
        if not cls.DATABRICKS_SQL_WAREHOUSE_ID:
            missing.append("DATABRICKS_SQL_WAREHOUSE_ID")
        return missing

    @classmethod
    def get_connection_string(cls) -> str:
        """Generate Databricks connection string for SQLAlchemy"""
        # Build the base connection string
        conn_str = (
            f"databricks://token:{cls.DATABRICKS_TOKEN}@{cls.DATABRICKS_HOST}?"
            f"http_path=/sql/1.0/warehouses/{cls.DATABRICKS_SQL_WAREHOUSE_ID}"
        )
        
        # Add catalog and schema if specified
        if cls.DATABRICKS_CATALOG:
            conn_str += f"&catalog={cls.DATABRICKS_CATALOG}"
        if cls.DATABRICKS_SCHEMA:
            conn_str += f"&schema={cls.DATABRICKS_SCHEMA}"
            
        return conn_str


config = Config()
