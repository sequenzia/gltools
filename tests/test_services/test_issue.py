"""Tests for the Issue service layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gltools.client.exceptions import NotFoundError
from gltools.models import DryRunResult, Issue, Note, PaginatedResponse
from gltools.services.issue import IssueService
from gltools.services.merge_request import ProjectResolutionError


def _make_config(default_project: str | None = None) -> MagicMock:
    """Create a mock GitLabConfig."""
    config = MagicMock()
    config.default_project = default_project
    return config


def _make_client() -> MagicMock:
    """Create a mock GitLabClient with async issues manager."""
    client = MagicMock()
    client.issues = MagicMock()
    client.issues.list = AsyncMock()
    client.issues.get = AsyncMock()
    client.issues.create = AsyncMock()
    client.issues.update = AsyncMock()
    client.issues.close = AsyncMock()
    client.issues.reopen = AsyncMock()
    client.issues.create_note = AsyncMock()
    return client


def _make_issue(**overrides: object) -> Issue:
    """Create a minimal Issue for testing."""
    defaults = {
        "id": 1,
        "iid": 5,
        "title": "Test Issue",
        "description": None,
        "state": "opened",
        "author": {"id": 1, "username": "user", "name": "User"},
        "assignee": None,
        "labels": [],
        "milestone": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "closed_at": None,
    }
    defaults.update(overrides)
    return Issue.model_validate(defaults)


class TestProjectResolution:
    """Tests for project ID resolution logic."""

    async def test_explicit_project_takes_precedence(self) -> None:
        client = _make_client()
        config = _make_config(default_project="config/project")
        service = IssueService(client, config, project="explicit/proj")
        assert service._resolve_project() == "explicit/proj"

    async def test_config_default_project_used_when_no_explicit(self) -> None:
        client = _make_client()
        config = _make_config(default_project="config/project")
        service = IssueService(client, config)
        assert service._resolve_project() == "config/project"

    @patch("gltools.services.issue.detect_gitlab_remote")
    async def test_git_remote_fallback(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = MagicMock(project_path="remote/project")
        client = _make_client()
        config = _make_config(default_project=None)
        service = IssueService(client, config)
        assert service._resolve_project() == "remote/project"

    @patch("gltools.services.issue.detect_gitlab_remote")
    async def test_no_project_raises_error(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = None
        client = _make_client()
        config = _make_config(default_project=None)
        service = IssueService(client, config)
        with pytest.raises(ProjectResolutionError):
            service._resolve_project()


class TestListIssues:
    """Tests for listing issues."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        issue = _make_issue()
        client.issues.list.return_value = PaginatedResponse[Issue](
            items=[issue], page=1, per_page=20, total=1, total_pages=1, next_page=None
        )
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.list_issues(state="opened", per_page=20, page=1)

        client.issues.list.assert_called_once_with(
            "group/proj",
            state="opened",
            labels=None,
            assignee_username=None,
            milestone=None,
            scope=None,
            search=None,
            per_page=20,
            page=1,
        )
        assert len(result.items) == 1
        assert result.items[0].iid == 5

    async def test_all_pages_collects_everything(self) -> None:
        client = _make_client()
        issue1 = _make_issue(iid=1)
        issue2 = _make_issue(iid=2)
        page1 = PaginatedResponse[Issue](
            items=[issue1], page=1, per_page=1, total=2, total_pages=2, next_page=2
        )
        page2 = PaginatedResponse[Issue](
            items=[issue2], page=2, per_page=1, total=2, total_pages=2, next_page=None
        )
        client.issues.list.side_effect = [page1, page2]
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.list_issues(all_pages=True, per_page=1)

        assert len(result.items) == 2
        assert result.items[0].iid == 1
        assert result.items[1].iid == 2
        assert client.issues.list.call_count == 2


class TestGetIssue:
    """Tests for getting a single issue."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        issue = _make_issue()
        client.issues.get.return_value = issue
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.get_issue(5)

        client.issues.get.assert_called_once_with("group/proj", 5)
        assert result.iid == 5

    async def test_not_found_raises_with_message(self) -> None:
        client = _make_client()
        client.issues.get.side_effect = NotFoundError(resource="Issue", path="/projects/1/issues/999")
        service = IssueService(client, _make_config(), project="group/proj")

        with pytest.raises(NotFoundError, match="Issue not found"):
            await service.get_issue(999)


class TestCreateIssue:
    """Tests for creating an issue."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        issue = _make_issue()
        client.issues.create.return_value = issue
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.create_issue(title="Bug report")

        client.issues.create.assert_called_once_with(
            "group/proj",
            title="Bug report",
            description=None,
            labels=None,
            assignee_ids=None,
            milestone_id=None,
            due_date=None,
        )
        assert isinstance(result, Issue)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.create_issue(title="Bug report", dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.method == "POST"
        assert "/issues" in result.url
        assert result.body is not None
        assert result.body["title"] == "Bug report"
        client.issues.create.assert_not_called()


class TestUpdateIssue:
    """Tests for updating an issue."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        issue = _make_issue(title="Updated")
        client.issues.update.return_value = issue
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.update_issue(5, title="Updated")

        client.issues.update.assert_called_once_with("group/proj", 5, title="Updated")
        assert isinstance(result, Issue)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.update_issue(5, dry_run=True, title="Updated")

        assert isinstance(result, DryRunResult)
        assert result.method == "PUT"
        client.issues.update.assert_not_called()


class TestCloseIssue:
    """Tests for closing an issue."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        issue = _make_issue(state="closed")
        client.issues.close.return_value = issue
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.close_issue(5)

        client.issues.close.assert_called_once_with("group/proj", 5)
        assert isinstance(result, Issue)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.close_issue(5, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body == {"state_event": "close"}
        client.issues.close.assert_not_called()


class TestReopenIssue:
    """Tests for reopening an issue."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        issue = _make_issue(state="opened")
        client.issues.reopen.return_value = issue
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.reopen_issue(5)

        client.issues.reopen.assert_called_once_with("group/proj", 5)
        assert isinstance(result, Issue)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.reopen_issue(5, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body == {"state_event": "reopen"}
        client.issues.reopen.assert_not_called()


class TestAddNote:
    """Tests for adding a note to an issue."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        note = Note.model_validate({
            "id": 1, "body": "Comment", "author": {"id": 1, "username": "u", "name": "U"},
            "created_at": "2025-01-01T00:00:00Z", "updated_at": "2025-01-01T00:00:00Z",
            "system": False,
        })
        client.issues.create_note.return_value = note
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.add_note(5, "Comment")

        client.issues.create_note.assert_called_once_with("group/proj", 5, "Comment")
        assert isinstance(result, Note)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.add_note(5, "Comment", dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body == {"body": "Comment"}
        client.issues.create_note.assert_not_called()


class TestCreateIssueWithOptionalParams:
    """Tests for create_issue with all optional parameters."""

    async def test_with_all_optional_params(self) -> None:
        client = _make_client()
        issue = _make_issue()
        client.issues.create.return_value = issue
        service = IssueService(client, _make_config(), project="group/proj")

        await service.create_issue(
            title="Bug",
            description="Details here",
            labels=["bug", "critical"],
            assignee_ids=[1, 2],
            milestone_id=5,
            due_date="2025-12-31",
        )

        client.issues.create.assert_called_once_with(
            "group/proj",
            title="Bug",
            description="Details here",
            labels=["bug", "critical"],
            assignee_ids=[1, 2],
            milestone_id=5,
            due_date="2025-12-31",
        )

    async def test_dry_run_includes_all_optional_fields(self) -> None:
        client = _make_client()
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.create_issue(
            title="Bug",
            description="desc",
            labels=["a", "b"],
            assignee_ids=[3],
            milestone_id=7,
            due_date="2025-06-01",
            dry_run=True,
        )

        assert isinstance(result, DryRunResult)
        assert result.body["title"] == "Bug"
        assert result.body["description"] == "desc"
        assert result.body["labels"] == "a,b"
        assert result.body["assignee_ids"] == [3]
        assert result.body["milestone_id"] == 7
        assert result.body["due_date"] == "2025-06-01"
        client.issues.create.assert_not_called()


class TestUpdateIssueEdgeCases:
    """Edge cases for update_issue."""

    async def test_dry_run_no_fields_body_is_none(self) -> None:
        client = _make_client()
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.update_issue(5, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body is None


class TestEncodeProject:
    """Tests for URL-encoding of project paths in issue service."""

    async def test_slashes_encoded_in_dry_run_url(self) -> None:
        client = _make_client()
        service = IssueService(client, _make_config(), project="group/subgroup/proj")

        result = await service.create_issue(title="Test", dry_run=True)

        assert isinstance(result, DryRunResult)
        assert "group%2Fsubgroup%2Fproj" in result.url


class TestListIssuesFilterParams:
    """Tests for list_issues with all filter parameters."""

    async def test_passes_all_filter_params(self) -> None:
        client = _make_client()
        client.issues.list.return_value = PaginatedResponse[Issue](
            items=[], page=1, per_page=20, total=0, total_pages=1, next_page=None
        )
        service = IssueService(client, _make_config(), project="group/proj")

        await service.list_issues(
            state="closed",
            labels=["enhancement"],
            assignee="janedoe",
            milestone="v1.0",
            scope="created_by_me",
            search="login",
            per_page=50,
            page=2,
        )

        client.issues.list.assert_called_once_with(
            "group/proj",
            state="closed",
            labels=["enhancement"],
            assignee_username="janedoe",
            milestone="v1.0",
            scope="created_by_me",
            search="login",
            per_page=50,
            page=2,
        )

    async def test_all_pages_single_page(self) -> None:
        client = _make_client()
        issue = _make_issue()
        client.issues.list.return_value = PaginatedResponse[Issue](
            items=[issue], page=1, per_page=20, total=1, total_pages=1, next_page=None
        )
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.list_issues(all_pages=True)

        assert len(result.items) == 1
        assert result.next_page is None
        assert client.issues.list.call_count == 1

    async def test_all_pages_empty_result(self) -> None:
        client = _make_client()
        client.issues.list.return_value = PaginatedResponse[Issue](
            items=[], page=1, per_page=20, total=0, total_pages=1, next_page=None
        )
        service = IssueService(client, _make_config(), project="group/proj")

        result = await service.list_issues(all_pages=True)

        assert len(result.items) == 0
        assert result.total == 0


class TestGetIssueErrorWrapping:
    """Tests for error wrapping in get_issue."""

    async def test_not_found_wraps_with_new_message(self) -> None:
        """The service wraps NotFoundError with a user-friendly message."""
        client = _make_client()
        client.issues.get.side_effect = NotFoundError(resource="Issue", path="/issues/42")
        service = IssueService(client, _make_config(), project="group/proj")

        with pytest.raises(NotFoundError) as exc_info:
            await service.get_issue(42)

        assert "Issue not found" in str(exc_info.value)
        assert "issues/42" in str(exc_info.value)
