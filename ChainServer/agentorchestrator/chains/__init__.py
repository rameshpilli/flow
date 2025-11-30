"""
AgentOrchestrator Chains Module

Provides pre-built chain implementations.

Usage:
    from agentorchestrator.chains import CMPTChain

    chain = CMPTChain()
    result = await chain.run(corporate_company_name="Apple Inc")
"""

from agentorchestrator.chains.cmpt import CMPTChain

__all__ = ["CMPTChain"]
