#!/usr/bin/env python3
"""
Cohere Compass/Enterprise Test Suite

Tests what features are available with your corporate Cohere deployment.
Run this to understand what you have access to before integrating with mem0.
"""

import sys
import json
import time
from typing import Dict, Any, List, Optional
import httpx
from datetime import datetime


class CohereCompassTester:
    """Test suite for Cohere Compass/Enterprise deployment"""
    
    def __init__(
        self,
        server_url: str,
        server_bearer_token: str,
        index_name: str,
        parser_url: Optional[str] = None,
        parser_bearer_token: Optional[str] = None
    ):
        self.server_url = server_url.rstrip('/')
        self.server_bearer_token = server_bearer_token
        self.index_name = index_name
        self.parser_url = parser_url.rstrip('/') if parser_url else None
        self.parser_bearer_token = parser_bearer_token
        
        self.client = httpx.Client(timeout=30.0)
        self.results = {}
        
    def _make_request(
        self,
        method: str,
        url: str,
        bearer_token: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> tuple[bool, Any, str]:
        """Make HTTP request and return (success, data, message)"""
        try:
            headers = {
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json"
            }
            
            response = self.client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params
            )
            
            # Try to parse JSON response
            try:
                data = response.json()
            except:
                data = response.text
            
            if response.status_code in [200, 201]:
                return True, data, f"Success ({response.status_code})"
            else:
                return False, data, f"Error {response.status_code}: {data}"
                
        except httpx.TimeoutException:
            return False, None, "Request timeout (30s)"
        except httpx.ConnectError as e:
            return False, None, f"Connection error: {e}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"
    
    def print_section(self, title: str):
        """Print section header"""
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}\n")
    
    def print_test(self, name: str, success: bool, message: str, details: Any = None):
        """Print test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} | {name}")
        print(f"       {message}")
        if details:
            print(f"       Details: {json.dumps(details, indent=2)[:200]}...")
        print()
    
    # ========================================================================
    # TEST 1: Basic Connectivity
    # ========================================================================
    
    def test_server_connectivity(self):
        """Test if server is reachable"""
        self.print_section("TEST 1: Server Connectivity")
        
        # Test main server
        success, data, message = self._make_request(
            "GET",
            f"{self.server_url}/",
            self.server_bearer_token
        )
        
        self.results['server_reachable'] = success
        self.print_test("Server Reachable", success, message, data if success else None)
        
        # Test parser if provided
        if self.parser_url:
            success, data, message = self._make_request(
                "GET",
                f"{self.parser_url}/",
                self.parser_bearer_token
            )
            self.results['parser_reachable'] = success
            self.print_test("Parser Reachable", success, message, data if success else None)
    
    # ========================================================================
    # TEST 2: Authentication
    # ========================================================================
    
    def test_authentication(self):
        """Test bearer token authentication"""
        self.print_section("TEST 2: Authentication")
        
        # Common Cohere endpoints to test
        endpoints = [
            "/v1/check-api-key",
            "/health",
            "/v1/models",
            "/api/v1/models",
        ]
        
        auth_success = False
        for endpoint in endpoints:
            success, data, message = self._make_request(
                "GET",
                f"{self.server_url}{endpoint}",
                self.server_bearer_token
            )
            
            if success:
                auth_success = True
                self.print_test(f"Auth via {endpoint}", True, message, data)
                break
        
        if not auth_success:
            self.print_test("Authentication", False, "Could not verify auth with any known endpoint", None)
        
        self.results['authenticated'] = auth_success
    
    # ========================================================================
    # TEST 3: Embedding Generation
    # ========================================================================
    
    def test_embeddings(self):
        """Test embedding generation"""
        self.print_section("TEST 3: Embedding Generation")
        
        test_texts = [
            "This is a test sentence for embedding.",
            "Memory store integration test."
        ]
        
        # Try different API paths
        api_paths = [
            "/v1/embed",
            "/api/v1/embed",
            "/v2/embed",
            "/embed"
        ]
        
        embed_success = False
        for path in api_paths:
            payload = {
                "texts": test_texts,
                "model": "embed-english-v3.0",
                "input_type": "search_document"
            }
            
            success, data, message = self._make_request(
                "POST",
                f"{self.server_url}{path}",
                self.server_bearer_token,
                json_data=payload
            )
            
            if success:
                embed_success = True
                embeddings = data.get('embeddings', [])
                
                details = {
                    "endpoint": path,
                    "num_embeddings": len(embeddings),
                    "embedding_dim": len(embeddings[0]) if embeddings else 0,
                    "sample": embeddings[0][:5] if embeddings else []
                }
                
                self.results['embeddings_available'] = True
                self.results['embedding_endpoint'] = path
                self.results['embedding_dimension'] = details['embedding_dim']
                
                self.print_test("Generate Embeddings", True, message, details)
                break
        
        if not embed_success:
            self.results['embeddings_available'] = False
            self.print_test("Generate Embeddings", False, "Could not generate embeddings via any endpoint", None)
    
    # ========================================================================
    # TEST 4: Index Operations (Compass-specific)
    # ========================================================================
    
    def test_index_operations(self):
        """Test Compass index operations"""
        self.print_section("TEST 4: Index/Collection Operations")
        
        # Try to list indices/collections
        list_paths = [
            "/v1/indexes",
            "/v1/collections",
            "/api/v1/indexes",
            "/indexes"
        ]
        
        for path in list_paths:
            success, data, message = self._make_request(
                "GET",
                f"{self.server_url}{path}",
                self.server_bearer_token
            )
            
            if success:
                self.results['can_list_indexes'] = True
                self.print_test(f"List Indexes via {path}", True, message, data)
                break
        
        # Try to get specific index info
        index_paths = [
            f"/v1/indexes/{self.index_name}",
            f"/v1/collections/{self.index_name}",
            f"/api/v1/indexes/{self.index_name}"
        ]
        
        for path in index_paths:
            success, data, message = self._make_request(
                "GET",
                f"{self.server_url}{path}",
                self.server_bearer_token
            )
            
            if success:
                self.results['index_exists'] = True
                self.results['index_info'] = data
                self.print_test(f"Get Index '{self.index_name}'", True, message, data)
                break
    
    # ========================================================================
    # TEST 5: Document Operations (Add/Search)
    # ========================================================================
    
    def test_document_operations(self):
        """Test adding and searching documents"""
        self.print_section("TEST 5: Document Add & Search")
        
        # Generate test document
        test_doc_id = f"test_doc_{int(time.time())}"
        test_text = "This is a test memory from the integration test suite."
        test_metadata = {
            "agent_id": "test_agent",
            "timestamp": datetime.utcnow().isoformat(),
            "test": True
        }
        
        # Try to add document
        add_paths = [
            f"/v1/indexes/{self.index_name}/documents",
            f"/v1/collections/{self.index_name}/documents",
            f"/api/v1/indexes/{self.index_name}/add",
            f"/v1/indexes/{self.index_name}/add"
        ]
        
        add_success = False
        for path in add_paths:
            payload = {
                "documents": [{
                    "id": test_doc_id,
                    "text": test_text,
                    "metadata": test_metadata
                }]
            }
            
            success, data, message = self._make_request(
                "POST",
                f"{self.server_url}{path}",
                self.server_bearer_token,
                json_data=payload
            )
            
            if success:
                add_success = True
                self.results['can_add_documents'] = True
                self.results['add_endpoint'] = path
                self.print_test("Add Document", True, message, data)
                break
        
        if not add_success:
            self.results['can_add_documents'] = False
            self.print_test("Add Document", False, "Could not add document via any endpoint", None)
        
        # Try to search documents
        if add_success:
            time.sleep(1)  # Wait for indexing
            
            search_paths = [
                f"/v1/indexes/{self.index_name}/search",
                f"/v1/collections/{self.index_name}/search",
                f"/api/v1/indexes/{self.index_name}/search",
                f"/v1/search"
            ]
            
            for path in search_paths:
                payload = {
                    "query": "test memory integration",
                    "top_k": 5
                }
                
                success, data, message = self._make_request(
                    "POST",
                    f"{self.server_url}{path}",
                    self.server_bearer_token,
                    json_data=payload
                )
                
                if success:
                    self.results['can_search'] = True
                    self.results['search_endpoint'] = path
                    
                    results = data.get('results', data.get('documents', []))
                    self.print_test("Search Documents", True, f"{message} - Found {len(results)} results", data)
                    break
    
    # ========================================================================
    # TEST 6: Parser Service (if available)
    # ========================================================================
    
    def test_parser_service(self):
        """Test parser service if provided"""
        if not self.parser_url:
            return
        
        self.print_section("TEST 6: Parser Service")
        
        # Test document parsing
        test_document = "This is a long document that needs to be parsed and chunked into smaller pieces for better embedding and retrieval."
        
        parse_paths = [
            "/v1/parse",
            "/api/v1/parse",
            "/parse"
        ]
        
        for path in parse_paths:
            payload = {
                "text": test_document,
                "chunk_size": 100,
                "chunk_overlap": 20
            }
            
            success, data, message = self._make_request(
                "POST",
                f"{self.parser_url}{path}",
                self.parser_bearer_token,
                json_data=payload
            )
            
            if success:
                self.results['parser_available'] = True
                self.results['parser_endpoint'] = path
                self.print_test("Parse Document", True, message, data)
                break
    
    # ========================================================================
    # TEST 7: Available Models
    # ========================================================================
    
    def test_available_models(self):
        """Check what models are available"""
        self.print_section("TEST 7: Available Models")
        
        model_paths = [
            "/v1/models",
            "/api/v1/models",
            "/models"
        ]
        
        for path in model_paths:
            success, data, message = self._make_request(
                "GET",
                f"{self.server_url}{path}",
                self.server_bearer_token
            )
            
            if success:
                models = data.get('models', data.get('data', []))
                
                embedding_models = [m for m in models if 'embed' in str(m).lower()]
                
                self.results['available_models'] = models
                self.results['embedding_models'] = embedding_models
                
                details = {
                    "total_models": len(models),
                    "embedding_models": embedding_models[:5]  # First 5
                }
                
                self.print_test("List Available Models", True, message, details)
                break
    
    # ========================================================================
    # Run All Tests
    # ========================================================================
    
    def run_all_tests(self):
        """Run complete test suite"""
        print("\n" + "="*70)
        print("  COHERE COMPASS/ENTERPRISE TEST SUITE")
        print("="*70)
        print(f"\nConfiguration:")
        print(f"  Server URL: {self.server_url}")
        print(f"  Index Name: {self.index_name}")
        print(f"  Parser URL: {self.parser_url or 'Not provided'}")
        print(f"  Timestamp: {datetime.utcnow().isoformat()}")
        
        # Run all tests
        self.test_server_connectivity()
        self.test_authentication()
        self.test_embeddings()
        self.test_index_operations()
        self.test_document_operations()
        self.test_parser_service()
        self.test_available_models()
        
        # Print summary
        self.print_summary()
    
    # ========================================================================
    # Summary Report
    # ========================================================================
    
    def print_summary(self):
        """Print summary of what's available"""
        self.print_section("SUMMARY: What You Have Access To")
        
        capabilities = []
        missing = []
        
        # Check capabilities
        if self.results.get('server_reachable'):
            capabilities.append("✅ Server connectivity")
        else:
            missing.append("❌ Server not reachable")
        
        if self.results.get('authenticated'):
            capabilities.append("✅ Authentication working")
        else:
            missing.append("❌ Authentication failed")
        
        if self.results.get('embeddings_available'):
            dim = self.results.get('embedding_dimension', 'unknown')
            endpoint = self.results.get('embedding_endpoint', 'unknown')
            capabilities.append(f"✅ Embeddings ({dim}D) via {endpoint}")
        else:
            missing.append("❌ Embedding generation not available")
        
        if self.results.get('can_add_documents'):
            endpoint = self.results.get('add_endpoint', 'unknown')
            capabilities.append(f"✅ Document storage via {endpoint}")
        else:
            missing.append("❌ Cannot add documents")
        
        if self.results.get('can_search'):
            endpoint = self.results.get('search_endpoint', 'unknown')
            capabilities.append(f"✅ Vector search via {endpoint}")
        else:
            missing.append("❌ Cannot search documents")
        
        if self.results.get('parser_available'):
            endpoint = self.results.get('parser_endpoint', 'unknown')
            capabilities.append(f"✅ Parser service via {endpoint}")
        
        if self.results.get('available_models'):
            count = len(self.results.get('embedding_models', []))
            capabilities.append(f"✅ {count} embedding models available")
        
        # Print capabilities
        print("Available Capabilities:")
        for cap in capabilities:
            print(f"  {cap}")
        
        if missing:
            print("\nMissing/Failed:")
            for miss in missing:
                print(f"  {miss}")
        
        # Integration readiness
        print("\n" + "-"*70)
        ready = (
            self.results.get('server_reachable') and
            self.results.get('authenticated') and
            self.results.get('embeddings_available') and
            self.results.get('can_add_documents') and
            self.results.get('can_search')
        )
        
        if ready:
            print("🎉 READY FOR MEM0 INTEGRATION!")
            print("\nYou have everything needed:")
            print("  • Embeddings generation")
            print("  • Vector storage (add documents)")
            print("  • Vector search")
            print("\nNext steps:")
            print("  1. Update mem0 config with these endpoints")
            print("  2. Configure vector store to use Cohere Compass")
            print("  3. Test with mem0 client")
        else:
            print("⚠️  NOT READY - Missing capabilities")
            print("\nYou need to resolve:")
            for miss in missing:
                print(f"  {miss}")
            print("\nContact your platform team for:")
            print("  • API endpoint documentation")
            print("  • Required permissions/scopes")
            print("  • Index creation (if needed)")
        
        print("\n" + "="*70)
        print(f"Test completed at {datetime.utcnow().isoformat()}")
        print("="*70 + "\n")
        
        # Save results to file
        with open('cohere_test_results.json', 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print("📄 Full results saved to: cohere_test_results.json\n")
    
    def __del__(self):
        """Cleanup"""
        self.client.close()


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("  Cohere Compass Test Configuration")
    print("="*70 + "\n")
    
    # Get configuration from user
    print("Please provide your Cohere configuration:")
    print("(Press Enter to skip optional fields)\n")
    
    server_url = input("Server URL (required): ").strip()
    if not server_url:
        print("❌ Server URL is required!")
        sys.exit(1)
    
    server_token = input("Server Bearer Token (required): ").strip()
    if not server_token:
        print("❌ Server bearer token is required!")
        sys.exit(1)
    
    index_name = input("Index Name (required): ").strip()
    if not index_name:
        print("❌ Index name is required!")
        sys.exit(1)
    
    parser_url = input("Parser URL (optional, press Enter to skip): ").strip() or None
    parser_token = None
    if parser_url:
        parser_token = input("Parser Bearer Token (required if parser URL provided): ").strip()
    
    # Create tester and run
    print("\n🚀 Starting tests...\n")
    
    tester = CohereCompassTester(
        server_url=server_url,
        server_bearer_token=server_token,
        index_name=index_name,
        parser_url=parser_url,
        parser_bearer_token=parser_token
    )
    
    tester.run_all_tests()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}\n")
        sys.exit(1)
