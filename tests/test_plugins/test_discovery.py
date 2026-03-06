"""Tests for plugin discovery and loading."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import typer

from gltools.plugins import (
    PluginInfo,
    discover_plugins,
    register_cli_plugins,
)

if TYPE_CHECKING:
    import textual.app


class FakePlugin:
    """A fake plugin for testing discovery."""

    name: str = "fake-plugin"
    version: str = "2.0.0"

    def register_commands(self, app: typer.Typer) -> None:
        @app.command(name="fake-cmd")
        def fake_cmd() -> None:
            """Fake command from plugin."""

    def register_tui_views(self, app: textual.app.App) -> None:
        pass


class BrokenPlugin:
    """A plugin that raises on register_commands."""

    name: str = "broken-plugin"
    version: str = "0.0.1"

    def register_commands(self, app: typer.Typer) -> None:
        msg = "Registration failed!"
        raise RuntimeError(msg)

    def register_tui_views(self, app: textual.app.App) -> None:
        pass


def _make_entry_point(name: str, load_result: object | None = None, load_error: Exception | None = None) -> MagicMock:
    """Create a mock entry point."""
    ep = MagicMock()
    ep.name = name
    if load_error:
        ep.load.side_effect = load_error
    else:
        ep.load.return_value = load_result
    return ep


class TestDiscoverPlugins:
    """Tests for the discover_plugins function."""

    @patch("gltools.plugins.entry_points")
    def test_no_plugins_returns_empty_list(self, mock_eps: MagicMock) -> None:
        mock_eps.return_value = []
        plugins = discover_plugins()
        assert plugins == []

    @patch("gltools.plugins.entry_points")
    def test_discovers_valid_plugin(self, mock_eps: MagicMock) -> None:
        mock_eps.return_value = [_make_entry_point("fake", FakePlugin)]
        plugins = discover_plugins()
        assert len(plugins) == 1
        assert plugins[0].loaded is True
        assert plugins[0].name == "fake-plugin"
        assert plugins[0].version == "2.0.0"

    @patch("gltools.plugins.entry_points")
    def test_handles_import_error_gracefully(self, mock_eps: MagicMock) -> None:
        mock_eps.return_value = [_make_entry_point("bad", load_error=ImportError("no module"))]
        plugins = discover_plugins()
        assert len(plugins) == 1
        assert plugins[0].loaded is False
        assert plugins[0].error is not None
        assert "no module" in plugins[0].error

    @patch("gltools.plugins.entry_points")
    def test_mixed_valid_and_broken_plugins(self, mock_eps: MagicMock) -> None:
        mock_eps.return_value = [
            _make_entry_point("good", FakePlugin),
            _make_entry_point("bad", load_error=ImportError("broken")),
        ]
        plugins = discover_plugins()
        assert len(plugins) == 2
        assert plugins[0].loaded is True
        assert plugins[1].loaded is False

    @patch("gltools.plugins.entry_points")
    def test_entry_points_called_with_correct_group(self, mock_eps: MagicMock) -> None:
        mock_eps.return_value = []
        discover_plugins()
        mock_eps.assert_called_once_with(group="gltools.plugins")


class TestRegisterCliPlugins:
    """Tests for CLI plugin registration."""

    def test_registers_commands_from_plugin(self) -> None:
        app = typer.Typer()
        info = PluginInfo(entry_point_name="fake", plugin=FakePlugin(), loaded=True)
        register_cli_plugins([info], app)
        # The plugin should have registered a command
        assert info.loaded is True

    def test_handles_registration_error(self) -> None:
        app = typer.Typer()
        info = PluginInfo(entry_point_name="broken", plugin=BrokenPlugin(), loaded=True)
        register_cli_plugins([info], app)
        assert info.loaded is False
        assert info.error is not None
        assert "registration failed" in info.error.lower()

    def test_skips_unloaded_plugins(self) -> None:
        app = typer.Typer()
        info = PluginInfo(entry_point_name="skip", loaded=False)
        register_cli_plugins([info], app)
        assert info.loaded is False


class TestPluginInfo:
    """Tests for the PluginInfo dataclass."""

    def test_name_from_plugin(self) -> None:
        info = PluginInfo(entry_point_name="ep-name", plugin=FakePlugin(), loaded=True)
        assert info.name == "fake-plugin"

    def test_name_fallback_to_entry_point(self) -> None:
        info = PluginInfo(entry_point_name="ep-name")
        assert info.name == "ep-name"

    def test_version_from_plugin(self) -> None:
        info = PluginInfo(entry_point_name="ep", plugin=FakePlugin(), loaded=True)
        assert info.version == "2.0.0"

    def test_version_unknown_when_no_plugin(self) -> None:
        info = PluginInfo(entry_point_name="ep")
        assert info.version == "unknown"

    def test_status_loaded(self) -> None:
        info = PluginInfo(entry_point_name="ep", plugin=FakePlugin(), loaded=True)
        assert info.status == "loaded"

    def test_status_error(self) -> None:
        info = PluginInfo(entry_point_name="ep", error="import failed")
        assert "error" in info.status

    def test_status_not_loaded(self) -> None:
        info = PluginInfo(entry_point_name="ep")
        assert info.status == "not loaded"
