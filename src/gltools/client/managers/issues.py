"""Issue resource manager for GitLab Issue API operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from gltools.client.exceptions import NotFoundError
from gltools.models import Issue, Note, PaginatedResponse

if TYPE_CHECKING:
    from gltools.client.http import GitLabHTTPClient


def _encode_project(project_id: int | str) -> str:
    """URL-encode a project ID (handles both numeric IDs and namespace/project paths)."""
    if isinstance(project_id, int):
        return str(project_id)
    return quote(project_id, safe="")


class IssueManager:
    """Typed resource manager for GitLab Issue API operations."""

    def __init__(self, client: GitLabHTTPClient) -> None:
        self._client = client

    def _base_path(self, project_id: int | str) -> str:
        return f"/projects/{_encode_project(project_id)}/issues"

    def _issue_path(self, project_id: int | str, issue_iid: int) -> str:
        return f"{self._base_path(project_id)}/{issue_iid}"

    async def list(
        self,
        project_id: int | str,
        *,
        state: str | None = None,
        labels: list[str] | None = None,
        assignee_username: str | None = None,
        milestone: str | None = None,
        scope: str | None = None,
        search: str | None = None,
        per_page: int = 20,
        page: int = 1,
    ) -> PaginatedResponse[Issue]:
        """List issues for a project with optional filters.

        Args:
            project_id: The project ID or URL-encoded path.
            state: Filter by state (opened, closed, all).
            labels: Filter by labels (comma-joined in API).
            assignee_username: Filter by assignee username.
            milestone: Filter by milestone title.
            scope: Filter by scope (created_by_me, assigned_to_me, all).
            search: Search in title and description.
            per_page: Number of items per page (default 20).
            page: Page number (default 1).

        Returns:
            Paginated response containing Issue models.
        """
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        if state is not None:
            params["state"] = state
        if labels is not None:
            params["labels"] = ",".join(labels)
        if assignee_username is not None:
            params["assignee_username"] = assignee_username
        if milestone is not None:
            params["milestone"] = milestone
        if scope is not None:
            params["scope"] = scope
        if search is not None:
            params["search"] = search

        response = await self._client.get(self._base_path(project_id), **params)
        pagination = self._client.parse_pagination(response)
        items = [Issue.model_validate(item) for item in response.json()]

        return PaginatedResponse[Issue](
            items=items,
            page=pagination.page or page,
            per_page=pagination.per_page or per_page,
            total=pagination.total,
            total_pages=pagination.total_pages,
            next_page=pagination.next_page,
        )

    async def get(self, project_id: int | str, issue_iid: int) -> Issue:
        """Get a single issue by its IID.

        Args:
            project_id: The project ID or URL-encoded path.
            issue_iid: The internal issue ID (IID) within the project.

        Returns:
            The Issue model.

        Raises:
            NotFoundError: If the issue does not exist or is not accessible.
        """
        try:
            response = await self._client.get(self._issue_path(project_id, issue_iid))
        except NotFoundError:
            raise NotFoundError(resource="Issue", path=self._issue_path(project_id, issue_iid)) from None
        return Issue.model_validate(response.json())

    async def create(
        self,
        project_id: int | str,
        *,
        title: str,
        description: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        milestone_id: int | None = None,
        due_date: str | None = None,
    ) -> Issue:
        """Create a new issue in a project.

        Args:
            project_id: The project ID or URL-encoded path.
            title: The issue title.
            description: The issue description.
            labels: Labels to assign (comma-joined in API).
            assignee_ids: User IDs to assign.
            milestone_id: Milestone ID to associate.
            due_date: Due date in YYYY-MM-DD format.

        Returns:
            The created Issue model.
        """
        body: dict[str, Any] = {"title": title}
        if description is not None:
            body["description"] = description
        if labels is not None:
            body["labels"] = ",".join(labels)
        if assignee_ids is not None:
            body["assignee_ids"] = assignee_ids
        if milestone_id is not None:
            body["milestone_id"] = milestone_id
        if due_date is not None:
            body["due_date"] = due_date

        response = await self._client.post(self._base_path(project_id), **body)
        return Issue.model_validate(response.json())

    async def update(self, project_id: int | str, issue_iid: int, **fields: Any) -> Issue:
        """Update an existing issue.

        Args:
            project_id: The project ID or URL-encoded path.
            issue_iid: The internal issue ID (IID) within the project.
            **fields: Fields to update (title, description, labels, state_event, etc.).

        Returns:
            The updated Issue model.

        Raises:
            NotFoundError: If the issue does not exist.
        """
        try:
            response = await self._client.put(self._issue_path(project_id, issue_iid), **fields)
        except NotFoundError:
            raise NotFoundError(resource="Issue", path=self._issue_path(project_id, issue_iid)) from None
        return Issue.model_validate(response.json())

    async def close(self, project_id: int | str, issue_iid: int) -> Issue:
        """Close an issue by setting state_event to 'close'.

        Args:
            project_id: The project ID or URL-encoded path.
            issue_iid: The internal issue ID (IID) within the project.

        Returns:
            The updated Issue model with closed state.
        """
        return await self.update(project_id, issue_iid, state_event="close")

    async def reopen(self, project_id: int | str, issue_iid: int) -> Issue:
        """Reopen an issue by setting state_event to 'reopen'.

        Args:
            project_id: The project ID or URL-encoded path.
            issue_iid: The internal issue ID (IID) within the project.

        Returns:
            The updated Issue model with reopened state.
        """
        return await self.update(project_id, issue_iid, state_event="reopen")

    async def notes(self, project_id: int | str, issue_iid: int) -> list[Note]:
        """List all notes (comments) on an issue.

        Args:
            project_id: The project ID or URL-encoded path.
            issue_iid: The internal issue ID (IID) within the project.

        Returns:
            List of Note models.

        Raises:
            NotFoundError: If the issue does not exist.
        """
        try:
            response = await self._client.get(f"{self._issue_path(project_id, issue_iid)}/notes")
        except NotFoundError:
            raise NotFoundError(resource="Issue", path=self._issue_path(project_id, issue_iid)) from None
        return [Note.model_validate(item) for item in response.json()]

    async def create_note(self, project_id: int | str, issue_iid: int, body: str) -> Note:
        """Create a new note (comment) on an issue.

        Args:
            project_id: The project ID or URL-encoded path.
            issue_iid: The internal issue ID (IID) within the project.
            body: The note body text.

        Returns:
            The created Note model.

        Raises:
            NotFoundError: If the issue does not exist.
        """
        try:
            response = await self._client.post(
                f"{self._issue_path(project_id, issue_iid)}/notes",
                body=body,
            )
        except NotFoundError:
            raise NotFoundError(resource="Issue", path=self._issue_path(project_id, issue_iid)) from None
        return Note.model_validate(response.json())
