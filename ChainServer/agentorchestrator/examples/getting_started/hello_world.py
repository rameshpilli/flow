"""
Hello World Example
====================

The simplest possible AgentOrchestrator chain.

Usage:
    python hello_world.py

    # Or with custom name
    python hello_world.py --name "AgentOrchestrator"

What this example demonstrates:
    - Creating an AgentOrchestrator instance
    - Defining a step with @ao.step()
    - Defining a chain with @ao.chain()
    - Running a chain with ao.launch()
"""

from __future__ import annotations

import asyncio
import argparse

from agentorchestrator import AgentOrchestrator


def create_hello_world_orchestrator() -> AgentOrchestrator:
    """
    Create the hello world orchestrator.

    Returns:
        Configured AgentOrchestrator instance
    """
    ao = AgentOrchestrator(name="hello_world", isolated=True)

    @ao.step(name="greet", description="Generate a greeting message")
    async def greet(ctx):
        """
        Simple greeting step.

        Reads 'name' from context and returns a greeting.
        """
        name = ctx.get("name", "World")
        greeting = f"Hello, {name}!"

        # Store in context for potential downstream steps
        ctx.set("greeting", greeting)

        return {"greeting": greeting}

    @ao.chain(name="hello_chain")
    class HelloChain:
        """Single-step chain that generates a greeting."""
        steps = ["greet"]

    return ao


async def run_hello_world(name: str = "World") -> dict:
    """
    Run the hello world example.

    Args:
        name: Name to greet

    Returns:
        Result dictionary with greeting
    """
    ao = create_hello_world_orchestrator()

    result = await ao.launch("hello_chain", {"name": name})

    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Hello World AgentOrchestrator example")
    parser.add_argument("--name", default="World", help="Name to greet")
    args = parser.parse_args()

    result = asyncio.run(run_hello_world(args.name))

    print(f"\nResult: {result['greeting']}")
    print(f"\nFull result: {result}")


if __name__ == "__main__":
    main()
