"""Tests for MR CLI commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from gltools.cli.app import app
from gltools.models import DiffFile, MergeRequest, Note, PaginatedResponse
from gltools.models.output import DryRunResult
from gltools.models.user import UserRef

runner = CliRunner()

# Common test fixtures
_AUTHOR = UserRef(id=1, username="testuser", name="Test User")
_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

_SAMPLE_MR = MergeRequest(
    id=100,
    iid=42,
    title="Fix login bug",
    description="Fixes the login timeout issue",
    state="opened",
    source_branch="fix-login",
    target_branch="main",
    author=_AUTHOR,
    labels=["bug"],
    created_at=_NOW,
    updated_at=_NOW,
)

_MERGED_MR = MergeRequest(
    id=101,
    iid=43,
    title="Already merged",
    state="merged",
    source_branch="feature-x",
    target_branch="main",
    author=_AUTHOR,
    created_at=_NOW,
    updated_at=_NOW,
    merged_at=_NOW,
)


def _mock_service(method_name: str, return_value: object) -> AsyncMock:
    """Create a mock MergeRequestService with a single mocked method."""
    mock = AsyncMock()
    getattr(mock, method_name).return_value = return_value
    return mock


def _patch_build_service(mock_service: AsyncMock) -> object:
    """Patch _build_service to return the mock service and a mock client."""
    mock_client = AsyncMock()

    async def _fake_build(ctx, project=None):
        return mock_service, mock_client

    return patch("gltools.cli.mr._build_service", side_effect=_fake_build)


class TestMRList:
    """Tests for `gltools mr list`."""

    def test_list_text_output(self) -> None:
        service = _mock_service(
            "list_mrs",
            PaginatedResponse[MergeRequest](
                items=[_SAMPLE_MR],
                page=1,
                per_page=20,
                total=1,
                total_pages=1,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "list"])

        assert result.exit_code == 0
        assert "42" in result.output
        assert "Fix login bug" in result.output

    def test_list_json_output(self) -> None:
        service = _mock_service(
            "list_mrs",
            PaginatedResponse[MergeRequest](
                items=[_SAMPLE_MR],
                page=1,
                per_page=20,
                total=1,
                total_pages=1,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["items"][0]["iid"] == 42

    def test_list_empty(self) -> None:
        service = _mock_service(
            "list_mrs",
            PaginatedResponse[MergeRequest](
                items=[],
                page=1,
                per_page=20,
                total=0,
                total_pages=0,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "list"])

        assert result.exit_code == 0
        assert "No merge requests found" in result.output

    def test_list_with_filters(self) -> None:
        service = _mock_service(
            "list_mrs",
            PaginatedResponse[MergeRequest](
                items=[],
                page=1,
                per_page=10,
                total=0,
                total_pages=0,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["mr", "list", "--state", "merged", "--per-page", "10", "--author", "someone"],
            )

        assert result.exit_code == 0
        service.list_mrs.assert_called_once_with(
            state="merged",
            labels=None,
            author="someone",
            scope=None,
            search=None,
            per_page=10,
            page=1,
            all_pages=False,
        )


class TestMRCreate:
    """Tests for `gltools mr create`."""

    def test_create_with_current_branch(self) -> None:
        service = _mock_service("create_mr", _SAMPLE_MR)
        with (
            _patch_build_service(service),
            patch("gltools.cli.mr._get_current_branch", return_value="fix-login"),
        ):
            result = runner.invoke(
                app,
                ["mr", "create", "--title", "Fix login bug"],
            )

        assert result.exit_code == 0
        service.create_mr.assert_called_once()
        call_kwargs = service.create_mr.call_args.kwargs
        assert call_kwargs["source_branch"] == "fix-login"

    def test_create_explicit_source(self) -> None:
        service = _mock_service("create_mr", _SAMPLE_MR)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["mr", "create", "--title", "Test", "--source", "my-branch", "--target", "develop"],
            )

        assert result.exit_code == 0
        call_kwargs = service.create_mr.call_args.kwargs
        assert call_kwargs["source_branch"] == "my-branch"
        assert call_kwargs["target_branch"] == "develop"

    def test_create_no_branch_detected(self) -> None:
        with patch("gltools.cli.mr._get_current_branch", return_value=None):
            result = runner.invoke(
                app,
                ["mr", "create", "--title", "Test"],
            )

        assert result.exit_code == 1
        assert "Could not detect current branch" in result.output

    def test_create_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="POST",
            url="/projects/test%2Fproject/merge_requests",
            body={"title": "Test", "source_branch": "feat", "target_branch": "main"},
        )
        service = _mock_service("create_mr", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["mr", "create", "--title", "Test", "--source", "feat", "--dry-run"],
            )

        assert result.exit_code == 0
        service.create_mr.assert_called_once()
        assert service.create_mr.call_args.kwargs["dry_run"] is True

    def test_create_json_output(self) -> None:
        service = _mock_service("create_mr", _SAMPLE_MR)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["--json", "mr", "create", "--title", "Test", "--source", "feat"],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["iid"] == 42


class TestMRView:
    """Tests for `gltools mr view`."""

    def test_view_text_output(self) -> None:
        service = _mock_service("get_mr", _SAMPLE_MR)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "view", "42"])

        assert result.exit_code == 0
        assert "Fix login bug" in result.output

    def test_view_json_output(self) -> None:
        service = _mock_service("get_mr", _SAMPLE_MR)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "view", "42"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["iid"] == 42

    def test_view_not_found(self) -> None:
        from gltools.client.exceptions import NotFoundError

        service = AsyncMock()
        service.get_mr = AsyncMock(side_effect=NotFoundError("merge request", "/projects/1/merge_requests/999"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "view", "999"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestMRMerge:
    """Tests for `gltools mr merge`."""

    def test_merge_success(self) -> None:
        merged = _SAMPLE_MR.model_copy(update={"state": "merged"})
        service = AsyncMock()
        service.get_mr = AsyncMock(return_value=_SAMPLE_MR)  # opened state
        service.merge_mr = AsyncMock(return_value=merged)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "merge", "42"])

        assert result.exit_code == 0

    def test_merge_already_merged(self) -> None:
        service = AsyncMock()
        service.get_mr = AsyncMock(return_value=_MERGED_MR)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "merge", "43"])

        assert result.exit_code == 1
        assert "already merged" in result.output.lower()

    def test_merge_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="PUT",
            url="/projects/test%2Fproject/merge_requests/42/merge",
        )
        service = _mock_service("merge_mr", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "merge", "42", "--dry-run"])

        assert result.exit_code == 0
        service.merge_mr.assert_called_once()


class TestMRApprove:
    """Tests for `gltools mr approve`."""

    def test_approve_success(self) -> None:
        service = _mock_service("approve_mr", None)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "approve", "42"])

        assert result.exit_code == 0

    def test_approve_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="POST",
            url="/projects/test%2Fproject/merge_requests/42/approve",
        )
        service = _mock_service("approve_mr", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "approve", "42", "--dry-run"])

        assert result.exit_code == 0


class TestMRDiff:
    """Tests for `gltools mr diff`."""

    def test_diff_text_output(self) -> None:
        diffs = [
            DiffFile(
                old_path="README.md",
                new_path="README.md",
                diff="@@ -1,3 +1,4 @@\n # Project\n+New line\n rest",
                new_file=False,
                renamed_file=False,
                deleted_file=False,
            ),
        ]
        service = _mock_service("get_diff", diffs)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "diff", "42"])

        assert result.exit_code == 0
        assert "README.md" in result.output

    def test_diff_json_output(self) -> None:
        diffs = [
            DiffFile(
                old_path="README.md",
                new_path="README.md",
                diff="@@ -1 +1 @@\n-old\n+new",
                new_file=False,
                renamed_file=False,
                deleted_file=False,
            ),
        ]
        service = _mock_service("get_diff", diffs)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "diff", "42"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"][0]["new_path"] == "README.md"

    def test_diff_empty(self) -> None:
        service = _mock_service("get_diff", [])
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "diff", "42"])

        assert result.exit_code == 0
        assert "No changes" in result.output


class TestMRNote:
    """Tests for `gltools mr note`."""

    def test_note_success(self) -> None:
        note = Note(
            id=1,
            body="Looks good!",
            author=_AUTHOR,
            created_at=_NOW,
            updated_at=_NOW,
            system=False,
        )
        service = _mock_service("add_note", note)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "note", "42", "--body", "Looks good!"])

        assert result.exit_code == 0

    def test_note_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="POST",
            url="/projects/test%2Fproject/merge_requests/42/notes",
            body={"body": "Test note"},
        )
        service = _mock_service("add_note", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "note", "42", "--body", "Test note", "--dry-run"])

        assert result.exit_code == 0


class TestMRClose:
    """Tests for `gltools mr close`."""

    def test_close_success(self) -> None:
        closed = _SAMPLE_MR.model_copy(update={"state": "closed"})
        service = _mock_service("close_mr", closed)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "close", "42"])

        assert result.exit_code == 0

    def test_close_not_found(self) -> None:
        from gltools.client.exceptions import NotFoundError

        service = AsyncMock()
        service.close_mr = AsyncMock(side_effect=NotFoundError("merge request"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "close", "999"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestMRReopen:
    """Tests for `gltools mr reopen`."""

    def test_reopen_success(self) -> None:
        reopened = _SAMPLE_MR.model_copy(update={"state": "opened"})
        service = _mock_service("reopen_mr", reopened)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "reopen", "42"])

        assert result.exit_code == 0


class TestMRUpdate:
    """Tests for `gltools mr update`."""

    def test_update_title(self) -> None:
        updated = _SAMPLE_MR.model_copy(update={"title": "New title"})
        service = _mock_service("update_mr", updated)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "update", "42", "--title", "New title"])

        assert result.exit_code == 0
        service.update_mr.assert_called_once()
        call_args = service.update_mr.call_args
        assert call_args.kwargs.get("title") == "New title" or call_args[1].get("title") == "New title"

    def test_update_no_fields(self) -> None:
        result = runner.invoke(app, ["mr", "update", "42"])

        assert result.exit_code == 1
        assert "No fields to update" in result.output

    def test_update_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="PUT",
            url="/projects/test%2Fproject/merge_requests/42",
            body={"title": "New"},
        )
        service = _mock_service("update_mr", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "update", "42", "--title", "New", "--dry-run"])

        assert result.exit_code == 0


class TestMRListJSON:
    """JSON validation tests for MR list."""

    def test_list_json_parseable_with_pagination(self) -> None:
        service = _mock_service(
            "list_mrs",
            PaginatedResponse[MergeRequest](
                items=[_SAMPLE_MR],
                page=1,
                per_page=20,
                total=1,
                total_pages=1,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "items" in data
        assert "page" in data
        assert "total" in data

    def test_list_json_empty_parseable(self) -> None:
        service = _mock_service(
            "list_mrs",
            PaginatedResponse[MergeRequest](
                items=[],
                page=1,
                per_page=20,
                total=0,
                total_pages=0,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["items"] == []


class TestMRCreateLabels:
    """Tests for label parsing in MR create."""

    def test_create_with_labels(self) -> None:
        service = _mock_service("create_mr", _SAMPLE_MR)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["mr", "create", "--title", "Test", "--source", "feat", "--labels", "bug,feature"],
            )

        assert result.exit_code == 0
        call_kwargs = service.create_mr.call_args.kwargs
        assert call_kwargs["labels"] == ["bug", "feature"]

    def test_create_labels_trimmed(self) -> None:
        service = _mock_service("create_mr", _SAMPLE_MR)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["mr", "create", "--title", "Test", "--source", "feat", "--labels", " bug , feature "],
            )

        assert result.exit_code == 0
        call_kwargs = service.create_mr.call_args.kwargs
        assert call_kwargs["labels"] == ["bug", "feature"]


class TestMRMergeJSON:
    """JSON validation tests for MR merge."""

    def test_merge_json_output(self) -> None:
        merged = _SAMPLE_MR.model_copy(update={"state": "merged"})
        service = AsyncMock()
        service.get_mr = AsyncMock(return_value=_SAMPLE_MR)
        service.merge_mr = AsyncMock(return_value=merged)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "merge", "42"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["state"] == "merged"


class TestMRApproveJSON:
    """JSON validation tests for MR approve."""

    def test_approve_json_output(self) -> None:
        service = _mock_service("approve_mr", None)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "approve", "42"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["approved"] is True
        assert data["data"]["mr_iid"] == 42


class TestMRCloseJSON:
    """JSON validation tests for MR close."""

    def test_close_json_output(self) -> None:
        closed = _SAMPLE_MR.model_copy(update={"state": "closed"})
        service = _mock_service("close_mr", closed)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "close", "42"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["state"] == "closed"


class TestMRReopenJSON:
    """JSON validation tests for MR reopen."""

    def test_reopen_json_output(self) -> None:
        reopened = _SAMPLE_MR.model_copy(update={"state": "opened"})
        service = _mock_service("reopen_mr", reopened)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "reopen", "42"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["state"] == "opened"


class TestMRNoteJSON:
    """JSON validation tests for MR note."""

    def test_note_json_output(self) -> None:
        note = Note(
            id=1,
            body="Looks good!",
            author=_AUTHOR,
            created_at=_NOW,
            updated_at=_NOW,
            system=False,
        )
        service = _mock_service("add_note", note)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "note", "42", "--body", "Looks good!"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["body"] == "Looks good!"


class TestMRUpdateJSON:
    """JSON validation tests for MR update."""

    def test_update_json_output(self) -> None:
        updated = _SAMPLE_MR.model_copy(update={"title": "New title"})
        service = _mock_service("update_mr", updated)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "update", "42", "--title", "New title"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["title"] == "New title"

    def test_update_multiple_fields(self) -> None:
        updated = _SAMPLE_MR.model_copy(update={"title": "New", "description": "Updated desc"})
        service = _mock_service("update_mr", updated)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["mr", "update", "42", "--title", "New", "--description", "Updated desc", "--target", "develop"],
            )

        assert result.exit_code == 0
        call_kwargs = service.update_mr.call_args.kwargs
        assert call_kwargs.get("title") == "New"
        assert call_kwargs.get("description") == "Updated desc"
        assert call_kwargs.get("target_branch") == "develop"


class TestMRDiffSpecialCases:
    """Additional tests for diff rendering."""

    def test_diff_new_file(self) -> None:
        diffs = [
            DiffFile(
                old_path="new_file.py",
                new_path="new_file.py",
                diff="@@ -0,0 +1 @@\n+print('hello')",
                new_file=True,
                renamed_file=False,
                deleted_file=False,
            ),
        ]
        service = _mock_service("get_diff", diffs)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "diff", "42"])

        assert result.exit_code == 0
        assert "new_file.py" in result.output

    def test_diff_deleted_file(self) -> None:
        diffs = [
            DiffFile(
                old_path="old_file.py",
                new_path="old_file.py",
                diff="@@ -1 +0,0 @@\n-print('bye')",
                new_file=False,
                renamed_file=False,
                deleted_file=True,
            ),
        ]
        service = _mock_service("get_diff", diffs)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "diff", "42"])

        assert result.exit_code == 0
        assert "old_file.py" in result.output

    def test_diff_renamed_file(self) -> None:
        diffs = [
            DiffFile(
                old_path="old_name.py",
                new_path="new_name.py",
                diff="",
                new_file=False,
                renamed_file=True,
                deleted_file=False,
            ),
        ]
        service = _mock_service("get_diff", diffs)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "diff", "42"])

        assert result.exit_code == 0
        assert "new_name.py" in result.output


class TestMRErrorHandling:
    """Tests for error handling across MR commands."""

    def test_permission_denied(self) -> None:
        from gltools.client.exceptions import AuthenticationError

        service = AsyncMock()
        service.get_mr = AsyncMock(return_value=_SAMPLE_MR)
        service.merge_mr = AsyncMock(side_effect=AuthenticationError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "merge", "42"])

        assert result.exit_code == 1
        assert "Authentication failed" in result.output

    def test_generic_gitlab_error(self) -> None:
        from gltools.client.exceptions import GitLabClientError

        service = AsyncMock()
        service.get_mr = AsyncMock(side_effect=GitLabClientError("Server error"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "view", "42"])

        assert result.exit_code == 1
        assert "Server error" in result.output

    def test_view_not_found_json(self) -> None:
        from gltools.client.exceptions import NotFoundError

        service = AsyncMock()
        service.get_mr = AsyncMock(side_effect=NotFoundError("merge request", "/projects/1/merge_requests/999"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "view", "999"])

        assert result.exit_code == 1
        # Error output goes to stderr in JSON mode, but CliRunner captures both

    def test_create_error_json(self) -> None:
        from gltools.client.exceptions import GitLabClientError

        service = AsyncMock()
        service.create_mr = AsyncMock(side_effect=GitLabClientError("Validation error"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "mr", "create", "--title", "Test", "--source", "feat"])

        assert result.exit_code == 1

    def test_forbidden_error(self) -> None:
        from gltools.client.exceptions import ForbiddenError

        service = AsyncMock()
        service.get_mr = AsyncMock(return_value=_SAMPLE_MR)
        service.merge_mr = AsyncMock(side_effect=ForbiddenError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "merge", "42"])

        assert result.exit_code == 1
        assert "permission" in result.output.lower()
        assert "!42" in result.output

    def test_connection_error(self) -> None:
        from gltools.client.exceptions import ConnectionError

        service = AsyncMock()
        service.get_mr = AsyncMock(side_effect=ConnectionError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "view", "42"])

        assert result.exit_code == 1
        assert "network connection" in result.output.lower()

    def test_timeout_error(self) -> None:
        from gltools.client.exceptions import TimeoutError

        service = AsyncMock()
        service.get_mr = AsyncMock(side_effect=TimeoutError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "view", "42"])

        assert result.exit_code == 1
        assert "timed out" in result.output.lower()

    def test_rate_limit_error(self) -> None:
        from gltools.client.exceptions import RateLimitError

        service = AsyncMock()
        service.get_mr = AsyncMock(side_effect=RateLimitError(retry_after=60.0))
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "view", "42"])

        assert result.exit_code == 1
        assert "rate limit" in result.output.lower()

    def test_server_error(self) -> None:
        from gltools.client.exceptions import ServerError

        service = AsyncMock()
        service.get_mr = AsyncMock(side_effect=ServerError(502, "Bad Gateway"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "view", "42"])

        assert result.exit_code == 1
        assert "502" in result.output

    def test_auth_error_includes_re_auth_instructions(self) -> None:
        from gltools.client.exceptions import AuthenticationError

        service = AsyncMock()
        service.get_mr = AsyncMock(side_effect=AuthenticationError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "view", "42"])

        assert result.exit_code == 1
        assert "gltools auth login" in result.output

    def test_merge_with_squash_and_delete_branch(self) -> None:
        merged = _SAMPLE_MR.model_copy(update={"state": "merged"})
        service = AsyncMock()
        service.get_mr = AsyncMock(return_value=_SAMPLE_MR)
        service.merge_mr = AsyncMock(return_value=merged)
        with _patch_build_service(service):
            result = runner.invoke(app, ["mr", "merge", "42", "--squash", "--delete-branch"])

        assert result.exit_code == 0
        call_kwargs = service.merge_mr.call_args.kwargs
        assert call_kwargs["squash"] is True
        assert call_kwargs["delete_branch"] is True
