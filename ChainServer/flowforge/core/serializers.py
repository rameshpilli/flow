"""
FlowForge Context Serializers

Provides configurable serialization for ChainContext data, enabling:
- Truncation of large fields for logging/API responses
- Redaction of sensitive fields
- Context reference preservation (don't expand refs)
- Custom field transformations

Usage:
    from flowforge.core.serializers import TruncatingSerializer, RedactingSerializer

    # For API responses (truncate large fields)
    serializer = TruncatingSerializer(max_field_size=1000)
    safe_output = ctx.to_dict(serializer=serializer)

    # For logs (redact + truncate)
    serializer = CompositeSerializer([
        RedactingSerializer(patterns=["password", "token", "secret"]),
        TruncatingSerializer(max_field_size=500),
    ])
    log_safe = ctx.to_dict(serializer=serializer)
"""

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class ContextSerializer(ABC):
    """
    Abstract base class for context serializers.

    Serializers transform context data before output (to_dict, logging, API response).
    """

    @abstractmethod
    def serialize_context_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Serialize context data dictionary.

        Args:
            data: Raw context data (key -> value)

        Returns:
            Transformed data safe for output
        """
        pass

    def serialize_value(self, key: str, value: Any) -> Any:
        """
        Serialize a single value.

        Override for custom per-field logic.

        Args:
            key: Context key
            value: The value to serialize

        Returns:
            Serialized value
        """
        return value


class TruncatingSerializer(ContextSerializer):
    """
    Serializer that truncates large string/list/dict fields.

    Prevents huge payloads from blowing up logs or API responses.
    """

    def __init__(
        self,
        max_field_size: int = 1000,
        max_list_items: int = 10,
        max_dict_keys: int = 20,
        truncation_marker: str = "...[TRUNCATED]",
        preserve_context_refs: bool = True,
    ):
        """
        Initialize truncating serializer.

        Args:
            max_field_size: Max characters for string fields
            max_list_items: Max items to include from lists
            max_dict_keys: Max keys to include from dicts
            truncation_marker: Marker to append when truncating
            preserve_context_refs: Keep ContextRefs as-is (don't expand)
        """
        self.max_field_size = max_field_size
        self.max_list_items = max_list_items
        self.max_dict_keys = max_dict_keys
        self.truncation_marker = truncation_marker
        self.preserve_context_refs = preserve_context_refs

    def serialize_context_data(self, data: dict[str, Any]) -> dict[str, Any]:
        return {k: self.serialize_value(k, v) for k, v in data.items()}

    def serialize_value(self, key: str, value: Any) -> Any:
        # Handle ContextRefs - preserve as lightweight reference
        if self.preserve_context_refs:
            from flowforge.core.context_store import ContextRef, is_context_ref
            if is_context_ref(value):
                if isinstance(value, ContextRef):
                    return value.to_dict()
                return value  # Already a dict with _is_context_ref

        # Handle strings
        if isinstance(value, str):
            if len(value) > self.max_field_size:
                return value[:self.max_field_size] + self.truncation_marker
            return value

        # Handle lists
        if isinstance(value, list):
            truncated = [
                self.serialize_value(f"{key}[{i}]", item)
                for i, item in enumerate(value[:self.max_list_items])
            ]
            if len(value) > self.max_list_items:
                truncated.append(f"{self.truncation_marker} ({len(value) - self.max_list_items} more items)")
            return truncated

        # Handle dicts (recursive)
        if isinstance(value, dict):
            keys = list(value.keys())[:self.max_dict_keys]
            truncated = {
                k: self.serialize_value(f"{key}.{k}", value[k])
                for k in keys
            }
            if len(value) > self.max_dict_keys:
                truncated["_truncated"] = f"{len(value) - self.max_dict_keys} more keys"
            return truncated

        # Handle bytes
        if isinstance(value, bytes):
            if len(value) > self.max_field_size:
                return f"<bytes: {len(value)} bytes, truncated>"
            return f"<bytes: {len(value)} bytes>"

        # Handle Pydantic models
        if hasattr(value, "model_dump"):
            return self.serialize_value(key, value.model_dump())
        if hasattr(value, "dict"):
            return self.serialize_value(key, value.dict())

        # Fallback: try to JSON serialize
        try:
            json.dumps(value, default=str)
            return value
        except (TypeError, ValueError):
            return f"<{type(value).__name__}: {str(value)[:100]}>"


class RedactingSerializer(ContextSerializer):
    """
    Serializer that redacts sensitive fields.

    Matches field names against patterns and replaces values with [REDACTED].
    """

    DEFAULT_PATTERNS = [
        r"password",
        r"token",
        r"secret",
        r"api_key",
        r"apikey",
        r"api-key",
        r"auth",
        r"bearer",
        r"credential",
        r"private",
    ]

    def __init__(
        self,
        patterns: list[str] | None = None,
        redaction_marker: str = "[REDACTED]",
        case_sensitive: bool = False,
    ):
        """
        Initialize redacting serializer.

        Args:
            patterns: Regex patterns to match sensitive field names
            redaction_marker: What to replace sensitive values with
            case_sensitive: Whether pattern matching is case sensitive
        """
        self.patterns = patterns or self.DEFAULT_PATTERNS
        self.redaction_marker = redaction_marker
        self.case_sensitive = case_sensitive

        # Compile patterns
        flags = 0 if case_sensitive else re.IGNORECASE
        self._compiled = [re.compile(p, flags) for p in self.patterns]

    def _is_sensitive(self, key: str) -> bool:
        """Check if a key matches any sensitive pattern."""
        return any(pattern.search(key) for pattern in self._compiled)

    def serialize_context_data(self, data: dict[str, Any]) -> dict[str, Any]:
        return {k: self.serialize_value(k, v) for k, v in data.items()}

    def serialize_value(self, key: str, value: Any) -> Any:
        if self._is_sensitive(key):
            return self.redaction_marker

        # Recurse into dicts
        if isinstance(value, dict):
            return {
                k: self.serialize_value(f"{key}.{k}", v)
                for k, v in value.items()
            }

        # Recurse into lists
        if isinstance(value, list):
            return [
                self.serialize_value(f"{key}[{i}]", item)
                for i, item in enumerate(value)
            ]

        return value


class ContextRefSerializer(ContextSerializer):
    """
    Serializer that converts ContextRefs to their dict representation.

    Handles both ContextRef objects and serialized ContextRef dicts.
    Ensures context refs are properly serialized without expanding to full data.

    This is the preferred serializer for Redis-based context store references.
    """

    def __init__(self, include_metadata: bool = True, include_key_fields: bool = True):
        """
        Initialize context ref serializer.

        Args:
            include_metadata: Include metadata dict in output
            include_key_fields: Include key_fields in output (critical extracted data)
        """
        self.include_metadata = include_metadata
        self.include_key_fields = include_key_fields

    def serialize_context_data(self, data: dict[str, Any]) -> dict[str, Any]:
        return {k: self.serialize_value(k, v) for k, v in data.items()}

    def serialize_value(self, key: str, value: Any) -> Any:
        # Import here to avoid circular imports
        from flowforge.core.context_store import ContextRef

        if isinstance(value, ContextRef):
            ref_dict = value.to_dict()
            if not self.include_metadata:
                ref_dict.pop("metadata", None)
            if not self.include_key_fields:
                ref_dict.pop("key_fields", None)
            return ref_dict

        if isinstance(value, dict):
            if value.get("_is_context_ref"):
                # Already serialized ContextRef
                if not self.include_metadata:
                    value = {k: v for k, v in value.items() if k != "metadata"}
                if not self.include_key_fields:
                    value = {k: v for k, v in value.items() if k != "key_fields"}
                return value
            return {k: self.serialize_value(f"{key}.{k}", v) for k, v in value.items()}

        if isinstance(value, list):
            return [self.serialize_value(f"{key}[{i}]", v) for i, v in enumerate(value)]

        return value


class SummarySerializer(ContextSerializer):
    """
    Serializer that creates a lightweight summary of context data.

    Shows types and sizes instead of full values.
    """

    def __init__(self, show_sizes: bool = True):
        self.show_sizes = show_sizes

    def serialize_context_data(self, data: dict[str, Any]) -> dict[str, Any]:
        return {k: self._summarize(k, v) for k, v in data.items()}

    def _summarize(self, key: str, value: Any) -> dict[str, Any]:
        """Create summary for a value."""
        # Import here to avoid circular imports
        from flowforge.core.context_store import ContextRef, is_context_ref

        summary: dict[str, Any] = {"type": type(value).__name__}

        if isinstance(value, ContextRef):
            summary["type"] = "ContextRef"
            summary["ref_id"] = value.ref_id
            summary["size"] = value.to_dict().get("size_human", "unknown")
            return summary

        if is_context_ref(value) and isinstance(value, dict):
            summary["type"] = "ContextRef"
            summary["ref_id"] = value.get("ref_id", "unknown")
            summary["size"] = value.get("size_human", "unknown")
            return summary

        if isinstance(value, str):
            if self.show_sizes:
                summary["length"] = len(value)
            summary["preview"] = value[:50] + "..." if len(value) > 50 else value
            return summary

        if isinstance(value, list):
            summary["length"] = len(value)
            if value:
                summary["item_type"] = type(value[0]).__name__
            return summary

        if isinstance(value, dict):
            summary["keys"] = len(value)
            summary["key_names"] = list(value.keys())[:10]
            return summary

        if isinstance(value, bytes):
            summary["size"] = len(value)
            return summary

        # For simple types, include value
        if isinstance(value, (int, float, bool, type(None))):
            summary["value"] = value
            return summary

        return summary

    def serialize_value(self, key: str, value: Any) -> Any:
        return self._summarize(key, value)


class CompositeSerializer(ContextSerializer):
    """
    Chains multiple serializers together.

    Applies serializers in order, passing output of each to the next.
    """

    def __init__(self, serializers: list[ContextSerializer]):
        self.serializers = serializers

    def serialize_context_data(self, data: dict[str, Any]) -> dict[str, Any]:
        result = data
        for serializer in self.serializers:
            result = serializer.serialize_context_data(result)
        return result

    def serialize_value(self, key: str, value: Any) -> Any:
        result = value
        for serializer in self.serializers:
            result = serializer.serialize_value(key, result)
        return result


class CustomSerializer(ContextSerializer):
    """
    Serializer with custom per-field handlers.

    Allows fine-grained control over specific fields.
    """

    def __init__(
        self,
        handlers: dict[str, Callable[[Any], Any]] | None = None,
        default_handler: Callable[[str, Any], Any] | None = None,
    ):
        """
        Initialize custom serializer.

        Args:
            handlers: Dict mapping field names/patterns to handler functions
            default_handler: Handler for fields without specific handler
        """
        self.handlers = handlers or {}
        self.default_handler = default_handler or (lambda k, v: v)

    def serialize_context_data(self, data: dict[str, Any]) -> dict[str, Any]:
        return {k: self.serialize_value(k, v) for k, v in data.items()}

    def serialize_value(self, key: str, value: Any) -> Any:
        # Check for exact match first
        if key in self.handlers:
            return self.handlers[key](value)

        # Check for pattern matches
        for pattern, handler in self.handlers.items():
            if "*" in pattern or "?" in pattern:
                import fnmatch
                if fnmatch.fnmatch(key, pattern):
                    return handler(value)

        return self.default_handler(key, value)


# ═══════════════════════════════════════════════════════════════════════════════
#                         FACTORY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def create_safe_serializer(
    max_field_size: int = 1000,
    redact_sensitive: bool = True,
) -> ContextSerializer:
    """
    Create a serializer safe for logging and API responses.

    Combines redaction and truncation.
    """
    serializers = []

    if redact_sensitive:
        serializers.append(RedactingSerializer())

    serializers.append(TruncatingSerializer(max_field_size=max_field_size))

    if len(serializers) == 1:
        return serializers[0]

    return CompositeSerializer(serializers)


def create_summary_serializer() -> ContextSerializer:
    """Create a serializer that only shows summaries (types and sizes)."""
    return SummarySerializer(show_sizes=True)


# Type alias for convenience
ContextSerializer = ContextSerializer
