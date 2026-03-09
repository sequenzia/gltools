"""Pipeline resource manager for GitLab CI/CD API operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

from gltools.client.exceptions import NotFoundError
from gltools.models.output import PaginatedResponse
from gltools.models.pipeline import Pipeline

if TYPE_CHECKING:
    from gltools.client.http import GitLabHTTPClient


def _encode_project(project_id: int | str) -> str:
    """URL-encode a project ID (handles both numeric IDs and namespace/project paths)."""
    if isinstance(project_id, int):
        return str(project_id)
    return quote(project_id, safe="")


class PipelineManager:
    """Typed manager for GitLab CI/CD pipeline API operations."""

    def __init__(self, client: GitLabHTTPClient) -> None:
        self._client = client

    def _base_path(self, project_id: int | str) -> str:
        return f"/projects/{_encode_project(project_id)}/pipelines"

    def _pipeline_path(self, project_id: int | str, pipeline_id: int) -> str:
        return f"{self._base_path(project_id)}/{pipeline_id}"

    async def list(
        self,
        project_id: int | str,
        *,
        status: str | None = None,
        ref: str | None = None,
        source: str | None = None,
        per_page: int = 20,
        page: int = 1,
    ) -> PaginatedResponse[Pipeline]:
        """List pipelines for a project with optional filters.

        Args:
            project_id: The project ID or URL-encoded path.
            status: Filter by pipeline status (e.g., "running", "success", "failed").
            ref: Filter by git ref (branch or tag name).
            source: Filter by pipeline source (e.g., "push", "merge_request_event").
            per_page: Number of items per page.
            page: Page number to retrieve.

        Returns:
            A paginated response containing Pipeline objects.
        """
        params: dict[str, str | int] = {"per_page": per_page, "page": page}
        if status is not None:
            params["status"] = status
        if ref is not None:
            params["ref"] = ref
        if source is not None:
            params["source"] = source

        response = await self._client.get(self._base_path(project_id), **params)
        pagination = self._client.parse_pagination(response)

        items = [Pipeline.model_validate(item) for item in response.json()]
        return PaginatedResponse[Pipeline](
            items=items,
            page=pagination.page or page,
            per_page=pagination.per_page or per_page,
            total=pagination.total,
            total_pages=pagination.total_pages,
            next_page=pagination.next_page,
        )

    async def get(self, project_id: int | str, pipeline_id: int) -> Pipeline:
        """Get a single pipeline by ID.

        Args:
            project_id: The project ID or URL-encoded path.
            pipeline_id: The pipeline ID.

        Returns:
            The Pipeline object.

        Raises:
            NotFoundError: If the pipeline is not found.
        """
        path = self._pipeline_path(project_id, pipeline_id)
        try:
            response = await self._client.get(path)
        except NotFoundError:
            raise NotFoundError(resource="Pipeline", path=path) from None
        return Pipeline.model_validate(response.json())

    async def create(self, project_id: int | str, *, ref: str) -> Pipeline:
        """Trigger a new pipeline for a ref.

        Args:
            project_id: The project ID or URL-encoded path.
            ref: The branch or tag to run the pipeline for.

        Returns:
            The newly created Pipeline object.
        """
        path = f"/projects/{_encode_project(project_id)}/pipeline"
        response = await self._client.post(path, ref=ref)
        return Pipeline.model_validate(response.json())

    async def retry(self, project_id: int | str, pipeline_id: int) -> Pipeline:
        """Retry a pipeline.

        Args:
            project_id: The project ID or URL-encoded path.
            pipeline_id: The pipeline ID to retry.

        Returns:
            The retried Pipeline object.

        Raises:
            NotFoundError: If the pipeline is not found.
        """
        path = self._pipeline_path(project_id, pipeline_id)
        try:
            response = await self._client.post(f"{path}/retry")
        except NotFoundError:
            raise NotFoundError(resource="Pipeline", path=path) from None
        return Pipeline.model_validate(response.json())

    async def cancel(self, project_id: int | str, pipeline_id: int) -> Pipeline:
        """Cancel a running pipeline.

        Args:
            project_id: The project ID or URL-encoded path.
            pipeline_id: The pipeline ID to cancel.

        Returns:
            The cancelled Pipeline object.

        Raises:
            NotFoundError: If the pipeline is not found.
        """
        path = self._pipeline_path(project_id, pipeline_id)
        try:
            response = await self._client.post(f"{path}/cancel")
        except NotFoundError:
            raise NotFoundError(resource="Pipeline", path=path) from None
        return Pipeline.model_validate(response.json())
