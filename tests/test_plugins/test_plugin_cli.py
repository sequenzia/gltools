"""Tests for plugin CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gltools.cli.app import app
from gltools.plugins import PluginInfo

runner = CliRunner()


class TestPluginListCommand:
    """Tests for the `gltools plugin list` command."""

    @patch("gltools.cli.plugin.discover_plugins")
    def test_no_plugins_shows_message(self, mock_discover: MagicMock) -> None:
        mock_discover.return_value = []
        result = runner.invoke(app, ["plugin", "list"])
        assert result.exit_code == 0
        assert "No plugins found" in result.output

    @patch("gltools.cli.plugin.discover_plugins")
    def test_shows_plugin_info(self, mock_discover: MagicMock) -> None:
        fake_plugin = MagicMock()
        fake_plugin.name = "my-plugin"
        fake_plugin.version = "1.0.0"
        info = PluginInfo(entry_point_name="my-plugin", plugin=fake_plugin, loaded=True)
        mock_discover.return_value = [info]
        result = runner.invoke(app, ["plugin", "list"])
        assert result.exit_code == 0
        assert "my-plugin" in result.output
        assert "1.0.0" in result.output
        assert "loaded" in result.output

    @patch("gltools.cli.plugin.discover_plugins")
    def test_shows_error_plugin(self, mock_discover: MagicMock) -> None:
        info = PluginInfo(entry_point_name="broken", error="import failed")
        mock_discover.return_value = [info]
        result = runner.invoke(app, ["plugin", "list"])
        assert result.exit_code == 0
        assert "broken" in result.output
        assert "error" in result.output
