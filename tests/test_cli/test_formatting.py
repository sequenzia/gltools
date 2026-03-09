"""Tests for the output formatting module."""

import json
from io import StringIO
from unittest.mock import patch

from pydantic import BaseModel
from rich.console import Console

from gltools.cli.formatting import (
    DEFAULT_TRUNCATE_LENGTH,
    _colored_status,
    _create_console,
    _safe_serialize,
    _truncate,
    build_list_table,
    format_detail_text,
    format_json_error,
    format_json_paginated,
    format_json_success,
    format_text_empty,
    get_output_format,
    is_quiet,
    output_dry_run,
    output_error,
    output_paginated,
    output_result,
)
from gltools.models.output import CommandResult, DryRunResult, ErrorResult, PaginatedResponse

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class FakeMergeRequest(BaseModel):
    """Minimal MR-like model for testing."""

    iid: int
    title: str
    description: str | None = None
    state: str = "opened"
    source_branch: str = "feature"
    target_branch: str = "main"
    author: dict = {"name": "Alice", "username": "alice"}
    updated_at: str = "2026-01-15T10:00:00Z"


class FakeIssue(BaseModel):
    """Minimal Issue-like model for testing."""

    iid: int
    title: str
    description: str | None = None
    state: str = "opened"
    milestone: dict | None = None
    author: dict = {"name": "Bob", "username": "bob"}
    labels: list[str] = []
    updated_at: str = "2026-01-15T10:00:00Z"


class FakePipeline(BaseModel):
    """Minimal Pipeline-like model for testing."""

    id: int
    status: str = "success"
    ref: str = "main"
    sha: str = "abc123def456"
    source: str = "push"
    duration: float | None = 120.5
    created_at: str = "2026-01-15T10:00:00Z"


def _capture_console_output(func, *args, **kwargs) -> str:
    """Capture Rich console output by temporarily redirecting stdout."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    with patch("gltools.cli.formatting._create_console", return_value=console):
        func(*args, **kwargs)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# get_output_format
# ---------------------------------------------------------------------------


class TestGetOutputFormat:
    def test_json_from_cli_flags(self) -> None:
        assert get_output_format({"output_format": "json"}) == "json"

    def test_text_from_cli_flags(self) -> None:
        assert get_output_format({"output_format": "text"}) == "text"

    def test_fallback_to_config(self) -> None:
        assert get_output_format({}, config_format="json") == "json"

    def test_default_to_text(self) -> None:
        assert get_output_format() == "text"
        assert get_output_format({}) == "text"

    def test_cli_overrides_config(self) -> None:
        assert get_output_format({"output_format": "json"}, config_format="text") == "json"


# ---------------------------------------------------------------------------
# is_quiet
# ---------------------------------------------------------------------------


class TestIsQuiet:
    def test_quiet_true(self) -> None:
        assert is_quiet({"quiet": True}) is True

    def test_quiet_false(self) -> None:
        assert is_quiet({"quiet": False}) is False

    def test_quiet_missing(self) -> None:
        assert is_quiet({}) is False
        assert is_quiet(None) is False


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_string_unchanged(self) -> None:
        assert _truncate("hello", 10) == "hello"

    def test_exact_length_unchanged(self) -> None:
        text = "a" * DEFAULT_TRUNCATE_LENGTH
        assert _truncate(text) == text

    def test_long_string_truncated(self) -> None:
        text = "a" * 100
        result = _truncate(text, 20)
        assert len(result) == 20
        assert result.endswith("...")

    def test_none_returns_empty(self) -> None:
        assert _truncate(None) == ""


# ---------------------------------------------------------------------------
# _colored_status
# ---------------------------------------------------------------------------


class TestColoredStatus:
    def test_success_is_green(self) -> None:
        text = _colored_status("success")
        assert "green" in str(text.style)

    def test_merged_is_green(self) -> None:
        text = _colored_status("merged")
        assert "green" in str(text.style)

    def test_failed_is_red(self) -> None:
        text = _colored_status("failed")
        assert "red" in str(text.style)

    def test_running_is_yellow(self) -> None:
        text = _colored_status("running")
        assert "yellow" in str(text.style)

    def test_pending_is_yellow(self) -> None:
        text = _colored_status("pending")
        assert "yellow" in str(text.style)

    def test_closed_is_red(self) -> None:
        text = _colored_status("closed")
        assert "red" in str(text.style)

    def test_unknown_status_white(self) -> None:
        text = _colored_status("something_unknown")
        assert "white" in str(text.style)


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


class TestJsonSerialization:
    def test_command_result_json_valid(self) -> None:
        result = CommandResult(status="success", data={"key": "value"})
        output = format_json_success(result)
        parsed = json.loads(output)
        assert parsed["status"] == "success"
        assert parsed["data"] == {"key": "value"}

    def test_command_result_json_has_status_field(self) -> None:
        result = CommandResult()
        parsed = json.loads(format_json_success(result))
        assert "status" in parsed
        assert parsed["status"] == "success"

    def test_error_result_json_valid(self) -> None:
        error = ErrorResult(error="Something went wrong", code=404)
        output = format_json_error(error)
        parsed = json.loads(output)
        assert parsed["status"] == "error"
        assert parsed["error"] == "Something went wrong"
        assert parsed["code"] == 404

    def test_paginated_response_json_valid(self) -> None:
        response = PaginatedResponse(items=[1, 2, 3], page=1, per_page=20, total=3)
        output = format_json_paginated(response)
        parsed = json.loads(output)
        assert parsed["items"] == [1, 2, 3]
        assert parsed["page"] == 1
        assert parsed["total"] == 3

    def test_empty_paginated_response_json(self) -> None:
        response = PaginatedResponse(items=[], page=1, per_page=20, total=0)
        output = format_json_paginated(response)
        parsed = json.loads(output)
        assert parsed["items"] == []

    def test_safe_serialize_fallback(self) -> None:
        """Non-serializable object falls back to str()."""

        class Unserializable:
            def __repr__(self) -> str:
                return "<Unserializable>"

        result = _safe_serialize(Unserializable())
        assert "Unserializable" in result


# ---------------------------------------------------------------------------
# Text output - empty lists
# ---------------------------------------------------------------------------


class TestTextEmpty:
    def test_empty_default_message(self) -> None:
        assert format_text_empty() == "No items found."

    def test_empty_custom_entity(self) -> None:
        assert format_text_empty("merge requests") == "No merge requests found."


# ---------------------------------------------------------------------------
# Table building
# ---------------------------------------------------------------------------


class TestBuildListTable:
    def test_mr_table_columns(self) -> None:
        items = [FakeMergeRequest(iid=1, title="Fix bug")]
        table = build_list_table(items)
        col_names = [c.header for c in table.columns]
        assert "IID" in col_names
        assert "Title" in col_names
        assert "State" in col_names

    def test_issue_table_columns(self) -> None:
        items = [FakeIssue(iid=1, title="Feature request")]
        table = build_list_table(items)
        col_names = [c.header for c in table.columns]
        assert "IID" in col_names
        assert "Labels" in col_names

    def test_pipeline_table_columns(self) -> None:
        items = [FakePipeline(id=100)]
        table = build_list_table(items)
        col_names = [c.header for c in table.columns]
        assert "ID" in col_names
        assert "Status" in col_names
        assert "Ref" in col_names

    def test_long_title_truncated_in_table(self) -> None:
        long_title = "A" * 200
        items = [FakeMergeRequest(iid=1, title=long_title)]
        table = build_list_table(items)
        # The table was built successfully; verify the row data is truncated
        # by checking the renderable cells
        # Column index 1 is "Title"
        cell_text = str(table.columns[1]._cells[0])
        assert len(cell_text) <= 63  # 60 + "..."

    def test_generic_table_for_unknown_type(self) -> None:
        class CustomItem(BaseModel):
            name: str
            value: int

        items = [CustomItem(name="test", value=42)]
        table = build_list_table(items)
        assert len(table.columns) > 0


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------


class TestDetailView:
    def test_detail_prints_description_as_markdown(self) -> None:
        mr = FakeMergeRequest(iid=1, title="Test MR", description="# Heading\n\nSome *bold* text")
        output = _capture_console_output(format_detail_text, mr)
        assert "Heading" in output
        assert "Description" in output

    def test_detail_full_description_not_truncated(self) -> None:
        long_desc = "A" * 500
        mr = FakeMergeRequest(iid=1, title="Test MR", description=long_desc)
        output = _capture_console_output(format_detail_text, mr)
        # Full description should be present (not truncated)
        assert "A" * 100 in output


# ---------------------------------------------------------------------------
# output_result
# ---------------------------------------------------------------------------


class TestOutputResult:
    def test_json_mode_outputs_valid_json(self) -> None:
        result = CommandResult(status="success", data={"id": 1})
        output = _capture_console_output(output_result, result, ctx_obj={"output_format": "json", "quiet": False})
        parsed = json.loads(output.strip())
        assert parsed["status"] == "success"

    def test_text_mode_empty_list(self) -> None:
        result = CommandResult(status="success", data=[])
        output = _capture_console_output(output_result, result, ctx_obj={"output_format": "text", "quiet": False})
        assert "No items found" in output

    def test_quiet_suppresses_output(self) -> None:
        result = CommandResult(status="success", data={"id": 1})
        output = _capture_console_output(output_result, result, ctx_obj={"output_format": "text", "quiet": True})
        assert output == ""

    def test_text_mode_success_no_data(self) -> None:
        result = CommandResult(status="success")
        output = _capture_console_output(output_result, result, ctx_obj={"output_format": "text", "quiet": False})
        assert "Success" in output


# ---------------------------------------------------------------------------
# output_paginated
# ---------------------------------------------------------------------------


class TestOutputPaginated:
    def test_json_mode_valid_json(self) -> None:
        response = PaginatedResponse(items=[1, 2], page=1, per_page=20, total=2)
        output = _capture_console_output(output_paginated, response, ctx_obj={"output_format": "json", "quiet": False})
        parsed = json.loads(output.strip())
        assert parsed["items"] == [1, 2]

    def test_text_mode_empty_list(self) -> None:
        response = PaginatedResponse(items=[], page=1, per_page=20, total=0)
        output = _capture_console_output(
            output_paginated,
            response,
            entity_name="merge requests",
            ctx_obj={"output_format": "text", "quiet": False},
        )
        assert "No merge requests found" in output

    def test_quiet_suppresses_output(self) -> None:
        response = PaginatedResponse(items=[1], page=1, per_page=20, total=1)
        output = _capture_console_output(output_paginated, response, ctx_obj={"output_format": "text", "quiet": True})
        assert output == ""


# ---------------------------------------------------------------------------
# output_error
# ---------------------------------------------------------------------------


class TestOutputError:
    def test_json_error_to_stderr(self) -> None:
        error = ErrorResult(error="Not found", code=404)
        # For error output, we need to capture stderr
        buf = StringIO()
        stderr_console = Console(file=buf, force_terminal=False, width=200)
        with patch("gltools.cli.formatting._create_console", return_value=stderr_console):
            output_error(error, ctx_obj={"output_format": "json", "quiet": False})
        output = buf.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["status"] == "error"
        assert parsed["error"] == "Not found"

    def test_text_error_to_stderr(self) -> None:
        error = ErrorResult(error="Something failed", code=500, details={"trace": "line 42"})
        buf = StringIO()
        stderr_console = Console(file=buf, force_terminal=False, width=200)
        with patch("gltools.cli.formatting._create_console", return_value=stderr_console):
            output_error(error, ctx_obj={"output_format": "text", "quiet": False})
        output = buf.getvalue()
        assert "Something failed" in output
        assert "500" in output

    def test_error_not_suppressed_by_quiet(self) -> None:
        """Errors always display, even with --quiet."""
        error = ErrorResult(error="Critical failure")
        buf = StringIO()
        stderr_console = Console(file=buf, force_terminal=False, width=200)
        with patch("gltools.cli.formatting._create_console", return_value=stderr_console):
            output_error(error, ctx_obj={"output_format": "text", "quiet": True})
        output = buf.getvalue()
        assert "Critical failure" in output


# ---------------------------------------------------------------------------
# output_dry_run
# ---------------------------------------------------------------------------


class TestOutputDryRun:
    def test_text_mode_shows_dry_run_banner(self) -> None:
        result = DryRunResult(
            method="POST",
            url="/projects/test%2Fproject/merge_requests",
            body={"title": "Test MR", "source_branch": "feat", "target_branch": "main"},
        )
        output = _capture_console_output(output_dry_run, result, ctx_obj={"output_format": "text"})
        assert "DRY RUN" in output
        assert "POST" in output
        assert "/projects/test%2Fproject/merge_requests" in output
        assert "Test MR" in output

    def test_text_mode_no_body(self) -> None:
        result = DryRunResult(
            method="POST",
            url="/projects/42/pipelines/100/retry",
        )
        output = _capture_console_output(output_dry_run, result, ctx_obj={"output_format": "text"})
        assert "DRY RUN" in output
        assert "POST" in output
        assert "Body" not in output

    def test_json_mode_outputs_structured_result(self) -> None:
        result = DryRunResult(
            method="PUT",
            url="/projects/42/merge_requests/10",
            body={"title": "Updated"},
        )
        output = _capture_console_output(output_dry_run, result, ctx_obj={"output_format": "json"})
        parsed = json.loads(output.strip())
        assert parsed["dry_run"] is True
        assert parsed["method"] == "PUT"
        assert parsed["url"] == "/projects/42/merge_requests/10"
        assert parsed["body"] == {"title": "Updated"}

    def test_json_mode_no_body(self) -> None:
        result = DryRunResult(
            method="POST",
            url="/projects/42/merge_requests/10/approve",
        )
        output = _capture_console_output(output_dry_run, result, ctx_obj={"output_format": "json"})
        parsed = json.loads(output.strip())
        assert parsed["dry_run"] is True
        assert parsed["method"] == "POST"
        assert parsed["body"] is None

    def test_text_mode_shows_end_banner(self) -> None:
        result = DryRunResult(method="PUT", url="/test")
        output = _capture_console_output(output_dry_run, result, ctx_obj={"output_format": "text"})
        assert "END DRY RUN" in output


# ---------------------------------------------------------------------------
# Non-TTY behavior
# ---------------------------------------------------------------------------


class TestNonTTY:
    def test_console_respects_non_tty(self) -> None:
        """When force_terminal is None, Rich auto-detects TTY and disables colors for non-TTY."""
        console = _create_console()
        # In test environment, stdout is not a real TTY
        # Console should not force terminal mode
        assert console._force_terminal is None  # noqa: SLF001
