"""Tests for IssueManager."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from gltools.client.exceptions import NotFoundError
from gltools.client.http import GitLabHTTPClient, RetryConfig
from gltools.client.managers.issues import IssueManager
from gltools.models import Issue, Note, PaginatedResponse


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
def manager(client: GitLabHTTPClient) -> IssueManager:
    return IssueManager(client)


# Sample response data

ISSUE_DATA = {
    "id": 1,
    "iid": 10,
    "title": "Bug in login",
    "description": "Login fails intermittently",
    "state": "opened",
    "author": {"id": 5, "username": "alice", "name": "Alice"},
    "assignee": {"id": 6, "username": "bob", "name": "Bob"},
    "labels": ["bug", "critical"],
    "milestone": "v1.0",
    "created_at": "2026-01-10T08:00:00Z",
    "updated_at": "2026-01-11T09:00:00Z",
    "closed_at": None,
}

NOTE_DATA = {
    "id": 200,
    "body": "I can reproduce this.",
    "author": {"id": 5, "username": "alice", "name": "Alice"},
    "created_at": "2026-01-10T10:00:00Z",
    "updated_at": "2026-01-10T10:00:00Z",
    "system": False,
}

PAGINATION_HEADERS = {
    "X-Page": "1",
    "X-Per-Page": "20",
    "X-Total": "3",
    "X-Total-Pages": "1",
    "X-Next-Page": "",
}


class TestList:
    @respx.mock
    async def test_list_returns_paginated_response(self, manager: IssueManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/issues").mock(
            return_value=httpx.Response(200, json=[ISSUE_DATA], headers=PAGINATION_HEADERS)
        )
        result = await manager.list(1)
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Issue)
        assert result.items[0].iid == 10
        assert result.page == 1
        assert result.per_page == 20
        assert result.total == 3

    @respx.mock
    async def test_list_with_all_filters(self, manager: IssueManager, base_url: str) -> None:
        route = respx.get(f"{base_url}/projects/1/issues").mock(
            return_value=httpx.Response(200, json=[], headers=PAGINATION_HEADERS)
        )
        await manager.list(
            1,
            state="opened",
            labels=["bug", "urgent"],
            assignee_username="bob",
            milestone="v1.0",
            scope="assigned_to_me",
            search="login",
            per_page=10,
            page=2,
        )
        request = route.calls[0].request
        assert request.url.params["state"] == "opened"
        assert request.url.params["labels"] == "bug,urgent"
        assert request.url.params["assignee_username"] == "bob"
        assert request.url.params["milestone"] == "v1.0"
        assert request.url.params["scope"] == "assigned_to_me"
        assert request.url.params["search"] == "login"
        assert request.url.params["per_page"] == "10"
        assert request.url.params["page"] == "2"

    @respx.mock
    async def test_list_empty_results(self, manager: IssueManager, base_url: str) -> None:
        headers = {**PAGINATION_HEADERS, "X-Total": "0", "X-Total-Pages": "0"}
        respx.get(f"{base_url}/projects/1/issues").mock(
            return_value=httpx.Response(200, json=[], headers=headers)
        )
        result = await manager.list(1)
        assert result.items == []
        assert result.total == 0

    @respx.mock
    async def test_list_with_string_project_id(self, manager: IssueManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/my-group%2Fmy-project/issues").mock(
            return_value=httpx.Response(200, json=[], headers=PAGINATION_HEADERS)
        )
        result = await manager.list("my-group/my-project")
        assert isinstance(result, PaginatedResponse)


class TestGet:
    @respx.mock
    async def test_get_returns_issue(self, manager: IssueManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/issues/10").mock(
            return_value=httpx.Response(200, json=ISSUE_DATA)
        )
        result = await manager.get(1, 10)
        assert isinstance(result, Issue)
        assert result.iid == 10
        assert result.title == "Bug in login"
        assert result.state == "opened"

    @respx.mock
    async def test_get_not_found_raises_with_clear_message(self, manager: IssueManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/issues/999").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError, match="Issue"):
            await manager.get(1, 999)

    @respx.mock
    async def test_get_confidential_not_accessible_returns_404(self, manager: IssueManager, base_url: str) -> None:
        """Confidential issue not accessible returns 404, not leaking existence."""
        respx.get(f"{base_url}/projects/1/issues/50").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError, match="Issue"):
            await manager.get(1, 50)


class TestCreate:
    @respx.mock
    async def test_create_sends_correct_body(self, manager: IssueManager, base_url: str) -> None:
        route = respx.post(f"{base_url}/projects/1/issues").mock(
            return_value=httpx.Response(201, json=ISSUE_DATA)
        )
        result = await manager.create(
            1,
            title="Bug in login",
            description="Login fails intermittently",
            labels=["bug", "critical"],
            assignee_ids=[6],
            milestone_id=1,
            due_date="2026-02-01",
        )
        assert isinstance(result, Issue)
        body = json.loads(route.calls[0].request.content)
        assert body["title"] == "Bug in login"
        assert body["description"] == "Login fails intermittently"
        assert body["labels"] == "bug,critical"
        assert body["assignee_ids"] == [6]
        assert body["milestone_id"] == 1
        assert body["due_date"] == "2026-02-01"

    @respx.mock
    async def test_create_minimal(self, manager: IssueManager, base_url: str) -> None:
        route = respx.post(f"{base_url}/projects/1/issues").mock(
            return_value=httpx.Response(201, json=ISSUE_DATA)
        )
        await manager.create(1, title="Simple issue")
        body = json.loads(route.calls[0].request.content)
        assert body["title"] == "Simple issue"
        assert "description" not in body
        assert "labels" not in body
        assert "assignee_ids" not in body
        assert "milestone_id" not in body
        assert "due_date" not in body


class TestUpdate:
    @respx.mock
    async def test_update_sends_fields(self, manager: IssueManager, base_url: str) -> None:
        route = respx.put(f"{base_url}/projects/1/issues/10").mock(
            return_value=httpx.Response(200, json=ISSUE_DATA)
        )
        result = await manager.update(1, 10, title="Updated title", description="New desc")
        assert isinstance(result, Issue)
        body = json.loads(route.calls[0].request.content)
        assert body["title"] == "Updated title"
        assert body["description"] == "New desc"

    @respx.mock
    async def test_update_not_found_raises(self, manager: IssueManager, base_url: str) -> None:
        respx.put(f"{base_url}/projects/1/issues/999").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError, match="Issue"):
            await manager.update(1, 999, title="nope")


class TestClose:
    @respx.mock
    async def test_close_sends_state_event_close(self, manager: IssueManager, base_url: str) -> None:
        closed = {**ISSUE_DATA, "state": "closed", "closed_at": "2026-01-12T00:00:00Z"}
        route = respx.put(f"{base_url}/projects/1/issues/10").mock(
            return_value=httpx.Response(200, json=closed)
        )
        result = await manager.close(1, 10)
        assert isinstance(result, Issue)
        assert result.state == "closed"
        body = json.loads(route.calls[0].request.content)
        assert body["state_event"] == "close"


class TestReopen:
    @respx.mock
    async def test_reopen_sends_state_event_reopen(self, manager: IssueManager, base_url: str) -> None:
        reopened = {**ISSUE_DATA, "state": "opened"}
        route = respx.put(f"{base_url}/projects/1/issues/10").mock(
            return_value=httpx.Response(200, json=reopened)
        )
        result = await manager.reopen(1, 10)
        assert isinstance(result, Issue)
        assert result.state == "opened"
        body = json.loads(route.calls[0].request.content)
        assert body["state_event"] == "reopen"


class TestNotes:
    @respx.mock
    async def test_notes_returns_list(self, manager: IssueManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/issues/10/notes").mock(
            return_value=httpx.Response(200, json=[NOTE_DATA])
        )
        result = await manager.notes(1, 10)
        assert len(result) == 1
        assert isinstance(result[0], Note)
        assert result[0].body == "I can reproduce this."

    @respx.mock
    async def test_notes_not_found_raises(self, manager: IssueManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/issues/999/notes").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError, match="Issue"):
            await manager.notes(1, 999)

    @respx.mock
    async def test_create_note_sends_body(self, manager: IssueManager, base_url: str) -> None:
        route = respx.post(f"{base_url}/projects/1/issues/10/notes").mock(
            return_value=httpx.Response(201, json=NOTE_DATA)
        )
        result = await manager.create_note(1, 10, "I can reproduce this.")
        assert isinstance(result, Note)
        body = json.loads(route.calls[0].request.content)
        assert body["body"] == "I can reproduce this."


class TestIssueWithLinkedMR:
    @respx.mock
    async def test_issue_with_extra_fields_parsed(self, manager: IssueManager, base_url: str) -> None:
        """Issue with linked MR or extra fields is handled via extra='ignore'."""
        data = {
            **ISSUE_DATA,
            "merge_requests_count": 2,
            "web_url": "https://gitlab.example.com/project/-/issues/10",
            "confidential": False,
        }
        respx.get(f"{base_url}/projects/1/issues/10").mock(
            return_value=httpx.Response(200, json=data)
        )
        result = await manager.get(1, 10)
        assert isinstance(result, Issue)
        assert result.iid == 10
