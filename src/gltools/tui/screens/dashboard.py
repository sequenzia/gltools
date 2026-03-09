"""Dashboard screen showing an overview of recent GitLab activity."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, LoadingIndicator, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from gltools.config.settings import GitLabConfig
    from gltools.models.issue import Issue
    from gltools.models.merge_request import MergeRequest
    from gltools.models.pipeline import Pipeline

logger = logging.getLogger(__name__)

STATUS_ICONS: dict[str, str] = {
    "opened": "[green]\u25cf[/]",
    "merged": "[magenta]\u25cf[/]",
    "closed": "[red]\u25cf[/]",
    "locked": "[yellow]\u25cf[/]",
    "success": "[green]\u2714[/]",
    "failed": "[red]\u2718[/]",
    "running": "[blue]\u25b6[/]",
    "pending": "[yellow]\u25cb[/]",
    "canceled": "[dim]\u2718[/]",
    "skipped": "[dim]\u25cb[/]",
    "created": "[dim]\u25cb[/]",
    "manual": "[yellow]\u25a0[/]",
}


def _status_icon(status: str) -> str:
    """Return a Rich markup status icon for a given status string."""
    return STATUS_ICONS.get(status, f"[dim]{status}[/]")


class ItemSelected(Message):
    """Message emitted when a dashboard item is selected for navigation."""

    def __init__(self, item_type: str, item_id: int) -> None:
        super().__init__()
        self.item_type = item_type
        self.item_id = item_id


class DashboardPanel(Widget):
    """A single panel in the dashboard showing a list of items with a title."""

    DEFAULT_CSS = """
    DashboardPanel {
        height: 1fr;
        border: solid $primary-background;
        padding: 0 1;
    }

    DashboardPanel .panel-title {
        text-style: bold;
        padding: 0 0 1 0;
        color: $text;
    }

    DashboardPanel .panel-empty {
        color: $text-muted;
        padding: 1 0;
    }

    DashboardPanel .panel-error {
        color: $error;
        padding: 1 0;
    }

    DashboardPanel LoadingIndicator {
        height: 3;
    }

    DashboardPanel ListView {
        height: 1fr;
    }

    DashboardPanel ListItem {
        height: auto;
        padding: 0 1;
    }

    DashboardPanel ListItem:hover {
        background: $boost;
    }
    """

    def __init__(self, title: str, panel_id: str) -> None:
        super().__init__(id=panel_id)
        self._title = title

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="panel-title")
        yield LoadingIndicator()

    def show_loading(self) -> None:
        """Show the loading indicator."""
        with contextlib.suppress(NoMatches):
            self.query_one(LoadingIndicator).display = True
        with contextlib.suppress(NoMatches):
            self.query_one(ListView).display = False

    def show_items(self, items: list[ListItem]) -> None:
        """Replace loading indicator with a list of items."""
        with contextlib.suppress(NoMatches):
            self.query_one(LoadingIndicator).display = False

        with contextlib.suppress(NoMatches):
            self.query_one(ListView).remove()

        if not items:
            self.mount(Static("No items found", classes="panel-empty"))
            return

        list_view = ListView(*items)
        self.mount(list_view)

    def show_error(self, error_message: str) -> None:
        """Replace loading indicator with an error message."""
        with contextlib.suppress(NoMatches):
            self.query_one(LoadingIndicator).display = False

        self.mount(Static(f"Error: {error_message}", classes="panel-error"))


class DashboardScreen(Widget):
    """Dashboard overview screen showing recent MRs, issues, and pipeline status.

    Asynchronously loads data from the services layer and displays it
    in three side-by-side panels. Supports click/Enter navigation
    to detail screens via the ItemSelected message.
    """

    DEFAULT_CSS = """
    DashboardScreen {
        height: 1fr;
        padding: 1 2;
    }

    DashboardScreen #dashboard-header {
        height: auto;
        padding: 0 0 1 0;
    }

    DashboardScreen #dashboard-panels {
        height: 1fr;
    }
    """

    def __init__(self, config: GitLabConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield Static(f"Dashboard - {self._config.host}", id="dashboard-header")
        with Horizontal(id="dashboard-panels"):
            yield DashboardPanel("Recent Merge Requests", "panel-mrs")
            yield DashboardPanel("Recent Issues", "panel-issues")
            yield DashboardPanel("Pipeline Status", "panel-pipelines")

    def on_mount(self) -> None:
        """Start async data loading when the screen mounts."""
        self._load_all_data()

    def _load_all_data(self) -> None:
        """Kick off all three data loading workers."""
        self.run_worker(self._load_mrs(), name="load_mrs", exclusive=True)
        self.run_worker(self._load_issues(), name="load_issues", exclusive=True)
        self.run_worker(self._load_pipelines(), name="load_pipelines", exclusive=True)

    async def _create_client(self) -> tuple[object, object] | None:
        """Create a GitLabClient for data fetching.

        Returns a (client, token) tuple, or None if authentication is missing.
        """
        from gltools.client.gitlab import GitLabClient

        token = self._config.token
        if not token:
            return None

        client = GitLabClient(host=self._config.host, token=token)
        return client, token

    async def _load_mrs(self) -> None:
        """Load recent merge requests asynchronously."""
        panel = self.query_one("#panel-mrs", DashboardPanel)

        result = await self._create_client()
        if result is None:
            panel.show_error("Authentication not configured")
            return

        client, _token = result
        try:
            from gltools.services.merge_request import MergeRequestService

            service = MergeRequestService(client, self._config)
            response = await service.list_mrs(state="opened", per_page=10)
            items = [self._mr_to_list_item(mr) for mr in response.items]
            panel.show_items(items)
        except Exception as exc:
            logger.exception("Failed to load merge requests")
            panel.show_error(str(exc))
        finally:
            await client.close()

    async def _load_issues(self) -> None:
        """Load recent issues asynchronously."""
        panel = self.query_one("#panel-issues", DashboardPanel)

        result = await self._create_client()
        if result is None:
            panel.show_error("Authentication not configured")
            return

        client, _token = result
        try:
            from gltools.services.issue import IssueService

            service = IssueService(client, self._config)
            response = await service.list_issues(state="opened", per_page=10)
            items = [self._issue_to_list_item(issue) for issue in response.items]
            panel.show_items(items)
        except Exception as exc:
            logger.exception("Failed to load issues")
            panel.show_error(str(exc))
        finally:
            await client.close()

    async def _load_pipelines(self) -> None:
        """Load recent pipeline statuses asynchronously."""
        panel = self.query_one("#panel-pipelines", DashboardPanel)

        result = await self._create_client()
        if result is None:
            panel.show_error("Authentication not configured")
            return

        client, _token = result
        try:
            from gltools.config.git_remote import detect_gitlab_remote
            from gltools.services.ci import CIService

            remote_info = detect_gitlab_remote()
            project = self._config.default_project or (
                remote_info.project_path_encoded if remote_info else None
            )

            if not project:
                panel.show_error("No project configured or detected")
                return

            service = CIService(
                project_id=project,
                pipeline_manager=client.pipelines,
                job_manager=client.jobs,
                mr_manager=client.merge_requests,
            )
            response = await service.list_pipelines(per_page=10)
            items = [self._pipeline_to_list_item(p) for p in response.items]
            panel.show_items(items)
        except Exception as exc:
            logger.exception("Failed to load pipelines")
            panel.show_error(str(exc))
        finally:
            await client.close()

    def _mr_to_list_item(self, mr: MergeRequest) -> ListItem:
        """Convert a MergeRequest to a ListItem widget."""
        icon = _status_icon(mr.state)
        label = f"{icon} !{mr.iid} {mr.title} ({mr.author.username})"
        item = ListItem(Static(label, markup=True))
        item.set_class(True, "mr-item")
        item._dashboard_item_type = "mr"  # type: ignore[attr-defined]
        item._dashboard_item_id = mr.iid  # type: ignore[attr-defined]
        return item

    def _issue_to_list_item(self, issue: Issue) -> ListItem:
        """Convert an Issue to a ListItem widget."""
        icon = _status_icon(issue.state)
        labels_str = ""
        if issue.labels:
            labels_str = " [" + ", ".join(issue.labels[:3]) + "]"
        label = f"{icon} #{issue.iid} {issue.title}{labels_str} ({issue.state})"
        item = ListItem(Static(label, markup=True))
        item.set_class(True, "issue-item")
        item._dashboard_item_type = "issue"  # type: ignore[attr-defined]
        item._dashboard_item_id = issue.iid  # type: ignore[attr-defined]
        return item

    def _pipeline_to_list_item(self, pipeline: Pipeline) -> ListItem:
        """Convert a Pipeline to a ListItem widget."""
        icon = _status_icon(pipeline.status)
        duration_str = ""
        if pipeline.duration is not None:
            duration_str = f" ({pipeline.duration:.0f}s)"
        label = f"{icon} #{pipeline.id} {pipeline.ref} - {pipeline.status}{duration_str}"
        item = ListItem(Static(label, markup=True))
        item.set_class(True, "pipeline-item")
        item._dashboard_item_type = "pipeline"  # type: ignore[attr-defined]
        item._dashboard_item_id = pipeline.id  # type: ignore[attr-defined]
        return item

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle item selection in any panel's list view."""
        item = event.item
        item_type = getattr(item, "_dashboard_item_type", None)
        item_id = getattr(item, "_dashboard_item_id", None)
        if item_type and item_id is not None:
            self.post_message(ItemSelected(item_type=item_type, item_id=item_id))
