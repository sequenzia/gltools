"""Tests for the MergeRequest service layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gltools.models import DiffFile, DryRunResult, MergeRequest, Note, PaginatedResponse
from gltools.services.merge_request import MergeRequestService, ProjectResolutionError


def _make_config(default_project: str | None = None) -> MagicMock:
    """Create a mock GitLabConfig."""
    config = MagicMock()
    config.default_project = default_project
    return config


def _make_client() -> MagicMock:
    """Create a mock GitLabClient with async merge_requests manager."""
    client = MagicMock()
    client.merge_requests = MagicMock()
    client.merge_requests.list = AsyncMock()
    client.merge_requests.get = AsyncMock()
    client.merge_requests.create = AsyncMock()
    client.merge_requests.update = AsyncMock()
    client.merge_requests.merge = AsyncMock()
    client.merge_requests.approve = AsyncMock()
    client.merge_requests.diff = AsyncMock()
    client.merge_requests.create_note = AsyncMock()
    return client


def _make_mr(**overrides: object) -> MergeRequest:
    """Create a minimal MergeRequest for testing."""
    defaults = {
        "id": 1,
        "iid": 10,
        "title": "Test MR",
        "state": "opened",
        "source_branch": "feature",
        "target_branch": "main",
        "author": {"id": 1, "username": "user", "name": "User"},
        "labels": [],
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return MergeRequest.model_validate(defaults)


class TestProjectResolution:
    """Tests for project ID resolution logic."""

    async def test_explicit_project_takes_precedence(self) -> None:
        client = _make_client()
        config = _make_config(default_project="config/project")
        service = MergeRequestService(client, config, project="explicit/proj")
        assert service._resolve_project() == "explicit/proj"

    async def test_config_default_project_used_when_no_explicit(self) -> None:
        client = _make_client()
        config = _make_config(default_project="config/project")
        service = MergeRequestService(client, config)
        assert service._resolve_project() == "config/project"

    @patch("gltools.services.merge_request.detect_gitlab_remote")
    async def test_git_remote_fallback(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = MagicMock(project_path="remote/project")
        client = _make_client()
        config = _make_config(default_project=None)
        service = MergeRequestService(client, config)
        assert service._resolve_project() == "remote/project"

    @patch("gltools.services.merge_request.detect_gitlab_remote")
    async def test_no_project_raises_error(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = None
        client = _make_client()
        config = _make_config(default_project=None)
        service = MergeRequestService(client, config)
        with pytest.raises(ProjectResolutionError):
            service._resolve_project()


class TestListMrs:
    """Tests for listing merge requests."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        mr = _make_mr()
        client.merge_requests.list.return_value = PaginatedResponse[MergeRequest](
            items=[mr], page=1, per_page=20, total=1, total_pages=1, next_page=None
        )
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.list_mrs(state="opened", per_page=20, page=1)

        client.merge_requests.list.assert_called_once_with(
            "group/proj",
            state="opened",
            labels=None,
            author_username=None,
            scope=None,
            search=None,
            per_page=20,
            page=1,
        )
        assert len(result.items) == 1
        assert result.items[0].iid == 10

    async def test_all_pages_collects_everything(self) -> None:
        client = _make_client()
        mr1 = _make_mr(iid=1)
        mr2 = _make_mr(iid=2)
        page1 = PaginatedResponse[MergeRequest](
            items=[mr1], page=1, per_page=1, total=2, total_pages=2, next_page=2
        )
        page2 = PaginatedResponse[MergeRequest](
            items=[mr2], page=2, per_page=1, total=2, total_pages=2, next_page=None
        )
        client.merge_requests.list.side_effect = [page1, page2]
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.list_mrs(all_pages=True, per_page=1)

        assert len(result.items) == 2
        assert result.items[0].iid == 1
        assert result.items[1].iid == 2
        assert client.merge_requests.list.call_count == 2


class TestGetMr:
    """Tests for getting a single merge request."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        mr = _make_mr()
        client.merge_requests.get.return_value = mr
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.get_mr(10)

        client.merge_requests.get.assert_called_once_with("group/proj", 10)
        assert result.iid == 10


class TestCreateMr:
    """Tests for creating a merge request."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        mr = _make_mr()
        client.merge_requests.create.return_value = mr
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.create_mr(
            title="Test", source_branch="feat", target_branch="main"
        )

        client.merge_requests.create.assert_called_once_with(
            "group/proj",
            title="Test",
            source_branch="feat",
            target_branch="main",
            description=None,
            labels=None,
            assignee_ids=None,
        )
        assert isinstance(result, MergeRequest)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.create_mr(
            title="Test", source_branch="feat", target_branch="main", dry_run=True
        )

        assert isinstance(result, DryRunResult)
        assert result.method == "POST"
        assert "/merge_requests" in result.url
        assert result.body is not None
        assert result.body["title"] == "Test"
        client.merge_requests.create.assert_not_called()


class TestUpdateMr:
    """Tests for updating a merge request."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        mr = _make_mr(title="Updated")
        client.merge_requests.update.return_value = mr
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.update_mr(10, title="Updated")

        client.merge_requests.update.assert_called_once_with("group/proj", 10, title="Updated")
        assert isinstance(result, MergeRequest)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.update_mr(10, dry_run=True, title="Updated")

        assert isinstance(result, DryRunResult)
        assert result.method == "PUT"
        client.merge_requests.update.assert_not_called()


class TestMergeMr:
    """Tests for merging a merge request."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        mr = _make_mr(state="merged")
        client.merge_requests.merge.return_value = mr
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.merge_mr(10, squash=True, delete_branch=True)

        client.merge_requests.merge.assert_called_once_with(
            "group/proj", 10, squash=True, delete_source_branch=True
        )
        assert isinstance(result, MergeRequest)

    async def test_dry_run_shows_endpoint_and_parameters(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.merge_mr(10, squash=True, delete_branch=True, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.method == "PUT"
        assert "/merge" in result.url
        assert result.body is not None
        assert result.body["squash"] is True
        assert result.body["should_remove_source_branch"] is True
        client.merge_requests.merge.assert_not_called()


class TestApproveMr:
    """Tests for approving a merge request."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.approve_mr(10)

        client.merge_requests.approve.assert_called_once_with("group/proj", 10)
        assert result is None

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.approve_mr(10, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert "/approve" in result.url
        client.merge_requests.approve.assert_not_called()


class TestGetDiff:
    """Tests for getting merge request diffs."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        diff = DiffFile(
            old_path="a.py", new_path="a.py", diff="@@ ...",
            new_file=False, renamed_file=False, deleted_file=False,
        )
        client.merge_requests.diff.return_value = [diff]
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.get_diff(10)

        client.merge_requests.diff.assert_called_once_with("group/proj", 10)
        assert len(result) == 1


class TestAddNote:
    """Tests for adding a note to a merge request."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        note = Note.model_validate({
            "id": 1, "body": "LGTM", "author": {"id": 1, "username": "u", "name": "U"},
            "created_at": "2025-01-01T00:00:00Z", "updated_at": "2025-01-01T00:00:00Z",
            "system": False,
        })
        client.merge_requests.create_note.return_value = note
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.add_note(10, "LGTM")

        client.merge_requests.create_note.assert_called_once_with("group/proj", 10, "LGTM")
        assert isinstance(result, Note)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.add_note(10, "LGTM", dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body == {"body": "LGTM"}
        client.merge_requests.create_note.assert_not_called()


class TestCloseMr:
    """Tests for closing a merge request."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        mr = _make_mr(state="closed")
        client.merge_requests.update.return_value = mr
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.close_mr(10)

        client.merge_requests.update.assert_called_once_with(
            "group/proj", 10, state_event="close"
        )
        assert isinstance(result, MergeRequest)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.close_mr(10, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body == {"state_event": "close"}
        client.merge_requests.update.assert_not_called()


class TestReopenMr:
    """Tests for reopening a merge request."""

    async def test_delegates_to_manager(self) -> None:
        client = _make_client()
        mr = _make_mr(state="opened")
        client.merge_requests.update.return_value = mr
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.reopen_mr(10)

        client.merge_requests.update.assert_called_once_with(
            "group/proj", 10, state_event="reopen"
        )
        assert isinstance(result, MergeRequest)

    async def test_dry_run_returns_preview(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.reopen_mr(10, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body == {"state_event": "reopen"}
        client.merge_requests.update.assert_not_called()


class TestProjectResolutionError:
    """Tests for ProjectResolutionError."""

    def test_default_message(self) -> None:
        err = ProjectResolutionError()
        assert "No project configured" in str(err)
        assert "default_project" in str(err)
        assert "--project" in str(err)

    def test_custom_message(self) -> None:
        err = ProjectResolutionError("custom error")
        assert str(err) == "custom error"


class TestEncodeProject:
    """Tests for URL-encoding of project paths."""

    async def test_slashes_encoded_in_dry_run_url(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/subgroup/proj")

        result = await service.create_mr(
            title="Test", source_branch="feat", target_branch="main", dry_run=True
        )

        assert isinstance(result, DryRunResult)
        assert "group%2Fsubgroup%2Fproj" in result.url

    async def test_special_chars_encoded(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj with spaces")

        result = await service.update_mr(10, dry_run=True, title="x")

        assert isinstance(result, DryRunResult)
        assert "group%2Fproj%20with%20spaces" in result.url


class TestCreateMrWithOptionalParams:
    """Tests for create_mr with all optional parameters."""

    async def test_with_description_labels_assignees(self) -> None:
        client = _make_client()
        mr = _make_mr()
        client.merge_requests.create.return_value = mr
        service = MergeRequestService(client, _make_config(), project="group/proj")

        await service.create_mr(
            title="Test",
            source_branch="feat",
            target_branch="main",
            description="A description",
            labels=["bug", "fix"],
            assignees=[1, 2],
        )

        client.merge_requests.create.assert_called_once_with(
            "group/proj",
            title="Test",
            source_branch="feat",
            target_branch="main",
            description="A description",
            labels=["bug", "fix"],
            assignee_ids=[1, 2],
        )

    async def test_dry_run_includes_optional_fields_in_body(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.create_mr(
            title="Test",
            source_branch="feat",
            target_branch="main",
            description="desc",
            labels=["a", "b"],
            assignees=[5],
            dry_run=True,
        )

        assert isinstance(result, DryRunResult)
        assert result.body["description"] == "desc"
        assert result.body["labels"] == "a,b"
        assert result.body["assignee_ids"] == [5]


class TestMergeMrForceOption:
    """Tests for merge_mr force flag."""

    async def test_force_merge_dry_run_includes_flag(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.merge_mr(10, force=True, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body is not None
        assert result.body["merge_when_pipeline_succeeds"] is False

    async def test_merge_no_options_dry_run_body_is_none(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.merge_mr(10, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body is None


class TestUpdateMrEmptyFields:
    """Tests for update_mr edge cases."""

    async def test_dry_run_no_fields_body_is_none(self) -> None:
        client = _make_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.update_mr(10, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body is None


class TestListMrsFilterParams:
    """Tests for list_mrs with filter parameters."""

    async def test_passes_all_filter_params(self) -> None:
        client = _make_client()
        client.merge_requests.list.return_value = PaginatedResponse[MergeRequest](
            items=[], page=1, per_page=20, total=0, total_pages=1, next_page=None
        )
        service = MergeRequestService(client, _make_config(), project="group/proj")

        await service.list_mrs(
            state="merged",
            labels=["bug"],
            author="janedoe",
            scope="assigned_to_me",
            search="fix",
            per_page=50,
            page=3,
        )

        client.merge_requests.list.assert_called_once_with(
            "group/proj",
            state="merged",
            labels=["bug"],
            author_username="janedoe",
            scope="assigned_to_me",
            search="fix",
            per_page=50,
            page=3,
        )

    async def test_all_pages_single_page_result(self) -> None:
        """When all_pages=True but only one page exists, returns correctly."""
        client = _make_client()
        mr = _make_mr()
        client.merge_requests.list.return_value = PaginatedResponse[MergeRequest](
            items=[mr], page=1, per_page=20, total=1, total_pages=1, next_page=None
        )
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.list_mrs(all_pages=True)

        assert len(result.items) == 1
        assert result.total_pages == 1
        assert result.next_page is None
        assert client.merge_requests.list.call_count == 1

    async def test_all_pages_empty_result(self) -> None:
        """When all_pages=True but no items, returns empty."""
        client = _make_client()
        client.merge_requests.list.return_value = PaginatedResponse[MergeRequest](
            items=[], page=1, per_page=20, total=0, total_pages=1, next_page=None
        )
        service = MergeRequestService(client, _make_config(), project="group/proj")

        result = await service.list_mrs(all_pages=True)

        assert len(result.items) == 0
        assert result.total == 0
