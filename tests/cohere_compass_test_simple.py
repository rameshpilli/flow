#!/usr/bin/env python3
"""
Simple Cohere Compass Test (No User Input Required)

Edit the configuration section below with your credentials and run.
"""

import json
import httpx
from datetime import datetime


# ============================================================================
# CONFIGURATION - EDIT THESE VALUES
# ============================================================================

CONFIG = {
    # Required
    "server_url": "https://your-cohere-server.example.com",  # EDIT THIS
    "server_bearer_token": "your_bearer_token_here",  # EDIT THIS
    "index_name": "your_index_name",  # EDIT THIS
    
    # Optional (set to None if not available)
    "parser_url": None,  # EDIT THIS or leave as None
    "parser_bearer_token": None,  # EDIT THIS or leave as None
}

# ============================================================================
# DO NOT EDIT BELOW THIS LINE
# ============================================================================


def test_quick():
    """Quick test of core functionality"""
    print("\n" + "="*70)
    print("  QUICK COHERE COMPASS TEST")
    print("="*70 + "\n")
    
    server_url = CONFIG['server_url'].rstrip('/')
    token = CONFIG['server_bearer_token']
    index = CONFIG['index_name']
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    client = httpx.Client(timeout=30.0)
    results = {}
    
    # Test 1: Server connectivity
    print("TEST 1: Server Connectivity")
    try:
        response = client.get(f"{server_url}/", headers=headers)
        print(f"  ✅ Server reachable - Status: {response.status_code}")
        print(f"  Response: {response.text[:200]}\n")
        results['server_ok'] = True
    except Exception as e:
        print(f"  ❌ Server not reachable: {e}\n")
        results['server_ok'] = False
        return
    
    # Test 2: Embeddings
    print("TEST 2: Embedding Generation")
    endpoints = ["/v1/embed", "/api/v1/embed", "/v2/embed"]
    
    embed_ok = False
    for endpoint in endpoints:
        try:
            payload = {
                "texts": ["test sentence"],
                "model": "embed-english-v3.0",
                "input_type": "search_document"
            }
            response = client.post(
                f"{server_url}{endpoint}",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                embeddings = data.get('embeddings', [])
                if embeddings:
                    dim = len(embeddings[0])
                    print(f"  ✅ Embeddings work via {endpoint}")
                    print(f"  Dimension: {dim}")
                    print(f"  Sample: {embeddings[0][:5]}...\n")
                    results['embed_endpoint'] = endpoint
                    results['embed_dim'] = dim
                    embed_ok = True
                    break
        except:
            continue
    
    if not embed_ok:
        print("  ❌ Could not generate embeddings\n")
        results['embed_ok'] = False
    else:
        results['embed_ok'] = True
    
    # Test 3: Add document
    print("TEST 3: Add Document")
    endpoints = [
        f"/v1/indexes/{index}/documents",
        f"/v1/collections/{index}/documents",
        f"/api/v1/indexes/{index}/add"
    ]
    
    add_ok = False
    for endpoint in endpoints:
        try:
            payload = {
                "documents": [{
                    "id": f"test_{int(datetime.now().timestamp())}",
                    "text": "This is a test memory",
                    "metadata": {"test": True}
                }]
            }
            response = client.post(
                f"{server_url}{endpoint}",
                headers=headers,
                json=payload
            )
            
            if response.status_code in [200, 201]:
                print(f"  ✅ Add document works via {endpoint}")
                print(f"  Response: {response.text[:200]}\n")
                results['add_endpoint'] = endpoint
                add_ok = True
                break
        except Exception as e:
            continue
    
    if not add_ok:
        print("  ❌ Could not add document\n")
        results['add_ok'] = False
    else:
        results['add_ok'] = True
    
    # Test 4: Search
    print("TEST 4: Search Documents")
    endpoints = [
        f"/v1/indexes/{index}/search",
        f"/v1/collections/{index}/search",
        f"/api/v1/indexes/{index}/search"
    ]
    
    search_ok = False
    for endpoint in endpoints:
        try:
            payload = {
                "query": "test memory",
                "top_k": 5
            }
            response = client.post(
                f"{server_url}{endpoint}",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                results_count = len(data.get('results', data.get('documents', [])))
                print(f"  ✅ Search works via {endpoint}")
                print(f"  Found: {results_count} results")
                print(f"  Response: {json.dumps(data, indent=2)[:300]}...\n")
                results['search_endpoint'] = endpoint
                search_ok = True
                break
        except:
            continue
    
    if not search_ok:
        print("  ❌ Could not search documents\n")
        results['search_ok'] = False
    else:
        results['search_ok'] = True
    
    # Test 5: Parser (if provided)
    if CONFIG.get('parser_url'):
        print("TEST 5: Parser Service")
        parser_url = CONFIG['parser_url'].rstrip('/')
        parser_token = CONFIG['parser_bearer_token']
        
        parser_headers = {
            "Authorization": f"Bearer {parser_token}",
            "Content-Type": "application/json"
        }
        
        try:
            payload = {
                "text": "This is a test document to parse",
                "chunk_size": 100
            }
            response = client.post(
                f"{parser_url}/v1/parse",
                headers=parser_headers,
                json=payload
            )
            
            if response.status_code == 200:
                print(f"  ✅ Parser works")
                print(f"  Response: {response.text[:200]}\n")
                results['parser_ok'] = True
            else:
                print(f"  ❌ Parser failed: {response.status_code}\n")
                results['parser_ok'] = False
        except Exception as e:
            print(f"  ❌ Parser error: {e}\n")
            results['parser_ok'] = False
    
    # Summary
    print("="*70)
    print("  SUMMARY")
    print("="*70 + "\n")
    
    all_good = (
        results.get('server_ok') and
        results.get('embed_ok') and
        results.get('add_ok') and
        results.get('search_ok')
    )
    
    if all_good:
        print("🎉 ALL TESTS PASSED - Ready for mem0 integration!\n")
        print("Configuration for mem0:")
        print(f"  COHERE_SERVER_URL={CONFIG['server_url']}")
        print(f"  COHERE_BEARER_TOKEN=<your-token>")
        print(f"  COHERE_INDEX_NAME={CONFIG['index_name']}")
        if results.get('embed_endpoint'):
            print(f"  COHERE_EMBED_ENDPOINT={results['embed_endpoint']}")
        if results.get('add_endpoint'):
            print(f"  COHERE_ADD_ENDPOINT={results['add_endpoint']}")
        if results.get('search_endpoint'):
            print(f"  COHERE_SEARCH_ENDPOINT={results['search_endpoint']}")
    else:
        print("⚠️  SOME TESTS FAILED\n")
        print("Failed:")
        if not results.get('server_ok'):
            print("  ❌ Server connectivity")
        if not results.get('embed_ok'):
            print("  ❌ Embedding generation")
        if not results.get('add_ok'):
            print("  ❌ Adding documents")
        if not results.get('search_ok'):
            print("  ❌ Searching documents")
    
    print("\n" + "="*70 + "\n")
    
    # Save results
    with open('cohere_quick_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("📄 Results saved to: cohere_quick_test_results.json\n")
    
    client.close()


if __name__ == "__main__":
    # Check if configuration is set
    if CONFIG['server_url'] == "https://your-cohere-server.example.com":
        print("\n⚠️  Please edit the CONFIG section in this file first!\n")
        print("Update these values:")
        print("  - server_url")
        print("  - server_bearer_token")
        print("  - index_name")
        print("\nThen run again: python cohere_compass_test_simple.py\n")
    else:
        test_quick()
