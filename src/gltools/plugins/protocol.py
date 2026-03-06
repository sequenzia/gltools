"""GLToolsPlugin protocol defining the extension interface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import textual.app
    import typer


@runtime_checkable
class GLToolsPlugin(Protocol):
    """Protocol that all gltools plugins must implement.

    Plugins are discovered via the ``gltools.plugins`` entry point group.
    Each entry point should reference a class (or callable returning an instance)
    that satisfies this protocol.
    """

    name: str
    version: str

    def register_commands(self, app: typer.Typer) -> None:
        """Register CLI commands with the given Typer application."""
        ...

    def register_tui_views(self, app: textual.app.App) -> None:
        """Register TUI views with the given Textual application."""
        ...
