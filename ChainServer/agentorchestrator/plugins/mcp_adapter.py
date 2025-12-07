"""
MCP Adapter Agent

A real MCP (Model Context Protocol) adapter for connecting to MCP servers.

Features:
- Tool discovery and invocation
- Resource listing and reading
- Prompt template support
- Connection management
- Retry and error handling

Usage:
    from agentorchestrator.plugins import MCPAdapterAgent, MCPAdapterConfig

    # Create adapter
    config = MCPAdapterConfig(
        name="my_mcp",
        server_url="http://localhost:3000",
        transport="http",  # or "stdio"
    )
    agent = MCPAdapterAgent(config)
    await agent.initialize()

    # List available tools
    tools = await agent.list_tools()

    # Call a tool
    result = await agent.call_tool("search", {"query": "test"})

    # Or use via fetch interface
    result = await agent.fetch("search", tool_args={"query": "test"})
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from agentorchestrator.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class MCPAdapterConfig:
    """
    Configuration for MCP adapter agent.

    Attributes:
        name: Server/agent name
        server_url: Server URL (for HTTP transport)
        server_command: Command to start server (for stdio transport)
        server_args: Arguments for server command
        transport: Transport type
        timeout_seconds: Request timeout
        max_retries: Maximum retries
        headers: Additional HTTP headers
        env: Environment variables for stdio transport
        verify_ssl: Whether to verify SSL certificates (set False for internal/self-signed certs)
    """

    name: str
    server_url: str | None = None
    server_command: str | None = None
    server_args: list[str] = field(default_factory=list)
    transport: Literal["http", "stdio", "sse"] = "http"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    headers: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True


@dataclass
class MCPTool:
    """MCP tool definition."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPResource:
    """MCP resource definition."""

    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = "text/plain"

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


class MCPAdapterAgent(BaseAgent):
    """
    MCP adapter agent for connecting to MCP servers.

    Supports both HTTP and stdio transports.
    """

    _ao_name = "mcp_adapter"
    _ao_version = "1.0.0"

    # Capability schema
    CAPABILITIES = {
        "call_tool": {
            "description": "Call an MCP tool",
            "parameters": {
                "tool_name": {"type": "string", "required": True},
                "arguments": {"type": "object", "default": {}},
            },
        },
        "list_tools": {
            "description": "List available MCP tools",
            "parameters": {},
        },
        "read_resource": {
            "description": "Read an MCP resource",
            "parameters": {
                "uri": {"type": "string", "required": True},
            },
        },
        "list_resources": {
            "description": "List available MCP resources",
            "parameters": {},
        },
    }

    def __init__(self, config: MCPAdapterConfig | dict[str, Any] | None = None):
        super().__init__()

        if isinstance(config, dict):
            self._config = MCPAdapterConfig(**config)
        elif config:
            self._config = config
        else:
            self._config = MCPAdapterConfig(name="mcp")

        self._ao_name = self._config.name
        self._http_client = None
        self._stdio_process = None
        self._tools: list[MCPTool] = []
        self._resources: list[MCPResource] = []
        self._request_id = 0
        self._session_id: str | None = None
        self._mcp_session = None  # MCP ClientSession from SDK
        self._streams = None  # Keep reference to streams for cleanup

    async def initialize(self) -> None:
        """Initialize MCP connection using official SDK."""
        if self._config.transport == "http":
            await self._init_http_sdk()
        elif self._config.transport == "stdio":
            await self._init_stdio()
        elif self._config.transport == "sse":
            await self._init_http_sdk()  # SSE uses HTTP transport

        await super().initialize()
        logger.info(f"MCPAdapterAgent initialized: {self._config.name}")

    async def _init_http_sdk(self) -> None:
        """Initialize HTTP transport using official MCP SDK."""
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        import httpx
        
        if not self._config.server_url:
            raise ValueError("server_url required for HTTP transport")

        # Prepare headers with auth
        headers = {**self._config.headers}
        
        # Debug: Log headers (mask auth tokens)
        debug_headers = {k: ("***MASKED***" if k.lower() == "authorization" else v) for k, v in headers.items()}
        logger.info(f"MCPAdapter {self._config.name} connecting to {self._config.server_url}")
        logger.info(f"MCPAdapter {self._config.name} headers: {debug_headers}")
        logger.info(f"MCPAdapter {self._config.name} SSL verification: {self._config.verify_ssl}")
        
        # Create custom httpx client factory that respects verify_ssl setting
        def custom_httpx_factory(
            headers: dict[str, str] | None = None,
            timeout: httpx.Timeout | None = None,
            auth: httpx.Auth | None = None
        ) -> httpx.AsyncClient:
            """Factory that creates httpx client with custom SSL settings."""
            return httpx.AsyncClient(
                headers=headers,
                timeout=timeout,
                auth=auth,
                verify=self._config.verify_ssl  # Use our SSL setting
            )
        
        try:
            # Use the official MCP SDK streamablehttp_client with custom factory
            # This returns (read_stream, write_stream, connection_info)
            streams_context = streamablehttp_client(
                self._config.server_url,
                headers=headers,
                httpx_client_factory=custom_httpx_factory
            )
            
            # Enter the context to get streams
            read_stream, write_stream, _ = await streams_context.__aenter__()
            self._streams = (streams_context, read_stream, write_stream)
            
            # Create MCP ClientSession
            session_context = ClientSession(read_stream, write_stream)
            self._mcp_session = await session_context.__aenter__()
            
            # Initialize the session
            init_result = await self._mcp_session.initialize()
            logger.info(f"MCP session initialized: {init_result}")
            
            # Discover tools and resources
            await self._discover_sdk()
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP SDK session: {e}")
            raise

    async def _init_stdio(self) -> None:
        """Initialize stdio transport."""
        if not self._config.server_command:
            raise ValueError("server_command required for stdio transport")

        # Start MCP server process
        env = {**self._config.env}

        self._stdio_process = await asyncio.create_subprocess_exec(
            self._config.server_command,
            *self._config.server_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Send initialize request
        await self._stdio_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "AgentOrchestrator",
                "version": "1.0.0",
            },
        })

        # Send initialized notification
        await self._stdio_notify("notifications/initialized", {})

    async def _init_sse(self) -> None:
        """Initialize SSE transport."""
        # SSE transport uses HTTP SDK
        await self._init_http_sdk()

    async def _discover_sdk(self) -> None:
        """Discover available tools and resources using MCP SDK."""
        try:
            if not self._mcp_session:
                logger.warning("No MCP session available for discovery")
                return
                
            # List tools via MCP SDK
            tools_result = await self._mcp_session.list_tools()
            if tools_result and tools_result.tools:
                self._tools = [
                    MCPTool(
                        name=t.name,
                        description=t.description or "",
                        input_schema=t.inputSchema or {},
                    )
                    for t in tools_result.tools
                ]
                logger.info(f"Discovered {len(self._tools)} tools: {[t.name for t in self._tools]}")

            # List resources via MCP SDK
            resources_result = await self._mcp_session.list_resources()
            if resources_result and resources_result.resources:
                self._resources = [
                    MCPResource(
                        uri=r.uri,
                        name=r.name or "",
                        description=r.description or "",
                        mime_type=r.mimeType or "text/plain",
                    )
                    for r in resources_result.resources
                ]
                logger.info(f"Discovered {len(self._resources)} resources")

        except Exception as e:
            logger.warning(f"Failed to discover MCP capabilities: {e}")

    async def _initialize_session(self) -> None:
        """Initialize MCP session with the server using SSE."""
        import uuid
        
        try:
            # Generate a unique session ID for this client
            self._session_id = str(uuid.uuid4())
            logger.info(f"Generated session ID for {self._config.name}: {self._session_id}")
            
            # For SSE-based MCP servers, establish streaming connection
            if self._http_client:
                await self._establish_sse_session()
            
        except Exception as e:
            logger.warning(f"Failed to initialize MCP session: {e}")

    async def _establish_sse_session(self) -> None:
        """Establish SSE streaming session with MCP server."""
        import asyncio
        import json
        
        try:
            # Send initialize request with streaming - keep connection open
            payload = {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "roots": {"listChanged": False},
                        "sampling": {},
                    },
                    "clientInfo": {
                        "name": "AgentOrchestrator",
                        "version": "1.0.0",
                    },
                },
            }
            
            # Add session ID to metadata
            if self._session_id:
                payload["_meta"] = {"sessionId": self._session_id}
            
            # Start streaming request - keep it open
            self._sse_response = await self._http_client.stream("POST", "/", json=payload).__aenter__()
            self._sse_response.raise_for_status()
            
            # Read first SSE event to get initialization response
            async for line in self._sse_response.aiter_lines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data:
                        try:
                            event_data = json.loads(data)
                            logger.info(f"SSE event received: {event_data}")
                            
                            # Check for session ID or initialization confirmation
                            if "result" in event_data:
                                result = event_data["result"]
                                if "sessionId" in result:
                                    self._session_id = result["sessionId"]
                                    logger.info(f"MCP server provided sessionId: {self._session_id}")
                                
                                # Session established - start background listener
                                asyncio.create_task(self._listen_sse_stream())
                                
                                # Send initialized notification via the stream
                                await self._send_request_via_sse("notifications/initialized", {})
                                
                                logger.info(f"SSE session established for {self._config.name}")
                                return
                            elif "error" in event_data:
                                logger.error(f"SSE error: {event_data['error']}")
                                return
                        except json.JSONDecodeError:
                            logger.debug(f"Non-JSON SSE data: {data}")
                elif line.startswith("event:"):
                    logger.debug(f"SSE event type: {line[6:].strip()}")
                    
        except Exception as e:
            logger.warning(f"Failed to establish SSE session: {e}")
            if self._sse_response:
                await self._sse_response.__aexit__(None, None, None)
                self._sse_response = None

    async def _listen_sse_stream(self) -> None:
        """Background task to listen for SSE events."""
        import json
        
        try:
            async for line in self._sse_response.aiter_lines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data:
                        try:
                            event_data = json.loads(data)
                            logger.debug(f"SSE event: {event_data}")
                            
                            # Match response to pending request
                            if "id" in event_data:
                                req_id = event_data["id"]
                                if req_id in self._pending_responses:
                                    future = self._pending_responses.pop(req_id)
                                    if "error" in event_data:
                                        future.set_exception(Exception(f"MCP error: {event_data['error']}"))
                                    else:
                                        future.set_result(event_data.get("result"))
                        except json.JSONDecodeError:
                            logger.debug(f"Non-JSON SSE data: {data}")
        except Exception as e:
            logger.warning(f"SSE stream listener error: {e}")

    async def _send_request_via_sse(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Send a request via the SSE stream connection."""
        import asyncio
        
        if not self._sse_response:
            raise RuntimeError("SSE stream not established")
        
        request_id = self._next_request_id()
        
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        
        # Include session ID
        if self._session_id:
            payload["sessionId"] = self._session_id
            payload["_meta"] = {"sessionId": self._session_id}
        
        # Create future for response
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_responses[request_id] = future
        
        # Send request via HTTP POST (separate from SSE stream)
        headers = {}
        if self._session_id:
            headers["X-Session-ID"] = self._session_id
        
        try:
            response = await self._http_client.post("/", json=payload, headers=headers)
            
            # For notifications (no response expected), return immediately
            if method.startswith("notifications/"):
                return None
            
            # If we get a direct response (not SSE), use it
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    result = response.json()
                    if "error" in result:
                        raise Exception(f"MCP error: {result['error']}")
                    return result.get("result")
            
            # Otherwise wait for SSE response
            try:
                result = await asyncio.wait_for(future, timeout=30.0)
                return result
            except asyncio.TimeoutError:
                self._pending_responses.pop(request_id, None)
                raise Exception(f"Timeout waiting for response to {method}")
                
        except Exception as e:
            self._pending_responses.pop(request_id, None)
            raise

    async def _send_initialized(self) -> None:
        """Send initialized notification to MCP server."""
        try:
            # For HTTP, we typically send this as a notification (no response expected)
            if self._http_client:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
                
                # Include session ID in metadata
                if self._session_id:
                    payload["_meta"] = {"sessionId": self._session_id}
                
                # Include session ID in header
                headers = {}
                if self._session_id:
                    headers["X-Session-ID"] = self._session_id
                
                await self._http_client.post("/", json=payload, headers=headers)
        except Exception as e:
            logger.debug(f"Failed to send initialized notification: {e}")

    async def _discover(self) -> None:
        """Discover available tools and resources."""
        try:
            # Use SSE stream if available, otherwise fall back to regular HTTP
            if self._sse_response:
                # List tools via SSE
                tools_result = await self._send_request_via_sse("tools/list", {})
            else:
                # List tools via regular HTTP
                tools_result = await self._request("tools/list", {})
                
            if tools_result and "tools" in tools_result:
                self._tools = [
                    MCPTool(
                        name=t["name"],
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                    )
                    for t in tools_result["tools"]
                ]
                logger.info(f"Discovered {len(self._tools)} tools: {[t.name for t in self._tools]}")

            # List resources
            if self._sse_response:
                resources_result = await self._send_request_via_sse("resources/list", {})
            else:
                resources_result = await self._request("resources/list", {})
                
            if resources_result and "resources" in resources_result:
                self._resources = [
                    MCPResource(
                        uri=r["uri"],
                        name=r.get("name", ""),
                        description=r.get("description", ""),
                        mime_type=r.get("mimeType", "text/plain"),
                    )
                    for r in resources_result["resources"]
                ]
                logger.info(f"Discovered {len(self._resources)} resources")

        except Exception as e:
            logger.warning(f"Failed to discover MCP capabilities: {e}")

    async def cleanup(self) -> None:
        """Cleanup MCP connection."""
        # Close MCP session first
        if self._mcp_session:
            try:
                await self._mcp_session.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error closing MCP session: {e}")
            finally:
                self._mcp_session = None
        
        # Close streams - handle anyio task scope issues gracefully
        if self._streams:
            try:
                streams_context, _, _ = self._streams
                # Try to exit the streams context, but catch anyio task scope errors
                # These occur when cleanup happens in a different async context than creation
                await streams_context.__aexit__(None, None, None)
            except RuntimeError as e:
                # Suppress "Attempted to exit cancel scope in a different task" errors
                # This is expected when cleanup happens after the main async context exits
                if "cancel scope" in str(e) or "different task" in str(e):
                    logger.debug(f"Ignoring expected cleanup error: {e}")
                else:
                    logger.warning(f"Error closing streams: {e}")
            except BaseException as e:
                # Catch BaseExceptionGroup from anyio task cleanup
                logger.debug(f"Ignoring async generator cleanup error: {type(e).__name__}")
            finally:
                self._streams = None
            
        if self._http_client:
            try:
                await self._http_client.aclose()
            except Exception as e:
                logger.debug(f"Error closing HTTP client: {e}")
            finally:
                self._http_client = None

        if self._stdio_process:
            try:
                self._stdio_process.terminate()
                await self._stdio_process.wait()
            except Exception as e:
                logger.debug(f"Error closing stdio process: {e}")
            finally:
                self._stdio_process = None

        await super().cleanup()

    def _next_request_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Make MCP JSON-RPC request."""
        if self._config.transport == "http":
            return await self._http_request(method, params)
        elif self._config.transport == "stdio":
            return await self._stdio_request(method, params)
        else:
            raise ValueError(f"Unsupported transport: {self._config.transport}")

    async def _http_request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Make HTTP JSON-RPC request."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        request_id = self._next_request_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        
        # Include session ID directly in payload if available
        if self._session_id:
            payload["sessionId"] = self._session_id
            payload["_meta"] = {"sessionId": self._session_id}

        # Prepare headers with session ID if available
        headers = {}
        if self._session_id:
            headers["X-Session-ID"] = self._session_id

        try:
            response = await self._http_client.post("/", json=payload, headers=headers)
            
            # Debug: Log response details
            logger.debug(f"MCP Response status: {response.status_code}, headers: {dict(response.headers)}")
            logger.debug(f"MCP Response content-type: {response.headers.get('content-type')}, body: {response.text[:200]}")
            
            # Debug: Log response details on error
            if response.status_code >= 400:
                logger.error(f"MCP HTTP error response body: {response.text[:500]}")
            
            response.raise_for_status()

            # Debug: Log raw response for parsing issues
            if not response.text.strip():
                logger.warning(f"MCP server returned empty response for method: {method}")
                return None
            
            # Handle SSE responses (text/event-stream)
            content_type = response.headers.get("content-type", "")
            if "event-stream" in content_type:
                logger.info(f"MCP server returned SSE stream for method: {method}")
                # For initialize, SSE stream means session is established
                # Extract session ID from response if present
                if "set-cookie" in response.headers:
                    logger.info(f"MCP server set cookies: {response.headers.get('set-cookie')}")
                return {"success": True}  # Session established via SSE
            
            result = response.json()

            if "error" in result:
                error = result["error"]
                raise Exception(f"MCP error: {error.get('message', error)}")

            return result.get("result")

        except Exception as e:
            logger.error(f"MCP HTTP request failed: {e}")
            raise

    async def _stdio_request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Make stdio JSON-RPC request."""
        if not self._stdio_process or not self._stdio_process.stdin:
            raise RuntimeError("Stdio process not running")

        request_id = self._next_request_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Send request
        message = json.dumps(payload) + "\n"
        self._stdio_process.stdin.write(message.encode())
        await self._stdio_process.stdin.drain()

        # Read response
        if not self._stdio_process.stdout:
            raise RuntimeError("Stdout not available")

        response_line = await asyncio.wait_for(
            self._stdio_process.stdout.readline(),
            timeout=self._config.timeout_seconds,
        )

        if not response_line:
            raise Exception("No response from MCP server")

        result = json.loads(response_line.decode())

        if "error" in result:
            error = result["error"]
            raise Exception(f"MCP error: {error.get('message', error)}")

        return result.get("result")

    async def _stdio_notify(self, method: str, params: dict[str, Any]) -> None:
        """Send stdio notification (no response expected)."""
        if not self._stdio_process or not self._stdio_process.stdin:
            return

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        message = json.dumps(payload) + "\n"
        self._stdio_process.stdin.write(message.encode())
        await self._stdio_process.stdin.drain()

    # ═══════════════════════════════════════════════════════════════════════
    #                         PUBLIC API
    # ═══════════════════════════════════════════════════════════════════════

    async def list_tools(self) -> list[MCPTool]:
        """List available MCP tools."""
        return self._tools

    async def list_resources(self) -> list[MCPResource]:
        """List available MCP resources."""
        return self._resources

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Call an MCP tool using the official SDK.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if not self._mcp_session:
            raise RuntimeError("MCP session not initialized")
        
        try:
            # Call tool using MCP SDK
            result = await self._mcp_session.call_tool(
                name=tool_name,
                arguments=arguments or {}
            )
            
            # Extract content from result
            if result and result.content:
                # Convert MCP content to dict format
                content_list = []
                for content_item in result.content:
                    if hasattr(content_item, 'text'):
                        content_list.append({"text": content_item.text})
                    else:
                        content_list.append(content_item.model_dump() if hasattr(content_item, 'model_dump') else str(content_item))
                
                return {"content": content_list}
            
            return {}
            
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """
        Read an MCP resource.

        Args:
            uri: Resource URI

        Returns:
            Resource content
        """
        result = await self._request("resources/read", {"uri": uri})
        return result or {}

    async def fetch(
        self,
        query: str,
        tool_args: dict[str, Any] | None = None,
        **kwargs,
    ) -> AgentResult:
        """
        Fetch data via MCP (implements BaseAgent.fetch).

        The query is interpreted as a tool name.

        Args:
            query: Tool name to call
            tool_args: Arguments for the tool
            **kwargs: Additional arguments

        Returns:
            AgentResult with tool output
        """
        start = time.perf_counter()

        try:
            result = await self.call_tool(query, tool_args)
            duration = (time.perf_counter() - start) * 1000

            return AgentResult(
                data=result,
                source=self._ao_name,
                query=query,
                duration_ms=duration,
                metadata={
                    "tool_name": query,
                    "transport": self._config.transport,
                },
            )

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=query,
                duration_ms=duration,
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if MCP connection is healthy."""
        try:
            # Try to list tools as health check
            await self._request("tools/list", {})
            return True
        except Exception:
            return False

    def get_tool(self, name: str) -> MCPTool | None:
        """Get tool by name."""
        return next((t for t in self._tools if t.name == name), None)

    def has_tool(self, name: str) -> bool:
        """Check if tool exists."""
        return any(t.name == name for t in self._tools)


def create_mcp_agent(
    name: str,
    server_url: str | None = None,
    server_command: str | None = None,
    server_args: list[str] | None = None,
    transport: str = "http",
    **kwargs,
) -> MCPAdapterAgent:
    """
    Factory function to create MCP adapter agent.

    Args:
        name: Agent name
        server_url: Server URL (for HTTP)
        server_command: Server command (for stdio)
        server_args: Server arguments
        transport: Transport type
        **kwargs: Additional config options

    Returns:
        Configured MCPAdapterAgent
    """
    config = MCPAdapterConfig(
        name=name,
        server_url=server_url,
        server_command=server_command,
        server_args=server_args or [],
        transport=transport,
        **kwargs,
    )

    return MCPAdapterAgent(config)