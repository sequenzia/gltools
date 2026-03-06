"""Command palette provider for the gltools TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.command import DiscoveryHit, Hit, Hits, Provider

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

    from gltools.tui.app import GLToolsApp


class GLToolsCommand:
    """Represents an available command in the palette."""

    def __init__(
        self,
        name: str,
        description: str,
        callback_name: str,
        keybinding: str | None = None,
        requires_auth: bool = False,
        category: str = "Navigation",
    ) -> None:
        self.name = name
        self.description = description
        self.callback_name = callback_name
        self.keybinding = keybinding
        self.requires_auth = requires_auth
        self.category = category

    @property
    def display_text(self) -> str:
        """Command name with keybinding hint."""
        if self.keybinding:
            return f"{self.name}  [{self.keybinding}]"
        return self.name

    @property
    def help_text(self) -> str:
        """Category and description for the help line."""
        return f"{self.category}: {self.description}"


# All available commands with keybinding hints
COMMANDS: list[GLToolsCommand] = [
    # Navigation commands
    GLToolsCommand(
        name="Go to Dashboard",
        description="Show the dashboard overview",
        callback_name="switch_screen_dashboard",
        keybinding="d",
        requires_auth=True,
        category="Navigation",
    ),
    GLToolsCommand(
        name="Go to Merge Requests",
        description="Show the merge request list",
        callback_name="switch_screen_mr",
        keybinding="m",
        requires_auth=True,
        category="Navigation",
    ),
    GLToolsCommand(
        name="Go to Issues",
        description="Show the issue list",
        callback_name="switch_screen_issues",
        keybinding="i",
        requires_auth=True,
        category="Navigation",
    ),
    GLToolsCommand(
        name="Go to CI/CD Pipelines",
        description="Show CI/CD pipeline status",
        callback_name="switch_screen_ci",
        keybinding="c",
        requires_auth=True,
        category="Navigation",
    ),
    # MR operations
    GLToolsCommand(
        name="Refresh Current View",
        description="Reload data for the current screen",
        callback_name="refresh_view",
        keybinding="r",
        requires_auth=True,
        category="Actions",
    ),
    # Application commands
    GLToolsCommand(
        name="Quit Application",
        description="Exit gltools TUI",
        callback_name="quit_app",
        keybinding="q",
        category="Application",
    ),
]


class GLToolsProvider(Provider):
    """Command palette provider for gltools TUI actions.

    Provides fuzzy search across all available actions including
    screen navigation, MR/issue/CI operations. Shows keybinding
    hints alongside command names.
    """

    @property
    def _gltools_app(self) -> GLToolsApp:
        """Get the typed app reference."""
        return self.app  # type: ignore[return-value]

    def _is_command_available(self, command: GLToolsCommand) -> bool:
        """Check if a command is available in the current context."""
        return not (command.requires_auth and not self._gltools_app._auth_available)

    async def discover(self) -> Hits:
        """Yield all available commands for initial display."""
        for cmd in COMMANDS:
            if not self._is_command_available(cmd):
                continue

            callback = self._make_callback(cmd.callback_name)
            yield DiscoveryHit(
                display=cmd.display_text,
                command=callback,
                help=cmd.help_text,
            )

    async def search(self, query: str) -> Hits:
        """Fuzzy search across all available commands."""
        matcher = self.matcher(query)

        for cmd in COMMANDS:
            if not self._is_command_available(cmd):
                continue

            # Match against the command name, category, and description
            search_text = f"{cmd.name} {cmd.category} {cmd.description}"
            score = matcher.match(search_text)

            if score > 0:
                callback = self._make_callback(cmd.callback_name)
                yield Hit(
                    score=score,
                    match_display=matcher.highlight(cmd.display_text),
                    command=callback,
                    help=cmd.help_text,
                )

    def _make_callback(self, callback_name: str) -> Callable[[], Coroutine[Any, Any, None]]:
        """Create a callback function for a command."""
        gltools_app = self._gltools_app

        async def _execute() -> None:
            if callback_name == "switch_screen_dashboard":
                gltools_app.action_switch_screen("dashboard")
            elif callback_name == "switch_screen_mr":
                gltools_app.action_switch_screen("mr")
            elif callback_name == "switch_screen_issues":
                gltools_app.action_switch_screen("issues")
            elif callback_name == "switch_screen_ci":
                gltools_app.action_switch_screen("ci")
            elif callback_name == "refresh_view":
                gltools_app._refresh_current_view()
            elif callback_name == "quit_app":
                gltools_app.exit()

        return _execute
