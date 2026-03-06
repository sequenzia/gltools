"""Tests for GitLabHTTPClient."""

from __future__ import annotations

import httpx
import pytest
import respx

from gltools.client.exceptions import (
    AuthenticationError,
    ConnectionError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError,
    _mask_token,
)
from gltools.client.http import GitLabHTTPClient, PaginationInfo, RetryConfig


@pytest.fixture
def base_url() -> str:
    return "https://gitlab.example.com/api/v4"


@pytest.fixture
def client() -> GitLabHTTPClient:
    return GitLabHTTPClient(
        host="https://gitlab.example.com",
        token="glpat-test-token-12345",
        retry_config=RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.1),
    )


# --- Token masking ---


class TestTokenMasking:
    def test_mask_private_token_header(self) -> None:
        text = "PRIVATE-TOKEN: glpat-abc123"
        assert "glpat-abc123" not in _mask_token(text)
        assert "[MASKED]" in _mask_token(text)

    def test_mask_glpat_token(self) -> None:
        text = "Token is glpat-secret123 in message"
        result = _mask_token(text)
        assert "glpat-secret123" not in result
        assert "[MASKED]" in result

    def test_no_token_unchanged(self) -> None:
        text = "Normal log message without tokens"
        assert _mask_token(text) == text


# --- Base URL construction ---


class TestBaseURL:
    def test_constructs_api_v4_url(self, client: GitLabHTTPClient) -> None:
        assert client.base_url == "https://gitlab.example.com/api/v4"

    def test_strips_trailing_slash(self) -> None:
        c = GitLabHTTPClient(host="https://gitlab.example.com/", token="tok")
        assert c.base_url == "https://gitlab.example.com/api/v4"


# --- Authentication header ---


class TestAuthentication:
    @respx.mock
    async def test_sends_private_token_header(self, client: GitLabHTTPClient, base_url: str) -> None:
        route = respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={}))
        await client.get("/test")
        assert route.called
        request = route.calls[0].request
        assert request.headers["PRIVATE-TOKEN"] == "glpat-test-token-12345"

    @respx.mock
    async def test_post_sends_private_token_header(self, client: GitLabHTTPClient, base_url: str) -> None:
        route = respx.post(f"{base_url}/test").mock(return_value=httpx.Response(201, json={}))
        await client.post("/test", title="foo")
        assert route.called
        request = route.calls[0].request
        assert request.headers["PRIVATE-TOKEN"] == "glpat-test-token-12345"


# --- HTTP methods ---


class TestHTTPMethods:
    @respx.mock
    async def test_get(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/projects").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
        response = await client.get("/projects")
        assert response.status_code == 200
        assert response.json() == [{"id": 1}]

    @respx.mock
    async def test_get_with_params(self, client: GitLabHTTPClient, base_url: str) -> None:
        route = respx.get(f"{base_url}/projects").mock(return_value=httpx.Response(200, json=[]))
        await client.get("/projects", per_page=10, page=2)
        assert route.called
        request = route.calls[0].request
        assert request.url.params["per_page"] == "10"
        assert request.url.params["page"] == "2"

    @respx.mock
    async def test_post(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.post(f"{base_url}/projects/1/merge_requests").mock(
            return_value=httpx.Response(201, json={"iid": 42})
        )
        response = await client.post("/projects/1/merge_requests", title="New MR", source_branch="feature")
        assert response.status_code == 201
        assert response.json() == {"iid": 42}

    @respx.mock
    async def test_put(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.put(f"{base_url}/projects/1/merge_requests/42").mock(
            return_value=httpx.Response(200, json={"iid": 42, "title": "Updated"})
        )
        response = await client.put("/projects/1/merge_requests/42", title="Updated")
        assert response.status_code == 200

    @respx.mock
    async def test_delete(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.delete(f"{base_url}/projects/1/merge_requests/42").mock(
            return_value=httpx.Response(204)
        )
        response = await client.delete("/projects/1/merge_requests/42")
        assert response.status_code == 204


# --- Streaming ---


class TestStreaming:
    @respx.mock
    async def test_stream_get_yields_chunks(self, client: GitLabHTTPClient, base_url: str) -> None:
        content = b"line1\nline2\nline3\n"
        respx.get(f"{base_url}/projects/1/jobs/10/trace").mock(
            return_value=httpx.Response(200, content=content)
        )
        chunks: list[bytes] = []
        async with client.stream_get("/projects/1/jobs/10/trace") as stream:
            async for chunk in stream:
                chunks.append(chunk)
        assert b"".join(chunks) == content

    @respx.mock
    async def test_stream_get_401_raises_auth_error(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(401))
        with pytest.raises(AuthenticationError):
            async with client.stream_get("/test") as stream:
                async for _ in stream:
                    pass

    @respx.mock
    async def test_stream_get_404_raises_not_found(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(404))
        with pytest.raises(NotFoundError):
            async with client.stream_get("/test") as stream:
                async for _ in stream:
                    pass


# --- Pagination ---


class TestPagination:
    def test_parse_pagination_headers(self) -> None:
        response = httpx.Response(
            200,
            headers={
                "X-Page": "2",
                "X-Per-Page": "20",
                "X-Total": "100",
                "X-Total-Pages": "5",
                "X-Next-Page": "3",
            },
        )
        info = GitLabHTTPClient.parse_pagination(response)
        assert info.page == 2
        assert info.per_page == 20
        assert info.total == 100
        assert info.total_pages == 5
        assert info.next_page == 3

    def test_parse_pagination_missing_headers(self) -> None:
        response = httpx.Response(200, headers={"X-Page": "1"})
        info = GitLabHTTPClient.parse_pagination(response)
        assert info.page == 1
        assert info.per_page is None
        assert info.total is None
        assert info.total_pages is None
        assert info.next_page is None

    def test_parse_pagination_empty_headers(self) -> None:
        response = httpx.Response(200)
        info = GitLabHTTPClient.parse_pagination(response)
        assert info.page is None

    def test_parse_pagination_invalid_header_value(self) -> None:
        response = httpx.Response(200, headers={"X-Page": "not-a-number"})
        info = PaginationInfo.from_response(response)
        assert info.page is None


# --- Rate limiting and retries ---


class TestRateLimiting:
    @respx.mock
    async def test_429_retries_with_backoff(self, client: GitLabHTTPClient, base_url: str) -> None:
        route = respx.get(f"{base_url}/test")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0.01"}),
            httpx.Response(200, json={"ok": True}),
        ]
        response = await client.get("/test")
        assert response.status_code == 200
        assert route.call_count == 2

    @respx.mock
    async def test_429_respects_retry_after_header(self, client: GitLabHTTPClient, base_url: str) -> None:
        route = respx.get(f"{base_url}/test")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0.01"}),
            httpx.Response(200, json={}),
        ]
        await client.get("/test")
        assert route.call_count == 2

    @respx.mock
    async def test_429_exhausted_retries_raises_rate_limit_error(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "0.01"})
        )
        with pytest.raises(RateLimitError):
            await client.get("/test")


class TestServerErrors:
    @respx.mock
    async def test_5xx_retries(self, client: GitLabHTTPClient, base_url: str) -> None:
        route = respx.get(f"{base_url}/test")
        route.side_effect = [
            httpx.Response(502),
            httpx.Response(200, json={"ok": True}),
        ]
        response = await client.get("/test")
        assert response.status_code == 200
        assert route.call_count == 2

    @respx.mock
    async def test_5xx_exhausted_retries_raises_server_error(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(503))
        with pytest.raises(ServerError):
            await client.get("/test")


# --- Error handling ---


class TestErrorHandling:
    @respx.mock
    async def test_401_raises_authentication_error(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(401))
        with pytest.raises(AuthenticationError, match="re-authenticate"):
            await client.get("/test")

    @respx.mock
    async def test_404_raises_not_found_error(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/projects/999").mock(return_value=httpx.Response(404))
        with pytest.raises(NotFoundError, match="/projects/999"):
            await client.get("/projects/999")

    @respx.mock
    async def test_connection_error(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(side_effect=httpx.ConnectError("Connection refused"))
        with pytest.raises(ConnectionError, match="network connection"):
            await client.get("/test")

    @respx.mock
    async def test_timeout_error(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(side_effect=httpx.ReadTimeout("read timed out"))
        with pytest.raises(TimeoutError, match="timed out"):
            await client.get("/test")

    def test_token_not_in_auth_error_message(self) -> None:
        err = AuthenticationError("Failed with PRIVATE-TOKEN: glpat-secret123")
        assert "glpat-secret123" not in str(err)
        assert "[MASKED]" in str(err)

    def test_token_not_in_connection_error_message(self) -> None:
        err = ConnectionError("Error connecting with glpat-mytoken to host")
        assert "glpat-mytoken" not in str(err)

    @respx.mock
    async def test_403_raises_forbidden_error(self, client: GitLabHTTPClient, base_url: str) -> None:
        from gltools.client.exceptions import ForbiddenError

        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(403))
        with pytest.raises(ForbiddenError, match="Permission denied"):
            await client.get("/test")

    @respx.mock
    async def test_connect_timeout_retries_then_raises(self, base_url: str) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="test-token",
            retry_config=RetryConfig(max_retries=1, base_delay=0.01),
        )
        respx.get(f"{base_url}/test").mock(side_effect=httpx.ConnectTimeout("connect timed out"))
        with pytest.raises(TimeoutError, match="host may be offline"):
            await client.get("/test")

    def test_bearer_token_masked(self) -> None:
        text = "Authorization: Bearer glpat-mysecrettoken"
        result = _mask_token(text)
        assert "glpat-mysecrettoken" not in result
        assert "[MASKED]" in result

    def test_token_not_in_forbidden_error_message(self) -> None:
        from gltools.client.exceptions import ForbiddenError

        err = ForbiddenError("Forbidden for glpat-token123")
        assert "glpat-token123" not in str(err)
        assert "[MASKED]" in str(err)


# --- Streaming error handling ---


class TestStreamingErrorHandling:
    @respx.mock
    async def test_stream_get_403_raises_forbidden(self, client: GitLabHTTPClient, base_url: str) -> None:
        from gltools.client.exceptions import ForbiddenError

        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(403))
        with pytest.raises(ForbiddenError):
            async with client.stream_get("/test") as stream:
                async for _ in stream:
                    pass

    @respx.mock
    async def test_stream_get_429_raises_rate_limit(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "30"})
        )
        with pytest.raises(RateLimitError):
            async with client.stream_get("/test") as stream:
                async for _ in stream:
                    pass

    @respx.mock
    async def test_stream_get_5xx_raises_server_error(self, client: GitLabHTTPClient, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(502, text="Bad Gateway"))
        with pytest.raises(ServerError, match="502"):
            async with client.stream_get("/test") as stream:
                async for _ in stream:
                    pass


# --- Context manager ---


class TestContextManager:
    @respx.mock
    async def test_async_context_manager(self, base_url: str) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={}))
        async with GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="test-token",
            retry_config=RetryConfig(max_retries=0),
        ) as client:
            response = await client.get("/test")
            assert response.status_code == 200
