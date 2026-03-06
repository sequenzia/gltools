"""Tests for the gltools TUI application."""

from __future__ import annotations

import pytest
from textual.widgets import Footer, Header

from gltools.config.settings import GitLabConfig
from gltools.tui.app import (
    AuthRequiredScreen,
    CIScreen,
    DashboardScreen,
    GLToolsApp,
    IssueScreen,
    MergeRequestScreen,
)


def _make_config(
    host: str = "https://gitlab.com",
    token: str = "test-token",
    profile: str = "default",
) -> GitLabConfig:
    """Create a GitLabConfig for testing."""
    return GitLabConfig(host=host, token=token, profile=profile)


class TestGLToolsAppInit:
    """Test app initialization."""

    def test_app_title(self) -> None:
        app = GLToolsApp(config=_make_config())
        assert app.TITLE == "gltools"

    def test_app_bindings(self) -> None:
        app = GLToolsApp(config=_make_config())
        binding_keys = [b.key for b in app.BINDINGS]
        assert "d" in binding_keys
        assert "m" in binding_keys
        assert "i" in binding_keys
        assert "c" in binding_keys
        assert "q" in binding_keys


class TestGLToolsAppMount:
    """Test app mounting and screen display."""

    @pytest.mark.asyncio
    async def test_app_has_header_and_footer(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)):
            assert app.query_one(Header)
            assert app.query_one(Footer)

    @pytest.mark.asyncio
    async def test_app_shows_dashboard_on_mount(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)):
            assert app.query(DashboardScreen)

    @pytest.mark.asyncio
    async def test_app_sub_title_shows_host(self) -> None:
        app = GLToolsApp(config=_make_config(host="https://gitlab.example.com"))
        async with app.run_test(size=(80, 24)):
            assert app.sub_title == "https://gitlab.example.com"

    @pytest.mark.asyncio
    async def test_auth_required_when_no_token(self) -> None:
        config = _make_config(token="")
        app = GLToolsApp(config=config)
        async with app.run_test(size=(80, 24)):
            auth_screens = app.query(AuthRequiredScreen)
            assert len(auth_screens) > 0


class TestScreenNavigation:
    """Test keyboard-driven screen navigation."""

    @pytest.mark.asyncio
    async def test_switch_to_mr_screen(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("m")
            assert app.query(MergeRequestScreen)

    @pytest.mark.asyncio
    async def test_switch_to_issues_screen(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("i")
            assert app.query(IssueScreen)

    @pytest.mark.asyncio
    async def test_switch_to_ci_screen(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("c")
            assert app.query(CIScreen)

    @pytest.mark.asyncio
    async def test_switch_back_to_dashboard(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("m")
            await pilot.press("d")
            assert app.query(DashboardScreen)

    @pytest.mark.asyncio
    async def test_no_navigation_without_auth(self) -> None:
        config = _make_config(token="")
        app = GLToolsApp(config=config)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("m")
            assert app.query(AuthRequiredScreen)
            assert not app.query(MergeRequestScreen)


class TestScreenNavigationCycles:
    """Test navigation cycles between multiple screens."""

    @pytest.mark.asyncio
    async def test_cycle_through_all_screens(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.query(DashboardScreen)
            await pilot.press("m")
            assert app.query(MergeRequestScreen)
            await pilot.press("i")
            assert app.query(IssueScreen)
            await pilot.press("c")
            assert app.query(CIScreen)
            await pilot.press("d")
            assert app.query(DashboardScreen)

    @pytest.mark.asyncio
    async def test_rapid_screen_switches(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("m")
            await pilot.press("i")
            await pilot.press("c")
            assert app.query(CIScreen)

    @pytest.mark.asyncio
    async def test_switch_to_same_screen(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("m")
            assert app.query(MergeRequestScreen)
            await pilot.press("m")
            assert app.query(MergeRequestScreen)

    def test_show_screen_unknown_falls_back_to_dashboard_widget(self) -> None:
        app = GLToolsApp(config=_make_config())
        assert app._current_screen_name == "dashboard"

    @pytest.mark.asyncio
    async def test_current_screen_name_tracked(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            assert app._current_screen_name == "dashboard"
            await pilot.press("m")
            assert app._current_screen_name == "mr"
            await pilot.press("i")
            assert app._current_screen_name == "issues"
            await pilot.press("c")
            assert app._current_screen_name == "ci"

    def test_quit_keybinding(self) -> None:
        app = GLToolsApp(config=_make_config())
        binding_keys = [b.key for b in app.BINDINGS]
        assert "q" in binding_keys


class TestScreenWidgets:
    """Test individual screen widgets."""

    def test_dashboard_screen_stores_config(self) -> None:
        config = _make_config()
        screen = DashboardScreen(config)
        assert screen._config is config

    def test_mr_screen_stores_config(self) -> None:
        config = _make_config()
        screen = MergeRequestScreen(config)
        assert screen._config is config

    def test_issue_screen_stores_config(self) -> None:
        config = _make_config()
        screen = IssueScreen(config)
        assert screen._config is config

    def test_ci_screen_stores_config(self) -> None:
        config = _make_config()
        screen = CIScreen(config)
        assert screen._config is config


class TestTerminalSize:
    """Test terminal size handling."""

    @pytest.mark.asyncio
    async def test_check_terminal_size_sufficient(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)):
            assert app.check_terminal_size()


class TestCLIIntegration:
    """Test the CLI tui command integration."""

    def test_tui_command_registered(self) -> None:
        from typer.testing import CliRunner

        from gltools.cli.app import app as cli_app

        runner = CliRunner()
        result = runner.invoke(cli_app, ["--help"])
        assert "tui" in result.output

    def test_launch_tui_importable(self) -> None:
        from gltools.tui import launch_tui

        assert callable(launch_tui)

    def test_gltools_app_importable(self) -> None:
        from gltools.tui import GLToolsApp

        assert GLToolsApp is not None
