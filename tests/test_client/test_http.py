"""Tests for GitLabHTTPClient."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

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
        respx.post(f"{base_url}/projects/1/merge_requests").mock(return_value=httpx.Response(201, json={"iid": 42}))
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
        respx.delete(f"{base_url}/projects/1/merge_requests/42").mock(return_value=httpx.Response(204))
        response = await client.delete("/projects/1/merge_requests/42")
        assert response.status_code == 204


# --- Streaming ---


class TestStreaming:
    @respx.mock
    async def test_stream_get_yields_chunks(self, client: GitLabHTTPClient, base_url: str) -> None:
        content = b"line1\nline2\nline3\n"
        respx.get(f"{base_url}/projects/1/jobs/10/trace").mock(return_value=httpx.Response(200, content=content))
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
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(429, headers={"Retry-After": "0.01"}))
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
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(429, headers={"Retry-After": "30"}))
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


# --- OAuth Bearer auth ---


class TestBearerAuth:
    @respx.mock
    async def test_sends_bearer_header_for_oauth(self, base_url: str) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="oauth-access-token",
            auth_type="oauth",
            retry_config=RetryConfig(max_retries=0),
        )
        route = respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={}))
        await client.get("/test")
        assert route.called
        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer oauth-access-token"
        assert "PRIVATE-TOKEN" not in request.headers
        await client.close()

    @respx.mock
    async def test_sends_private_token_for_pat(self, base_url: str) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="glpat-test",
            auth_type="pat",
            retry_config=RetryConfig(max_retries=0),
        )
        route = respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={}))
        await client.get("/test")
        request = route.calls[0].request
        assert request.headers["PRIVATE-TOKEN"] == "glpat-test"
        assert "Authorization" not in request.headers
        await client.close()

    @respx.mock
    async def test_default_auth_type_is_pat(self, base_url: str) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="glpat-test",
            retry_config=RetryConfig(max_retries=0),
        )
        route = respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={}))
        await client.get("/test")
        request = route.calls[0].request
        assert "PRIVATE-TOKEN" in request.headers
        await client.close()


class TestTokenRefreshOn401:
    @respx.mock
    async def test_refreshes_token_on_401(self, base_url: str) -> None:
        refresher = AsyncMock(return_value="new-token")
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="expired-token",
            auth_type="oauth",
            token_refresher=refresher,
            retry_config=RetryConfig(max_retries=0),
        )

        route = respx.get(f"{base_url}/test")
        route.side_effect = [
            httpx.Response(401),
            httpx.Response(200, json={"ok": True}),
        ]

        response = await client.get("/test")
        assert response.status_code == 200
        refresher.assert_awaited_once()
        # Second request should use new token
        second_request = route.calls[1].request
        assert second_request.headers["Authorization"] == "Bearer new-token"
        await client.close()

    @respx.mock
    async def test_refresh_only_once_per_request(self, base_url: str) -> None:
        refresher = AsyncMock(return_value="still-bad-token")
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="expired-token",
            auth_type="oauth",
            token_refresher=refresher,
            retry_config=RetryConfig(max_retries=0),
        )

        # Both responses are 401
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(401))

        with pytest.raises(AuthenticationError):
            await client.get("/test")

        # Refresher called once, then gave up
        refresher.assert_awaited_once()
        await client.close()

    @respx.mock
    async def test_no_refresher_raises_immediately(self, base_url: str) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="expired-token",
            auth_type="oauth",
            retry_config=RetryConfig(max_retries=0),
        )

        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(401))

        with pytest.raises(AuthenticationError):
            await client.get("/test")
        await client.close()

    @respx.mock
    async def test_refresh_failure_raises_auth_error(self, base_url: str) -> None:
        refresher = AsyncMock(side_effect=RuntimeError("refresh failed"))
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="expired-token",
            auth_type="oauth",
            token_refresher=refresher,
            retry_config=RetryConfig(max_retries=0),
        )

        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(401))

        with pytest.raises(AuthenticationError):
            await client.get("/test")
        await client.close()


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


# --- HTTP request/response logging ---

_HTTP_LOGGER = "gltools.client.http"


@pytest.fixture(autouse=False)
def _ensure_logger_propagation():
    """Ensure the gltools logger hierarchy propagates to root so caplog works.

    Other tests (e.g. test_logging.py) may set propagate=False on the 'gltools'
    logger, which prevents caplog from capturing records. We also temporarily
    remove any stale handlers to avoid I/O errors on closed streams.
    """
    gltools_logger = logging.getLogger("gltools")
    http_logger = logging.getLogger(_HTTP_LOGGER)
    original_propagate = gltools_logger.propagate
    original_level = http_logger.level
    original_handlers = list(gltools_logger.handlers)
    # Temporarily clear handlers and enable propagation so caplog can capture
    gltools_logger.handlers = []
    gltools_logger.propagate = True
    http_logger.setLevel(logging.DEBUG)
    yield
    gltools_logger.propagate = original_propagate
    gltools_logger.handlers = original_handlers
    http_logger.setLevel(original_level)


@pytest.mark.usefixtures("_ensure_logger_propagation")
class TestHTTPLogging:
    """Tests for HTTP request/response logging in GitLabHTTPClient."""

    @respx.mock
    async def test_info_logs_method_and_url_for_request(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/projects").mock(return_value=httpx.Response(200, json=[]))
        with caplog.at_level(logging.INFO, logger="gltools.client.http"):
            await client.get("/projects")
        assert any("GET /projects" in r.message for r in caplog.records if r.levelno == logging.INFO)

    @respx.mock
    async def test_info_logs_response_status_code(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/projects").mock(return_value=httpx.Response(200, json=[]))
        with caplog.at_level(logging.INFO, logger="gltools.client.http"):
            await client.get("/projects")
        assert any("Response: 200" in r.message for r in caplog.records if r.levelno == logging.INFO)

    @respx.mock
    async def test_debug_logs_request_headers(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={}))
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"):
            await client.get("/test")
        assert any("Request headers:" in r.message for r in caplog.records if r.levelno == logging.DEBUG)

    @respx.mock
    async def test_debug_logs_response_headers(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={}))
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"):
            await client.get("/test")
        assert any("Response headers:" in r.message for r in caplog.records if r.levelno == logging.DEBUG)

    @respx.mock
    async def test_debug_logs_response_body(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={"id": 1}))
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"):
            await client.get("/test")
        assert any("Response body:" in r.message for r in caplog.records if r.levelno == logging.DEBUG)

    @respx.mock
    async def test_no_logging_at_warning_level(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={}))
        with caplog.at_level(logging.WARNING, logger="gltools.client.http"):
            await client.get("/test")
        # No INFO or DEBUG logs should appear at WARNING level
        http_records = [r for r in caplog.records if r.name == "gltools.client.http" and r.levelno < logging.WARNING]
        assert len(http_records) == 0

    @respx.mock
    async def test_post_logs_request_body_at_debug(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.post(f"{base_url}/projects/1/merge_requests").mock(
            return_value=httpx.Response(201, json={"iid": 42}),
        )
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"):
            await client.post("/projects/1/merge_requests", title="New MR")
        assert any("Request body:" in r.message for r in caplog.records if r.levelno == logging.DEBUG)

    @respx.mock
    async def test_get_with_params_logs_params_at_debug(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/projects").mock(return_value=httpx.Response(200, json=[]))
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"):
            await client.get("/projects", per_page=10)
        assert any("Request params:" in r.message for r in caplog.records if r.levelno == logging.DEBUG)

    @respx.mock
    async def test_response_includes_timing_in_ms(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={}))
        with caplog.at_level(logging.INFO, logger="gltools.client.http"):
            await client.get("/test")
        response_logs = [r for r in caplog.records if "Response: 200" in r.message and r.levelno == logging.INFO]
        assert len(response_logs) == 1
        assert "ms" in response_logs[0].message


@pytest.mark.usefixtures("_ensure_logger_propagation")
class TestHTTPLoggingBodyTruncation:
    """Tests for body truncation in HTTP logging."""

    def test_truncate_body_short_text(self) -> None:
        text = "short body"
        assert GitLabHTTPClient._truncate_body(text) == text

    def test_truncate_body_long_text(self) -> None:
        text = "x" * 1000
        result = GitLabHTTPClient._truncate_body(text, max_chars=100)
        assert len(result) < len(text)
        assert result.startswith("x" * 100)
        assert "[truncated, 1000 chars total]" in result

    def test_truncate_body_exact_limit(self) -> None:
        text = "x" * 500
        result = GitLabHTTPClient._truncate_body(text, max_chars=500)
        assert result == text

    @respx.mock
    async def test_large_response_body_truncated_in_log(self, base_url: str, caplog: pytest.LogCaptureFixture) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="test-token",
            retry_config=RetryConfig(max_retries=0),
        )
        large_body = '{"data": "' + "x" * 2000 + '"}'
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, text=large_body))
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"):
            await client.get("/test")
        body_logs = [r for r in caplog.records if "Response body:" in r.message and r.levelno == logging.DEBUG]
        assert len(body_logs) == 1
        assert "[truncated," in body_logs[0].message
        await client.close()


@pytest.mark.usefixtures("_ensure_logger_propagation")
class TestHTTPLoggingFailedRequests:
    """Tests for logging on failed requests."""

    @respx.mock
    async def test_connection_error_logged(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/test").mock(side_effect=httpx.ConnectError("Connection refused"))
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"), pytest.raises(ConnectionError):
            await client.get("/test")
        assert any("failed:" in r.message for r in caplog.records if r.levelno == logging.DEBUG)

    @respx.mock
    async def test_timeout_error_logged(self, base_url: str, caplog: pytest.LogCaptureFixture) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="test-token",
            retry_config=RetryConfig(max_retries=0, base_delay=0.01),
        )
        respx.get(f"{base_url}/test").mock(side_effect=httpx.ReadTimeout("read timed out"))
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"), pytest.raises(TimeoutError):
            await client.get("/test")
        assert any("failed:" in r.message for r in caplog.records if r.levelno == logging.DEBUG)
        await client.close()

    @respx.mock
    async def test_connect_timeout_error_logged(self, base_url: str, caplog: pytest.LogCaptureFixture) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="test-token",
            retry_config=RetryConfig(max_retries=0, base_delay=0.01),
        )
        respx.get(f"{base_url}/test").mock(side_effect=httpx.ConnectTimeout("connect timed out"))
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"), pytest.raises(TimeoutError):
            await client.get("/test")
        assert any("failed:" in r.message for r in caplog.records if r.levelno == logging.DEBUG)
        await client.close()


@pytest.mark.usefixtures("_ensure_logger_propagation")
class TestHTTPLoggingStreaming:
    """Tests for logging in streaming responses."""

    @respx.mock
    async def test_stream_get_logs_request_and_response(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        content = b"line1\nline2\n"
        respx.get(f"{base_url}/projects/1/jobs/10/trace").mock(return_value=httpx.Response(200, content=content))
        with caplog.at_level(logging.INFO, logger="gltools.client.http"):
            async with client.stream_get("/projects/1/jobs/10/trace") as stream:
                async for _ in stream:
                    pass
        # Should have INFO for request method/URL
        assert any("GET /projects/1/jobs/10/trace" in r.message for r in caplog.records if r.levelno == logging.INFO)
        # Should have INFO for stream response status
        assert any(
            "Response: 200" in r.message and "stream" in r.message for r in caplog.records if r.levelno == logging.INFO
        )

    @respx.mock
    async def test_stream_get_does_not_buffer_body(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        content = b"streaming data"
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, content=content))
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"):
            async with client.stream_get("/test") as stream:
                async for _ in stream:
                    pass
        # Streaming responses should NOT have "Response body:" logs (body is not buffered)
        body_logs = [r for r in caplog.records if "Response body:" in r.message]
        assert len(body_logs) == 0

    @respx.mock
    async def test_stream_get_logs_content_type_and_length(
        self,
        client: GitLabHTTPClient,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        respx.get(f"{base_url}/test").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-type": "text/plain", "content-length": "4"},
            )
        )
        with caplog.at_level(logging.INFO, logger="gltools.client.http"):
            async with client.stream_get("/test") as stream:
                async for _ in stream:
                    pass
        stream_logs = [r for r in caplog.records if "stream" in r.message and r.levelno == logging.INFO]
        assert len(stream_logs) > 0
        assert "content-type=text/plain" in stream_logs[0].message


@pytest.mark.usefixtures("_ensure_logger_propagation")
class TestHTTPLoggingBinaryResponse:
    """Tests for logging of binary responses."""

    @respx.mock
    async def test_binary_response_logs_content_type_and_size(
        self,
        base_url: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="test-token",
            retry_config=RetryConfig(max_retries=0),
        )
        respx.get(f"{base_url}/test").mock(
            return_value=httpx.Response(
                200,
                content=b"\x00\x01\x02",
                headers={"content-type": "application/octet-stream", "content-length": "3"},
            )
        )
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"):
            await client.get("/test")
        body_logs = [r for r in caplog.records if "Response body:" in r.message and r.levelno == logging.DEBUG]
        assert len(body_logs) == 1
        assert "binary" in body_logs[0].message
        assert "application/octet-stream" in body_logs[0].message
        assert "size=3" in body_logs[0].message
        await client.close()


@pytest.mark.usefixtures("_ensure_logger_propagation")
class TestHTTPLoggingIntegration:
    """Integration tests for HTTP logging with respx mocks showing expected details."""

    @respx.mock
    async def test_full_request_response_logging_flow(self, base_url: str, caplog: pytest.LogCaptureFixture) -> None:
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="glpat-secret-test-123",
            retry_config=RetryConfig(max_retries=0),
        )
        respx.get(f"{base_url}/projects/1/merge_requests").mock(
            return_value=httpx.Response(200, json=[{"iid": 1, "title": "Test MR"}])
        )
        with caplog.at_level(logging.DEBUG, logger="gltools.client.http"):
            await client.get("/projects/1/merge_requests", state="opened")

        # Verify the complete logging flow
        messages = [r.message for r in caplog.records]

        # 1. Request summary at INFO
        assert any("GET /projects/1/merge_requests" in m for m in messages)
        # 2. Request headers at DEBUG (token should be masked by _safe_log)
        header_logs = [m for m in messages if "Request headers:" in m]
        assert len(header_logs) > 0
        assert "glpat-secret-test-123" not in header_logs[0]
        # 3. Response status at INFO
        assert any("Response: 200" in m for m in messages)
        # 4. Response body at DEBUG
        assert any("Response body:" in m for m in messages)

        await client.close()

    @respx.mock
    async def test_logging_does_not_break_request_flow(self, base_url: str) -> None:
        """Ensure that even if logging encounters issues, the request completes."""
        client = GitLabHTTPClient(
            host="https://gitlab.example.com",
            token="test-token",
            retry_config=RetryConfig(max_retries=0),
        )
        respx.get(f"{base_url}/test").mock(return_value=httpx.Response(200, json={"ok": True}))
        # Request should succeed regardless of logging state
        response = await client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        await client.close()
