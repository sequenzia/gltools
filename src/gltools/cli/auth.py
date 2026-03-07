"""Authentication CLI commands for gltools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer
from rich.console import Console

from gltools.cli.app import auth_app
from gltools.services.auth import AuthService

console = Console()
err_console = Console(stderr=True)

DEFAULT_HOST = "https://gitlab.com"


def _get_profile(ctx: typer.Context) -> str:
    """Extract profile from context or default."""
    ctx.ensure_object(dict)
    return ctx.obj.get("profile") or "default"


def _is_json(ctx: typer.Context) -> bool:
    """Check if JSON output is requested."""
    ctx.ensure_object(dict)
    return ctx.obj.get("output_format") == "json"


def _output_json(data: dict[str, Any]) -> None:
    """Print JSON output to stdout."""
    console.print_json(json.dumps(data))


def _output_error_json(error: str, code: int | None = None) -> None:
    """Print JSON error to stderr."""
    data: dict[str, Any] = {"status": "error", "error": error}
    if code is not None:
        data["code"] = code
    err_console.print_json(json.dumps(data))


@auth_app.command(name="login")
def login(
    ctx: typer.Context,
    method: str = typer.Option(
        "pat",
        "--method",
        "-m",
        help="Authentication method: 'pat' (token), 'web' (browser OAuth), or 'device' (device code OAuth).",
    ),
) -> None:
    """Interactive setup flow: configure host, validate token, store credentials."""
    profile = _get_profile(ctx)
    use_json = _is_json(ctx)

    host = typer.prompt("GitLab host URL", default=DEFAULT_HOST)

    service = AuthService(profile=profile)

    if method == "pat":
        token = typer.prompt("Personal access token", hide_input=True)

        if not token.strip():
            if use_json:
                _output_error_json("Token cannot be empty.")
            else:
                err_console.print("[bold red]Error:[/bold red] Token cannot be empty.")
            raise typer.Exit(1)

        if not use_json:
            console.print(f"Validating token against {host}...")

        result = asyncio.run(service.login(host, token.strip()))

    elif method in ("web", "device"):
        client_id = typer.prompt("OAuth Application ID (from GitLab Settings > Applications)")

        if not client_id.strip():
            if use_json:
                _output_error_json("Application ID cannot be empty.")
            else:
                err_console.print("[bold red]Error:[/bold red] Application ID cannot be empty.")
            raise typer.Exit(1)

        if not use_json:
            if method == "web":
                console.print("Opening browser for authentication...")
            else:
                console.print("Starting device authorization flow...")

        result = asyncio.run(service.oauth_login(host, client_id.strip(), method=method))

    else:
        if use_json:
            _output_error_json(f"Unknown method '{method}'. Use 'pat', 'web', or 'device'.")
        else:
            err_console.print(f"[bold red]Error:[/bold red] Unknown method '{method}'. Use 'pat', 'web', or 'device'.")
        raise typer.Exit(1)

    if result.success:
        if use_json:
            _output_json(
                {
                    "status": "success",
                    "data": {
                        "username": result.username,
                        "host": result.host,
                        "profile": profile,
                        "token_storage": result.token_storage,
                        "auth_type": result.auth_type,
                    },
                }
            )
        else:
            console.print(f"[green]Authenticated as [bold]{result.username}[/bold] on {result.host}[/green]")
            console.print(f"[dim]Token stored in {result.token_storage} (profile: {profile})[/dim]")
    else:
        if use_json:
            _output_error_json(result.error or "Login failed.")
        else:
            err_console.print(f"[bold red]Error:[/bold red] {result.error}")
        raise typer.Exit(1)


@auth_app.command(name="status")
def status(ctx: typer.Context) -> None:
    """Show current authentication state."""
    profile = _get_profile(ctx)
    use_json = _is_json(ctx)

    service = AuthService(profile=profile)
    auth_status = asyncio.run(service.get_status())

    if not auth_status.authenticated:
        if use_json:
            _output_json(
                {
                    "status": "success",
                    "data": {
                        "authenticated": False,
                        "profile": auth_status.profile,
                        "config_file": auth_status.config_file,
                    },
                }
            )
        else:
            err_console.print("[yellow]Not authenticated.[/yellow] Run `gltools auth login` to set up.")
        raise typer.Exit(1)

    if use_json:
        _output_json(
            {
                "status": "success",
                "data": {
                    "authenticated": True,
                    "host": auth_status.host,
                    "username": auth_status.username,
                    "token_valid": auth_status.token_valid,
                    "config_file": auth_status.config_file,
                    "token_storage": auth_status.token_storage,
                    "profile": auth_status.profile,
                    "auth_type": auth_status.auth_type,
                },
            }
        )
    else:
        console.print(f"[bold]Profile:[/bold] {auth_status.profile}")
        console.print(f"[bold]Host:[/bold] {auth_status.host or '-'}")
        console.print(f"[bold]Username:[/bold] {auth_status.username or '-'}")
        valid_str = "[green]valid[/green]" if auth_status.token_valid else "[red]invalid[/red]"
        console.print(f"[bold]Token:[/bold] {valid_str}")
        console.print(f"[bold]Auth type:[/bold] {auth_status.auth_type}")
        console.print(f"[bold]Storage:[/bold] {auth_status.token_storage}")
        console.print(f"[bold]Config:[/bold] {auth_status.config_file}")


@auth_app.command(name="logout")
def logout(ctx: typer.Context) -> None:
    """Remove stored credentials for the current profile."""
    profile = _get_profile(ctx)
    use_json = _is_json(ctx)

    service = AuthService(profile=profile)
    deleted = service.logout()

    if deleted:
        if use_json:
            _output_json(
                {
                    "status": "success",
                    "data": {
                        "message": "Credentials removed.",
                        "profile": profile,
                    },
                }
            )
        else:
            console.print(f"[green]Credentials removed for profile '{profile}'.[/green]")
    else:
        if use_json:
            _output_json(
                {
                    "status": "success",
                    "data": {
                        "message": "No credentials found.",
                        "profile": profile,
                    },
                }
            )
        else:
            console.print(
                f"[yellow]No credentials found for profile '{profile}'.[/yellow] Run `gltools auth login` to set up."
            )
