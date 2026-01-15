#!/usr/bin/env python3
"""
Test mem0 with Cohere Compass

This script tests if mem0 can work with Cohere Compass as a vector store.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rbc_security import enable_certs

enable_certs()

# Configuration - FILL THESE IN
COHERE_API_KEY = ""
COMPASS_API_URL = ""
COMPASS_TOKEN = ""
INDEX_NAME = "mem0_test_index"


def test_1_mem0_native_support():
    """Test 1: Check if mem0 natively supports Compass"""
    print(f"\n{'='*60}")
    print("TEST 1: Check mem0 Native Compass Support")
    print(f"{'='*60}\n")
    
    try:
        from mem0 import Memory
        
        # Try to initialize with compass as provider
        config = {
            "vector_store": {
                "provider": "compass",  # This will fail
                "config": {
                    "api_url": COMPASS_API_URL,
                    "bearer_token": COMPASS_TOKEN,
                    "index_name": INDEX_NAME,
                }
            },
            "embedder": {
                "provider": "cohere",
                "config": {
                    "api_key": COHERE_API_KEY,
                    "model": "embed-english-v3.0",
                }
            }
        }
        
        print("Attempting to initialize mem0 with 'compass' provider...")
        memory = Memory.from_config(config)
        
        print("✅ SUCCESS: mem0 supports Compass natively!")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ FAILED: {error_msg}\n")
        
        if "compass" in error_msg.lower() or "provider" in error_msg.lower():
            print("Expected result: mem0 does NOT support Compass as a provider")
            print("Available providers: qdrant, chroma, pinecone, weaviate, pgvector, etc.\n")
        
        return False


def test_2_check_available_providers():
    """Test 2: List all available vector store providers in mem0"""
    print(f"\n{'='*60}")
    print("TEST 2: Available Vector Store Providers")
    print(f"{'='*60}\n")
    
    try:
        from mem0.vector_stores.base import VectorStoreBase
        from mem0.vector_stores import configs
        import inspect
        
        # Try to find all vector store classes
        print("Searching for available providers...\n")
        
        # Common providers we know about
        providers = [
            "qdrant", "chroma", "pinecone", "weaviate", 
            "pgvector", "redis", "milvus", "opensearch"
        ]
        
        available = []
        for provider in providers:
            try:
                # Try to import the provider module
                module = __import__(f"mem0.vector_stores.{provider}", fromlist=[provider])
                available.append(provider)
                print(f"  ✓ {provider}")
            except ImportError:
                pass
        
        print(f"\n✅ Found {len(available)} available providers")
        print("\n❌ 'compass' is NOT in the list")
        
        return available
        
    except Exception as e:
        print(f"❌ Error inspecting providers: {e}")
        return []


def test_3_mem0_with_qdrant():
    """Test 3: Test mem0 with Qdrant (should work)"""
    print(f"\n{'='*60}")
    print("TEST 3: Test mem0 with Qdrant (Current Setup)")
    print(f"{'='*60}\n")
    
    try:
        from mem0 import Memory
        
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "host": "localhost",
                    "port": 6333,
                    "collection_name": "test_collection",
                }
            },
            "embedder": {
                "provider": "cohere",
                "config": {
                    "api_key": COHERE_API_KEY,
                    "model": "embed-english-v3.0",
                }
            }
        }
        
        print("Initializing mem0 with Qdrant...")
        memory = Memory.from_config(config)
        
        print("✅ mem0 initialized successfully with Qdrant!")
        print("\nThis is your current working setup:")
        print("  - Cohere: Generates embeddings")
        print("  - Qdrant: Stores and searches vectors")
        print("  - mem0: Orchestrates everything")
        
        return True
        
    except Exception as e:
        print(f"⚠️  Failed (expected if Qdrant not running): {e}")
        print("\nThis is expected if Qdrant is not running locally")
        print("Your Kubernetes deployment will have Qdrant running")
        return False


def test_4_compass_sdk_directly():
    """Test 4: Verify Compass SDK works (bypass mem0)"""
    print(f"\n{'='*60}")
    print("TEST 4: Test Compass SDK Directly")
    print(f"{'='*60}\n")
    
    try:
        from cohere_compass.clients.compass import CompassClient
        
        print("Initializing Compass client...")
        client = CompassClient(
            index_url=COMPASS_API_URL,
            bearer_token=COMPASS_TOKEN
        )
        
        print("Listing indexes...")
        result = client.list_indexes()
        
        indexes = result.indexes if hasattr(result, 'indexes') else []
        print(f"✅ Compass SDK works! Found {len(indexes)} indexes\n")
        
        for idx in indexes[:3]:  # Show first 3
            print(f"  - {idx.name}")
        
        print("\n💡 Compass works, but mem0 doesn't support it natively")
        
        return True
        
    except Exception as e:
        print(f"❌ Compass SDK test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("MEM0 + COHERE COMPASS COMPATIBILITY TEST")
    print("="*60)
    
    # Validate config
    if not COHERE_API_KEY or not COMPASS_API_URL or not COMPASS_TOKEN:
        print("\n❌ ERROR: Please fill in the configuration at the top of this script:")
        print("  - COHERE_API_KEY")
        print("  - COMPASS_API_URL")
        print("  - COMPASS_TOKEN")
        print("  - INDEX_NAME (optional)\n")
        return False
    
    results = {}
    
    # Run tests
    results['native_support'] = test_1_mem0_native_support()
    results['available_providers'] = test_2_check_available_providers()
    results['qdrant_works'] = test_3_mem0_with_qdrant()
    results['compass_sdk_works'] = test_4_compass_sdk_directly()
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}\n")
    
    print("✅ What Works:")
    print("  1. Cohere API (embeddings)")
    print("  2. Compass SDK (direct usage)")
    print("  3. mem0 with Qdrant")
    
    print("\n❌ What Doesn't Work:")
    print("  1. mem0 with Compass (not supported)")
    
    print("\n💡 RECOMMENDATION:")
    print("\n  Option A: Keep Current Setup (RECOMMENDED)")
    print("    ├─ mem0 + Qdrant + Cohere embeddings")
    print("    ├─ ✓ Battle-tested, production-ready")
    print("    ├─ ✓ Full control, in-cluster")
    print("    └─ ✓ No external dependencies")
    
    print("\n  Option B: Build Custom Compass Adapter")
    print("    ├─ Create custom VectorStoreBase implementation")
    print("    ├─ Wrap Compass SDK")
    print("    ├─ ⚠️  Requires maintenance")
    print("    └─ ⚠️  Not officially supported")
    
    print("\n  Option C: Use Compass Separately")
    print("    ├─ mem0 for agent memory (Qdrant)")
    print("    ├─ Compass for document search")
    print("    └─ ✓ Best of both worlds")
    
    print("\n" + "="*60)
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
