"""
Plugin Discovery and Loading

Discovers and loads FlowForge plugins via Python entry points.

Plugins are registered in pyproject.toml:

    [project.entry-points."flowforge.agents"]
    my_agent = "my_package.agents:MyAgent"

Usage:
    from flowforge.plugins import discover_plugins, PluginManager

    # Discover all plugins
    plugins = discover_plugins()
    for name, info in plugins.items():
        print(f"{name}: {info.module_path}")

    # Use plugin manager
    pm = PluginManager()
    pm.load_all()
    agent = pm.get("my_agent")
"""

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Entry point group names
AGENT_ENTRY_POINT = "flowforge.agents"
CONNECTOR_ENTRY_POINT = "flowforge.connectors"
MIDDLEWARE_ENTRY_POINT = "flowforge.middleware"


@dataclass
class PluginInfo:
    """
    Information about a discovered plugin.

    Attributes:
        name: Plugin name (entry point name)
        module_path: Full module path (e.g., "my_package.agents:MyAgent")
        group: Entry point group (e.g., "flowforge.agents")
        version: Plugin version (if available)
        description: Plugin description
        capabilities: List of capabilities (for agents)
        loaded: Whether plugin is loaded
        instance: Loaded plugin instance (if loaded)
        error: Error message if loading failed
    """

    name: str
    module_path: str
    group: str
    version: str = ""
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    loaded: bool = False
    instance: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "module_path": self.module_path,
            "group": self.group,
            "version": self.version,
            "description": self.description,
            "capabilities": self.capabilities,
            "loaded": self.loaded,
            "error": self.error,
        }


def discover_plugins(
    groups: list[str] | None = None,
) -> dict[str, PluginInfo]:
    """
    Discover all FlowForge plugins via entry points.

    Args:
        groups: Entry point groups to scan (default: all FlowForge groups)

    Returns:
        Dict mapping plugin names to PluginInfo
    """
    if groups is None:
        groups = [AGENT_ENTRY_POINT, CONNECTOR_ENTRY_POINT, MIDDLEWARE_ENTRY_POINT]

    plugins: dict[str, PluginInfo] = {}

    # Python 3.10+ uses importlib.metadata
    try:
        from importlib.metadata import entry_points
    except ImportError:
        from importlib_metadata import entry_points  # type: ignore

    for group in groups:
        try:
            # Python 3.10+ returns SelectableGroups
            eps = entry_points(group=group)
            if hasattr(eps, "select"):
                eps = eps.select(group=group)
        except TypeError:
            # Older Python versions
            all_eps = entry_points()
            eps = all_eps.get(group, [])

        for ep in eps:
            try:
                # Get module path
                module_path = f"{ep.value}"

                # Extract metadata if available
                version = ""
                description = ""
                capabilities = []

                # Try to get version from distribution
                try:
                    from importlib.metadata import metadata
                    dist_name = ep.value.split(":")[0].split(".")[0]
                    meta = metadata(dist_name)
                    version = meta.get("Version", "")
                    description = meta.get("Summary", "")
                except Exception:
                    pass

                plugins[ep.name] = PluginInfo(
                    name=ep.name,
                    module_path=module_path,
                    group=group,
                    version=version,
                    description=description,
                    capabilities=capabilities,
                )

            except Exception as e:
                logger.warning(f"Failed to discover plugin {ep.name}: {e}")
                plugins[ep.name] = PluginInfo(
                    name=ep.name,
                    module_path=str(ep.value),
                    group=group,
                    error=str(e),
                )

    return plugins


def load_plugin(
    name: str,
    group: str = AGENT_ENTRY_POINT,
    config: dict[str, Any] | None = None,
) -> Any:
    """
    Load a specific plugin by name.

    Args:
        name: Plugin name (entry point name)
        group: Entry point group
        config: Configuration to pass to plugin

    Returns:
        Loaded plugin instance

    Raises:
        ValueError: If plugin not found
        ImportError: If plugin cannot be loaded
    """
    # Discover plugins
    plugins = discover_plugins(groups=[group])

    if name not in plugins:
        available = list(plugins.keys())
        raise ValueError(
            f"Plugin '{name}' not found in group '{group}'. "
            f"Available: {available}"
        )

    info = plugins[name]

    if info.error:
        raise ImportError(f"Plugin '{name}' has error: {info.error}")

    # Load the plugin class
    try:
        module_path, class_name = info.module_path.rsplit(":", 1)
        module = importlib.import_module(module_path)
        plugin_class = getattr(module, class_name)

        # Instantiate with config
        if config:
            instance = plugin_class(config=config)
        else:
            instance = plugin_class()

        return instance

    except Exception as e:
        raise ImportError(f"Failed to load plugin '{name}': {e}") from e


def load_plugin_class(
    name: str,
    group: str = AGENT_ENTRY_POINT,
) -> type[Any]:
    """
    Load a plugin class without instantiating.

    Args:
        name: Plugin name
        group: Entry point group

    Returns:
        Plugin class
    """
    plugins = discover_plugins(groups=[group])

    if name not in plugins:
        raise ValueError(f"Plugin '{name}' not found")

    info = plugins[name]
    module_path, class_name = info.module_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class PluginManager:
    """
    Manager for FlowForge plugins.

    Provides:
    - Lazy loading
    - Instance caching
    - Lifecycle management
    - Capability filtering

    Usage:
        pm = PluginManager()
        pm.load_all()

        # Get agent by name
        agent = pm.get("news_agent")

        # Get agents by capability
        agents = pm.get_by_capability("search")

        # Cleanup
        await pm.cleanup()
    """

    def __init__(
        self,
        groups: list[str] | None = None,
        auto_load: bool = False,
    ):
        """
        Initialize plugin manager.

        Args:
            groups: Entry point groups to manage
            auto_load: Automatically load all plugins on init
        """
        self.groups = groups or [AGENT_ENTRY_POINT]
        self._plugins: dict[str, PluginInfo] = {}
        self._instances: dict[str, Any] = {}
        self._initialized = False

        if auto_load:
            self.load_all()

    def discover(self) -> dict[str, PluginInfo]:
        """Discover available plugins."""
        self._plugins = discover_plugins(groups=self.groups)
        return self._plugins

    def load_all(self, config: dict[str, dict[str, Any]] | None = None) -> None:
        """
        Load all discovered plugins.

        Args:
            config: Dict mapping plugin names to their configs
        """
        if not self._plugins:
            self.discover()

        config = config or {}

        for name, info in self._plugins.items():
            if info.error:
                logger.warning(f"Skipping plugin {name} due to error: {info.error}")
                continue

            try:
                plugin_config = config.get(name, {})
                instance = load_plugin(name, info.group, plugin_config)
                self._instances[name] = instance
                info.loaded = True
                info.instance = instance

                # Extract capabilities if available
                if hasattr(instance, "CAPABILITIES"):
                    caps = instance.CAPABILITIES
                    if hasattr(caps, "capabilities"):
                        info.capabilities = [c.name for c in caps.capabilities]
                    elif isinstance(caps, dict):
                        info.capabilities = list(caps.keys())

                logger.debug(f"Loaded plugin: {name}")

            except Exception as e:
                logger.error(f"Failed to load plugin {name}: {e}")
                info.error = str(e)

        self._initialized = True

    def get(self, name: str, config: dict[str, Any] | None = None) -> Any:
        """
        Get a plugin instance by name.

        Args:
            name: Plugin name
            config: Config to pass if loading new instance

        Returns:
            Plugin instance
        """
        # Return cached instance
        if name in self._instances:
            return self._instances[name]

        # Lazy load
        if not self._plugins:
            self.discover()

        if name not in self._plugins:
            raise ValueError(f"Plugin '{name}' not found")

        instance = load_plugin(name, self._plugins[name].group, config)
        self._instances[name] = instance
        self._plugins[name].loaded = True
        self._plugins[name].instance = instance

        return instance

    def get_by_capability(self, capability: str) -> list[Any]:
        """
        Get all plugins that have a specific capability.

        Args:
            capability: Capability name (e.g., "search")

        Returns:
            List of plugin instances with that capability
        """
        matching = []

        for name, info in self._plugins.items():
            if capability in info.capabilities:
                if info.loaded and info.instance:
                    matching.append(info.instance)
                else:
                    try:
                        instance = self.get(name)
                        matching.append(instance)
                    except Exception as e:
                        logger.warning(f"Could not load {name}: {e}")

        return matching

    def list_plugins(self) -> list[PluginInfo]:
        """List all discovered plugins."""
        if not self._plugins:
            self.discover()
        return list(self._plugins.values())

    def list_capabilities(self) -> dict[str, list[str]]:
        """
        List all capabilities and which plugins provide them.

        Returns:
            Dict mapping capability names to list of plugin names
        """
        caps: dict[str, list[str]] = {}

        for name, info in self._plugins.items():
            for cap in info.capabilities:
                if cap not in caps:
                    caps[cap] = []
                caps[cap].append(name)

        return caps

    async def initialize_all(self) -> None:
        """Initialize all loaded plugins (call their initialize method)."""
        for name, instance in self._instances.items():
            if hasattr(instance, "initialize"):
                try:
                    await instance.initialize()
                    logger.debug(f"Initialized plugin: {name}")
                except Exception as e:
                    logger.error(f"Failed to initialize {name}: {e}")

    async def cleanup(self) -> None:
        """Cleanup all loaded plugins."""
        for name, instance in self._instances.items():
            if hasattr(instance, "cleanup"):
                try:
                    await instance.cleanup()
                    logger.debug(f"Cleaned up plugin: {name}")
                except Exception as e:
                    logger.error(f"Failed to cleanup {name}: {e}")

        self._instances.clear()

    def __contains__(self, name: str) -> bool:
        """Check if plugin is registered."""
        return name in self._plugins

    def __getitem__(self, name: str) -> Any:
        """Get plugin by name."""
        return self.get(name)
