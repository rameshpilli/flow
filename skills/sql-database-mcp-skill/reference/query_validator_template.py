# app/db/query_validator.py
import re
import logging
from typing import Tuple

logger = logging.getLogger("dbx_sql_mcp.db")


class QueryValidator:
    """Validates SQL queries for safety"""
    
    # Forbidden keywords that could modify data
    FORBIDDEN_KEYWORDS = [
        r'\bDELETE\b',
        r'\bINSERT\b',
        r'\bUPDATE\b',
        r'\bDROP\b',
        r'\bCREATE\b',
        r'\bALTER\b',
        r'\bTRUNCATE\b',
        r'\bREPLACE\b',
        r'\bMERGE\b',
        r'\bGRANT\b',
        r'\bREVOKE\b',
    ]
    
    @classmethod
    def validate(cls, query: str) -> Tuple[bool, str]:
        """
        Validate if query is safe (read-only SELECT)
        
        Args:
            query: SQL query to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not query or not query.strip():
            return False, "Query is empty"
        
        query_upper = query.upper()
        
        # Check for forbidden keywords
        for keyword_pattern in cls.FORBIDDEN_KEYWORDS:
            if re.search(keyword_pattern, query_upper):
                keyword = keyword_pattern.replace(r'\b', '').replace('\\', '')
                return False, f"Query contains forbidden keyword: {keyword}. Only SELECT queries are allowed."
        
        # Check if query starts with SELECT (allow CTEs with WITH)
        query_stripped = query_upper.strip()
        if not (query_stripped.startswith('SELECT') or query_stripped.startswith('WITH')):
            return False, "Query must be a SELECT statement or CTE (WITH clause)"
        
        # Check for multiple statements (potential SQL injection)
        if ';' in query.rstrip(';'):
            return False, "Multiple statements not allowed. Only single SELECT queries permitted."
        
        return True, ""
    
    @classmethod
    def add_limit(cls, query: str, max_rows: int) -> str:
        """
        Add LIMIT clause to query if not present
        
        Args:
            query: SQL query
            max_rows: Maximum rows to return
            
        Returns:
            Query with LIMIT clause
        """
        query_upper = query.upper()
        
        # Check if LIMIT already exists
        if re.search(r'\bLIMIT\s+\d+', query_upper):
            logger.debug("Query already has LIMIT clause")
            return query
        
        # Add LIMIT
        query_with_limit = f"{query.rstrip(';')} LIMIT {max_rows}"
        logger.debug(f"Added LIMIT {max_rows} to query")
        return query_with_limit
