"""
AgentOrchestrator Test Assertions

Custom assertion helpers for testing AgentOrchestrator chains and steps.
"""

from typing import Any

from agentorchestrator.core.context import ChainContext, ExecutionSummary, StepResult


def assert_step_completed(
    result: ExecutionSummary | dict[str, Any],
    step_name: str,
    message: str | None = None,
) -> None:
    """
    Assert that a specific step completed successfully.

    Args:
        result: Execution result from forge.launch()
        step_name: Name of step to check
        message: Optional custom error message

    Raises:
        AssertionError if step did not complete
    """
    if isinstance(result, ExecutionSummary):
        step_results = {r.step_name: r for r in result.step_results}
    elif isinstance(result, dict):
        # Handle dict result from launch()
        step_results = {}
        if "step_details" in result:
            for detail in result["step_details"]:
                name = detail.get("step_name") or detail.get("name")
                step_results[name] = detail
        elif "steps" in result:
            for step in result["steps"]:
                name = step.get("step_name") or step.get("name")
                step_results[name] = step
    else:
        raise TypeError(f"Unexpected result type: {type(result)}")

    if step_name not in step_results:
        available = list(step_results.keys())
        raise AssertionError(
            message or f"Step '{step_name}' not found in results. Available steps: {available}"
        )

    step = step_results[step_name]

    # Check success
    if isinstance(step, StepResult):
        success = step.success
    elif isinstance(step, dict):
        success = step.get("success", step.get("status") == "completed")
    else:
        success = False

    if not success:
        error = None
        if isinstance(step, StepResult):
            error = step.error
        elif isinstance(step, dict):
            error = step.get("error") or step.get("error_message")

        raise AssertionError(
            message or f"Step '{step_name}' did not complete successfully. Error: {error}"
        )


def assert_step_failed(
    result: ExecutionSummary | dict[str, Any],
    step_name: str,
    error_type: str | None = None,
    message: str | None = None,
) -> None:
    """
    Assert that a specific step failed.

    Args:
        result: Execution result from forge.launch()
        step_name: Name of step to check
        error_type: Optional expected error type name
        message: Optional custom error message

    Raises:
        AssertionError if step did not fail (or wrong error type)
    """
    if isinstance(result, ExecutionSummary):
        step_results = {r.step_name: r for r in result.step_results}
    elif isinstance(result, dict):
        step_results = {}
        if "step_details" in result:
            for detail in result["step_details"]:
                name = detail.get("step_name") or detail.get("name")
                step_results[name] = detail
        elif "steps" in result:
            for step in result["steps"]:
                name = step.get("step_name") or step.get("name")
                step_results[name] = step
    else:
        raise TypeError(f"Unexpected result type: {type(result)}")

    if step_name not in step_results:
        available = list(step_results.keys())
        raise AssertionError(
            message or f"Step '{step_name}' not found in results. Available: {available}"
        )

    step = step_results[step_name]

    # Check failure
    if isinstance(step, StepResult):
        success = step.success
        actual_error_type = step.error_type
    elif isinstance(step, dict):
        success = step.get("success", step.get("status") == "completed")
        actual_error_type = step.get("error_type")
    else:
        success = True
        actual_error_type = None

    if success:
        raise AssertionError(
            message or f"Step '{step_name}' did not fail - it completed successfully"
        )

    if error_type and actual_error_type != error_type:
        raise AssertionError(
            message or f"Step '{step_name}' failed with wrong error type. "
            f"Expected: {error_type}, Got: {actual_error_type}"
        )


def assert_context_has(
    ctx: ChainContext | dict[str, Any],
    key: str,
    value: Any = ...,  # Ellipsis = don't check value
    message: str | None = None,
) -> None:
    """
    Assert that context contains a specific key (and optionally value).

    Args:
        ctx: ChainContext or context dict
        key: Key to check for
        value: Optional expected value (skip check if ... / Ellipsis)
        message: Optional custom error message

    Raises:
        AssertionError if key missing or value doesn't match
    """
    if isinstance(ctx, ChainContext):
        has_key = ctx.has(key)
        actual_value = ctx.get(key) if has_key else None
    elif isinstance(ctx, dict):
        has_key = key in ctx
        actual_value = ctx.get(key)
    else:
        raise TypeError(f"Unexpected context type: {type(ctx)}")

    if not has_key:
        raise AssertionError(
            message or f"Context does not contain key '{key}'"
        )

    if value is not ...:
        if actual_value != value:
            raise AssertionError(
                message or f"Context key '{key}' has wrong value. "
                f"Expected: {value!r}, Got: {actual_value!r}"
            )


def assert_context_missing(
    ctx: ChainContext | dict[str, Any],
    key: str,
    message: str | None = None,
) -> None:
    """
    Assert that context does NOT contain a specific key.

    Args:
        ctx: ChainContext or context dict
        key: Key to check for absence
        message: Optional custom error message

    Raises:
        AssertionError if key exists
    """
    if isinstance(ctx, ChainContext):
        has_key = ctx.has(key)
    elif isinstance(ctx, dict):
        has_key = key in ctx
    else:
        raise TypeError(f"Unexpected context type: {type(ctx)}")

    if has_key:
        raise AssertionError(
            message or f"Context unexpectedly contains key '{key}'"
        )


def assert_chain_valid(
    forge,  # AgentOrchestrator instance
    chain_name: str,
    message: str | None = None,
) -> None:
    """
    Assert that a chain passes validation.

    Args:
        forge: AgentOrchestrator instance
        chain_name: Name of chain to validate
        message: Optional custom error message

    Raises:
        AssertionError if chain is invalid
    """
    result = forge.check(chain_name)

    if not result.get("valid"):
        errors = result.get("errors", [])
        raise AssertionError(
            message or f"Chain '{chain_name}' is invalid. Errors: {errors}"
        )


def assert_chain_invalid(
    forge,  # AgentOrchestrator instance
    chain_name: str,
    expected_error: str | None = None,
    message: str | None = None,
) -> None:
    """
    Assert that a chain FAILS validation.

    Useful for testing that invalid configurations are caught.

    Args:
        forge: AgentOrchestrator instance
        chain_name: Name of chain to validate
        expected_error: Optional substring to find in error messages
        message: Optional custom error message

    Raises:
        AssertionError if chain is valid (or wrong error)
    """
    result = forge.check(chain_name)

    if result.get("valid"):
        raise AssertionError(
            message or f"Chain '{chain_name}' is unexpectedly valid"
        )

    if expected_error:
        errors = result.get("errors", [])
        errors_str = str(errors)
        if expected_error not in errors_str:
            raise AssertionError(
                message or f"Expected error containing '{expected_error}' not found. "
                f"Actual errors: {errors}"
            )


def assert_execution_success(
    result: ExecutionSummary | dict[str, Any],
    message: str | None = None,
) -> None:
    """
    Assert that chain execution was successful.

    Args:
        result: Execution result from forge.launch()
        message: Optional custom error message

    Raises:
        AssertionError if execution failed
    """
    if isinstance(result, ExecutionSummary):
        success = result.success
        error_info = result.error_message if hasattr(result, 'error_message') else None
    elif isinstance(result, dict):
        success = result.get("success", False)
        error_info = result.get("error") or result.get("error_message")
    else:
        raise TypeError(f"Unexpected result type: {type(result)}")

    if not success:
        raise AssertionError(
            message or f"Execution failed. Error: {error_info}"
        )


def assert_execution_failed(
    result: ExecutionSummary | dict[str, Any],
    message: str | None = None,
) -> None:
    """
    Assert that chain execution failed.

    Args:
        result: Execution result from forge.launch()
        message: Optional custom error message

    Raises:
        AssertionError if execution succeeded
    """
    if isinstance(result, ExecutionSummary):
        success = result.success
    elif isinstance(result, dict):
        success = result.get("success", False)
    else:
        raise TypeError(f"Unexpected result type: {type(result)}")

    if success:
        raise AssertionError(
            message or "Execution unexpectedly succeeded"
        )


def assert_partial_success(
    result: ExecutionSummary | dict[str, Any],
    min_completed: int | None = None,
    message: str | None = None,
) -> None:
    """
    Assert partial success (some steps completed, some failed).

    Args:
        result: Execution result from forge.launch()
        min_completed: Minimum number of completed steps
        message: Optional custom error message

    Raises:
        AssertionError if not partial success
    """
    if isinstance(result, ExecutionSummary):
        completed = sum(1 for r in result.step_results if r.success)
        failed = sum(1 for r in result.step_results if not r.success and not r.skipped)
    elif isinstance(result, dict):
        completed = result.get("completed_steps", 0)
        failed = result.get("failed_steps", 0)
    else:
        raise TypeError(f"Unexpected result type: {type(result)}")

    if completed == 0:
        raise AssertionError(
            message or "No steps completed - not partial success"
        )

    if failed == 0:
        raise AssertionError(
            message or "No steps failed - this is full success, not partial"
        )

    if min_completed is not None and completed < min_completed:
        raise AssertionError(
            message or f"Only {completed} steps completed, expected at least {min_completed}"
        )