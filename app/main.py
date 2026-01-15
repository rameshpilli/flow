# app/main.py
import logging
import uvicorn
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.config import config
from app.auth import AuthBackend, AuthContextMiddleware, on_auth_error

# Configure logging
logger = logging.getLogger("dbx_sql_mcp")
logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.propagate = False

print("\n" + "#"*80)
print("#" + " "*78 + "#")
print("#" + "  DATABRICKS SQL MCP SERVER".center(78) + "#")
print("#" + " "*78 + "#")
print("#"*80)

# Create FastMCP instance
mcp = FastMCP(name="Databricks SQL MCP Server")

# Set up MCP singleton for tools to access
from app.mcp_singleton import set_mcp_instance
set_mcp_instance(mcp)

# Configure middleware
middleware = [
    Middleware(
        AuthenticationMiddleware,
        backend=AuthBackend(server_secret=config.AUTH_SERVER_SECRET),
        on_error=on_auth_error,
    ),
    Middleware(AuthContextMiddleware, debug=config.DEVELOPMENT),
]

# Create MCP HTTP app with stateless transport
mcp_app = mcp.http_app(stateless_http=True)
mcp_app.user_middleware.extend(middleware)
logger.info("MCP middleware configured.")

# Import tools (this registers them with the MCP instance)
import app.tools.databricks_tools

# Log registered tools
from app.utils.startup_diagnostics import log_tool_registration
tool_names = [
    "databricks_list_tables",
    "databricks_get_schema",
    "databricks_execute_query",
    "databricks_clear_cache",
    "databricks_cache_stats",
]
log_tool_registration(tool_names)

# Use MCP app directly as the main app
app = mcp_app

# Add CORS middleware
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GZip compression for responses > 1KB
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,      # Only compress responses > 1KB
    compresslevel=6         # Balance between speed (1) and compression (9)
)
logger.info("✓ GZip compression enabled for responses > 1KB")

# Run startup diagnostics
from app.utils.startup_diagnostics import run_startup_diagnostics
run_startup_diagnostics(tool_count=len(tool_names))

logger.info("MCP application configured at /mcp (default path)")

# Add health check and root routes
def root(request):
    return JSONResponse({
        "message": "Databricks SQL MCP Server",
        "status": "ok",
        "version": "0.1.0"
    })

def health(request):
    """Health check endpoint"""
    from app.db.connector import db_connector
    from app.utils.cache import cache
    
    health_status = {
        "status": "healthy",
        "database": "connected" if db_connector.test_connection() else "disconnected",
        "cache": "enabled" if cache.enabled else "disabled"
    }
    
    # Return 503 if database is not connected
    status_code = 200 if health_status["database"] == "connected" else 503
    
    return JSONResponse(health_status, status_code=status_code)

# Add routes to the MCP app
app.routes.append(Route("/", root, methods=["GET"]))
app.routes.append(Route("/health", health, methods=["GET"]))
logger.info("✓ Additional routes added: /, /health")

# Startup summary
from app.utils.startup_diagnostics import log_startup_summary
log_startup_summary(tool_count=len(tool_names))

if __name__ == "__main__":
    host = config.MCP_SERVER_HOST
    port = config.MCP_SERVER_PORT
    
    logger.info(f"Starting uvicorn server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
