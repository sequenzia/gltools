"""Output formatting layer supporting JSON and human-readable text modes."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from gltools.models.output import CommandResult, DryRunResult, ErrorResult, PaginatedResponse

# Status color mapping
STATUS_COLORS: dict[str, str] = {
    # Success / merged / passed
    "success": "green",
    "merged": "green",
    "passed": "green",
    "closed": "red",
    # Pending / running / warning
    "pending": "yellow",
    "running": "yellow",
    "opened": "yellow",
    "created": "yellow",
    "waiting_for_resource": "yellow",
    "preparing": "yellow",
    "manual": "yellow",
    "scheduled": "yellow",
    # Failed / error
    "failed": "red",
    "error": "red",
    "canceled": "red",
    "skipped": "dim",
}

# Default max width for truncated fields in table views
DEFAULT_TRUNCATE_LENGTH = 80


def get_output_format(ctx_obj: dict[str, Any] | None = None, config_format: str | None = None) -> str:
    """Determine the output format from CLI flags, config, or default.

    Priority:
    1. --json / --text CLI flags (stored in ctx.obj["output_format"])
    2. Config output_format setting
    3. Default to "text"
    """
    if ctx_obj and ctx_obj.get("output_format"):
        return ctx_obj["output_format"]
    if config_format:
        return config_format
    return "text"


def is_quiet(ctx_obj: dict[str, Any] | None = None) -> bool:
    """Check if --quiet flag is set."""
    if ctx_obj:
        return bool(ctx_obj.get("quiet", False))
    return False


def _create_console(*, stderr: bool = False) -> Console:
    """Create a Rich Console that auto-detects TTY for color support."""
    file = sys.stderr if stderr else sys.stdout
    return Console(file=file, force_terminal=None)


def _safe_serialize(obj: Any) -> str:
    """Safely serialize an object to JSON string, with str() fallback."""
    if isinstance(obj, BaseModel):
        try:
            return obj.model_dump_json(indent=2)
        except Exception:
            try:
                return json.dumps(obj.model_dump(), indent=2, default=str)
            except Exception:
                return str(obj)
    try:
        return json.dumps(obj, indent=2, default=str)
    except Exception:
        return str(obj)


def _colored_status(status: str) -> Text:
    """Return a Rich Text with color based on status value."""
    color = STATUS_COLORS.get(status.lower(), "white")
    return Text(status, style=color)


def _truncate(text: str | None, max_length: int = DEFAULT_TRUNCATE_LENGTH) -> str:
    """Truncate a string to max_length, appending ellipsis if needed."""
    if text is None:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


# ---------------------------------------------------------------------------
# JSON output helpers
# ---------------------------------------------------------------------------


def format_json_success(result: CommandResult) -> str:
    """Serialize a CommandResult to JSON."""
    return _safe_serialize(result)


def format_json_error(error: ErrorResult) -> str:
    """Serialize an ErrorResult to JSON."""
    return _safe_serialize(error)


def format_json_paginated(response: PaginatedResponse[Any]) -> str:
    """Serialize a PaginatedResponse to JSON."""
    return _safe_serialize(response)


# ---------------------------------------------------------------------------
# Text output helpers
# ---------------------------------------------------------------------------


def format_text_empty(entity_name: str = "items") -> str:
    """Return a user-friendly message for an empty list."""
    return f"No {entity_name} found."


def _build_mr_table(items: list[Any]) -> Table:
    """Build a Rich Table for merge request list views."""
    table = Table(title="Merge Requests", expand=True)
    table.add_column("IID", style="bold", no_wrap=True)
    table.add_column("Title")
    table.add_column("Author")
    table.add_column("State")
    table.add_column("Source → Target", no_wrap=True)
    table.add_column("Updated")

    for item in items:
        iid = str(getattr(item, "iid", ""))
        title = _truncate(getattr(item, "title", ""), 60)
        author = getattr(getattr(item, "author", None), "name", "") or getattr(
            getattr(item, "author", None), "username", ""
        )
        state = getattr(item, "state", "")
        source = getattr(item, "source_branch", "")
        target = getattr(item, "target_branch", "")
        branch_info = f"{source} → {target}" if source and target else ""
        updated = str(getattr(item, "updated_at", ""))[:10]  # date only

        table.add_row(iid, title, str(author), _colored_status(state), branch_info, updated)

    return table


def _build_issue_table(items: list[Any]) -> Table:
    """Build a Rich Table for issue list views."""
    table = Table(title="Issues", expand=True)
    table.add_column("IID", style="bold", no_wrap=True)
    table.add_column("Title")
    table.add_column("Author")
    table.add_column("State")
    table.add_column("Labels")
    table.add_column("Updated")

    for item in items:
        iid = str(getattr(item, "iid", ""))
        title = _truncate(getattr(item, "title", ""), 60)
        author = getattr(getattr(item, "author", None), "name", "") or getattr(
            getattr(item, "author", None), "username", ""
        )
        state = getattr(item, "state", "")
        labels = ", ".join(getattr(item, "labels", [])[:3])
        if len(getattr(item, "labels", [])) > 3:
            labels += "..."
        updated = str(getattr(item, "updated_at", ""))[:10]

        table.add_row(iid, title, str(author), _colored_status(state), labels, updated)

    return table


def _build_pipeline_table(items: list[Any]) -> Table:
    """Build a Rich Table for pipeline list views."""
    table = Table(title="Pipelines", expand=True)
    table.add_column("ID", style="bold", no_wrap=True)
    table.add_column("Status")
    table.add_column("Ref")
    table.add_column("SHA", no_wrap=True)
    table.add_column("Source")
    table.add_column("Duration")
    table.add_column("Created")

    for item in items:
        pid = str(getattr(item, "id", ""))
        status = getattr(item, "status", "")
        ref = _truncate(getattr(item, "ref", ""), 30)
        sha = str(getattr(item, "sha", ""))[:8]
        source = getattr(item, "source", "")
        duration = getattr(item, "duration", None)
        duration_str = f"{duration:.0f}s" if duration is not None else "-"
        created = str(getattr(item, "created_at", ""))[:10]

        table.add_row(pid, _colored_status(status), ref, sha, source, duration_str, created)

    return table


def _detect_item_type(items: list[Any]) -> str:
    """Detect the type of items in a list for table selection."""
    if not items:
        return "unknown"
    first = items[0]
    type_name = type(first).__name__.lower()
    if "mergerequest" in type_name or "mr" in type_name:
        return "mr"
    if "issue" in type_name:
        return "issue"
    if "pipeline" in type_name:
        return "pipeline"
    # Fallback: check for distinctive attributes
    if hasattr(first, "source_branch"):
        return "mr"
    if hasattr(first, "milestone"):
        return "issue"
    if hasattr(first, "sha") and hasattr(first, "ref"):
        return "pipeline"
    return "unknown"


def _build_generic_table(items: list[Any]) -> Table:
    """Build a generic table for unknown item types."""
    table = Table(expand=True)
    if not items:
        return table

    first = items[0]
    if isinstance(first, BaseModel):
        fields = list(type(first).model_fields.keys())[:6]
    elif isinstance(first, dict):
        fields = list(first.keys())[:6]
    else:
        fields = ["value"]

    for field in fields:
        table.add_column(field.replace("_", " ").title())

    for item in items:
        row: list[str] = []
        for field in fields:
            val = item.get(field, "") if isinstance(item, dict) else getattr(item, field, "")
            row.append(_truncate(str(val), 40))
        table.add_row(*row)

    return table


def build_list_table(items: list[Any]) -> Table:
    """Build the appropriate Rich Table based on the item type."""
    item_type = _detect_item_type(items)
    if item_type == "mr":
        return _build_mr_table(items)
    if item_type == "issue":
        return _build_issue_table(items)
    if item_type == "pipeline":
        return _build_pipeline_table(items)
    return _build_generic_table(items)


def format_detail_text(item: Any) -> None:
    """Print a detailed view of a single item to stdout using Rich.

    Renders full descriptions as Markdown instead of truncating.
    """
    console = _create_console()

    if isinstance(item, BaseModel):
        data = item.model_dump()
    elif isinstance(item, dict):
        data = item
    else:
        console.print(str(item))
        return

    for key, value in data.items():
        label = key.replace("_", " ").title()
        if key == "description" and value:
            console.print(f"\n[bold]{label}:[/bold]")
            console.print(Markdown(str(value)))
        elif key == "state" or key == "status":
            console.print(f"[bold]{label}:[/bold] ", end="")
            console.print(_colored_status(str(value or "")))
        elif isinstance(value, BaseModel):
            display = getattr(value, "title", None) or getattr(value, "name", None) or str(value)
            console.print(f"[bold]{label}:[/bold] {display}")
        elif isinstance(value, dict):
            display = value.get("title") or value.get("name") or str(value)
            console.print(f"[bold]{label}:[/bold] {display}")
        else:
            display = str(value) if value is not None else "-"
            console.print(f"[bold]{label}:[/bold] {display}")


# ---------------------------------------------------------------------------
# Main output functions
# ---------------------------------------------------------------------------


def output_result(
    result: CommandResult,
    *,
    ctx_obj: dict[str, Any] | None = None,
    config_format: str | None = None,
) -> None:
    """Output a CommandResult in the appropriate format.

    Routes to JSON or text mode based on CLI flags / config.
    Respects --quiet flag (suppresses non-error output).
    """
    if is_quiet(ctx_obj):
        return

    fmt = get_output_format(ctx_obj, config_format)

    if fmt == "json":
        console = _create_console()
        console.print_json(data=None, json=format_json_success(result))
    else:
        # Text mode: if data is a list, show table; if single item, show detail
        data = result.data
        if isinstance(data, list):
            if not data:
                console = _create_console()
                console.print(format_text_empty())
            else:
                console = _create_console()
                table = build_list_table(data)
                console.print(table)
        elif data is not None:
            format_detail_text(data)
        else:
            console = _create_console()
            console.print("[green]Success[/green]")


def output_dry_run(
    result: DryRunResult,
    *,
    ctx_obj: dict[str, Any] | None = None,
    config_format: str | None = None,
) -> None:
    """Output a DryRunResult in the appropriate format.

    JSON mode: prints the structured DryRunResult as JSON.
    Text mode: prints a "DRY RUN" banner with method, URL, and body preview.
    Always exits with code 0 (no error).
    """
    fmt = get_output_format(ctx_obj, config_format)
    console = _create_console()

    if fmt == "json":
        console.print_json(data=None, json=_safe_serialize(result))
    else:
        console.print("[bold yellow]--- DRY RUN ---[/bold yellow]")
        console.print(f"[bold]Method:[/bold] {result.method}")
        console.print(f"[bold]URL:[/bold]    {result.url}")
        if result.body:
            console.print("[bold]Body:[/bold]")
            body_json = json.dumps(result.body, indent=2, default=str)
            for line in body_json.splitlines():
                console.print(f"  {line}")
        console.print("[bold yellow]--- END DRY RUN ---[/bold yellow]")


def output_paginated(
    response: PaginatedResponse[Any],
    *,
    entity_name: str = "items",
    ctx_obj: dict[str, Any] | None = None,
    config_format: str | None = None,
) -> None:
    """Output a PaginatedResponse in the appropriate format.

    Routes to JSON or text mode based on CLI flags / config.
    Respects --quiet flag.
    """
    if is_quiet(ctx_obj):
        return

    fmt = get_output_format(ctx_obj, config_format)

    if fmt == "json":
        console = _create_console()
        console.print_json(data=None, json=format_json_paginated(response))
    else:
        items = response.items
        if not items:
            console = _create_console()
            console.print(format_text_empty(entity_name))
        else:
            console = _create_console()
            table = build_list_table(items)
            console.print(table)
            if response.total is not None:
                console.print(
                    f"\nShowing page {response.page} of {response.total_pages or '?'}"
                    f" ({response.total} total {entity_name})"
                )


def output_error(
    error: ErrorResult,
    *,
    ctx_obj: dict[str, Any] | None = None,
    config_format: str | None = None,
) -> None:
    """Output an ErrorResult in the appropriate format.

    Always outputs to stderr. Not affected by --quiet flag
    (errors always display).
    """
    fmt = get_output_format(ctx_obj, config_format)
    console = _create_console(stderr=True)

    if fmt == "json":
        console.print_json(data=None, json=format_json_error(error))
    else:
        console.print(f"[bold red]Error:[/bold red] {error.error}")
        if error.code:
            console.print(f"[dim]Code: {error.code}[/dim]")
        if error.details:
            for key, value in error.details.items():
                console.print(f"[dim]  {key}: {value}[/dim]")
