"""Issue service bridging CLI/TUI with the GitLab Issue API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from gltools.client.exceptions import NotFoundError
from gltools.config.git_remote import detect_gitlab_remote
from gltools.models import DryRunResult, Issue, Note, PaginatedResponse
from gltools.services.merge_request import ProjectResolutionError

if TYPE_CHECKING:
    from gltools.client.gitlab import GitLabClient
    from gltools.config.settings import GitLabConfig

logger = logging.getLogger(__name__)


class IssueService:
    """High-level issue operations bridging CLI/TUI with the API client.

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
            Project ID or path.

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

    def _issue_endpoint(self, project: str, issue_iid: int | None = None) -> str:
        """Build the API endpoint URL for issue operations."""
        base = f"/projects/{self._encode_project(project)}/issues"
        if issue_iid is not None:
            return f"{base}/{issue_iid}"
        return base

    async def list_issues(
        self,
        *,
        state: str | None = None,
        labels: list[str] | None = None,
        assignee: str | None = None,
        milestone: str | None = None,
        scope: str | None = None,
        search: str | None = None,
        per_page: int = 20,
        page: int = 1,
        all_pages: bool = False,
    ) -> PaginatedResponse[Issue]:
        """List issues with optional filters and auto-pagination.

        Args:
            state: Filter by state (opened, closed, all).
            labels: Filter by labels.
            assignee: Filter by assignee username.
            milestone: Filter by milestone title.
            scope: Filter by scope (created_by_me, assigned_to_me, all).
            search: Search in title and description.
            per_page: Number of items per page.
            page: Page number to fetch.
            all_pages: If True, fetch all pages and combine results.

        Returns:
            Paginated response containing Issue models.
        """
        project = self._resolve_project()
        logger.debug("Fetching issues...")

        if not all_pages:
            result = await self._client.issues.list(
                project,
                state=state,
                labels=labels,
                assignee_username=assignee,
                milestone=milestone,
                scope=scope,
                search=search,
                per_page=per_page,
                page=page,
            )
            logger.debug("Found %d issues", len(result.items))
            return result

        all_items: list[Issue] = []
        current_page = 1
        while True:
            result = await self._client.issues.list(
                project,
                state=state,
                labels=labels,
                assignee_username=assignee,
                milestone=milestone,
                scope=scope,
                search=search,
                per_page=per_page,
                page=current_page,
            )
            all_items.extend(result.items)
            if result.next_page is None:
                break
            current_page = result.next_page

        logger.debug("Found %d issues (all pages)", len(all_items))
        return PaginatedResponse[Issue](
            items=all_items,
            page=1,
            per_page=len(all_items),
            total=len(all_items),
            total_pages=1,
            next_page=None,
        )

    async def get_issue(self, issue_iid: int) -> Issue:
        """Get a single issue by IID.

        Args:
            issue_iid: The internal issue ID within the project.

        Returns:
            The Issue model.

        Raises:
            NotFoundError: If the issue does not exist (including confidential 404s).
        """
        project = self._resolve_project()
        logger.debug("Fetching issue #%d...", issue_iid)
        try:
            issue = await self._client.issues.get(project, issue_iid)
            logger.debug("Fetched issue #%d: %s", issue_iid, issue.title)
            return issue
        except NotFoundError:
            logger.debug("Issue #%d not found", issue_iid)
            raise NotFoundError(resource="Issue not found", path=f"issues/{issue_iid}") from None

    async def create_issue(
        self,
        *,
        title: str,
        description: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        milestone_id: int | None = None,
        due_date: str | None = None,
        dry_run: bool = False,
    ) -> Issue | DryRunResult:
        """Create a new issue.

        Args:
            title: The issue title.
            description: The issue description.
            labels: Labels to assign.
            assignee_ids: User IDs to assign.
            milestone_id: Milestone ID to associate.
            due_date: Due date in YYYY-MM-DD format.
            dry_run: If True, return a preview instead of creating.

        Returns:
            The created Issue model, or DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Creating issue: %s...", title)

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

        if dry_run:
            logger.debug("Dry-run: would POST to %s", self._issue_endpoint(project))
            return DryRunResult(
                method="POST",
                url=self._issue_endpoint(project),
                body=body,
            )

        issue = await self._client.issues.create(
            project,
            title=title,
            description=description,
            labels=labels,
            assignee_ids=assignee_ids,
            milestone_id=milestone_id,
            due_date=due_date,
        )
        logger.debug("Issue created: #%d", issue.iid)
        return issue

    async def update_issue(
        self,
        issue_iid: int,
        *,
        dry_run: bool = False,
        **fields: Any,
    ) -> Issue | DryRunResult:
        """Update an existing issue.

        Args:
            issue_iid: The internal issue ID within the project.
            dry_run: If True, return a preview instead of updating.
            **fields: Fields to update (title, description, labels, etc.).

        Returns:
            The updated Issue model, or DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Updating issue #%d (fields: %s)...", issue_iid, list(fields.keys()))

        if dry_run:
            logger.debug("Dry-run: would PUT to %s", self._issue_endpoint(project, issue_iid))
            return DryRunResult(
                method="PUT",
                url=self._issue_endpoint(project, issue_iid),
                body=fields if fields else None,
            )

        issue = await self._client.issues.update(project, issue_iid, **fields)
        logger.debug("Issue #%d updated", issue_iid)
        return issue

    async def close_issue(
        self,
        issue_iid: int,
        *,
        dry_run: bool = False,
    ) -> Issue | DryRunResult:
        """Close an issue.

        Args:
            issue_iid: The internal issue ID within the project.
            dry_run: If True, return a preview instead of closing.

        Returns:
            The updated Issue model, or DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Closing issue #%d...", issue_iid)

        if dry_run:
            logger.debug("Dry-run: would close issue #%d", issue_iid)
            return DryRunResult(
                method="PUT",
                url=self._issue_endpoint(project, issue_iid),
                body={"state_event": "close"},
            )

        issue = await self._client.issues.close(project, issue_iid)
        logger.debug("Issue #%d closed", issue_iid)
        return issue

    async def reopen_issue(
        self,
        issue_iid: int,
        *,
        dry_run: bool = False,
    ) -> Issue | DryRunResult:
        """Reopen a closed issue.

        Args:
            issue_iid: The internal issue ID within the project.
            dry_run: If True, return a preview instead of reopening.

        Returns:
            The updated Issue model, or DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Reopening issue #%d...", issue_iid)

        if dry_run:
            logger.debug("Dry-run: would reopen issue #%d", issue_iid)
            return DryRunResult(
                method="PUT",
                url=self._issue_endpoint(project, issue_iid),
                body={"state_event": "reopen"},
            )

        issue = await self._client.issues.reopen(project, issue_iid)
        logger.debug("Issue #%d reopened", issue_iid)
        return issue

    async def add_note(
        self,
        issue_iid: int,
        body: str,
        *,
        dry_run: bool = False,
    ) -> Note | DryRunResult:
        """Add a note (comment) to an issue.

        Args:
            issue_iid: The internal issue ID within the project.
            body: The note body text.
            dry_run: If True, return a preview instead of creating.

        Returns:
            The created Note model, or DryRunResult if dry_run is True.
        """
        project = self._resolve_project()
        logger.debug("Adding note to issue #%d...", issue_iid)

        if dry_run:
            logger.debug("Dry-run: would POST note to issue #%d", issue_iid)
            return DryRunResult(
                method="POST",
                url=f"{self._issue_endpoint(project, issue_iid)}/notes",
                body={"body": body},
            )

        note = await self._client.issues.create_note(project, issue_iid, body)
        logger.debug("Note added to issue #%d", issue_iid)
        return note
