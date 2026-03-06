"""Main Textual application for gltools TUI."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, LoadingIndicator, Static

from gltools.config.keyring import get_token
from gltools.config.settings import GitLabConfig
from gltools.tui.commands import GLToolsProvider
from gltools.tui.screens.dashboard import DashboardScreen


class AuthRequiredScreen(Static):
    """Displayed when no authentication is configured."""

    def compose(self) -> ComposeResult:
        yield Static(
            "\n\n  Authentication Required\n\n"
            "  No GitLab token is configured.\n"
            "  Run 'gltools auth login' to authenticate first.\n\n"
            "  Press 'q' to quit.\n",
            id="auth-required-message",
        )


class MergeRequestScreen(Static):
    """Merge request list screen."""

    DEFAULT_CSS = """
    MergeRequestScreen {
        height: 1fr;
        padding: 1 2;
    }
    """

    def __init__(self, config: GitLabConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield Static("Merge Requests", id="mr-title")
        yield LoadingIndicator(id="mr-loading")

    def on_mount(self) -> None:
        loading_indicator = self.query_one("#mr-loading", LoadingIndicator)
        loading_indicator.display = False
        self.query_one("#mr-title", Static).update(
            f"Merge Requests\n\n  Host: {self._config.host}\n  Loading merge requests..."
        )


class IssueScreen(Static):
    """Issue list screen."""

    DEFAULT_CSS = """
    IssueScreen {
        height: 1fr;
        padding: 1 2;
    }
    """

    def __init__(self, config: GitLabConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield Static("Issues", id="issue-title")
        yield LoadingIndicator(id="issue-loading")

    def on_mount(self) -> None:
        loading_indicator = self.query_one("#issue-loading", LoadingIndicator)
        loading_indicator.display = False
        self.query_one("#issue-title", Static).update(
            f"Issues\n\n  Host: {self._config.host}\n  Loading issues..."
        )


class CIScreen(Static):
    """CI/CD pipeline status screen."""

    DEFAULT_CSS = """
    CIScreen {
        height: 1fr;
        padding: 1 2;
    }
    """

    def __init__(self, config: GitLabConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield Static("CI/CD Pipelines", id="ci-title")
        yield LoadingIndicator(id="ci-loading")

    def on_mount(self) -> None:
        loading_indicator = self.query_one("#ci-loading", LoadingIndicator)
        loading_indicator.display = False
        self.query_one("#ci-title", Static).update(
            f"CI/CD Pipelines\n\n  Host: {self._config.host}\n  Loading pipelines..."
        )


class GLToolsApp(App[None]):
    """Main gltools TUI application."""

    TITLE = "gltools"
    SUB_TITLE = "GitLab TUI"

    CSS = """
    Screen {
        layout: vertical;
    }

    #auth-required-message {
        text-align: center;
        margin: 4 8;
        padding: 2 4;
        border: heavy $warning;
        height: auto;
    }

    #screen-container {
        height: 1fr;
    }
    """

    COMMANDS = {GLToolsProvider}

    BINDINGS = [
        Binding("d", "switch_screen('dashboard')", "Dashboard", show=True),
        Binding("m", "switch_screen('mr')", "MRs", show=True),
        Binding("i", "switch_screen('issues')", "Issues", show=True),
        Binding("c", "switch_screen('ci')", "CI/CD", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        *,
        config: GitLabConfig | None = None,
        profile: str | None = None,
        host: str | None = None,
        token: str | None = None,
    ) -> None:
        super().__init__()
        cli_overrides: dict[str, str | None] = {}
        if host:
            cli_overrides["host"] = host
        if token:
            cli_overrides["token"] = token
        if profile:
            cli_overrides["profile"] = profile

        if config is not None:
            self._config = config
        else:
            self._config = GitLabConfig.from_config(
                profile=profile,
                cli_overrides=cli_overrides if cli_overrides else None,
            )

        self._current_screen_name = "dashboard"
        self._auth_available = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="screen-container")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = self._config.host
        token = self._config.token or get_token(profile=self._config.profile)
        self._auth_available = bool(token)

        if not self._auth_available:
            self._show_auth_required()
        else:
            self._show_screen("dashboard")

    def _show_auth_required(self) -> None:
        """Display the auth required message."""
        container = self.query_one("#screen-container", Static)
        container.remove_children()
        container.mount(AuthRequiredScreen())

    def _show_screen(self, screen_name: str) -> None:
        """Switch the displayed screen content."""
        container = self.query_one("#screen-container", Static)
        container.remove_children()

        screen_widget: Static | DashboardScreen
        if screen_name == "dashboard":
            screen_widget = DashboardScreen(self._config)
        elif screen_name == "mr":
            screen_widget = MergeRequestScreen(self._config)
        elif screen_name == "issues":
            screen_widget = IssueScreen(self._config)
        elif screen_name == "ci":
            screen_widget = CIScreen(self._config)
        else:
            screen_widget = DashboardScreen(self._config)

        self._current_screen_name = screen_name
        container.mount(screen_widget)

    def action_switch_screen(self, screen_name: str) -> None:
        """Handle screen switching via keybinding."""
        if not self._auth_available:
            return
        self._show_screen(screen_name)

    def _refresh_current_view(self) -> None:
        """Refresh the current screen by remounting it."""
        if not self._auth_available:
            return
        self._show_screen(self._current_screen_name)

    def check_terminal_size(self) -> bool:
        """Check if terminal is large enough for the TUI."""
        return self.size.width >= 40 and self.size.height >= 10

    def on_resize(self) -> None:
        """Handle terminal resize events."""
        if not self.check_terminal_size():
            self.notify(
                "Terminal too small. Please resize to at least 40x10.",
                severity="warning",
                timeout=5,
            )
