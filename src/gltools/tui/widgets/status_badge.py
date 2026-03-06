"""Status badge widget with semantic colors for GitLab statuses."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static

# Semantic color mapping for GitLab statuses
STATUS_STYLES: dict[str, tuple[str, str]] = {
    # MR states
    "opened": ("bold white on dark_green", "OPEN"),
    "merged": ("bold white on blue", "MERGED"),
    "closed": ("bold white on red", "CLOSED"),
    "locked": ("bold white on dark_orange", "LOCKED"),
    # Pipeline statuses
    "success": ("bold white on green", "PASSED"),
    "passed": ("bold white on green", "PASSED"),
    "failed": ("bold white on red", "FAILED"),
    "running": ("bold black on yellow", "RUNNING"),
    "pending": ("bold black on yellow", "PENDING"),
    "canceled": ("bold white on grey50", "CANCELED"),
    "skipped": ("dim", "SKIPPED"),
    "created": ("bold black on cyan", "CREATED"),
    "waiting_for_resource": ("bold black on yellow", "WAITING"),
    "preparing": ("bold black on yellow", "PREPARING"),
    "manual": ("bold white on dark_orange", "MANUAL"),
    "scheduled": ("bold black on cyan", "SCHEDULED"),
    # Approval
    "approved": ("bold white on green", "APPROVED"),
    "unapproved": ("bold white on dark_orange", "UNAPPROVED"),
}


class StatusBadge(Static):
    """A colored badge displaying a GitLab status.

    Renders the status as a short label with semantic background color.
    """

    DEFAULT_CSS = """
    StatusBadge {
        width: auto;
        height: 1;
        padding: 0 1;
        min-width: 8;
        text-align: center;
    }
    """

    status: reactive[str] = reactive("", layout=True)

    def __init__(
        self,
        status: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.status = status

    def watch_status(self, new_status: str) -> None:
        """Update the badge display when status changes."""
        self._refresh_display(new_status)

    def _refresh_display(self, status: str) -> None:
        """Render the badge with the appropriate style."""
        key = status.lower().strip()
        style, label = STATUS_STYLES.get(key, ("bold", status.upper()))
        self.update(f"[{style}] {label} [/]")

    def on_mount(self) -> None:
        """Render on mount."""
        self._refresh_display(self.status)


class PipelineStatusBadge(StatusBadge):
    """Specialized badge for pipeline statuses."""

    DEFAULT_CSS = """
    PipelineStatusBadge {
        width: auto;
        height: 1;
        padding: 0 1;
    }
    """


def status_color(status: str) -> str:
    """Return the Rich color name for a given status.

    Useful for inline text coloring outside of the badge widget.
    """
    color_map: dict[str, str] = {
        "opened": "green",
        "merged": "blue",
        "closed": "red",
        "success": "green",
        "passed": "green",
        "failed": "red",
        "running": "yellow",
        "pending": "yellow",
        "canceled": "grey50",
        "skipped": "dim",
        "created": "cyan",
        "manual": "dark_orange",
    }
    return color_map.get(status.lower().strip(), "white")
