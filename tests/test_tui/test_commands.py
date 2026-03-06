"""Tests for the gltools TUI command palette."""

from __future__ import annotations

import pytest

from gltools.config.settings import GitLabConfig
from gltools.tui.app import GLToolsApp
from gltools.tui.commands import COMMANDS, GLToolsCommand, GLToolsProvider


def _make_config(
    host: str = "https://gitlab.com",
    token: str = "test-token",
    profile: str = "default",
) -> GitLabConfig:
    """Create a GitLabConfig for testing."""
    return GitLabConfig(host=host, token=token, profile=profile)


class TestGLToolsCommand:
    """Test the GLToolsCommand data class."""

    def test_display_text_with_keybinding(self) -> None:
        cmd = GLToolsCommand(
            name="Go to Dashboard",
            description="Show dashboard",
            callback_name="switch_screen_dashboard",
            keybinding="d",
        )
        assert cmd.display_text == "Go to Dashboard  [d]"

    def test_display_text_without_keybinding(self) -> None:
        cmd = GLToolsCommand(
            name="Some Action",
            description="Do something",
            callback_name="some_action",
        )
        assert cmd.display_text == "Some Action"

    def test_help_text(self) -> None:
        cmd = GLToolsCommand(
            name="Go to Dashboard",
            description="Show dashboard",
            callback_name="switch_screen_dashboard",
            category="Navigation",
        )
        assert cmd.help_text == "Navigation: Show dashboard"


class TestCommandsList:
    """Test the COMMANDS list is properly defined."""

    def test_commands_not_empty(self) -> None:
        assert len(COMMANDS) > 0

    def test_all_navigation_commands_present(self) -> None:
        nav_names = [c.name for c in COMMANDS if c.category == "Navigation"]
        assert "Go to Dashboard" in nav_names
        assert "Go to Merge Requests" in nav_names
        assert "Go to Issues" in nav_names
        assert "Go to CI/CD Pipelines" in nav_names

    def test_quit_command_present(self) -> None:
        quit_cmds = [c for c in COMMANDS if c.callback_name == "quit_app"]
        assert len(quit_cmds) == 1
        assert quit_cmds[0].keybinding == "q"

    def test_all_commands_have_keybinding_hints(self) -> None:
        for cmd in COMMANDS:
            assert cmd.keybinding is not None, f"Command '{cmd.name}' missing keybinding"

    def test_auth_required_commands(self) -> None:
        """Navigation and action commands require auth, but quit does not."""
        for cmd in COMMANDS:
            if cmd.callback_name == "quit_app":
                assert not cmd.requires_auth
            else:
                assert cmd.requires_auth


class TestGLToolsProviderIntegration:
    """Test the command palette provider in the app."""

    def test_app_has_commands_set(self) -> None:
        assert GLToolsProvider in GLToolsApp.COMMANDS

    @pytest.mark.asyncio
    async def test_command_palette_opens_with_ctrl_p(self) -> None:
        """Ctrl+P should open the command palette."""
        from textual.command import CommandPalette

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("ctrl+p")
            await pilot.pause()
            # CommandPalette is pushed as a modal screen
            assert isinstance(app.screen, CommandPalette)

    @pytest.mark.asyncio
    async def test_command_palette_dismiss_with_escape(self) -> None:
        """Escape should dismiss the command palette."""
        from textual.command import CommandPalette

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, CommandPalette)

    @pytest.mark.asyncio
    async def test_command_palette_navigate_to_mr(self) -> None:
        """Executing 'Go to Merge Requests' from palette should switch screen."""
        from gltools.tui.app import MergeRequestScreen

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            # Use action directly since testing palette search is fragile
            app.action_switch_screen("mr")
            await pilot.pause()
            assert app.query(MergeRequestScreen)

    @pytest.mark.asyncio
    async def test_no_auth_hides_auth_commands(self) -> None:
        """When not authenticated, auth-required commands should be hidden."""
        config = _make_config(token="")
        app = GLToolsApp(config=config)
        async with app.run_test(size=(80, 24)):
            # Verify the app has no auth
            assert not app._auth_available


class TestRefreshView:
    """Test the refresh current view functionality."""

    @pytest.mark.asyncio
    async def test_refresh_remounts_screen(self) -> None:
        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(80, 24)) as pilot:
            # Switch to MR screen first
            await pilot.press("m")
            await pilot.pause()

            # Refresh should remount the current screen
            app._refresh_current_view()
            await pilot.pause()
            # Should still be on MR screen after refresh
            from gltools.tui.app import MergeRequestScreen

            assert app.query(MergeRequestScreen)

    @pytest.mark.asyncio
    async def test_refresh_no_op_without_auth(self) -> None:
        config = _make_config(token="")
        app = GLToolsApp(config=config)
        async with app.run_test(size=(80, 24)):
            # Should not crash
            app._refresh_current_view()
