"""
Basic Memory Store Usage Examples

Run these examples to test your Memory Store deployment.
"""

import asyncio
import os
from memory_store.client import MemoryStoreClient


async def example_1_basic_operations():
    """Example 1: Basic memory operations."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Memory Operations")
    print("=" * 60)
    
    # Initialize client
    memory = MemoryStoreClient(
        base_url=os.getenv("MEMORY_STORE_URL", "http://localhost:8000"),
        agent_id="example_agent"
    )
    
    try:
        # Health check
        print("\n1. Checking service health...")
        health = await memory.health_check()
        print(f"   Status: {health.get('status')}")
        
        # Add memories
        print("\n2. Adding memories...")
        await memory.add_memory(
            "User prefers dark mode and Python programming",
            metadata={"category": "preferences"}
        )
        await memory.add_memory(
            "User asked about AAPL Q4 2025 earnings report",
            metadata={"category": "query", "ticker": "AAPL"}
        )
        await memory.add_memory(
            "Python is the user's favorite language for data science",
            metadata={"category": "preferences", "topic": "programming"}
        )
        print("   ✓ Added 3 memories")
        
        # Search memories
        print("\n3. Searching memories...")
        results = await memory.search_memories(
            query="What programming language does the user like?",
            limit=3
        )
        print(f"   Found {len(results)} memories:")
        for i, mem in enumerate(results, 1):
            print(f"   {i}. {mem.get('memory', 'N/A')[:60]}...")
            print(f"      Score: {mem.get('score', 'N/A')}")
        
        # Get all memories
        print("\n4. Getting all memories...")
        all_memories = await memory.get_all_memories(limit=10)
        print(f"   Total memories: {len(all_memories)}")
        
    finally:
        await memory.close()
        print("\n✓ Example completed\n")


async def example_2_context_manager():
    """Example 2: Using context manager."""
    print("\n" + "=" * 60)
    print("Example 2: Context Manager Usage")
    print("=" * 60)
    
    async with MemoryStoreClient(
        base_url=os.getenv("MEMORY_STORE_URL", "http://localhost:8000"),
        agent_id="context_agent"
    ) as memory:
        print("\n1. Adding memory...")
        await memory.add_memory(
            "This is a memory from context manager example"
        )
        
        print("2. Searching...")
        results = await memory.search_memories("context manager")
        print(f"   Found {len(results)} results")
    
    print("3. Connection automatically closed")
    print("\n✓ Example completed\n")


async def example_3_metadata_filtering():
    """Example 3: Using metadata for organization."""
    print("\n" + "=" * 60)
    print("Example 3: Metadata and Organization")
    print("=" * 60)
    
    memory = MemoryStoreClient(
        base_url=os.getenv("MEMORY_STORE_URL", "http://localhost:8000"),
        agent_id="finance_agent"
    )
    
    try:
        # Add memories with rich metadata
        print("\n1. Adding memories with metadata...")
        
        await memory.add_memory(
            "AAPL reported revenue of $119.6B in Q1 2024",
            metadata={
                "ticker": "AAPL",
                "quarter": "Q1",
                "year": "2024",
                "metric": "revenue",
                "importance": "high"
            }
        )
        
        await memory.add_memory(
            "MSFT cloud revenue grew 30% YoY",
            metadata={
                "ticker": "MSFT",
                "category": "cloud",
                "growth": "30%",
                "importance": "medium"
            }
        )
        
        print("   ✓ Added 2 memories with metadata")
        
        # Search
        print("\n2. Searching for Apple...")
        results = await memory.search_memories("Apple earnings", limit=5)
        print(f"   Found {len(results)} results")
        
        for mem in results[:1]:
            print(f"\n   Memory: {mem.get('memory')}")
            print(f"   Metadata: {mem.get('metadata', {})}")
        
    finally:
        await memory.close()
        print("\n✓ Example completed\n")


async def example_4_team_memory():
    """Example 4: Shared team memory."""
    print("\n" + "=" * 60)
    print("Example 4: Team Memory Sharing")
    print("=" * 60)
    
    # Agent 1 - personal and team memory
    agent1_personal = MemoryStoreClient(
        base_url=os.getenv("MEMORY_STORE_URL", "http://localhost:8000"),
        agent_id="analyst_1"
    )
    
    team_memory = MemoryStoreClient(
        base_url=os.getenv("MEMORY_STORE_URL", "http://localhost:8000"),
        agent_id="team_finance"
    )
    
    # Agent 2 - same team
    agent2_personal = MemoryStoreClient(
        base_url=os.getenv("MEMORY_STORE_URL", "http://localhost:8000"),
        agent_id="analyst_2"
    )
    
    try:
        # Agent 1 adds personal memory
        print("\n1. Agent 1 adds personal memory...")
        await agent1_personal.add_memory(
            "I'm analyzing tech stocks today",
            metadata={"agent": "analyst_1", "private": True}
        )
        
        # Agent 1 shares with team
        print("2. Agent 1 shares finding with team...")
        await team_memory.add_memory(
            "Important: Tech sector showing strong momentum",
            metadata={"shared_by": "analyst_1", "importance": "high"}
        )
        
        # Agent 2 searches team memory
        print("3. Agent 2 searches team memory...")
        team_findings = await team_memory.search_memories(
            "tech sector",
            limit=5
        )
        print(f"   Agent 2 found {len(team_findings)} team memories")
        if team_findings:
            print(f"   → {team_findings[0].get('memory')}")
        
        # Agent 2 can't see Agent 1's personal memory
        print("4. Agent 2 searches own personal memory...")
        personal = await agent2_personal.search_memories("analyzing", limit=5)
        print(f"   Found {len(personal)} personal memories (should be 0)")
        
    finally:
        await agent1_personal.close()
        await agent2_personal.close()
        await team_memory.close()
        print("\n✓ Example completed\n")


async def example_5_error_handling():
    """Example 5: Robust error handling."""
    print("\n" + "=" * 60)
    print("Example 5: Error Handling")
    print("=" * 60)
    
    memory = MemoryStoreClient(
        base_url=os.getenv("MEMORY_STORE_URL", "http://localhost:8000"),
        agent_id="robust_agent"
    )
    
    try:
        print("\n1. Testing health check...")
        try:
            health = await memory.health_check()
            print(f"   ✓ Service is {health.get('status')}")
        except Exception as e:
            print(f"   ✗ Health check failed: {e}")
            print("   → Cannot proceed without healthy service")
            return
        
        print("\n2. Adding memory with error handling...")
        try:
            await memory.add_memory(
                "This should work",
                metadata={"test": "error_handling"}
            )
            print("   ✓ Memory added successfully")
        except Exception as e:
            print(f"   ✗ Failed to add memory: {e}")
        
        print("\n3. Search with fallback...")
        results = await memory.search_memories("test query", limit=5)
        if results:
            print(f"   ✓ Found {len(results)} results")
        else:
            print("   → No results, but continuing without error")
        
    finally:
        await memory.close()
        print("\n✓ Example completed\n")


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Memory Store Client Examples")
    print("=" * 60)
    print(f"\nConnecting to: {os.getenv('MEMORY_STORE_URL', 'http://localhost:8000')}")
    print("\nNote: Make sure Memory Store is running!")
    print("  Local: docker-compose up -d")
    print("  K8s: kubectl port-forward -n memory-store svc/mem0-service 8000:8000")
    
    try:
        await example_1_basic_operations()
        await example_2_context_manager()
        await example_3_metadata_filtering()
        await example_4_team_memory()
        await example_5_error_handling()
        
        print("\n" + "=" * 60)
        print("All examples completed successfully! ✓")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n✗ Example failed with error: {e}")
        print("\nTroubleshooting:")
        print("  1. Is Memory Store running? Check: curl http://localhost:8000/health")
        print("  2. Is Cohere API key set?")
        print("  3. Check logs: docker-compose logs memory-store")


if __name__ == "__main__":
    # Set environment variable if not already set
    if "MEMORY_STORE_URL" not in os.environ:
        os.environ["MEMORY_STORE_URL"] = "http://localhost:8000"
    
    asyncio.run(main())
