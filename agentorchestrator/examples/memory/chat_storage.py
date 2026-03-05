"""
Chat Storage Example
====================

Demonstrates conversation storage with InMemory and Redis backends.

Usage:
    # InMemory storage (default)
    python chat_storage.py

    # Redis storage (requires Redis running)
    python chat_storage.py --redis

What this example demonstrates:
    - Saving chat messages with user/session/agent scoping
    - Retrieving conversation history
    - Clearing chat history
    - Switching between storage backends

Expected output:
    === InMemory Chat Storage Example ===

    Saving messages...
    [user] Hello, I need help with Python.
    [assistant] Of course! What Python topic would you like to explore?
    [user] How do I use async/await?

    Fetching history...
    Retrieved 3 messages

    History:
    1. [user] Hello, I need help with Python.
    2. [assistant] Of course! What Python topic would you like to explore?
    3. [user] How do I use async/await?
"""

from __future__ import annotations

import asyncio
import argparse

from agentorchestrator.squad.storage import InMemoryChatStorage
from agentorchestrator.squad.types import ConversationMessage


async def run_inmemory_example():
    """
    Run the InMemory chat storage example.

    InMemoryChatStorage is ideal for:
    - Development and testing
    - Short-lived sessions
    - Environments without Redis
    """
    print("=== InMemory Chat Storage Example ===\n")

    # Create storage
    storage = InMemoryChatStorage()

    # Define conversation participants
    user_id = "user-123"
    session_id = "session-abc"
    agent_id = "assistant"

    # Simulate a conversation
    messages = [
        {"role": "user", "content": "Hello, I need help with Python."},
        {"role": "assistant", "content": "Of course! What Python topic would you like to explore?"},
        {"role": "user", "content": "How do I use async/await?"},
    ]

    print("Saving messages...")
    for msg in messages:
        print(f"  [{msg['role']}] {msg['content']}")
        await storage.save_chat_message(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            new_message=ConversationMessage(
                role=msg["role"],
                content=[{"text": msg["content"]}]
            ),
        )

    # Fetch history
    print("\nFetching history...")
    history = await storage.fetch_chat(user_id, session_id, agent_id)
    print(f"Retrieved {len(history)} messages")

    print("\nHistory:")
    for i, msg in enumerate(history, 1):
        text = msg.get_text() if hasattr(msg, 'get_text') else str(msg)
        role = msg.role if hasattr(msg, 'role') else 'unknown'
        print(f"  {i}. [{role}] {text}")

    # Demonstrate max_history_size
    print("\n--- With max_history_size=2 ---")
    limited_history = await storage.fetch_chat(
        user_id, session_id, agent_id, max_history_size=2
    )
    print(f"Retrieved {len(limited_history)} messages (limited)")

    # Clear history
    print("\n--- Clearing history ---")
    await storage.clear_chat(user_id, session_id, agent_id)
    cleared_history = await storage.fetch_chat(user_id, session_id, agent_id)
    print(f"After clear: {len(cleared_history)} messages")

    return {"messages_saved": len(messages), "cleared": True}


async def run_redis_example():
    """
    Run the Redis chat storage example.

    RedisChatStorage is ideal for:
    - Production environments
    - Persistent conversation history
    - Multi-instance deployments

    Requires:
        Redis running on localhost:6379 or configured via environment
    """
    print("=== Redis Chat Storage Example ===\n")

    try:
        from agentorchestrator.squad.storage.redis import RedisChatStorage
    except ImportError:
        print("Redis storage not available. Install with: pip install redis")
        return {"error": "redis not installed"}

    # Create Redis storage
    storage = RedisChatStorage(
        host="localhost",
        port=6379,
        # password="secret",  # Uncomment if Redis requires auth
        # ssl=True,           # Uncomment for TLS
    )

    # Same API as InMemoryChatStorage
    user_id = "user-123"
    session_id = "session-redis"
    agent_id = "assistant"

    messages = [
        {"role": "user", "content": "Store this in Redis."},
        {"role": "assistant", "content": "Message stored persistently!"},
    ]

    print("Saving messages to Redis...")
    for msg in messages:
        print(f"  [{msg['role']}] {msg['content']}")
        await storage.save_chat_message(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            new_message=ConversationMessage(
                role=msg["role"],
                content=[{"text": msg["content"]}]
            ),
        )

    # Fetch and display
    print("\nFetching from Redis...")
    history = await storage.fetch_chat(user_id, session_id, agent_id)
    print(f"Retrieved {len(history)} messages from Redis")

    print("\nThese messages persist across process restarts!")

    return {"messages_saved": len(messages), "storage": "redis"}


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Chat storage examples")
    parser.add_argument(
        "--redis",
        action="store_true",
        help="Use Redis storage instead of InMemory",
    )
    args = parser.parse_args()

    if args.redis:
        asyncio.run(run_redis_example())
    else:
        asyncio.run(run_inmemory_example())


if __name__ == "__main__":
    main()
