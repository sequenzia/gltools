"""Tests for response factories to verify they produce valid Pydantic models."""

from gltools.models import Issue, Job, MergeRequest, Pipeline, UserRef
from tests.fixtures.responses import (
    issue_response,
    job_response,
    merge_request_response,
    paginated_response,
    pipeline_response,
    user_response,
)


class TestUserResponseFactory:
    def test_defaults_parse_into_model(self) -> None:
        data = user_response()
        user = UserRef.model_validate(data)
        assert user.id == 1
        assert user.username == "janedoe"
        assert user.name == "Jane Doe"

    def test_override_fields(self) -> None:
        data = user_response(id=99, username="alice")
        user = UserRef.model_validate(data)
        assert user.id == 99
        assert user.username == "alice"
        assert user.name == "Jane Doe"  # default preserved


class TestMergeRequestResponseFactory:
    def test_defaults_parse_into_model(self) -> None:
        data = merge_request_response()
        mr = MergeRequest.model_validate(data)
        assert mr.id == 101
        assert mr.iid == 42
        assert mr.title == "Add feature X"
        assert mr.state == "opened"
        assert mr.author.username == "janedoe"
        assert mr.pipeline is not None
        assert mr.pipeline.id == 500

    def test_override_nested_author(self) -> None:
        data = merge_request_response(author={"id": 50, "username": "override_user", "name": "Override User"})
        mr = MergeRequest.model_validate(data)
        assert mr.author.id == 50
        assert mr.author.username == "override_user"

    def test_override_nested_author_partial(self) -> None:
        """Overriding a nested dict merges with defaults."""
        data = merge_request_response(author={"username": "partial_override"})
        mr = MergeRequest.model_validate(data)
        assert mr.author.username == "partial_override"
        assert mr.author.id == 1  # default preserved
        assert mr.author.name == "Jane Doe"  # default preserved

    def test_override_top_level_fields(self) -> None:
        data = merge_request_response(title="New Title", state="merged")
        mr = MergeRequest.model_validate(data)
        assert mr.title == "New Title"
        assert mr.state == "merged"


class TestIssueResponseFactory:
    def test_defaults_parse_into_model(self) -> None:
        data = issue_response()
        issue = Issue.model_validate(data)
        assert issue.id == 201
        assert issue.iid == 10
        assert issue.author.username == "bobsmith"
        assert issue.assignee is not None
        assert issue.assignee.username == "janedoe"
        assert issue.milestone is not None
        assert issue.milestone.title == "v1.0"

    def test_override_nested_author(self) -> None:
        data = issue_response(author={"id": 77, "username": "charlie", "name": "Charlie"})
        issue = Issue.model_validate(data)
        assert issue.author.id == 77


class TestPipelineResponseFactory:
    def test_defaults_parse_into_model(self) -> None:
        data = pipeline_response()
        pipeline = Pipeline.model_validate(data)
        assert pipeline.id == 500
        assert pipeline.status == "success"
        assert pipeline.ref == "main"
        assert pipeline.duration == 330.5

    def test_override_fields(self) -> None:
        data = pipeline_response(status="failed", ref="develop")
        pipeline = Pipeline.model_validate(data)
        assert pipeline.status == "failed"
        assert pipeline.ref == "develop"


class TestJobResponseFactory:
    def test_defaults_parse_into_model(self) -> None:
        data = job_response()
        job = Job.model_validate(data)
        assert job.id == 1001
        assert job.name == "test"
        assert job.stage == "test"
        assert job.status == "success"
        assert job.duration == 45.2

    def test_override_fields(self) -> None:
        data = job_response(name="deploy", stage="deploy", status="failed", failure_reason="script_failure")
        job = Job.model_validate(data)
        assert job.name == "deploy"
        assert job.failure_reason == "script_failure"


class TestPaginatedResponse:
    def test_returns_items_and_headers(self) -> None:
        items = [user_response(id=i) for i in range(3)]
        body, headers = paginated_response(items)
        assert body == items
        assert headers["X-Page"] == "1"
        assert headers["X-Per-Page"] == "20"
        assert headers["X-Total"] == "3"
        assert headers["X-Total-Pages"] == "1"
        assert headers["X-Next-Page"] == ""

    def test_custom_pagination(self) -> None:
        items = [user_response()]
        body, headers = paginated_response(items, page=2, per_page=10, total=25)
        assert headers["X-Page"] == "2"
        assert headers["X-Per-Page"] == "10"
        assert headers["X-Total"] == "25"
        assert headers["X-Total-Pages"] == "3"
        assert headers["X-Next-Page"] == "3"

    def test_last_page_no_next(self) -> None:
        items = [user_response()]
        _, headers = paginated_response(items, page=3, per_page=10, total=25)
        assert headers["X-Next-Page"] == ""

    def test_includes_x_page_and_x_total_headers(self) -> None:
        """Verify X-Page and X-Total headers are always present."""
        _, headers = paginated_response([])
        assert "X-Page" in headers
        assert "X-Total" in headers
