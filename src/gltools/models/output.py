"""Output envelope models for consistent CLI response formatting."""

from typing import Any

from pydantic import BaseModel, Field


class PaginatedResponse[T](BaseModel):
    """Paginated list response wrapping GitLab API paginated results."""

    items: list[T]
    page: int
    per_page: int
    total: int | None = None
    total_pages: int | None = None
    next_page: int | None = None


class CommandResult(BaseModel):
    """Envelope for all successful CLI command responses."""

    status: str = Field(default="success")
    data: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class DryRunResult(BaseModel):
    """Preview of an API request without executing it."""

    dry_run: bool = Field(default=True)
    method: str
    url: str
    body: dict[str, Any] | None = None


class ErrorResult(BaseModel):
    """Structured error output for JSON mode."""

    status: str = Field(default="error")
    error: str
    code: int | None = None
    details: dict[str, Any] | None = None
