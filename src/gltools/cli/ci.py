"""CI/CD pipeline CLI commands for gltools."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from gltools.cli.app import ci_app
from gltools.cli.formatting import (
    STATUS_COLORS,
    _colored_status,
    _create_console,
    format_json_success,
    get_output_format,
    is_quiet,
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

err_console = Console(stderr=True, force_terminal=None)


def _build_service(ctx: typer.Context) -> Any:
    """Build a CIService from the Typer context.

    Resolves config from CLI flags and creates the full client stack.
    Returns the CIService and GitLabClient (for cleanup).
    """
    from gltools.client.gitlab import GitLabClient
    from gltools.config.git_remote import detect_gitlab_remote
    from gltools.config.settings import GitLabConfig
    from gltools.services.ci import CIService

    ctx.ensure_object(dict)
    obj = ctx.obj

    config = GitLabConfig.from_config(
        profile=obj.get("profile"),
        cli_overrides={
            "host": obj.get("host"),
            "token": obj.get("token"),
        },
    )

    token_refresher = _make_token_refresher(config) if config.auth_type == "oauth" and config.client_id else None
    client = GitLabClient(
        host=config.host,
        token=config.token,
        auth_type=config.auth_type,
        token_refresher=token_refresher,
    )

    # Resolve project
    project: str | None = config.default_project
    if project is None:
        remote_info = detect_gitlab_remote()
        if remote_info is not None:
            project = remote_info.project_path_encoded

    if project is None:
        raise typer.BadParameter(
            "No project configured. Set 'default_project' in your config, "
            "run from a git repository with a GitLab remote, or pass --project explicitly."
        )

    service = CIService(
        project_id=project,
        pipeline_manager=client.pipelines,
        job_manager=client.jobs,
        mr_manager=client.merge_requests,
    )
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


def _output_dry_run(result: DryRunResult, ctx_obj: dict[str, Any]) -> None:
    """Output a dry-run result using the centralized formatter."""
    output_dry_run(result, ctx_obj=ctx_obj)


def _build_job_table(jobs: list[Any], *, title: str = "Jobs") -> Table:
    """Build a Rich Table for jobs grouped by stage."""
    table = Table(title=title, expand=True)
    table.add_column("ID", style="bold", no_wrap=True)
    table.add_column("Name")
    table.add_column("Stage")
    table.add_column("Status")
    table.add_column("Duration")
    table.add_column("Failure Reason")

    # Sort by stage for grouping
    sorted_jobs = sorted(jobs, key=lambda j: (getattr(j, "stage", ""), getattr(j, "name", "")))

    for job in sorted_jobs:
        job_id = str(getattr(job, "id", ""))
        name = getattr(job, "name", "")
        stage = getattr(job, "stage", "")
        status = getattr(job, "status", "")
        duration = getattr(job, "duration", None)
        duration_str = f"{duration:.1f}s" if duration is not None else "-"
        failure_reason = getattr(job, "failure_reason", None) or ""

        # Mark manual jobs
        if status == "manual":
            status_text = Text("manual", style="yellow")
            status_text.append(" (trigger to run)", style="dim")
        else:
            color = STATUS_COLORS.get(status.lower(), "white")
            status_text = Text(status, style=color)

        table.add_row(job_id, name, stage, status_text, duration_str, failure_reason)

    return table


def _build_status_table(pipeline: Any, jobs: list[Any]) -> Table:
    """Build a status table showing pipeline info and job breakdown by stage."""
    console = _create_console()

    # Pipeline summary
    console.print(f"\n[bold]Pipeline #{pipeline.id}[/bold]")
    console.print("  [bold]Status:[/bold] ", end="")
    console.print(_colored_status(pipeline.status))
    console.print(f"  [bold]Ref:[/bold] {pipeline.ref}")
    console.print(f"  [bold]SHA:[/bold] {pipeline.sha[:8]}")
    console.print(f"  [bold]Source:[/bold] {pipeline.source}")
    duration = getattr(pipeline, "duration", None)
    if duration is not None:
        console.print(f"  [bold]Duration:[/bold] {duration:.0f}s")
    console.print(f"  [bold]Created:[/bold] {str(pipeline.created_at)[:19]}")
    finished = getattr(pipeline, "finished_at", None)
    if finished:
        console.print(f"  [bold]Finished:[/bold] {str(finished)[:19]}")

    if jobs:
        console.print()
        table = _build_job_table(jobs, title="Job Breakdown")
        console.print(table)


def _handle_error(err: Exception, ctx_obj: dict[str, Any]) -> None:
    """Output an error and exit with code 1."""
    if isinstance(err, AuthenticationError):
        msg = "Authentication failed: token may be expired. Run `gltools auth login` to refresh."
        error_result = ErrorResult(error=msg, code=401)
    elif isinstance(err, ForbiddenError):
        error_result = ErrorResult(error="Permission denied. You don't have access to this resource.", code=403)
    elif isinstance(err, NotFoundError):
        error_result = ErrorResult(error=str(err), code=404)
    elif isinstance(err, GitLabConnectionError):
        error_result = ErrorResult(
            error="Unable to connect to GitLab. Check your network connection and the configured host URL."
        )
    elif isinstance(err, GitLabTimeoutError):
        error_result = ErrorResult(error="Request timed out. The server may be slow or unreachable. Try again later.")
    elif isinstance(err, (RateLimitError, ServerError)):
        error_result = ErrorResult(error=str(err))
    else:
        error_result = ErrorResult(error=str(err))
    output_error(error_result, ctx_obj=ctx_obj)
    raise typer.Exit(1)


@ci_app.command(name="status")
def status(
    ctx: typer.Context,
    mr: int | None = typer.Option(None, "--mr", help="Get pipeline from merge request IID."),
    ref: str | None = typer.Option(None, "--ref", help="Git ref (branch/tag)."),
) -> None:
    """Show pipeline status for current branch (or specified MR/branch)."""
    ctx.ensure_object(dict)
    obj = ctx.obj

    async def _run() -> None:
        from gltools.services.ci import NoPipelineError

        service, client = _build_service(ctx)
        try:
            pipeline = await service.get_status(mr_iid=mr, ref=ref)
            jobs = await service.list_jobs(pipeline.id)

            fmt = get_output_format(obj)
            if fmt == "json":
                data = pipeline.model_dump()
                data["jobs"] = [j.model_dump() for j in jobs]
                result = CommandResult(data=data)
                console = _create_console()
                console.print_json(data=None, json=format_json_success(result))
            else:
                if not is_quiet(obj):
                    _build_status_table(pipeline, jobs)
        except NoPipelineError as e:
            _handle_error(e, obj)
        except ValueError as e:
            _handle_error(e, obj)
        except GitLabClientError as e:
            _handle_error(e, obj)
        finally:
            await client.close()

    asyncio.run(_run())


@ci_app.command(name="list")
def list_pipelines(
    ctx: typer.Context,
    status_filter: str | None = typer.Option(None, "--status", help="Filter by status."),
    ref: str | None = typer.Option(None, "--ref", help="Filter by git ref."),
    source: str | None = typer.Option(None, "--source", help="Filter by pipeline source."),
    per_page: int = typer.Option(20, "--per-page", help="Items per page."),
    page: int = typer.Option(1, "--page", help="Page number."),
    all_pages: bool = typer.Option(False, "--all", help="Fetch all pages."),
) -> None:
    """List pipelines with optional filters."""
    ctx.ensure_object(dict)
    obj = ctx.obj

    async def _run() -> None:
        service, client = _build_service(ctx)
        try:
            result = await service.list_pipelines(
                status=status_filter,
                ref=ref,
                source=source,
                per_page=per_page,
                page=page,
                all_pages=all_pages,
            )
            output_paginated(result, entity_name="pipelines", ctx_obj=obj)
        except GitLabClientError as e:
            _handle_error(e, obj)
        finally:
            await client.close()

    asyncio.run(_run())


@ci_app.command(name="run")
def run_pipeline(
    ctx: typer.Context,
    ref: str | None = typer.Option(None, "--ref", help="Branch or tag to run pipeline for."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview the API call without executing."),
) -> None:
    """Trigger a new pipeline for a branch."""
    ctx.ensure_object(dict)
    obj = ctx.obj

    async def _run() -> None:
        service, client = _build_service(ctx)
        try:
            result = await service.trigger_pipeline(ref=ref, dry_run=dry_run)
            if isinstance(result, DryRunResult):
                _output_dry_run(result, obj)
            else:
                cmd_result = CommandResult(data=result)
                output_result(cmd_result, ctx_obj=obj)
        except ValueError as e:
            _handle_error(e, obj)
        except GitLabClientError as e:
            _handle_error(e, obj)
        finally:
            await client.close()

    asyncio.run(_run())


@ci_app.command(name="retry")
def retry_pipeline(
    ctx: typer.Context,
    pipeline_id: int = typer.Argument(help="Pipeline ID to retry."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview the API call without executing."),
) -> None:
    """Retry a failed pipeline."""
    ctx.ensure_object(dict)
    obj = ctx.obj

    async def _run() -> None:
        service, client = _build_service(ctx)
        try:
            result = await service.retry_pipeline(pipeline_id, dry_run=dry_run)
            if isinstance(result, DryRunResult):
                _output_dry_run(result, obj)
            else:
                cmd_result = CommandResult(data=result)
                output_result(cmd_result, ctx_obj=obj)
        except NotFoundError as e:
            _handle_error(e, obj)
        except GitLabClientError as e:
            _handle_error(e, obj)
        finally:
            await client.close()

    asyncio.run(_run())


@ci_app.command(name="cancel")
def cancel_pipeline(
    ctx: typer.Context,
    pipeline_id: int = typer.Argument(help="Pipeline ID to cancel."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview the API call without executing."),
) -> None:
    """Cancel a running pipeline."""
    ctx.ensure_object(dict)
    obj = ctx.obj

    async def _run() -> None:
        service, client = _build_service(ctx)
        try:
            result = await service.cancel_pipeline(pipeline_id, dry_run=dry_run)
            if isinstance(result, DryRunResult):
                _output_dry_run(result, obj)
            else:
                cmd_result = CommandResult(data=result)
                output_result(cmd_result, ctx_obj=obj)
        except NotFoundError as e:
            _handle_error(e, obj)
        except GitLabClientError as e:
            _handle_error(e, obj)
        finally:
            await client.close()

    asyncio.run(_run())


@ci_app.command(name="jobs")
def jobs(
    ctx: typer.Context,
    pipeline_id: int = typer.Argument(help="Pipeline ID to list jobs for."),
) -> None:
    """List jobs in a pipeline."""
    ctx.ensure_object(dict)
    obj = ctx.obj

    async def _run() -> None:
        service, client = _build_service(ctx)
        try:
            job_list = await service.list_jobs(pipeline_id)

            fmt = get_output_format(obj)
            if fmt == "json":
                result = CommandResult(data=[j.model_dump() for j in job_list])
                console = _create_console()
                console.print_json(data=None, json=format_json_success(result))
            else:
                if not is_quiet(obj):
                    if not job_list:
                        console = _create_console()
                        console.print("No jobs found for this pipeline.")
                    else:
                        console = _create_console()
                        table = _build_job_table(job_list, title=f"Jobs for Pipeline #{pipeline_id}")
                        console.print(table)
        except NotFoundError as e:
            _handle_error(e, obj)
        except GitLabClientError as e:
            _handle_error(e, obj)
        finally:
            await client.close()

    asyncio.run(_run())


@ci_app.command(name="logs")
def logs(
    ctx: typer.Context,
    job_id: int = typer.Argument(help="Job ID to retrieve logs for."),
    tail: int | None = typer.Option(None, "--tail", help="Show only the last N lines."),
) -> None:
    """Retrieve job logs (streamed)."""
    ctx.ensure_object(dict)
    obj = ctx.obj

    async def _run() -> None:
        service, client = _build_service(ctx)
        try:
            fmt = get_output_format(obj)

            if fmt == "json":
                # Collect all log output for JSON mode
                log_lines: list[str] = []
                async for chunk in service.get_logs(job_id, tail=tail):
                    log_lines.append(chunk)

                log_text = "".join(log_lines)
                result = CommandResult(data={"job_id": job_id, "log": log_text})
                console = _create_console()
                console.print_json(data=None, json=format_json_success(result))
            else:
                # Stream output directly to stdout
                async for chunk in service.get_logs(job_id, tail=tail):
                    sys.stdout.write(chunk)
                    sys.stdout.flush()

        except NotFoundError as e:
            _handle_error(e, obj)
        except GitLabClientError as e:
            _handle_error(e, obj)
        finally:
            await client.close()

    asyncio.run(_run())


@ci_app.command(name="artifacts")
def artifacts(
    ctx: typer.Context,
    job_id: int = typer.Argument(help="Job ID to download artifacts for."),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path."),
) -> None:
    """Download job artifacts."""
    ctx.ensure_object(dict)
    obj = ctx.obj

    async def _run() -> None:
        service, client = _build_service(ctx)
        try:
            result = await service.download_artifacts(job_id, output_path=output)

            if isinstance(result, Path):
                fmt = get_output_format(obj)
                if fmt == "json":
                    cmd_result = CommandResult(
                        data={"job_id": job_id, "output_path": str(result), "size_bytes": result.stat().st_size}
                    )
                    console = _create_console()
                    console.print_json(data=None, json=format_json_success(cmd_result))
                else:
                    if not is_quiet(obj):
                        console = _create_console()
                        console.print(f"Artifacts saved to [bold]{result}[/bold] ({result.stat().st_size} bytes)")
            else:
                # Write raw bytes to stdout
                sys.stdout.buffer.write(result)
                sys.stdout.buffer.flush()

        except NotFoundError as e:
            _handle_error(e, obj)
        except GitLabClientError as e:
            _handle_error(e, obj)
        finally:
            await client.close()

    asyncio.run(_run())
