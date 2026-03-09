"""Tests for PipelineManager."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from gltools.client.exceptions import NotFoundError
from gltools.client.http import GitLabHTTPClient, RetryConfig
from gltools.client.managers.pipelines import PipelineManager
from gltools.models.output import PaginatedResponse
from gltools.models.pipeline import Pipeline


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
def manager(client: GitLabHTTPClient) -> PipelineManager:
    return PipelineManager(client)


PIPELINE_DATA = {
    "id": 100,
    "status": "success",
    "ref": "main",
    "sha": "abc123def456",
    "source": "push",
    "created_at": "2026-01-15T10:30:00Z",
    "finished_at": "2026-01-15T10:35:00Z",
    "duration": 300.0,
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
        self, manager: PipelineManager, base_url: str
    ) -> None:
        respx.get(f"{base_url}/projects/1/pipelines").mock(
            return_value=httpx.Response(200, json=[PIPELINE_DATA], headers=PAGINATION_HEADERS)
        )
        result = await manager.list(1)
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Pipeline)
        assert result.items[0].id == 100
        assert result.items[0].status == "success"
        assert result.page == 1
        assert result.per_page == 20
        assert result.total == 2

    @respx.mock
    async def test_list_with_status_filter(self, manager: PipelineManager, base_url: str) -> None:
        route = respx.get(f"{base_url}/projects/1/pipelines").mock(
            return_value=httpx.Response(200, json=[], headers=PAGINATION_HEADERS)
        )
        await manager.list(1, status="running")
        request = route.calls[0].request
        assert request.url.params["status"] == "running"

    @respx.mock
    async def test_list_with_ref_filter(self, manager: PipelineManager, base_url: str) -> None:
        route = respx.get(f"{base_url}/projects/1/pipelines").mock(
            return_value=httpx.Response(200, json=[], headers=PAGINATION_HEADERS)
        )
        await manager.list(1, ref="feature-branch")
        request = route.calls[0].request
        assert request.url.params["ref"] == "feature-branch"

    @respx.mock
    async def test_list_with_source_filter(self, manager: PipelineManager, base_url: str) -> None:
        route = respx.get(f"{base_url}/projects/1/pipelines").mock(
            return_value=httpx.Response(200, json=[], headers=PAGINATION_HEADERS)
        )
        await manager.list(1, source="merge_request_event")
        request = route.calls[0].request
        assert request.url.params["source"] == "merge_request_event"

    @respx.mock
    async def test_list_with_all_filters(self, manager: PipelineManager, base_url: str) -> None:
        route = respx.get(f"{base_url}/projects/1/pipelines").mock(
            return_value=httpx.Response(200, json=[], headers=PAGINATION_HEADERS)
        )
        await manager.list(
            1,
            status="success",
            ref="main",
            source="push",
            per_page=10,
            page=2,
        )
        request = route.calls[0].request
        assert request.url.params["status"] == "success"
        assert request.url.params["ref"] == "main"
        assert request.url.params["source"] == "push"
        assert request.url.params["per_page"] == "10"
        assert request.url.params["page"] == "2"

    @respx.mock
    async def test_list_empty_results(self, manager: PipelineManager, base_url: str) -> None:
        headers = {**PAGINATION_HEADERS, "X-Total": "0", "X-Total-Pages": "0"}
        respx.get(f"{base_url}/projects/1/pipelines").mock(
            return_value=httpx.Response(200, json=[], headers=headers)
        )
        result = await manager.list(1)
        assert result.items == []
        assert result.total == 0

    @respx.mock
    async def test_list_pipelines_with_manual_status(
        self, manager: PipelineManager, base_url: str
    ) -> None:
        manual_pipeline = {**PIPELINE_DATA, "id": 200, "status": "manual"}
        respx.get(f"{base_url}/projects/1/pipelines").mock(
            return_value=httpx.Response(200, json=[manual_pipeline], headers=PAGINATION_HEADERS)
        )
        result = await manager.list(1)
        assert result.items[0].status == "manual"

    @respx.mock
    async def test_list_with_string_project_id(self, manager: PipelineManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/my-group%2Fmy-project/pipelines").mock(
            return_value=httpx.Response(200, json=[], headers=PAGINATION_HEADERS)
        )
        result = await manager.list("my-group/my-project")
        assert isinstance(result, PaginatedResponse)


class TestGet:
    @respx.mock
    async def test_get_returns_pipeline(self, manager: PipelineManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/pipelines/100").mock(
            return_value=httpx.Response(200, json=PIPELINE_DATA)
        )
        result = await manager.get(1, 100)
        assert isinstance(result, Pipeline)
        assert result.id == 100
        assert result.ref == "main"

    @respx.mock
    async def test_get_not_found_raises(self, manager: PipelineManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/pipelines/999").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError, match="Pipeline"):
            await manager.get(1, 999)


class TestCreate:
    @respx.mock
    async def test_create_triggers_new_pipeline(
        self, manager: PipelineManager, base_url: str
    ) -> None:
        route = respx.post(f"{base_url}/projects/1/pipeline").mock(
            return_value=httpx.Response(201, json=PIPELINE_DATA)
        )
        result = await manager.create(1, ref="main")
        assert isinstance(result, Pipeline)
        assert result.id == 100
        body = json.loads(route.calls[0].request.content)
        assert body["ref"] == "main"


class TestRetry:
    @respx.mock
    async def test_retry_pipeline(self, manager: PipelineManager, base_url: str) -> None:
        route = respx.post(f"{base_url}/projects/1/pipelines/100/retry").mock(
            return_value=httpx.Response(201, json=PIPELINE_DATA)
        )
        result = await manager.retry(1, 100)
        assert isinstance(result, Pipeline)
        assert route.called

    @respx.mock
    async def test_retry_not_found_raises(self, manager: PipelineManager, base_url: str) -> None:
        respx.post(f"{base_url}/projects/1/pipelines/999/retry").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError, match="Pipeline"):
            await manager.retry(1, 999)


class TestCancel:
    @respx.mock
    async def test_cancel_pipeline(self, manager: PipelineManager, base_url: str) -> None:
        cancelled = {**PIPELINE_DATA, "status": "canceled"}
        route = respx.post(f"{base_url}/projects/1/pipelines/100/cancel").mock(
            return_value=httpx.Response(200, json=cancelled)
        )
        result = await manager.cancel(1, 100)
        assert isinstance(result, Pipeline)
        assert result.status == "canceled"
        assert route.called

    @respx.mock
    async def test_cancel_not_found_raises(self, manager: PipelineManager, base_url: str) -> None:
        respx.post(f"{base_url}/projects/1/pipelines/999/cancel").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError, match="Pipeline"):
            await manager.cancel(1, 999)
