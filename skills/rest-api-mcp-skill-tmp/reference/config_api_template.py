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

    # Query Services
    QUERY_SERVICES_BASE_URL: Optional[str] = os.getenv("QUERY_SERVICES_BASE_URL")
    QUERY_SERVICES_AUTH_TOKEN: Optional[str] = os.getenv("QUERY_SERVICES_AUTH_TOKEN")

    # Elasticsearch
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "")
    ELASTICSEARCH_AUTH_TOKEN: str = os.getenv("ELASTICSEARCH_AUTH_TOKEN", "")
    ELASTICSEARCH_TIMEOUT: int = int(os.getenv("ELASTICSEARCH_TIMEOUT", "15"))

    # Logging
    LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_TO_STDOUT: bool = os.getenv("LOG_TO_STDOUT", "true").lower() == "true"

    # Authentication
    AUTH_SERVER_SECRET: Optional[str] = os.getenv("AUTH_SERVER_SECRET")
    LDAP_SERVICE: Optional[str] = os.getenv("LDAP_SERVICE")

    # Client Services
    CLIENT_CONTACT_SERVICE_URL: Optional[str] = os.getenv("CLIENT_CONTACT_SERVICE_URL")
    CLIENT_COVERAGE_SERVICE_URL: Optional[str] = os.getenv("CLIENT_COVERAGE_SERVICE_URL")
    CLIENT_HIERARCHY_SERVICE_URL: Optional[str] = os.getenv("CLIENT_HIERARCHY_SERVICE_URL")
    INTERACTION_SERVICE_URL: Optional[str] = os.getenv("INTERACTION_SERVICE_URL")
    MEETING_REPORTS_SERVICE_URL: Optional[str] = os.getenv("MEETING_REPORTS_SERVICE_URL")

    # Performance settings
    DEVELOPMENT: bool = os.getenv("DEVELOPMENT", "false").lower() == "true"

    # Redis Cache settings
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = _parse_int(os.getenv("REDIS_PORT", ""), 6379)
    REDIS_DB: int = _parse_int(os.getenv("REDIS_DB", ""), 0)
    ENABLE_CACHING: bool = _parse_bool(os.getenv("ENABLE_CACHING", ""), True)

    # Cache TTL settings (in seconds)
    CACHE_TTL_CLIENT_SEARCH: int = _parse_int(os.getenv("CACHE_TTL_CLIENT_SEARCH", ""), 3600)  # 1 hour
    CACHE_TTL_DAILY_TRADES: int = _parse_int(os.getenv("CACHE_TTL_DAILY_TRADES", ""), 300)  # 5 minutes
    CACHE_TTL_CLIENT_COVERAGE: int = _parse_int(os.getenv("CACHE_TTL_CLIENT_COVERAGE", ""), 1800)  # 30 minutes

    # MCP Context Caching (for FastMCP state caching)
    ENABLE_CONTEXT_CACHING: bool = _parse_bool(os.getenv("ENABLE_CONTEXT_CACHING", ""), True)
    CONTEXT_CACHE_MAX_AGE: int = _parse_int(os.getenv("CONTEXT_CACHE_MAX_AGE", ""), 300)  # 5 minutes

    @classmethod
    def validate_required_config(cls) -> list[str]:
        """Check for missing required configuration values"""
        missing = []
        if not cls.QUERY_SERVICES_BASE_URL:
            missing.append("QUERY_SERVICES_BASE_URL")
        if not cls.QUERY_SERVICES_AUTH_TOKEN:
            missing.append("QUERY_SERVICES_AUTH_TOKEN")
        if not cls.ELASTICSEARCH_URL:
            missing.append("ELASTICSEARCH_URL")
        if not cls.CLIENT_CONTACT_SERVICE_URL:
            missing.append("CLIENT_CONTACT_SERVICE_URL")
        if not cls.CLIENT_COVERAGE_SERVICE_URL:
            missing.append("CLIENT_COVERAGE_SERVICE_URL")
        if not cls.CLIENT_HIERARCHY_SERVICE_URL:
            missing.append("CLIENT_HIERARCHY_SERVICE_URL")
        if not cls.INTERACTION_SERVICE_URL:
            missing.append("INTERACTION_SERVICE_URL")
        if not cls.MEETING_REPORTS_SERVICE_URL:
            missing.append("MEETING_REPORTS_SERVICE_URL")
        return missing


config = Config()
