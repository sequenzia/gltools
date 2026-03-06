"""Tests for JobManager."""

from __future__ import annotations

import httpx
import pytest
import respx

from gltools.client.exceptions import NotFoundError
from gltools.client.http import GitLabHTTPClient, RetryConfig
from gltools.client.managers.jobs import JobManager
from gltools.models.job import Job


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
def manager(client: GitLabHTTPClient) -> JobManager:
    return JobManager(client)


JOB_DATA = {
    "id": 1001,
    "name": "rspec",
    "stage": "test",
    "status": "success",
    "duration": 120.5,
    "failure_reason": None,
    "web_url": "https://gitlab.com/project/-/jobs/1001",
}


class TestList:
    @respx.mock
    async def test_list_returns_jobs_for_pipeline(
        self, manager: JobManager, base_url: str
    ) -> None:
        job2 = {**JOB_DATA, "id": 1002, "name": "lint", "stage": "lint"}
        respx.get(f"{base_url}/projects/1/pipelines/100/jobs").mock(
            return_value=httpx.Response(200, json=[JOB_DATA, job2])
        )
        result = await manager.list(1, 100)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(j, Job) for j in result)
        assert result[0].id == 1001
        assert result[1].id == 1002

    @respx.mock
    async def test_list_empty_pipeline(self, manager: JobManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/pipelines/100/jobs").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await manager.list(1, 100)
        assert result == []

    @respx.mock
    async def test_list_includes_manual_jobs(self, manager: JobManager, base_url: str) -> None:
        manual_job = {**JOB_DATA, "id": 1003, "name": "deploy", "stage": "deploy", "status": "manual"}
        respx.get(f"{base_url}/projects/1/pipelines/100/jobs").mock(
            return_value=httpx.Response(200, json=[JOB_DATA, manual_job])
        )
        result = await manager.list(1, 100)
        assert len(result) == 2
        assert result[1].status == "manual"


class TestGet:
    @respx.mock
    async def test_get_returns_job(self, manager: JobManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/jobs/1001").mock(
            return_value=httpx.Response(200, json=JOB_DATA)
        )
        result = await manager.get(1, 1001)
        assert isinstance(result, Job)
        assert result.id == 1001
        assert result.name == "rspec"

    @respx.mock
    async def test_get_not_found_raises(self, manager: JobManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/jobs/9999").mock(
            return_value=httpx.Response(404, json={"message": "404 Not Found"})
        )
        with pytest.raises(NotFoundError, match="Job"):
            await manager.get(1, 9999)


class TestLogs:
    @respx.mock
    async def test_logs_streams_output(self, manager: JobManager, base_url: str) -> None:
        content = b"Step 1: Building...\nStep 2: Testing...\nStep 3: Done!\n"
        respx.get(f"{base_url}/projects/1/jobs/1001/trace").mock(
            return_value=httpx.Response(200, content=content)
        )
        chunks: list[bytes] = []
        async with manager.logs(1, 1001) as stream:
            async for chunk in stream:
                chunks.append(chunk)
        assert b"".join(chunks) == content

    @respx.mock
    async def test_logs_not_found_raises(self, manager: JobManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/jobs/9999/trace").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(NotFoundError, match="Job"):
            async with manager.logs(1, 9999) as stream:
                async for _ in stream:
                    pass


class TestArtifacts:
    @respx.mock
    async def test_artifacts_streams_download(self, manager: JobManager, base_url: str) -> None:
        content = b"\x50\x4b\x03\x04fake-zip-data"
        respx.get(f"{base_url}/projects/1/jobs/1001/artifacts").mock(
            return_value=httpx.Response(200, content=content)
        )
        chunks: list[bytes] = []
        async with manager.artifacts(1, 1001) as stream:
            async for chunk in stream:
                chunks.append(chunk)
        assert b"".join(chunks) == content

    @respx.mock
    async def test_artifacts_not_found_raises(self, manager: JobManager, base_url: str) -> None:
        respx.get(f"{base_url}/projects/1/jobs/9999/artifacts").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(NotFoundError, match="Job"):
            async with manager.artifacts(1, 9999) as stream:
                async for _ in stream:
                    pass
