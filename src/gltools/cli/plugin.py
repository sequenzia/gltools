"""Plugin management CLI commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from gltools.plugins import discover_plugins

console = Console()


def register_plugin_commands(app: typer.Typer) -> None:
    """Register plugin management commands on the given Typer app."""
    app.command(name="list")(list_plugins)


def list_plugins() -> None:
    """Show installed plugins (name, version, status)."""
    plugins = discover_plugins()

    if not plugins:
        typer.echo("No plugins found.")
        raise typer.Exit(0)

    table = Table(title="Installed Plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Status", style="yellow")

    for info in plugins:
        table.add_row(info.name, info.version, info.status)

    console.print(table)
