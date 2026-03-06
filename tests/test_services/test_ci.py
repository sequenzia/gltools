"""Tests for the CI service layer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gltools.models import DryRunResult, MergeRequest, PaginatedResponse, Pipeline
from gltools.models.job import Job
from gltools.services.ci import CIService, NoPipelineError, _get_current_branch


def _make_pipeline(**overrides: object) -> Pipeline:
    """Create a minimal Pipeline for testing."""
    defaults = {
        "id": 100,
        "status": "success",
        "ref": "main",
        "sha": "abc123",
        "source": "push",
        "created_at": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return Pipeline.model_validate(defaults)


def _make_job(**overrides: object) -> Job:
    """Create a minimal Job for testing."""
    defaults = {
        "id": 1001,
        "name": "test",
        "stage": "test",
        "status": "success",
    }
    defaults.update(overrides)
    return Job.model_validate(defaults)


def _make_mr(**overrides: object) -> MergeRequest:
    """Create a minimal MergeRequest for testing."""
    defaults = {
        "id": 1,
        "iid": 10,
        "title": "Test MR",
        "state": "opened",
        "source_branch": "feature",
        "target_branch": "main",
        "author": {"id": 1, "username": "user", "name": "User"},
        "labels": [],
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return MergeRequest.model_validate(defaults)


def _make_service() -> tuple[CIService, MagicMock, MagicMock, MagicMock]:
    """Create a CIService with mock managers."""
    pipeline_mgr = MagicMock()
    pipeline_mgr.list = AsyncMock()
    pipeline_mgr.get = AsyncMock()
    pipeline_mgr.create = AsyncMock()
    pipeline_mgr.retry = AsyncMock()
    pipeline_mgr.cancel = AsyncMock()

    job_mgr = MagicMock()
    job_mgr.list = AsyncMock()
    job_mgr.logs = MagicMock()
    job_mgr.artifacts = MagicMock()

    mr_mgr = MagicMock()
    mr_mgr.get = AsyncMock()

    service = CIService(
        project_id=42,
        pipeline_manager=pipeline_mgr,
        job_manager=job_mgr,
        mr_manager=mr_mgr,
    )
    return service, pipeline_mgr, job_mgr, mr_mgr


class TestGetCurrentBranch:
    def test_returns_branch_name(self) -> None:
        with patch("gltools.services.ci.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="feature-branch\n")
            assert _get_current_branch() == "feature-branch"

    def test_returns_none_on_detached_head(self) -> None:
        with patch("gltools.services.ci.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="HEAD\n")
            assert _get_current_branch() is None

    def test_returns_none_on_failure(self) -> None:
        with patch("gltools.services.ci.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            assert _get_current_branch() is None

    def test_returns_none_when_git_not_found(self) -> None:
        with patch("gltools.services.ci.subprocess.run", side_effect=FileNotFoundError):
            assert _get_current_branch() is None


class TestGetStatus:
    async def test_get_status_by_ref(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        pipeline = _make_pipeline()
        pipeline_mgr.list.return_value = PaginatedResponse[Pipeline](
            items=[pipeline], page=1, per_page=1, total=1, total_pages=1
        )
        pipeline_mgr.get.return_value = pipeline

        result = await service.get_status(ref="main")

        assert result.id == 100
        pipeline_mgr.list.assert_called_once_with(42, ref="main", per_page=1, page=1)
        pipeline_mgr.get.assert_called_once_with(42, 100)

    async def test_get_status_uses_current_branch(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        pipeline = _make_pipeline(ref="feature")
        pipeline_mgr.list.return_value = PaginatedResponse[Pipeline](
            items=[pipeline], page=1, per_page=1, total=1, total_pages=1
        )
        pipeline_mgr.get.return_value = pipeline

        with patch("gltools.services.ci._get_current_branch", return_value="feature"):
            result = await service.get_status()

        assert result.id == 100
        pipeline_mgr.list.assert_called_once_with(42, ref="feature", per_page=1, page=1)

    async def test_get_status_no_pipelines_raises(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        pipeline_mgr.list.return_value = PaginatedResponse[Pipeline](
            items=[], page=1, per_page=1, total=0, total_pages=0
        )

        with pytest.raises(NoPipelineError, match="No pipelines found for branch 'main'"):
            await service.get_status(ref="main")

    async def test_get_status_no_branch_raises(self) -> None:
        service, _, _, _ = _make_service()

        with (
            patch("gltools.services.ci._get_current_branch", return_value=None),
            pytest.raises(ValueError, match="Cannot determine current branch"),
        ):
            await service.get_status()

    async def test_get_status_from_mr(self) -> None:
        service, pipeline_mgr, _, mr_mgr = _make_service()
        mr = _make_mr(pipeline={"id": 200, "status": "success", "web_url": "http://x"})
        mr_mgr.get.return_value = mr
        pipeline = _make_pipeline(id=200)
        pipeline_mgr.get.return_value = pipeline

        result = await service.get_status(mr_iid=10)

        assert result.id == 200
        mr_mgr.get.assert_called_once_with(42, 10)
        pipeline_mgr.get.assert_called_once_with(42, 200)

    async def test_get_status_from_mr_no_pipeline(self) -> None:
        service, _, _, mr_mgr = _make_service()
        mr = _make_mr(pipeline=None)
        mr_mgr.get.return_value = mr

        with pytest.raises(NoPipelineError, match="merge request !10"):
            await service.get_status(mr_iid=10)


class TestListPipelines:
    async def test_list_pipelines_passes_filters(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        pipeline_mgr.list.return_value = PaginatedResponse[Pipeline](
            items=[], page=1, per_page=20, total=0, total_pages=0
        )

        await service.list_pipelines(status="running", ref="main", source="push")

        pipeline_mgr.list.assert_called_once_with(
            42, status="running", ref="main", source="push", per_page=20, page=1
        )

    async def test_list_all_pages(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        p1 = _make_pipeline(id=1)
        p2 = _make_pipeline(id=2)

        pipeline_mgr.list.side_effect = [
            PaginatedResponse[Pipeline](
                items=[p1], page=1, per_page=1, total=2, total_pages=2, next_page=2
            ),
            PaginatedResponse[Pipeline](
                items=[p2], page=2, per_page=1, total=2, total_pages=2, next_page=None
            ),
        ]

        result = await service.list_pipelines(all_pages=True, per_page=1)

        assert len(result.items) == 2
        assert result.items[0].id == 1
        assert result.items[1].id == 2


class TestTriggerPipeline:
    async def test_trigger_creates_pipeline(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        pipeline = _make_pipeline()
        pipeline_mgr.create.return_value = pipeline

        result = await service.trigger_pipeline(ref="main")

        assert isinstance(result, Pipeline)
        pipeline_mgr.create.assert_called_once_with(42, ref="main")

    async def test_trigger_dry_run(self) -> None:
        service, _, _, _ = _make_service()

        result = await service.trigger_pipeline(ref="main", dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.dry_run is True
        assert result.method == "POST"
        assert "pipeline" in result.url
        assert result.body == {"ref": "main"}

    async def test_trigger_uses_current_branch(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        pipeline_mgr.create.return_value = _make_pipeline()

        with patch("gltools.services.ci._get_current_branch", return_value="develop"):
            await service.trigger_pipeline()

        pipeline_mgr.create.assert_called_once_with(42, ref="develop")

    async def test_trigger_no_branch_raises(self) -> None:
        service, _, _, _ = _make_service()

        with (
            patch("gltools.services.ci._get_current_branch", return_value=None),
            pytest.raises(ValueError, match="Cannot determine current branch"),
        ):
            await service.trigger_pipeline()


class TestRetryPipeline:
    async def test_retry_calls_manager(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        pipeline_mgr.retry.return_value = _make_pipeline()

        result = await service.retry_pipeline(100)

        assert isinstance(result, Pipeline)
        pipeline_mgr.retry.assert_called_once_with(42, 100)

    async def test_retry_dry_run(self) -> None:
        service, _, _, _ = _make_service()

        result = await service.retry_pipeline(100, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.method == "POST"
        assert "retry" in result.url


class TestCancelPipeline:
    async def test_cancel_calls_manager(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        pipeline_mgr.cancel.return_value = _make_pipeline(status="canceled")

        result = await service.cancel_pipeline(100)

        assert isinstance(result, Pipeline)
        assert result.status == "canceled"
        pipeline_mgr.cancel.assert_called_once_with(42, 100)

    async def test_cancel_dry_run(self) -> None:
        service, _, _, _ = _make_service()

        result = await service.cancel_pipeline(100, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert "cancel" in result.url


class TestListJobs:
    async def test_list_jobs(self) -> None:
        service, _, job_mgr, _ = _make_service()
        jobs = [_make_job(id=1), _make_job(id=2)]
        job_mgr.list.return_value = jobs

        result = await service.list_jobs(100)

        assert len(result) == 2
        job_mgr.list.assert_called_once_with(42, 100)


class TestGetLogs:
    async def test_streaming_logs(self) -> None:
        service, _, job_mgr, _ = _make_service()

        async def _mock_stream():
            yield b"line 1\n"
            yield b"line 2\n"

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_mock_stream())
        ctx.__aexit__ = AsyncMock(return_value=False)
        job_mgr.logs.return_value = ctx

        chunks = []
        async for chunk in service.get_logs(1001):
            chunks.append(chunk)

        assert chunks == ["line 1\n", "line 2\n"]

    async def test_streaming_logs_with_tail(self) -> None:
        service, _, job_mgr, _ = _make_service()

        async def _mock_stream():
            yield b"line 1\nline 2\nline 3\nline 4\nline 5\n"

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_mock_stream())
        ctx.__aexit__ = AsyncMock(return_value=False)
        job_mgr.logs.return_value = ctx

        lines = []
        async for line in service.get_logs(1001, tail=2):
            lines.append(line)

        assert lines == ["line 4\n", "line 5\n"]

    async def test_tail_with_large_stream(self) -> None:
        """Tail with many chunks - only last N lines kept in memory."""
        service, _, job_mgr, _ = _make_service()

        async def _mock_stream():
            for i in range(100):
                yield f"line {i}\n".encode()

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_mock_stream())
        ctx.__aexit__ = AsyncMock(return_value=False)
        job_mgr.logs.return_value = ctx

        lines = []
        async for line in service.get_logs(1001, tail=3):
            lines.append(line)

        assert len(lines) == 3
        assert lines[0] == "line 97\n"
        assert lines[1] == "line 98\n"
        assert lines[2] == "line 99\n"


class TestDownloadArtifacts:
    async def test_download_to_bytes(self) -> None:
        service, _, job_mgr, _ = _make_service()

        async def _mock_stream():
            yield b"chunk1"
            yield b"chunk2"

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_mock_stream())
        ctx.__aexit__ = AsyncMock(return_value=False)
        job_mgr.artifacts.return_value = ctx

        result = await service.download_artifacts(1001)

        assert isinstance(result, bytes)
        assert result == b"chunk1chunk2"

    async def test_download_to_file(self, tmp_path: Path) -> None:
        service, _, job_mgr, _ = _make_service()

        async def _mock_stream():
            yield b"file-content"

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_mock_stream())
        ctx.__aexit__ = AsyncMock(return_value=False)
        job_mgr.artifacts.return_value = ctx

        output = tmp_path / "artifacts.zip"
        result = await service.download_artifacts(1001, output_path=output)

        assert isinstance(result, Path)
        assert result == output
        assert output.read_bytes() == b"file-content"


class TestNoPipelineError:
    def test_message_for_branch(self) -> None:
        err = NoPipelineError(ref="develop")
        assert "branch 'develop'" in str(err)

    def test_message_for_mr(self) -> None:
        err = NoPipelineError(mr_iid=42)
        assert "merge request !42" in str(err)

    def test_message_generic(self) -> None:
        err = NoPipelineError()
        assert str(err) == "No pipelines found"


class TestGetCurrentBranchEdgeCases:
    def test_returns_none_on_timeout(self) -> None:
        import subprocess

        with patch("gltools.services.ci.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5)):
            assert _get_current_branch() is None

    def test_returns_none_on_empty_output(self) -> None:
        with patch("gltools.services.ci.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            assert _get_current_branch() is None


class TestGetLogsEdgeCases:
    async def test_tail_with_partial_line_no_trailing_newline(self) -> None:
        """Tail handles streams that don't end with a newline."""
        service, _, job_mgr, _ = _make_service()

        async def _mock_stream():
            yield b"line 1\nline 2\npartial"

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_mock_stream())
        ctx.__aexit__ = AsyncMock(return_value=False)
        job_mgr.logs.return_value = ctx

        lines = []
        async for line in service.get_logs(1001, tail=2):
            lines.append(line)

        assert lines == ["line 2\n", "partial\n"]

    async def test_tail_zero_lines(self) -> None:
        """Requesting tail=0 returns nothing from deque(maxlen=0)."""
        service, _, job_mgr, _ = _make_service()

        async def _mock_stream():
            yield b"line 1\nline 2\n"

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_mock_stream())
        ctx.__aexit__ = AsyncMock(return_value=False)
        job_mgr.logs.return_value = ctx

        lines = []
        async for line in service.get_logs(1001, tail=0):
            lines.append(line)

        assert lines == []

    async def test_tail_more_than_available(self) -> None:
        """Requesting more tail lines than available returns all lines."""
        service, _, job_mgr, _ = _make_service()

        async def _mock_stream():
            yield b"a\nb\n"

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_mock_stream())
        ctx.__aexit__ = AsyncMock(return_value=False)
        job_mgr.logs.return_value = ctx

        lines = []
        async for line in service.get_logs(1001, tail=100):
            lines.append(line)

        assert lines == ["a\n", "b\n"]


class TestListPipelinesEdgeCases:
    async def test_all_pages_empty_result(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        pipeline_mgr.list.return_value = PaginatedResponse[Pipeline](
            items=[], page=1, per_page=20, total=0, total_pages=1, next_page=None
        )

        result = await service.list_pipelines(all_pages=True)

        assert len(result.items) == 0
        assert result.total == 0

    async def test_all_pages_single_page(self) -> None:
        service, pipeline_mgr, _, _ = _make_service()
        p = _make_pipeline()
        pipeline_mgr.list.return_value = PaginatedResponse[Pipeline](
            items=[p], page=1, per_page=20, total=1, total_pages=1, next_page=None
        )

        result = await service.list_pipelines(all_pages=True)

        assert len(result.items) == 1
        assert result.next_page is None
        assert pipeline_mgr.list.call_count == 1


class TestTriggerPipelineDryRunDetails:
    async def test_dry_run_includes_project_id_in_url(self) -> None:
        service, _, _, _ = _make_service()

        result = await service.trigger_pipeline(ref="main", dry_run=True)

        assert isinstance(result, DryRunResult)
        assert "42" in result.url
        assert "pipeline" in result.url

    async def test_dry_run_uses_current_branch(self) -> None:
        service, _, _, _ = _make_service()

        with patch("gltools.services.ci._get_current_branch", return_value="develop"):
            result = await service.trigger_pipeline(dry_run=True)

        assert isinstance(result, DryRunResult)
        assert result.body == {"ref": "develop"}

    async def test_dry_run_no_branch_raises(self) -> None:
        service, _, _, _ = _make_service()

        with (
            patch("gltools.services.ci._get_current_branch", return_value=None),
            pytest.raises(ValueError, match="Cannot determine current branch"),
        ):
            await service.trigger_pipeline(dry_run=True)


class TestRetryPipelineDryRunDetails:
    async def test_dry_run_includes_pipeline_id_in_url(self) -> None:
        service, _, _, _ = _make_service()

        result = await service.retry_pipeline(999, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert "999" in result.url
        assert "retry" in result.url


class TestCancelPipelineDryRunDetails:
    async def test_dry_run_includes_pipeline_id_in_url(self) -> None:
        service, _, _, _ = _make_service()

        result = await service.cancel_pipeline(888, dry_run=True)

        assert isinstance(result, DryRunResult)
        assert "888" in result.url
        assert "cancel" in result.url


class TestDownloadArtifactsEdgeCases:
    async def test_download_to_bytes_empty_stream(self) -> None:
        service, _, job_mgr, _ = _make_service()

        async def _mock_stream():
            return
            yield  # noqa: RET504 - make it an async generator

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_mock_stream())
        ctx.__aexit__ = AsyncMock(return_value=False)
        job_mgr.artifacts.return_value = ctx

        result = await service.download_artifacts(1001)

        assert isinstance(result, bytes)
        assert result == b""
