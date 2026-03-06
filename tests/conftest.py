"""Shared test fixtures and configuration."""

import pytest
import respx

from gltools.client.http import GitLabHTTPClient


@pytest.fixture()
def mock_router() -> respx.MockRouter:
    """Provide a respx mock router for mocking httpx requests."""
    with respx.mock(base_url="https://gitlab.example.com/api/v4") as router:
        yield router


@pytest.fixture()
def http_client() -> GitLabHTTPClient:
    """Provide a GitLabHTTPClient configured with a mocked base URL."""
    return GitLabHTTPClient(
        host="https://gitlab.example.com",
        token="test-token-000",
    )
