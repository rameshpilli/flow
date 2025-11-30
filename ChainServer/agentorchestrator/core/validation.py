"""
AgentOrchestrator Input/Output Contract Validation

Provides Pydantic-based validation for step inputs and outputs,
enabling fail-fast behavior on bad payloads with clear error messages.
"""

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class ContractValidationError(Exception):
    """
    Raised when input/output contract validation fails.

    Contains structured error information for debugging:
    - step_name: Which step failed validation
    - contract_type: "input" or "output"
    - model_name: Name of the Pydantic model
    - errors: List of validation errors from Pydantic
    - raw_value: The value that failed validation (truncated for safety)
    """

    def __init__(
        self,
        step_name: str,
        contract_type: str,
        model_name: str,
        errors: list[dict[str, Any]],
        raw_value: Any = None,
    ):
        self.step_name = step_name
        self.contract_type = contract_type
        self.model_name = model_name
        self.errors = errors
        self.raw_value = raw_value

        # Build human-readable message
        error_details = []
        for err in errors[:5]:  # Limit to first 5 errors
            loc = " -> ".join(str(x) for x in err.get("loc", []))
            msg = err.get("msg", "Unknown error")
            error_details.append(f"  - {loc}: {msg}")

        error_str = "\n".join(error_details)
        if len(errors) > 5:
            error_str += f"\n  ... and {len(errors) - 5} more errors"

        message = (
            f"{contract_type.capitalize()} validation failed for step '{step_name}'.\n"
            f"Expected model: {model_name}\n"
            f"Errors:\n{error_str}"
        )

        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": "ContractValidationError",
            "step_name": self.step_name,
            "contract_type": self.contract_type,
            "model_name": self.model_name,
            "errors": self.errors,
            "message": str(self),
        }


def validate_input(
    step_name: str,
    input_model: type,
    value: Any,
    input_key: str | None = None,
) -> Any:
    """
    Validate input data against a Pydantic model.

    Args:
        step_name: Name of the step (for error messages)
        input_model: Pydantic model class to validate against
        value: The value to validate
        input_key: The context key being validated (for error messages)

    Returns:
        Validated model instance (can be used directly by the step)

    Raises:
        ContractValidationError: If validation fails
    """
    if value is None:
        raise ContractValidationError(
            step_name=step_name,
            contract_type="input",
            model_name=input_model.__name__,
            errors=[{"loc": [input_key or "input"], "msg": "Value is None/missing"}],
            raw_value=value,
        )

    try:
        # If already an instance of the model, return as-is
        if isinstance(value, input_model):
            return value

        # If dict, validate and convert
        if isinstance(value, dict):
            return input_model(**value)

        # Try model_validate for other types (Pydantic v2)
        if hasattr(input_model, "model_validate"):
            return input_model.model_validate(value)

        # Fallback: try direct instantiation
        return input_model(**value) if isinstance(value, dict) else input_model(value)

    except ValidationError as e:
        logger.error(
            f"Input validation failed for step '{step_name}': {e.error_count()} errors"
        )
        raise ContractValidationError(
            step_name=step_name,
            contract_type="input",
            model_name=input_model.__name__,
            errors=e.errors(),
            raw_value=_truncate_value(value),
        ) from e


def validate_output(
    step_name: str,
    output_model: type,
    value: Any,
) -> Any:
    """
    Validate output data against a Pydantic model.

    Args:
        step_name: Name of the step (for error messages)
        output_model: Pydantic model class to validate against
        value: The step output to validate

    Returns:
        Validated model instance

    Raises:
        ContractValidationError: If validation fails
    """
    if value is None:
        # None is valid output in many cases - just return it
        return value

    try:
        # If already an instance of the model, return as-is
        if isinstance(value, output_model):
            return value

        # If dict, validate and convert
        if isinstance(value, dict):
            return output_model(**value)

        # Try model_validate for other types (Pydantic v2)
        if hasattr(output_model, "model_validate"):
            return output_model.model_validate(value)

        # Fallback: try direct instantiation
        return output_model(**value) if isinstance(value, dict) else output_model(value)

    except ValidationError as e:
        logger.error(
            f"Output validation failed for step '{step_name}': {e.error_count()} errors"
        )
        raise ContractValidationError(
            step_name=step_name,
            contract_type="output",
            model_name=output_model.__name__,
            errors=e.errors(),
            raw_value=_truncate_value(value),
        ) from e


def validate_chain_input(
    chain_name: str,
    first_step_name: str,
    input_model: type,
    initial_data: dict[str, Any] | None,
    input_key: str = "request",
) -> dict[str, Any]:
    """
    Validate chain input data before execution starts (fail-fast).

    Called by AgentOrchestrator.launch() to validate input before any steps run.

    Args:
        chain_name: Name of the chain (for error messages)
        first_step_name: Name of the first step that requires this input
        input_model: Pydantic model class to validate against
        initial_data: The initial data dict passed to launch()
        input_key: The key in initial_data to validate

    Returns:
        Updated initial_data with validated model instance

    Raises:
        ContractValidationError: If validation fails
    """
    if initial_data is None:
        initial_data = {}

    # Get the value to validate
    value = initial_data.get(input_key)

    if value is None:
        # Check if the entire initial_data might be the input
        # (common pattern: launch("chain", {"company_name": "..."}) instead of
        #  launch("chain", {"request": {"company_name": "..."}}))
        if input_key == "request" and initial_data:
            # Try validating the entire initial_data as the request
            try:
                validated = validate_input(
                    step_name=first_step_name,
                    input_model=input_model,
                    value=initial_data,
                    input_key=input_key,
                )
                # Wrap in the expected structure
                return {input_key: validated}
            except ContractValidationError:
                # Fall through to regular validation error
                pass

        raise ContractValidationError(
            step_name=first_step_name,
            contract_type="input",
            model_name=input_model.__name__,
            errors=[{
                "loc": [input_key],
                "msg": f"Required key '{input_key}' not found in initial_data",
            }],
            raw_value=initial_data,
        )

    # Validate the value
    validated = validate_input(
        step_name=first_step_name,
        input_model=input_model,
        value=value,
        input_key=input_key,
    )

    # Return updated data with validated model
    result = initial_data.copy()
    result[input_key] = validated
    return result


def _truncate_value(value: Any, max_length: int = 200) -> str:
    """Truncate a value for safe logging/error messages."""
    try:
        value_str = str(value)
        if len(value_str) > max_length:
            return value_str[:max_length] + "..."
        return value_str
    except Exception:
        return "<unable to convert to string>"


def is_pydantic_model(cls: type | None) -> bool:
    """Check if a class is a Pydantic model."""
    if cls is None:
        return False
    try:
        return issubclass(cls, BaseModel)
    except TypeError:
        return False
