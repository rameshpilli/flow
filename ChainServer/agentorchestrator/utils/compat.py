"""
Pydantic v1/v2 Compatibility Utilities
======================================

Provides unified functions that work with both Pydantic v1 and v2,
eliminating the need for repeated version checks throughout the codebase.

This module detects the installed Pydantic version and provides:
- Model validation functions
- Model serialization functions
- Field extraction utilities
- Version detection constants

Usage:
    from agentorchestrator.utils.compat import (
        validate_model,
        model_dump,
        model_json,
        PYDANTIC_V2,
    )
    
    # Works with both Pydantic v1 and v2
    validated = validate_model(MyModel, data_dict)
    as_dict = model_dump(my_instance)
    as_json = model_json(my_instance)

Example:
    >>> from pydantic import BaseModel
    >>> from agentorchestrator.utils.compat import validate_model, model_dump
    >>> 
    >>> class User(BaseModel):
    ...     name: str
    ...     age: int
    >>> 
    >>> # Validate data regardless of Pydantic version
    >>> user = validate_model(User, {"name": "Alice", "age": 30})
    >>> 
    >>> # Dump to dict regardless of Pydantic version
    >>> data = model_dump(user)
    >>> print(data)  # {"name": "Alice", "age": 30}
"""

from typing import Any, TypeVar

from pydantic import BaseModel

# Detect Pydantic version
try:
    from pydantic import __version__ as PYDANTIC_VERSION
    
    _major_version = int(PYDANTIC_VERSION.split(".")[0])
    PYDANTIC_V2 = _major_version >= 2
    PYDANTIC_V1 = _major_version < 2
except (ImportError, AttributeError, ValueError):
    # Fallback - assume v1 if we can't detect
    PYDANTIC_VERSION = "1.0.0"
    PYDANTIC_V2 = False
    PYDANTIC_V1 = True

T = TypeVar("T", bound=BaseModel)


def validate_model(model_class: type[T], data: Any) -> T:
    """
    Validate data against a Pydantic model.
    
    Works with both Pydantic v1 and v2.
    
    Args:
        model_class: The Pydantic model class to validate against.
        data: The data to validate. Can be a dict, another model instance,
              or any type that Pydantic can coerce.
    
    Returns:
        A validated model instance.
    
    Raises:
        pydantic.ValidationError: If validation fails.
    
    Example:
        >>> class User(BaseModel):
        ...     name: str
        >>> user = validate_model(User, {"name": "Alice"})
        >>> user.name
        'Alice'
    """
    # If already an instance of the model, return as-is
    if isinstance(data, model_class):
        return data
    
    # Try Pydantic v2 first (model_validate)
    if hasattr(model_class, "model_validate"):
        if isinstance(data, dict):
            return model_class.model_validate(data)
        return model_class.model_validate(data)
    
    # Fallback to Pydantic v1 (parse_obj)
    if hasattr(model_class, "parse_obj"):
        return model_class.parse_obj(data)
    
    # Last resort - direct instantiation
    if isinstance(data, dict):
        return model_class(**data)
    
    raise TypeError(
        f"Cannot validate {type(data).__name__} against {model_class.__name__}. "
        f"Expected dict or compatible type."
    )


def model_dump(instance: BaseModel, **kwargs) -> dict[str, Any]:
    """
    Convert a Pydantic model to a dictionary.
    
    Works with both Pydantic v1 and v2.
    
    Args:
        instance: The model instance to convert.
        **kwargs: Additional arguments passed to the underlying method.
            Common options:
            - exclude_unset: Exclude fields that weren't explicitly set
            - exclude_none: Exclude fields with None values
            - by_alias: Use field aliases in keys
    
    Returns:
        Dictionary representation of the model.
    
    Example:
        >>> user = User(name="Alice", age=30)
        >>> model_dump(user)
        {'name': 'Alice', 'age': 30}
        >>> model_dump(user, exclude_none=True)
        {'name': 'Alice', 'age': 30}
    """
    # Try Pydantic v2 first (model_dump)
    if hasattr(instance, "model_dump"):
        return instance.model_dump(**kwargs)
    
    # Fallback to Pydantic v1 (dict)
    if hasattr(instance, "dict"):
        return instance.dict(**kwargs)
    
    # Last resort
    raise TypeError(
        f"Cannot dump {type(instance).__name__}. "
        f"Expected Pydantic model instance."
    )


def model_json(instance: BaseModel, **kwargs) -> str:
    """
    Convert a Pydantic model to JSON string.
    
    Works with both Pydantic v1 and v2.
    
    Args:
        instance: The model instance to convert.
        **kwargs: Additional arguments passed to the underlying method.
    
    Returns:
        JSON string representation of the model.
    
    Example:
        >>> user = User(name="Alice", age=30)
        >>> model_json(user)
        '{"name":"Alice","age":30}'
    """
    # Try Pydantic v2 first (model_dump_json)
    if hasattr(instance, "model_dump_json"):
        return instance.model_dump_json(**kwargs)
    
    # Fallback to Pydantic v1 (json)
    if hasattr(instance, "json"):
        return instance.json(**kwargs)
    
    # Last resort - use model_dump + json.dumps
    import json
    return json.dumps(model_dump(instance, **kwargs))


def model_json_schema(model_class: type[BaseModel], **kwargs) -> dict[str, Any]:
    """
    Get the JSON schema for a Pydantic model.
    
    Works with both Pydantic v1 and v2.
    
    Args:
        model_class: The Pydantic model class.
        **kwargs: Additional arguments passed to the underlying method.
    
    Returns:
        JSON schema dictionary.
    
    Example:
        >>> class User(BaseModel):
        ...     name: str
        >>> schema = model_json_schema(User)
        >>> schema['properties']['name']['type']
        'string'
    """
    # Try Pydantic v2 first (model_json_schema)
    if hasattr(model_class, "model_json_schema"):
        return model_class.model_json_schema(**kwargs)
    
    # Fallback to Pydantic v1 (schema)
    if hasattr(model_class, "schema"):
        return model_class.schema(**kwargs)
    
    raise TypeError(
        f"Cannot get JSON schema for {model_class.__name__}. "
        f"Expected Pydantic model class."
    )


def get_model_fields(model_class: type[BaseModel]) -> dict[str, Any]:
    """
    Get the fields defined on a Pydantic model.
    
    Works with both Pydantic v1 and v2.
    
    Args:
        model_class: The Pydantic model class.
    
    Returns:
        Dictionary mapping field names to field info objects.
    
    Example:
        >>> class User(BaseModel):
        ...     name: str
        ...     age: int
        >>> fields = get_model_fields(User)
        >>> list(fields.keys())
        ['name', 'age']
    """
    # Try Pydantic v2 first (model_fields)
    if hasattr(model_class, "model_fields"):
        return model_class.model_fields
    
    # Fallback to Pydantic v1 (__fields__)
    if hasattr(model_class, "__fields__"):
        return model_class.__fields__
    
    raise TypeError(
        f"Cannot get fields for {model_class.__name__}. "
        f"Expected Pydantic model class."
    )


def get_field_default(model_class: type[BaseModel], field_name: str) -> Any:
    """
    Get the default value for a model field.
    
    Works with both Pydantic v1 and v2.
    
    Args:
        model_class: The Pydantic model class.
        field_name: The name of the field.
    
    Returns:
        The default value, or None if no default is set.
    
    Example:
        >>> class User(BaseModel):
        ...     name: str
        ...     age: int = 0
        >>> get_field_default(User, 'age')
        0
    """
    fields = get_model_fields(model_class)
    field_info = fields.get(field_name)
    
    if field_info is None:
        raise KeyError(f"Field '{field_name}' not found in {model_class.__name__}")
    
    # Pydantic v2
    if hasattr(field_info, "default"):
        from pydantic_core import PydanticUndefinedType
        default = field_info.default
        if isinstance(default, PydanticUndefinedType):
            return None
        return default
    
    # Pydantic v1
    if hasattr(field_info, "default"):
        return field_info.default
    
    return None


def is_pydantic_model(cls: type | None) -> bool:
    """
    Check if a class is a Pydantic model.
    
    Args:
        cls: The class to check.
    
    Returns:
        True if the class is a Pydantic BaseModel subclass.
    
    Example:
        >>> from pydantic import BaseModel
        >>> class User(BaseModel):
        ...     name: str
        >>> is_pydantic_model(User)
        True
        >>> is_pydantic_model(str)
        False
    """
    if cls is None:
        return False
    try:
        return issubclass(cls, BaseModel)
    except TypeError:
        return False


def model_copy(instance: T, update: dict[str, Any] | None = None, **kwargs) -> T:
    """
    Create a copy of a Pydantic model, optionally updating fields.
    
    Works with both Pydantic v1 and v2.
    
    Args:
        instance: The model instance to copy.
        update: Dictionary of field values to update in the copy.
        **kwargs: Additional arguments passed to the underlying method.
    
    Returns:
        A new model instance with updated values.
    
    Example:
        >>> user = User(name="Alice", age=30)
        >>> user2 = model_copy(user, update={"age": 31})
        >>> user2.age
        31
    """
    # Try Pydantic v2 first (model_copy)
    if hasattr(instance, "model_copy"):
        return instance.model_copy(update=update, **kwargs)
    
    # Fallback to Pydantic v1 (copy)
    if hasattr(instance, "copy"):
        return instance.copy(update=update, **kwargs)
    
    raise TypeError(
        f"Cannot copy {type(instance).__name__}. "
        f"Expected Pydantic model instance."
    )


__all__ = [
    # Version detection
    "PYDANTIC_VERSION",
    "PYDANTIC_V1",
    "PYDANTIC_V2",
    # Core functions
    "validate_model",
    "model_dump",
    "model_json",
    "model_json_schema",
    "model_copy",
    # Field utilities
    "get_model_fields",
    "get_field_default",
    "is_pydantic_model",
]
