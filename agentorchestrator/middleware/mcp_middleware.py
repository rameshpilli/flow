"""
MCP Middleware for FastAPI

Provides request-scoped access to MCP adapters in FastAPI applications.
Integrates with MCPServiceManager for application-level lifecycle management.

Features:
- Request-scoped adapter access
- Error handling and retries
- Request context injection
- Health check support

Usage:
    from fastapi import FastAPI, Request
    from contextlib import asynccontextmanager
    from agentorchestrator.middleware.mcp_middleware import MCPMiddleware
    from agentorchestrator.services.mcp_service import MCPServiceManager

    mcp_service = MCPServiceManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        await mcp_service.startup()
        yield
        # Shutdown
        await mcp_service.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(MCPMiddleware, mcp_service=mcp_service)

    @app.get("/analyze")
    async def analyze(request: Request, query: str):
        # Get MCP adapters from request state
        mcp_adapters = request.state.mcp_adapters
        ravenpack = request.state.mcp_service.get_adapter("RavenPack News")

        if ravenpack:
            tools = await ravenpack.get_tool_functions()
            # Use tools...
"""

import logging
import time
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class MCPMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for MCP adapter access.

    Injects MCP service into request state for easy access in route handlers.
    Handles error tracking and request timing.
    """

    def __init__(
        self,
        app: ASGIApp,
        mcp_service=None,  # MCPServiceManager instance
        include_timing: bool = True,
        log_requests: bool = False,
    ):
        """
        Initialize MCP middleware.

        Args:
            app: ASGI application
            mcp_service: MCPServiceManager instance
            include_timing: Add MCP timing headers to response
            log_requests: Log MCP-related requests
        """
        super().__init__(app)
        self.mcp_service = mcp_service
        self.include_timing = include_timing
        self.log_requests = log_requests

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request and inject MCP service into request state.

        Args:
            request: FastAPI request
            call_next: Next middleware/route handler

        Returns:
            Response with optional MCP timing headers
        """
        start_time = time.perf_counter()

        # Inject MCP service into request state
        if self.mcp_service:
            request.state.mcp_service = self.mcp_service
            request.state.mcp_adapters = self.mcp_service.get_all_adapters()

            # Add convenience method to get adapter by name
            def get_mcp_adapter(name: str):
                return self.mcp_service.get_adapter(name)

            request.state.get_mcp_adapter = get_mcp_adapter

            if self.log_requests:
                logger.debug(
                    f"MCP middleware: injected {len(request.state.mcp_adapters)} adapter(s) "
                    f"for {request.method} {request.url.path}"
                )
        else:
            request.state.mcp_service = None
            request.state.mcp_adapters = []
            request.state.get_mcp_adapter = lambda name: None

        # Process request
        try:
            response = await call_next(request)

            # Add timing header if enabled
            if self.include_timing:
                duration_ms = (time.perf_counter() - start_time) * 1000
                response.headers["X-MCP-Middleware-Time-Ms"] = f"{duration_ms:.2f}"

            return response

        except Exception as e:
            # Log MCP-related errors
            logger.error(f"MCP middleware error: {e}")
            raise


class MCPHealthMiddleware(BaseHTTPMiddleware):
    """
    Lightweight middleware that adds MCP health check endpoint.

    Automatically adds /_health/mcp endpoint without needing route definition.
    """

    def __init__(
        self,
        app: ASGIApp,
        mcp_service=None,  # MCPServiceManager instance
        health_path: str = "/_health/mcp",
    ):
        """
        Initialize MCP health middleware.

        Args:
            app: ASGI application
            mcp_service: MCPServiceManager instance
            health_path: Health check endpoint path
        """
        super().__init__(app)
        self.mcp_service = mcp_service
        self.health_path = health_path

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Intercept health check requests and return MCP health status.

        Args:
            request: FastAPI request
            call_next: Next middleware/route handler

        Returns:
            Health check response or normal response
        """
        # Check if this is a health check request
        if request.url.path == self.health_path:
            if not self.mcp_service:
                return Response(
                    content='{"status":"unavailable","message":"MCP service not configured"}',
                    status_code=503,
                    media_type="application/json",
                )

            try:
                health = await self.mcp_service.health_check()
                status_code = 200 if health["status"] == "healthy" else 503

                import json
                return Response(
                    content=json.dumps(health, indent=2),
                    status_code=status_code,
                    media_type="application/json",
                )
            except Exception as e:
                logger.error(f"MCP health check failed: {e}")
                return Response(
                    content=f'{{"status":"error","message":"{str(e)}"}}',
                    status_code=500,
                    media_type="application/json",
                )

        # Not a health check, continue normally
        return await call_next(request)


def get_mcp_service(request: Request):
    """
    FastAPI dependency to get MCP service from request state.

    Usage:
        from fastapi import Depends
        from agentorchestrator.middleware.mcp_middleware import get_mcp_service

        @app.get("/analyze")
        async def analyze(
            query: str,
            mcp_service = Depends(get_mcp_service)
        ):
            adapters = mcp_service.get_all_adapters()
            # Use adapters...
    """
    return getattr(request.state, "mcp_service", None)


def get_mcp_adapters(request: Request):
    """
    FastAPI dependency to get all MCP adapters from request state.

    Usage:
        from fastapi import Depends
        from agentorchestrator.middleware.mcp_middleware import get_mcp_adapters

        @app.get("/analyze")
        async def analyze(
            query: str,
            mcp_adapters = Depends(get_mcp_adapters)
        ):
            # Use adapters directly...
    """
    return getattr(request.state, "mcp_adapters", [])


def get_mcp_adapter(name: str):
    """
    FastAPI dependency factory to get specific MCP adapter by name.

    Usage:
        from fastapi import Depends
        from agentorchestrator.middleware.mcp_middleware import get_mcp_adapter

        @app.get("/news")
        async def get_news(
            query: str,
            ravenpack = Depends(get_mcp_adapter("RavenPack News"))
        ):
            if ravenpack:
                tools = await ravenpack.get_tool_functions()
                # Use tools...
    """
    def dependency(request: Request):
        get_adapter_fn = getattr(request.state, "get_mcp_adapter", None)
        if get_adapter_fn:
            return get_adapter_fn(name)
        return None

    return dependency