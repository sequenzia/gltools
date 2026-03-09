"""Issue detail TUI screen with description, comments, and action buttons."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, LoadingIndicator, Markdown, Static, TabbedContent, TabPane

from gltools.tui.widgets.status_badge import StatusBadge, status_color

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from gltools.models import Issue, Note


class IssueDetailClosed(Message):
    """Message posted when the detail view is closed (go back to list)."""


class IssueActionRequested(Message):
    """Message posted when an issue action button is pressed."""

    def __init__(self, action: str, issue_iid: int, payload: dict[str, Any] | None = None) -> None:
        super().__init__()
        self.action = action
        self.issue_iid = issue_iid
        self.payload = payload or {}


class IssueHeader(Widget):
    """Header section showing issue title, IID, status badge, and metadata."""

    DEFAULT_CSS = """
    IssueHeader {
        height: auto;
        padding: 1 2;
        background: $surface;
        border-bottom: solid $primary;
    }

    IssueHeader #issue-title-row {
        height: auto;
        layout: horizontal;
    }

    IssueHeader #issue-title-text {
        width: 1fr;
    }

    IssueHeader #issue-meta {
        height: auto;
        padding-top: 1;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        issue: Issue | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._issue = issue

    def compose(self) -> ComposeResult:
        if self._issue is None:
            yield Static("[dim]Loading...[/dim]")
            return

        issue = self._issue
        with Horizontal(id="issue-title-row"):
            title_prefix = ""
            if getattr(issue, "confidential", False):
                title_prefix = "[bold red]CONFIDENTIAL[/] "
            yield Static(
                f"{title_prefix}[bold]#{issue.iid}[/bold]  {issue.title}",
                id="issue-title-text",
            )
            yield StatusBadge(issue.state, id="issue-state-badge")

        meta_parts = [
            f"[bold]Author:[/bold] {issue.author.name} (@{issue.author.username})",
            f"[bold]Updated:[/bold] {str(issue.updated_at)[:16]}",
        ]
        if issue.labels:
            meta_parts.append(f"[bold]Labels:[/bold] {', '.join(issue.labels)}")
        if issue.assignee:
            meta_parts.append(f"[bold]Assignee:[/bold] {issue.assignee.name}")
        if issue.milestone:
            meta_parts.append(f"[bold]Milestone:[/bold] {issue.milestone.title}")

        yield Static("\n".join(meta_parts), id="issue-meta")

    def update_issue(self, issue: Issue) -> None:
        """Update the header with new issue data."""
        self._issue = issue
        self.remove_children()
        if self._issue:
            header_row = Horizontal(id="issue-title-row")
            self.mount(header_row)
            title_prefix = ""
            if getattr(issue, "confidential", False):
                title_prefix = "[bold red]CONFIDENTIAL[/] "
            header_row.mount(Static(f"{title_prefix}[bold]#{issue.iid}[/bold]  {issue.title}", id="issue-title-text"))
            header_row.mount(StatusBadge(issue.state, id="issue-state-badge"))

            meta_parts = [
                f"[bold]Author:[/bold] {issue.author.name} (@{issue.author.username})",
                f"[bold]Updated:[/bold] {str(issue.updated_at)[:16]}",
            ]
            if issue.labels:
                meta_parts.append(f"[bold]Labels:[/bold] {', '.join(issue.labels)}")
            if issue.assignee:
                meta_parts.append(f"[bold]Assignee:[/bold] {issue.assignee.name}")
            if issue.milestone:
                meta_parts.append(f"[bold]Milestone:[/bold] {issue.milestone.title}")

            self.mount(Static("\n".join(meta_parts), id="issue-meta"))


class IssueCommentList(VerticalScroll):
    """Scrollable list of issue comments/notes."""

    DEFAULT_CSS = """
    IssueCommentList {
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


class IssueActionBar(Widget):
    """Action buttons for issue operations: close/reopen, comment."""

    DEFAULT_CSS = """
    IssueActionBar {
        height: auto;
        padding: 1;
        dock: bottom;
        layout: horizontal;
        background: $surface;
        border-top: solid $primary;
    }

    IssueActionBar Button {
        margin-right: 1;
    }

    IssueActionBar #comment-input {
        width: 1fr;
    }
    """

    def __init__(
        self,
        issue_iid: int = 0,
        issue_state: str = "opened",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._issue_iid = issue_iid
        self._issue_state = issue_state

    def compose(self) -> ComposeResult:
        if self._issue_state == "opened":
            yield Button("Close", variant="error", id="btn-close")
        else:
            yield Button("Reopen", variant="success", id="btn-reopen")
        yield Input(placeholder="Add a comment...", id="comment-input")
        yield Button("Comment", variant="default", id="btn-comment")

    @on(Button.Pressed, "#btn-close")
    def _on_close(self, event: Button.Pressed) -> None:
        self.post_message(IssueActionRequested("close", self._issue_iid))

    @on(Button.Pressed, "#btn-reopen")
    def _on_reopen(self, event: Button.Pressed) -> None:
        self.post_message(IssueActionRequested("reopen", self._issue_iid))

    @on(Button.Pressed, "#btn-comment")
    def _on_comment(self, event: Button.Pressed) -> None:
        comment_input = self.query_one("#comment-input", Input)
        body = comment_input.value.strip()
        if body:
            self.post_message(IssueActionRequested("comment", self._issue_iid, {"body": body}))
            comment_input.value = ""

    @on(Input.Submitted, "#comment-input")
    def _on_comment_submitted(self, event: Input.Submitted) -> None:
        body = event.value.strip()
        if body:
            self.post_message(IssueActionRequested("comment", self._issue_iid, {"body": body}))
            event.input.value = ""


class IssueDetailScreen(Widget):
    """Full issue detail view.

    Shows the issue header, tabbed content with description and comments,
    and action buttons for close/reopen/comment operations.

    Keyboard navigation:
    - Escape/Backspace: return to issue list
    - Tab switching: 1=Description, 2=Comments, 3=Linked MRs
    """

    DEFAULT_CSS = """
    IssueDetailScreen {
        height: 1fr;
        width: 1fr;
        layout: vertical;
    }

    IssueDetailScreen #issue-detail-loading {
        height: 1fr;
        content-align: center middle;
    }

    IssueDetailScreen #description-content {
        height: 1fr;
        padding: 1 2;
    }

    IssueDetailScreen .comment-entry {
        margin-bottom: 1;
        padding: 1;
        border: solid $surface-lighten-2;
    }

    IssueDetailScreen #linked-mrs-content {
        height: 1fr;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("backspace", "go_back", "Back", show=False),
    ]

    def __init__(
        self,
        issue_iid: int,
        config: Any,
        *,
        issue: Issue | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._issue_iid = issue_iid
        self._config = config
        self._issue = issue
        self._notes: list[Note] = []
        self._linked_mrs: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield IssueHeader(self._issue, id="issue-header")
        yield LoadingIndicator(id="issue-detail-loading")

        with TabbedContent(id="issue-tabs"):
            with TabPane("Description", id="tab-description"):
                yield VerticalScroll(
                    Markdown(
                        "*Loading...*" if self._issue is None else (self._issue.description or "*No description*")
                    ),
                    id="description-content",
                )
            with TabPane("Comments", id="tab-comments"):
                yield IssueCommentList(id="comment-list")
            with TabPane("Linked MRs", id="tab-linked-mrs"):
                yield VerticalScroll(
                    Static("[dim]No linked merge requests.[/dim]"),
                    id="linked-mrs-content",
                )

        if self._issue:
            yield IssueActionBar(self._issue_iid, self._issue.state, id="action-bar")
        else:
            yield IssueActionBar(self._issue_iid, "opened", id="action-bar")

    def on_mount(self) -> None:
        """Initialize the detail view."""
        loading = self.query_one("#issue-detail-loading", LoadingIndicator)
        if self._issue is not None:
            loading.display = False
        else:
            loading.display = True

    def set_issue(self, issue: Issue) -> None:
        """Set the issue data and update the display.

        Called by the app after fetching issue details from the service layer.
        """
        self._issue = issue
        self._issue_iid = issue.iid

        # Update header
        header = self.query_one("#issue-header", IssueHeader)
        header.update_issue(issue)

        # Update description
        desc_scroll = self.query_one("#description-content", VerticalScroll)
        desc_scroll.remove_children()
        desc_scroll.mount(Markdown(issue.description or "*No description*"))

        # Hide loading
        loading = self.query_one("#issue-detail-loading", LoadingIndicator)
        loading.display = False

    def set_notes(self, notes: list[Note]) -> None:
        """Set comment data for the comments tab.

        Args:
            notes: List of Note models from the API.
        """
        self._notes = notes
        comment_list = self.query_one("#comment-list", IssueCommentList)
        comment_list.update_notes(notes)

    def set_linked_mrs(self, mrs: list[dict[str, Any]]) -> None:
        """Set linked merge requests for the linked MRs tab.

        Args:
            mrs: List of dicts with MR info (iid, title, state, web_url).
        """
        self._linked_mrs = mrs
        container = self.query_one("#linked-mrs-content", VerticalScroll)
        container.remove_children()

        if not mrs:
            container.mount(Static("[dim]No linked merge requests.[/dim]"))
            return

        for mr in mrs:
            iid = mr.get("iid", "?")
            title = mr.get("title", "Untitled")
            state = mr.get("state", "unknown")
            state_colored = f"[{status_color(state)}]{state}[/]"
            container.mount(Static(f"  !{iid}  {title}  {state_colored}", classes="linked-mr-entry"))

    def action_go_back(self) -> None:
        """Return to the issue list."""
        self.post_message(IssueDetailClosed())
