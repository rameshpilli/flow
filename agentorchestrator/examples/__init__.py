"""
AgentOrchestrator Examples
==========================

Comprehensive examples demonstrating AgentOrchestrator capabilities.

Example Categories:
    - getting_started: Hello world, simple chains, parallel execution
    - memory: Chat storage (InMemory, Redis) and semantic memory (Mem0)
    - rag: Retrieval-augmented generation pipelines
    - agents: Multi-agent orchestration patterns

Quick Start:
    from agentorchestrator.examples.getting_started import run_hello_world
    import asyncio
    asyncio.run(run_hello_world())

For full documentation, see the README in each subdirectory.
"""

# Getting Started examples
from agentorchestrator.examples.getting_started import (
    create_hello_world_orchestrator,
    run_hello_world,
    create_simple_chain_orchestrator,
    run_simple_chain,
    create_parallel_orchestrator,
    run_parallel_example,
)

# Legacy exports for backward compatibility
from agentorchestrator.examples.supervisor_chain import (
    create_supervisor_orchestrator,
    create_squad_supervisor_orchestrator,
    run_example,
)

from agentorchestrator.examples.usage_examples import (
    create_simple_chain,
    run_simple_chain_example,
    run_supervisor_example,
    run_squad_supervisor_example,
)

__all__ = [
    # Getting started
    "create_hello_world_orchestrator",
    "run_hello_world",
    "create_simple_chain_orchestrator",
    "run_simple_chain",
    "create_parallel_orchestrator",
    "run_parallel_example",
    # Supervisor chain
    "create_supervisor_orchestrator",
    "create_squad_supervisor_orchestrator",
    "run_example",
    # Usage examples
    "create_simple_chain",
    "run_simple_chain_example",
    "run_supervisor_example",
    "run_squad_supervisor_example",
]
