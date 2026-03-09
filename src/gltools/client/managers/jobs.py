"""Job resource manager for GitLab CI/CD API operations."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from urllib.parse import quote

from gltools.client.exceptions import NotFoundError
from gltools.models.job import Job

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from gltools.client.http import GitLabHTTPClient


def _encode_project(project_id: int | str) -> str:
    """URL-encode a project ID (handles both numeric IDs and namespace/project paths)."""
    if isinstance(project_id, int):
        return str(project_id)
    return quote(project_id, safe="")


class JobManager:
    """Typed manager for GitLab CI/CD job API operations."""

    def __init__(self, client: GitLabHTTPClient) -> None:
        self._client = client

    def _job_path(self, project_id: int | str, job_id: int) -> str:
        return f"/projects/{_encode_project(project_id)}/jobs/{job_id}"

    async def list(self, project_id: int | str, pipeline_id: int) -> list[Job]:
        """List jobs for a specific pipeline.

        Args:
            project_id: The project ID or URL-encoded path.
            pipeline_id: The pipeline ID.

        Returns:
            A list of Job objects for the pipeline.
        """
        path = f"/projects/{_encode_project(project_id)}/pipelines/{pipeline_id}/jobs"
        response = await self._client.get(path)
        return [Job.model_validate(item) for item in response.json()]

    async def get(self, project_id: int | str, job_id: int) -> Job:
        """Get a single job by ID.

        Args:
            project_id: The project ID or URL-encoded path.
            job_id: The job ID.

        Returns:
            The Job object.

        Raises:
            NotFoundError: If the job is not found.
        """
        path = self._job_path(project_id, job_id)
        try:
            response = await self._client.get(path)
        except NotFoundError:
            raise NotFoundError(resource="Job", path=path) from None
        return Job.model_validate(response.json())

    @asynccontextmanager
    async def logs(self, project_id: int | str, job_id: int) -> AsyncIterator[AsyncIterator[bytes]]:
        """Stream job log output without loading entirely into memory.

        Usage:
            async with job_manager.logs(project_id, job_id) as stream:
                async for chunk in stream:
                    process(chunk)

        Args:
            project_id: The project ID or URL-encoded path.
            job_id: The job ID.

        Yields:
            An async iterator of byte chunks from the job log.

        Raises:
            NotFoundError: If the job is not found.
        """
        path = self._job_path(project_id, job_id)
        try:
            async with self._client.stream_get(f"{path}/trace") as stream:
                yield stream
        except NotFoundError:
            raise NotFoundError(resource="Job", path=path) from None

    @asynccontextmanager
    async def artifacts(self, project_id: int | str, job_id: int) -> AsyncIterator[AsyncIterator[bytes]]:
        """Stream job artifacts download without loading entirely into memory.

        Usage:
            async with job_manager.artifacts(project_id, job_id) as stream:
                async for chunk in stream:
                    write_to_file(chunk)

        Args:
            project_id: The project ID or URL-encoded path.
            job_id: The job ID.

        Yields:
            An async iterator of byte chunks from the artifacts archive.

        Raises:
            NotFoundError: If the job is not found.
        """
        path = self._job_path(project_id, job_id)
        try:
            async with self._client.stream_get(f"{path}/artifacts") as stream:
                yield stream
        except NotFoundError:
            raise NotFoundError(resource="Job", path=path) from None
