"""Tests for the GLToolsPlugin protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from gltools.plugins.protocol import GLToolsPlugin

if TYPE_CHECKING:
    import textual.app


class ValidPlugin:
    """A valid plugin implementation for testing."""

    name: str = "test-plugin"
    version: str = "1.0.0"

    def register_commands(self, app: typer.Typer) -> None:
        pass

    def register_tui_views(self, app: textual.app.App) -> None:
        pass


class MissingMethodPlugin:
    """A plugin missing register_tui_views."""

    name: str = "bad-plugin"
    version: str = "0.1.0"

    def register_commands(self, app: typer.Typer) -> None:
        pass


class TestGLToolsPluginProtocol:
    """Verify the GLToolsPlugin protocol type checks."""

    def test_valid_plugin_satisfies_protocol(self) -> None:
        plugin = ValidPlugin()
        assert isinstance(plugin, GLToolsPlugin)

    def test_missing_method_does_not_satisfy_protocol(self) -> None:
        plugin = MissingMethodPlugin()
        assert not isinstance(plugin, GLToolsPlugin)

    def test_protocol_has_name_attribute(self) -> None:
        plugin = ValidPlugin()
        assert plugin.name == "test-plugin"

    def test_protocol_has_version_attribute(self) -> None:
        plugin = ValidPlugin()
        assert plugin.version == "1.0.0"

    def test_register_commands_callable(self) -> None:
        plugin = ValidPlugin()
        app = typer.Typer()
        plugin.register_commands(app)
