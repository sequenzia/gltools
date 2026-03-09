"""Low-level async HTTP client wrapping httpx.AsyncClient for GitLab API communication."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

import httpx

from gltools.client.exceptions import (
    AuthenticationError,
    ConnectionError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError,
    _mask_token,
)

logger = logging.getLogger(__name__)

# Maximum number of characters to include in body summaries at DEBUG level
_BODY_SUMMARY_MAX_CHARS = 500


@dataclass(frozen=True)
class PaginationInfo:
    """Parsed pagination headers from a GitLab API response."""

    page: int | None = None
    per_page: int | None = None
    total: int | None = None
    total_pages: int | None = None
    next_page: int | None = None

    @classmethod
    def from_response(cls, response: httpx.Response) -> PaginationInfo:
        """Parse GitLab pagination headers from an HTTP response."""

        def _int_or_none(header: str) -> int | None:
            val = response.headers.get(header)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return None
            return None

        return cls(
            page=_int_or_none("X-Page"),
            per_page=_int_or_none("X-Per-Page"),
            total=_int_or_none("X-Total"),
            total_pages=_int_or_none("X-Total-Pages"),
            next_page=_int_or_none("X-Next-Page"),
        )


@dataclass
class RetryConfig:
    """Configuration for request retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    retry_on_429: bool = True
    retry_on_5xx: bool = True


class GitLabHTTPClient:
    """Low-level HTTP client wrapping httpx.AsyncClient for GitLab API communication.

    Handles authentication, rate limiting, retries with exponential backoff,
    and pagination header parsing.
    """

    def __init__(
        self,
        host: str,
        token: str,
        *,
        auth_type: str = "pat",
        token_refresher: Callable[[], Awaitable[str]] | None = None,
        retry_config: RetryConfig | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._base_url = f"{self._host}/api/v4"
        self._token = token
        self._auth_type = auth_type
        self._token_refresher = token_refresher
        self._retry_config = retry_config or RetryConfig()
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        """The base URL for API requests."""
        return self._base_url

    def _build_client(self) -> httpx.AsyncClient:
        """Build and return a new httpx.AsyncClient with configured defaults."""
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._auth_type == "oauth":
            headers["Authorization"] = f"Bearer {self._token}"
        else:
            headers["PRIVATE-TOKEN"] = self._token
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=httpx.Timeout(self._timeout),
        )

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Return the existing client or create a new one."""
        if self._client is None or self._client.is_closed:
            self._client = self._build_client()
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> GitLabHTTPClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _safe_log(self, level: int, msg: str, *args: Any) -> None:
        """Log a message with token masking applied."""
        masked_msg = _mask_token(msg)
        masked_args = tuple(_mask_token(str(a)) if isinstance(a, str) else a for a in args)
        logger.log(level, masked_msg, *masked_args)

    @staticmethod
    def _truncate_body(text: str, max_chars: int = _BODY_SUMMARY_MAX_CHARS) -> str:
        """Truncate a response body for logging, appending an indicator if trimmed."""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + f"... [truncated, {len(text)} chars total]"

    @staticmethod
    def _format_headers(headers: httpx.Headers) -> str:
        """Format HTTP headers as a string for debug logging."""
        return " ".join(f"{k}={v}" for k, v in headers.items())

    def _log_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> None:
        """Log request details at INFO (summary) and DEBUG (full details)."""
        with contextlib.suppress(Exception):
            self._safe_log(logging.INFO, "%s %s", method, path)
            if logger.isEnabledFor(logging.DEBUG):
                if params:
                    self._safe_log(logging.DEBUG, "Request params: %s", str(params))
                if json_body:
                    body_str = str(json_body)
                    self._safe_log(logging.DEBUG, "Request body: %s", self._truncate_body(body_str))

    def _log_request_headers(self, client: httpx.AsyncClient) -> None:
        """Log request headers at DEBUG level (tokens masked by SensitiveDataFilter)."""
        with contextlib.suppress(Exception):
            if logger.isEnabledFor(logging.DEBUG):
                self._safe_log(logging.DEBUG, "Request headers: %s", self._format_headers(client.headers))

    def _log_response(self, response: httpx.Response, elapsed_ms: float) -> None:
        """Log response details at INFO (summary) and DEBUG (full details)."""
        with contextlib.suppress(Exception):
            self._safe_log(logging.INFO, "Response: %d (%.1fms)", response.status_code, elapsed_ms)
            if logger.isEnabledFor(logging.DEBUG):
                self._safe_log(logging.DEBUG, "Response headers: %s", self._format_headers(response.headers))
                content_type = response.headers.get("content-type", "")
                if "application/octet-stream" in content_type or "application/zip" in content_type:
                    content_length = response.headers.get("content-length", "unknown")
                    self._safe_log(
                        logging.DEBUG,
                        "Response body: [binary, content-type=%s, size=%s]",
                        content_type,
                        content_length,
                    )
                else:
                    self._safe_log(logging.DEBUG, "Response body: %s", self._truncate_body(response.text))

    def _log_error(self, method: str, path: str, error: Exception) -> None:
        """Log error context for failed requests."""
        with contextlib.suppress(Exception):
            self._safe_log(logging.DEBUG, "%s %s failed: %s: %s", method, path, type(error).__name__, str(error))

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with retry logic for 429 and 5xx responses."""
        client = await self._ensure_client()
        last_exception: Exception | None = None
        max_attempts = self._retry_config.max_retries + 1
        refreshed = False
        attempt = 0

        # Log the request details once before the retry loop
        self._log_request(method, path, params, json_body)
        self._log_request_headers(client)

        while attempt < max_attempts:
            try:
                self._safe_log(
                    logging.DEBUG,
                    "%s %s (attempt %d/%d)",
                    method,
                    path,
                    attempt + 1,
                    max_attempts,
                )

                start_time = time.monotonic()
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                )
                elapsed_ms = (time.monotonic() - start_time) * 1000

                # Log response summary and details
                self._log_response(response, elapsed_ms)

                # Handle rate limiting (429)
                if response.status_code == 429 and self._retry_config.retry_on_429:
                    if attempt < self._retry_config.max_retries:
                        delay = self._get_retry_delay(response, attempt)
                        self._safe_log(
                            logging.WARNING,
                            "Rate limited (429). Retrying in %.1fs (attempt %d/%d)",
                            delay,
                            attempt + 1,
                            max_attempts,
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                    raise RateLimitError(
                        retry_after=self._parse_retry_after(response),
                    )

                # Handle server errors (5xx)
                if response.status_code >= 500 and self._retry_config.retry_on_5xx:
                    if attempt < self._retry_config.max_retries:
                        delay = self._get_backoff_delay(attempt)
                        self._safe_log(
                            logging.WARNING,
                            "Server error (%d). Retrying in %.1fs (attempt %d/%d)",
                            response.status_code,
                            delay,
                            attempt + 1,
                            max_attempts,
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                    raise ServerError(response.status_code, response.text)

                # Handle client errors — try token refresh on 401 (separate from retry budget)
                if response.status_code == 401:
                    if self._token_refresher is not None and not refreshed:
                        try:
                            self._token = await self._token_refresher()
                            await self.close()
                            self._client = None
                            client = await self._ensure_client()
                            refreshed = True
                            continue  # retry without incrementing attempt
                        except Exception:
                            pass
                    raise AuthenticationError()

                if response.status_code == 403:
                    raise ForbiddenError()

                if response.status_code == 404:
                    raise NotFoundError(path=path)

                # Raise for other 4xx errors
                if response.status_code >= 400:
                    response.raise_for_status()

                return response

            except httpx.ConnectTimeout as exc:
                last_exception = exc
                self._log_error(method, path, exc)
                if attempt < self._retry_config.max_retries:
                    delay = self._get_backoff_delay(attempt)
                    self._safe_log(
                        logging.WARNING,
                        "Connection timed out. Retrying in %.1fs (attempt %d/%d)",
                        delay,
                        attempt + 1,
                        max_attempts,
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise TimeoutError(
                    "Connection timed out. The host may be offline or unreachable. Check the configured host URL."
                ) from exc

            except httpx.TimeoutException as exc:
                last_exception = exc
                self._log_error(method, path, exc)
                if attempt < self._retry_config.max_retries:
                    delay = self._get_backoff_delay(attempt)
                    self._safe_log(
                        logging.WARNING,
                        "Request timed out. Retrying in %.1fs (attempt %d/%d)",
                        delay,
                        attempt + 1,
                        max_attempts,
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise TimeoutError() from exc

            except httpx.ConnectError as exc:
                self._log_error(method, path, exc)
                raise ConnectionError() from exc

            except (
                AuthenticationError,
                ForbiddenError,
                NotFoundError,
                RateLimitError,
                ServerError,
                TimeoutError,
                ConnectionError,
            ):
                raise

            except httpx.HTTPError as exc:
                self._log_error(method, path, exc)
                raise ConnectionError(f"HTTP error communicating with GitLab: {type(exc).__name__}") from exc

        # Should not reach here, but just in case
        if last_exception is not None:
            raise TimeoutError() from last_exception
        raise ServerError(500, "Unexpected: retries exhausted without a response")

    def _parse_retry_after(self, response: httpx.Response) -> float | None:
        """Parse the Retry-After header value."""
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                return None
        return None

    def _get_retry_delay(self, response: httpx.Response, attempt: int) -> float:
        """Calculate retry delay, preferring Retry-After header if present."""
        retry_after = self._parse_retry_after(response)
        if retry_after is not None and retry_after > 0:
            return min(retry_after, self._retry_config.max_delay)
        return self._get_backoff_delay(attempt)

    def _get_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay for a given attempt."""
        delay = self._retry_config.base_delay * (2**attempt)
        return min(delay, self._retry_config.max_delay)

    @staticmethod
    def parse_pagination(response: httpx.Response) -> PaginationInfo:
        """Parse GitLab pagination headers from a response.

        GitLab returns pagination info in these headers:
        - X-Page: Current page number
        - X-Per-Page: Items per page
        - X-Total: Total number of items
        - X-Total-Pages: Total number of pages
        - X-Next-Page: Next page number (empty if last page)
        """
        return PaginationInfo.from_response(response)

    async def get(self, path: str, **params: Any) -> httpx.Response:
        """Send an authenticated GET request to the GitLab API.

        Args:
            path: API path relative to /api/v4 (e.g., "/projects/1/merge_requests").
            **params: Query parameters.

        Returns:
            The HTTP response.
        """
        return await self._request_with_retry("GET", path, params=params or None)

    async def post(self, path: str, **json_body: Any) -> httpx.Response:
        """Send an authenticated POST request to the GitLab API.

        Args:
            path: API path relative to /api/v4.
            **json_body: JSON body fields.

        Returns:
            The HTTP response.
        """
        return await self._request_with_retry("POST", path, json_body=json_body or None)

    async def put(self, path: str, **json_body: Any) -> httpx.Response:
        """Send an authenticated PUT request to the GitLab API.

        Args:
            path: API path relative to /api/v4.
            **json_body: JSON body fields.

        Returns:
            The HTTP response.
        """
        return await self._request_with_retry("PUT", path, json_body=json_body or None)

    async def delete(self, path: str) -> httpx.Response:
        """Send an authenticated DELETE request to the GitLab API.

        Args:
            path: API path relative to /api/v4.

        Returns:
            The HTTP response.
        """
        return await self._request_with_retry("DELETE", path)

    @asynccontextmanager
    async def stream_get(self, path: str, **params: Any) -> AsyncIterator[AsyncIterator[bytes]]:
        """Stream a GET response for large payloads (e.g., job logs).

        Yields chunks of bytes without loading the full response into memory.

        Args:
            path: API path relative to /api/v4.
            **params: Query parameters.

        Yields:
            An async iterator of byte chunks from the response body.
        """
        self._log_request("GET", path, params or None, None)
        client = await self._ensure_client()
        self._log_request_headers(client)
        try:
            async with client.stream(
                "GET",
                path,
                params=params or None,
            ) as response:
                # Log stream start without buffering the body
                with contextlib.suppress(Exception):
                    content_type = response.headers.get("content-type", "unknown")
                    content_length = response.headers.get("content-length", "unknown")
                    self._safe_log(
                        logging.INFO,
                        "Response: %d [stream, content-type=%s, content-length=%s]",
                        response.status_code,
                        content_type,
                        content_length,
                    )
                    if logger.isEnabledFor(logging.DEBUG):
                        self._safe_log(logging.DEBUG, "Response headers: %s", self._format_headers(response.headers))

                if response.status_code == 401:
                    raise AuthenticationError()
                if response.status_code == 403:
                    raise ForbiddenError()
                if response.status_code == 404:
                    raise NotFoundError(path=path)
                if response.status_code == 429:
                    raise RateLimitError(
                        retry_after=self._parse_retry_after(response),
                    )
                if response.status_code >= 500:
                    await response.aread()
                    raise ServerError(response.status_code, response.text)
                if response.status_code >= 400:
                    await response.aread()
                    response.raise_for_status()
                yield response.aiter_bytes()
        except httpx.TimeoutException as exc:
            self._log_error("GET", path, exc)
            raise TimeoutError() from exc
        except httpx.ConnectError as exc:
            self._log_error("GET", path, exc)
            raise ConnectionError() from exc
        except (
            AuthenticationError,
            ForbiddenError,
            NotFoundError,
            RateLimitError,
            ServerError,
            TimeoutError,
            ConnectionError,
        ):
            raise
        except httpx.HTTPError as exc:
            self._log_error("GET", path, exc)
            raise ConnectionError(f"HTTP error during streaming: {type(exc).__name__}") from exc
