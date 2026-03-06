"""Issue list TUI screen with DataTable, filtering, sorting, and pagination."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import on, work
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label, LoadingIndicator, Select, Static

from gltools.tui.widgets.status_badge import status_color

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from gltools.models import Issue


# Sort key options for Issue list
SORT_OPTIONS: list[tuple[str, str]] = [
    ("Updated (newest)", "updated_desc"),
    ("Updated (oldest)", "updated_asc"),
    ("Created (newest)", "created_desc"),
    ("Created (oldest)", "created_asc"),
    ("Title (A-Z)", "title_asc"),
    ("Title (Z-A)", "title_desc"),
]

# State filter options
STATE_OPTIONS: list[tuple[str, str]] = [
    ("All", "all"),
    ("Open", "opened"),
    ("Closed", "closed"),
]

# Page size
DEFAULT_PER_PAGE = 20


class IssueSelected(Message):
    """Message posted when an issue is selected from the list."""

    def __init__(self, issue_iid: int) -> None:
        super().__init__()
        self.issue_iid = issue_iid


class IssueFilterBar(Widget):
    """Filter controls for the issue list: state, author, labels, milestone, search."""

    DEFAULT_CSS = """
    IssueFilterBar {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
        layout: horizontal;
    }

    IssueFilterBar Select {
        width: 20;
        margin-right: 1;
    }

    IssueFilterBar Input {
        width: 1fr;
    }

    IssueFilterBar .filter-label {
        width: auto;
        padding: 0 1;
        content-align: center middle;
        height: 3;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("State:", classes="filter-label")
        yield Select(
            [(label, value) for label, value in STATE_OPTIONS],
            value="opened",
            id="state-filter",
            allow_blank=False,
        )
        yield Label("Author:", classes="filter-label")
        yield Input(placeholder="username", id="author-filter")
        yield Label("Labels:", classes="filter-label")
        yield Input(placeholder="comma-separated", id="labels-filter")
        yield Label("Milestone:", classes="filter-label")
        yield Input(placeholder="milestone", id="milestone-filter")
        yield Label("Search:", classes="filter-label")
        yield Input(placeholder="search title/description", id="search-filter")


class IssuePaginationBar(Widget):
    """Pagination controls showing current page and navigation."""

    DEFAULT_CSS = """
    IssuePaginationBar {
        height: 1;
        padding: 0 1;
        dock: bottom;
    }
    """

    page: reactive[int] = reactive(1)
    total_pages: reactive[int] = reactive(1)
    total_items: reactive[int] = reactive(0)

    def render(self) -> str:
        return f"Page {self.page}/{self.total_pages} ({self.total_items} total)  [dim][ <- prev ]  [ next -> ][/dim]"


class IssueListScreen(Widget):
    """Issue list screen with DataTable, filtering, sorting, and pagination.

    Displays issues in a DataTable with columns for IID, title, author, state,
    labels, and milestone. Supports filtering by state, author, labels, milestone,
    and text search. Keyboard-driven with Enter to view details.
    """

    DEFAULT_CSS = """
    IssueListScreen {
        height: 1fr;
        width: 1fr;
        layout: vertical;
    }

    IssueListScreen #issue-table {
        height: 1fr;
    }

    IssueListScreen #issue-loading {
        height: 1fr;
        content-align: center middle;
    }

    IssueListScreen #sort-bar {
        height: auto;
        padding: 0 1;
        layout: horizontal;
    }

    IssueListScreen #sort-bar Select {
        width: 25;
    }

    IssueListScreen #sort-bar .sort-label {
        width: auto;
        padding: 0 1;
        height: 3;
        content-align: center middle;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("enter", "select_issue", "View", show=True),
        Binding("n", "next_page", "Next Page", show=True),
        Binding("p", "prev_page", "Prev Page", show=True),
        Binding("/", "focus_search", "Search", show=True),
    ]

    # Current filter state
    _current_state: str = "opened"
    _current_author: str = ""
    _current_labels: str = ""
    _current_milestone: str = ""
    _current_search: str = ""
    _current_sort: str = "updated_desc"
    _current_page: int = 1
    _total_pages: int = 1
    _total_items: int = 0
    _issue_data: list[Issue] = []

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

    def compose(self) -> ComposeResult:
        yield Static("[bold]Issues[/bold]", id="issue-list-title")
        yield IssueFilterBar(id="filter-bar")
        with Horizontal(id="sort-bar"):
            yield Label("Sort:", classes="sort-label")
            yield Select(
                [(label, value) for label, value in SORT_OPTIONS],
                value="updated_desc",
                id="sort-select",
                allow_blank=False,
            )

        yield LoadingIndicator(id="issue-loading")
        table: DataTable[str] = DataTable(id="issue-table")
        table.cursor_type = "row"
        table.zebra_stripes = True
        yield table
        yield IssuePaginationBar(id="pagination-bar")

    def on_mount(self) -> None:
        """Set up the DataTable columns and trigger initial data load."""
        table = self.query_one("#issue-table", DataTable)
        table.add_column("IID", key="iid", width=6)
        table.add_column("Title", key="title")
        table.add_column("Author", key="author", width=15)
        table.add_column("State", key="state", width=10)
        table.add_column("Labels", key="labels", width=20)
        table.add_column("Milestone", key="milestone", width=15)
        table.add_column("Updated", key="updated", width=12)
        table.display = False
        self._trigger_load()

    def _trigger_load(self) -> None:
        """Start loading issue data (stub - actual loading via service layer)."""
        loading = self.query_one("#issue-loading", LoadingIndicator)
        loading.display = True
        table = self.query_one("#issue-table", DataTable)
        table.display = False
        self._load_data()

    @work(exclusive=True)
    async def _load_data(self) -> None:
        """Load issue data from the service layer.

        This is a stub that will be connected to the IssueService
        when the service integration is wired up. For now, it hides the
        loading indicator and shows the empty table.
        """
        loading = self.query_one("#issue-loading", LoadingIndicator)
        loading.display = False
        table = self.query_one("#issue-table", DataTable)
        table.display = True

    def populate_table(self, issues: list[Issue], total: int = 0, page: int = 1, total_pages: int = 1) -> None:
        """Populate the DataTable with issue data.

        Called by the app or service layer after fetching issue data.

        Args:
            issues: List of Issue models to display.
            total: Total number of issues matching the filter.
            page: Current page number.
            total_pages: Total number of pages.
        """
        self._issue_data = issues
        self._current_page = page
        self._total_pages = total_pages
        self._total_items = total

        table = self.query_one("#issue-table", DataTable)
        table.clear()

        for issue in issues:
            iid = str(issue.iid)
            title = issue.title[:60] + "..." if len(issue.title) > 60 else issue.title
            # Prepend confidential indicator if present
            if getattr(issue, "confidential", False):
                title = "[bold red]CONFIDENTIAL[/] " + title
            author = issue.author.username if issue.author else ""
            state = issue.state
            labels = ", ".join(issue.labels[:3])
            if len(issue.labels) > 3:
                labels += "..."
            milestone = issue.milestone or "-"
            updated = str(issue.updated_at)[:10]

            state_styled = f"[{status_color(state)}]{state}[/]"

            table.add_row(iid, title, author, state_styled, labels, milestone, updated, key=str(issue.iid))

        # Update pagination bar
        pagination = self.query_one("#pagination-bar", IssuePaginationBar)
        pagination.page = page
        pagination.total_pages = total_pages
        pagination.total_items = total

        # Show table, hide loading
        loading = self.query_one("#issue-loading", LoadingIndicator)
        loading.display = False
        table.display = True

    def get_filters(self) -> dict[str, Any]:
        """Return the current filter settings as a dict for API calls.

        Returns:
            Dictionary with state, author, labels, milestone, search, sort, page keys.
        """
        return {
            "state": self._current_state,
            "author": self._current_author or None,
            "labels": [lbl.strip() for lbl in self._current_labels.split(",") if lbl.strip()] or None,
            "milestone": self._current_milestone or None,
            "search": self._current_search or None,
            "sort": self._current_sort,
            "page": self._current_page,
            "per_page": DEFAULT_PER_PAGE,
        }

    # -- Event Handlers -------------------------------------------------------

    @on(Select.Changed, "#state-filter")
    def _on_state_changed(self, event: Select.Changed) -> None:
        self._current_state = str(event.value) if event.value is not None else "all"
        self._current_page = 1
        self._trigger_load()

    @on(Select.Changed, "#sort-select")
    def _on_sort_changed(self, event: Select.Changed) -> None:
        self._current_sort = str(event.value) if event.value is not None else "updated_desc"
        self._current_page = 1
        self._trigger_load()

    @on(Input.Submitted, "#author-filter")
    def _on_author_submitted(self, event: Input.Submitted) -> None:
        self._current_author = event.value.strip()
        self._current_page = 1
        self._trigger_load()

    @on(Input.Submitted, "#labels-filter")
    def _on_labels_submitted(self, event: Input.Submitted) -> None:
        self._current_labels = event.value.strip()
        self._current_page = 1
        self._trigger_load()

    @on(Input.Submitted, "#milestone-filter")
    def _on_milestone_submitted(self, event: Input.Submitted) -> None:
        self._current_milestone = event.value.strip()
        self._current_page = 1
        self._trigger_load()

    @on(Input.Submitted, "#search-filter")
    def _on_search_submitted(self, event: Input.Submitted) -> None:
        self._current_search = event.value.strip()
        self._current_page = 1
        self._trigger_load()

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key and event.row_key.value is not None:
            try:
                issue_iid = int(event.row_key.value)
                self.post_message(IssueSelected(issue_iid))
            except (ValueError, TypeError):
                pass

    # -- Actions --------------------------------------------------------------

    def action_refresh(self) -> None:
        """Refresh the issue list."""
        self._trigger_load()

    def action_select_issue(self) -> None:
        """Select the currently highlighted issue."""
        table = self.query_one("#issue-table", DataTable)
        if table.cursor_row is not None and self._issue_data:
            table.action_select_cursor()

    def action_next_page(self) -> None:
        """Go to the next page."""
        if self._current_page < self._total_pages:
            self._current_page += 1
            self._trigger_load()

    def action_prev_page(self) -> None:
        """Go to the previous page."""
        if self._current_page > 1:
            self._current_page -= 1
            self._trigger_load()

    def action_focus_search(self) -> None:
        """Focus the search input."""
        search = self.query_one("#search-filter", Input)
        search.focus()
