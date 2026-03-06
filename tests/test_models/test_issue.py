"""Tests for Issue model."""

from datetime import UTC, datetime

from gltools.models.issue import Issue
from gltools.models.user import UserRef


def _make_issue_data(**overrides: object) -> dict:
    """Return a minimal valid GitLab Issue API response dict."""
    base: dict = {
        "id": 101,
        "iid": 5,
        "title": "Fix login bug",
        "description": "Users cannot log in after password reset.",
        "state": "opened",
        "author": {"id": 1, "username": "alice", "name": "Alice"},
        "assignee": {"id": 2, "username": "bob", "name": "Bob"},
        "labels": ["bug", "priority::high"],
        "milestone": "v1.0",
        "created_at": "2025-06-15T10:30:00.000Z",
        "updated_at": "2025-06-16T08:00:00.000Z",
        "closed_at": None,
    }
    base.update(overrides)
    return base


class TestIssueParsing:
    """Tests for Issue model parsing."""

    def test_parse_valid_response(self) -> None:
        """Issue parses a complete GitLab API response."""
        issue = Issue.model_validate(_make_issue_data())
        assert issue.id == 101
        assert issue.iid == 5
        assert issue.title == "Fix login bug"
        assert issue.description == "Users cannot log in after password reset."
        assert issue.state == "opened"
        assert isinstance(issue.author, UserRef)
        assert issue.author.username == "alice"
        assert isinstance(issue.assignee, UserRef)
        assert issue.assignee.username == "bob"
        assert issue.labels == ["bug", "priority::high"]
        assert issue.milestone == "v1.0"
        assert issue.closed_at is None

    def test_datetime_fields_parse_iso8601(self) -> None:
        """Datetime fields correctly parse ISO 8601 strings from GitLab API."""
        issue = Issue.model_validate(_make_issue_data())
        assert isinstance(issue.created_at, datetime)
        assert isinstance(issue.updated_at, datetime)
        assert issue.created_at == datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)
        assert issue.updated_at == datetime(2025, 6, 16, 8, 0, 0, tzinfo=UTC)

    def test_closed_at_parses_when_present(self) -> None:
        """closed_at parses a valid ISO 8601 string."""
        issue = Issue.model_validate(_make_issue_data(closed_at="2025-06-17T12:00:00.000Z"))
        assert isinstance(issue.closed_at, datetime)
        assert issue.closed_at == datetime(2025, 6, 17, 12, 0, 0, tzinfo=UTC)

    def test_description_none(self) -> None:
        """Issue accepts None for description."""
        issue = Issue.model_validate(_make_issue_data(description=None))
        assert issue.description is None

    def test_assignee_none(self) -> None:
        """Issue accepts None for assignee."""
        issue = Issue.model_validate(_make_issue_data(assignee=None))
        assert issue.assignee is None

    def test_milestone_none(self) -> None:
        """Issue accepts None for milestone."""
        issue = Issue.model_validate(_make_issue_data(milestone=None))
        assert issue.milestone is None

    def test_empty_labels(self) -> None:
        """Issue accepts an empty labels list."""
        issue = Issue.model_validate(_make_issue_data(labels=[]))
        assert issue.labels == []


class TestIssueExtraFields:
    """Tests for Issue handling of extra fields from the API."""

    def test_ignores_extra_fields(self) -> None:
        """Issue silently ignores extra fields from the GitLab API response."""
        data = _make_issue_data(
            web_url="https://gitlab.com/project/-/issues/5",
            confidential=False,
            weight=3,
        )
        issue = Issue.model_validate(data)
        assert issue.id == 101
        assert not hasattr(issue, "web_url")
        assert not hasattr(issue, "confidential")
        assert not hasattr(issue, "weight")
