"""
OAuth Token Manager for LLM Gateway

Handles OAuth client credentials flow and automatic token refresh.
"""

import base64
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class OAuthTokenManager:
    """
    Manages OAuth access tokens for LLM Gateway with automatic refresh.
    
    Uses client credentials flow to obtain and refresh tokens automatically.
    """

    def __init__(
        self,
        oauth_endpoint: str,
        client_id: str,
        client_secret: str,
        token_refresh_buffer: int = 300,  # Refresh 5 minutes before expiry
    ):
        """
        Initialize OAuth token manager.

        Args:
            oauth_endpoint: OAuth token endpoint URL
            client_id: OAuth client ID
            client_secret: OAuth client secret
            token_refresh_buffer: Seconds before expiry to refresh token
        """
        self.oauth_endpoint = oauth_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_refresh_buffer = token_refresh_buffer

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._lock = False  # Simple lock to prevent concurrent refresh

    def _get_basic_auth_header(self) -> str:
        """Generate Basic Auth header from client credentials."""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _fetch_token(self) -> tuple[str, int]:
        """
        Fetch a new access token from OAuth endpoint.

        Returns:
            Tuple of (access_token, expires_in_seconds)

        Raises:
            httpx.HTTPError: If token request fails
        """
        headers = {
            "Authorization": self._get_basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {"grant_type": "client_credentials"}

        logger.debug(f"Fetching OAuth token from {self.oauth_endpoint}")

        with httpx.Client(timeout=30.0, verify=False) as client:
            response = client.post(self.oauth_endpoint, headers=headers, data=data)
            response.raise_for_status()

            token_data = response.json()
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour

            if not access_token:
                raise ValueError("No access_token in OAuth response")

            logger.info(f"OAuth token obtained, expires in {expires_in} seconds")
            return access_token, expires_in

    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Args:
            force_refresh: Force token refresh even if current token is valid

        Returns:
            Valid access token

        Raises:
            httpx.HTTPError: If token request fails
        """
        current_time = time.time()

        # Check if we need to refresh
        needs_refresh = (
            force_refresh
            or not self._access_token
            or current_time >= (self._token_expires_at - self.token_refresh_buffer)
        )

        if needs_refresh:
            # Simple lock to prevent concurrent refresh
            if self._lock:
                # Wait a bit and retry
                time.sleep(0.1)
                if self._access_token:
                    return self._access_token

            self._lock = True
            try:
                access_token, expires_in = self._fetch_token()
                self._access_token = access_token
                self._token_expires_at = current_time + expires_in
                logger.debug(f"Token refreshed, expires at {self._token_expires_at}")
            finally:
                self._lock = False

        return self._access_token

    def is_token_valid(self) -> bool:
        """Check if current token is still valid."""
        if not self._access_token:
            return False
        return time.time() < (self._token_expires_at - self.token_refresh_buffer)

    def clear_token(self):
        """Clear the cached token (useful for testing or forced refresh)."""
        self._access_token = None
        self._token_expires_at = 0.0


__all__ = ["OAuthTokenManager"]
