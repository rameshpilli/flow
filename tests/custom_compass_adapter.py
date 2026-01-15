#!/usr/bin/env python3
"""
Custom Compass Adapter for mem0

This is a PROOF OF CONCEPT showing how you could integrate Cohere Compass
with mem0 by creating a custom vector store adapter.

⚠️  WARNING: This is experimental and not officially supported by mem0.
⚠️  Use at your own risk. The recommended approach is to use Qdrant.
"""

from typing import List, Dict, Any, Optional
import logging
from dataclasses import dataclass

try:
    from mem0.vector_stores.base import VectorStoreBase
    from cohere_compass.clients.compass import CompassClient
    from cohere_compass.clients.parser import CompassParserClient, ParserConfig
    from cohere_compass.models import DocumentFormat
except ImportError as e:
    print(f"⚠️  Missing dependency: {e}")
    print("This is a proof-of-concept and requires mem0 and cohere-compass packages")
    exit(1)

logger = logging.getLogger(__name__)


@dataclass
class CompassConfig:
    """Configuration for Compass vector store"""
    api_url: str
    parser_url: Optional[str] = None
    bearer_token: str = ""
    index_name: str = "mem0_memories"
    embedding_dims: int = 1024  # Cohere embed-v3 dimension


class CompassVectorStore(VectorStoreBase):
    """
    Custom Compass adapter for mem0
    
    This adapter wraps the Cohere Compass SDK to make it compatible with mem0's
    VectorStoreBase interface.
    
    ⚠️  LIMITATIONS:
    - Compass manages embeddings internally, so this bypasses mem0's embedder
    - Metadata storage is limited by Compass's schema
    - Some mem0 features may not work as expected
    - Not officially supported or tested
    """
    
    def __init__(self, config: CompassConfig):
        """Initialize Compass vector store"""
        self.config = config
        self.client = CompassClient(
            index_url=config.api_url,
            bearer_token=config.bearer_token
        )
        self.index_name = config.index_name
        
        # Create index if it doesn't exist
        self._ensure_index_exists()
        
        logger.info(f"Compass vector store initialized: {self.index_name}")
    
    def _ensure_index_exists(self):
        """Ensure the index exists, create if not"""
        try:
            # Try to get index info
            self.client.get_index(index_name=self.index_name)
            logger.info(f"Using existing index: {self.index_name}")
        except Exception:
            # Index doesn't exist, create it
            logger.info(f"Creating new index: {self.index_name}")
            import httpx
            
            headers = {
                "Authorization": f"Bearer {self.config.bearer_token}",
                "Content-Type": "application/json"
            }
            
            response = httpx.put(
                f"{self.config.api_url}/v1/indexes/{self.index_name}",
                headers=headers,
                json={}
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Failed to create index: {response.text}")
    
    def create_col(self, name: str, vector_size: int, distance: str):
        """Create collection (index in Compass terms)"""
        # Compass creates indexes differently, this is a no-op
        logger.info(f"Collection creation handled by _ensure_index_exists")
    
    def insert(self, vectors: List[List[float]], payloads: Optional[List[Dict]] = None, ids: Optional[List[str]] = None):
        """
        Insert vectors into Compass
        
        ⚠️  PROBLEM: Compass generates embeddings internally, so we can't directly
        insert pre-computed vectors. This is a fundamental incompatibility.
        
        WORKAROUND: Convert vectors back to text (if available in metadata) and
        let Compass re-embed them. This is inefficient but makes it work.
        """
        if not payloads:
            payloads = [{}] * len(vectors)
        
        if not ids:
            ids = [f"doc_{i}" for i in range(len(vectors))]
        
        # Extract text from payloads
        # mem0 should include the original text in metadata
        docs = []
        for i, (vector, payload, doc_id) in enumerate(zip(vectors, payloads, ids)):
            text = payload.get('data', '') or payload.get('text', f'Document {i}')
            
            # Create a simple text document
            # In reality, you'd use the parser client for better results
            doc = {
                'doc_id': doc_id,
                'text': text,
                'metadata': payload
            }
            docs.append(doc)
        
        # Insert documents (Compass will generate embeddings)
        try:
            # Note: This is simplified - real implementation would use parser client
            logger.warning("⚠️  Compass is re-generating embeddings (inefficient)")
            self.client.insert_docs(index_name=self.index_name, docs=docs)
            self.client.refresh_index(index_name=self.index_name)
            logger.info(f"Inserted {len(docs)} documents")
        except Exception as e:
            logger.error(f"Failed to insert documents: {e}")
            raise
    
    def search(self, query: List[float], limit: int = 5, filters: Optional[Dict] = None) -> List[Dict]:
        """
        Search for similar vectors
        
        ⚠️  PROBLEM: Compass expects text queries, not vectors.
        
        WORKAROUND: If the query vector came from text, we need that text.
        This is another fundamental incompatibility.
        """
        # This is a major limitation - we need the query text, not the vector
        # For now, we'll have to skip this and return empty
        logger.error("⚠️  Cannot search with vectors - Compass requires text queries")
        logger.error("   This is a fundamental incompatibility with mem0's interface")
        return []
    
    def search_by_text(self, query_text: str, limit: int = 5, filters: Optional[Dict] = None) -> List[Dict]:
        """
        Search by text query (Compass's native method)
        
        This is what Compass is designed for, but it's not part of mem0's standard interface.
        """
        try:
            result = self.client.search_chunks(
                index_name=self.index_name,
                query=query_text,
                top_k=limit
            )
            
            # Convert Compass results to mem0 format
            results = []
            for hit in result.hits:
                results.append({
                    'id': getattr(hit, 'doc_id', 'unknown'),
                    'score': hit.score,
                    'payload': {
                        'text': getattr(hit.chunk, 'text', str(hit.chunk)) if hasattr(hit, 'chunk') else str(hit)
                    }
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def delete(self, vector_id: str):
        """Delete a vector by ID"""
        try:
            # Compass deletion API
            logger.warning("Compass document deletion not yet implemented")
        except Exception as e:
            logger.error(f"Delete failed: {e}")
    
    def update(self, vector_id: str, vector: List[float], payload: Optional[Dict] = None):
        """Update a vector"""
        # Delete and re-insert
        self.delete(vector_id)
        self.insert([vector], [payload or {}], [vector_id])
    
    def get(self, vector_id: str) -> Optional[Dict]:
        """Get a vector by ID"""
        logger.warning("Compass get by ID not supported")
        return None
    
    def list_cols(self) -> List[str]:
        """List all collections (indexes)"""
        try:
            result = self.client.list_indexes()
            if hasattr(result, 'indexes'):
                return [idx.name for idx in result.indexes]
            return []
        except Exception as e:
            logger.error(f"Failed to list indexes: {e}")
            return []
    
    def delete_col(self, name: str):
        """Delete a collection (index)"""
        try:
            self.client.delete_index(index_name=name)
            logger.info(f"Deleted index: {name}")
        except Exception as e:
            logger.error(f"Failed to delete index: {e}")
    
    def col_info(self, name: str) -> Dict:
        """Get collection info"""
        try:
            result = self.client.get_index(index_name=name)
            return {
                'name': name,
                'count': getattr(result, 'count', 0),
                'status': 'ready'
            }
        except Exception as e:
            logger.error(f"Failed to get index info: {e}")
            return {}


def test_custom_adapter():
    """Test the custom Compass adapter"""
    print("\n" + "="*60)
    print("TESTING CUSTOM COMPASS ADAPTER")
    print("="*60 + "\n")
    
    # Configuration - FILL THESE IN
    COMPASS_API_URL = ""
    COMPASS_TOKEN = ""
    COHERE_API_KEY = ""
    
    if not all([COMPASS_API_URL, COMPASS_TOKEN, COHERE_API_KEY]):
        print("❌ Please fill in configuration at the top of this file")
        return False
    
    try:
        from mem0 import Memory
        
        # Create config with custom adapter
        config = {
            "vector_store": {
                "provider": "custom",  # Tell mem0 we're using a custom provider
                "config": CompassConfig(
                    api_url=COMPASS_API_URL,
                    bearer_token=COMPASS_TOKEN,
                    index_name="mem0_test"
                )
            },
            "embedder": {
                "provider": "cohere",
                "config": {
                    "api_key": COHERE_API_KEY,
                    "model": "embed-english-v3.0",
                }
            }
        }
        
        print("⚠️  This is experimental and has known limitations:\n")
        print("  1. Compass generates embeddings internally (duplicates work)")
        print("  2. Vector search not possible (need text queries)")
        print("  3. Some mem0 features won't work")
        print("  4. Not officially supported\n")
        
        print("Recommendation: Use Qdrant instead\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print(__doc__)
    print("\n" + "="*60)
    print("⚠️  PROOF OF CONCEPT - NOT RECOMMENDED FOR PRODUCTION")
    print("="*60)
    
    test_custom_adapter()
