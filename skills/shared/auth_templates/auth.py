# app/auth/auth.py
import logging
from typing import Optional, Tuple
from starlette.authentication import (
    AuthenticationBackend,
    AuthenticationError,
    SimpleUser,
    AuthCredentials,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import jwt

logger = logging.getLogger("dbx_sql_mcp.auth")


class AuthBackend(AuthenticationBackend):
    """JWT-based authentication backend"""
    
    def __init__(self, server_secret: Optional[str] = None):
        self.server_secret = server_secret
        self.auth_enabled = server_secret is not None
        
        if not self.auth_enabled:
            logger.warning("⚠ Authentication disabled - no AUTH_SERVER_SECRET provided")
        else:
            logger.info("✓ Authentication enabled")
    
    async def authenticate(self, request: Request) -> Optional[Tuple[AuthCredentials, SimpleUser]]:
        """Authenticate request using Bearer token"""
        
        # Skip authentication for health check endpoint
        if request.url.path in ["/health", "/"]:
            return AuthCredentials(["public"]), SimpleUser("anonymous")
        
        # If auth is disabled, allow all requests
        if not self.auth_enabled:
            return AuthCredentials(["authenticated"]), SimpleUser("anonymous")
        
        # Get Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise AuthenticationError("Missing Authorization header")
        
        # Parse Bearer token
        try:
            scheme, token = auth_header.split()
            if scheme.lower() != "bearer":
                raise AuthenticationError("Invalid authentication scheme. Use Bearer token.")
        except ValueError:
            raise AuthenticationError("Invalid Authorization header format")
        
        # Verify JWT token
        try:
            payload = jwt.decode(
                token,
                self.server_secret,
                algorithms=["HS256"]
            )
            user_id = payload.get("sub", "unknown")
            return AuthCredentials(["authenticated"]), SimpleUser(user_id)
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}")


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Middleware to add auth context to request"""
    
    def __init__(self, app, debug: bool = False):
        super().__init__(app)
        self.debug = debug
    
    async def dispatch(self, request: Request, call_next):
        # Log authentication info in debug mode
        if self.debug and hasattr(request, "user"):
            logger.debug(f"Request from user: {request.user.display_name if request.user.is_authenticated else 'anonymous'}")
        
        response = await call_next(request)
        return response


def on_auth_error(request: Request, exc: Exception) -> JSONResponse:
    """Handle authentication errors"""
    logger.warning(f"Authentication failed: {exc}")
    return JSONResponse(
        {
            "error": "Authentication failed",
            "message": str(exc),
            "detail": "Please provide a valid Bearer token in the Authorization header"
        },
        status_code=401
    )
