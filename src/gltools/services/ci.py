"""CI service bridging CLI/TUI with Pipeline and Job API client layer."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from gltools.models.output import DryRunResult, PaginatedResponse
from gltools.models.pipeline import Pipeline

logger = logging.getLogger("gltools.services.ci")

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from gltools.client.managers.jobs import JobManager
    from gltools.client.managers.merge_requests import MergeRequestManager
    from gltools.client.managers.pipelines import PipelineManager
    from gltools.models.job import Job


class NoPipelineError(Exception):
    """Raised when no pipeline is found for a given branch or MR."""

    def __init__(self, ref: str | None = None, mr_iid: int | None = None) -> None:
        if mr_iid is not None:
            msg = f"No pipelines found for merge request !{mr_iid}"
        elif ref is not None:
            msg = f"No pipelines found for branch '{ref}'"
        else:
            msg = "No pipelines found"
        super().__init__(msg)


def _get_current_branch() -> str | None:
    """Get the current git branch name, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch and branch != "HEAD" else None


class CIService:
    """Bridges CLI/TUI with Pipeline and Job API client layer.

    Provides high-level CI/CD operations including branch/MR resolution,
    dry-run support, streaming logs, and artifact downloads.
    """

    def __init__(
        self,
        *,
        project_id: int | str,
        pipeline_manager: PipelineManager,
        job_manager: JobManager,
        mr_manager: MergeRequestManager,
    ) -> None:
        self._project_id = project_id
        self._pipelines = pipeline_manager
        self._jobs = job_manager
        self._mrs = mr_manager

    async def get_status(
        self,
        *,
        mr_iid: int | None = None,
        ref: str | None = None,
    ) -> Pipeline:
        """Get the current pipeline for a branch or MR.

        When mr_iid is provided, fetches the pipeline associated with that MR.
        Otherwise, looks up the most recent pipeline for the given ref (or
        current git branch if ref is None).

        Args:
            mr_iid: Merge request IID to get pipeline from.
            ref: Git ref (branch/tag). Defaults to current branch.

        Returns:
            The most recent Pipeline.

        Raises:
            NoPipelineError: If no pipeline is found.
            ValueError: If ref cannot be determined.
        """
        logger.debug("Getting pipeline status...")
        if mr_iid is not None:
            logger.debug("Resolving pipeline from MR !%d", mr_iid)
            return await self._get_pipeline_from_mr(mr_iid)

        if ref is None:
            ref = _get_current_branch()
            if ref is None:
                raise ValueError(
                    "Cannot determine current branch. Specify --ref or run from a git repository."
                )
            logger.debug("Resolved ref from current branch: %s", ref)

        logger.debug("Fetching latest pipeline for ref '%s'...", ref)
        result = await self._pipelines.list(self._project_id, ref=ref, per_page=1, page=1)
        if not result.items:
            raise NoPipelineError(ref=ref)

        pipeline = result.items[0]
        logger.debug("Found pipeline #%d (status: %s)", pipeline.id, pipeline.status)
        return await self._pipelines.get(self._project_id, pipeline.id)

    async def _get_pipeline_from_mr(self, mr_iid: int) -> Pipeline:
        """Resolve the pipeline attached to a merge request."""
        mr = await self._mrs.get(self._project_id, mr_iid)
        if mr.pipeline is None:
            logger.debug("MR !%d has no pipeline attached", mr_iid)
            raise NoPipelineError(mr_iid=mr_iid)
        logger.debug("MR !%d has pipeline #%d", mr_iid, mr.pipeline.id)
        return await self._pipelines.get(self._project_id, mr.pipeline.id)

    async def list_pipelines(
        self,
        *,
        status: str | None = None,
        ref: str | None = None,
        source: str | None = None,
        per_page: int = 20,
        page: int = 1,
        all_pages: bool = False,
    ) -> PaginatedResponse[Pipeline]:
        """List pipelines with optional filters.

        Args:
            status: Filter by pipeline status.
            ref: Filter by git ref.
            source: Filter by pipeline source.
            per_page: Items per page.
            page: Page number.
            all_pages: If True, fetch all pages and combine results.

        Returns:
            Paginated response of pipelines.
        """
        logger.debug("Fetching pipelines...")
        if not all_pages:
            result = await self._pipelines.list(
                self._project_id,
                status=status,
                ref=ref,
                source=source,
                per_page=per_page,
                page=page,
            )
            logger.debug("Found %d pipelines", len(result.items))
            return result

        all_items: list[Pipeline] = []
        current_page = 1
        while True:
            result = await self._pipelines.list(
                self._project_id,
                status=status,
                ref=ref,
                source=source,
                per_page=per_page,
                page=current_page,
            )
            all_items.extend(result.items)
            if result.next_page is None:
                break
            current_page = result.next_page

        logger.debug("Found %d pipelines (all pages)", len(all_items))
        return PaginatedResponse[Pipeline](
            items=all_items,
            page=1,
            per_page=len(all_items),
            total=len(all_items),
            total_pages=1,
            next_page=None,
        )

    async def trigger_pipeline(
        self,
        *,
        ref: str | None = None,
        dry_run: bool = False,
    ) -> Pipeline | DryRunResult:
        """Trigger a new pipeline for a ref.

        Args:
            ref: Branch or tag to run pipeline for. Defaults to current branch.
            dry_run: If True, return a preview instead of executing.

        Returns:
            The created Pipeline, or DryRunResult if dry_run is True.

        Raises:
            ValueError: If ref cannot be determined.
        """
        if ref is None:
            ref = _get_current_branch()
            if ref is None:
                raise ValueError(
                    "Cannot determine current branch. Specify --ref or run from a git repository."
                )
            logger.debug("Resolved ref from current branch: %s", ref)

        logger.debug("Triggering pipeline for ref '%s'...", ref)
        if dry_run:
            logger.debug("Dry-run: would POST pipeline for ref '%s'", ref)
            return DryRunResult(
                method="POST",
                url=f"/projects/{self._project_id}/pipeline",
                body={"ref": ref},
            )

        pipeline = await self._pipelines.create(self._project_id, ref=ref)
        logger.debug("Pipeline #%d triggered for ref '%s'", pipeline.id, ref)
        return pipeline

    async def retry_pipeline(
        self,
        pipeline_id: int,
        *,
        dry_run: bool = False,
    ) -> Pipeline | DryRunResult:
        """Retry a failed pipeline.

        Args:
            pipeline_id: The pipeline ID to retry.
            dry_run: If True, return a preview instead of executing.

        Returns:
            The retried Pipeline, or DryRunResult if dry_run is True.
        """
        logger.debug("Retrying pipeline #%d...", pipeline_id)
        if dry_run:
            logger.debug("Dry-run: would retry pipeline #%d", pipeline_id)
            return DryRunResult(
                method="POST",
                url=f"/projects/{self._project_id}/pipelines/{pipeline_id}/retry",
            )

        pipeline = await self._pipelines.retry(self._project_id, pipeline_id)
        logger.debug("Pipeline #%d retried", pipeline_id)
        return pipeline

    async def cancel_pipeline(
        self,
        pipeline_id: int,
        *,
        dry_run: bool = False,
    ) -> Pipeline | DryRunResult:
        """Cancel a running pipeline.

        Args:
            pipeline_id: The pipeline ID to cancel.
            dry_run: If True, return a preview instead of executing.

        Returns:
            The cancelled Pipeline, or DryRunResult if dry_run is True.
        """
        logger.debug("Cancelling pipeline #%d...", pipeline_id)
        if dry_run:
            logger.debug("Dry-run: would cancel pipeline #%d", pipeline_id)
            return DryRunResult(
                method="POST",
                url=f"/projects/{self._project_id}/pipelines/{pipeline_id}/cancel",
            )

        pipeline = await self._pipelines.cancel(self._project_id, pipeline_id)
        logger.debug("Pipeline #%d cancelled", pipeline_id)
        return pipeline

    async def list_jobs(self, pipeline_id: int) -> list[Job]:
        """List jobs in a pipeline.

        Args:
            pipeline_id: The pipeline ID.

        Returns:
            List of jobs in the pipeline.
        """
        logger.debug("Fetching jobs for pipeline #%d...", pipeline_id)
        jobs = await self._jobs.list(self._project_id, pipeline_id)
        logger.debug("Found %d jobs for pipeline #%d", len(jobs), pipeline_id)
        return jobs

    async def get_logs(
        self,
        job_id: int,
        *,
        tail: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream job log output.

        Streams log content without loading the entire log into memory.
        When tail is specified, only the last N lines are yielded.

        Args:
            job_id: The job ID.
            tail: If set, yield only the last N lines.

        Yields:
            String chunks (or lines when tail is used) from the job log.
        """
        logger.debug("Streaming logs for job #%d (tail=%s)...", job_id, tail)
        if tail is not None:
            async for line in self._get_tail_logs(job_id, tail):
                yield line
        else:
            async with self._jobs.logs(self._project_id, job_id) as stream:
                async for chunk in stream:
                    yield chunk.decode("utf-8", errors="replace")

    async def _get_tail_logs(self, job_id: int, n: int) -> AsyncIterator[str]:
        """Get the last N lines of a job log using a ring buffer.

        Streams the entire log but only keeps the last N lines in memory,
        avoiding loading the full log into a single string.
        """
        from collections import deque

        buffer: deque[str] = deque(maxlen=n)
        partial_line = ""

        async with self._jobs.logs(self._project_id, job_id) as stream:
            async for chunk in stream:
                text = partial_line + chunk.decode("utf-8", errors="replace")
                lines = text.split("\n")
                partial_line = lines.pop()
                for line in lines:
                    buffer.append(line)

        if partial_line:
            buffer.append(partial_line)

        for line in buffer:
            yield line + "\n"

    async def download_artifacts(
        self,
        job_id: int,
        *,
        output_path: Path | str | None = None,
    ) -> bytes | Path:
        """Download job artifacts.

        When output_path is provided, streams to the file and returns the Path.
        Otherwise, collects all bytes in memory and returns them (for stdout).

        Args:
            job_id: The job ID.
            output_path: Optional file path to write artifacts to.

        Returns:
            Path if written to file, or bytes if no output_path.
        """
        logger.debug("Downloading artifacts for job #%d...", job_id)
        if output_path is not None:
            path = Path(output_path)
            async with self._jobs.artifacts(self._project_id, job_id) as stream:
                with path.open("wb") as f:
                    async for chunk in stream:
                        f.write(chunk)
            logger.debug("Artifacts saved to %s", path)
            return path

        chunks: list[bytes] = []
        async with self._jobs.artifacts(self._project_id, job_id) as stream:
            async for chunk in stream:
                chunks.append(chunk)
        logger.debug("Artifacts downloaded (%d bytes)", sum(len(c) for c in chunks))
        return b"".join(chunks)
