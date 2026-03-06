"""Tests for CI/CD pipeline status TUI screen."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from gltools.config.settings import GitLabConfig
from gltools.models.job import Job
from gltools.models.pipeline import Pipeline
from gltools.tui.screens.ci_status import (
    AUTO_REFRESH_INTERVAL,
    CIStatusScreen,
    JobLogViewer,
    JobStagePanel,
    PipelineActionBar,
    PipelineActionRequested,
    PipelineListPanel,
    PipelineSelected,
    _format_duration,
)


def _make_config() -> GitLabConfig:
    return GitLabConfig(host="https://gitlab.com", token="test-token", profile="default")


def _make_pipeline(
    pipeline_id: int = 100,
    status: str = "success",
    ref: str = "main",
    source: str = "push",
    duration: float | None = 120.0,
) -> Pipeline:
    return Pipeline(
        id=pipeline_id,
        status=status,
        ref=ref,
        sha="abc123def456",
        source=source,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        finished_at=datetime(2026, 1, 1, 0, 2, tzinfo=UTC) if duration else None,
        duration=duration,
    )


def _make_job(
    job_id: int = 1,
    name: str = "test",
    stage: str = "test",
    status: str = "success",
    duration: float | None = 30.0,
    failure_reason: str | None = None,
) -> Job:
    return Job(
        id=job_id,
        name=name,
        stage=stage,
        status=status,
        duration=duration,
        failure_reason=failure_reason,
    )


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestFormatDuration:
    """Test the _format_duration helper."""

    def test_none_returns_dash(self) -> None:
        assert _format_duration(None) == "-"

    def test_seconds_only(self) -> None:
        assert _format_duration(45.0) == "45s"

    def test_minutes_and_seconds(self) -> None:
        assert _format_duration(125.0) == "2m 5s"

    def test_zero(self) -> None:
        assert _format_duration(0.0) == "0s"


# ---------------------------------------------------------------------------
# Message tests
# ---------------------------------------------------------------------------


class TestMessages:
    """Test CI status message types."""

    def test_pipeline_selected(self) -> None:
        msg = PipelineSelected(42)
        assert msg.pipeline_id == 42

    def test_pipeline_action_retry(self) -> None:
        msg = PipelineActionRequested("retry", 42)
        assert msg.action == "retry"
        assert msg.pipeline_id == 42

    def test_pipeline_action_cancel(self) -> None:
        msg = PipelineActionRequested("cancel", 100)
        assert msg.action == "cancel"
        assert msg.pipeline_id == 100

    def test_pipeline_action_trigger(self) -> None:
        msg = PipelineActionRequested("trigger", 0)
        assert msg.action == "trigger"


# ---------------------------------------------------------------------------
# PipelineListPanel tests
# ---------------------------------------------------------------------------


class PipelineListApp(App[None]):
    def compose(self) -> ComposeResult:
        yield PipelineListPanel(id="pipeline-list-panel")


class TestPipelineListPanel:
    """Test the pipeline list panel."""

    @pytest.mark.asyncio
    async def test_renders(self) -> None:
        app = PipelineListApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#pipeline-list-panel", PipelineListPanel)
            assert panel is not None

    @pytest.mark.asyncio
    async def test_has_table(self) -> None:
        app = PipelineListApp()
        async with app.run_test(size=(120, 30)):
            table = app.query_one("#pipeline-table", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    async def test_table_columns(self) -> None:
        app = PipelineListApp()
        async with app.run_test(size=(120, 30)):
            table = app.query_one("#pipeline-table", DataTable)
            column_keys = [col.key.value for col in table.columns.values()]
            assert "id" in column_keys
            assert "status" in column_keys
            assert "ref" in column_keys
            assert "source" in column_keys
            assert "duration" in column_keys
            assert "created" in column_keys

    @pytest.mark.asyncio
    async def test_populate_with_pipelines(self) -> None:
        app = PipelineListApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#pipeline-list-panel", PipelineListPanel)
            pipelines = [_make_pipeline(100), _make_pipeline(101, status="failed")]
            panel.populate(pipelines)
            table = app.query_one("#pipeline-table", DataTable)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_populate_empty_shows_message(self) -> None:
        app = PipelineListApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#pipeline-list-panel", PipelineListPanel)
            panel.populate([])
            no_msg = app.query_one("#no-pipelines-msg", Static)
            assert no_msg.display is True

    @pytest.mark.asyncio
    async def test_has_running_pipelines_true(self) -> None:
        app = PipelineListApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#pipeline-list-panel", PipelineListPanel)
            panel.populate([_make_pipeline(100, status="running")])
            assert panel.has_running_pipelines() is True

    @pytest.mark.asyncio
    async def test_has_running_pipelines_false(self) -> None:
        app = PipelineListApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#pipeline-list-panel", PipelineListPanel)
            panel.populate([_make_pipeline(100, status="success")])
            assert panel.has_running_pipelines() is False

    @pytest.mark.asyncio
    async def test_pipeline_without_duration(self) -> None:
        app = PipelineListApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#pipeline-list-panel", PipelineListPanel)
            panel.populate([_make_pipeline(100, duration=None)])
            table = app.query_one("#pipeline-table", DataTable)
            assert table.row_count == 1


# ---------------------------------------------------------------------------
# JobStagePanel tests
# ---------------------------------------------------------------------------


class JobStagePanelApp(App[None]):
    def compose(self) -> ComposeResult:
        yield JobStagePanel(id="job-stage-panel")


class TestJobStagePanel:
    """Test the job stage panel."""

    @pytest.mark.asyncio
    async def test_renders(self) -> None:
        app = JobStagePanelApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#job-stage-panel", JobStagePanel)
            assert panel is not None

    @pytest.mark.asyncio
    async def test_populate_with_jobs(self) -> None:
        app = JobStagePanelApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#job-stage-panel", JobStagePanel)
            jobs = [
                _make_job(1, "build", "build"),
                _make_job(2, "unit-test", "test"),
                _make_job(3, "lint", "test"),
            ]
            panel.populate(jobs, pipeline_id=100)
            # Scroll should be visible
            scroll = panel.query_one("#job-stage-scroll")
            assert scroll.display is True

    @pytest.mark.asyncio
    async def test_populate_empty(self) -> None:
        app = JobStagePanelApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#job-stage-panel", JobStagePanel)
            panel.populate([])
            no_msg = panel.query_one("#no-jobs-msg", Static)
            assert no_msg.display is True

    @pytest.mark.asyncio
    async def test_manual_job_shown(self) -> None:
        app = JobStagePanelApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#job-stage-panel", JobStagePanel)
            jobs = [_make_job(1, "deploy", "deploy", status="manual")]
            panel.populate(jobs, pipeline_id=100)
            scroll = panel.query_one("#job-stage-scroll")
            assert scroll.display is True

    @pytest.mark.asyncio
    async def test_failed_job_with_reason(self) -> None:
        app = JobStagePanelApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#job-stage-panel", JobStagePanel)
            jobs = [_make_job(1, "test", "test", status="failed", failure_reason="script_failure")]
            panel.populate(jobs, pipeline_id=100)
            scroll = panel.query_one("#job-stage-scroll")
            assert scroll.display is True

    def test_get_job_by_name(self) -> None:
        panel = JobStagePanel()
        panel._jobs = [_make_job(1, "build", "build"), _make_job(2, "test", "test")]
        assert panel.get_job_by_name("build") is not None
        assert panel.get_job_by_name("build").id == 1  # type: ignore[union-attr]
        assert panel.get_job_by_name("nonexistent") is None


# ---------------------------------------------------------------------------
# JobLogViewer tests
# ---------------------------------------------------------------------------


class JobLogApp(App[None]):
    def compose(self) -> ComposeResult:
        yield JobLogViewer(id="job-log-viewer")


class TestJobLogViewer:
    """Test the job log viewer."""

    @pytest.mark.asyncio
    async def test_renders(self) -> None:
        app = JobLogApp()
        async with app.run_test(size=(120, 30)):
            viewer = app.query_one("#job-log-viewer", JobLogViewer)
            assert viewer is not None

    @pytest.mark.asyncio
    async def test_set_log(self) -> None:
        app = JobLogApp()
        async with app.run_test(size=(120, 30)):
            viewer = app.query_one("#job-log-viewer", JobLogViewer)
            viewer.set_log("Line 1\nLine 2\nLine 3", job_id=42)
            assert viewer._log_content == "Line 1\nLine 2\nLine 3"
            assert viewer._job_id == 42

    @pytest.mark.asyncio
    async def test_set_empty_log(self) -> None:
        app = JobLogApp()
        async with app.run_test(size=(120, 30)):
            viewer = app.query_one("#job-log-viewer", JobLogViewer)
            viewer.set_log("")
            placeholders = app.query(".log-placeholder")
            assert len(placeholders) > 0

    @pytest.mark.asyncio
    async def test_append_log(self) -> None:
        app = JobLogApp()
        async with app.run_test(size=(120, 30)):
            viewer = app.query_one("#job-log-viewer", JobLogViewer)
            viewer.set_log("Line 1\n")
            viewer.append_log("Line 2\n")
            assert "Line 1" in viewer._log_content
            assert "Line 2" in viewer._log_content

    @pytest.mark.asyncio
    async def test_clear_log(self) -> None:
        app = JobLogApp()
        async with app.run_test(size=(120, 30)):
            viewer = app.query_one("#job-log-viewer", JobLogViewer)
            viewer.set_log("Some log content", job_id=42)
            viewer.clear_log()
            assert viewer._log_content == ""
            assert viewer._job_id is None

    @pytest.mark.asyncio
    async def test_large_log_scrollable(self) -> None:
        app = JobLogApp()
        async with app.run_test(size=(120, 30)):
            viewer = app.query_one("#job-log-viewer", JobLogViewer)
            large_log = "\n".join([f"Log line {i}" for i in range(500)])
            viewer.set_log(large_log)
            assert "Log line 499" in viewer._log_content


# ---------------------------------------------------------------------------
# PipelineActionBar tests
# ---------------------------------------------------------------------------


class ActionBarApp(App[None]):
    def __init__(self, pipeline_id: int | None = None, status: str = "") -> None:
        super().__init__()
        self._pid = pipeline_id
        self._status = status

    def compose(self) -> ComposeResult:
        yield PipelineActionBar(self._pid, self._status, id="pipeline-action-bar")


class TestPipelineActionBar:
    """Test pipeline action bar."""

    @pytest.mark.asyncio
    async def test_trigger_always_shown(self) -> None:
        app = ActionBarApp()
        async with app.run_test(size=(120, 30)):
            trigger_btn = app.query(".btn-trigger")
            assert len(trigger_btn) > 0

    @pytest.mark.asyncio
    async def test_retry_shown_for_failed(self) -> None:
        app = ActionBarApp(42, "failed")
        async with app.run_test(size=(120, 30)):
            retry_btn = app.query(".btn-retry")
            assert len(retry_btn) > 0

    @pytest.mark.asyncio
    async def test_cancel_shown_for_running(self) -> None:
        app = ActionBarApp(42, "running")
        async with app.run_test(size=(120, 30)):
            cancel_btn = app.query(".btn-cancel")
            assert len(cancel_btn) > 0

    @pytest.mark.asyncio
    async def test_no_retry_for_success(self) -> None:
        app = ActionBarApp(42, "success")
        async with app.run_test(size=(120, 30)):
            retry_btn = app.query(".btn-retry")
            assert len(retry_btn) == 0

    @pytest.mark.asyncio
    async def test_no_cancel_for_success(self) -> None:
        app = ActionBarApp(42, "success")
        async with app.run_test(size=(120, 30)):
            cancel_btn = app.query(".btn-cancel")
            assert len(cancel_btn) == 0

    @pytest.mark.asyncio
    async def test_update_pipeline(self) -> None:
        app = ActionBarApp()
        async with app.run_test(size=(120, 30)) as pilot:
            action_bar = app.query_one("#pipeline-action-bar", PipelineActionBar)
            action_bar.update_pipeline(99, "failed")
            await pilot.pause()
            await pilot.pause()
            retry_btn = app.query(".btn-retry")
            assert len(retry_btn) > 0


# ---------------------------------------------------------------------------
# CIStatusScreen tests
# ---------------------------------------------------------------------------


class CIStatusApp(App[None]):
    def __init__(self, config: GitLabConfig | None = None) -> None:
        super().__init__()
        self._config = config or _make_config()

    def compose(self) -> ComposeResult:
        yield CIStatusScreen(self._config, id="ci-status")


class TestCIStatusScreen:
    """Test the main CI status screen."""

    @pytest.mark.asyncio
    async def test_renders(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            assert screen is not None

    @pytest.mark.asyncio
    async def test_has_pipeline_list_panel(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#pipeline-list-panel", PipelineListPanel)
            assert panel is not None

    @pytest.mark.asyncio
    async def test_has_job_stage_panel(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            panel = app.query_one("#job-stage-panel", JobStagePanel)
            assert panel is not None

    @pytest.mark.asyncio
    async def test_has_log_viewer(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            viewer = app.query_one("#job-log-viewer", JobLogViewer)
            assert viewer is not None

    @pytest.mark.asyncio
    async def test_has_action_bar(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            action_bar = app.query_one("#pipeline-action-bar", PipelineActionBar)
            assert action_bar is not None

    @pytest.mark.asyncio
    async def test_set_pipelines(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            pipelines = [_make_pipeline(100), _make_pipeline(101, status="running")]
            screen.set_pipelines(pipelines)
            table = app.query_one("#pipeline-table", DataTable)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_set_pipelines_empty(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            screen.set_pipelines([])
            no_msg = app.query_one("#no-pipelines-msg", Static)
            assert no_msg.display is True

    @pytest.mark.asyncio
    async def test_set_jobs(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            jobs = [_make_job(1, "build", "build"), _make_job(2, "test", "test")]
            screen.set_jobs(jobs, pipeline_id=100)
            stage_panel = app.query_one("#job-stage-panel", JobStagePanel)
            assert len(stage_panel._jobs) == 2

    @pytest.mark.asyncio
    async def test_set_job_log(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            screen.set_job_log("Build output here", job_id=1)
            viewer = app.query_one("#job-log-viewer", JobLogViewer)
            assert viewer._log_content == "Build output here"

    @pytest.mark.asyncio
    async def test_bindings_defined(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            binding_keys = [b.key for b in screen.BINDINGS]
            assert "r" in binding_keys
            assert "enter" in binding_keys
            assert "escape" in binding_keys
            assert "l" in binding_keys

    @pytest.mark.asyncio
    async def test_auto_refresh_starts_for_running(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            screen.set_pipelines([_make_pipeline(100, status="running")])
            assert screen._auto_refresh_timer is not None

    @pytest.mark.asyncio
    async def test_auto_refresh_stops_when_all_complete(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            screen.set_pipelines([_make_pipeline(100, status="running")])
            assert screen._auto_refresh_timer is not None
            screen.set_pipelines([_make_pipeline(100, status="success")])
            assert screen._auto_refresh_timer is None

    @pytest.mark.asyncio
    async def test_action_go_back_clears_detail(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            screen.set_jobs([_make_job()], pipeline_id=100)
            screen.set_job_log("some log")
            screen.action_go_back()
            viewer = app.query_one("#job-log-viewer", JobLogViewer)
            assert viewer._log_content == ""
            assert screen._selected_pipeline_id is None

    @pytest.mark.asyncio
    async def test_auto_refresh_interval_constant(self) -> None:
        assert AUTO_REFRESH_INTERVAL == 10.0

    @pytest.mark.asyncio
    async def test_action_refresh(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            screen.action_refresh()

    @pytest.mark.asyncio
    async def test_action_select_pipeline(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            screen.set_pipelines([_make_pipeline(100)])
            screen.action_select_pipeline()

    @pytest.mark.asyncio
    async def test_pipeline_selection_updates_action_bar(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            pipelines = [_make_pipeline(100, status="failed")]
            screen.set_pipelines(pipelines)
            screen._on_pipeline_selected(PipelineSelected(100))
            assert screen._selected_pipeline_id == 100
            assert screen._selected_pipeline_status == "failed"

    @pytest.mark.asyncio
    async def test_on_unmount_stops_auto_refresh(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            screen.set_pipelines([_make_pipeline(100, status="running")])
            assert screen._auto_refresh_timer is not None
            screen.on_unmount()
            assert screen._auto_refresh_timer is None

    @pytest.mark.asyncio
    async def test_set_jobs_then_go_back_clears_selection(self) -> None:
        app = CIStatusApp()
        async with app.run_test(size=(120, 30)):
            screen = app.query_one("#ci-status", CIStatusScreen)
            screen.set_jobs([_make_job(1, "build", "build")], pipeline_id=100)
            screen._selected_pipeline_id = 100
            screen.action_go_back()
            assert screen._selected_pipeline_id is None
            assert len(screen.query_one("#job-stage-panel", JobStagePanel)._jobs) == 0


# ---------------------------------------------------------------------------
# Pipeline action button press tests
# ---------------------------------------------------------------------------


class TestPipelineActionButtonPress:
    """Test pipeline action bar button press events."""

    @pytest.mark.asyncio
    async def test_retry_button_posts_action(self) -> None:
        from textual.widgets import Button

        app = ActionBarApp(42, "failed")
        messages: list[PipelineActionRequested] = []
        async with app.run_test(size=(120, 30)) as pilot:
            action_bar = app.query_one("#pipeline-action-bar", PipelineActionBar)
            original_post = action_bar.post_message
            action_bar.post_message = lambda msg: messages.append(msg) or original_post(msg)  # type: ignore[assignment]
            retry_btn = app.query_one(".btn-retry", Button)
            retry_btn.press()
            await pilot.pause()
            await pilot.pause()
            action_msgs = [m for m in messages if isinstance(m, PipelineActionRequested)]
            assert len(action_msgs) >= 1
            assert action_msgs[0].action == "retry"
            assert action_msgs[0].pipeline_id == 42

    @pytest.mark.asyncio
    async def test_cancel_button_posts_action(self) -> None:
        from textual.widgets import Button

        app = ActionBarApp(42, "running")
        messages: list[PipelineActionRequested] = []
        async with app.run_test(size=(120, 30)) as pilot:
            action_bar = app.query_one("#pipeline-action-bar", PipelineActionBar)
            original_post = action_bar.post_message
            action_bar.post_message = lambda msg: messages.append(msg) or original_post(msg)  # type: ignore[assignment]
            cancel_btn = app.query_one(".btn-cancel", Button)
            cancel_btn.press()
            await pilot.pause()
            await pilot.pause()
            action_msgs = [m for m in messages if isinstance(m, PipelineActionRequested)]
            assert len(action_msgs) >= 1
            assert action_msgs[0].action == "cancel"

    @pytest.mark.asyncio
    async def test_trigger_button_posts_action(self) -> None:
        from textual.widgets import Button

        app = ActionBarApp()
        messages: list[PipelineActionRequested] = []
        async with app.run_test(size=(120, 30)) as pilot:
            action_bar = app.query_one("#pipeline-action-bar", PipelineActionBar)
            original_post = action_bar.post_message
            action_bar.post_message = lambda msg: messages.append(msg) or original_post(msg)  # type: ignore[assignment]
            trigger_btn = app.query_one(".btn-trigger", Button)
            trigger_btn.press()
            await pilot.pause()
            await pilot.pause()
            action_msgs = [m for m in messages if isinstance(m, PipelineActionRequested)]
            assert len(action_msgs) >= 1
            assert action_msgs[0].action == "trigger"
