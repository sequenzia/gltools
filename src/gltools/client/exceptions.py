"""Custom exceptions for the GitLab HTTP client."""

from __future__ import annotations

import re


def _mask_token(text: str) -> str:
    """Replace any GitLab private tokens in text with masked versions."""
    # Mask common token patterns (glpat-... or arbitrary token strings in PRIVATE-TOKEN headers)
    masked = re.sub(r"(PRIVATE-TOKEN[:\s]+)\S+", r"\1[MASKED]", text, flags=re.IGNORECASE)
    # Mask Authorization: Bearer tokens
    masked = re.sub(r"(Authorization[:\s]+Bearer\s+)\S+", r"\1[MASKED]", masked, flags=re.IGNORECASE)
    # Mask glpat- prefixed tokens anywhere
    masked = re.sub(r"glpat-\S+", "[MASKED]", masked)
    return masked


class GitLabClientError(Exception):
    """Base exception for all GitLab client errors."""

    def __init__(self, message: str) -> None:
        super().__init__(_mask_token(message))


class AuthenticationError(GitLabClientError):
    """Raised on 401 Unauthorized responses."""

    def __init__(self, message: str | None = None) -> None:
        default = "Authentication failed. Check your token or run `gltools auth login` to re-authenticate."
        super().__init__(message or default)


class ForbiddenError(GitLabClientError):
    """Raised on 403 Forbidden responses."""

    def __init__(self, message: str | None = None) -> None:
        default = "Permission denied. You don't have access to this resource."
        super().__init__(message or default)


class NotFoundError(GitLabClientError):
    """Raised on 404 Not Found responses."""

    def __init__(self, resource: str = "resource", path: str = "") -> None:
        msg = f"Not found: {resource}"
        if path:
            msg += f" (path: {path})"
        super().__init__(msg)


class RateLimitError(GitLabClientError):
    """Raised when rate limit retries are exhausted."""

    def __init__(self, retry_after: float | None = None) -> None:
        msg = "Rate limit exceeded and retries exhausted."
        if retry_after is not None:
            msg += f" Retry after {retry_after}s."
        super().__init__(msg)


class ServerError(GitLabClientError):
    """Raised on 5xx responses after retries are exhausted."""

    def __init__(self, status_code: int, message: str = "") -> None:
        msg = f"Server error ({status_code})"
        if message:
            msg += f": {message}"
        msg += ". Retries exhausted."
        super().__init__(msg)


class ConnectionError(GitLabClientError):
    """Raised on network connectivity errors."""

    def __init__(self, message: str | None = None) -> None:
        default = "Unable to connect to GitLab. Check your network connection and the configured host URL."
        super().__init__(message or default)


class TimeoutError(GitLabClientError):
    """Raised on request timeouts."""

    def __init__(self, message: str | None = None) -> None:
        default = "Request timed out. The server may be slow or unreachable. Try again later."
        super().__init__(message or default)
