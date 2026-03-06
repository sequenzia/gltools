"""Tests for Issue CLI commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from gltools.cli.app import app
from gltools.models import Issue, Note, PaginatedResponse
from gltools.models.output import DryRunResult
from gltools.models.user import UserRef

runner = CliRunner()

# Common test fixtures
_AUTHOR = UserRef(id=1, username="testuser", name="Test User")
_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

_SAMPLE_ISSUE = Issue(
    id=200,
    iid=10,
    title="Fix auth flow",
    description="Auth flow is broken on mobile",
    state="opened",
    author=_AUTHOR,
    assignee=None,
    labels=["bug", "auth"],
    milestone=None,
    created_at=_NOW,
    updated_at=_NOW,
    closed_at=None,
)

_CLOSED_ISSUE = Issue(
    id=201,
    iid=11,
    title="Old bug",
    description=None,
    state="closed",
    author=_AUTHOR,
    assignee=None,
    labels=[],
    milestone=None,
    created_at=_NOW,
    updated_at=_NOW,
    closed_at=_NOW,
)


def _mock_service(method_name: str, return_value: object) -> AsyncMock:
    """Create a mock IssueService with a single mocked method."""
    mock = AsyncMock()
    getattr(mock, method_name).return_value = return_value
    return mock


def _patch_build_service(mock_service: AsyncMock) -> object:
    """Patch _build_service to return the mock service and a mock client."""
    mock_client = AsyncMock()

    async def _fake_build(ctx, project=None):
        return mock_service, mock_client

    return patch("gltools.cli.issue._build_service", side_effect=_fake_build)


class TestIssueList:
    """Tests for `gltools issue list`."""

    def test_list_text_output(self) -> None:
        service = _mock_service(
            "list_issues",
            PaginatedResponse[Issue](
                items=[_SAMPLE_ISSUE],
                page=1,
                per_page=20,
                total=1,
                total_pages=1,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "list"])

        assert result.exit_code == 0
        assert "10" in result.output
        assert "Fix auth flow" in result.output

    def test_list_json_output(self) -> None:
        service = _mock_service(
            "list_issues",
            PaginatedResponse[Issue](
                items=[_SAMPLE_ISSUE],
                page=1,
                per_page=20,
                total=1,
                total_pages=1,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "issue", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["items"][0]["iid"] == 10

    def test_list_empty(self) -> None:
        service = _mock_service(
            "list_issues",
            PaginatedResponse[Issue](
                items=[],
                page=1,
                per_page=20,
                total=0,
                total_pages=0,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "list"])

        assert result.exit_code == 0
        assert "No issues found" in result.output

    def test_list_with_filters(self) -> None:
        service = _mock_service(
            "list_issues",
            PaginatedResponse[Issue](
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
                ["issue", "list", "--state", "closed", "--per-page", "10", "--assignee", "someone"],
            )

        assert result.exit_code == 0
        service.list_issues.assert_called_once_with(
            state="closed",
            labels=None,
            assignee="someone",
            milestone=None,
            scope=None,
            search=None,
            per_page=10,
            page=1,
            all_pages=False,
        )

    def test_list_pagination_flags(self) -> None:
        service = _mock_service(
            "list_issues",
            PaginatedResponse[Issue](
                items=[_SAMPLE_ISSUE],
                page=2,
                per_page=5,
                total=10,
                total_pages=2,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "list", "--page", "2", "--per-page", "5"])

        assert result.exit_code == 0
        service.list_issues.assert_called_once()
        call_kwargs = service.list_issues.call_args.kwargs
        assert call_kwargs["page"] == 2
        assert call_kwargs["per_page"] == 5

    def test_list_all_pages(self) -> None:
        service = _mock_service(
            "list_issues",
            PaginatedResponse[Issue](
                items=[_SAMPLE_ISSUE, _CLOSED_ISSUE],
                page=1,
                per_page=2,
                total=2,
                total_pages=1,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "list", "--all"])

        assert result.exit_code == 0
        service.list_issues.assert_called_once()
        assert service.list_issues.call_args.kwargs["all_pages"] is True


class TestIssueCreate:
    """Tests for `gltools issue create`."""

    def test_create_success(self) -> None:
        service = _mock_service("create_issue", _SAMPLE_ISSUE)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["issue", "create", "--title", "Fix auth flow"],
            )

        assert result.exit_code == 0
        service.create_issue.assert_called_once()

    def test_create_with_all_options(self) -> None:
        service = _mock_service("create_issue", _SAMPLE_ISSUE)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                [
                    "issue", "create",
                    "--title", "Fix auth flow",
                    "--description", "Detailed description",
                    "--labels", "bug,auth",
                    "--assignee-ids", "1,2",
                    "--milestone-id", "5",
                    "--due-date", "2026-12-31",
                ],
            )

        assert result.exit_code == 0
        call_kwargs = service.create_issue.call_args.kwargs
        assert call_kwargs["title"] == "Fix auth flow"
        assert call_kwargs["description"] == "Detailed description"
        assert call_kwargs["labels"] == ["bug", "auth"]
        assert call_kwargs["assignee_ids"] == [1, 2]
        assert call_kwargs["milestone_id"] == 5
        assert call_kwargs["due_date"] == "2026-12-31"

    def test_create_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="POST",
            url="/projects/test%2Fproject/issues",
            body={"title": "Test"},
        )
        service = _mock_service("create_issue", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["issue", "create", "--title", "Test", "--dry-run"],
            )

        assert result.exit_code == 0
        assert service.create_issue.call_args.kwargs["dry_run"] is True

    def test_create_json_output(self) -> None:
        service = _mock_service("create_issue", _SAMPLE_ISSUE)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["--json", "issue", "create", "--title", "Test"],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["iid"] == 10


class TestIssueView:
    """Tests for `gltools issue view`."""

    def test_view_text_output(self) -> None:
        service = _mock_service("get_issue", _SAMPLE_ISSUE)
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "view", "10"])

        assert result.exit_code == 0
        assert "Fix auth flow" in result.output

    def test_view_json_output(self) -> None:
        service = _mock_service("get_issue", _SAMPLE_ISSUE)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "issue", "view", "10"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["iid"] == 10

    def test_view_not_found(self) -> None:
        from gltools.client.exceptions import NotFoundError

        service = AsyncMock()
        service.get_issue = AsyncMock(side_effect=NotFoundError("Issue not found", "issues/999"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "view", "999"])

        assert result.exit_code == 1
        assert "Issue #999 not found" in result.output

    def test_view_confidential_not_found(self) -> None:
        """Confidential issue returns same not-found error without leaking existence."""
        from gltools.client.exceptions import NotFoundError

        service = AsyncMock()
        service.get_issue = AsyncMock(side_effect=NotFoundError("Issue not found", "issues/42"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "view", "42"])

        assert result.exit_code == 1
        assert "Issue #42 not found" in result.output


class TestIssueUpdate:
    """Tests for `gltools issue update`."""

    def test_update_title(self) -> None:
        updated = _SAMPLE_ISSUE.model_copy(update={"title": "New title"})
        service = _mock_service("update_issue", updated)
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "update", "10", "--title", "New title"])

        assert result.exit_code == 0
        service.update_issue.assert_called_once()
        call_kwargs = service.update_issue.call_args.kwargs
        assert call_kwargs.get("title") == "New title"

    def test_update_no_fields(self) -> None:
        result = runner.invoke(app, ["issue", "update", "10"])

        assert result.exit_code == 1
        assert "No fields to update" in result.output

    def test_update_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="PUT",
            url="/projects/test%2Fproject/issues/10",
            body={"title": "New"},
        )
        service = _mock_service("update_issue", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "update", "10", "--title", "New", "--dry-run"])

        assert result.exit_code == 0

    def test_update_not_found(self) -> None:
        from gltools.client.exceptions import NotFoundError

        service = AsyncMock()
        service.update_issue = AsyncMock(side_effect=NotFoundError("Issue not found"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "update", "999", "--title", "X"])

        assert result.exit_code == 1
        assert "Issue #999 not found" in result.output


class TestIssueClose:
    """Tests for `gltools issue close`."""

    def test_close_success(self) -> None:
        closed = _SAMPLE_ISSUE.model_copy(update={"state": "closed"})
        service = _mock_service("close_issue", closed)
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "close", "10"])

        assert result.exit_code == 0

    def test_close_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="PUT",
            url="/projects/test%2Fproject/issues/10",
            body={"state_event": "close"},
        )
        service = _mock_service("close_issue", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "close", "10", "--dry-run"])

        assert result.exit_code == 0

    def test_close_not_found(self) -> None:
        from gltools.client.exceptions import NotFoundError

        service = AsyncMock()
        service.close_issue = AsyncMock(side_effect=NotFoundError("Issue not found"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "close", "999"])

        assert result.exit_code == 1
        assert "Issue #999 not found" in result.output


class TestIssueReopen:
    """Tests for `gltools issue reopen`."""

    def test_reopen_success(self) -> None:
        reopened = _CLOSED_ISSUE.model_copy(update={"state": "opened", "closed_at": None})
        service = _mock_service("reopen_issue", reopened)
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "reopen", "11"])

        assert result.exit_code == 0

    def test_reopen_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="PUT",
            url="/projects/test%2Fproject/issues/11",
            body={"state_event": "reopen"},
        )
        service = _mock_service("reopen_issue", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "reopen", "11", "--dry-run"])

        assert result.exit_code == 0


class TestIssueNote:
    """Tests for `gltools issue note`."""

    def test_note_success(self) -> None:
        note = Note(
            id=1,
            body="This is a comment",
            author=_AUTHOR,
            created_at=_NOW,
            updated_at=_NOW,
            system=False,
        )
        service = _mock_service("add_note", note)
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "note", "10", "--body", "This is a comment"])

        assert result.exit_code == 0

    def test_note_dry_run(self) -> None:
        dry_result = DryRunResult(
            method="POST",
            url="/projects/test%2Fproject/issues/10/notes",
            body={"body": "Test note"},
        )
        service = _mock_service("add_note", dry_result)
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "note", "10", "--body", "Test note", "--dry-run"])

        assert result.exit_code == 0

    def test_note_not_found(self) -> None:
        from gltools.client.exceptions import NotFoundError

        service = AsyncMock()
        service.add_note = AsyncMock(side_effect=NotFoundError("Issue not found"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "note", "999", "--body", "Hello"])

        assert result.exit_code == 1
        assert "Issue #999 not found" in result.output


class TestIssueCloseJSON:
    """JSON validation tests for issue close."""

    def test_close_json_output(self) -> None:
        closed = _SAMPLE_ISSUE.model_copy(update={"state": "closed"})
        service = _mock_service("close_issue", closed)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "issue", "close", "10"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["state"] == "closed"


class TestIssueReopenJSON:
    """JSON validation tests for issue reopen."""

    def test_reopen_json_output(self) -> None:
        reopened = _CLOSED_ISSUE.model_copy(update={"state": "opened", "closed_at": None})
        service = _mock_service("reopen_issue", reopened)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "issue", "reopen", "11"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["state"] == "opened"


class TestIssueNoteJSON:
    """JSON validation tests for issue note."""

    def test_note_json_output(self) -> None:
        note = Note(
            id=1,
            body="This is a comment",
            author=_AUTHOR,
            created_at=_NOW,
            updated_at=_NOW,
            system=False,
        )
        service = _mock_service("add_note", note)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "issue", "note", "10", "--body", "This is a comment"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["body"] == "This is a comment"


class TestIssueUpdateJSON:
    """JSON validation tests for issue update."""

    def test_update_json_output(self) -> None:
        updated = _SAMPLE_ISSUE.model_copy(update={"title": "New title"})
        service = _mock_service("update_issue", updated)
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "issue", "update", "10", "--title", "New title"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["title"] == "New title"

    def test_update_multiple_fields(self) -> None:
        updated = _SAMPLE_ISSUE.model_copy(update={"title": "New", "description": "Updated"})
        service = _mock_service("update_issue", updated)
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                [
                    "issue", "update", "10",
                    "--title", "New",
                    "--description", "Updated",
                    "--labels", "bug,critical",
                    "--assignee-ids", "1,2",
                    "--milestone-id", "5",
                    "--due-date", "2026-12-31",
                ],
            )

        assert result.exit_code == 0
        call_kwargs = service.update_issue.call_args.kwargs
        assert call_kwargs.get("title") == "New"
        assert call_kwargs.get("description") == "Updated"
        assert call_kwargs.get("labels") == "bug,critical"
        assert call_kwargs.get("assignee_ids") == [1, 2]
        assert call_kwargs.get("milestone_id") == 5
        assert call_kwargs.get("due_date") == "2026-12-31"


class TestIssueListJSON:
    """JSON validation tests for issue list."""

    def test_list_json_parseable_with_pagination(self) -> None:
        service = _mock_service(
            "list_issues",
            PaginatedResponse[Issue](
                items=[_SAMPLE_ISSUE],
                page=1,
                per_page=20,
                total=1,
                total_pages=1,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["--json", "issue", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "items" in data
        assert "page" in data
        assert "total" in data

    def test_list_with_labels_filter(self) -> None:
        service = _mock_service(
            "list_issues",
            PaginatedResponse[Issue](
                items=[],
                page=1,
                per_page=20,
                total=0,
                total_pages=0,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "list", "--labels", "bug,feature"])

        assert result.exit_code == 0
        call_kwargs = service.list_issues.call_args.kwargs
        assert call_kwargs["labels"] == ["bug", "feature"]

    def test_list_with_search_and_scope(self) -> None:
        service = _mock_service(
            "list_issues",
            PaginatedResponse[Issue](
                items=[],
                page=1,
                per_page=20,
                total=0,
                total_pages=0,
            ),
        )
        with _patch_build_service(service):
            result = runner.invoke(
                app,
                ["issue", "list", "--search", "login", "--scope", "created_by_me", "--milestone", "v1.0"],
            )

        assert result.exit_code == 0
        call_kwargs = service.list_issues.call_args.kwargs
        assert call_kwargs["search"] == "login"
        assert call_kwargs["scope"] == "created_by_me"
        assert call_kwargs["milestone"] == "v1.0"


class TestIssueErrorHandling:
    """Tests for error handling across issue commands."""

    def test_permission_denied(self) -> None:
        from gltools.client.exceptions import AuthenticationError

        service = AsyncMock()
        service.get_issue = AsyncMock(side_effect=AuthenticationError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "view", "10"])

        assert result.exit_code == 1
        assert "Authentication failed" in result.output

    def test_generic_gitlab_error(self) -> None:
        from gltools.client.exceptions import GitLabClientError

        service = AsyncMock()
        service.get_issue = AsyncMock(side_effect=GitLabClientError("Server error"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "view", "10"])

        assert result.exit_code == 1
        assert "Server error" in result.output

    def test_create_error(self) -> None:
        from gltools.client.exceptions import GitLabClientError

        service = AsyncMock()
        service.create_issue = AsyncMock(side_effect=GitLabClientError("Validation error"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "create", "--title", "Test"])

        assert result.exit_code == 1

    def test_list_error(self) -> None:
        from gltools.client.exceptions import GitLabClientError

        service = AsyncMock()
        service.list_issues = AsyncMock(side_effect=GitLabClientError("Bad request"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "list"])

        assert result.exit_code == 1

    def test_reopen_not_found(self) -> None:
        from gltools.client.exceptions import NotFoundError

        service = AsyncMock()
        service.reopen_issue = AsyncMock(side_effect=NotFoundError("Issue not found"))
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "reopen", "999"])

        assert result.exit_code == 1
        assert "Issue #999 not found" in result.output

    def test_connection_error(self) -> None:
        from gltools.client.exceptions import ConnectionError

        service = AsyncMock()
        service.get_issue = AsyncMock(side_effect=ConnectionError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "view", "10"])

        assert result.exit_code == 1
        assert "network connection" in result.output.lower()

    def test_timeout_error(self) -> None:
        from gltools.client.exceptions import TimeoutError

        service = AsyncMock()
        service.get_issue = AsyncMock(side_effect=TimeoutError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "view", "10"])

        assert result.exit_code == 1
        assert "timed out" in result.output.lower()

    def test_forbidden_error(self) -> None:
        from gltools.client.exceptions import ForbiddenError

        service = AsyncMock()
        service.get_issue = AsyncMock(side_effect=ForbiddenError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "view", "10"])

        assert result.exit_code == 1
        assert "permission" in result.output.lower()

    def test_auth_error_includes_re_auth_instructions(self) -> None:
        from gltools.client.exceptions import AuthenticationError

        service = AsyncMock()
        service.get_issue = AsyncMock(side_effect=AuthenticationError())
        with _patch_build_service(service):
            result = runner.invoke(app, ["issue", "view", "10"])

        assert result.exit_code == 1
        assert "gltools auth login" in result.output
