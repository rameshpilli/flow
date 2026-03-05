"""Production-ready MCP client with session management and JWT authentication.

This module provides a production-ready MCP (Model Context Protocol) client implementation
that properly handles:
- JWT bearer token authentication with caching
- Session initialization and management
- Server-Sent Events (SSE) response format
- JSON-RPC 2.0 protocol
- Path-based routing (RavenPack-style) vs single-endpoint JSON-RPC (CapIQ-style)

By default, the MCP client generates bearer tokens using JWT encoding with user
credentials and server secret.

Example:
    # Using MCPSession context manager (recommended)
    async with MCPSession(
        endpoint="https://mcp-server.example.com",
        client_secret="secret123",
        use_path_routing=True
    ) as session:
        tools = await session.list_tools()
        result = await session.call_tool("search", {"query": "test"})
"""

import hashlib
import json
import logging
import os
from base64 import b64encode
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
import jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Global token cache
_bearer_token: Optional[str] = None
_bearer_token_expires: Optional[datetime] = None
_bearer_token_secret: Optional[str] = None


class AuthHeaderTokens(BaseModel):
    """Authentication header tokens model for MCP JWT encoding."""

    server_secret: str
    user_id_token: str
    connector_access_tokens: Dict[str, str] = {}


def create_bearer_token(
    email: str,
    name: str,
    preferred_username: str,
    server_secret: str,
) -> str:
    """Create a bearer token using JWT encoding and base64.

    Args:
        email: User email address
        name: User full name
        preferred_username: Preferred username
        server_secret: MCP server secret

    Returns:
        Base64-encoded bearer token string

    Example:
        token = create_bearer_token(
            email="user@example.com",
            name="Test User",
            preferred_username="testuser",
            server_secret="secret123"
        )
    """
    user_id_token = jwt.encode(
        payload={
            "email": email,
            "name": name,
            "preferred_username": preferred_username,
        },
        key="does-not-matter",
    )

    header = AuthHeaderTokens(
        server_secret=server_secret,
        user_id_token=user_id_token,
        connector_access_tokens={"google": "abc"},
    )

    header_as_json = json.dumps(header.model_dump())
    header_as_b64 = b64encode(header_as_json.encode()).decode()
    return header_as_b64


def verify_bearer_token(authorization: str, server_secret: str) -> bool:
    """Verify an inbound MCP bearer token produced by create_bearer_token().

    This is the server-side complement to create_bearer_token().  Use it in
    MCP server endpoints to authenticate requests from Cohere North or any
    other MCP client that was configured with the same server_secret.

    The token is a base64-encoded JSON object (AuthHeaderTokens) containing
    the server_secret used at token-creation time.  We decode it and compare
    the embedded secret against the expected value.

    Args:
        authorization: Full value of the Authorization header,
                       e.g. "Bearer <base64-encoded-token>".
        server_secret: The shared secret this MCP server was initialised with.

    Returns:
        True if the token is authentic, False otherwise.

    Example:
        ok = verify_bearer_token(
            request.headers.get("Authorization", ""),
            server_secret="my-corp-secret",
        )
        if not ok:
            raise HTTPException(status_code=401)
    """
    try:
        token = authorization.removeprefix("Bearer ").strip()
        decoded = b64decode(token.encode()).decode()
        payload = json.loads(decoded)
        return payload.get("server_secret") == server_secret
    except Exception:
        return False


async def get_bearer_token_async(
    email: Optional[str] = None,
    name: Optional[str] = None,
    preferred_username: Optional[str] = None,
    server_secret: Optional[str] = None,
    force_refresh: bool = False,
    cache_ttl: int = 3600,
) -> str:
    """Get bearer token with automatic caching and refresh.

    Args:
        email: User email (uses MCP_USER_EMAIL from env if not provided)
        name: User name (uses MCP_USER_NAME from env if not provided)
        preferred_username: Preferred username (uses MCP_USERNAME from env if not provided)
        server_secret: MCP server secret (uses MCP_SECRET from env if not provided)
        force_refresh: Force token refresh even if cached token is valid
        cache_ttl: Cache time-to-live in seconds (default: 3600)

    Returns:
        Bearer token string

    Raises:
        ValueError: If required configuration is missing

    Example:
        token = await get_bearer_token_async()
    """
    global _bearer_token, _bearer_token_expires, _bearer_token_secret

    # Get configuration from environment
    email_val = email or os.getenv("MCP_USER_EMAIL")
    name_val = name or os.getenv("MCP_USER_NAME", "MCP User")
    username_val = preferred_username or os.getenv("MCP_USERNAME", "mcp_user")
    secret_val = server_secret or os.getenv("MCP_SECRET")

    if not email_val:
        raise ValueError(
            "User email not configured. Set MCP_USER_EMAIL in .env or pass as argument."
        )
    if not secret_val:
        raise ValueError(
            "Server secret not configured. Set MCP_SECRET in .env or pass as argument."
        )

    # Return cached token only if still valid AND secret hasn't changed
    if (
        not force_refresh
        and _bearer_token
        and _bearer_token_expires
        and _bearer_token_secret
    ):
        if _bearer_token_expires > datetime.now() and _bearer_token_secret == secret_val:
            return _bearer_token

    # Generate new bearer token
    token = create_bearer_token(
        email=email_val,
        name=name_val,
        preferred_username=username_val,
        server_secret=secret_val,
    )

    # Cache token with secret
    _bearer_token = token
    _bearer_token_expires = datetime.now() + timedelta(seconds=cache_ttl)
    _bearer_token_secret = secret_val

    return token


def parse_sse_response(text: str) -> dict:
    """Parse Server-Sent Events (SSE) format response.

    Args:
        text: Raw SSE response text (e.g., "event: message\\ndata: {json}\\n\\n")

    Returns:
        Parsed JSON data from the SSE event

    Example:
        response_text = "data: {\\"result\\": {\\"tools\\": []}}\\n\\n"
        data = parse_sse_response(response_text)
    """
    lines = text.strip().split("\n")
    data_lines = []

    for line in lines:
        if line.startswith("data: "):
            data_lines.append(line[6:])

    if data_lines:
        json_str = "\n".join(data_lines)
        return json.loads(json_str)

    return {}


async def initialize_mcp_session(
    mcp_server_url: Optional[str] = None,
    bearer_token: Optional[str] = None,
    client_secret: Optional[str] = None,
    use_token_generation: bool = True,
    timeout: int = 30,
    verify_ssl: bool = True,
    use_path_routing: bool = True,
) -> Tuple[str, httpx.AsyncClient]:
    """Initialize an MCP session and return the session ID and client.

    Args:
        mcp_server_url: MCP server URL (uses MCP_ENDPOINT from env if not provided)
        bearer_token: Bearer token for auth (not used if use_token_generation=True)
        client_secret: MCP server secret (uses MCP_SECRET from env if not provided)
        use_token_generation: If True, generate bearer token using JWT encoding (default: True)
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
        use_path_routing: If True, use path-based routing (e.g., /initialize) for RavenPack-style endpoints

    Returns:
        Tuple of (session_id, async_client) - keep the client alive for the session

    Raises:
        ValueError: If configuration is missing
        httpx.HTTPError: If request fails

    Example:
        session_id, client = await initialize_mcp_session()
        try:
            # Use session
            pass
        finally:
            await client.aclose()
    """
    raw_url = mcp_server_url or os.getenv("MCP_ENDPOINT", "")

    if not raw_url:
        raise ValueError(
            "MCP server URL not configured. Set MCP_ENDPOINT in .env or pass as argument."
        )

    # Use pre-generated bearer token if provided and token generation is disabled
    if bearer_token and not use_token_generation:
        token = bearer_token
    else:
        # Generate JWT token (default)
        try:
            token = await get_bearer_token_async(server_secret=client_secret)
        except ValueError as e:
            raise ValueError(
                f"Bearer token generation failed: {str(e)}\n"
                "Make sure the following are configured in .env:\n"
                "  - MCP_USER_EMAIL\n"
                "  - MCP_SECRET\n"
                "  - MCP_USER_NAME (optional)\n"
                "  - MCP_USERNAME (optional)"
            ) from e

    secret = client_secret or os.getenv("MCP_SECRET")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    if secret:
        headers["X-Client-Secret"] = secret

    # Enable redirect following to handle 307 redirects
    client = httpx.AsyncClient(
        timeout=timeout, verify=verify_ssl, follow_redirects=True
    )

    # Determine URL based on routing style
    if use_path_routing:
        url = raw_url.rstrip("/")
        request_url = f"{url}/initialize"
    else:
        # Use URL exactly as provided (including trailing slash if present)
        request_url = raw_url

    response = await client.post(
        request_url,
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
                "clientInfo": {
                    "name": "agentorchestrator",
                    "version": "1.0.0",
                },
            },
        },
    )

    response.raise_for_status()

    # Get session ID from headers
    session_id = response.headers.get("mcp-session-id")

    if not session_id:
        # Try alternative header names as fallback
        alt_headers = ["X-Session-Id", "x-session-id"]
        for alt_header in alt_headers:
            session_id = response.headers.get(alt_header)
            if session_id:
                break

    if not session_id:
        # Generate a local session ID if server doesn't provide one
        import uuid

        session_id = str(uuid.uuid4().hex)

    return session_id, client


async def list_mcp_tools(
    session_id: str,
    mcp_server_url: Optional[str] = None,
    bearer_token: Optional[str] = None,
    client_secret: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    use_token_generation: bool = True,
    timeout: int = 30,
    verify_ssl: bool = True,
    use_path_routing: bool = True,
) -> list:
    """Get list of available MCP tools.

    Args:
        session_id: MCP session ID from initialize_mcp_session
        mcp_server_url: MCP server URL (uses MCP_ENDPOINT from env if not provided)
        bearer_token: Pre-generated bearer token (used when use_token_generation=False)
        client_secret: MCP server secret (uses MCP_SECRET from env if not provided)
        client: Optional existing httpx client (will create new one if not provided)
        use_token_generation: If True, generate bearer token using JWT encoding
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
        use_path_routing: If True, use path-based routing (e.g., /tools/list)

    Returns:
        List of available tools

    Example:
        session_id, client = await initialize_mcp_session()
        try:
            tools = await list_mcp_tools(session_id, client=client)
            for tool in tools:
                print(f"Tool: {tool['name']}")
        finally:
            await client.aclose()
    """
    raw_url = mcp_server_url or os.getenv("MCP_ENDPOINT", "")

    # Use pre-generated bearer token if provided and token generation is disabled
    if bearer_token and not use_token_generation:
        token = bearer_token
    else:
        token = await get_bearer_token_async(server_secret=client_secret)

    secret = client_secret or os.getenv("MCP_SECRET")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "mcp-session-id": session_id,
    }

    if secret:
        headers["X-Client-Secret"] = secret

    # Determine URL based on routing style
    if use_path_routing:
        url = raw_url.rstrip("/")
        request_url = f"{url}/tools/list"
    else:
        request_url = raw_url

    # Use provided client or create temporary one
    if client:
        response = await client.post(
            request_url,
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
    else:
        async with httpx.AsyncClient(timeout=timeout, verify=verify_ssl) as temp_client:
            response = await temp_client.post(
                request_url,
                headers=headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )

    response.raise_for_status()

    # Parse SSE response
    data = parse_sse_response(response.text)

    # Extract tools from JSON-RPC response
    if isinstance(data, dict) and "result" in data:
        result = data["result"]
        if isinstance(result, dict) and "tools" in result:
            return result["tools"]
        elif isinstance(result, list):
            return result

    return []


async def call_mcp_tool(
    tool_name: str,
    arguments: dict,
    session_id: str,
    mcp_server_url: Optional[str] = None,
    bearer_token: Optional[str] = None,
    client_secret: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    use_token_generation: bool = True,
    timeout: int = 30,
    verify_ssl: bool = True,
    use_path_routing: bool = True,
) -> dict:
    """Call an MCP tool and return the result.

    Args:
        tool_name: Name of the MCP tool to call
        arguments: Dictionary of arguments to pass to the tool
        session_id: MCP session ID from initialize_mcp_session
        mcp_server_url: MCP server URL (uses MCP_ENDPOINT from env if not provided)
        bearer_token: Pre-generated bearer token (used when use_token_generation=False)
        client_secret: MCP server secret (uses MCP_SECRET from env if not provided)
        client: Optional existing httpx client (will create new one if not provided)
        use_token_generation: If True, generate bearer token using JWT encoding
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
        use_path_routing: If True, use path-based routing (e.g., /tools/call)

    Returns:
        Tool execution result as dict

    Example:
        session_id, client = await initialize_mcp_session()
        try:
            result = await call_mcp_tool(
                "search",
                {"query": "test"},
                session_id,
                client=client
            )
        finally:
            await client.aclose()
    """
    raw_url = mcp_server_url or os.getenv("MCP_ENDPOINT", "")

    # Use pre-generated bearer token if provided and token generation is disabled
    if bearer_token and not use_token_generation:
        token = bearer_token
    else:
        token = await get_bearer_token_async(server_secret=client_secret)

    secret = client_secret or os.getenv("MCP_SECRET")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "mcp-session-id": session_id,
    }

    if secret:
        headers["X-Client-Secret"] = secret

    # Determine URL based on routing style
    if use_path_routing:
        url = raw_url.rstrip("/")
        request_url = f"{url}/tools/call"
    else:
        request_url = raw_url

    # Use provided client or create temporary one
    if client:
        response = await client.post(
            request_url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        )
    else:
        async with httpx.AsyncClient(timeout=timeout, verify=verify_ssl) as temp_client:
            response = await temp_client.post(
                request_url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                },
            )

    response.raise_for_status()

    # Parse SSE response
    data = parse_sse_response(response.text)

    # Extract result from JSON-RPC response
    if isinstance(data, dict) and "result" in data:
        return data["result"]

    return data


class MCPSession:
    """Managed MCP session with automatic cleanup and JWT bearer token management.

    This class handles session lifecycle and provides a clean interface for
    interacting with MCP tools. JWT token generation is always enforced by default.

    Example:
        # RavenPack-style (default - path-based routing)
        async with MCPSession() as session:
            tools = await session.list_tools()
            result = await session.call_tool("search", {"query": "test"})

        # CapIQ-style (disable path routing)
        async with MCPSession(use_path_routing=False) as session:
            tools = await session.list_tools()
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        bearer_token: Optional[str] = None,
        client_secret: Optional[str] = None,
        use_token_generation: bool = True,
        verify_ssl: bool = True,
        use_path_routing: bool = True,
    ):
        """Initialize MCPSession.

        Args:
            endpoint: MCP server URL (uses MCP_ENDPOINT from env if not provided)
            bearer_token: Pre-generated bearer token (used when use_token_generation=False)
            client_secret: MCP server secret (uses MCP_SECRET from env if not provided)
            use_token_generation: If True, generate bearer token using JWT encoding
            verify_ssl: Whether to verify SSL certificates
            use_path_routing: If True, use path-based routing
        """
        self.endpoint = endpoint
        self.bearer_token = bearer_token
        self.client_secret = client_secret
        self.use_token_generation = use_token_generation
        self.verify_ssl = verify_ssl
        self.use_path_routing = use_path_routing
        self.session_id: Optional[str] = None
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Initialize session on context entry."""
        self.session_id, self.client = await initialize_mcp_session(
            self.endpoint,
            self.bearer_token,
            self.client_secret,
            use_token_generation=self.use_token_generation,
            verify_ssl=self.verify_ssl,
            use_path_routing=self.use_path_routing,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up session on context exit."""
        if self.client:
            await self.client.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools in this session."""
        if not self.session_id or not self.client:
            raise RuntimeError(
                "Session not initialized. Use 'async with MCPSession()' pattern."
            )

        return await list_mcp_tools(
            self.session_id,
            self.endpoint,
            self.bearer_token,
            self.client_secret,
            client=self.client,
            use_token_generation=self.use_token_generation,
            use_path_routing=self.use_path_routing,
        )

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call a tool in this session."""
        if not self.session_id or not self.client:
            raise RuntimeError(
                "Session not initialized. Use 'async with MCPSession()' pattern."
            )

        return await call_mcp_tool(
            tool_name,
            arguments,
            self.session_id,
            self.endpoint,
            self.bearer_token,
            self.client_secret,
            client=self.client,
            use_token_generation=self.use_token_generation,
            use_path_routing=self.use_path_routing,
        )

    async def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get tool schemas in OpenAI function calling format."""
        tools = await self.list_tools()
        schemas = []

        for tool in tools:
            schema = {
                "type": "function",
                "function": {
                    "name": tool.get("name", "unknown"),
                    "description": tool.get("description", ""),
                },
            }

            if "inputSchema" in tool:
                schema["function"]["parameters"] = tool["inputSchema"]
            elif "parameters" in tool:
                schema["function"]["parameters"] = tool["parameters"]

            schemas.append(schema)

        return schemas