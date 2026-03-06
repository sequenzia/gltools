"""Diff viewer widget with syntax highlighting for merge request diffs."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from gltools.models import DiffFile

# Maximum diff lines to render at once before lazy loading kicks in
LAZY_LOAD_THRESHOLD = 500

# Map file extensions to Rich Syntax lexer names
_EXTENSION_LEXER_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".xml": "xml",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".sql": "sql",
    ".r": "r",
    ".swift": "swift",
    ".php": "php",
    ".lua": "lua",
    ".vim": "vim",
    ".dockerfile": "dockerfile",
    ".tf": "terraform",
}

# Special filenames mapped to lexers
_FILENAME_LEXER_MAP: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "Gemfile": "ruby",
    "Rakefile": "ruby",
    "Vagrantfile": "ruby",
    ".gitignore": "gitignore",
    ".env": "bash",
}


def _detect_lexer(file_path: str) -> str:
    """Detect the syntax lexer for a file based on its extension or name."""
    basename = os.path.basename(file_path)
    if basename in _FILENAME_LEXER_MAP:
        return _FILENAME_LEXER_MAP[basename]

    _, ext = os.path.splitext(file_path)
    return _EXTENSION_LEXER_MAP.get(ext.lower(), "text")


def _file_status_label(diff_file: DiffFile) -> str:
    """Return a human-readable label for the file change type."""
    if diff_file.new_file:
        return "[bold green]NEW[/bold green]"
    if diff_file.deleted_file:
        return "[bold red]DELETED[/bold red]"
    if diff_file.renamed_file:
        return f"[bold yellow]RENAMED[/bold yellow] {diff_file.old_path} -> {diff_file.new_path}"
    return "[bold blue]MODIFIED[/bold blue]"


def _classify_line(line: str) -> str:
    """Return the CSS class for a diff line based on its prefix."""
    if line.startswith("+") and not line.startswith("+++"):
        return "addition"
    if line.startswith("-") and not line.startswith("---"):
        return "deletion"
    if line.startswith("@@"):
        return "hunk-header"
    return ""


class DiffLine(Static):
    """A single line in a diff display with appropriate coloring."""

    DEFAULT_CSS = """
    DiffLine {
        height: 1;
        width: 1fr;
    }
    DiffLine.addition {
        background: $success 15%;
    }
    DiffLine.deletion {
        background: $error 15%;
    }
    DiffLine.hunk-header {
        background: $primary 15%;
        color: $text-muted;
    }
    """


class DiffFileHeader(Static):
    """Header widget for a single file in the diff viewer."""

    DEFAULT_CSS = """
    DiffFileHeader {
        height: auto;
        padding: 0 1;
        background: $surface;
        border-bottom: solid $primary;
        margin-top: 1;
    }
    """


class DiffFileViewer(Widget):
    """Displays the diff for a single file with syntax-aware coloring.

    Supports lazy loading for large diffs: initially renders up to
    LAZY_LOAD_THRESHOLD lines, with an expand button to load the rest.
    """

    DEFAULT_CSS = """
    DiffFileViewer {
        height: auto;
        width: 1fr;
        margin-bottom: 1;
    }
    """

    expanded: reactive[bool] = reactive(False)

    def __init__(
        self,
        diff_file: DiffFile,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._diff_file = diff_file
        self._all_lines = diff_file.diff.splitlines() if diff_file.diff else []
        self._is_large = len(self._all_lines) > LAZY_LOAD_THRESHOLD

    def compose(self) -> ComposeResult:
        file_path = self._diff_file.new_path or self._diff_file.old_path
        status = _file_status_label(self._diff_file)
        yield DiffFileHeader(f"{status}  [bold]{file_path}[/bold]")

        if self._is_large and not self.expanded:
            lines_to_show = self._all_lines[:LAZY_LOAD_THRESHOLD]
        else:
            lines_to_show = self._all_lines

        for line in lines_to_show:
            css_class = _classify_line(line)
            yield DiffLine(line, classes=css_class)

        if self._is_large and not self.expanded:
            remaining = len(self._all_lines) - LAZY_LOAD_THRESHOLD
            yield Static(
                f"[bold yellow]... {remaining} more lines. Press Enter to expand.[/bold yellow]",
                id="expand-hint",
                classes="expand-hint",
            )

    def on_click(self) -> None:
        """Expand the diff when clicked if truncated."""
        if self._is_large and not self.expanded:
            self.expanded = True
            self.remove_children()
            self._compose_children_again()

    def _compose_children_again(self) -> None:
        """Re-compose children after expanding."""
        file_path = self._diff_file.new_path or self._diff_file.old_path
        status = _file_status_label(self._diff_file)
        self.mount(DiffFileHeader(f"{status}  [bold]{file_path}[/bold]"))

        for line in self._all_lines:
            css_class = _classify_line(line)
            self.mount(DiffLine(line, classes=css_class))


class DiffViewer(VerticalScroll):
    """Scrollable viewer for multiple file diffs.

    Displays each file's diff with a header showing the file path,
    change type (new/modified/deleted/renamed), and syntax-highlighted
    diff content.
    """

    DEFAULT_CSS = """
    DiffViewer {
        height: 1fr;
        width: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        diff_files: list[DiffFile] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._diff_files: list[DiffFile] = diff_files or []

    def compose(self) -> ComposeResult:
        if not self._diff_files:
            yield Static("[dim]No diff data available.[/dim]", id="no-diff")
            return

        yield Static(
            f"[bold]Files changed: {len(self._diff_files)}[/bold]",
            id="diff-summary",
        )

        for i, diff_file in enumerate(self._diff_files):
            yield DiffFileViewer(diff_file, id=f"diff-file-{i}")

    def update_diffs(self, diff_files: list[DiffFile]) -> None:
        """Replace the displayed diffs with new data."""
        self._diff_files = diff_files
        self.remove_children()
        if not diff_files:
            self.mount(Static("[dim]No diff data available.[/dim]", id="no-diff"))
            return

        self.mount(
            Static(
                f"[bold]Files changed: {len(diff_files)}[/bold]",
                id="diff-summary",
            )
        )
        for i, diff_file in enumerate(diff_files):
            self.mount(DiffFileViewer(diff_file, id=f"diff-file-{i}"))
