"""
Tool Registry - Centralized Tool Discovery and Management
=========================================================

Provides a centralized system for registering, discovering, and managing tools
that can be used by agents.

Features:
- Centralized tool registration with metadata
- Tool discovery by name, tags, or capabilities
- Schema validation for tool parameters
- Built-in tools for common operations
- Tool composition and chaining
- Usage tracking and analytics

Usage:
    from agentorchestrator.agents.tools import ToolRegistry, tool

    # Create a registry
    registry = ToolRegistry()

    # Register tools via decorator
    @registry.tool(
        name="search",
        description="Search the web for information",
        tags=["web", "search"],
    )
    async def search(query: str) -> str:
        return await search_engine.search(query)

    # Register tools programmatically
    registry.register(
        name="calculate",
        func=eval_math,
        description="Evaluate mathematical expressions",
    )

    # Discover tools
    web_tools = registry.find_by_tag("web")
    all_tools = registry.list_all()

    # Get tool schema for LLM
    schema = registry.get_openai_schema()

Example:
    >>> from agentorchestrator.agents.tools import ToolRegistry, get_default_registry
    >>>
    >>> # Use the global registry
    >>> registry = get_default_registry()
    >>>
    >>> # Register a tool
    >>> @registry.tool("greet", "Greet someone by name")
    ... def greet(name: str) -> str:
    ...     return f"Hello, {name}!"
    >>>
    >>> # Execute a tool
    >>> result = await registry.execute("greet", name="World")
    >>> print(result)  # "Hello, World!"
"""

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TypeVar, get_type_hints

logger = logging.getLogger(__name__)

__all__ = [
    "ToolRegistry",
    "ToolDefinition",
    "ToolCategory",
    "ToolExecutionResult",
    "get_default_registry",
    "tool",
    # Built-in tools
    "register_builtin_tools",
]

F = TypeVar("F", bound=Callable[..., Any])


class ToolCategory(str, Enum):
    """Categories for organizing tools."""
    SEARCH = "search"
    CALCULATION = "calculation"
    DATA = "data"
    FILE = "file"
    WEB = "web"
    CODE = "code"
    MEMORY = "memory"
    COMMUNICATION = "communication"
    UTILITY = "utility"
    CUSTOM = "custom"


@dataclass
class ToolParameter:
    """Parameter definition for a tool."""
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON schema format."""
        schema: dict[str, Any] = {
            "type": self._python_type_to_json(self.type),
        }
        if self.description:
            schema["description"] = self.description
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema

    @staticmethod
    def _python_type_to_json(python_type: str) -> str:
        """Convert Python type to JSON schema type."""
        type_map = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
            "Any": "string",
            "None": "null",
        }
        return type_map.get(python_type, "string")


@dataclass
class ToolDefinition:
    """
    Complete definition of a registered tool.

    Attributes:
        name: Unique tool identifier
        func: The callable to execute
        description: Human-readable description
        parameters: List of parameter definitions
        category: Tool category for organization
        tags: Tags for discovery
        version: Tool version
        author: Tool author
        is_async: Whether the function is async
        requires_auth: Whether the tool requires authentication
        rate_limit: Rate limit (calls per minute, 0 = unlimited)
        timeout_ms: Default timeout for execution
        enabled: Whether the tool is enabled
        metadata: Additional metadata
    """
    name: str
    func: Callable[..., Any]
    description: str = ""
    parameters: list[ToolParameter] = field(default_factory=list)
    category: ToolCategory = ToolCategory.CUSTOM
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""
    is_async: bool = False
    requires_auth: bool = False
    rate_limit: int = 0
    timeout_ms: int = 30000
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    # Usage tracking
    call_count: int = 0
    total_duration_ms: float = 0.0
    error_count: int = 0

    def __post_init__(self):
        """Auto-detect async and extract parameters from function signature."""
        self.is_async = asyncio.iscoroutinefunction(self.func)
        if not self.parameters:
            self.parameters = self._extract_parameters()

    def _extract_parameters(self) -> list[ToolParameter]:
        """Extract parameters from function signature."""
        params = []
        sig = inspect.signature(self.func)
        hints = get_type_hints(self.func) if hasattr(self.func, "__annotations__") else {}

        for name, param in sig.parameters.items():
            if name in ("self", "cls"):
                continue

            type_hint = hints.get(name, Any)
            type_name = getattr(type_hint, "__name__", str(type_hint))

            # Get description from docstring if available
            description = ""
            if self.func.__doc__:
                # Simple docstring parameter extraction
                import re
                pattern = rf":param {name}:\s*(.+?)(?:\n|$)"
                match = re.search(pattern, self.func.__doc__)
                if match:
                    description = match.group(1).strip()

            params.append(ToolParameter(
                name=name,
                type=type_name,
                description=description,
                required=param.default is inspect.Parameter.empty,
                default=None if param.default is inspect.Parameter.empty else param.default,
            ))

        return params

    def to_openai_schema(self) -> dict[str, Any]:
        """
        Convert to OpenAI function calling schema.

        Returns:
            Dict compatible with OpenAI's function calling format
        """
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_anthropic_schema(self) -> dict[str, Any]:
        """
        Convert to Anthropic tool use schema.

        Returns:
            Dict compatible with Anthropic's tool use format
        """
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


@dataclass
class ToolExecutionResult:
    """Result from executing a tool."""
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "result": self.result if self.success else None,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class ToolRegistry:
    """
    Central registry for tool discovery and management.

    The registry provides:
    - Tool registration via decorator or programmatic API
    - Tool discovery by name, tags, or category
    - Schema generation for LLM function calling
    - Execution with timeout and error handling
    - Usage tracking and analytics

    Example:
        >>> registry = ToolRegistry()
        >>>
        >>> @registry.tool("search", "Search the web")
        ... async def search(query: str) -> str:
        ...     return await web_search(query)
        >>>
        >>> # Execute
        >>> result = await registry.execute("search", query="AI news")
        >>>
        >>> # Get schemas for LLM
        >>> schemas = registry.get_openai_schemas()
    """

    def __init__(self, name: str = "default"):
        """
        Initialize the tool registry.

        Args:
            name: Registry name for identification
        """
        self.name = name
        self._tools: dict[str, ToolDefinition] = {}
        self._hooks: dict[str, list[Callable]] = {
            "before_execute": [],
            "after_execute": [],
            "on_error": [],
        }

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        description: str = "",
        category: ToolCategory = ToolCategory.CUSTOM,
        tags: list[str] | None = None,
        **kwargs,
    ) -> ToolDefinition:
        """
        Register a tool programmatically.

        Args:
            name: Unique tool name
            func: The function to execute
            description: Tool description
            category: Tool category
            tags: Tags for discovery
            **kwargs: Additional ToolDefinition fields

        Returns:
            The registered ToolDefinition

        Raises:
            ValueError: If tool with same name already exists
        """
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")

        tool_def = ToolDefinition(
            name=name,
            func=func,
            description=description or func.__doc__ or f"Execute {name}",
            category=category,
            tags=tags or [],
            **kwargs,
        )

        self._tools[name] = tool_def
        logger.debug(f"Registered tool: {name}")
        return tool_def

    def tool(
        self,
        name: str | None = None,
        description: str = "",
        category: ToolCategory = ToolCategory.CUSTOM,
        tags: list[str] | None = None,
        **kwargs,
    ) -> Callable[[F], F]:
        """
        Decorator to register a function as a tool.

        Args:
            name: Tool name (defaults to function name)
            description: Tool description
            category: Tool category
            tags: Tags for discovery
            **kwargs: Additional ToolDefinition fields

        Returns:
            Decorator function

        Example:
            >>> @registry.tool("search", "Search the web", tags=["web"])
            ... async def search(query: str) -> str:
            ...     return await web_search(query)
        """
        def decorator(func: F) -> F:
            tool_name = name or func.__name__
            self.register(
                name=tool_name,
                func=func,
                description=description or func.__doc__ or "",
                category=category,
                tags=tags,
                **kwargs,
            )
            return func
        return decorator

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool.

        Args:
            name: Tool name to unregister

        Returns:
            True if tool was unregistered, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            logger.debug(f"Unregistered tool: {name}")
            return True
        return False

    def get(self, name: str) -> ToolDefinition | None:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            ToolDefinition or None if not found
        """
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_all(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tool definitions."""
        return list(self._tools.values())

    def find_by_tag(self, tag: str) -> list[ToolDefinition]:
        """
        Find tools by tag.

        Args:
            tag: Tag to search for

        Returns:
            List of matching tools
        """
        return [t for t in self._tools.values() if tag in t.tags]

    def find_by_category(self, category: ToolCategory) -> list[ToolDefinition]:
        """
        Find tools by category.

        Args:
            category: Category to filter by

        Returns:
            List of matching tools
        """
        return [t for t in self._tools.values() if t.category == category]

    def search(self, query: str) -> list[ToolDefinition]:
        """
        Search tools by name or description.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching tools
        """
        query_lower = query.lower()
        return [
            t for t in self._tools.values()
            if query_lower in t.name.lower() or query_lower in t.description.lower()
        ]

    async def execute(
        self,
        name: str,
        timeout_ms: int | None = None,
        **kwargs,
    ) -> ToolExecutionResult:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            timeout_ms: Override default timeout (None = use tool's default)
            **kwargs: Arguments to pass to the tool

        Returns:
            ToolExecutionResult with success/failure and result
        """
        tool = self._tools.get(name)
        if not tool:
            return ToolExecutionResult(
                tool_name=name,
                success=False,
                result=None,
                error=f"Tool '{name}' not found",
            )

        if not tool.enabled:
            return ToolExecutionResult(
                tool_name=name,
                success=False,
                result=None,
                error=f"Tool '{name}' is disabled",
            )

        # Run before hooks
        for hook in self._hooks["before_execute"]:
            try:
                hook(tool, kwargs)
            except Exception as e:
                logger.warning(f"Before hook failed: {e}")

        start_time = time.perf_counter()
        timeout = (timeout_ms or tool.timeout_ms) / 1000

        try:
            if tool.is_async:
                result = await asyncio.wait_for(
                    tool.func(**kwargs),
                    timeout=timeout,
                )
            else:
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tool.func(**kwargs)),
                    timeout=timeout,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000

            # Update stats
            tool.call_count += 1
            tool.total_duration_ms += duration_ms

            exec_result = ToolExecutionResult(
                tool_name=name,
                success=True,
                result=result,
                duration_ms=duration_ms,
            )

            # Run after hooks
            for hook in self._hooks["after_execute"]:
                try:
                    hook(tool, exec_result)
                except Exception as e:
                    logger.warning(f"After hook failed: {e}")

            return exec_result

        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            tool.error_count += 1

            exec_result = ToolExecutionResult(
                tool_name=name,
                success=False,
                result=None,
                error=f"Tool timed out after {timeout}s",
                duration_ms=duration_ms,
            )

            for hook in self._hooks["on_error"]:
                try:
                    hook(tool, exec_result)
                except Exception as e:
                    logger.warning(f"Error hook failed: {e}")

            return exec_result

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            tool.error_count += 1

            exec_result = ToolExecutionResult(
                tool_name=name,
                success=False,
                result=None,
                error=str(e),
                duration_ms=duration_ms,
            )

            for hook in self._hooks["on_error"]:
                try:
                    hook(tool, exec_result)
                except Exception as hook_e:
                    logger.warning(f"Error hook failed: {hook_e}")

            return exec_result

    def execute_sync(self, name: str, **kwargs) -> ToolExecutionResult:
        """Synchronous wrapper for execute()."""
        return asyncio.run(self.execute(name, **kwargs))

    def add_hook(
        self,
        event: str,
        hook: Callable,
    ) -> None:
        """
        Add an execution hook.

        Args:
            event: Event type ("before_execute", "after_execute", "on_error")
            hook: Hook function
        """
        if event not in self._hooks:
            raise ValueError(f"Unknown hook event: {event}")
        self._hooks[event].append(hook)

    def get_openai_schemas(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        """
        Get all tools as OpenAI function calling schemas.

        Args:
            enabled_only: Only include enabled tools

        Returns:
            List of OpenAI-compatible function schemas
        """
        tools = self._tools.values()
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        return [t.to_openai_schema() for t in tools]

    def get_anthropic_schemas(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        """
        Get all tools as Anthropic tool use schemas.

        Args:
            enabled_only: Only include enabled tools

        Returns:
            List of Anthropic-compatible tool schemas
        """
        tools = self._tools.values()
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        return [t.to_anthropic_schema() for t in tools]

    def get_tools_description(self, enabled_only: bool = True) -> str:
        """
        Get a text description of all tools for prompts.

        Args:
            enabled_only: Only include enabled tools

        Returns:
            Formatted string describing all tools
        """
        tools = self._tools.values()
        if enabled_only:
            tools = [t for t in tools if t.enabled]

        lines = []
        for tool in tools:
            params = ", ".join(p.name for p in tool.parameters)
            lines.append(f"- {tool.name}({params}): {tool.description}")
        return "\n".join(lines)

    def get_stats(self) -> dict[str, Any]:
        """
        Get usage statistics for all tools.

        Returns:
            Dict with per-tool and aggregate statistics
        """
        total_calls = sum(t.call_count for t in self._tools.values())
        total_errors = sum(t.error_count for t in self._tools.values())
        total_duration = sum(t.total_duration_ms for t in self._tools.values())

        per_tool = {
            name: {
                "calls": t.call_count,
                "errors": t.error_count,
                "total_duration_ms": t.total_duration_ms,
                "avg_duration_ms": t.total_duration_ms / t.call_count if t.call_count > 0 else 0,
            }
            for name, t in self._tools.items()
        }

        return {
            "total_tools": len(self._tools),
            "total_calls": total_calls,
            "total_errors": total_errors,
            "total_duration_ms": total_duration,
            "error_rate": total_errors / total_calls if total_calls > 0 else 0,
            "per_tool": per_tool,
        }

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()

    def merge(self, other: "ToolRegistry") -> None:
        """
        Merge another registry into this one.

        Args:
            other: Registry to merge from

        Raises:
            ValueError: If there are name conflicts
        """
        for name, tool in other._tools.items():
            if name in self._tools:
                raise ValueError(f"Tool '{name}' already exists in this registry")
            self._tools[name] = tool


# Global default registry
_default_registry: ToolRegistry | None = None


def get_default_registry() -> ToolRegistry:
    """
    Get the default global tool registry.

    Returns:
        The global ToolRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry(name="global")
        register_builtin_tools(_default_registry)
    return _default_registry


def tool(
    name: str | None = None,
    description: str = "",
    **kwargs,
) -> Callable[[F], F]:
    """
    Decorator to register a tool in the default registry.

    Args:
        name: Tool name (defaults to function name)
        description: Tool description
        **kwargs: Additional registration options

    Example:
        >>> @tool("search", "Search the web")
        ... async def search(query: str) -> str:
        ...     return await web_search(query)
    """
    registry = get_default_registry()
    return registry.tool(name=name, description=description, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
#                              BUILT-IN TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

def register_builtin_tools(registry: ToolRegistry) -> None:
    """
    Register built-in utility tools.

    Args:
        registry: Registry to register tools in
    """

    # Calculator tool
    @registry.tool(
        name="calculate",
        description="Evaluate a mathematical expression safely. Supports basic arithmetic (+, -, *, /, **, %), parentheses, and common functions (abs, min, max, round).",
        category=ToolCategory.CALCULATION,
        tags=["math", "calculation"],
    )
    def calculate(expression: str) -> str:
        """
        Evaluate a mathematical expression.

        :param expression: Mathematical expression to evaluate (e.g., "2 + 2", "sqrt(16)")
        """
        import ast
        import operator

        # Safe operators
        ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        # Safe functions
        safe_funcs = {
            "abs": abs,
            "min": min,
            "max": max,
            "round": round,
            "sum": sum,
            "len": len,
            "int": int,
            "float": float,
        }

        def _eval(node):
            if isinstance(node, ast.Constant):
                return node.value
            elif isinstance(node, ast.BinOp):
                return ops[type(node.op)](_eval(node.left), _eval(node.right))
            elif isinstance(node, ast.UnaryOp):
                return ops[type(node.op)](_eval(node.operand))
            elif isinstance(node, ast.Call):
                func_name = node.func.id if isinstance(node.func, ast.Name) else None
                if func_name in safe_funcs:
                    args = [_eval(arg) for arg in node.args]
                    return safe_funcs[func_name](*args)
                raise ValueError(f"Unsafe function: {func_name}")
            else:
                raise ValueError(f"Unsupported expression: {ast.dump(node)}")

        try:
            tree = ast.parse(expression, mode="eval")
            result = _eval(tree.body)
            return str(result)
        except Exception as e:
            return f"Error: {e}"

    # Current date/time tool
    @registry.tool(
        name="get_current_time",
        description="Get the current date and time in ISO format.",
        category=ToolCategory.UTILITY,
        tags=["time", "date", "utility"],
    )
    def get_current_time() -> str:
        """Get current date and time."""
        from datetime import datetime
        return datetime.now().isoformat()

    # Text length tool
    @registry.tool(
        name="text_length",
        description="Count the number of characters and words in a text.",
        category=ToolCategory.UTILITY,
        tags=["text", "utility"],
    )
    def text_length(text: str) -> str:
        """
        Count text length.

        :param text: Text to analyze
        """
        chars = len(text)
        words = len(text.split())
        return f"Characters: {chars}, Words: {words}"

    logger.debug(f"Registered {len(registry.list_all())} built-in tools")
