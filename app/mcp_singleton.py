# app/mcp_singleton.py
"""
Singleton pattern for FastMCP instance.
This allows tools to register themselves with the MCP instance before it's fully initialized.
"""
from typing import Optional
from fastmcp import FastMCP

_mcp_instance: Optional[FastMCP] = None


def set_mcp_instance(mcp: FastMCP):
    """Set the global MCP instance"""
    global _mcp_instance
    _mcp_instance = mcp


def get_mcp_instance() -> FastMCP:
    """Get the global MCP instance"""
    if _mcp_instance is None:
        raise RuntimeError("MCP instance not initialized. Call set_mcp_instance first.")
    return _mcp_instance
