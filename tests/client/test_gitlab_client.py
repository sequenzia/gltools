"""Tests for GitLabClient facade."""

import pytest

from gltools.client import GitLabClient, GitLabHTTPClient
from gltools.client.managers import IssueManager, JobManager, MergeRequestManager, PipelineManager


class TestGitLabClientInit:
    """Tests for GitLabClient initialization."""

    def test_creates_all_resource_managers(self) -> None:
        """All four resource managers should be accessible as typed attributes."""
        client = GitLabClient(host="https://gitlab.example.com", token="test-token")

        assert isinstance(client.merge_requests, MergeRequestManager)
        assert isinstance(client.issues, IssueManager)
        assert isinstance(client.pipelines, PipelineManager)
        assert isinstance(client.jobs, JobManager)

    def test_accepts_pre_configured_http_client(self) -> None:
        """Constructor should accept an existing GitLabHTTPClient."""
        http = GitLabHTTPClient(host="https://gitlab.example.com", token="test-token")
        client = GitLabClient(host="", token="", http_client=http)

        assert client._http is http

    def test_creates_http_client_from_params(self) -> None:
        """Constructor should create a new HTTP client when none is provided."""
        client = GitLabClient(host="https://gitlab.example.com", token="test-token")

        assert isinstance(client._http, GitLabHTTPClient)
        assert client._http.base_url == "https://gitlab.example.com/api/v4"


class TestGitLabClientContextManager:
    """Tests for async context manager support."""

    @pytest.mark.anyio()
    async def test_async_context_manager_enters_and_exits(self) -> None:
        """Client should work as an async context manager."""
        async with GitLabClient(host="https://gitlab.example.com", token="test-token") as client:
            assert isinstance(client, GitLabClient)
            assert client._http._client is not None
            assert not client._http._client.is_closed

    @pytest.mark.anyio()
    async def test_async_context_manager_closes_on_exit(self) -> None:
        """HTTP client should be closed when context manager exits."""
        client = GitLabClient(host="https://gitlab.example.com", token="test-token")

        async with client:
            http_client = client._http._client
            assert http_client is not None

        assert client._http._client is None

    @pytest.mark.anyio()
    async def test_close_without_context_manager(self) -> None:
        """Client should work without context manager but require manual close."""
        client = GitLabClient(host="https://gitlab.example.com", token="test-token")

        # Using without context manager still works
        assert isinstance(client.merge_requests, MergeRequestManager)

        # Manual close works
        await client.close()
        assert client._http._client is None

    @pytest.mark.anyio()
    async def test_close_idempotent(self) -> None:
        """Calling close multiple times should not raise."""
        client = GitLabClient(host="https://gitlab.example.com", token="test-token")
        await client.close()
        await client.close()


class TestGitLabClientExports:
    """Tests for client module exports."""

    def test_gitlab_client_importable_from_client_package(self) -> None:
        """GitLabClient should be importable from gltools.client."""
        from gltools.client import GitLabClient as Imported

        assert Imported is GitLabClient

    def test_http_client_importable_from_client_package(self) -> None:
        """GitLabHTTPClient should be importable from gltools.client."""
        from gltools.client import GitLabHTTPClient as Imported

        assert Imported is GitLabHTTPClient
