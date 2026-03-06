"""Plugin system for gltools.

Provides plugin discovery via ``gltools.plugins`` entry point group
and loading/registration of discovered plugins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from gltools.plugins.protocol import GLToolsPlugin

if TYPE_CHECKING:
    import textual.app
    import typer

logger = logging.getLogger(__name__)

__all__ = ["GLToolsPlugin", "PluginInfo", "discover_plugins", "load_plugins", "register_cli_plugins"]

ENTRY_POINT_GROUP = "gltools.plugins"


@dataclass
class PluginInfo:
    """Metadata about a discovered plugin."""

    entry_point_name: str
    plugin: GLToolsPlugin | None = None
    error: str | None = None
    loaded: bool = False

    @property
    def name(self) -> str:
        if self.plugin is not None:
            return self.plugin.name
        return self.entry_point_name

    @property
    def version(self) -> str:
        if self.plugin is not None:
            return self.plugin.version
        return "unknown"

    @property
    def status(self) -> str:
        if self.loaded and self.plugin is not None:
            return "loaded"
        if self.error:
            return f"error: {self.error}"
        return "not loaded"


# Module-level registry of discovered plugins
_discovered_plugins: list[PluginInfo] = []


def discover_plugins() -> list[PluginInfo]:
    """Discover and load all plugins from the ``gltools.plugins`` entry point group.

    Returns a list of PluginInfo objects describing each discovered plugin,
    including any that failed to load.
    """
    global _discovered_plugins  # noqa: PLW0603
    plugins: list[PluginInfo] = []

    eps = entry_points(group=ENTRY_POINT_GROUP)

    for ep in eps:
        info = PluginInfo(entry_point_name=ep.name)
        try:
            plugin_cls = ep.load()
            plugin_instance = plugin_cls() if callable(plugin_cls) else plugin_cls
            if not isinstance(plugin_instance, GLToolsPlugin):
                info.error = "does not implement GLToolsPlugin protocol"
                logger.warning("Plugin '%s' does not implement GLToolsPlugin protocol", ep.name)
            else:
                info.plugin = plugin_instance
                info.loaded = True
        except Exception as exc:  # noqa: BLE001
            info.error = str(exc)
            logger.warning("Failed to load plugin '%s': %s", ep.name, exc)
        plugins.append(info)

    _discovered_plugins = plugins
    return plugins


def get_discovered_plugins() -> list[PluginInfo]:
    """Return the list of previously discovered plugins (empty if discover_plugins not yet called)."""
    return _discovered_plugins


def load_plugins(app: typer.Typer) -> list[PluginInfo]:
    """Discover plugins and register their CLI commands.

    This is the main entry point for the plugin system during CLI startup.
    """
    plugins = discover_plugins()
    register_cli_plugins(plugins, app)
    return plugins


def register_cli_plugins(plugins: list[PluginInfo], app: typer.Typer) -> None:
    """Register CLI commands from all successfully loaded plugins."""
    for info in plugins:
        if info.loaded and info.plugin is not None:
            try:
                info.plugin.register_commands(app)
            except Exception as exc:  # noqa: BLE001
                info.loaded = False
                info.error = f"registration failed: {exc}"
                logger.warning("Plugin '%s' failed during command registration: %s", info.name, exc)


def register_tui_plugins(plugins: list[PluginInfo], app: textual.app.App) -> None:
    """Register TUI views from all successfully loaded plugins."""
    for info in plugins:
        if info.loaded and info.plugin is not None:
            try:
                info.plugin.register_tui_views(app)
            except Exception as exc:  # noqa: BLE001
                info.error = f"TUI registration failed: {exc}"
                logger.warning("Plugin '%s' failed during TUI registration: %s", info.name, exc)
