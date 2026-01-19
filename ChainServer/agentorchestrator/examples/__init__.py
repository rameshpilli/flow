"""
AgentOrchestrator Examples

This module contains example implementations demonstrating various patterns
for using AgentOrchestrator.

Examples:
    - supervisor_chain: Multi-agent supervisor pattern with @ao decorators
"""

from agentorchestrator.examples.supervisor_chain import (
    create_supervisor_orchestrator,
    create_squad_supervisor_orchestrator,
    run_example,
)

__all__ = [
    "create_supervisor_orchestrator",
    "create_squad_supervisor_orchestrator",
    "run_example",
]
