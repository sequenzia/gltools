"""Merge request CLI commands for gltools."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import typer
from rich.console import Console
from rich.syntax import Syntax

from gltools.cli.app import async_command, mr_app
from gltools.cli.formatting import (
    output_dry_run,
    output_error,
    output_paginated,
    output_result,
)
from gltools.client.exceptions import (
    AuthenticationError,
    ForbiddenError,
    GitLabClientError,
    NotFoundError,
    RateLimitError,
    ServerError,
)
from gltools.client.exceptions import (
    ConnectionError as GitLabConnectionError,
)
from gltools.client.exceptions import (
    TimeoutError as GitLabTimeoutError,
)
from gltools.models.output import CommandResult, DryRunResult, ErrorResult

console = Console()
err_console = Console(stderr=True)


def _get_current_branch() -> str | None:
    """Get the current git branch name, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch and branch != "HEAD" else None


def _ctx_obj(ctx: typer.Context) -> dict[str, Any]:
    """Get context object dict."""
    return ctx.ensure_object(dict)


async def _build_service(ctx: typer.Context, project: str | None = None) -> Any:
    """Build a MergeRequestService from CLI context.

    Returns a tuple of (service, client) so the caller can close the client.
    """
    from gltools.client.gitlab import GitLabClient
    from gltools.config.settings import GitLabConfig
    from gltools.services.merge_request import MergeRequestService

    obj = _ctx_obj(ctx)
    config = GitLabConfig.from_config(
        profile=obj.get("profile"),
        cli_overrides={
            "host": obj.get("host"),
            "token": obj.get("token"),
            "output_format": obj.get("output_format"),
        },
    )

    token_refresher = _make_token_refresher(config) if config.auth_type == "oauth" and config.client_id else None
    client = GitLabClient(
        host=config.host,
        token=config.token,
        auth_type=config.auth_type,
        token_refresher=token_refresher,
    )
    service = MergeRequestService(client, config, project=project)
    return service, client


def _make_token_refresher(config: Any) -> Any:
    """Build an async token refresher for OAuth clients."""

    async def _refresh() -> str:
        from gltools.config.keyring import get_refresh_token, store_refresh_token, store_token
        from gltools.config.oauth import refresh_access_token

        refresh_tok = get_refresh_token(profile=config.profile)
        if not refresh_tok:
            raise AuthenticationError("No refresh token. Re-run `gltools auth login --method web`.")

        result = await refresh_access_token(config.host, config.client_id, refresh_tok)
        store_token(result.access_token, profile=config.profile)
        if result.refresh_token:
            store_refresh_token(result.refresh_token, profile=config.profile)
        return result.access_token

    return _refresh


def _handle_dry_run(result: DryRunResult, ctx: typer.Context) -> None:
    """Output a dry-run result."""
    obj = _ctx_obj(ctx)
    output_dry_run(result, ctx_obj=obj)


def _handle_error(msg: str, ctx: typer.Context, *, code: int | None = None) -> None:
    """Output an error and exit with code 1."""
    obj = _ctx_obj(ctx)
    output_error(ErrorResult(error=msg, code=code), ctx_obj=obj)
    raise typer.Exit(1)


def _handle_gitlab_error(exc: GitLabClientError, ctx: typer.Context, mr_iid: int | None = None) -> None:
    """Handle a GitLab client error with appropriate messaging."""
    if isinstance(exc, NotFoundError):
        if mr_iid is not None:
            _handle_error(f"Merge request !{mr_iid} not found.", ctx, code=404)
        else:
            _handle_error(str(exc), ctx, code=404)
    elif isinstance(exc, AuthenticationError):
        _handle_error(
            "Authentication failed: token may be expired. Run `gltools auth login` to refresh.",
            ctx,
            code=401,
        )
    elif isinstance(exc, ForbiddenError):
        if mr_iid is not None:
            _handle_error(f"You don't have permission to access !{mr_iid}.", ctx, code=403)
        else:
            _handle_error("Permission denied. You don't have access to this resource.", ctx, code=403)
    elif isinstance(exc, GitLabConnectionError):
        _handle_error(
            "Unable to connect to GitLab. Check your network connection and the configured host URL.",
            ctx,
        )
    elif isinstance(exc, GitLabTimeoutError):
        _handle_error(
            "Request timed out. The server may be slow or unreachable. Try again later.",
            ctx,
        )
    elif isinstance(exc, (RateLimitError, ServerError)):
        _handle_error(str(exc), ctx)
    else:
        _handle_error(str(exc), ctx)


@mr_app.command(name="create")
@async_command
async def mr_create(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title", "-t", help="Merge request title."),
    source: str | None = typer.Option(None, "--source", "-s", help="Source branch (defaults to current branch)."),
    target: str = typer.Option("main", "--target", "-T", help="Target branch."),
    description: str | None = typer.Option(None, "--description", "-d", help="Merge request description."),
    labels: str | None = typer.Option(None, "--labels", "-l", help="Comma-separated labels."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating."),
) -> None:
    """Create a new merge request."""
    obj = _ctx_obj(ctx)

    source_branch = source
    if source_branch is None:
        source_branch = _get_current_branch()
        if source_branch is None:
            _handle_error(
                "Could not detect current branch. Specify --source explicitly.",
                ctx,
            )
            return

    label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()] if labels else None

    service, client = await _build_service(ctx, project)
    try:
        result = await service.create_mr(
            title=title,
            source_branch=source_branch,
            target_branch=target,
            description=description,
            labels=label_list,
            dry_run=dry_run,
        )
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx)
    finally:
        await client.close()


@mr_app.command(name="list")
@async_command
async def mr_list(
    ctx: typer.Context,
    state: str = typer.Option("opened", "--state", help="Filter by state (opened, closed, merged, all)."),
    author: str | None = typer.Option(None, "--author", help="Filter by author username."),
    labels: str | None = typer.Option(None, "--labels", "-l", help="Comma-separated labels."),
    scope: str | None = typer.Option(None, "--scope", help="Filter scope (created_by_me, assigned_to_me, all)."),
    search: str | None = typer.Option(None, "--search", help="Search in title and description."),
    per_page: int = typer.Option(20, "--per-page", help="Items per page."),
    page: int = typer.Option(1, "--page", help="Page number."),
    all_pages: bool = typer.Option(False, "--all", help="Fetch all pages."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
) -> None:
    """List merge requests with optional filters."""
    obj = _ctx_obj(ctx)

    label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()] if labels else None

    service, client = await _build_service(ctx, project)
    try:
        result = await service.list_mrs(
            state=state,
            labels=label_list,
            author=author,
            scope=scope,
            search=search,
            per_page=per_page,
            page=page,
            all_pages=all_pages,
        )
        output_paginated(result, entity_name="merge requests", ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx)
    finally:
        await client.close()


@mr_app.command(name="view")
@async_command
async def mr_view(
    ctx: typer.Context,
    mr_iid: int = typer.Argument(..., help="Merge request IID."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
) -> None:
    """View merge request details including description, diff stats, approvals, and pipeline status."""
    obj = _ctx_obj(ctx)

    service, client = await _build_service(ctx, project)
    try:
        mr = await service.get_mr(mr_iid)
        output_result(CommandResult(data=mr), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, mr_iid=mr_iid)
    finally:
        await client.close()


@mr_app.command(name="merge")
@async_command
async def mr_merge(
    ctx: typer.Context,
    mr_iid: int = typer.Argument(..., help="Merge request IID."),
    squash: bool = typer.Option(False, "--squash", help="Squash commits."),
    delete_branch: bool = typer.Option(False, "--delete-branch", help="Delete source branch after merge."),
    force: bool = typer.Option(False, "--force", help="Force merge even if pipeline is running."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without merging."),
) -> None:
    """Merge a merge request."""
    obj = _ctx_obj(ctx)

    service, client = await _build_service(ctx, project)
    try:
        # Check if already merged before attempting merge
        if not dry_run:
            mr = await service.get_mr(mr_iid)
            if mr.state == "merged":
                _handle_error(f"MR !{mr_iid} is already merged.", ctx)
                return

        result = await service.merge_mr(
            mr_iid,
            squash=squash,
            delete_branch=delete_branch,
            force=force,
            dry_run=dry_run,
        )
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, mr_iid=mr_iid)
    finally:
        await client.close()


@mr_app.command(name="approve")
@async_command
async def mr_approve(
    ctx: typer.Context,
    mr_iid: int = typer.Argument(..., help="Merge request IID."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without approving."),
) -> None:
    """Approve a merge request."""
    obj = _ctx_obj(ctx)

    service, client = await _build_service(ctx, project)
    try:
        result = await service.approve_mr(mr_iid, dry_run=dry_run)
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data={"approved": True, "mr_iid": mr_iid}), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, mr_iid=mr_iid)
    finally:
        await client.close()


@mr_app.command(name="diff")
@async_command
async def mr_diff(
    ctx: typer.Context,
    mr_iid: int = typer.Argument(..., help="Merge request IID."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
) -> None:
    """View merge request diff with syntax highlighting."""
    obj = _ctx_obj(ctx)

    service, client = await _build_service(ctx, project)
    try:
        diffs = await service.get_diff(mr_iid)

        fmt = obj.get("output_format")
        if fmt == "json":
            output_result(CommandResult(data=[d.model_dump() for d in diffs]), ctx_obj=obj)
        else:
            if not diffs:
                console.print("No changes in this merge request.")
                return

            out = Console(file=sys.stdout, force_terminal=None)
            for diff_file in diffs:
                # Header showing file path and status
                if diff_file.new_file:
                    status = "[green]new file[/green]"
                elif diff_file.deleted_file:
                    status = "[red]deleted[/red]"
                elif diff_file.renamed_file:
                    status = f"[yellow]renamed[/yellow] {diff_file.old_path} -> {diff_file.new_path}"
                else:
                    status = "[blue]modified[/blue]"

                out.print(f"\n[bold]{diff_file.new_path}[/bold] ({status})")
                out.print("=" * min(len(diff_file.new_path) + 20, 80))

                # Syntax-highlighted diff
                if diff_file.diff:
                    syntax = Syntax(diff_file.diff, "diff", theme="monokai", line_numbers=False)
                    out.print(syntax)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, mr_iid=mr_iid)
    finally:
        await client.close()


@mr_app.command(name="note")
@async_command
async def mr_note(
    ctx: typer.Context,
    mr_iid: int = typer.Argument(..., help="Merge request IID."),
    body: str = typer.Option(..., "--body", "-b", help="Note body text."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating."),
) -> None:
    """Add a comment/note to a merge request."""
    obj = _ctx_obj(ctx)

    service, client = await _build_service(ctx, project)
    try:
        result = await service.add_note(mr_iid, body, dry_run=dry_run)
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, mr_iid=mr_iid)
    finally:
        await client.close()


@mr_app.command(name="close")
@async_command
async def mr_close(
    ctx: typer.Context,
    mr_iid: int = typer.Argument(..., help="Merge request IID."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without closing."),
) -> None:
    """Close a merge request without merging."""
    obj = _ctx_obj(ctx)

    service, client = await _build_service(ctx, project)
    try:
        result = await service.close_mr(mr_iid, dry_run=dry_run)
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, mr_iid=mr_iid)
    finally:
        await client.close()


@mr_app.command(name="reopen")
@async_command
async def mr_reopen(
    ctx: typer.Context,
    mr_iid: int = typer.Argument(..., help="Merge request IID."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without reopening."),
) -> None:
    """Reopen a closed merge request."""
    obj = _ctx_obj(ctx)

    service, client = await _build_service(ctx, project)
    try:
        result = await service.reopen_mr(mr_iid, dry_run=dry_run)
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, mr_iid=mr_iid)
    finally:
        await client.close()


@mr_app.command(name="update")
@async_command
async def mr_update(
    ctx: typer.Context,
    mr_iid: int = typer.Argument(..., help="Merge request IID."),
    title: str | None = typer.Option(None, "--title", "-t", help="New title."),
    description: str | None = typer.Option(None, "--description", "-d", help="New description."),
    labels: str | None = typer.Option(None, "--labels", "-l", help="Comma-separated labels."),
    target_branch: str | None = typer.Option(None, "--target", "-T", help="New target branch."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path or ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without updating."),
) -> None:
    """Update merge request properties."""
    obj = _ctx_obj(ctx)

    fields: dict[str, Any] = {}
    if title is not None:
        fields["title"] = title
    if description is not None:
        fields["description"] = description
    if labels is not None:
        fields["labels"] = labels
    if target_branch is not None:
        fields["target_branch"] = target_branch

    if not fields and not dry_run:
        _handle_error("No fields to update. Use --title, --description, --labels, or --target.", ctx)
        return

    service, client = await _build_service(ctx, project)
    try:
        result = await service.update_mr(mr_iid, dry_run=dry_run, **fields)
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, mr_iid=mr_iid)
    finally:
        await client.close()
