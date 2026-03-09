"""Issue CLI commands for gltools."""

from __future__ import annotations

import logging
from typing import Any

import typer

from gltools.cli.app import async_command, issue_app
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

logger = logging.getLogger("gltools.cli.issue")


def _ctx_obj(ctx: typer.Context) -> dict[str, Any]:
    """Get context object dict."""
    return ctx.ensure_object(dict)


async def _build_service(ctx: typer.Context, project: str | None = None) -> Any:
    """Build an IssueService from CLI context.

    Returns a tuple of (service, client) so the caller can close the client.
    """
    from gltools.client.gitlab import GitLabClient
    from gltools.config.settings import GitLabConfig
    from gltools.services.issue import IssueService

    obj = _ctx_obj(ctx)
    config = GitLabConfig.from_config(
        profile=obj.get("profile"),
        cli_overrides={
            "host": obj.get("host"),
            "token": obj.get("token"),
            "output_format": obj.get("output_format"),
        },
    )

    logger.info(
        "Config: host=%s, auth=%s, project=%s, profile=%s",
        config.host,
        config.auth_type,
        project or config.default_project or "(auto-detect)",
        config.profile,
    )

    token_refresher = _make_token_refresher(config) if config.auth_type == "oauth" and config.client_id else None
    client = GitLabClient(
        host=config.host,
        token=config.token,
        auth_type=config.auth_type,
        token_refresher=token_refresher,
    )
    service = IssueService(client, config, project=project)
    return service, client


def _make_token_refresher(config: Any) -> Any:
    """Build an async token refresher for OAuth clients."""

    async def _refresh() -> str:
        from gltools.config.keyring import get_refresh_token, store_refresh_token, store_token
        from gltools.config.oauth import refresh_access_token

        refresh_tok = get_refresh_token(profile=config.profile)
        if not refresh_tok:
            from gltools.client.exceptions import AuthenticationError

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


def _handle_gitlab_error(exc: GitLabClientError, ctx: typer.Context, issue_iid: int | None = None) -> None:
    """Handle a GitLab client error with appropriate messaging."""
    if isinstance(exc, NotFoundError):
        if issue_iid is not None:
            _handle_error(f"Issue #{issue_iid} not found", ctx, code=404)
        else:
            _handle_error(str(exc), ctx, code=404)
    elif isinstance(exc, AuthenticationError):
        _handle_error(
            "Authentication failed: token may be expired. Run `gltools auth login` to refresh.",
            ctx,
            code=401,
        )
    elif isinstance(exc, ForbiddenError):
        if issue_iid is not None:
            _handle_error(f"You don't have permission to access #{issue_iid}.", ctx, code=403)
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


def _parse_labels(labels: str | None) -> list[str] | None:
    """Parse comma-separated labels string into a list."""
    if not labels:
        return None
    return [lbl.strip() for lbl in labels.split(",") if lbl.strip()]


def _parse_int_list(value: str | None) -> list[int] | None:
    """Parse comma-separated integer string into a list."""
    if not value:
        return None
    return [int(v.strip()) for v in value.split(",") if v.strip()]


@issue_app.command(name="create")
@async_command
async def issue_create(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title", "-t", help="Issue title."),
    description: str | None = typer.Option(None, "--description", "-d", help="Issue description."),
    labels: str | None = typer.Option(None, "--labels", "-l", help="Comma-separated labels."),
    assignee_ids: str | None = typer.Option(None, "--assignee-ids", help="Comma-separated assignee user IDs."),
    milestone_id: int | None = typer.Option(None, "--milestone-id", help="Milestone ID."),
    due_date: str | None = typer.Option(None, "--due-date", help="Due date (YYYY-MM-DD)."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating."),
) -> None:
    """Create a new issue."""
    obj = _ctx_obj(ctx)
    service, client = await _build_service(ctx, project)
    try:
        result = await service.create_issue(
            title=title,
            description=description,
            labels=_parse_labels(labels),
            assignee_ids=_parse_int_list(assignee_ids),
            milestone_id=milestone_id,
            due_date=due_date,
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


@issue_app.command(name="list")
@async_command
async def issue_list(
    ctx: typer.Context,
    state: str | None = typer.Option(None, "--state", "-s", help="Filter by state (opened, closed, all)."),
    labels: str | None = typer.Option(None, "--labels", "-l", help="Comma-separated labels to filter by."),
    assignee: str | None = typer.Option(None, "--assignee", help="Filter by assignee username."),
    milestone: str | None = typer.Option(None, "--milestone", help="Filter by milestone title."),
    scope: str | None = typer.Option(None, "--scope", help="Filter scope (created_by_me, assigned_to_me, all)."),
    search: str | None = typer.Option(None, "--search", help="Search in title and description."),
    per_page: int = typer.Option(20, "--per-page", help="Items per page."),
    page: int = typer.Option(1, "--page", help="Page number."),
    all_pages: bool = typer.Option(False, "--all", help="Fetch all pages."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path."),
) -> None:
    """List issues with optional filters."""
    obj = _ctx_obj(ctx)
    service, client = await _build_service(ctx, project)
    try:
        response = await service.list_issues(
            state=state,
            labels=_parse_labels(labels),
            assignee=assignee,
            milestone=milestone,
            scope=scope,
            search=search,
            per_page=per_page,
            page=page,
            all_pages=all_pages,
        )
        output_paginated(response, entity_name="issues", ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx)
    finally:
        await client.close()


@issue_app.command(name="view")
@async_command
async def issue_view(
    ctx: typer.Context,
    issue_iid: int = typer.Argument(..., help="Issue IID."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path."),
) -> None:
    """View issue details with comments."""
    obj = _ctx_obj(ctx)
    service, client = await _build_service(ctx, project)
    try:
        issue = await service.get_issue(issue_iid)
        output_result(CommandResult(data=issue), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, issue_iid=issue_iid)
    finally:
        await client.close()


@issue_app.command(name="update")
@async_command
async def issue_update(
    ctx: typer.Context,
    issue_iid: int = typer.Argument(..., help="Issue IID."),
    title: str | None = typer.Option(None, "--title", "-t", help="New title."),
    description: str | None = typer.Option(None, "--description", "-d", help="New description."),
    labels: str | None = typer.Option(None, "--labels", "-l", help="Comma-separated labels to set."),
    assignee_ids: str | None = typer.Option(None, "--assignee-ids", help="Comma-separated assignee user IDs."),
    milestone_id: int | None = typer.Option(None, "--milestone-id", help="Milestone ID."),
    due_date: str | None = typer.Option(None, "--due-date", help="Due date (YYYY-MM-DD)."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without updating."),
) -> None:
    """Update an existing issue."""
    obj = _ctx_obj(ctx)

    fields: dict[str, Any] = {}
    if title is not None:
        fields["title"] = title
    if description is not None:
        fields["description"] = description
    if labels is not None:
        fields["labels"] = labels
    if assignee_ids is not None:
        fields["assignee_ids"] = _parse_int_list(assignee_ids)
    if milestone_id is not None:
        fields["milestone_id"] = milestone_id
    if due_date is not None:
        fields["due_date"] = due_date

    if not fields and not dry_run:
        _handle_error(
            "No fields to update. Use --title, --description, --labels, --assignee-ids, --milestone-id, or --due-date.",
            ctx,
        )
        return

    service, client = await _build_service(ctx, project)
    try:
        result = await service.update_issue(issue_iid, dry_run=dry_run, **fields)
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, issue_iid=issue_iid)
    finally:
        await client.close()


@issue_app.command(name="close")
@async_command
async def issue_close(
    ctx: typer.Context,
    issue_iid: int = typer.Argument(..., help="Issue IID."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without closing."),
) -> None:
    """Close an issue."""
    obj = _ctx_obj(ctx)
    service, client = await _build_service(ctx, project)
    try:
        result = await service.close_issue(issue_iid, dry_run=dry_run)
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, issue_iid=issue_iid)
    finally:
        await client.close()


@issue_app.command(name="reopen")
@async_command
async def issue_reopen(
    ctx: typer.Context,
    issue_iid: int = typer.Argument(..., help="Issue IID."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without reopening."),
) -> None:
    """Reopen a closed issue."""
    obj = _ctx_obj(ctx)
    service, client = await _build_service(ctx, project)
    try:
        result = await service.reopen_issue(issue_iid, dry_run=dry_run)
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, issue_iid=issue_iid)
    finally:
        await client.close()


@issue_app.command(name="note")
@async_command
async def issue_note(
    ctx: typer.Context,
    issue_iid: int = typer.Argument(..., help="Issue IID."),
    body: str = typer.Option(..., "--body", "-b", help="Note body text."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without adding note."),
) -> None:
    """Add a comment (note) to an issue."""
    obj = _ctx_obj(ctx)
    service, client = await _build_service(ctx, project)
    try:
        result = await service.add_note(issue_iid, body, dry_run=dry_run)
        if isinstance(result, DryRunResult):
            _handle_dry_run(result, ctx)
        else:
            output_result(CommandResult(data=result), ctx_obj=obj)
    except GitLabClientError as exc:
        _handle_gitlab_error(exc, ctx, issue_iid=issue_iid)
    finally:
        await client.close()
