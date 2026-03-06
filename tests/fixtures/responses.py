"""Response factories for GitLab API response types.

Each factory returns a dict matching the GitLab API JSON structure with realistic
defaults. All defaults can be overridden via keyword arguments.
"""

from typing import Any


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge overrides into base dict, handling nested dicts."""
    result = base.copy()
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def user_response(**overrides: Any) -> dict[str, Any]:
    """Create a realistic GitLab user reference response.

    Returns a dict that parses into a UserRef Pydantic model.
    """
    defaults: dict[str, Any] = {
        "id": 1,
        "username": "janedoe",
        "name": "Jane Doe",
    }
    return _deep_merge(defaults, overrides)


def merge_request_response(**overrides: Any) -> dict[str, Any]:
    """Create a realistic GitLab merge request response.

    Returns a dict that parses into a MergeRequest Pydantic model.
    Includes nested UserRef for author and a PipelineRef for pipeline.
    """
    defaults: dict[str, Any] = {
        "id": 101,
        "iid": 42,
        "title": "Add feature X",
        "description": "Implements feature X as described in issue #10.",
        "state": "opened",
        "source_branch": "feature/x",
        "target_branch": "main",
        "author": user_response(),
        "assignee": None,
        "labels": ["enhancement", "review"],
        "pipeline": {
            "id": 500,
            "status": "success",
            "web_url": "https://gitlab.example.com/project/-/pipelines/500",
        },
        "created_at": "2025-06-15T10:30:00.000Z",
        "updated_at": "2025-06-16T14:00:00.000Z",
        "merged_at": None,
    }
    return _deep_merge(defaults, overrides)


def issue_response(**overrides: Any) -> dict[str, Any]:
    """Create a realistic GitLab issue response.

    Returns a dict that parses into an Issue Pydantic model.
    """
    defaults: dict[str, Any] = {
        "id": 201,
        "iid": 10,
        "title": "Bug: login fails on Safari",
        "description": "Users cannot log in when using Safari 17.",
        "state": "opened",
        "author": user_response(id=2, username="bobsmith", name="Bob Smith"),
        "assignee": user_response(),
        "labels": ["bug", "priority::high"],
        "milestone": "v1.0",
        "created_at": "2025-05-20T08:00:00.000Z",
        "updated_at": "2025-05-21T09:15:00.000Z",
        "closed_at": None,
    }
    return _deep_merge(defaults, overrides)


def pipeline_response(**overrides: Any) -> dict[str, Any]:
    """Create a realistic GitLab pipeline response.

    Returns a dict that parses into a Pipeline Pydantic model.
    """
    defaults: dict[str, Any] = {
        "id": 500,
        "status": "success",
        "ref": "main",
        "sha": "abc123def456789012345678901234567890abcd",
        "source": "push",
        "jobs": [],
        "created_at": "2025-06-15T10:00:00.000Z",
        "finished_at": "2025-06-15T10:05:30.000Z",
        "duration": 330.5,
    }
    return _deep_merge(defaults, overrides)


def job_response(**overrides: Any) -> dict[str, Any]:
    """Create a realistic GitLab job response.

    Returns a dict that parses into a Job Pydantic model.
    """
    defaults: dict[str, Any] = {
        "id": 1001,
        "name": "test",
        "stage": "test",
        "status": "success",
        "duration": 45.2,
        "failure_reason": None,
        "web_url": "https://gitlab.example.com/project/-/jobs/1001",
    }
    return _deep_merge(defaults, overrides)


def paginated_response(
    items: list[dict[str, Any]],
    page: int = 1,
    per_page: int = 20,
    total: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Create a paginated GitLab API response with pagination headers.

    Args:
        items: The list of response items for this page.
        page: Current page number.
        per_page: Number of items per page.
        total: Total number of items across all pages. Defaults to len(items).

    Returns:
        A tuple of (response_body, pagination_headers) where pagination_headers
        is a dict of header name to header value strings.
    """
    if total is None:
        total = len(items)

    total_pages = max(1, (total + per_page - 1) // per_page)
    next_page = page + 1 if page < total_pages else ""

    headers: dict[str, str] = {
        "X-Page": str(page),
        "X-Per-Page": str(per_page),
        "X-Total": str(total),
        "X-Total-Pages": str(total_pages),
        "X-Next-Page": str(next_page),
    }

    return items, headers
