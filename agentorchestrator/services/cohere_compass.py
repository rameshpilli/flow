"""
AgentOrchestrator Cohere Compass Service
========================================

Service for interacting with Cohere Compass/Enterprise deployment for
RAG (Retrieval-Augmented Generation) applications.
"""

import logging
import time
from typing import Any, Dict, Iterable, List, Optional
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

class CohereCompassService:
    """
    Service for Cohere Compass index and search operations.
    """
    
    def __init__(
        self,
        server_url: str,
        api_key: str,
        index_name: str,
        timeout: float = 30.0,
        verify_ssl: bool = True,
    ):
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.index_name = index_name
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout, verify=verify_ssl)

    async def upsert(self, documents: List[Dict[str, Any]]) -> bool:
        """
        Add or update documents in the Compass index.
        Expects documents in format: [{"id": "...", "text": "...", "metadata": {...}}]
        """
        # Compass endpoints often vary, we'll try the common ones or allow override
        # Based on test script, common is /v1/indexes/{index}/documents
        url = f"{self.server_url}/v1/indexes/{self.index_name}/documents"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {"documents": documents}
        
        try:
            resp = await self._client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Cohere Compass upsert failed: {e}")
            # Try fallback endpoint if needed, but for now we'll fail fast
            raise

    async def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search the Compass index.
        """
        url = f"{self.server_url}/v1/indexes/{self.index_name}/search"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "query": query_text,
            "top_k": top_k
        }
        
        try:
            resp = await self._client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # Compass returns results in 'results' or 'documents' key
            return data.get('results', data.get('documents', []))
        except Exception as e:
            logger.error(f"Cohere Compass query failed: {e}")
            return []

    async def parse(
        self,
        text: str,
        parser_url: Optional[str] = None,
        parser_token: Optional[str] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Parse and chunk text using the Cohere Compass parser service.
        """
        url = f"{(parser_url or self.server_url).rstrip('/')}/v1/parse"
        token = parser_token or self.api_key
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap
        }
        
        try:
            resp = await self._client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Cohere Compass parsing failed: {e}")
            return [{"text": text}] # Fallback to single chunk

    async def health_check(self) -> bool:
        """Check server connectivity."""
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            # Many Cohere deployments have a /health or /v1/models endpoint
            resp = await self._client.get(f"{self.server_url}/health", headers=headers)
            if resp.status_code == 404:
                # Try generic root if /health doesn't exist
                resp = await self._client.get(f"{self.server_url}/", headers=headers)
            return resp.status_code < 400
        except Exception:
            return False

    async def close(self):
        await self._client.aclose()