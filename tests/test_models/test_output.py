"""Tests for output envelope models."""

import json

from gltools.models.output import CommandResult, DryRunResult, ErrorResult, PaginatedResponse
from gltools.models.user import UserRef


class TestPaginatedResponse:
    """Tests for PaginatedResponse model."""

    def test_generic_with_user_ref(self) -> None:
        """PaginatedResponse works with UserRef type."""
        users = [
            UserRef(id=1, username="alice", name="Alice"),
            UserRef(id=2, username="bob", name="Bob"),
        ]
        resp = PaginatedResponse[UserRef](items=users, page=1, per_page=20, total=2, total_pages=1)
        assert len(resp.items) == 2
        assert resp.items[0].username == "alice"
        assert resp.page == 1
        assert resp.total == 2

    def test_generic_with_dict(self) -> None:
        """PaginatedResponse works with plain dict items."""
        resp = PaginatedResponse[dict](items=[{"id": 1}], page=1, per_page=20)
        assert resp.items == [{"id": 1}]

    def test_none_total_and_total_pages(self) -> None:
        """PaginatedResponse handles None total/total_pages for large result sets."""
        resp = PaginatedResponse[dict](
            items=[{"id": i} for i in range(20)],
            page=1,
            per_page=20,
            total=None,
            total_pages=None,
            next_page=2,
        )
        assert resp.total is None
        assert resp.total_pages is None
        assert resp.next_page == 2

    def test_defaults_to_none(self) -> None:
        """PaginatedResponse defaults optional fields to None."""
        resp = PaginatedResponse[dict](items=[], page=1, per_page=20)
        assert resp.total is None
        assert resp.total_pages is None
        assert resp.next_page is None

    def test_serialize_to_json(self) -> None:
        """PaginatedResponse serializes to clean JSON."""
        resp = PaginatedResponse[dict](items=[{"a": 1}], page=1, per_page=10, total=1, total_pages=1)
        parsed = json.loads(resp.model_dump_json())
        assert parsed["items"] == [{"a": 1}]
        assert parsed["page"] == 1
        assert parsed["per_page"] == 10
        assert parsed["total"] == 1


class TestCommandResult:
    """Tests for CommandResult model."""

    def test_default_status_success(self) -> None:
        """CommandResult defaults to status='success'."""
        result = CommandResult()
        assert result.status == "success"

    def test_wraps_data(self) -> None:
        """CommandResult wraps data with success status."""
        result = CommandResult(data={"id": 42, "title": "Test"})
        assert result.status == "success"
        assert result.data == {"id": 42, "title": "Test"}

    def test_none_data_for_delete(self) -> None:
        """CommandResult handles None data for delete operations."""
        result = CommandResult(data=None, metadata={"action": "delete"})
        assert result.data is None
        assert result.metadata == {"action": "delete"}

    def test_with_metadata(self) -> None:
        """CommandResult includes metadata like pagination info."""
        result = CommandResult(
            data=[1, 2, 3],
            metadata={"page": 1, "total": 100, "timestamp": "2026-01-01T00:00:00Z"},
        )
        assert result.metadata["page"] == 1
        assert result.metadata["timestamp"] == "2026-01-01T00:00:00Z"

    def test_error_command_result(self) -> None:
        """CommandResult can represent an error state."""
        result = CommandResult(status="error", error="Something went wrong")
        assert result.status == "error"
        assert result.error == "Something went wrong"

    def test_serialize_to_json(self) -> None:
        """CommandResult serializes to clean JSON."""
        result = CommandResult(data={"key": "value"})
        parsed = json.loads(result.model_dump_json())
        assert parsed["status"] == "success"
        assert parsed["data"] == {"key": "value"}


class TestDryRunResult:
    """Tests for DryRunResult model."""

    def test_dry_run_always_true(self) -> None:
        """DryRunResult always has dry_run=True."""
        result = DryRunResult(method="POST", url="https://gitlab.com/api/v4/projects/1/merge_requests")
        assert result.dry_run is True

    def test_shows_method_url_body(self) -> None:
        """DryRunResult shows method, URL, and body for previews."""
        result = DryRunResult(
            method="PUT",
            url="https://gitlab.com/api/v4/projects/1/merge_requests/5",
            body={"title": "Updated title", "description": "New description"},
        )
        assert result.method == "PUT"
        assert result.url == "https://gitlab.com/api/v4/projects/1/merge_requests/5"
        assert result.body == {"title": "Updated title", "description": "New description"}

    def test_none_body(self) -> None:
        """DryRunResult handles None body for GET/DELETE requests."""
        result = DryRunResult(method="GET", url="https://gitlab.com/api/v4/projects/1/issues")
        assert result.body is None

    def test_serialize_to_json(self) -> None:
        """DryRunResult serializes to clean JSON."""
        result = DryRunResult(method="DELETE", url="https://gitlab.com/api/v4/projects/1/issues/3")
        parsed = json.loads(result.model_dump_json())
        assert parsed["dry_run"] is True
        assert parsed["method"] == "DELETE"
        assert parsed["url"] == "https://gitlab.com/api/v4/projects/1/issues/3"


class TestErrorResult:
    """Tests for ErrorResult model."""

    def test_default_status_error(self) -> None:
        """ErrorResult defaults to status='error'."""
        result = ErrorResult(error="Not found")
        assert result.status == "error"

    def test_structured_error(self) -> None:
        """ErrorResult provides structured error output."""
        result = ErrorResult(
            error="Merge request not found",
            code=404,
            details={"project_id": 1, "mr_iid": 999},
        )
        assert result.error == "Merge request not found"
        assert result.code == 404
        assert result.details == {"project_id": 1, "mr_iid": 999}

    def test_none_code_and_details(self) -> None:
        """ErrorResult handles None code and details."""
        result = ErrorResult(error="Unknown error")
        assert result.code is None
        assert result.details is None

    def test_serialize_to_json(self) -> None:
        """ErrorResult serializes to clean JSON."""
        result = ErrorResult(error="Forbidden", code=403)
        parsed = json.loads(result.model_dump_json())
        assert parsed["status"] == "error"
        assert parsed["error"] == "Forbidden"
        assert parsed["code"] == 403
