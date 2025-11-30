"""
CMPT (Client Meeting Prep Tool) Chain Example

This is an example implementation using the FlowForge framework.
It demonstrates how to build a production-ready chain for preparing
client meeting materials.

Usage:
    from examples.cmpt import CMPTChain, create_cmpt_chain

    chain = create_cmpt_chain()
    result = await chain.run({"company": "Apple Inc"})
"""

from examples.cmpt.chains.cmpt import CMPTChain, create_cmpt_chain

__all__ = [
    "CMPTChain",
    "create_cmpt_chain",
]
