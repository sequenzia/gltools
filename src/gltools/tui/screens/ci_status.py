"""CI/CD pipeline status TUI screen with pipeline list, job breakdown, and log viewer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import on, work
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, DataTable, Label, LoadingIndicator, Static, TabbedContent, TabPane

from gltools.tui.widgets.status_badge import status_color

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from gltools.models.job import Job
    from gltools.models.pipeline import Pipeline

# Auto-refresh interval in seconds for running pipelines
AUTO_REFRESH_INTERVAL = 10.0


class PipelineSelected(Message):
    """Message posted when a pipeline is selected from the list."""

    def __init__(self, pipeline_id: int) -> None:
        super().__init__()
        self.pipeline_id = pipeline_id


class PipelineActionRequested(Message):
    """Message posted when a pipeline action button is pressed."""

    def __init__(self, action: str, pipeline_id: int) -> None:
        super().__init__()
        self.action = action
        self.pipeline_id = pipeline_id


class PipelineListPanel(Widget):
    """Panel showing a list of pipelines with status, ref, and duration."""

    DEFAULT_CSS = """
    PipelineListPanel {
        height: 1fr;
        width: 1fr;
        layout: vertical;
    }

    PipelineListPanel #pipeline-table {
        height: 1fr;
    }

    PipelineListPanel #pipeline-loading {
        height: 1fr;
        content-align: center middle;
    }

    PipelineListPanel #no-pipelines-msg {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    """

    _pipeline_data: list[Pipeline] = []

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._pipeline_data = []

    def compose(self) -> ComposeResult:
        yield Static("[bold]Pipelines[/bold]", id="pipeline-list-title")
        yield LoadingIndicator(id="pipeline-loading")
        table: DataTable[str] = DataTable(id="pipeline-table")
        table.cursor_type = "row"
        table.zebra_stripes = True
        yield table
        yield Static("[dim]No pipelines found.[/dim]", id="no-pipelines-msg")

    def on_mount(self) -> None:
        """Set up DataTable columns."""
        table = self.query_one("#pipeline-table", DataTable)
        table.add_column("ID", key="id", width=10)
        table.add_column("Status", key="status", width=12)
        table.add_column("Ref", key="ref", width=20)
        table.add_column("Source", key="source", width=12)
        table.add_column("Duration", key="duration", width=12)
        table.add_column("Created", key="created", width=18)
        table.display = False
        no_msg = self.query_one("#no-pipelines-msg", Static)
        no_msg.display = False

    def populate(self, pipelines: list[Pipeline]) -> None:
        """Populate the table with pipeline data."""
        self._pipeline_data = pipelines

        loading = self.query_one("#pipeline-loading", LoadingIndicator)
        loading.display = False
        table = self.query_one("#pipeline-table", DataTable)
        no_msg = self.query_one("#no-pipelines-msg", Static)

        table.clear()

        if not pipelines:
            table.display = False
            no_msg.display = True
            return

        no_msg.display = False
        table.display = True

        for pipeline in pipelines:
            pid = str(pipeline.id)
            status_styled = f"[{status_color(pipeline.status)}]{pipeline.status}[/]"
            ref = pipeline.ref[:18] + ".." if len(pipeline.ref) > 20 else pipeline.ref
            source = pipeline.source
            duration = f"{pipeline.duration:.0f}s" if pipeline.duration is not None else "-"
            created = str(pipeline.created_at)[:16]
            table.add_row(pid, status_styled, ref, source, duration, created, key=str(pipeline.id))

    def show_loading(self) -> None:
        """Show loading state."""
        loading = self.query_one("#pipeline-loading", LoadingIndicator)
        loading.display = True
        table = self.query_one("#pipeline-table", DataTable)
        table.display = False
        no_msg = self.query_one("#no-pipelines-msg", Static)
        no_msg.display = False

    def has_running_pipelines(self) -> bool:
        """Check if any displayed pipeline is in a running/pending state."""
        running_states = {"running", "pending", "created", "waiting_for_resource", "preparing"}
        return any(p.status in running_states for p in self._pipeline_data)

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key and event.row_key.value is not None:
            try:
                pipeline_id = int(event.row_key.value)
                self.post_message(PipelineSelected(pipeline_id))
            except (ValueError, TypeError):
                pass


def _format_duration(seconds: float | None) -> str:
    """Format duration in seconds to a human-readable string."""
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


class JobStagePanel(Widget):
    """Panel showing jobs grouped by stage for a selected pipeline."""

    DEFAULT_CSS = """
    JobStagePanel {
        height: 1fr;
        width: 1fr;
        layout: vertical;
    }

    JobStagePanel #job-stage-scroll {
        height: 1fr;
    }

    JobStagePanel #no-jobs-msg {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }

    JobStagePanel .stage-header {
        text-style: bold;
        padding: 1 0 0 1;
        color: $text;
    }

    JobStagePanel .job-entry {
        padding: 0 0 0 3;
    }

    JobStagePanel .job-entry-manual {
        padding: 0 0 0 3;
        color: darkorange;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._jobs: list[Job] = []
        self._selected_pipeline_id: int | None = None

    def compose(self) -> ComposeResult:
        yield Static("[bold]Jobs by Stage[/bold]", id="job-stage-title")
        yield Static("[dim]Select a pipeline to view jobs.[/dim]", id="no-jobs-msg")
        yield VerticalScroll(id="job-stage-scroll")

    def on_mount(self) -> None:
        scroll = self.query_one("#job-stage-scroll", VerticalScroll)
        scroll.display = False

    def populate(self, jobs: list[Job], pipeline_id: int | None = None) -> None:
        """Populate jobs grouped by stage."""
        self._jobs = jobs
        self._selected_pipeline_id = pipeline_id

        no_msg = self.query_one("#no-jobs-msg", Static)
        scroll = self.query_one("#job-stage-scroll", VerticalScroll)

        scroll.remove_children()

        if not jobs:
            no_msg.update("[dim]No jobs found for this pipeline.[/dim]")
            no_msg.display = True
            scroll.display = False
            return

        no_msg.display = False
        scroll.display = True

        stages: dict[str, list[Job]] = {}
        for job in jobs:
            stages.setdefault(job.stage, []).append(job)

        for stage_name, stage_jobs in stages.items():
            scroll.mount(Static(f"[bold]{stage_name}[/bold]", classes="stage-header"))
            for job in stage_jobs:
                icon = f"[{status_color(job.status)}]{job.status.upper()}[/]"
                duration_str = _format_duration(job.duration)
                manual_tag = " [dark_orange](manual)[/]" if job.status == "manual" else ""
                failure_tag = f" [red]({job.failure_reason})[/]" if job.failure_reason else ""
                css_class = "job-entry-manual" if job.status == "manual" else "job-entry"
                scroll.mount(
                    Static(
                        f"  {icon}  {job.name}  {duration_str}{manual_tag}{failure_tag}",
                        classes=css_class,
                    )
                )

    def get_job_by_name(self, name: str) -> Job | None:
        """Find a job by name in the current job list."""
        for job in self._jobs:
            if job.name == name:
                return job
        return None


class JobLogViewer(VerticalScroll):
    """Scrollable viewer for job log output."""

    DEFAULT_CSS = """
    JobLogViewer {
        height: 1fr;
        width: 1fr;
        border: solid $primary;
        padding: 1;
        background: $surface;
    }

    JobLogViewer .log-line {
        height: auto;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._log_content: str = ""
        self._job_id: int | None = None

    def compose(self) -> ComposeResult:
        yield Static("[dim]Select a job to view its log.[/dim]", classes="log-placeholder")

    def set_log(self, content: str, job_id: int | None = None) -> None:
        """Set the log content to display."""
        self._log_content = content
        self._job_id = job_id
        self.remove_children()

        if not content.strip():
            self.mount(Static("[dim]Log is empty.[/dim]", classes="log-placeholder"))
            return

        self.mount(Static(content, classes="log-line"))
        self.scroll_end(animate=False)

    def append_log(self, content: str) -> None:
        """Append content to the existing log."""
        self._log_content += content
        self.remove_children()
        self.mount(Static(self._log_content, classes="log-line"))
        self.scroll_end(animate=False)

    def clear_log(self) -> None:
        """Clear the log viewer."""
        self._log_content = ""
        self._job_id = None
        self.remove_children()
        self.mount(Static("[dim]Select a job to view its log.[/dim]", classes="log-placeholder"))


class PipelineActionBar(Widget):
    """Action buttons for pipeline operations: retry, cancel, trigger."""

    DEFAULT_CSS = """
    PipelineActionBar {
        height: auto;
        padding: 1;
        dock: bottom;
        layout: horizontal;
        background: $surface;
        border-top: solid $primary;
    }

    PipelineActionBar Button {
        margin-right: 1;
    }

    PipelineActionBar #pipeline-info-label {
        width: 1fr;
        content-align: left middle;
        height: 3;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        pipeline_id: int | None = None,
        pipeline_status: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._pipeline_id = pipeline_id
        self._pipeline_status = pipeline_status

    def compose(self) -> ComposeResult:
        if self._pipeline_id is not None:
            if self._pipeline_status in ("failed", "canceled"):
                yield Button("Retry", variant="warning", classes="btn-retry")
            if self._pipeline_status in ("running", "pending", "created"):
                yield Button("Cancel", variant="error", classes="btn-cancel")
        yield Button("Trigger New", variant="success", classes="btn-trigger")
        info = f"Pipeline #{self._pipeline_id}" if self._pipeline_id else "No pipeline selected"
        yield Label(info, classes="pipeline-info-label")

    def update_pipeline(self, pipeline_id: int | None, status: str = "") -> None:
        """Update the action bar for a different pipeline."""
        self._pipeline_id = pipeline_id
        self._pipeline_status = status
        self.remove_children()
        if pipeline_id is not None:
            if status in ("failed", "canceled"):
                self.mount(Button("Retry", variant="warning", classes="btn-retry"))
            if status in ("running", "pending", "created"):
                self.mount(Button("Cancel", variant="error", classes="btn-cancel"))
        self.mount(Button("Trigger New", variant="success", classes="btn-trigger"))
        info = f"Pipeline #{pipeline_id}" if pipeline_id else "No pipeline selected"
        self.mount(Label(info, classes="pipeline-info-label"))

    @on(Button.Pressed, ".btn-retry")
    def _on_retry(self, event: Button.Pressed) -> None:
        if self._pipeline_id is not None:
            self.post_message(PipelineActionRequested("retry", self._pipeline_id))

    @on(Button.Pressed, ".btn-cancel")
    def _on_cancel(self, event: Button.Pressed) -> None:
        if self._pipeline_id is not None:
            self.post_message(PipelineActionRequested("cancel", self._pipeline_id))

    @on(Button.Pressed, ".btn-trigger")
    def _on_trigger(self, event: Button.Pressed) -> None:
        self.post_message(PipelineActionRequested("trigger", self._pipeline_id or 0))


class CIStatusScreen(Widget):
    """CI/CD pipeline status screen.

    Shows a pipeline list with status/ref/duration, job breakdown by stage
    with status badges, a job log viewer, and action buttons for retry/cancel/trigger.
    Supports auto-refresh for running pipelines.

    Keyboard navigation:
    - r: Refresh pipeline list
    - Enter: Select pipeline to view jobs
    - Escape: Go back (if in detail view)
    - l: View log for selected job
    """

    DEFAULT_CSS = """
    CIStatusScreen {
        height: 1fr;
        width: 1fr;
        layout: vertical;
    }

    CIStatusScreen #ci-main-panels {
        height: 1fr;
    }

    CIStatusScreen #ci-left-panel {
        width: 1fr;
    }

    CIStatusScreen #ci-right-panel {
        width: 1fr;
    }

    CIStatusScreen #ci-header-bar {
        height: auto;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("enter", "select_pipeline", "Select", show=True),
        Binding("escape", "go_back", "Back", show=True),
        Binding("l", "view_log", "View Log", show=True),
    ]

    def __init__(
        self,
        config: Any,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._config = config
        self._selected_pipeline_id: int | None = None
        self._selected_pipeline_status: str = ""
        self._auto_refresh_timer: object | None = None
        self._pipelines: list[Pipeline] = []
        self._jobs: list[Job] = []

    def compose(self) -> ComposeResult:
        yield Static("[bold]CI/CD Pipelines[/bold]", id="ci-header-bar")
        with Horizontal(id="ci-main-panels"):
            with TabPane("Pipelines", id="ci-left-panel"):
                yield PipelineListPanel(id="pipeline-list-panel")
            with TabPane("Details", id="ci-right-panel"), TabbedContent(id="ci-detail-tabs"):
                    with TabPane("Jobs", id="tab-jobs"):
                        yield JobStagePanel(id="job-stage-panel")
                    with TabPane("Log", id="tab-log"):
                        yield JobLogViewer(id="job-log-viewer")
        yield PipelineActionBar(id="pipeline-action-bar")

    def on_mount(self) -> None:
        """Start initial data load."""
        self._trigger_load()

    def _trigger_load(self) -> None:
        """Start loading pipeline data."""
        panel = self.query_one("#pipeline-list-panel", PipelineListPanel)
        panel.show_loading()
        self._load_pipelines()

    @work(exclusive=True, name="load_pipelines")
    async def _load_pipelines(self) -> None:
        """Load pipeline data. Stub for service integration."""
        panel = self.query_one("#pipeline-list-panel", PipelineListPanel)
        loading = panel.query_one("#pipeline-loading", LoadingIndicator)
        loading.display = False

    def set_pipelines(self, pipelines: list[Pipeline]) -> None:
        """Set pipeline data and update the display.

        Called by the app after fetching pipeline data from CIService.

        Args:
            pipelines: List of Pipeline models to display.
        """
        self._pipelines = pipelines
        panel = self.query_one("#pipeline-list-panel", PipelineListPanel)
        panel.populate(pipelines)
        self._manage_auto_refresh()

    def set_jobs(self, jobs: list[Job], pipeline_id: int | None = None) -> None:
        """Set job data for the selected pipeline.

        Args:
            jobs: List of Job models to display.
            pipeline_id: The pipeline ID these jobs belong to.
        """
        self._jobs = jobs
        stage_panel = self.query_one("#job-stage-panel", JobStagePanel)
        stage_panel.populate(jobs, pipeline_id)

    def set_job_log(self, content: str, job_id: int | None = None) -> None:
        """Set job log content in the log viewer.

        Args:
            content: The log text to display.
            job_id: The job ID the log belongs to.
        """
        viewer = self.query_one("#job-log-viewer", JobLogViewer)
        viewer.set_log(content, job_id)

    def _manage_auto_refresh(self) -> None:
        """Start or stop auto-refresh based on pipeline states."""
        panel = self.query_one("#pipeline-list-panel", PipelineListPanel)
        if panel.has_running_pipelines():
            self._start_auto_refresh()
        else:
            self._stop_auto_refresh()

    def _start_auto_refresh(self) -> None:
        """Start the auto-refresh timer."""
        if self._auto_refresh_timer is None:
            self._auto_refresh_timer = self.set_interval(
                AUTO_REFRESH_INTERVAL, self._on_auto_refresh
            )

    def _stop_auto_refresh(self) -> None:
        """Stop the auto-refresh timer."""
        if self._auto_refresh_timer is not None:
            self._auto_refresh_timer.stop()  # type: ignore[union-attr]
            self._auto_refresh_timer = None

    def _on_auto_refresh(self) -> None:
        """Callback for auto-refresh timer."""
        self._trigger_load()

    @on(PipelineSelected)
    def _on_pipeline_selected(self, event: PipelineSelected) -> None:
        """Handle pipeline selection from the list."""
        self._selected_pipeline_id = event.pipeline_id
        for pipeline in self._pipelines:
            if pipeline.id == event.pipeline_id:
                self._selected_pipeline_status = pipeline.status
                break
        action_bar = self.query_one("#pipeline-action-bar", PipelineActionBar)
        action_bar.update_pipeline(event.pipeline_id, self._selected_pipeline_status)

    # -- Actions --------------------------------------------------------------

    def action_refresh(self) -> None:
        """Refresh the pipeline list."""
        self._trigger_load()

    def action_select_pipeline(self) -> None:
        """Select the currently highlighted pipeline."""
        panel = self.query_one("#pipeline-list-panel", PipelineListPanel)
        table = panel.query_one("#pipeline-table", DataTable)
        if table.cursor_row is not None:
            table.action_select_cursor()

    def action_go_back(self) -> None:
        """Clear the job/log detail view."""
        stage_panel = self.query_one("#job-stage-panel", JobStagePanel)
        stage_panel.populate([])
        viewer = self.query_one("#job-log-viewer", JobLogViewer)
        viewer.clear_log()
        self._selected_pipeline_id = None
        action_bar = self.query_one("#pipeline-action-bar", PipelineActionBar)
        action_bar.update_pipeline(None)

    def action_view_log(self) -> None:
        """Placeholder for viewing the selected job's log."""
        pass

    def on_unmount(self) -> None:
        """Clean up the auto-refresh timer."""
        self._stop_auto_refresh()
