"""PostgreSQL connector with environment-based configuration.

This module provides a reusable PostgreSQL connection manager that uses
environment variables for configuration and connection pooling for efficiency.

Environment Variables:
    PG_HOST - PostgreSQL host (default: localhost)
    PG_PORT - PostgreSQL port (default: 5432)
    PG_DATABASE - Database name (required)
    PG_USERNAME - Database username (required)
    PG_PASSWORD - Database password (required)

Example:
    # .env
    PG_HOST=localhost
    PG_PORT=5432
    PG_DATABASE=mydb
    PG_USERNAME=user
    PG_PASSWORD=pass

    # Code
    from agentorchestrator.services.postgresql import PostgreSQLManager

    db = PostgreSQLManager()

    # Query data
    results = db.execute_query(
        "SELECT * FROM users WHERE id = %s",
        params=(123,),
        fetch=True
    )

    # Insert data
    db.execute_query(
        "INSERT INTO users (name, email) VALUES (%s, %s)",
        params=("John", "john@example.com")
    )

    # Cleanup
    db.close()
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration from environment variables."""

    @staticmethod
    def get_host() -> str:
        return os.getenv("PG_HOST", "localhost")

    @staticmethod
    def get_port() -> str:
        return os.getenv("PG_PORT", "5432")

    @staticmethod
    def get_database() -> str:
        return os.getenv("PG_DATABASE", "")

    @staticmethod
    def get_username() -> str:
        return os.getenv("PG_USERNAME", "")

    @staticmethod
    def get_password() -> str:
        return os.getenv("PG_PASSWORD", "")

    @classmethod
    def validate(cls) -> bool:
        """Validate that required database configuration is present.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If required configuration is missing
        """
        if not cls.get_database():
            raise ValueError("PG_DATABASE is required in environment variables")
        if not cls.get_username():
            raise ValueError("PG_USERNAME is required in environment variables")
        if not cls.get_password():
            raise ValueError("PG_PASSWORD is required in environment variables")
        return True

    @classmethod
    def get_connection_string(cls) -> str:
        """Get PostgreSQL connection string for debugging (password masked).

        Returns:
            Connection string with masked password
        """
        return (
            f"postgresql://{cls.get_username()}:***@"
            f"{cls.get_host()}:{cls.get_port()}/{cls.get_database()}"
        )


class PostgreSQLManager:
    """PostgreSQL connection manager with connection pooling.

    Provides a simple, reusable way to connect to PostgreSQL and execute queries.
    Uses connection pooling for efficient resource management.

    Attributes:
        connection_pool: psycopg2 connection pool

    Example:
        # Initialize
        db = PostgreSQLManager(min_connections=1, max_connections=10)

        # Use context manager
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users")
                results = cursor.fetchall()

        # Or use helper method
        results = db.execute_query(
            "SELECT * FROM users WHERE active = %s",
            params=(True,),
            fetch=True
        )

        # Cleanup
        db.close()
    """

    def __init__(self, min_connections: int = 1, max_connections: int = 10):
        """Initialize the PostgreSQL manager with connection pooling.

        Args:
            min_connections: Minimum number of connections in the pool
            max_connections: Maximum number of connections in the pool

        Raises:
            ImportError: If psycopg2 is not installed
            ValueError: If required configuration is missing
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for PostgreSQL connector. "
                "Install it with: pip install psycopg2-binary"
            )

        DatabaseConfig.validate()

        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                min_connections,
                max_connections,
                host=DatabaseConfig.get_host(),
                port=DatabaseConfig.get_port(),
                database=DatabaseConfig.get_database(),
                user=DatabaseConfig.get_username(),
                password=DatabaseConfig.get_password(),
            )
            logger.info(
                f"PostgreSQL connection pool created successfully "
                f"(host: {DatabaseConfig.get_host()}, "
                f"database: {DatabaseConfig.get_database()})"
            )
        except Exception as e:
            logger.error(f"Failed to create PostgreSQL connection pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool (context manager).

        Yields:
            Database connection

        Example:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM table")
                    results = cursor.fetchall()
        """
        connection = None
        try:
            connection = self.connection_pool.getconn()
            yield connection
        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if connection:
                self.connection_pool.putconn(connection)

    def execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
        fetch: bool = False,
        commit: bool = True,
    ) -> Optional[List[Dict[str, Any]]]:
        """Execute a SQL query.

        Args:
            query: SQL query to execute
            params: Query parameters (tuple)
            fetch: Whether to fetch and return results
            commit: Whether to commit the transaction

        Returns:
            List of result dictionaries if fetch=True, None otherwise

        Example:
            # Insert data
            db.execute_query(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                params=("John", "john@example.com"),
                commit=True
            )

            # Query data
            results = db.execute_query(
                "SELECT * FROM users WHERE name = %s",
                params=("John",),
                fetch=True
            )
        """
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)

                if fetch:
                    results = cursor.fetchall()
                    return [dict(row) for row in results]

                if commit:
                    conn.commit()

                return None

    def close(self) -> None:
        """Close all connections in the pool."""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("PostgreSQL connection pool closed")


# Global singleton instance (optional - for convenience)
_db_manager: Optional[PostgreSQLManager] = None


def get_db_manager() -> PostgreSQLManager:
    """Get or create a global database manager instance.

    Returns:
        PostgreSQLManager instance

    Example:
        from agentorchestrator.services.postgresql import get_db_manager

        db = get_db_manager()

        # Use context manager
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users")
                results = cursor.fetchall()

        # Or use execute_query helper
        results = db.execute_query(
            "SELECT * FROM users WHERE id = %s",
            params=(123,),
            fetch=True
        )
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = PostgreSQLManager()
    return _db_manager