"""
AgentOrchestrator Resource Management

Provides dependency injection and lifecycle management for resources.
Resources can be database connections, HTTP clients, configuration objects, etc.

Features:
- Lazy initialization of resources
- Automatic cleanup on shutdown
- Dependency injection into steps
- Context-scoped resources
- Async and sync resource support
"""

import asyncio
import atexit
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ResourceScope(Enum):
    """Lifecycle scope for resources"""
    SINGLETON = "singleton"    # One instance for entire app lifetime
    CHAIN = "chain"            # New instance per chain execution
    STEP = "step"              # New instance per step execution


class ResourceState(Enum):
    """State of a resource"""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    CLOSING = "closing"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class ResourceSpec:
    """Specification for a registered resource"""
    name: str
    factory: Callable[[], Any]  # Factory function to create resource
    scope: ResourceScope = ResourceScope.SINGLETON
    cleanup: Callable[[Any], Any] | None = None  # Cleanup function
    is_async_factory: bool = False
    is_async_cleanup: bool = False
    dependencies: list[str] = field(default_factory=list)  # Other resources this depends on
    state: ResourceState = ResourceState.UNINITIALIZED
    instance: Any | None = None
    error: Exception | None = None


class Resource(ABC):
    """
    Base class for resources that need lifecycle management.

    Implement this for resources that need explicit initialization and cleanup.

    Usage:
        class DatabaseResource(Resource):
            async def initialize(self) -> None:
                self.conn = await create_connection()

            async def cleanup(self) -> None:
                await self.conn.close()

            def get_connection(self):
                return self.conn

        # Register with AgentOrchestrator
        forge.resource("db", DatabaseResource())
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the resource (called once)"""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup the resource (called on shutdown)"""
        pass

    def __enter__(self) -> "Resource":
        asyncio.get_event_loop().run_until_complete(self.initialize())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        asyncio.get_event_loop().run_until_complete(self.cleanup())

    async def __aenter__(self) -> "Resource":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()


class ResourceManager:
    """
    Manages resource lifecycle and dependency injection.

    Features:
    - Lazy initialization
    - Automatic cleanup on shutdown
    - Dependency resolution between resources
    - Scoped resources (singleton, chain, step)

    Usage:
        manager = ResourceManager()

        # Register a simple resource
        manager.register("config", lambda: load_config())

        # Register with cleanup
        manager.register(
            "db",
            factory=lambda: create_db_pool(),
            cleanup=lambda pool: pool.close(),
        )

        # Register async resource
        manager.register(
            "cache",
            factory=create_redis_client,
            cleanup=lambda c: c.close(),
            is_async_factory=True,
        )

        # Get resource (lazy init)
        config = await manager.get("config")

        # Cleanup all
        await manager.cleanup_all()
    """

    def __init__(self):
        self._resources: dict[str, ResourceSpec] = {}
        self._lock = asyncio.Lock()
        self._sync_lock = __import__("threading").Lock()
        self._atexit_registered = False

    def register(
        self,
        name: str,
        factory: Callable[[], T] | T,
        scope: ResourceScope = ResourceScope.SINGLETON,
        cleanup: Callable[[T], Any] | None = None,
        is_async_factory: bool = False,
        is_async_cleanup: bool = False,
        dependencies: list[str] | None = None,
    ) -> "ResourceManager":
        """
        Register a resource.

        Args:
            name: Resource identifier
            factory: Factory function or instance. If not callable, treated as instance.
            scope: Lifecycle scope (singleton, chain, step)
            cleanup: Optional cleanup function
            is_async_factory: True if factory is async
            is_async_cleanup: True if cleanup is async
            dependencies: Other resources this depends on

        Returns:
            Self for chaining
        """
        # If factory is not callable, wrap it
        if not callable(factory):
            instance = factory

            def make_factory(inst):
                return lambda: inst

            factory = make_factory(instance)
            is_async_factory = False

        # Auto-detect async
        if is_async_factory is False and asyncio.iscoroutinefunction(factory):
            is_async_factory = True
        if cleanup and is_async_cleanup is False and asyncio.iscoroutinefunction(cleanup):
            is_async_cleanup = True

        spec = ResourceSpec(
            name=name,
            factory=factory,
            scope=scope,
            cleanup=cleanup,
            is_async_factory=is_async_factory,
            is_async_cleanup=is_async_cleanup,
            dependencies=dependencies or [],
        )

        self._resources[name] = spec
        self._ensure_atexit()

        logger.debug(f"Resource registered: {name} (scope={scope.value})")
        return self

    def _ensure_atexit(self) -> None:
        """Register atexit handler for cleanup"""
        if not self._atexit_registered:
            atexit.register(self._atexit_cleanup)
            self._atexit_registered = True

    def _atexit_cleanup(self) -> None:
        """Cleanup handler for process exit"""
        try:
            # Try to run async cleanup
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(self.cleanup_all())
        except Exception as e:
            logger.debug(f"Error during atexit cleanup: {e}")

    async def get(self, name: str) -> Any:
        """
        Get a resource by name (async, lazy initialization).

        Args:
            name: Resource identifier

        Returns:
            Resource instance

        Raises:
            KeyError: If resource not registered
            Exception: If resource initialization fails
        """
        if name not in self._resources:
            raise KeyError(f"Resource not registered: {name}")

        spec = self._resources[name]

        # Return existing instance for singletons
        if spec.scope == ResourceScope.SINGLETON and spec.instance is not None:
            return spec.instance

        async with self._lock:
            # Double-check after acquiring lock
            if spec.scope == ResourceScope.SINGLETON and spec.instance is not None:
                return spec.instance

            # Initialize dependencies first
            for dep in spec.dependencies:
                await self.get(dep)

            # Initialize this resource
            return await self._initialize_resource(spec)

    def get_sync(self, name: str) -> Any:
        """
        Get a resource by name (sync version).

        Note: For async resources, this will run in a new event loop.
        """
        if name not in self._resources:
            raise KeyError(f"Resource not registered: {name}")

        spec = self._resources[name]

        # Return existing instance for singletons
        if spec.scope == ResourceScope.SINGLETON and spec.instance is not None:
            return spec.instance

        with self._sync_lock:
            if spec.scope == ResourceScope.SINGLETON and spec.instance is not None:
                return spec.instance

            # Initialize dependencies first
            for dep in spec.dependencies:
                self.get_sync(dep)

            # Initialize this resource
            try:
                loop = asyncio.get_running_loop()
                # If we're in an async context, schedule it
                future = asyncio.run_coroutine_threadsafe(
                    self._initialize_resource(spec), loop
                )
                return future.result()
            except RuntimeError:
                # No running loop - run in new loop
                return asyncio.run(self._initialize_resource(spec))

    async def _initialize_resource(self, spec: ResourceSpec) -> Any:
        """Initialize a single resource"""
        spec.state = ResourceState.INITIALIZING

        try:
            if spec.is_async_factory:
                instance = await spec.factory()
            else:
                instance = spec.factory()

            # If it's a Resource subclass, initialize it
            if isinstance(instance, Resource):
                await instance.initialize()

            spec.instance = instance
            spec.state = ResourceState.READY
            logger.debug(f"Resource initialized: {spec.name}")
            return instance

        except Exception as e:
            spec.state = ResourceState.ERROR
            spec.error = e
            logger.error(f"Failed to initialize resource {spec.name}: {e}")
            raise

    async def cleanup(self, name: str) -> None:
        """Cleanup a specific resource"""
        if name not in self._resources:
            return

        spec = self._resources[name]
        await self._cleanup_resource(spec)

    async def cleanup_all(self) -> None:
        """Cleanup all resources in reverse registration order"""
        # Cleanup in reverse order (last registered first)
        for name in reversed(list(self._resources.keys())):
            await self._cleanup_resource(self._resources[name])

        logger.info("All resources cleaned up")

    async def _cleanup_resource(self, spec: ResourceSpec) -> None:
        """Cleanup a single resource"""
        if spec.instance is None or spec.state == ResourceState.CLOSED:
            return

        spec.state = ResourceState.CLOSING

        try:
            # If it's a Resource subclass, use its cleanup
            if isinstance(spec.instance, Resource):
                await spec.instance.cleanup()
            elif spec.cleanup:
                if spec.is_async_cleanup:
                    await spec.cleanup(spec.instance)
                else:
                    spec.cleanup(spec.instance)

            spec.state = ResourceState.CLOSED
            spec.instance = None
            logger.debug(f"Resource cleaned up: {spec.name}")

        except Exception as e:
            spec.state = ResourceState.ERROR
            logger.error(f"Error cleaning up resource {spec.name}: {e}")

    def has(self, name: str) -> bool:
        """Check if a resource is registered"""
        return name in self._resources

    def is_ready(self, name: str) -> bool:
        """Check if a resource is initialized and ready"""
        return (
            name in self._resources
            and self._resources[name].state == ResourceState.READY
        )

    def list_resources(self) -> list[str]:
        """List all registered resource names"""
        return list(self._resources.keys())

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all resources"""
        return {
            name: {
                "state": spec.state.value,
                "scope": spec.scope.value,
                "has_instance": spec.instance is not None,
                "dependencies": spec.dependencies,
            }
            for name, spec in self._resources.items()
        }

    def clear(self) -> None:
        """Clear all resources (for testing)"""
        self._resources.clear()


# Global resource manager instance
_global_resource_manager: ResourceManager | None = None


def get_resource_manager() -> ResourceManager:
    """Get the global resource manager"""
    global _global_resource_manager
    if _global_resource_manager is None:
        _global_resource_manager = ResourceManager()
    return _global_resource_manager


def reset_resource_manager() -> None:
    """Reset the global resource manager (for testing)"""
    global _global_resource_manager
    if _global_resource_manager:
        try:
            asyncio.run(_global_resource_manager.cleanup_all())
        except Exception:
            pass
    _global_resource_manager = ResourceManager()


# Convenience decorators
def resource(
    name: str,
    scope: ResourceScope = ResourceScope.SINGLETON,
    cleanup: Callable[[Any], Any] | None = None,
    dependencies: list[str] | None = None,
) -> Callable[[Callable[[], T]], Callable[[], T]]:
    """
    Decorator to register a factory function as a resource.

    Usage:
        @resource("db", cleanup=lambda c: c.close())
        def create_db_connection():
            return DatabaseConnection()

        @resource("cache", dependencies=["config"])
        async def create_cache():
            config = await get_resource_manager().get("config")
            return Redis(config.redis_url)
    """
    def decorator(factory: Callable[[], T]) -> Callable[[], T]:
        get_resource_manager().register(
            name=name,
            factory=factory,
            scope=scope,
            cleanup=cleanup,
            dependencies=dependencies,
        )
        return factory
    return decorator