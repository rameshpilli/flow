"""
AgentOrchestrator Chains Module

Provides base classes and utilities for building chains.

For application-specific chains, create them in your own package.
Example:
    from agentorchestrator import AgentOrchestrator

    ao = AgentOrchestrator(name="my_app")

    @ao.chain(name="my_chain")
    class MyChain:
        steps = ["step1", "step2"]
"""

__all__: list[str] = []
