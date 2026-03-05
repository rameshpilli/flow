"""MCP Tool Adapter for AgentOrchestrator integration.

This module provides an adapter that bridges MCP servers with AgentOrchestrator.
It handles:
- Session-based connection management with async lifecycle
- Tool discovery and schema conversion
- Tool invocation with caching and tracking integration
- Schema sanitization for agent compatibility
- MCP source detection for result attribution

Example:
    from agentorchestrator.utils.mcp_tool_adapter import MCPToolAdapter

    adapter = MCPToolAdapter(name="RavenPack News")
    await adapter.connect(
        endpoint="https://example.com/mcp",
        secret="secret123",
        use_path_routing=True
    )

    tools = await adapter.get_tool_functions()
    # Pass tools to AgentOrchestrator agents

    await adapter.disconnect()
"""

import json
import time
from typing import Any, Dict, List, Optional

from agentorchestrator.utils.mcp_cache import get_global_cache
from agentorchestrator.utils.mcp_client import MCPSession
from agentorchestrator.utils.tool_usage_tracker import get_global_tracker

# Try to import agents package (optional dependency)
try:
    from agents import FunctionTool
    from agents.tool import ToolContext

    AGENTS_AVAILABLE = True
except ImportError:
    FunctionTool = None
    ToolContext = None
    AGENTS_AVAILABLE = False


def _sanitize_schema_for_strict(schema: dict) -> dict:
    """Recursively remove additionalProperties from object schemas.

    The agents package's FunctionTool uses strict schema validation which
    rejects schemas with additionalProperties set. This function sanitizes
    MCP tool schemas to be compatible.

    Args:
        schema: JSON schema dictionary

    Returns:
        Sanitized schema without additionalProperties on object types
    """
    if not isinstance(schema, dict):
        return schema

    result = {}
    for key, value in schema.items():
        if key == "additionalProperties":
            # Skip additionalProperties for object types
            continue
        elif key == "properties" and isinstance(value, dict):
            # Recursively sanitize nested properties
            result[key] = {
                prop_name: _sanitize_schema_for_strict(prop_schema)
                for prop_name, prop_schema in value.items()
            }
        elif key == "items" and isinstance(value, dict):
            # Sanitize array items schema
            result[key] = _sanitize_schema_for_strict(value)
        elif key == "anyOf" and isinstance(value, list):
            # Sanitize anyOf variants
            result[key] = [_sanitize_schema_for_strict(v) for v in value]
        elif key == "oneOf" and isinstance(value, list):
            # Sanitize oneOf variants
            result[key] = [_sanitize_schema_for_strict(v) for v in value]
        elif key == "allOf" and isinstance(value, list):
            # Sanitize allOf variants
            result[key] = [_sanitize_schema_for_strict(v) for v in value]
        elif key == "$defs" and isinstance(value, dict):
            # Sanitize schema definitions
            result[key] = {
                def_name: _sanitize_schema_for_strict(def_schema)
                for def_name, def_schema in value.items()
            }
        elif key == "definitions" and isinstance(value, dict):
            # Sanitize schema definitions (older format)
            result[key] = {
                def_name: _sanitize_schema_for_strict(def_schema)
                for def_name, def_schema in value.items()
            }
        elif isinstance(value, dict):
            # Recursively sanitize other nested objects
            result[key] = _sanitize_schema_for_strict(value)
        else:
            result[key] = value

    return result


class MCPToolAdapter:
    """Adapter that converts MCP tools to callable functions for agents.

    This class maintains an active MCPSession and provides tools as
    Python functions that can be passed to AgentOrchestrator agents.

    Integrates with:
    - MCPSession: For MCP server communication
    - ToolUsageTracker: For call tracking and metrics
    - MCPCache: For result caching to reduce API calls

    Example:
        adapter = MCPToolAdapter(name="RavenPack News")
        await adapter.connect(
            endpoint="https://example.com/mcp",
            secret="secret123",
            use_path_routing=True
        )

        tools = await adapter.get_tool_functions()
        agent = orchestrator.create_agent(
            name="Analyst",
            instructions="You are an analyst.",
            tools=tools
        )

        # Clean up when done
        await adapter.disconnect()
    """

    def __init__(self, name: str = "MCP Tools"):
        """Initialize the adapter.

        Args:
            name: Descriptive name for this adapter (used for source attribution)
        """
        self.name = name
        self.session: Optional[MCPSession] = None
        self.endpoint: Optional[str] = None
        self.tools_list: List[Dict[str, Any]] = []

    async def connect(
        self,
        endpoint: Optional[str] = None,
        secret: Optional[str] = None,
        use_path_routing: bool = True,
        verify_ssl: bool = False,
    ) -> bool:
        """Connect to MCP endpoint and initialize session.

        Args:
            endpoint: MCP endpoint URL
            secret: MCP server secret for JWT authentication
            use_path_routing: Whether to use path-based routing (RavenPack/Factset)
                            or single-endpoint JSON-RPC (CapIQ/RBC Insights)
            verify_ssl: Whether to verify SSL certificates

        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self.endpoint = endpoint
            self.session = MCPSession(
                endpoint=endpoint,
                client_secret=secret,
                use_path_routing=use_path_routing,
                verify_ssl=verify_ssl,
            )

            # Enter the session context
            await self.session.__aenter__()

            # List available tools
            self.tools_list = await self.session.list_tools()

            print(f"✓ Connected {self.name} MCP adapter")
            print(f"  Endpoint: {endpoint}")
            print(f"  Tools: {len(self.tools_list)}")

            return True
        except Exception as e:
            print(f"❌ Failed to connect {self.name} MCP adapter: {e}")
            import traceback

            traceback.print_exc()
            return False

    async def disconnect(self):
        """Disconnect from MCP endpoint and clean up resources."""
        if self.session:
            try:
                await self.session.__aexit__(None, None, None)
                print(f"✓ Disconnected {self.name} MCP adapter")
            except Exception as e:
                print(f"⚠️  Error disconnecting {self.name}: {e}")
            finally:
                self.session = None

    def _get_mcp_source(self, tool_name: str) -> str:
        """Determine MCP data source from tool name and adapter name.

        This method maps adapter names and tool name patterns to human-readable
        MCP source identifiers for result attribution.

        Args:
            tool_name: Name of the tool

        Returns:
            MCP source identifier (e.g., "RavenPack News", "S&P Capital IQ")
        """
        # Map adapter names to sources
        adapter_lower = self.name.lower()
        if "ravenpack" in adapter_lower:
            return "RavenPack News"
        elif "capiq" in adapter_lower or "capital iq" in adapter_lower:
            return "S&P Capital IQ"
        elif "factset" in adapter_lower or "earnings" in adapter_lower:
            return "Factset Earnings"
        elif "rbc" in adapter_lower or "insights" in adapter_lower:
            return "RBC Insights"

        # Map tool name patterns to sources
        tool_lower = tool_name.lower()
        if "news" in tool_lower or "filing" in tool_lower:
            return "RavenPack News"
        elif "earnings_call" in tool_lower or "transcript" in tool_lower:
            return "Factset Earnings"
        elif (
            "research" in tool_lower
            or "analyst" in tool_lower
            or "natural_language" in tool_lower
        ):
            return "RBC Insights"
        elif any(
            prefix in tool_lower
            for prefix in ["get_", "financial", "competitor", "segment"]
        ):
            return "S&P Capital IQ"
        else:
            return f"MCP ({self.name})"

    async def get_tool_functions(self) -> List:
        """Get MCP tools as FunctionTool objects for agents.

        Converts MCP tool definitions into FunctionTool objects that can be
        passed to AgentOrchestrator agents. Each tool invocation:
        1. Checks cache for existing result
        2. Calls MCP endpoint if not cached
        3. Tracks call metrics (duration, success/error)
        4. Caches successful results
        5. Returns result with MCP source attribution

        Returns:
            List of FunctionTool objects that agents can use

        Raises:
            Warning if agents package is not available
        """
        if not self.session or not self.tools_list:
            print(f"⚠️  {self.name}: No tools available (not connected or no tools)")
            return []

        if not AGENTS_AVAILABLE or not FunctionTool:
            print("⚠️  agents package not available, cannot create FunctionTool objects")
            return []

        tools = []

        for tool_def in self.tools_list:
            tool_name = tool_def.get("name", "unknown")
            tool_description = tool_def.get("description", "No description")
            input_schema = tool_def.get("inputSchema") or tool_def.get("parameters", {})

            # Create async invoke function for this tool
            # Use default arguments to capture current values in closure
            async def invoke_tool(
                ctx: ToolContext, arguments: str, tool_name=tool_name, self_ref=self
            ):
                """Invoke an MCP tool with caching and tracking support."""
                start_time = time.time()
                tracker = get_global_tracker()
                cache = get_global_cache()

                try:
                    # Parse arguments JSON
                    args_dict = (
                        json.loads(arguments)
                        if isinstance(arguments, str)
                        else arguments
                    )

                    # Log the tool call attempt
                    print(f"\n🔧 [TOOL CALL] {tool_name}")
                    args_preview = json.dumps(args_dict, indent=2)
                    if len(args_preview) > 200:
                        args_preview = args_preview[:200] + "..."
                    print(f"   Arguments: {args_preview}")

                    # Check cache first
                    cached_result = cache.get(tool_name, args_dict) if cache else None

                    if cached_result is not None:
                        # Calculate duration (cache hit is fast)
                        duration_ms = (time.time() - start_time) * 1000

                        # Track the cached call
                        tracker.record_call(
                            tool_name=tool_name,
                            arguments=args_dict,
                            result=cached_result,
                            duration_ms=duration_ms,
                            mcp_source=self_ref._get_mcp_source(tool_name),
                            cached=True,
                        )

                        result_preview = (
                            str(cached_result)[:100] if cached_result else "None"
                        )
                        print(f"   ✅ Result: (CACHED) {result_preview}...")
                        print(f"   Duration: {duration_ms:.2f}ms")

                        # Wrap cached result with source metadata
                        result_with_source = {
                            "data": cached_result,
                            "mcp_source": self_ref._get_mcp_source(tool_name),
                            "tool_name": tool_name,
                            "timestamp": time.time(),
                            "cached": True,
                        }

                        return json.dumps(result_with_source, indent=2)

                    # Call the MCP tool (not in cache)
                    print("   🔄 Calling MCP endpoint...")
                    result = await self_ref.session.call_tool(tool_name, args_dict)

                    # Calculate duration
                    duration_ms = (time.time() - start_time) * 1000

                    # Log result
                    result_preview = str(result)[:100] if result else "None"
                    print(f"   ✅ Result: {result_preview}...")
                    print(f"   Duration: {duration_ms:.2f}ms")

                    # Track the call
                    tracker.record_call(
                        tool_name=tool_name,
                        arguments=args_dict,
                        result=result,
                        duration_ms=duration_ms,
                        mcp_source=self_ref._get_mcp_source(tool_name),
                        cached=False,
                    )

                    # Determine MCP source
                    mcp_source = self_ref._get_mcp_source(tool_name)

                    # Wrap result with source metadata
                    result_with_source = {
                        "data": result,
                        "mcp_source": mcp_source,
                        "tool_name": tool_name,
                        "timestamp": time.time(),
                        "cached": False,
                    }

                    # Cache the wrapped result (with source metadata)
                    if cache:
                        cache.set(tool_name, args_dict, result_with_source)

                    # Return as JSON string for LLM consumption
                    return json.dumps(result_with_source, indent=2)

                except Exception as e:
                    # Calculate duration
                    duration_ms = (time.time() - start_time) * 1000

                    # Log error
                    print(f"   ❌ Error: {str(e)}")
                    print(f"   Duration: {duration_ms:.2f}ms")

                    # Track the error
                    tracker.record_call(
                        tool_name=tool_name,
                        arguments=(
                            json.loads(arguments)
                            if isinstance(arguments, str)
                            else arguments
                        ),
                        error=str(e),
                        duration_ms=duration_ms,
                        mcp_source=self_ref._get_mcp_source(tool_name),
                    )

                    error_result = {
                        "error": str(e),
                        "tool": tool_name,
                        "arguments": arguments,
                    }
                    return json.dumps(error_result, indent=2)

            # Create FunctionTool with sanitized schema (remove additionalProperties)
            sanitized_schema = _sanitize_schema_for_strict(input_schema)
            function_tool = FunctionTool(
                name=tool_name,
                description=tool_description,
                params_json_schema=sanitized_schema,
                on_invoke_tool=invoke_tool,
            )

            # Add mcp_source attribute to the tool for filtering
            function_tool.mcp_source = self._get_mcp_source(tool_name)

            tools.append(function_tool)

        print(f"✓ Created {len(tools)} FunctionTool objects from {self.name}")
        return tools