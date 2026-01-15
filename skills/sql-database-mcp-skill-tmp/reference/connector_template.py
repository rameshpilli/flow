# app/db/connector.py
import logging
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from app.config import config

logger = logging.getLogger("dbx_sql_mcp.db")


class DatabricksConnector:
    """Manages Databricks SQL connection"""
    
    def __init__(self):
        self._engine: Optional[Engine] = None
    
    @property
    def engine(self) -> Engine:
        """Get or create SQLAlchemy engine"""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine
    
    def _create_engine(self) -> Engine:
        """Create SQLAlchemy engine for Databricks"""
        connection_string = config.get_connection_string()
        
        logger.info("Creating Databricks SQL connection...")
        logger.info(f"  Host: {config.DATABRICKS_HOST}")
        logger.info(f"  Warehouse: {config.DATABRICKS_SQL_WAREHOUSE_ID}")
        if config.DATABRICKS_CATALOG:
            logger.info(f"  Catalog: {config.DATABRICKS_CATALOG}")
        if config.DATABRICKS_SCHEMA:
            logger.info(f"  Schema: {config.DATABRICKS_SCHEMA}")
        
        try:
            engine = create_engine(
                connection_string,
                connect_args={
                    "http_path": f"/sql/1.0/warehouses/{config.DATABRICKS_SQL_WAREHOUSE_ID}",
                    "catalog": config.DATABRICKS_CATALOG or "default",
                    "schema": config.DATABRICKS_SCHEMA or "default",
                },
                echo=config.DEVELOPMENT,  # Log SQL in development mode
            )
            
            # Test connection
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            
            logger.info("✓ Databricks SQL connection established")
            return engine
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Databricks: {e}")
            raise
    
    def test_connection(self) -> bool:
        """Test if connection is working"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def close(self):
        """Close database connection"""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            logger.info("Databricks connection closed")


# Global connector instance
db_connector = DatabricksConnector()
