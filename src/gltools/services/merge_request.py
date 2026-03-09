"""MergeRequest service bridging CLI/TUI with the API client layer."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from gltools.config.git_remote import detect_gitlab_remote
from gltools.models import DiffFile, DryRunResult, MergeRequest, Note, PaginatedResponse

if TYPE_CHECKING:
    from gltools.client.gitlab import GitLabClient
    from gltools.config.settings import GitLabConfig

logger = logging.getLogger(__name__)


class ProjectResolutionError(Exception):
    """Raised when no project can be resolved from config, git remote, or explicit parameter."""

    def __init__(self, message: str | None = None) -> None:
        default = (
            "No project configured. Set 'default_project' in your config, "
            "run from a git repository with a GitLab remote, or pass --project explicitly."
        )
        super().__init__(message or default)


class MergeRequestService:
    """High-level merge request operations bridging CLI/TUI with the API client.

    Resolves the project from config, git remote, or explicit parameter.
    Supports dry-run mode to preview API calls without executing them.
    """

    def __init__(
        self,
        client: GitLabClient,
        config: GitLabConfig,
        *,
        project: str | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            client: Configured GitLab API client.
            config: Application configuration.
            project: Explicit project ID or path. Overrides config and git remote.
        """
        self._client = client
        self._config = config
        self._explicit_project = project

    def _resolve_project(self) -> str:
        """Resolve the project ID or path from available sources.

        Precedence:
        1. Explicit project passed to constructor
        2. default_project from config
        3. Auto-detected from git remote

        Returns:
            Project ID or URL-encoded path.

        Raises:
            ProjectResolutionError: If no project can be resolved.
        """
        logger.debug("Resolving project...")
        if self._explicit_project:
            logger.debug("Project resolved: %s (from --project flag)", self._explicit_project)
            return self._explicit_project

        if self._config.default_project:
            logger.debug("Project resolved: %s (from config)", self._config.default_project)
            return self._config.default_project

        remote_info = detect_gitlab_remote()
        if remote_info:
            logger.debug("Project resolved: %s (from git remote)", remote_info.project_path)
            return remote_info.project_path

        logger.debug("Project resolution failed: no project found from any source")
        raise ProjectResolutionError()

    def _encode_project(self, project: str) -> str:
        """URL-encode a project path for use in API endpoint paths."""
        return quote(project, safe="")

    def _mr_endpoint(self, project: str, mr_iid: int | None = None) -> str:
        """Build the API endpoint URL for merge request operations."""
        base = f"/projects/{self._encode_project(project)}/merge_requests"
        if mr_iid is not None:
            return f"{base}/{mr_iid}"
        return base

    async def list_mrs(
        self,
        *,
        state: str | None = None,
        labels: list[str] | None = None,
        author: str | None = None,
        scope: str | None = None,
        search: str | None = None,
        per_page: int = 20,
        page: int = 1,
        all_pages: bool = False,
    ) -> PaginatedResponse[MergeRequest]:
        """List merge requests with optional filters.

        Args:
            state: Filter by state (opened, closed, merged, all).
            labels: Filter by labels.
            author: Filter by author username.
            scope: Filter by scope (created_by_me, assigned_to_me, all).
            search: Search in title and description.
            per_page: Number of items per page.
            page: Page number to fetch.
            all_pages: If True, auto-paginate to collect all pages.

        Returns:
            Paginated response containing merge requests.
        """
        project = self._resolve_project()
        logger.debug("Fetching merge requests...")

        if not all_pages:
            result = await self._client.merge_requests.list(
                project,
                state=state,
                labels=labels,
                author_username=author,
                scope=scope,
                search=search,
                per_page=per_page,
                page=page,
            )
            logger.debug("Found %d merge requests", len(result.items))
            return result

        all_items: list[MergeRequest] = []
        current_page = 1
        while True:
            result = await self._client.merge_requests.list(
                project,
                state=state,
                labels=labels,
                author_username=author,
                scope=scope,
                search=search,
                per_page=per_page,
                page=current_page,
            )
            all_items.extend(result.items)
            if result.next_page is None:
                break
            current_page = result.next_page

        logger.debug("Found %d merge requests (all pages)", len(all_items))
        return PaginatedResponse[MergeRequest](
            items=all_items,
            page=1,
            per_page=len(all_items),
            total=len(all_items),
            total_pages=1,
            next_page=None,
        )

    async def get_mr(self, mr_iid: int) -> MergeRequest:
        """Get a single merge request by IID.

        Args:
            mr_iid: The internal ID of the merge request.

        Returns:
            The merge request details.
        """
        project = self._resolve_project()
        logger.debug("Fetching merge request !%d...", mr_iid)
        mr = await self._client.merge_requests.get(project, mr_iid)
        logger.debug("Fetched MR !%d: %s", mr_iid, mr.title)
        return mr

    async def create_mr(
        self,
        *,
        title: str,
        source_branch: str,
        target_branch: str,
        description: str | None = None,
        labels: list[str] | None = None,
        assignees: list[int] | None = None,
        dry_run: bool = False,
    ) -> MergeRequest | DryRunResult:
        """Create a new merge request.

        Args:
            title: The title of the merge request.
            source_branch: The source branch name.
            target_branch: The target branch name.
            description: Optional description body.
            labels: Optional list of label names.
            assignees: Optional list of assignee user IDs.
            dry_run: If True, return a preview without making the API call.

        Returns:
            The created merge request, or a DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Creating merge request: %s (%s -> %s)...", title, source_branch, target_branch)

        body: dict[str, Any] = {
            "title": title,
            "source_branch": source_branch,
            "target_branch": target_branch,
        }
        if description is not None:
            body["description"] = description
        if labels is not None:
            body["labels"] = ",".join(labels)
        if assignees is not None:
            body["assignee_ids"] = assignees

        if dry_run:
            logger.debug("Dry-run: would POST to %s", self._mr_endpoint(project))
            return DryRunResult(
                method="POST",
                url=self._mr_endpoint(project),
                body=body,
            )

        mr = await self._client.merge_requests.create(
            project,
            title=title,
            source_branch=source_branch,
            target_branch=target_branch,
            description=description,
            labels=labels,
            assignee_ids=assignees,
        )
        logger.debug("MR created: !%d", mr.iid)
        return mr

    async def update_mr(
        self,
        mr_iid: int,
        *,
        dry_run: bool = False,
        **fields: Any,
    ) -> MergeRequest | DryRunResult:
        """Update a merge request.

        Args:
            mr_iid: The internal ID of the merge request.
            dry_run: If True, return a preview without making the API call.
            **fields: Fields to update (title, description, labels, etc.).

        Returns:
            The updated merge request, or a DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Updating MR !%d (fields: %s)...", mr_iid, list(fields.keys()))

        if dry_run:
            logger.debug("Dry-run: would PUT to %s", self._mr_endpoint(project, mr_iid))
            return DryRunResult(
                method="PUT",
                url=self._mr_endpoint(project, mr_iid),
                body=fields if fields else None,
            )

        mr = await self._client.merge_requests.update(project, mr_iid, **fields)
        logger.debug("MR !%d updated", mr_iid)
        return mr

    async def merge_mr(
        self,
        mr_iid: int,
        *,
        squash: bool = False,
        delete_branch: bool = False,
        force: bool = False,
        dry_run: bool = False,
    ) -> MergeRequest | DryRunResult:
        """Accept and merge a merge request.

        Args:
            mr_iid: The internal ID of the merge request.
            squash: Whether to squash commits.
            delete_branch: Whether to delete the source branch after merge.
            force: Force merge even if checks have not passed.
            dry_run: If True, return a preview without making the API call.

        Returns:
            The merged merge request, or a DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Merging MR !%d (squash=%s, delete_branch=%s)...", mr_iid, squash, delete_branch)

        body: dict[str, Any] = {}
        if squash:
            body["squash"] = True
        if delete_branch:
            body["should_remove_source_branch"] = True
        if force:
            body["merge_when_pipeline_succeeds"] = False

        if dry_run:
            logger.debug("Dry-run: would PUT to %s/merge", self._mr_endpoint(project, mr_iid))
            return DryRunResult(
                method="PUT",
                url=f"{self._mr_endpoint(project, mr_iid)}/merge",
                body=body if body else None,
            )

        mr = await self._client.merge_requests.merge(
            project,
            mr_iid,
            squash=squash,
            delete_source_branch=delete_branch,
        )
        logger.debug("MR !%d merged", mr_iid)
        return mr

    async def approve_mr(
        self,
        mr_iid: int,
        *,
        dry_run: bool = False,
    ) -> None | DryRunResult:
        """Approve a merge request.

        Args:
            mr_iid: The internal ID of the merge request.
            dry_run: If True, return a preview without making the API call.

        Returns:
            None on success, or a DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Approving MR !%d...", mr_iid)

        if dry_run:
            logger.debug("Dry-run: would POST to %s/approve", self._mr_endpoint(project, mr_iid))
            return DryRunResult(
                method="POST",
                url=f"{self._mr_endpoint(project, mr_iid)}/approve",
                body=None,
            )

        await self._client.merge_requests.approve(project, mr_iid)
        logger.debug("MR !%d approved", mr_iid)
        return None

    async def get_diff(self, mr_iid: int) -> list[DiffFile]:
        """Get the diff files for a merge request.

        Args:
            mr_iid: The internal ID of the merge request.

        Returns:
            List of diff files.
        """
        project = self._resolve_project()
        logger.debug("Fetching diff for MR !%d...", mr_iid)
        diffs = await self._client.merge_requests.diff(project, mr_iid)
        logger.debug("Fetched %d diff files for MR !%d", len(diffs), mr_iid)
        return diffs

    async def add_note(
        self,
        mr_iid: int,
        body: str,
        *,
        dry_run: bool = False,
    ) -> Note | DryRunResult:
        """Create a note (comment) on a merge request.

        Args:
            mr_iid: The internal ID of the merge request.
            body: The note body text.
            dry_run: If True, return a preview without making the API call.

        Returns:
            The created note, or a DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Adding note to MR !%d...", mr_iid)

        if dry_run:
            logger.debug("Dry-run: would POST note to MR !%d", mr_iid)
            return DryRunResult(
                method="POST",
                url=f"{self._mr_endpoint(project, mr_iid)}/notes",
                body={"body": body},
            )

        note = await self._client.merge_requests.create_note(project, mr_iid, body)
        logger.debug("Note added to MR !%d", mr_iid)
        return note

    async def close_mr(
        self,
        mr_iid: int,
        *,
        dry_run: bool = False,
    ) -> MergeRequest | DryRunResult:
        """Close a merge request.

        Args:
            mr_iid: The internal ID of the merge request.
            dry_run: If True, return a preview without making the API call.

        Returns:
            The closed merge request, or a DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Closing MR !%d...", mr_iid)

        if dry_run:
            logger.debug("Dry-run: would close MR !%d", mr_iid)
            return DryRunResult(
                method="PUT",
                url=self._mr_endpoint(project, mr_iid),
                body={"state_event": "close"},
            )

        mr = await self._client.merge_requests.update(
            project, mr_iid, state_event="close"
        )
        logger.debug("MR !%d closed", mr_iid)
        return mr

    async def reopen_mr(
        self,
        mr_iid: int,
        *,
        dry_run: bool = False,
    ) -> MergeRequest | DryRunResult:
        """Reopen a closed merge request.

        Args:
            mr_iid: The internal ID of the merge request.
            dry_run: If True, return a preview without making the API call.

        Returns:
            The reopened merge request, or a DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Reopening MR !%d...", mr_iid)

        if dry_run:
            logger.debug("Dry-run: would reopen MR !%d", mr_iid)
            return DryRunResult(
                method="PUT",
                url=self._mr_endpoint(project, mr_iid),
                body={"state_event": "reopen"},
            )

        mr = await self._client.merge_requests.update(
            project, mr_iid, state_event="reopen"
        )
        logger.debug("MR !%d reopened", mr_iid)
        return mr
