"""
AgentOrchestrator Exception Hierarchy
=====================================

Provides a consistent exception hierarchy for the entire framework.
All custom exceptions inherit from AgentOrchestratorError.

Exception Categories:
    - Configuration errors: Invalid setup or missing configuration
    - Execution errors: Runtime failures during chain/step execution  
    - Validation errors: Input/output contract failures
    - Resource errors: Service/resource access failures
    - Agent errors: Agent-specific failures

Usage:
    from agentorchestrator.core.exceptions import (
        ChainNotFoundError,
        StepNotFoundError,
        StepTimeoutError,
    )
    
    try:
        await ao.launch("unknown_chain")
    except ChainNotFoundError as e:
        print(f"Chain not found: {e.chain_name}")

Example:
    >>> from agentorchestrator.core.exceptions import StepExecutionError
    >>> try:
    ...     result = await ao.launch("my_chain")
    ... except StepExecutionError as e:
    ...     print(f"Step {e.step_name} failed: {e}")
"""

from typing import Any, Optional


# =============================================================================
# Base Exception
# =============================================================================


class AgentOrchestratorError(Exception):
    """
    Base exception for all AgentOrchestrator errors.
    
    All custom exceptions in the framework inherit from this class,
    making it easy to catch all framework-specific errors.
    
    Attributes:
        message: Human-readable error message.
        details: Optional dict with additional error context.
    """
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigurationError(AgentOrchestratorError):
    """Base class for configuration-related errors."""
    pass


class ChainNotFoundError(ConfigurationError):
    """
    Raised when a chain cannot be found by name.
    
    Attributes:
        chain_name: The name of the chain that wasn't found.
    """
    
    def __init__(self, chain_name: str, available_chains: Optional[list[str]] = None):
        self.chain_name = chain_name
        self.available_chains = available_chains or []
        
        message = f"Chain not found: '{chain_name}'"
        if self.available_chains:
            message += f". Available chains: {', '.join(self.available_chains)}"
        
        super().__init__(message, {"chain_name": chain_name})


class StepNotFoundError(ConfigurationError):
    """
    Raised when a step cannot be found by name.
    
    Attributes:
        step_name: The name of the step that wasn't found.
        chain_name: Optional chain context where the step was expected.
    """
    
    def __init__(
        self,
        step_name: str,
        chain_name: Optional[str] = None,
        available_steps: Optional[list[str]] = None,
    ):
        self.step_name = step_name
        self.chain_name = chain_name
        self.available_steps = available_steps or []
        
        message = f"Step not found: '{step_name}'"
        if chain_name:
            message += f" in chain '{chain_name}'"
        if self.available_steps:
            message += f". Available steps: {', '.join(self.available_steps[:10])}"
            if len(self.available_steps) > 10:
                message += f" ... and {len(self.available_steps) - 10} more"
        
        super().__init__(
            message,
            {"step_name": step_name, "chain_name": chain_name},
        )


class AgentNotFoundError(ConfigurationError):
    """
    Raised when an agent cannot be found by name.
    
    Attributes:
        agent_name: The name of the agent that wasn't found.
    """
    
    def __init__(self, agent_name: str, available_agents: Optional[list[str]] = None):
        self.agent_name = agent_name
        self.available_agents = available_agents or []
        
        message = f"Agent not found: '{agent_name}'"
        if self.available_agents:
            message += f". Available agents: {', '.join(self.available_agents)}"
        
        super().__init__(message, {"agent_name": agent_name})


class ResourceNotFoundError(ConfigurationError):
    """
    Raised when a resource cannot be found by name.
    
    Attributes:
        resource_name: The name of the resource that wasn't found.
    """
    
    def __init__(self, resource_name: str, available_resources: Optional[list[str]] = None):
        self.resource_name = resource_name
        self.available_resources = available_resources or []
        
        message = f"Resource not found: '{resource_name}'"
        if self.available_resources:
            message += f". Available resources: {', '.join(self.available_resources)}"
        
        super().__init__(message, {"resource_name": resource_name})


class CircularDependencyError(ConfigurationError):
    """
    Raised when circular dependencies are detected in the DAG.
    
    Attributes:
        cycle: List of step names forming the cycle.
        chain_name: The chain where the cycle was detected.
    """
    
    def __init__(self, cycle: list[str], chain_name: Optional[str] = None):
        self.cycle = cycle
        self.chain_name = chain_name
        
        cycle_str = " -> ".join(cycle + [cycle[0]])
        message = f"Circular dependency detected: {cycle_str}"
        if chain_name:
            message = f"In chain '{chain_name}': {message}"
        
        super().__init__(message, {"cycle": cycle, "chain_name": chain_name})


# =============================================================================
# Execution Errors
# =============================================================================


class ExecutionError(AgentOrchestratorError):
    """Base class for execution-related errors."""
    pass


class StepExecutionError(ExecutionError):
    """
    Raised when a step fails during execution.
    
    Attributes:
        step_name: The name of the step that failed.
        chain_name: Optional chain context.
        original_error: The underlying exception.
    """
    
    def __init__(
        self,
        step_name: str,
        message: str,
        chain_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        self.step_name = step_name
        self.chain_name = chain_name
        self.original_error = original_error
        
        full_message = f"Step '{step_name}' failed: {message}"
        if chain_name:
            full_message = f"[{chain_name}] {full_message}"
        
        super().__init__(
            full_message,
            {
                "step_name": step_name,
                "chain_name": chain_name,
                "original_error_type": type(original_error).__name__ if original_error else None,
            },
        )


class StepTimeoutError(StepExecutionError):
    """
    Raised when a step times out.
    
    Attributes:
        step_name: The name of the step that timed out.
        timeout_ms: The timeout in milliseconds.
    """
    
    def __init__(
        self,
        step_name: str,
        timeout_ms: int,
        chain_name: Optional[str] = None,
    ):
        self.timeout_ms = timeout_ms
        super().__init__(
            step_name=step_name,
            message=f"Timed out after {timeout_ms}ms",
            chain_name=chain_name,
        )
        self.details["timeout_ms"] = timeout_ms


class ChainExecutionError(ExecutionError):
    """
    Raised when a chain fails during execution.
    
    Attributes:
        chain_name: The name of the chain that failed.
        failed_step: Optional name of the step that caused the failure.
    """
    
    def __init__(
        self,
        chain_name: str,
        message: str,
        failed_step: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        self.chain_name = chain_name
        self.failed_step = failed_step
        self.original_error = original_error
        
        full_message = f"Chain '{chain_name}' failed: {message}"
        if failed_step:
            full_message += f" (at step '{failed_step}')"
        
        super().__init__(
            full_message,
            {
                "chain_name": chain_name,
                "failed_step": failed_step,
                "original_error_type": type(original_error).__name__ if original_error else None,
            },
        )


class MaxRetriesExceededError(ExecutionError):
    """
    Raised when a step exceeds its maximum retry count.
    
    Attributes:
        step_name: The name of the step that failed.
        max_retries: The maximum number of retries.
        last_error: The last error that occurred.
    """
    
    def __init__(
        self,
        step_name: str,
        max_retries: int,
        last_error: Optional[Exception] = None,
    ):
        self.step_name = step_name
        self.max_retries = max_retries
        self.last_error = last_error
        
        message = f"Step '{step_name}' failed after {max_retries} retries"
        if last_error:
            message += f": {last_error}"
        
        super().__init__(
            message,
            {
                "step_name": step_name,
                "max_retries": max_retries,
                "last_error_type": type(last_error).__name__ if last_error else None,
            },
        )


# =============================================================================
# Validation Errors  
# =============================================================================


class ValidationError(AgentOrchestratorError):
    """Base class for validation-related errors."""
    pass


# ContractValidationError is defined in validation.py for historical reasons
# and re-exported here for consistency


# =============================================================================
# Resource Errors
# =============================================================================


class ResourceError(AgentOrchestratorError):
    """Base class for resource/service errors."""
    pass


class ResourceInitializationError(ResourceError):
    """
    Raised when a resource fails to initialize.
    
    Attributes:
        resource_name: The name of the resource.
    """
    
    def __init__(
        self,
        resource_name: str,
        message: str,
        original_error: Optional[Exception] = None,
    ):
        self.resource_name = resource_name
        self.original_error = original_error
        
        super().__init__(
            f"Failed to initialize resource '{resource_name}': {message}",
            {
                "resource_name": resource_name,
                "original_error_type": type(original_error).__name__ if original_error else None,
            },
        )


class ServiceUnavailableError(ResourceError):
    """
    Raised when an external service is unavailable.
    
    Attributes:
        service_name: The name of the service.
    """
    
    def __init__(
        self,
        service_name: str,
        message: Optional[str] = None,
    ):
        self.service_name = service_name
        
        full_message = f"Service '{service_name}' is unavailable"
        if message:
            full_message += f": {message}"
        
        super().__init__(full_message, {"service_name": service_name})


# =============================================================================
# Agent Errors
# =============================================================================


class AgentError(AgentOrchestratorError):
    """Base class for agent-specific errors."""
    pass


class AgentExecutionError(AgentError):
    """
    Raised when an agent fails during execution.
    
    Attributes:
        agent_name: The name of the agent.
    """
    
    def __init__(
        self,
        agent_name: str,
        message: str,
        original_error: Optional[Exception] = None,
    ):
        self.agent_name = agent_name
        self.original_error = original_error
        
        super().__init__(
            f"Agent '{agent_name}' failed: {message}",
            {
                "agent_name": agent_name,
                "original_error_type": type(original_error).__name__ if original_error else None,
            },
        )


class AgentHandoffError(AgentError):
    """
    Raised when an agent handoff fails.
    
    Attributes:
        source_agent: The agent attempting the handoff.
        target_agent: The intended target agent.
    """
    
    def __init__(
        self,
        source_agent: str,
        target_agent: str,
        reason: str,
    ):
        self.source_agent = source_agent
        self.target_agent = target_agent
        
        super().__init__(
            f"Handoff from '{source_agent}' to '{target_agent}' failed: {reason}",
            {"source_agent": source_agent, "target_agent": target_agent},
        )


class MaxIterationsExceededError(AgentError):
    """
    Raised when an agent exceeds its maximum iteration count (e.g., ReAct loop).
    
    Attributes:
        agent_name: The name of the agent.
        max_iterations: The maximum allowed iterations.
    """
    
    def __init__(self, agent_name: str, max_iterations: int):
        self.agent_name = agent_name
        self.max_iterations = max_iterations
        
        super().__init__(
            f"Agent '{agent_name}' exceeded maximum iterations ({max_iterations})",
            {"agent_name": agent_name, "max_iterations": max_iterations},
        )


# =============================================================================
# Event Errors
# =============================================================================


class EventError(AgentOrchestratorError):
    """Base class for event-related errors."""
    pass


class EventPublishError(EventError):
    """
    Raised when an event fails to publish.
    
    Attributes:
        event_type: The type of event that failed.
    """
    
    def __init__(
        self,
        event_type: str,
        message: str,
        original_error: Optional[Exception] = None,
    ):
        self.event_type = event_type
        self.original_error = original_error
        
        super().__init__(
            f"Failed to publish event '{event_type}': {message}",
            {
                "event_type": event_type,
                "original_error_type": type(original_error).__name__ if original_error else None,
            },
        )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Base
    "AgentOrchestratorError",
    # Configuration
    "ConfigurationError",
    "ChainNotFoundError",
    "StepNotFoundError",
    "AgentNotFoundError",
    "ResourceNotFoundError",
    "CircularDependencyError",
    # Execution
    "ExecutionError",
    "StepExecutionError",
    "StepTimeoutError",
    "ChainExecutionError",
    "MaxRetriesExceededError",
    # Validation
    "ValidationError",
    # Resource
    "ResourceError",
    "ResourceInitializationError",
    "ServiceUnavailableError",
    # Agent
    "AgentError",
    "AgentExecutionError",
    "AgentHandoffError",
    "MaxIterationsExceededError",
    # Event
    "EventError",
    "EventPublishError",
]
