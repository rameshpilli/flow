"""
Agent Capability Schema

Defines the capability schema for FlowForge agents, enabling:
- Plugin discovery by capability
- Self-documenting agents
- Validation of agent parameters
- Auto-generation of API docs

Usage:
    from flowforge.plugins.capability import AgentCapability, CapabilitySchema

    class MyAgent(BaseAgent):
        CAPABILITIES = CapabilitySchema(
            name="my_agent",
            version="1.0.0",
            capabilities=[
                AgentCapability(
                    name="search",
                    description="Search for items",
                    parameters=[
                        CapabilityParameter(name="query", type="string", required=True),
                        CapabilityParameter(name="limit", type="integer", default=10),
                    ],
                ),
            ],
        )
"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class CapabilityParameter:
    """
    Parameter definition for an agent capability.

    Attributes:
        name: Parameter name
        type: JSON Schema type (string, integer, number, boolean, array, object)
        required: Whether parameter is required
        default: Default value if not provided
        description: Parameter description
        enum: List of allowed values (for string type)
        minimum: Minimum value (for numeric types)
        maximum: Maximum value (for numeric types)
        items: Item schema (for array type)
    """

    name: str
    type: Literal["string", "integer", "number", "boolean", "array", "object"] = "string"
    required: bool = False
    default: Any = None
    description: str = ""
    enum: list[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    items: dict[str, Any] | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format."""
        schema: dict[str, Any] = {"type": self.type}

        if self.description:
            schema["description"] = self.description
        if self.default is not None:
            schema["default"] = self.default
        if self.enum:
            schema["enum"] = self.enum
        if self.minimum is not None:
            schema["minimum"] = self.minimum
        if self.maximum is not None:
            schema["maximum"] = self.maximum
        if self.items:
            schema["items"] = self.items

        return schema

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "description": self.description,
            "enum": self.enum,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "items": self.items,
        }


@dataclass
class AgentCapability:
    """
    Agent capability definition.

    Attributes:
        name: Capability name (e.g., "search", "fetch", "analyze")
        description: Human-readable description
        parameters: List of parameters for this capability
        returns: Description of return value
        examples: Usage examples
    """

    name: str
    description: str = ""
    parameters: list[CapabilityParameter] = field(default_factory=list)
    returns: str = ""
    examples: list[dict[str, Any]] = field(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format for the capability."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "returns": self.returns,
            "examples": self.examples,
        }

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """
        Validate parameters against schema.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check required parameters
        for param in self.parameters:
            if param.required and param.name not in params:
                errors.append(f"Missing required parameter: {param.name}")

        # Type validation
        for name, value in params.items():
            param = next((p for p in self.parameters if p.name == name), None)
            if param is None:
                errors.append(f"Unknown parameter: {name}")
                continue

            # Basic type checking
            type_map = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "array": list,
                "object": dict,
            }

            expected_type = type_map.get(param.type)
            if expected_type and not isinstance(value, expected_type):
                errors.append(
                    f"Parameter '{name}' expected {param.type}, got {type(value).__name__}"
                )

            # Enum validation
            if param.enum and value not in param.enum:
                errors.append(
                    f"Parameter '{name}' must be one of: {param.enum}"
                )

            # Range validation
            if param.minimum is not None and isinstance(value, (int, float)):
                if value < param.minimum:
                    errors.append(
                        f"Parameter '{name}' must be >= {param.minimum}"
                    )
            if param.maximum is not None and isinstance(value, (int, float)):
                if value > param.maximum:
                    errors.append(
                        f"Parameter '{name}' must be <= {param.maximum}"
                    )

        return errors


@dataclass
class CapabilitySchema:
    """
    Complete capability schema for an agent.

    Attributes:
        name: Agent name
        version: Agent version (semver)
        description: Agent description
        capabilities: List of capabilities
        tags: Categorization tags
        author: Author name/email
        license: License identifier
        homepage: Project homepage URL
    """

    name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: list[AgentCapability] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    author: str = ""
    license: str = ""
    homepage: str = ""

    def get_capability(self, name: str) -> AgentCapability | None:
        """Get capability by name."""
        return next((c for c in self.capabilities if c.name == name), None)

    def has_capability(self, name: str) -> bool:
        """Check if agent has capability."""
        return any(c.name == name for c in self.capabilities)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (for serialization/API docs)."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "tags": self.tags,
            "author": self.author,
            "license": self.license,
            "homepage": self.homepage,
        }

    def to_openapi(self) -> dict[str, Any]:
        """Convert to OpenAPI schema format."""
        schemas = {}
        for cap in self.capabilities:
            schemas[f"{self.name}_{cap.name}_params"] = cap.to_json_schema()

        return {
            "info": {
                "title": self.name,
                "version": self.version,
                "description": self.description,
            },
            "components": {
                "schemas": schemas,
            },
        }


def validate_capability_schema(schema: dict[str, Any] | CapabilitySchema) -> list[str]:
    """
    Validate a capability schema.

    Args:
        schema: Schema dict or CapabilitySchema object

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if isinstance(schema, CapabilitySchema):
        schema = schema.to_dict()

    # Required fields
    if not schema.get("name"):
        errors.append("Schema must have a 'name' field")
    if not schema.get("version"):
        errors.append("Schema must have a 'version' field")

    # Version format (semver-ish)
    version = schema.get("version", "")
    if version and not _is_valid_version(version):
        errors.append(f"Invalid version format: {version} (expected: X.Y.Z)")

    # Capabilities
    capabilities = schema.get("capabilities", [])
    if not isinstance(capabilities, list):
        errors.append("'capabilities' must be a list")
    else:
        for i, cap in enumerate(capabilities):
            if not cap.get("name"):
                errors.append(f"Capability {i} must have a 'name' field")

    return errors


def _is_valid_version(version: str) -> bool:
    """Check if version is valid semver-ish format."""
    import re
    pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$"
    return bool(re.match(pattern, version))


# ═══════════════════════════════════════════════════════════════════════════════
#                         CAPABILITY DECORATORS
# ═══════════════════════════════════════════════════════════════════════════════


def capability(
    name: str,
    description: str = "",
    parameters: list[CapabilityParameter] | None = None,
    returns: str = "",
):
    """
    Decorator to add capability to an agent class.

    Usage:
        @capability(
            name="search",
            description="Search for items",
            parameters=[
                CapabilityParameter(name="query", type="string", required=True),
            ],
        )
        class MyAgent(BaseAgent):
            ...
    """
    def decorator(cls):
        if not hasattr(cls, "_capabilities"):
            cls._capabilities = []

        cls._capabilities.append(AgentCapability(
            name=name,
            description=description,
            parameters=parameters or [],
            returns=returns,
        ))

        return cls

    return decorator
