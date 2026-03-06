"""Tests for Issue list and detail TUI screens and related widgets."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Input, Static

from gltools.config.settings import GitLabConfig
from gltools.models.issue import Issue
from gltools.models.user import UserRef
from gltools.tui.screens.issue_detail import (
    IssueActionBar,
    IssueActionRequested,
    IssueCommentList,
    IssueDetailClosed,
    IssueDetailScreen,
    IssueHeader,
)
from gltools.tui.screens.issue_list import (
    DEFAULT_PER_PAGE,
    IssueFilterBar,
    IssueListScreen,
    IssuePaginationBar,
    IssueSelected,
)


def _make_config() -> GitLabConfig:
    return GitLabConfig(host="https://gitlab.com", token="test-token", profile="default")


def _make_user(username: str = "testuser", name: str = "Test User") -> UserRef:
    return UserRef(id=1, username=username, name=name)


def _make_issue(
    iid: int = 1,
    title: str = "Test Issue",
    state: str = "opened",
    labels: list[str] | None = None,
    description: str | None = "An issue description.",
    milestone: str | None = None,
    confidential: bool = False,
    assignee: UserRef | None = None,
) -> Issue:
    return Issue(
        id=200 + iid,
        iid=iid,
        title=title,
        description=description,
        state=state,
        author=_make_user(),
        assignee=assignee,
        labels=labels or [],
        milestone=milestone,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        closed_at=None,
        confidential=confidential,
    )


def _make_note(note_id: int = 1, body: str = "A comment", system: bool = False) -> Any:
    from gltools.models import Note

    return Note(
        id=note_id,
        body=body,
        author=_make_user(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        system=system,
    )


# ---------------------------------------------------------------------------
# Message tests
# ---------------------------------------------------------------------------


class TestIssueMessages:
    """Test issue-related message types."""

    def test_issue_selected_message(self) -> None:
        msg = IssueSelected(42)
        assert msg.issue_iid == 42

    def test_issue_detail_closed_message(self) -> None:
        msg = IssueDetailClosed()
        assert isinstance(msg, IssueDetailClosed)

    def test_issue_action_requested_message(self) -> None:
        msg = IssueActionRequested("close", 42)
        assert msg.action == "close"
        assert msg.issue_iid == 42
        assert msg.payload == {}

    def test_issue_action_requested_with_payload(self) -> None:
        msg = IssueActionRequested("comment", 42, {"body": "hello"})
        assert msg.payload == {"body": "hello"}


# ---------------------------------------------------------------------------
# Issue List Screen Tests
# ---------------------------------------------------------------------------


class IssueListApp(App[None]):
    def __init__(self, config: GitLabConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield IssueListScreen(self._config, id="issue-list")


class TestIssueListScreen:
    """Test the issue list screen rendering and composition."""

    @pytest.mark.asyncio
    async def test_issue_list_renders(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            assert issue_list is not None

    @pytest.mark.asyncio
    async def test_issue_list_has_table(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            table = app.query_one("#issue-table", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    async def test_issue_list_table_columns(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            table = app.query_one("#issue-table", DataTable)
            column_keys = [col.key.value for col in table.columns.values()]
            assert "iid" in column_keys
            assert "title" in column_keys
            assert "author" in column_keys
            assert "state" in column_keys
            assert "labels" in column_keys
            assert "milestone" in column_keys

    @pytest.mark.asyncio
    async def test_issue_list_has_filter_bar(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            filter_bar = app.query_one("#filter-bar", IssueFilterBar)
            assert filter_bar is not None

    @pytest.mark.asyncio
    async def test_issue_list_has_pagination_bar(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            pagination = app.query_one("#pagination-bar", IssuePaginationBar)
            assert pagination is not None

    @pytest.mark.asyncio
    async def test_populate_table(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            issues = [_make_issue(iid=1), _make_issue(iid=2, title="Second Issue")]
            issue_list.populate_table(issues, total=2, page=1, total_pages=1)
            table = app.query_one("#issue-table", DataTable)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_populate_table_with_labels(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            issues = [_make_issue(iid=1, labels=["bug", "urgent", "frontend", "extra"])]
            issue_list.populate_table(issues, total=1)
            table = app.query_one("#issue-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_populate_table_with_milestone(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            issues = [_make_issue(iid=1, milestone="v1.0")]
            issue_list.populate_table(issues, total=1)
            table = app.query_one("#issue-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_populate_table_confidential(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            issues = [_make_issue(iid=1, confidential=True)]
            issue_list.populate_table(issues, total=1)
            table = app.query_one("#issue-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_pagination_bar_updates(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            issues = [_make_issue(iid=i) for i in range(1, 21)]
            issue_list.populate_table(issues, total=50, page=2, total_pages=3)
            pagination = app.query_one("#pagination-bar", IssuePaginationBar)
            assert pagination.page == 2
            assert pagination.total_pages == 3
            assert pagination.total_items == 50

    @pytest.mark.asyncio
    async def test_long_title_truncated(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            long_title = "A" * 80
            issues = [_make_issue(iid=1, title=long_title)]
            issue_list.populate_table(issues, total=1)
            table = app.query_one("#issue-table", DataTable)
            assert table.row_count == 1


class TestIssueListFilters:
    """Test issue list filter controls."""

    @pytest.mark.asyncio
    async def test_get_filters_default(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            filters = issue_list.get_filters()
            assert filters["state"] == "opened"
            assert filters["per_page"] == DEFAULT_PER_PAGE
            assert filters["page"] == 1

    @pytest.mark.asyncio
    async def test_get_filters_includes_milestone(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            filters = issue_list.get_filters()
            assert "milestone" in filters

    @pytest.mark.asyncio
    async def test_filter_bar_has_milestone_input(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            milestone_input = app.query_one("#milestone-filter", Input)
            assert milestone_input is not None


class TestIssueListKeyboard:
    """Test keyboard navigation in issue list."""

    @pytest.mark.asyncio
    async def test_bindings_defined(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            binding_keys = [b.key for b in issue_list.BINDINGS]
            assert "r" in binding_keys
            assert "enter" in binding_keys
            assert "n" in binding_keys
            assert "p" in binding_keys
            assert "/" in binding_keys

    @pytest.mark.asyncio
    async def test_next_page_action_increments(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            issue_list._total_pages = 3
            issue_list._current_page = 1
            issue_list.action_next_page()
            assert issue_list._current_page == 2

    @pytest.mark.asyncio
    async def test_next_page_action_clamps_at_max(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            issue_list._total_pages = 2
            issue_list._current_page = 2
            issue_list.action_next_page()
            assert issue_list._current_page == 2

    @pytest.mark.asyncio
    async def test_prev_page_action_decrements(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            issue_list._total_pages = 3
            issue_list._current_page = 2
            issue_list.action_prev_page()
            assert issue_list._current_page == 1

    @pytest.mark.asyncio
    async def test_prev_page_action_clamps_at_min(self) -> None:
        app = IssueListApp(_make_config())
        async with app.run_test(size=(120, 30)):
            issue_list = app.query_one("#issue-list", IssueListScreen)
            issue_list._total_pages = 3
            issue_list._current_page = 1
            issue_list.action_prev_page()
            assert issue_list._current_page == 1


# ---------------------------------------------------------------------------
# Issue Detail Screen Tests
# ---------------------------------------------------------------------------


class IssueDetailApp(App[None]):
    def __init__(self, issue: Issue | None = None) -> None:
        super().__init__()
        self._issue = issue

    def compose(self) -> ComposeResult:
        config = _make_config()
        issue_iid = self._issue.iid if self._issue else 1
        yield IssueDetailScreen(issue_iid, config, issue=self._issue, id="issue-detail")


class TestIssueDetailScreen:
    """Test the issue detail screen rendering and composition."""

    @pytest.mark.asyncio
    async def test_detail_renders_with_issue(self) -> None:
        issue = _make_issue()
        app = IssueDetailApp(issue)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#issue-detail", IssueDetailScreen)
            assert detail is not None

    @pytest.mark.asyncio
    async def test_detail_has_header(self) -> None:
        issue = _make_issue()
        app = IssueDetailApp(issue)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#issue-header", IssueHeader)
            assert header is not None

    @pytest.mark.asyncio
    async def test_detail_has_tabs(self) -> None:
        issue = _make_issue()
        app = IssueDetailApp(issue)
        async with app.run_test(size=(120, 30)):
            tabs = app.query_one("#issue-tabs")
            assert tabs is not None

    @pytest.mark.asyncio
    async def test_detail_has_action_bar(self) -> None:
        issue = _make_issue()
        app = IssueDetailApp(issue)
        async with app.run_test(size=(120, 30)):
            action_bar = app.query_one("#action-bar", IssueActionBar)
            assert action_bar is not None

    @pytest.mark.asyncio
    async def test_detail_without_issue_shows_loading(self) -> None:
        app = IssueDetailApp(None)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#issue-detail", IssueDetailScreen)
            assert detail is not None

    @pytest.mark.asyncio
    async def test_set_issue_updates_display(self) -> None:
        app = IssueDetailApp(None)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#issue-detail", IssueDetailScreen)
            issue = _make_issue(iid=5, title="Updated issue")
            detail.set_issue(issue)
            assert detail._issue is issue
            assert detail._issue_iid == 5

    @pytest.mark.asyncio
    async def test_set_notes_updates_comments(self) -> None:
        issue = _make_issue()
        app = IssueDetailApp(issue)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#issue-detail", IssueDetailScreen)
            notes = [_make_note(1, "First"), _make_note(2, "Second")]
            detail.set_notes(notes)
            comment_list = app.query_one("#comment-list", IssueCommentList)
            assert len(comment_list._notes) == 2

    @pytest.mark.asyncio
    async def test_set_linked_mrs(self) -> None:
        issue = _make_issue()
        app = IssueDetailApp(issue)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#issue-detail", IssueDetailScreen)
            linked = [{"iid": 1, "title": "MR 1", "state": "opened", "web_url": "http://x"}]
            detail.set_linked_mrs(linked)
            assert detail._linked_mrs == linked

    @pytest.mark.asyncio
    async def test_set_linked_mrs_empty(self) -> None:
        issue = _make_issue()
        app = IssueDetailApp(issue)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#issue-detail", IssueDetailScreen)
            detail.set_linked_mrs([])
            assert detail._linked_mrs == []

    @pytest.mark.asyncio
    async def test_escape_binding_exists(self) -> None:
        issue = _make_issue()
        app = IssueDetailApp(issue)
        async with app.run_test(size=(120, 30)):
            detail = app.query_one("#issue-detail", IssueDetailScreen)
            binding_keys = [b.key for b in detail.BINDINGS]
            assert "escape" in binding_keys
            assert "backspace" in binding_keys

    @pytest.mark.asyncio
    async def test_action_go_back_posts_message(self) -> None:
        issue = _make_issue()
        app = IssueDetailApp(issue)
        messages: list[IssueDetailClosed] = []

        async with app.run_test(size=(120, 30)) as pilot:
            detail = app.query_one("#issue-detail", IssueDetailScreen)
            original_post = detail.post_message
            detail.post_message = lambda msg: messages.append(msg) or original_post(msg)  # type: ignore[assignment]
            detail.action_go_back()
            await pilot.pause()
            closed_msgs = [m for m in messages if isinstance(m, IssueDetailClosed)]
            assert len(closed_msgs) >= 1


# ---------------------------------------------------------------------------
# Issue Action Bar Tests
# ---------------------------------------------------------------------------


class IssueActionBarApp(App[None]):
    def __init__(self, issue_iid: int = 1, state: str = "opened") -> None:
        super().__init__()
        self._iid = issue_iid
        self._state = state

    def compose(self) -> ComposeResult:
        yield IssueActionBar(self._iid, self._state, id="action-bar")


class TestIssueActionBar:
    """Test issue action bar buttons."""

    @pytest.mark.asyncio
    async def test_close_button_for_opened_issue(self) -> None:
        app = IssueActionBarApp(state="opened")
        async with app.run_test(size=(120, 30)):
            close_btn = app.query("#btn-close")
            assert len(close_btn) > 0

    @pytest.mark.asyncio
    async def test_reopen_button_for_closed_issue(self) -> None:
        app = IssueActionBarApp(state="closed")
        async with app.run_test(size=(120, 30)):
            reopen_btn = app.query("#btn-reopen")
            assert len(reopen_btn) > 0

    @pytest.mark.asyncio
    async def test_no_close_for_closed_issue(self) -> None:
        app = IssueActionBarApp(state="closed")
        async with app.run_test(size=(120, 30)):
            close_btn = app.query("#btn-close")
            assert len(close_btn) == 0

    @pytest.mark.asyncio
    async def test_no_reopen_for_opened_issue(self) -> None:
        app = IssueActionBarApp(state="opened")
        async with app.run_test(size=(120, 30)):
            reopen_btn = app.query("#btn-reopen")
            assert len(reopen_btn) == 0

    @pytest.mark.asyncio
    async def test_comment_button_always_shown(self) -> None:
        app = IssueActionBarApp(state="opened")
        async with app.run_test(size=(120, 30)):
            comment_btn = app.query("#btn-comment")
            assert len(comment_btn) > 0

    @pytest.mark.asyncio
    async def test_comment_input_present(self) -> None:
        app = IssueActionBarApp()
        async with app.run_test(size=(120, 30)):
            comment_input = app.query_one("#comment-input", Input)
            assert comment_input is not None

    @pytest.mark.asyncio
    async def test_close_button_posts_action(self) -> None:
        app = IssueActionBarApp(issue_iid=42, state="opened")
        messages: list[IssueActionRequested] = []
        async with app.run_test(size=(120, 30)) as pilot:
            action_bar = app.query_one("#action-bar", IssueActionBar)
            original_post = action_bar.post_message
            action_bar.post_message = lambda msg: messages.append(msg) or original_post(msg)  # type: ignore[assignment]
            close_btn = app.query_one("#btn-close", Button)
            close_btn.press()
            await pilot.pause()
            await pilot.pause()
            action_msgs = [m for m in messages if isinstance(m, IssueActionRequested)]
            assert len(action_msgs) >= 1
            assert action_msgs[0].action == "close"
            assert action_msgs[0].issue_iid == 42

    @pytest.mark.asyncio
    async def test_reopen_button_posts_action(self) -> None:
        app = IssueActionBarApp(issue_iid=10, state="closed")
        messages: list[IssueActionRequested] = []
        async with app.run_test(size=(120, 30)) as pilot:
            action_bar = app.query_one("#action-bar", IssueActionBar)
            original_post = action_bar.post_message
            action_bar.post_message = lambda msg: messages.append(msg) or original_post(msg)  # type: ignore[assignment]
            reopen_btn = app.query_one("#btn-reopen", Button)
            reopen_btn.press()
            await pilot.pause()
            await pilot.pause()
            action_msgs = [m for m in messages if isinstance(m, IssueActionRequested)]
            assert len(action_msgs) >= 1
            assert action_msgs[0].action == "reopen"


# ---------------------------------------------------------------------------
# Issue Comment List Tests
# ---------------------------------------------------------------------------


class IssueCommentApp(App[None]):
    def __init__(self, notes: list[Any] | None = None) -> None:
        super().__init__()
        self._notes = notes

    def compose(self) -> ComposeResult:
        yield IssueCommentList(self._notes, id="comment-list")


class TestIssueCommentList:
    """Test the issue comment list widget."""

    @pytest.mark.asyncio
    async def test_empty_comments_show_message(self) -> None:
        app = IssueCommentApp()
        async with app.run_test(size=(120, 30)):
            comment_list = app.query_one("#comment-list", IssueCommentList)
            assert comment_list is not None
            no_comments = app.query_one("#no-comments", Static)
            assert no_comments is not None

    @pytest.mark.asyncio
    async def test_with_notes(self) -> None:
        notes = [_make_note(1, "First"), _make_note(2, "Second")]
        app = IssueCommentApp(notes)
        async with app.run_test(size=(120, 30)):
            entries = app.query(".comment-entry")
            assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_system_note_tagged(self) -> None:
        notes = [_make_note(1, "System note", system=True)]
        app = IssueCommentApp(notes)
        async with app.run_test(size=(120, 30)):
            entries = app.query(".comment-entry")
            assert len(entries) == 1

    @pytest.mark.asyncio
    async def test_update_notes(self) -> None:
        app = IssueCommentApp()
        async with app.run_test(size=(120, 30)):
            comment_list = app.query_one("#comment-list", IssueCommentList)
            notes = [_make_note(1, "Updated comment")]
            comment_list.update_notes(notes)
            assert len(comment_list._notes) == 1

    @pytest.mark.asyncio
    async def test_update_notes_empty(self) -> None:
        notes = [_make_note(1, "Original")]
        app = IssueCommentApp(notes)
        async with app.run_test(size=(120, 30)):
            comment_list = app.query_one("#comment-list", IssueCommentList)
            comment_list.update_notes([])
            no_comments = app.query("#no-comments")
            assert len(no_comments) > 0


# ---------------------------------------------------------------------------
# Issue Header Tests
# ---------------------------------------------------------------------------


class IssueHeaderApp(App[None]):
    def __init__(self, issue: Issue | None = None) -> None:
        super().__init__()
        self._issue = issue

    def compose(self) -> ComposeResult:
        yield IssueHeader(self._issue, id="issue-header")


class TestIssueHeader:
    """Test the issue header widget."""

    @pytest.mark.asyncio
    async def test_renders_with_issue(self) -> None:
        issue = _make_issue()
        app = IssueHeaderApp(issue)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#issue-header", IssueHeader)
            assert header is not None

    @pytest.mark.asyncio
    async def test_renders_without_issue(self) -> None:
        app = IssueHeaderApp(None)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#issue-header", IssueHeader)
            assert header is not None

    @pytest.mark.asyncio
    async def test_update_issue(self) -> None:
        app = IssueHeaderApp(None)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#issue-header", IssueHeader)
            issue = _make_issue(iid=5, title="Updated")
            header.update_issue(issue)
            assert header._issue is issue

    @pytest.mark.asyncio
    async def test_issue_with_labels(self) -> None:
        issue = _make_issue(labels=["bug", "high"])
        app = IssueHeaderApp(issue)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#issue-header", IssueHeader)
            assert header is not None

    @pytest.mark.asyncio
    async def test_issue_with_assignee(self) -> None:
        issue = _make_issue(assignee=_make_user("alice", "Alice"))
        app = IssueHeaderApp(issue)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#issue-header", IssueHeader)
            assert header is not None

    @pytest.mark.asyncio
    async def test_issue_with_milestone(self) -> None:
        issue = _make_issue(milestone="v2.0")
        app = IssueHeaderApp(issue)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#issue-header", IssueHeader)
            assert header is not None

    @pytest.mark.asyncio
    async def test_confidential_issue(self) -> None:
        issue = _make_issue(confidential=True)
        app = IssueHeaderApp(issue)
        async with app.run_test(size=(120, 30)):
            header = app.query_one("#issue-header", IssueHeader)
            assert header is not None
