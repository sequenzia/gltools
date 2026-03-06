"""MergeRequest resource manager for GitLab MR API operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from gltools.models import DiffFile, MergeRequest, Note, PaginatedResponse

if TYPE_CHECKING:
    from gltools.client.http import GitLabHTTPClient


def _encode_project(project_id: int | str) -> str:
    """URL-encode a project ID (handles both numeric IDs and namespace/project paths)."""
    if isinstance(project_id, int):
        return str(project_id)
    return quote(project_id, safe="")


class MergeRequestManager:
    """Typed resource manager for GitLab Merge Request API operations."""

    def __init__(self, client: GitLabHTTPClient) -> None:
        self._client = client

    def _base_path(self, project_id: int | str) -> str:
        return f"/projects/{_encode_project(project_id)}/merge_requests"

    def _mr_path(self, project_id: int | str, mr_iid: int) -> str:
        return f"{self._base_path(project_id)}/{mr_iid}"

    async def list(
        self,
        project_id: int | str,
        *,
        state: str | None = None,
        labels: list[str] | None = None,
        author_username: str | None = None,
        scope: str | None = None,
        search: str | None = None,
        per_page: int = 20,
        page: int = 1,
    ) -> PaginatedResponse[MergeRequest]:
        """List merge requests for a project with optional filters.

        Args:
            project_id: The project ID or URL-encoded path.
            state: Filter by state (opened, closed, merged, all).
            labels: Filter by labels.
            author_username: Filter by author username.
            scope: Filter by scope (created_by_me, assigned_to_me, all).
            search: Search in title and description.
            per_page: Number of items per page (default 20).
            page: Page number (default 1).

        Returns:
            Paginated response containing MergeRequest items.
        """
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        if state is not None:
            params["state"] = state
        if labels is not None:
            params["labels"] = ",".join(labels)
        if author_username is not None:
            params["author_username"] = author_username
        if scope is not None:
            params["scope"] = scope
        if search is not None:
            params["search"] = search

        response = await self._client.get(self._base_path(project_id), **params)
        pagination = self._client.parse_pagination(response)
        items = [MergeRequest.model_validate(item) for item in response.json()]

        return PaginatedResponse[MergeRequest](
            items=items,
            page=pagination.page or page,
            per_page=pagination.per_page or per_page,
            total=pagination.total,
            total_pages=pagination.total_pages,
            next_page=pagination.next_page,
        )

    async def get(self, project_id: int | str, mr_iid: int) -> MergeRequest:
        """Get a single merge request by IID.

        Args:
            project_id: The project ID or URL-encoded path.
            mr_iid: The internal ID of the merge request.

        Returns:
            The merge request details.
        """
        response = await self._client.get(self._mr_path(project_id, mr_iid))
        return MergeRequest.model_validate(response.json())

    async def create(
        self,
        project_id: int | str,
        *,
        title: str,
        source_branch: str,
        target_branch: str,
        description: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
    ) -> MergeRequest:
        """Create a new merge request.

        Args:
            project_id: The project ID or URL-encoded path.
            title: The title of the merge request.
            source_branch: The source branch name.
            target_branch: The target branch name.
            description: Optional description body.
            labels: Optional list of label names.
            assignee_ids: Optional list of assignee user IDs.

        Returns:
            The created merge request.
        """
        body: dict[str, Any] = {
            "title": title,
            "source_branch": source_branch,
            "target_branch": target_branch,
        }
        if description is not None:
            body["description"] = description
        if labels is not None:
            body["labels"] = ",".join(labels)
        if assignee_ids is not None:
            body["assignee_ids"] = assignee_ids

        response = await self._client.post(self._base_path(project_id), **body)
        return MergeRequest.model_validate(response.json())

    async def update(self, project_id: int | str, mr_iid: int, **fields: Any) -> MergeRequest:
        """Update a merge request.

        Args:
            project_id: The project ID or URL-encoded path.
            mr_iid: The internal ID of the merge request.
            **fields: Fields to update (title, description, labels, etc.).

        Returns:
            The updated merge request.
        """
        response = await self._client.put(self._mr_path(project_id, mr_iid), **fields)
        return MergeRequest.model_validate(response.json())

    async def merge(
        self,
        project_id: int | str,
        mr_iid: int,
        *,
        squash: bool = False,
        delete_source_branch: bool = False,
    ) -> MergeRequest:
        """Accept and merge a merge request.

        Args:
            project_id: The project ID or URL-encoded path.
            mr_iid: The internal ID of the merge request.
            squash: Whether to squash commits.
            delete_source_branch: Whether to delete the source branch after merge.

        Returns:
            The merged merge request.
        """
        path = f"{self._mr_path(project_id, mr_iid)}/merge"
        body: dict[str, Any] = {}
        if squash:
            body["squash"] = True
        if delete_source_branch:
            body["should_remove_source_branch"] = True

        response = await self._client.put(path, **body)
        return MergeRequest.model_validate(response.json())

    async def approve(self, project_id: int | str, mr_iid: int) -> None:
        """Approve a merge request.

        Args:
            project_id: The project ID or URL-encoded path.
            mr_iid: The internal ID of the merge request.
        """
        path = f"{self._mr_path(project_id, mr_iid)}/approve"
        await self._client.post(path)

    async def diff(self, project_id: int | str, mr_iid: int) -> list[DiffFile]:
        """Get the diff files for a merge request.

        Args:
            project_id: The project ID or URL-encoded path.
            mr_iid: The internal ID of the merge request.

        Returns:
            List of diff files.
        """
        path = f"{self._mr_path(project_id, mr_iid)}/diffs"
        response = await self._client.get(path)
        return [DiffFile.model_validate(item) for item in response.json()]

    async def notes(self, project_id: int | str, mr_iid: int) -> list[Note]:
        """Get notes (comments) for a merge request.

        Args:
            project_id: The project ID or URL-encoded path.
            mr_iid: The internal ID of the merge request.

        Returns:
            List of notes.
        """
        path = f"{self._mr_path(project_id, mr_iid)}/notes"
        response = await self._client.get(path)
        return [Note.model_validate(item) for item in response.json()]

    async def create_note(self, project_id: int | str, mr_iid: int, body: str) -> Note:
        """Create a note (comment) on a merge request.

        Args:
            project_id: The project ID or URL-encoded path.
            mr_iid: The internal ID of the merge request.
            body: The note body text.

        Returns:
            The created note.
        """
        path = f"{self._mr_path(project_id, mr_iid)}/notes"
        response = await self._client.post(path, body=body)
        return Note.model_validate(response.json())
