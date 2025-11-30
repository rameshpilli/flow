"""
FlowForge Versioning and Migrations

Provides version tagging for chains/steps and migration utilities.

Features:
- Semantic versioning for chains and steps
- Output schema migrations
- Safe rollback support
- Dry-run/validate-only mode

Usage:
    from flowforge.core.versioning import (
        Version,
        ChainVersion,
        StepVersion,
        MigrationManager,
        validate_chain,
    )

    # Version a chain
    @forge.chain(name="my_chain", version="2.0.0")
    class MyChain:
        steps = [...]

    # Migrate outputs
    manager = MigrationManager()
    manager.register_migration("1.0.0", "2.0.0", migrate_v1_to_v2)
    new_data = manager.migrate(old_data, "1.0.0", "2.0.0")

    # Dry-run validation
    result = validate_chain("my_chain", dry_run=True)
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class Version:
    """
    Semantic version representation.

    Attributes:
        major: Major version (breaking changes)
        minor: Minor version (new features, backwards compatible)
        patch: Patch version (bug fixes)
        prerelease: Pre-release tag (e.g., "alpha", "beta.1")
        build: Build metadata
    """

    major: int = 1
    minor: int = 0
    patch: int = 0
    prerelease: str = ""
    build: str = ""

    @classmethod
    def parse(cls, version_str: str) -> "Version":
        """
        Parse version string.

        Args:
            version_str: Version string (e.g., "1.2.3", "2.0.0-beta.1")

        Returns:
            Version object
        """
        pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?(?:\+([a-zA-Z0-9.]+))?$"
        match = re.match(pattern, version_str.strip())

        if not match:
            raise ValueError(f"Invalid version format: {version_str}")

        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4) or "",
            build=match.group(5) or "",
        )

    def __str__(self) -> str:
        """Convert to string."""
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version

    def __lt__(self, other: "Version") -> bool:
        """Compare versions."""
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

        # Pre-release versions are lower than release versions
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False

        return self.prerelease < other.prerelease

    def __eq__(self, other: object) -> bool:
        """Check equality."""
        if not isinstance(other, Version):
            return False
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __le__(self, other: "Version") -> bool:
        return self < other or self == other

    def __gt__(self, other: "Version") -> bool:
        return not self <= other

    def __ge__(self, other: "Version") -> bool:
        return not self < other

    def is_compatible_with(self, other: "Version") -> bool:
        """
        Check if versions are compatible (same major version).

        According to semver, same major version should be backwards compatible.
        """
        return self.major == other.major

    def is_breaking_change_from(self, other: "Version") -> bool:
        """Check if this version is a breaking change from another."""
        return self.major != other.major

    def bump_major(self) -> "Version":
        """Create new version with bumped major."""
        return Version(major=self.major + 1, minor=0, patch=0)

    def bump_minor(self) -> "Version":
        """Create new version with bumped minor."""
        return Version(major=self.major, minor=self.minor + 1, patch=0)

    def bump_patch(self) -> "Version":
        """Create new version with bumped patch."""
        return Version(major=self.major, minor=self.minor, patch=self.patch + 1)


@dataclass
class ChainVersion:
    """
    Version metadata for a chain.

    Attributes:
        name: Chain name
        version: Version string
        created_at: Creation timestamp
        deprecated: Whether chain is deprecated
        deprecated_message: Deprecation message
        migration_path: Suggested migration chain
        output_schema_version: Version of output schema
    """

    name: str
    version: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    deprecated: bool = False
    deprecated_message: str = ""
    migration_path: str = ""
    output_schema_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "deprecated": self.deprecated,
            "deprecated_message": self.deprecated_message,
            "migration_path": self.migration_path,
            "output_schema_version": self.output_schema_version,
        }


@dataclass
class StepVersion:
    """
    Version metadata for a step.

    Attributes:
        name: Step name
        version: Version string
        input_schema_version: Version of input schema
        output_schema_version: Version of output schema
        deprecated: Whether step is deprecated
    """

    name: str
    version: str
    input_schema_version: str = ""
    output_schema_version: str = ""
    deprecated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "input_schema_version": self.input_schema_version,
            "output_schema_version": self.output_schema_version,
            "deprecated": self.deprecated,
        }


# Type alias for migration functions
MigrationFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class Migration:
    """
    Migration definition.

    Attributes:
        from_version: Source version
        to_version: Target version
        migrate_fn: Migration function
        rollback_fn: Rollback function (optional)
        description: Migration description
        breaking: Whether this is a breaking change
    """

    from_version: str
    to_version: str
    migrate_fn: MigrationFn
    rollback_fn: MigrationFn | None = None
    description: str = ""
    breaking: bool = False


class MigrationManager:
    """
    Manager for output schema migrations.

    Usage:
        manager = MigrationManager()

        # Register migration
        @manager.migration("1.0.0", "2.0.0")
        def migrate_v1_to_v2(data):
            # Transform data from v1 to v2 schema
            return {
                "new_field": data.get("old_field"),
                **data,
            }

        # Migrate data
        new_data = manager.migrate(old_data, "1.0.0", "2.0.0")

        # Rollback
        old_data = manager.rollback(new_data, "2.0.0", "1.0.0")
    """

    def __init__(self):
        self._migrations: dict[tuple[str, str], Migration] = {}
        self._chain_versions: dict[str, list[ChainVersion]] = {}
        self._step_versions: dict[str, list[StepVersion]] = {}

    def register_migration(
        self,
        from_version: str,
        to_version: str,
        migrate_fn: MigrationFn,
        rollback_fn: MigrationFn | None = None,
        description: str = "",
        breaking: bool = False,
    ) -> None:
        """
        Register a migration.

        Args:
            from_version: Source version
            to_version: Target version
            migrate_fn: Function to migrate data
            rollback_fn: Function to rollback (optional)
            description: Migration description
            breaking: Whether this is breaking change
        """
        key = (from_version, to_version)
        self._migrations[key] = Migration(
            from_version=from_version,
            to_version=to_version,
            migrate_fn=migrate_fn,
            rollback_fn=rollback_fn,
            description=description,
            breaking=breaking,
        )
        logger.debug(f"Registered migration: {from_version} -> {to_version}")

    def migration(
        self,
        from_version: str,
        to_version: str,
        description: str = "",
        breaking: bool = False,
    ):
        """
        Decorator to register a migration function.

        Usage:
            @manager.migration("1.0.0", "2.0.0")
            def migrate(data):
                return transformed_data
        """

        def decorator(fn: MigrationFn) -> MigrationFn:
            self.register_migration(
                from_version=from_version,
                to_version=to_version,
                migrate_fn=fn,
                description=description or fn.__doc__ or "",
                breaking=breaking,
            )
            return fn

        return decorator

    def migrate(
        self,
        data: dict[str, Any],
        from_version: str,
        to_version: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Migrate data from one version to another.

        Args:
            data: Data to migrate
            from_version: Current version
            to_version: Target version
            dry_run: If True, validate but don't actually transform

        Returns:
            Migrated data (or original if dry_run)

        Raises:
            ValueError: If no migration path found
        """
        if from_version == to_version:
            return data

        # Find migration path
        path = self._find_migration_path(from_version, to_version)

        if not path:
            raise ValueError(
                f"No migration path from {from_version} to {to_version}"
            )

        if dry_run:
            logger.info(
                f"Dry run: would migrate {from_version} -> {to_version} "
                f"via {len(path)} step(s)"
            )
            return data

        # Apply migrations in sequence
        result = data
        for migration in path:
            logger.info(
                f"Applying migration: {migration.from_version} -> {migration.to_version}"
            )
            result = migration.migrate_fn(result)

        return result

    def rollback(
        self,
        data: dict[str, Any],
        from_version: str,
        to_version: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Rollback data from one version to another.

        Args:
            data: Data to rollback
            from_version: Current version
            to_version: Target version (older)
            dry_run: If True, validate but don't actually transform

        Returns:
            Rolled back data

        Raises:
            ValueError: If rollback not supported
        """
        if from_version == to_version:
            return data

        # Find reverse migration path
        path = self._find_migration_path(to_version, from_version)

        if not path:
            raise ValueError(
                f"No rollback path from {from_version} to {to_version}"
            )

        # Check all migrations have rollback functions
        for migration in path:
            if migration.rollback_fn is None:
                raise ValueError(
                    f"Migration {migration.from_version} -> {migration.to_version} "
                    f"does not support rollback"
                )

        if dry_run:
            logger.info(
                f"Dry run: would rollback {from_version} -> {to_version} "
                f"via {len(path)} step(s)"
            )
            return data

        # Apply rollbacks in reverse order
        result = data
        for migration in reversed(path):
            logger.info(
                f"Applying rollback: {migration.to_version} -> {migration.from_version}"
            )
            result = migration.rollback_fn(result)  # type: ignore

        return result

    def _find_migration_path(
        self, from_version: str, to_version: str
    ) -> list[Migration]:
        """Find migration path using BFS."""
        if from_version == to_version:
            return []

        # Direct migration
        key = (from_version, to_version)
        if key in self._migrations:
            return [self._migrations[key]]

        # BFS for path
        from collections import deque

        visited = {from_version}
        queue = deque([(from_version, [])])

        while queue:
            current, path = queue.popleft()

            # Find all migrations from current version
            for (src, dst), migration in self._migrations.items():
                if src == current and dst not in visited:
                    new_path = path + [migration]

                    if dst == to_version:
                        return new_path

                    visited.add(dst)
                    queue.append((dst, new_path))

        return []

    def list_migrations(self) -> list[Migration]:
        """List all registered migrations."""
        return list(self._migrations.values())

    def has_migration(self, from_version: str, to_version: str) -> bool:
        """Check if migration path exists."""
        return bool(self._find_migration_path(from_version, to_version))

    def register_chain_version(self, version: ChainVersion) -> None:
        """Register a chain version."""
        if version.name not in self._chain_versions:
            self._chain_versions[version.name] = []
        self._chain_versions[version.name].append(version)

    def get_chain_versions(self, chain_name: str) -> list[ChainVersion]:
        """Get all versions of a chain."""
        return self._chain_versions.get(chain_name, [])

    def get_latest_chain_version(self, chain_name: str) -> ChainVersion | None:
        """Get latest version of a chain."""
        versions = self._chain_versions.get(chain_name, [])
        if not versions:
            return None
        return max(versions, key=lambda v: Version.parse(v.version))


# Global migration manager
_migration_manager: MigrationManager | None = None


def get_migration_manager() -> MigrationManager:
    """Get global migration manager."""
    global _migration_manager
    if _migration_manager is None:
        _migration_manager = MigrationManager()
    return _migration_manager


# ═══════════════════════════════════════════════════════════════════════════════
#                         VALIDATION / DRY-RUN
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ValidationResult:
    """
    Result of chain/step validation.

    Attributes:
        valid: Whether validation passed
        errors: List of error messages
        warnings: List of warning messages
        chain_name: Chain being validated
        steps_validated: Number of steps validated
        agents_checked: List of agents checked
        resources_checked: List of resources checked
    """

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    chain_name: str = ""
    steps_validated: int = 0
    agents_checked: list[str] = field(default_factory=list)
    resources_checked: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "chain_name": self.chain_name,
            "steps_validated": self.steps_validated,
            "agents_checked": self.agents_checked,
            "resources_checked": self.resources_checked,
        }


async def validate_chain(
    chain_name: str,
    dry_run: bool = True,
    check_agents: bool = True,
    check_resources: bool = True,
    sample_data: dict[str, Any] | None = None,
) -> ValidationResult:
    """
    Validate a chain definition (dry-run mode).

    Checks:
    - Chain exists and is properly defined
    - All steps exist and have valid dependencies
    - DAG has no cycles
    - Input/output contracts are valid
    - Agents are available (if check_agents=True)
    - Resources are registered (if check_resources=True)

    Args:
        chain_name: Name of chain to validate
        dry_run: If True, don't actually execute anything
        check_agents: Check agent availability
        check_resources: Check resource registration
        sample_data: Optional sample input for contract validation

    Returns:
        ValidationResult with validation status
    """
    from flowforge import get_forge

    result = ValidationResult(chain_name=chain_name)
    forge = get_forge()

    # Check chain exists
    if chain_name not in forge._chain_registry:
        result.valid = False
        result.errors.append(f"Chain '{chain_name}' not found")
        return result

    try:
        # Basic validation via forge.check()
        check_result = forge.check(chain_name)

        if not check_result.get("valid"):
            result.valid = False
            result.errors.extend(check_result.get("errors", []))
            result.warnings.extend(check_result.get("warnings", []))

        # Count steps
        chain_spec = forge._chain_registry.get_spec(chain_name)
        if chain_spec:
            result.steps_validated = len(chain_spec.steps)

        # Check agents if requested
        if check_agents:
            for agent_name in forge._agent_registry.keys():
                result.agents_checked.append(agent_name)
                try:
                    agent = forge.get_agent(agent_name)
                    if hasattr(agent, "health_check"):
                        # Don't actually run health check in dry-run
                        if not dry_run:
                            is_healthy = await agent.health_check()
                            if not is_healthy:
                                result.warnings.append(
                                    f"Agent '{agent_name}' health check failed"
                                )
                except Exception as e:
                    result.warnings.append(
                        f"Could not check agent '{agent_name}': {e}"
                    )

        # Check resources if requested
        if check_resources:
            for resource_name in forge._resource_manager._resources.keys():
                result.resources_checked.append(resource_name)

        # Validate input contract if sample_data provided
        if sample_data and chain_spec:
            from flowforge.core.validation import validate_chain_input

            try:
                # Get input model from chain or first step
                input_model = chain_spec.input_model
                if input_model:
                    validate_chain_input(sample_data, input_model)
            except Exception as e:
                result.warnings.append(f"Input validation warning: {e}")

    except Exception as e:
        result.valid = False
        result.errors.append(f"Validation error: {e}")

    return result


def cmd_validate(args) -> int:
    """CLI command for validation."""
    import asyncio

    chain_name = args.chain_name
    dry_run = not getattr(args, "execute", False)

    print(f"\n{'=' * 60}")
    print(f"  Validating: {chain_name}")
    print(f"  Mode: {'Dry Run' if dry_run else 'Full Validation'}")
    print(f"{'=' * 60}\n")

    result = asyncio.run(validate_chain(
        chain_name,
        dry_run=dry_run,
        check_agents=True,
        check_resources=True,
    ))

    # Print results
    if result.valid:
        print(f"  Status: VALID")
    else:
        print(f"  Status: INVALID")

    print(f"  Steps validated: {result.steps_validated}")
    print(f"  Agents checked: {len(result.agents_checked)}")
    print(f"  Resources checked: {len(result.resources_checked)}")

    if result.errors:
        print(f"\n  Errors:")
        for error in result.errors:
            print(f"    - {error}")

    if result.warnings:
        print(f"\n  Warnings:")
        for warning in result.warnings:
            print(f"    - {warning}")

    print(f"\n{'=' * 60}\n")

    return 0 if result.valid else 1
