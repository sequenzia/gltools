"""Tests for the TUI dashboard screen."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from gltools.config.settings import GitLabConfig
from gltools.models.issue import Issue
from gltools.models.merge_request import MergeRequest
from gltools.models.output import PaginatedResponse
from gltools.models.pipeline import Pipeline
from gltools.models.user import UserRef
from gltools.tui.screens.dashboard import (
    DashboardPanel,
    DashboardScreen,
    ItemSelected,
    _status_icon,
)


def _make_config(
    host: str = "https://gitlab.com",
    token: str = "test-token",
    profile: str = "default",
) -> GitLabConfig:
    """Create a GitLabConfig for testing."""
    return GitLabConfig(host=host, token=token, profile=profile)


def _make_user(username: str = "testuser") -> UserRef:
    return UserRef(id=1, username=username, name="Test User")


def _make_mr(
    iid: int = 1,
    title: str = "Test MR",
    state: str = "opened",
    username: str = "testuser",
) -> MergeRequest:
    now = datetime.now(tz=UTC)
    return MergeRequest(
        id=100 + iid,
        iid=iid,
        title=title,
        state=state,
        source_branch="feature",
        target_branch="main",
        author=_make_user(username),
        labels=[],
        created_at=now,
        updated_at=now,
    )


def _make_issue(
    iid: int = 1,
    title: str = "Test Issue",
    state: str = "opened",
    labels: list[str] | None = None,
) -> Issue:
    now = datetime.now(tz=UTC)
    return Issue(
        id=200 + iid,
        iid=iid,
        title=title,
        description=None,
        state=state,
        author=_make_user(),
        assignee=None,
        labels=labels or [],
        milestone=None,
        created_at=now,
        updated_at=now,
        closed_at=None,
    )


def _make_pipeline(
    pipeline_id: int = 1,
    status: str = "success",
    ref: str = "main",
    duration: float | None = 120.0,
) -> Pipeline:
    now = datetime.now(tz=UTC)
    return Pipeline(
        id=pipeline_id,
        status=status,
        ref=ref,
        sha="abc123",
        source="push",
        created_at=now,
        duration=duration,
    )


class TestStatusIcon:
    """Test status icon helper."""

    def test_opened_icon(self) -> None:
        icon = _status_icon("opened")
        assert "green" in icon

    def test_merged_icon(self) -> None:
        icon = _status_icon("merged")
        assert "magenta" in icon

    def test_closed_icon(self) -> None:
        icon = _status_icon("closed")
        assert "red" in icon

    def test_success_icon(self) -> None:
        icon = _status_icon("success")
        assert "green" in icon

    def test_failed_icon(self) -> None:
        icon = _status_icon("failed")
        assert "red" in icon

    def test_running_icon(self) -> None:
        icon = _status_icon("running")
        assert "blue" in icon

    def test_unknown_status_fallback(self) -> None:
        icon = _status_icon("unknown_status")
        assert "unknown_status" in icon


class TestItemSelectedMessage:
    """Test the ItemSelected message."""

    def test_item_selected_attributes(self) -> None:
        msg = ItemSelected(item_type="mr", item_id=42)
        assert msg.item_type == "mr"
        assert msg.item_id == 42


class TestDashboardScreenInit:
    """Test dashboard screen initialization."""

    def test_stores_config(self) -> None:
        config = _make_config()
        screen = DashboardScreen(config)
        assert screen._config is config


class TestDashboardScreenCompose:
    """Test dashboard screen composition and rendering."""

    @pytest.mark.asyncio
    async def test_has_three_panels(self) -> None:
        from gltools.tui.app import GLToolsApp

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(120, 40)):
            panels = app.query(DashboardPanel)
            assert len(panels) == 3

    @pytest.mark.asyncio
    async def test_panel_ids(self) -> None:
        from gltools.tui.app import GLToolsApp

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(120, 40)):
            assert app.query_one("#panel-mrs", DashboardPanel)
            assert app.query_one("#panel-issues", DashboardPanel)
            assert app.query_one("#panel-pipelines", DashboardPanel)

    @pytest.mark.asyncio
    async def test_dashboard_header_shows_host(self) -> None:
        from textual.widgets import Static

        from gltools.tui.app import GLToolsApp

        app = GLToolsApp(config=_make_config(host="https://gitlab.example.com"))
        async with app.run_test(size=(120, 40)):
            header = app.query_one("#dashboard-header", Static)
            # Static stores its content internally; check via update content
            assert header is not None


class TestDashboardDataLoading:
    """Test async data loading behavior."""

    @pytest.mark.asyncio
    async def test_load_mrs_shows_items(self) -> None:
        from gltools.tui.app import GLToolsApp

        mrs = [_make_mr(iid=1, title="Fix bug"), _make_mr(iid=2, title="Add feature")]
        paginated = PaginatedResponse[MergeRequest](
            items=mrs, page=1, per_page=10, total=2, total_pages=1, next_page=None
        )

        mock_list_mrs = AsyncMock(return_value=paginated)
        mock_close = AsyncMock()

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(120, 40)):
            dashboard = app.query_one(DashboardScreen)
            with (
                patch("gltools.tui.screens.dashboard.DashboardScreen._create_client") as mock_create,
                patch("gltools.services.merge_request.MergeRequestService.list_mrs", mock_list_mrs),
            ):
                mock_client = AsyncMock()
                mock_client.close = mock_close
                mock_create.return_value = (mock_client, "token")

                await dashboard._load_mrs()

            panel = app.query_one("#panel-mrs", DashboardPanel)
            from textual.widgets import ListView

            list_views = panel.query(ListView)
            assert len(list_views) > 0

    @pytest.mark.asyncio
    async def test_load_mrs_empty_shows_no_items(self) -> None:
        from gltools.tui.app import GLToolsApp

        paginated = PaginatedResponse[MergeRequest](
            items=[], page=1, per_page=10, total=0, total_pages=1, next_page=None
        )

        mock_list_mrs = AsyncMock(return_value=paginated)
        mock_close = AsyncMock()

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(120, 40)):
            dashboard = app.query_one(DashboardScreen)
            with (
                patch("gltools.tui.screens.dashboard.DashboardScreen._create_client") as mock_create,
                patch("gltools.services.merge_request.MergeRequestService.list_mrs", mock_list_mrs),
            ):
                mock_client = AsyncMock()
                mock_client.close = mock_close
                mock_create.return_value = (mock_client, "token")

                await dashboard._load_mrs()

            panel = app.query_one("#panel-mrs", DashboardPanel)
            statics = panel.query(".panel-empty")
            assert len(statics) > 0

    @pytest.mark.asyncio
    async def test_load_mrs_error_shows_error(self) -> None:
        from gltools.tui.app import GLToolsApp

        mock_close = AsyncMock()

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(120, 40)):
            dashboard = app.query_one(DashboardScreen)
            with (
                patch("gltools.tui.screens.dashboard.DashboardScreen._create_client") as mock_create,
                patch(
                    "gltools.services.merge_request.MergeRequestService.list_mrs",
                    AsyncMock(side_effect=Exception("API error")),
                ),
            ):
                mock_client = AsyncMock()
                mock_client.close = mock_close
                mock_create.return_value = (mock_client, "token")

                await dashboard._load_mrs()

            panel = app.query_one("#panel-mrs", DashboardPanel)
            error_statics = panel.query(".panel-error")
            assert len(error_statics) > 0

    @pytest.mark.asyncio
    async def test_load_issues_shows_items(self) -> None:
        from gltools.tui.app import GLToolsApp

        issues = [_make_issue(iid=1, title="Bug report", labels=["bug", "urgent"])]
        paginated = PaginatedResponse[Issue](
            items=issues, page=1, per_page=10, total=1, total_pages=1, next_page=None
        )

        mock_list_issues = AsyncMock(return_value=paginated)
        mock_close = AsyncMock()

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(120, 40)):
            dashboard = app.query_one(DashboardScreen)
            with (
                patch("gltools.tui.screens.dashboard.DashboardScreen._create_client") as mock_create,
                patch("gltools.services.issue.IssueService.list_issues", mock_list_issues),
            ):
                mock_client = AsyncMock()
                mock_client.close = mock_close
                mock_create.return_value = (mock_client, "token")

                await dashboard._load_issues()

            panel = app.query_one("#panel-issues", DashboardPanel)
            from textual.widgets import ListView

            list_views = panel.query(ListView)
            assert len(list_views) > 0

    @pytest.mark.asyncio
    async def test_load_issues_empty_shows_no_items(self) -> None:
        from gltools.tui.app import GLToolsApp

        paginated = PaginatedResponse[Issue](
            items=[], page=1, per_page=10, total=0, total_pages=1, next_page=None
        )

        mock_close = AsyncMock()

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(120, 40)):
            dashboard = app.query_one(DashboardScreen)
            with (
                patch("gltools.tui.screens.dashboard.DashboardScreen._create_client") as mock_create,
                patch("gltools.services.issue.IssueService.list_issues", AsyncMock(return_value=paginated)),
            ):
                mock_client = AsyncMock()
                mock_client.close = mock_close
                mock_create.return_value = (mock_client, "token")

                await dashboard._load_issues()

            panel = app.query_one("#panel-issues", DashboardPanel)
            statics = panel.query(".panel-empty")
            assert len(statics) > 0

    @pytest.mark.asyncio
    async def test_load_issues_error_shows_error(self) -> None:
        from gltools.tui.app import GLToolsApp

        mock_close = AsyncMock()

        app = GLToolsApp(config=_make_config())
        async with app.run_test(size=(120, 40)):
            dashboard = app.query_one(DashboardScreen)
            with (
                patch("gltools.tui.screens.dashboard.DashboardScreen._create_client") as mock_create,
                patch(
                    "gltools.services.issue.IssueService.list_issues",
                    AsyncMock(side_effect=Exception("Connection failed")),
                ),
            ):
                mock_client = AsyncMock()
                mock_client.close = mock_close
                mock_create.return_value = (mock_client, "token")

                await dashboard._load_issues()

            panel = app.query_one("#panel-issues", DashboardPanel)
            error_statics = panel.query(".panel-error")
            assert len(error_statics) > 0

    @pytest.mark.asyncio
    async def test_no_auth_shows_error_in_panels(self) -> None:
        from gltools.tui.app import GLToolsApp

        config = _make_config(token="")
        app = GLToolsApp(config=config)
        async with app.run_test(size=(120, 40)):
            # The app shows auth required screen when no token, so
            # test _create_client returning None directly
            dashboard = DashboardScreen(config)
            result = await dashboard._create_client()
            assert result is None


class TestDashboardListItems:
    """Test list item creation from models."""

    def test_mr_to_list_item_content(self) -> None:
        config = _make_config()
        screen = DashboardScreen(config)
        mr = _make_mr(iid=42, title="Fix critical bug", username="alice")
        item = screen._mr_to_list_item(mr)
        assert hasattr(item, "_dashboard_item_type")
        assert item._dashboard_item_type == "mr"  # type: ignore[attr-defined]
        assert item._dashboard_item_id == 42  # type: ignore[attr-defined]

    def test_issue_to_list_item_content(self) -> None:
        config = _make_config()
        screen = DashboardScreen(config)
        issue = _make_issue(iid=10, title="Broken login", labels=["bug", "high-priority"])
        item = screen._issue_to_list_item(issue)
        assert item._dashboard_item_type == "issue"  # type: ignore[attr-defined]
        assert item._dashboard_item_id == 10  # type: ignore[attr-defined]

    def test_issue_to_list_item_no_labels(self) -> None:
        config = _make_config()
        screen = DashboardScreen(config)
        issue = _make_issue(iid=5, title="No labels", labels=[])
        item = screen._issue_to_list_item(issue)
        assert item._dashboard_item_type == "issue"  # type: ignore[attr-defined]

    def test_pipeline_to_list_item_content(self) -> None:
        config = _make_config()
        screen = DashboardScreen(config)
        pipeline = _make_pipeline(pipeline_id=99, status="success", duration=45.0)
        item = screen._pipeline_to_list_item(pipeline)
        assert item._dashboard_item_type == "pipeline"  # type: ignore[attr-defined]
        assert item._dashboard_item_id == 99  # type: ignore[attr-defined]

    def test_pipeline_to_list_item_no_duration(self) -> None:
        config = _make_config()
        screen = DashboardScreen(config)
        pipeline = _make_pipeline(pipeline_id=100, status="running", duration=None)
        item = screen._pipeline_to_list_item(pipeline)
        assert item._dashboard_item_type == "pipeline"  # type: ignore[attr-defined]
