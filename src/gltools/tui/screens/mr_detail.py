"""MR detail TUI screen with description, diff viewer, comments, and action buttons."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, LoadingIndicator, Markdown, Static, TabbedContent, TabPane

from gltools.tui.widgets.diff_viewer import DiffViewer
from gltools.tui.widgets.status_badge import StatusBadge

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from gltools.models import DiffFile, MergeRequest, Note


class MRDetailClosed(Message):
    """Message posted when the detail view is closed (go back to list)."""


class MRActionRequested(Message):
    """Message posted when an MR action button is pressed."""

    def __init__(self, action: str, mr_iid: int, payload: dict[str, Any] | None = None) -> None:
        super().__init__()
        self.action = action
        self.mr_iid = mr_iid
        self.payload = payload or {}


class MRHeader(Widget):
    """Header section showing MR title, IID, branches, and status badge."""

    DEFAULT_CSS = """
    MRHeader {
        height: auto;
        padding: 1 2;
        background: $surface;
        border-bottom: solid $primary;
    }

    MRHeader #mr-title-row {
        height: auto;
        layout: horizontal;
    }

    MRHeader #mr-title-text {
        width: 1fr;
    }

    MRHeader #mr-meta {
        height: auto;
        padding-top: 1;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        mr: MergeRequest | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._mr = mr

    def compose(self) -> ComposeResult:
        if self._mr is None:
            yield Static("[dim]Loading...[/dim]")
            return

        mr = self._mr
        with Horizontal(id="mr-title-row"):
            yield Static(
                f"[bold]!{mr.iid}[/bold]  {mr.title}",
                id="mr-title-text",
            )
            yield StatusBadge(mr.state, id="mr-state-badge")
            if mr.pipeline:
                yield StatusBadge(mr.pipeline.status, id="mr-pipeline-badge")

        meta_parts = [
            f"[bold]Author:[/bold] {mr.author.name} (@{mr.author.username})",
            f"[bold]Branch:[/bold] {mr.source_branch} -> {mr.target_branch}",
            f"[bold]Updated:[/bold] {str(mr.updated_at)[:16]}",
        ]
        if mr.labels:
            meta_parts.append(f"[bold]Labels:[/bold] {', '.join(mr.labels)}")
        if mr.assignee:
            meta_parts.append(f"[bold]Assignee:[/bold] {mr.assignee.name}")

        yield Static("\n".join(meta_parts), id="mr-meta")

    def update_mr(self, mr: MergeRequest) -> None:
        """Update the header with new MR data."""
        self._mr = mr
        self.remove_children()
        # Re-compose
        if self._mr:
            header_row = Horizontal(id="mr-title-row")
            self.mount(header_row)
            header_row.mount(
                Static(f"[bold]!{mr.iid}[/bold]  {mr.title}", id="mr-title-text")
            )
            header_row.mount(StatusBadge(mr.state, id="mr-state-badge"))
            if mr.pipeline:
                header_row.mount(StatusBadge(mr.pipeline.status, id="mr-pipeline-badge"))

            meta_parts = [
                f"[bold]Author:[/bold] {mr.author.name} (@{mr.author.username})",
                f"[bold]Branch:[/bold] {mr.source_branch} -> {mr.target_branch}",
                f"[bold]Updated:[/bold] {str(mr.updated_at)[:16]}",
            ]
            if mr.labels:
                meta_parts.append(f"[bold]Labels:[/bold] {', '.join(mr.labels)}")
            if mr.assignee:
                meta_parts.append(f"[bold]Assignee:[/bold] {mr.assignee.name}")

            self.mount(Static("\n".join(meta_parts), id="mr-meta"))


class CommentList(VerticalScroll):
    """Scrollable list of MR comments/notes."""

    DEFAULT_CSS = """
    CommentList {
        height: 1fr;
        width: 1fr;
        border: solid $primary;
        padding: 1;
    }
    """

    def __init__(
        self,
        notes: list[Note] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._notes: list[Note] = notes or []

    def compose(self) -> ComposeResult:
        if not self._notes:
            yield Static("[dim]No comments yet.[/dim]", id="no-comments")
            return

        for note in self._notes:
            system_tag = " [dim](system)[/dim]" if note.system else ""
            yield Static(
                f"[bold]{note.author.name}[/bold] (@{note.author.username}){system_tag}  "
                f"[dim]{str(note.created_at)[:16]}[/dim]\n{note.body}\n",
                classes="comment-entry",
            )

    def update_notes(self, notes: list[Note]) -> None:
        """Replace displayed comments with new data."""
        self._notes = notes
        self.remove_children()
        if not notes:
            self.mount(Static("[dim]No comments yet.[/dim]", id="no-comments"))
            return

        for note in notes:
            system_tag = " [dim](system)[/dim]" if note.system else ""
            self.mount(
                Static(
                    f"[bold]{note.author.name}[/bold] (@{note.author.username}){system_tag}  "
                    f"[dim]{str(note.created_at)[:16]}[/dim]\n{note.body}\n",
                    classes="comment-entry",
                )
            )


class ActionBar(Widget):
    """Action buttons for MR operations: approve, merge, comment."""

    DEFAULT_CSS = """
    ActionBar {
        height: auto;
        padding: 1;
        dock: bottom;
        layout: horizontal;
        background: $surface;
        border-top: solid $primary;
    }

    ActionBar Button {
        margin-right: 1;
    }

    ActionBar #comment-input {
        width: 1fr;
    }
    """

    def __init__(
        self,
        mr_iid: int = 0,
        mr_state: str = "opened",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._mr_iid = mr_iid
        self._mr_state = mr_state

    def compose(self) -> ComposeResult:
        if self._mr_state == "opened":
            yield Button("Approve", variant="success", id="btn-approve")
            yield Button("Merge", variant="primary", id="btn-merge")
        yield Input(placeholder="Add a comment...", id="comment-input")
        yield Button("Comment", variant="default", id="btn-comment")

    @on(Button.Pressed, "#btn-approve")
    def _on_approve(self, event: Button.Pressed) -> None:
        self.post_message(MRActionRequested("approve", self._mr_iid))

    @on(Button.Pressed, "#btn-merge")
    def _on_merge(self, event: Button.Pressed) -> None:
        self.post_message(MRActionRequested("merge", self._mr_iid))

    @on(Button.Pressed, "#btn-comment")
    def _on_comment(self, event: Button.Pressed) -> None:
        comment_input = self.query_one("#comment-input", Input)
        body = comment_input.value.strip()
        if body:
            self.post_message(MRActionRequested("comment", self._mr_iid, {"body": body}))
            comment_input.value = ""

    @on(Input.Submitted, "#comment-input")
    def _on_comment_submitted(self, event: Input.Submitted) -> None:
        body = event.value.strip()
        if body:
            self.post_message(MRActionRequested("comment", self._mr_iid, {"body": body}))
            event.input.value = ""


class MRDetailScreen(Widget):
    """Full merge request detail view.

    Shows the MR header, tabbed content with description/diff/comments,
    and action buttons for approve/merge/comment operations.

    Keyboard navigation:
    - Escape/Backspace: return to MR list
    - Tab switching: 1=Description, 2=Diff, 3=Comments
    """

    DEFAULT_CSS = """
    MRDetailScreen {
        height: 1fr;
        width: 1fr;
        layout: vertical;
    }

    MRDetailScreen #mr-detail-loading {
        height: 1fr;
        content-align: center middle;
    }

    MRDetailScreen #description-content {
        height: 1fr;
        padding: 1 2;
    }

    MRDetailScreen .comment-entry {
        margin-bottom: 1;
        padding: 1;
        border: solid $surface-lighten-2;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("backspace", "go_back", "Back", show=False),
    ]

    def __init__(
        self,
        mr_iid: int,
        config: Any,
        *,
        mr: MergeRequest | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._mr_iid = mr_iid
        self._config = config
        self._mr = mr
        self._diff_files: list[DiffFile] = []
        self._notes: list[Note] = []

    def compose(self) -> ComposeResult:
        yield MRHeader(self._mr, id="mr-header")
        yield LoadingIndicator(id="mr-detail-loading")

        with TabbedContent(id="mr-tabs"):
            with TabPane("Description", id="tab-description"):
                yield VerticalScroll(
                    Markdown("*Loading...*" if self._mr is None else (self._mr.description or "*No description*")),
                    id="description-content",
                )
            with TabPane("Diff", id="tab-diff"):
                yield DiffViewer(id="diff-viewer")
            with TabPane("Comments", id="tab-comments"):
                yield CommentList(id="comment-list")

        if self._mr:
            yield ActionBar(self._mr_iid, self._mr.state, id="action-bar")
        else:
            yield ActionBar(self._mr_iid, "opened", id="action-bar")

    def on_mount(self) -> None:
        """Initialize the detail view."""
        loading = self.query_one("#mr-detail-loading", LoadingIndicator)
        if self._mr is not None:
            loading.display = False
        else:
            loading.display = True

    def set_mr(self, mr: MergeRequest) -> None:
        """Set the MR data and update the display.

        Called by the app after fetching MR details from the service layer.
        """
        self._mr = mr
        self._mr_iid = mr.iid

        # Update header
        header = self.query_one("#mr-header", MRHeader)
        header.update_mr(mr)

        # Update description
        desc_scroll = self.query_one("#description-content", VerticalScroll)
        desc_scroll.remove_children()
        desc_scroll.mount(Markdown(mr.description or "*No description*"))

        # Hide loading
        loading = self.query_one("#mr-detail-loading", LoadingIndicator)
        loading.display = False

    def set_diff(self, diff_files: list[DiffFile]) -> None:
        """Set diff data for the diff tab.

        Args:
            diff_files: List of DiffFile models from the API.
        """
        self._diff_files = diff_files
        viewer = self.query_one("#diff-viewer", DiffViewer)
        viewer.update_diffs(diff_files)

    def set_notes(self, notes: list[Note]) -> None:
        """Set comment data for the comments tab.

        Args:
            notes: List of Note models from the API.
        """
        self._notes = notes
        comment_list = self.query_one("#comment-list", CommentList)
        comment_list.update_notes(notes)

    def action_go_back(self) -> None:
        """Return to the MR list."""
        self.post_message(MRDetailClosed())
