"""
CMPT MCP Authentication

Token manager for connecting to internal MCP servers that require
custom JWT-based authentication with server secrets.

The auth scheme works as follows:
1. Create a user_id_token (JWT) with user info
2. Combine with server_secret and connector_access_tokens
3. Base64 encode the JSON payload
4. Use as Bearer token in Authorization header

Usage:
    from cmpt.mcp_auth import MCPAuthTokenManager, create_mcp_bearer_token

    # Option 1: Simple token generation
    token = create_mcp_bearer_token(
        server_secret="your-server-secret",
        email="user@example.com",
        name="John Doe",
    )

    # Use with MCPAdapterConfig
    from agentorchestrator.plugins import MCPAdapterConfig, MCPAdapterAgent

    config = MCPAdapterConfig(
        name="capiq",
        server_url="https://spcapiq-mcp.cfk.dev.com/mcp",
        headers={"Authorization": f"Bearer {token}"},
        verify_ssl=False,  # For internal self-signed certs
    )
    agent = MCPAdapterAgent(config)

    # Option 2: Token manager with caching and auto-refresh
    token_manager = MCPAuthTokenManager(
        server_secret="your-server-secret",
        user_email="user@example.com",
        user_name="John Doe",
        token_ttl_seconds=3600,
    )

    # Get token (cached if not expired)
    token = token_manager.get_bearer_token()

    # Use with MCPAdapterConfig
    config = MCPAdapterConfig(
        name="capiq",
        server_url="https://spcapiq-mcp.cfk.dev.com/mcp",
        headers=token_manager.get_auth_headers(),
        verify_ssl=False,
    )
"""

import json
import logging
import time
from base64 import b64encode
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AuthHeaderTokens:
    """
    Structure for MCP auth header tokens.

    Matches the server's expected format:
    {
        "server_secret": "...",
        "user_id_token": "jwt...",
        "connector_access_tokens": {"google": "abc", ...}
    }
    """

    server_secret: str
    user_id_token: str
    connector_access_tokens: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "server_secret": self.server_secret,
            "user_id_token": self.user_id_token,
            "connector_access_tokens": self.connector_access_tokens,
        }


def create_user_id_token(
    email: str,
    name: str,
    preferred_username: str | None = None,
    signing_key: str = "does-not-matter",
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a JWT user_id_token.

    Args:
        email: User's email address
        name: User's display name
        preferred_username: Preferred username (defaults to email)
        signing_key: JWT signing key (may not be validated by server)
        additional_claims: Additional JWT claims to include

    Returns:
        JWT token string

    Requires:
        pip install PyJWT
    """
    try:
        import jwt
    except ImportError:
        raise ImportError(
            "PyJWT package required for MCP auth. Install with: pip install PyJWT"
        )

    payload = {
        "email": email,
        "name": name,
        "preferred_username": preferred_username or email,
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(payload, signing_key, algorithm="HS256")


def create_mcp_bearer_token(
    server_secret: str,
    email: str,
    name: str,
    preferred_username: str | None = None,
    connector_tokens: dict[str, str] | None = None,
    signing_key: str = "does-not-matter",
) -> str:
    """
    Create a complete MCP Bearer token.

    This is the simplest way to generate a token for MCP authentication.

    Args:
        server_secret: Server secret for authentication
        email: User's email address
        name: User's display name
        preferred_username: Preferred username (defaults to email)
        connector_tokens: Access tokens for connectors (e.g., {"google": "abc"})
        signing_key: JWT signing key

    Returns:
        Base64-encoded Bearer token string

    Usage:
        token = create_mcp_bearer_token(
            server_secret=os.getenv("MCP_SERVER_SECRET"),
            email="user@example.com",
            name="John Doe",
        )

        # Use in curl:
        # curl -H "Authorization: Bearer {token}" ...

        # Use with MCPAdapterConfig:
        config = MCPAdapterConfig(
            name="my_mcp",
            server_url="https://mcp.example.com/mcp",
            headers={"Authorization": f"Bearer {token}"},
        )
    """
    # Create user_id_token JWT
    user_id_token = create_user_id_token(
        email=email,
        name=name,
        preferred_username=preferred_username,
        signing_key=signing_key,
    )

    # Build auth header structure
    header = AuthHeaderTokens(
        server_secret=server_secret,
        user_id_token=user_id_token,
        connector_access_tokens=connector_tokens or {},
    )

    # Base64 encode
    header_json = json.dumps(header.to_dict())
    return b64encode(header_json.encode()).decode()


class MCPAuthTokenManager:
    """
    Token manager for MCP servers with caching and auto-refresh.

    Caches the generated token and regenerates when expired.
    Thread-safe for concurrent access.

    Usage:
        token_manager = MCPAuthTokenManager(
            server_secret=os.getenv("MCP_SERVER_SECRET"),
            user_email="user@example.com",
            user_name="John Doe",
            token_ttl_seconds=3600,  # 1 hour
        )

        # Get token (regenerates if expired)
        token = token_manager.get_bearer_token()

        # Get complete auth headers
        headers = token_manager.get_auth_headers()

        # Use with MCPAdapterConfig
        config = MCPAdapterConfig(
            name="capiq",
            server_url="https://spcapiq-mcp.cfk.dev.com/mcp",
            headers=headers,
            verify_ssl=False,
        )
    """

    def __init__(
        self,
        server_secret: str,
        user_email: str,
        user_name: str,
        preferred_username: str | None = None,
        connector_tokens: dict[str, str] | None = None,
        token_ttl_seconds: int = 3600,
        signing_key: str = "does-not-matter",
    ):
        """
        Initialize MCP auth token manager.

        Args:
            server_secret: Server secret for authentication
            user_email: User's email address
            user_name: User's display name
            preferred_username: Preferred username (defaults to email)
            connector_tokens: Access tokens for connectors
            token_ttl_seconds: Token cache TTL in seconds (default: 1 hour)
            signing_key: JWT signing key
        """
        self._server_secret = server_secret
        self._user_email = user_email
        self._user_name = user_name
        self._preferred_username = preferred_username
        self._connector_tokens = connector_tokens or {}
        self._token_ttl = token_ttl_seconds
        self._signing_key = signing_key

        # Cache
        self._cached_token: str | None = None
        self._expires_at: float = 0

    def get_bearer_token(self) -> str:
        """
        Get Bearer token, regenerating if expired.

        Returns:
            Base64-encoded Bearer token string
        """
        now = time.time()

        if self._cached_token and now < self._expires_at:
            logger.debug("Using cached MCP auth token")
            return self._cached_token

        logger.debug("Generating new MCP auth token")
        self._cached_token = create_mcp_bearer_token(
            server_secret=self._server_secret,
            email=self._user_email,
            name=self._user_name,
            preferred_username=self._preferred_username,
            connector_tokens=self._connector_tokens,
            signing_key=self._signing_key,
        )
        self._expires_at = now + self._token_ttl

        return self._cached_token

    def get_auth_headers(self) -> dict[str, str]:
        """
        Get complete auth headers for MCP requests.

        Returns:
            Dict with Authorization header

        Usage:
            headers = token_manager.get_auth_headers()
            # headers = {"Authorization": "Bearer eyJ..."}
        """
        return {"Authorization": f"Bearer {self.get_bearer_token()}"}

    def invalidate(self) -> None:
        """
        Invalidate the cached token, forcing regeneration on next call.
        """
        self._cached_token = None
        self._expires_at = 0
        logger.debug("Invalidated MCP auth token cache")

    def update_connector_token(self, connector: str, token: str) -> None:
        """
        Update a connector access token.

        Args:
            connector: Connector name (e.g., "google")
            token: New access token
        """
        self._connector_tokens[connector] = token
        self.invalidate()  # Force token regeneration


class MCPAuthFromEnv(MCPAuthTokenManager):
    """
    MCP auth token manager that loads configuration from environment variables.

    Environment Variables:
        MCP_SERVER_SECRET: Server secret (required)
        MCP_USER_EMAIL: User email (required)
        MCP_USER_NAME: User display name (required)
        MCP_PREFERRED_USERNAME: Preferred username (optional)
        MCP_TOKEN_TTL: Token TTL in seconds (default: 3600)

    Usage:
        # Set environment variables, then:
        token_manager = MCPAuthFromEnv()
        headers = token_manager.get_auth_headers()
    """

    def __init__(self):
        import os

        server_secret = os.environ.get("MCP_SERVER_SECRET")
        user_email = os.environ.get("MCP_USER_EMAIL")
        user_name = os.environ.get("MCP_USER_NAME")

        if not server_secret:
            raise ValueError("MCP_SERVER_SECRET environment variable required")
        if not user_email:
            raise ValueError("MCP_USER_EMAIL environment variable required")
        if not user_name:
            raise ValueError("MCP_USER_NAME environment variable required")

        preferred_username = os.environ.get("MCP_PREFERRED_USERNAME")
        token_ttl = int(os.environ.get("MCP_TOKEN_TTL", "3600"))

        super().__init__(
            server_secret=server_secret,
            user_email=user_email,
            user_name=user_name,
            preferred_username=preferred_username,
            token_ttl_seconds=token_ttl,
        )


def create_mcp_adapter_with_auth(
    name: str,
    server_url: str,
    server_secret: str,
    user_email: str,
    user_name: str,
    verify_ssl: bool = False,
    **adapter_kwargs,
) -> "MCPAdapterAgent":
    """
    Convenience function to create an MCPAdapterAgent with auth configured.

    Args:
        name: MCP server name
        server_url: MCP server URL
        server_secret: Server secret for auth
        user_email: User email
        user_name: User display name
        verify_ssl: Whether to verify SSL (False for internal certs)
        **adapter_kwargs: Additional MCPAdapterConfig options

    Returns:
        Configured MCPAdapterAgent

    Usage:
        agent = create_mcp_adapter_with_auth(
            name="capiq",
            server_url="https://spcapiq-mcp.cfk.dev.com/mcp",
            server_secret=os.getenv("MCP_SERVER_SECRET"),
            user_email="user@example.com",
            user_name="John Doe",
        )

        await agent.initialize()
        tools = await agent.list_tools()
        result = await agent.call_tool("get_latest", {})
    """
    from agentorchestrator.plugins import MCPAdapterAgent, MCPAdapterConfig

    # Create token manager
    token_manager = MCPAuthTokenManager(
        server_secret=server_secret,
        user_email=user_email,
        user_name=user_name,
    )

    # Create config with auth headers
    config = MCPAdapterConfig(
        name=name,
        server_url=server_url,
        headers=token_manager.get_auth_headers(),
        verify_ssl=verify_ssl,
        **adapter_kwargs,
    )

    return MCPAdapterAgent(config)


# Export public API
__all__ = [
    "AuthHeaderTokens",
    "MCPAuthFromEnv",
    "MCPAuthTokenManager",
    "create_mcp_adapter_with_auth",
    "create_mcp_bearer_token",
    "create_user_id_token",
]
