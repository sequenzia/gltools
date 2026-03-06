"""Tests for MergeRequestManager."""

from __future__ import annotations

import httpx
import pytest
import respx

from gltools.client.exceptions import NotFoundError
from gltools.client.http import GitLabHTTPClient, RetryConfig
from gltools.client.managers.merge_requests import MergeRequestManager
from gltools.models import DiffFile, MergeRequest, Note, PaginatedResponse


@pytest.fixture
def base_url() -> str:
    return "https://gitlab.example.com/api/v4"


@pytest.fixture
def client() -> GitLabHTTPClient:
    return GitLabHTTPClient(
        host="https://gitlab.example.com",
        token="glpat-test-token",
        retry_config=RetryConfig(max_retries=0),
    )


@pytest.fixture
def manager(client: GitLabHTTPClient) -> MergeRequestManager:
    return MergeRequestManager(client)


# Sample response data

MR_DATA = {
    "id": 1,
    "iid": 42,
    "title": "Fix the thing",
    "description": "Detailed description",
    "state": "opened",
    "source_branch": "fix-thing",
    "target_branch": "main",
    "author": {"id": 10, "username": "dev", "name": "Dev User"},
    "labels": ["bug"],
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-01-16T12:00:00Z",
}

DIFF_DATA = {
    "old_path": "src/app.py",
    "new_path": "src/app.py",
    "diff": "@@ -1,3 +1,4 @@\n+new line",
    "new_file": False,
    "renamed_file": False,
    "deleted_file": False,
}

NOTE_DATA = {
    "id": 100,
    "body": "Looks good!",
    "author": {"id": 10, "username": "dev", "name": "Dev User"},
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-01-15T10:00:00Z",
    "system": False,
}

PAGINATION_HEADERS = {
    "X-Page": "1",
    "X-Per-Page": "20",
    "X-Total": "2",
    "X-Total-Pages": "1",
    "X-Next-Page": "",
}


class TestList:
    @respx.mock
    async def test_list_returns_paginated_response(
        self, manager: MergeRequestManager, base_url: str
    ) -> None:
        respx.get(f"{base_url}/projects/1/merge_requests").mock(
            return_value=httpx.Response(200, json=[MR_DATA], headers=PAGINATION_HEADERS)
        )
        result = await manager.list(1)
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], MergeRequest)
        assert result.items[0].iid == 42
        assert result.page == 1
        assert result.per_page == 20
        assert result.total == 2

    @respx.mock
    async def test_list_with_filters(self, manager: MergeRequestManager, base_url: str) -> None:
        route = respx.get(f"{base_url}/projects/1/merge_requests").mock(
            return_value=httpx.Response(200, json=[], headers=PAGINATION_HEADERS)
        )
        await manager.list(
            1,
            state="opened",
            labels=["bug", "urgent"],
            author_username="dev",
            scope="created_by_me",
            search="fix",
            per_page=10,
            page=2,
        )
        request = route.calls[0].request
        assert request.url.params["state"] == "opened"
        assert request.url.params["labels"] == "bug,urgent"
        assert request.url.params["author_username"] == "dev"
        assert request.url.params["scope"] == "created_by_me"
        assert request.url.params["search"] == "fix"
        assert request.url.params["per_page"] == "10"
        assert request.url.params["page"] == "2"

    @respx.mock
    async def test_list_empty_results(self, manager: MergeRequestManager, base_url: str) -> None:
        headers = {**PAGINATION_HEADERS, "X-Total": "0", "X-Total-Pages": "0"}
        respx.get(f"{base_url}/projects/1/merge_requests").mock(
            return_value=httpx.Response(200, json=[], headers=headers)
        )
        result = await manager.list(1)
        assert result.items == []
        assert result.total == 0

    @respx.mock
    async def test_list_with_string_project_id(self, manager: MergeRequestManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/my-group%2Fmy-project/merge_requests").mock(
            return_value=httpx.Response(200, json=[], headers=PAGINATION_HEADERS)
        )
        result = await manager.list("my-group/my-project")
        assert isinstance(result, PaginatedResponse)


class TestGet:
    @respx.mock
    async def test_get_returns_merge_request(self, manager: MergeRequestManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/merge_requests/42").mock(
            return_value=httpx.Response(200, json=MR_DATA)
        )
        result = await manager.get(1, 42)
        assert isinstance(result, MergeRequest)
        assert result.iid == 42
        assert result.title == "Fix the thing"

    @respx.mock
    async def test_get_not_found_raises(self, manager: MergeRequestManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/merge_requests/999").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError):
            await manager.get(1, 999)


class TestCreate:
    @respx.mock
    async def test_create_sends_correct_body(self, manager: MergeRequestManager, base_url: str) -> None:
        route = respx.post(f"{base_url}/projects/1/merge_requests").mock(
            return_value=httpx.Response(201, json=MR_DATA)
        )
        result = await manager.create(
            1,
            title="Fix the thing",
            source_branch="fix-thing",
            target_branch="main",
            description="Detailed description",
            labels=["bug"],
            assignee_ids=[10],
        )
        assert isinstance(result, MergeRequest)
        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        assert body["title"] == "Fix the thing"
        assert body["source_branch"] == "fix-thing"
        assert body["target_branch"] == "main"
        assert body["description"] == "Detailed description"
        assert body["labels"] == "bug"
        assert body["assignee_ids"] == [10]

    @respx.mock
    async def test_create_minimal(self, manager: MergeRequestManager, base_url: str) -> None:
        route = respx.post(f"{base_url}/projects/1/merge_requests").mock(
            return_value=httpx.Response(201, json=MR_DATA)
        )
        await manager.create(1, title="T", source_branch="src", target_branch="main")
        import json

        body = json.loads(route.calls[0].request.content)
        assert "description" not in body
        assert "labels" not in body
        assert "assignee_ids" not in body


class TestUpdate:
    @respx.mock
    async def test_update_sends_fields(self, manager: MergeRequestManager, base_url: str) -> None:
        route = respx.put(f"{base_url}/projects/1/merge_requests/42").mock(
            return_value=httpx.Response(200, json=MR_DATA)
        )
        result = await manager.update(1, 42, title="New title", description="New desc")
        assert isinstance(result, MergeRequest)
        import json

        body = json.loads(route.calls[0].request.content)
        assert body["title"] == "New title"
        assert body["description"] == "New desc"


class TestMerge:
    @respx.mock
    async def test_merge_default_options(self, manager: MergeRequestManager, base_url: str) -> None:
        merged = {**MR_DATA, "state": "merged"}
        route = respx.put(f"{base_url}/projects/1/merge_requests/42/merge").mock(
            return_value=httpx.Response(200, json=merged)
        )
        result = await manager.merge(1, 42)
        assert isinstance(result, MergeRequest)
        assert result.state == "merged"
        # No body when defaults
        request = route.calls[0].request
        assert request.content == b""

    @respx.mock
    async def test_merge_with_squash_and_delete_branch(
        self, manager: MergeRequestManager, base_url: str
    ) -> None:
        merged = {**MR_DATA, "state": "merged"}
        route = respx.put(f"{base_url}/projects/1/merge_requests/42/merge").mock(
            return_value=httpx.Response(200, json=merged)
        )
        await manager.merge(1, 42, squash=True, delete_source_branch=True)
        import json

        body = json.loads(route.calls[0].request.content)
        assert body["squash"] is True
        assert body["should_remove_source_branch"] is True


class TestApprove:
    @respx.mock
    async def test_approve_sends_post(self, manager: MergeRequestManager, base_url: str) -> None:
        route = respx.post(f"{base_url}/projects/1/merge_requests/42/approve").mock(
            return_value=httpx.Response(201, json={})
        )
        result = await manager.approve(1, 42)
        assert result is None
        assert route.called


class TestDiff:
    @respx.mock
    async def test_diff_returns_list(self, manager: MergeRequestManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/merge_requests/42/diffs").mock(
            return_value=httpx.Response(200, json=[DIFF_DATA, DIFF_DATA])
        )
        result = await manager.diff(1, 42)
        assert len(result) == 2
        assert all(isinstance(d, DiffFile) for d in result)
        assert result[0].old_path == "src/app.py"


class TestNotes:
    @respx.mock
    async def test_notes_returns_list(self, manager: MergeRequestManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/merge_requests/42/notes").mock(
            return_value=httpx.Response(200, json=[NOTE_DATA])
        )
        result = await manager.notes(1, 42)
        assert len(result) == 1
        assert isinstance(result[0], Note)
        assert result[0].body == "Looks good!"

    @respx.mock
    async def test_create_note_sends_body(self, manager: MergeRequestManager, base_url: str) -> None:
        route = respx.post(f"{base_url}/projects/1/merge_requests/42/notes").mock(
            return_value=httpx.Response(201, json=NOTE_DATA)
        )
        result = await manager.create_note(1, 42, "Looks good!")
        assert isinstance(result, Note)
        import json

        body = json.loads(route.calls[0].request.content)
        assert body["body"] == "Looks good!"


class TestErrorHandling:
    @respx.mock
    async def test_404_raises_not_found(self, manager: MergeRequestManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/merge_requests/999").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError):
            await manager.get(1, 999)

    @respx.mock
    async def test_403_raises_forbidden_error(self, manager: MergeRequestManager, base_url: str) -> None:
        from gltools.client.exceptions import ForbiddenError

        respx.post(f"{base_url}/projects/1/merge_requests/42/approve").mock(
            return_value=httpx.Response(403, json={"message": "403 Forbidden"})
        )
        with pytest.raises(ForbiddenError, match="Permission denied"):
            await manager.approve(1, 42)
