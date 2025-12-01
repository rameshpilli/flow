"""Application configuration."""

import os
import json
from dotenv import load_dotenv

load_dotenv()


class Config:
    # App Settings
    APP_NAME = os.getenv("APP_NAME", "MCP Repository")
    APP_DESCRIPTION = os.getenv("APP_DESCRIPTION", "Model Context Protocol Server")
    APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
    MCP_NAME = os.getenv("MCP_NAME", "Model Context Protocol Server")

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Chain Server Cache
    CHAIN_SERVER_CACHE_HOURS = os.getenv("CHAIN_SERVER_CACHE_HOURS", "1")
    CHAIN_SERVER_CACHE_MAXSIZE = os.getenv("CHAIN_SERVER_CACHE_MAXSIZE", "1024")

    # Context Builder Cache
    CONTEXT_BUILDER_CACHE_SECONDS = os.getenv("CONTEXT_BUILDER_CACHE_SECONDS", "3600")
    CONTEXT_BUILDER_CACHE_SIZE = os.getenv("CONTEXT_BUILDER_CACHE_SIZE", "128")

    # LLM
    LLM_MODEL_ENGINE = os.getenv("LLM_MODEL_ENGINE", "llm_gateway")
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "us.anthropic.claude-sonnet-4-20250514-v1:0")
    LLM_SERVER_URL = os.getenv("LLM_SERVER_URL")
    LLM_MAX_TOKENS = os.getenv("LLM_MAX_TOKENS", "16000")
    LLM_TEMPERATURE = os.getenv("LLM_TEMPERATURE", "0.2")
    LLM_TOP_P = os.getenv("LLM_TOP_P", "0.9")
    LLM_OAUTH_ENDPOINT = os.getenv("LLM_OAUTH_ENDPOINT")
    LLM_CLIENT_ID = os.getenv("LLM_CLIENT_ID")
    LLM_CLIENT_SECRET = os.getenv("LLM_CLIENT_SECRET")

    # Foundation Service
    FOUNDATION_COMPANY_MATCHES = os.getenv("FOUNDATION_COMPANY_MATCHES")
    FOUNDATION_EARNING_CALENDAR_URL = os.getenv("FOUNDATION_EARNING_CALENDAR_URL")

    # LDAP
    LDAP_DOMAIN = os.getenv("LDAP_DOMAIN")
    LDAP_SERVER = os.getenv("LDAP_SERVER")
    LDAP_USERNAME = os.getenv("LDAP_USERNAME")
    LDAP_PASSWORD = os.getenv("LDAP_PASSWORD")
    LDAP_USER_DN = os.getenv("LDAP_USER_DN")

    # Snowflake
    SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
    SNOWFLAKE_HOST = os.getenv("SNOWFLAKE_HOST")
    SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE")
    SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER")
    SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
    SNOWFLAKE_ROLE = os.getenv("SNOWFLAKE_ROLE")
    SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE")
    SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA")
    SNOWFLAKE_TABLES = os.getenv("SNOWFLAKE_TABLES")
    SNOWFLAKE_CACHE_TTL = os.getenv("SNOWFLAKE_CACHE_TTL", "1440")

    # Databricks
    DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
    DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
    DATABRICKS_CLUSTER_ID = os.getenv("DATABRICKS_CLUSTER_ID")
    DATABRICKS_CATALOG = os.getenv("DATABRICKS_CATALOG")
    DATABRICKS_SCHEMA = os.getenv("DATABRICKS_SCHEMA")
    DATABRICKS_TABLE = os.getenv("DATABRICKS_TABLE")
    DATABRICKS_TABLE_PREFIX = os.getenv("DATABRICKS_TABLE_PREFIX")
    DATABRICKS_VOLUME = os.getenv("DATABRICKS_VOLUME")
    DATABRICKS_LOCAL_FOLDER = os.getenv("DATABRICKS_LOCAL_FOLDER", "data/epai")
    DATABRICKS_META_FILE = os.getenv("DATABRICKS_META_FILE")
    DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH")
    DATABRICKS_EARNINGS_TRANSCRIPT_TABLE = os.getenv("DATABRICKS_EARNINGS_TRANSCRIPT_TABLE")

    # Cohere/Compass
    COHERE_MODEL_ENGINE = os.getenv("COHERE_MODEL_ENGINE", "cohere-rag")
    COHERE_API_URL = os.getenv("COHERE_API_URL")
    COHERE_PARSER_URL = os.getenv("COHERE_PARSER_URL")
    COHERE_USER_TOKEN = os.getenv("COHERE_USER_TOKEN")
    COHERE_PARSER_TOKEN = os.getenv("COHERE_PARSER_TOKEN")
    COHERE_IDX_PREFIX = os.getenv("COHERE_IDX_PREFIX")
    COHERE_IDX_SUFFIX = os.getenv("COHERE_IDX_SUFFIX")

    # Chunking
    CHUNK_ENGINE = os.getenv("CHUNK_ENGINE", "LlamaIndexTextChunker")
    CHUNK_SIZE = os.getenv("CHUNK_SIZE", "4096")
    CHUNK_OVERLAP = os.getenv("CHUNK_OVERLAP", "0")

    # ZoomInfo
    ZOOM_INFO_URL = os.getenv("ZOOM_INFO_URL")
    ZOOM_INFO_USERNAME = os.getenv("ZOOM_INFO_USERNAME")
    ZOOM_INFO_PASSWORD = os.getenv("ZOOM_INFO_PASSWORD")

    # Auth
    MCP_SERVER_SECRET = os.getenv("MCP_SERVER_SECRET")

    # MCP Agents (JSON array)
    AGENT_CONFIG = os.getenv("AGENT_CONFIG", "[]")

    # RAG Agents (JSON array)
    RAG_AGENT_CONFIG = os.getenv("RAG_AGENT_CONFIG", "[]")

    @classmethod
    def get_agents(cls) -> list[dict]:
        """Parse and return list of MCP agent configs."""
        return json.loads(cls.AGENT_CONFIG)

    @classmethod
    def get_agent(cls, name: str) -> dict | None:
        """Get a specific MCP agent config by name."""
        for agent in cls.get_agents():
            if agent.get("name") == name:
                return agent
        return None

    @classmethod
    def get_rag_agents(cls) -> list[dict]:
        """Parse and return list of RAG agent configs."""
        return json.loads(cls.RAG_AGENT_CONFIG)


config = Config
