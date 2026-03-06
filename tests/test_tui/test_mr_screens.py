"""Tests for MR list and detail TUI screens and related widgets."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from gltools.config.settings import GitLabConfig
from gltools.models import DiffFile, MergeRequest, Note, PipelineRef, UserRef
from gltools.tui.screens.mr_detail import (
    ActionBar,
    CommentList,
    MRActionRequested,
    MRDetailClosed,
    MRDetailScreen,
    MRHeader,
)
from gltools.tui.screens.mr_list import (
    DEFAULT_PER_PAGE,
    FilterBar,
    MRListScreen,
    MRSelected,
    PaginationBar,
)
from gltools.tui.widgets.diff_viewer import (
    LAZY_LOAD_THRESHOLD,
    DiffFileViewer,
    DiffViewer,
    _classify_line,
    _detect_lexer,
    _file_status_label,
)
from gltools.tui.widgets.status_badge import StatusBadge, status_color


def _make_config() -> GitLabConfig:
    return GitLabConfig(host="https://gitlab.com", token="test-token", profile="default")


def _make_user(username: str = "testuser", name: str = "Test User") -> UserRef:
    return UserRef(id=1, username=username, name=name)


def _make_mr(
    iid: int = 1,
    title: str = "Test MR",
    state: str = "opened",
    labels: list[str] | None = None,
    pipeline_status: str | None = None,
    description: str | None = "A test MR description.",
) -> MergeRequest:
    pipeline = None
    if pipeline_status:
        pipeline = PipelineRef(id=100, status=pipeline_status, web_url="https://gitlab.com/pipeline/100")
    return MergeRequest(
        id=1000 + iid,
        iid=iid,
        title=title,
        description=description,
        state=state,
        source_branch="feature",
        target_branch="main",
        author=_make_user(),
        labels=labels or [],
        pipeline=pipeline,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _make_note(note_id: int = 1, body: str = "A comment", system: bool = False) -> Note:
    return Note(
        id=note_id,
        body=body,
        author=_make_user(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        system=system,
    )


def _make_diff_file(
    new_path: str = "test.py",
    diff: str = "@@ -1,3 +1,4 @@\n context\n+added\n-removed\n context",
    new_file: bool = False,
    deleted_file: bool = False,
    renamed_file: bool = False,
    old_path: str | None = None,
) -> DiffFile:
    return DiffFile(
        old_path=old_path or new_path,
        new_path=new_path,
        diff=diff,
        new_file=new_file,
        deleted_file=deleted_file,
        renamed_file=renamed_file,
    )


# ---------------------------------------------------------------------------
# Status Badge Tests
# ---------------------------------------------------------------------------


class TestStatusColor:
    """Test the status_color helper function."""

    def test_opened_is_green(self) -> None:
        assert status_color("opened") == "green"

    def test_merged_is_blue(self) -> None:
        assert status_color("merged") == "blue"

    def test_closed_is_red(self) -> None:
        assert status_color("closed") == "red"

    def test_failed_is_red(self) -> None:
        assert status_color("failed") == "red"

    def test_running_is_yellow(self) -> None:
        assert status_color("running") == "yellow"

    def test_unknown_is_white(self) -> None:
        assert status_color("unknown_status") == "white"

    def test_case_insensitive(self) -> None:
        assert status_color("OPENED") == "green"
        assert status_color("Merged") == "blue"


class StatusBadgeApp(App[None]):
    def __init__(self, status: str) -> None:
        super().__init__()
        self._status = status

    def compose(self) -> ComposeResult:
        yield StatusBadge(self._status, id="badge")


class TestStatusBadge:
    """Test the StatusBadge widget."""

    @pytest.mark.asyncio
    async def test_badge_renders(self) -> None:
        app = StatusBadgeApp("opened")
        async with app.run_test(size=(40, 5)):
            badge = app.query_one("#badge", StatusBadge)
            assert badge is not None

    @pytest.mark.asyncio
    async def test_badge_status_reactive(self) -> None:
        app = StatusBadgeApp("opened")
        async with app.run_test(size=(40, 5)):
            badge = app.query_one("#badge", StatusBadge)
            badge.status = "merged"
            assert badge.status == "merged"


# ---------------------------------------------------------------------------
# Diff Viewer Tests
# ---------------------------------------------------------------------------


class TestDetectLexer:
    """Test file extension to lexer detection."""

    def test_python_file(self) -> None:
        assert _detect_lexer("src/main.py") == "python"

    def test_javascript_file(self) -> None:
        assert _detect_lexer("app.js") == "javascript"

    def test_typescript_file(self) -> None:
        assert _detect_lexer("component.tsx") == "typescript"

    def test_dockerfile(self) -> None:
        assert _detect_lexer("Dockerfile") == "dockerfile"

    def test_makefile(self) -> None:
        assert _detect_lexer("Makefile") == "makefile"

    def test_unknown_extension(self) -> None:
        assert _detect_lexer("file.xyz") == "text"

    def test_toml_file(self) -> None:
        assert _detect_lexer("pyproject.toml") == "toml"


class TestClassifyLine:
    """Test diff line classification."""

    def test_addition(self) -> None:
        assert _classify_line("+added line") == "addition"

    def test_deletion(self) -> None:
        assert _classify_line("-removed line") == "deletion"

    def test_hunk_header(self) -> None:
        assert _classify_line("@@ -1,3 +1,4 @@") == "hunk-header"

    def test_context_line(self) -> None:
        assert _classify_line(" context line") == ""

    def test_file_header_plus(self) -> None:
        assert _classify_line("+++ b/file.py") == ""

    def test_file_header_minus(self) -> None:
        assert _classify_line("--- a/file.py") == ""


class TestFileStatusLabel:
    """Test file status label generation."""

    def test_new_file(self) -> None:
        df = _make_diff_file(new_file=True)
        label = _file_status_label(df)
        assert "NEW" in label

    def test_deleted_file(self) -> None:
        df = _make_diff_file(deleted_file=True)
        label = _file_status_label(df)
        assert "DELETED" in label

    def test_renamed_file(self) -> None:
        df = _make_diff_file(renamed_file=True, old_path="old.py", new_path="new.py")
        label = _file_status_label(df)
        assert "RENAMED" in label

    def test_modified_file(self) -> None:
        df = _make_diff_file()
        label = _file_status_label(df)
        assert "MODIFIED" in label


class DiffViewerApp(App[None]):
    def __init__(self, diff_files: list[DiffFile]) -> None:
        super().__init__()
        self._diff_files = diff_files

    def compose(self) -> ComposeResult:
        yield DiffViewer(self._diff_files, id="diff-viewer")


class TestDiffViewer:
    """Test the DiffViewer widget."""

    @pytest.mark.asyncio
    async def test_empty_diff(self) -> None:
        app = DiffViewerApp([])
        async with app.run_test(size=(80, 24)):
            viewer = app.query_one("#diff-viewer", DiffViewer)
            assert viewer is not None
            no_diff = app.query_one("#no-diff", Static)
            assert no_diff is not None

    @pytest.mark.asyncio
    async def test_with_diff_files(self) -> None:
        diff_files = [_make_diff_file(), _make_diff_file(new_path="other.py")]
        app = DiffViewerApp(diff_files)
        async with app.run_test(size=(80, 24)):
            viewer = app.query_one("#diff-viewer", DiffViewer)
            assert viewer is not None
            summary = app.query_one("#diff-summary", Static)
            assert summary is not None

    @pytest.mark.asyncio
    async def test_update_diffs(self) -> None:
        app = DiffViewerApp([])
        async with app.run_test(size=(80, 24)) as pilot:
            viewer = app.query_one("#diff-viewer", DiffViewer)
            viewer.update_diffs([_make_diff_file()])
            await pilot.pause()
            summary = app.query("#diff-summary")
            assert len(summary) > 0


class TestDiffFileViewerLazyLoading:
    """Test lazy loading for large diffs."""

    def test_large_diff_detection(self) -> None:
        large_diff = "\n".join([f"+line {i}" for i in range(LAZY_LOAD_THRESHOLD + 100)])
        df = _make_diff_file(diff=large_diff)
        viewer = DiffFileViewer(df)
        assert viewer._is_large is True

    def test_small_diff_not_large(self) -> None:
        df = _make_diff_file()
        viewer = DiffFileViewer(df)
        assert viewer._is_large is False


# ---------------------------------------------------------------------------
# MR List Screen Tests
# ---------------------------------------------------------------------------


class MRListApp(App[None]):
    def __init__(self, config: GitLabConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield MRListScreen(self._config, id="mr-list")


class TestMRListScreen:
    """Test the MR list screen."""

    @pytest.mark.asyncio
    async def test_mr_list_renders(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            assert mr_list is not None

    @pytest.mark.asyncio
    async def test_mr_list_has_table(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            table = app.query_one("#mr-table", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    async def test_mr_list_table_columns(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            table = app.query_one("#mr-table", DataTable)
            column_keys = [col.key.value for col in table.columns.values()]
            assert "iid" in column_keys
            assert "title" in column_keys
            assert "author" in column_keys
            assert "state" in column_keys
            assert "pipeline" in column_keys
            assert "labels" in column_keys

    @pytest.mark.asyncio
    async def test_populate_table(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            mrs = [_make_mr(iid=1), _make_mr(iid=2, title="Second MR")]
            mr_list.populate_table(mrs, total=2, page=1, total_pages=1)
            table = app.query_one("#mr-table", DataTable)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_populate_table_with_pipeline(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            mrs = [_make_mr(iid=1, pipeline_status="success")]
            mr_list.populate_table(mrs, total=1)
            table = app.query_one("#mr-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_populate_table_with_labels(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            mrs = [_make_mr(iid=1, labels=["bug", "urgent", "frontend", "extra"])]
            mr_list.populate_table(mrs, total=1)
            table = app.query_one("#mr-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_pagination_bar_updates(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            mrs = [_make_mr(iid=i) for i in range(1, 21)]
            mr_list.populate_table(mrs, total=50, page=2, total_pages=3)
            pagination = app.query_one("#pagination-bar", PaginationBar)
            assert pagination.page == 2
            assert pagination.total_pages == 3
            assert pagination.total_items == 50


class TestMRListFilters:
    """Test MR list filter controls."""

    @pytest.mark.asyncio
    async def test_filter_bar_renders(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            filter_bar = app.query_one("#filter-bar", FilterBar)
            assert filter_bar is not None

    @pytest.mark.asyncio
    async def test_get_filters_default(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            filters = mr_list.get_filters()
            assert filters["state"] == "opened"
            assert filters["per_page"] == DEFAULT_PER_PAGE
            assert filters["page"] == 1


class TestMRListKeyboard:
    """Test keyboard navigation in MR list."""

    @pytest.mark.asyncio
    async def test_bindings_defined(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            binding_keys = [b.key for b in mr_list.BINDINGS]
            assert "r" in binding_keys
            assert "enter" in binding_keys
            assert "n" in binding_keys
            assert "p" in binding_keys
            assert "/" in binding_keys

    @pytest.mark.asyncio
    async def test_next_page_action_increments(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            mr_list._total_pages = 3
            mr_list._current_page = 1
            mr_list.action_next_page()
            assert mr_list._current_page == 2

    @pytest.mark.asyncio
    async def test_next_page_action_clamps_at_max(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            mr_list._total_pages = 2
            mr_list._current_page = 2
            mr_list.action_next_page()
            assert mr_list._current_page == 2

    @pytest.mark.asyncio
    async def test_prev_page_action_decrements(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            mr_list._total_pages = 3
            mr_list._current_page = 2
            mr_list.action_prev_page()
            assert mr_list._current_page == 1

    @pytest.mark.asyncio
    async def test_prev_page_action_clamps_at_min(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            mr_list._total_pages = 3
            mr_list._current_page = 1
            mr_list.action_prev_page()
            assert mr_list._current_page == 1

    @pytest.mark.asyncio
    async def test_action_refresh(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            mr_list = app.query_one("#mr-list", MRListScreen)
            mr_list.action_refresh()

    @pytest.mark.asyncio
    async def test_focus_search_action(self) -> None:
        app = MRListApp(_make_config())
        async with app.run_test(size=(120, 30)) as pilot:
            mr_list = app.query_one("#mr-list", MRListScreen)
            mr_list.action_focus_search()
            await pilot.pause()
            from textual.widgets import Input
            search = app.query_one("#search-filter", Input)
            assert search.has_focus


# ---------------------------------------------------------------------------
# MR Detail Screen Tests
# ---------------------------------------------------------------------------


class MRDetailApp(App[None]):
    def __init__(self, mr: MergeRequest | None = None) -> None:
        super().__init__()
        self._mr = mr

    def compose(self) -> ComposeResult:
        config = _make_config()
        mr_iid = self._mr.iid if self._mr else 1
        yield MRDetailScreen(mr_iid, config, mr=self._mr, id="mr-detail")


class TestMRDetailScreen:
    """Test the MR detail screen."""

    @pytest.mark.asyncio
    async def test_detail_renders_with_mr(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#mr-detail", MRDetailScreen)
            assert detail is not None

    @pytest.mark.asyncio
    async def test_detail_has_header(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#mr-header", MRHeader)
            assert header is not None

    @pytest.mark.asyncio
    async def test_detail_has_tabs(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            tabs = app.query_one("#mr-tabs")
            assert tabs is not None

    @pytest.mark.asyncio
    async def test_detail_has_action_bar(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            action_bar = app.query_one("#action-bar", ActionBar)
            assert action_bar is not None

    @pytest.mark.asyncio
    async def test_set_diff(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#mr-detail", MRDetailScreen)
            detail.set_diff([_make_diff_file()])
            viewer = app.query_one("#diff-viewer", DiffViewer)
            assert viewer is not None

    @pytest.mark.asyncio
    async def test_set_notes(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#mr-detail", MRDetailScreen)
            detail.set_notes([_make_note()])
            comment_list = app.query_one("#comment-list", CommentList)
            assert comment_list is not None

    @pytest.mark.asyncio
    async def test_detail_without_mr(self) -> None:
        app = MRDetailApp(None)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#mr-detail", MRDetailScreen)
            assert detail is not None


class TestMRDetailActions:
    """Test MR detail action buttons."""

    @pytest.mark.asyncio
    async def test_action_bar_has_approve_for_opened(self) -> None:
        mr = _make_mr(state="opened")
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            approve_btn = app.query("#btn-approve")
            assert len(approve_btn) > 0

    @pytest.mark.asyncio
    async def test_action_bar_has_merge_for_opened(self) -> None:
        mr = _make_mr(state="opened")
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            merge_btn = app.query("#btn-merge")
            assert len(merge_btn) > 0

    @pytest.mark.asyncio
    async def test_action_bar_has_comment(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            comment_btn = app.query("#btn-comment")
            assert len(comment_btn) > 0

    @pytest.mark.asyncio
    async def test_escape_binding_exists(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#mr-detail", MRDetailScreen)
            binding_keys = [b.key for b in detail.BINDINGS]
            assert "escape" in binding_keys


class TestMRDetailActionExecution:
    """Test MR detail action button execution."""

    @pytest.mark.asyncio
    async def test_approve_button_posts_action(self) -> None:
        from textual.widgets import Button

        mr = _make_mr(state="opened")
        app = MRDetailApp(mr)
        messages: list[MRActionRequested] = []
        async with app.run_test(size=(120, 30)) as pilot:
            action_bar = app.query_one("#action-bar", ActionBar)
            original_post = action_bar.post_message
            action_bar.post_message = lambda msg: messages.append(msg) or original_post(msg)  # type: ignore[assignment]
            approve_btn = app.query_one("#btn-approve", Button)
            approve_btn.press()
            await pilot.pause()
            await pilot.pause()
            action_msgs = [m for m in messages if isinstance(m, MRActionRequested)]
            assert len(action_msgs) >= 1
            assert action_msgs[0].action == "approve"

    @pytest.mark.asyncio
    async def test_merge_button_posts_action(self) -> None:
        from textual.widgets import Button

        mr = _make_mr(state="opened")
        app = MRDetailApp(mr)
        messages: list[MRActionRequested] = []
        async with app.run_test(size=(120, 30)) as pilot:
            action_bar = app.query_one("#action-bar", ActionBar)
            original_post = action_bar.post_message
            action_bar.post_message = lambda msg: messages.append(msg) or original_post(msg)  # type: ignore[assignment]
            merge_btn = app.query_one("#btn-merge", Button)
            merge_btn.press()
            await pilot.pause()
            await pilot.pause()
            action_msgs = [m for m in messages if isinstance(m, MRActionRequested)]
            assert len(action_msgs) >= 1
            assert action_msgs[0].action == "merge"

    @pytest.mark.asyncio
    async def test_go_back_action_posts_closed_message(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        messages: list[MRDetailClosed] = []
        async with app.run_test(size=(120, 30)) as pilot:
            detail = app.query_one("#mr-detail", MRDetailScreen)
            original_post = detail.post_message
            detail.post_message = lambda msg: messages.append(msg) or original_post(msg)  # type: ignore[assignment]
            detail.action_go_back()
            await pilot.pause()
            closed_msgs = [m for m in messages if isinstance(m, MRDetailClosed)]
            assert len(closed_msgs) >= 1

    @pytest.mark.asyncio
    async def test_set_mr_updates_header(self) -> None:
        app = MRDetailApp(None)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#mr-detail", MRDetailScreen)
            mr = _make_mr(iid=99, title="Freshly loaded MR")
            detail.set_mr(mr)
            assert detail._mr is mr
            assert detail._mr_iid == 99


class TestMRHeaderWidget:
    """Test the MR header widget."""

    @pytest.mark.asyncio
    async def test_header_with_mr(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#mr-header", MRHeader)
            assert header._mr is mr

    @pytest.mark.asyncio
    async def test_header_without_mr(self) -> None:
        app = MRDetailApp(None)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#mr-header", MRHeader)
            assert header._mr is None

    @pytest.mark.asyncio
    async def test_header_with_pipeline(self) -> None:
        mr = _make_mr(pipeline_status="success")
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#mr-header", MRHeader)
            assert header._mr is not None
            assert header._mr.pipeline is not None

    @pytest.mark.asyncio
    async def test_header_with_labels(self) -> None:
        mr = _make_mr(labels=["bug", "critical"])
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#mr-header", MRHeader)
            assert header is not None

    @pytest.mark.asyncio
    async def test_update_mr(self) -> None:
        app = MRDetailApp(None)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#mr-header", MRHeader)
            mr = _make_mr(iid=5, title="Updated MR")
            header.update_mr(mr)
            assert header._mr is mr


class TestCommentList:
    """Test the comment list widget."""

    @pytest.mark.asyncio
    async def test_empty_comments(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            comment_list = app.query_one("#comment-list", CommentList)
            assert comment_list is not None

    @pytest.mark.asyncio
    async def test_update_notes(self) -> None:
        mr = _make_mr()
        app = MRDetailApp(mr)
        async with app.run_test(size=(120, 30)):
            comment_list = app.query_one("#comment-list", CommentList)
            notes = [_make_note(1, "First comment"), _make_note(2, "Second comment")]
            comment_list.update_notes(notes)


class TestMRMessages:
    """Test message types."""

    def test_mr_selected_message(self) -> None:
        msg = MRSelected(42)
        assert msg.mr_iid == 42

    def test_mr_detail_closed_message(self) -> None:
        msg = MRDetailClosed()
        assert isinstance(msg, MRDetailClosed)

    def test_mr_action_requested_message(self) -> None:
        msg = MRActionRequested("approve", 42)
        assert msg.action == "approve"
        assert msg.mr_iid == 42
        assert msg.payload == {}

    def test_mr_action_requested_with_payload(self) -> None:
        msg = MRActionRequested("comment", 42, {"body": "hello"})
        assert msg.payload == {"body": "hello"}
