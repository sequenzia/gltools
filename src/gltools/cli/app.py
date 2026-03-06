"""Main Typer application for gltools CLI."""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import typer

from gltools import __version__
from gltools.cli.plugin import register_plugin_commands

# Subcommand groups
mr_app = typer.Typer(name="mr", help="Merge request commands.")
issue_app = typer.Typer(name="issue", help="Issue commands.")
ci_app = typer.Typer(name="ci", help="CI/CD pipeline commands.")
auth_app = typer.Typer(name="auth", help="Authentication commands.")
plugin_app = typer.Typer(name="plugin", help="Plugin management commands.")

# Placeholder commands so Typer registers each group
# (Typer won't show a group in --help unless it has at least one command)


@mr_app.callback(invoke_without_command=True)
def mr_callback(ctx: typer.Context) -> None:
    """Merge request commands."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(0)


@issue_app.callback(invoke_without_command=True)
def issue_callback(ctx: typer.Context) -> None:
    """Issue commands."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(0)


@ci_app.callback(invoke_without_command=True)
def ci_callback(ctx: typer.Context) -> None:
    """CI/CD pipeline commands."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(0)


@auth_app.callback(invoke_without_command=True)
def auth_callback(ctx: typer.Context) -> None:
    """Authentication commands."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(0)


@plugin_app.callback(invoke_without_command=True)
def plugin_callback(ctx: typer.Context) -> None:
    """Plugin management commands."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(0)


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"gltools {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="gltools",
    help="A Python-based CLI and TUI for GitLab.",
    no_args_is_help=True,
)

# Register subcommand groups
app.add_typer(mr_app)
app.add_typer(issue_app)
app.add_typer(ci_app)
app.add_typer(auth_app)
app.add_typer(plugin_app)

# Register plugin subcommands
register_plugin_commands(plugin_app)


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(  # noqa: ARG001
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format.",
    ),
    text_output: bool = typer.Option(
        False,
        "--text",
        help="Output in human-readable text format.",
    ),
    host: str | None = typer.Option(
        None,
        "--host",
        help="GitLab host URL.",
        envvar="GLTOOLS_HOST",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        help="GitLab personal access token.",
        envvar="GLTOOLS_TOKEN",
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Configuration profile name.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress non-error output.",
    ),
) -> None:
    """gltools - CLI and TUI for GitLab."""
    ctx.ensure_object(dict)

    # Determine output format from flags
    output_format: str | None = None
    if json_output:
        output_format = "json"
    elif text_output:
        output_format = "text"

    ctx.obj["output_format"] = output_format
    ctx.obj["host"] = host
    ctx.obj["token"] = token
    ctx.obj["profile"] = profile
    ctx.obj["quiet"] = quiet


@app.command()
def tui(ctx: typer.Context) -> None:
    """Launch the interactive TUI."""
    from gltools.tui import launch_tui

    obj = ctx.ensure_object(dict)
    launch_tui(
        profile=obj.get("profile"),
        host=obj.get("host"),
        token=obj.get("token"),
    )


def async_command(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap an async function so it can be used as a Typer command handler."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(func(*args, **kwargs))

    return wrapper
