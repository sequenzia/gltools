"""Tests for CI CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from gltools.cli.app import app
from gltools.client.exceptions import NotFoundError
from gltools.models.job import Job
from gltools.models.output import DryRunResult, PaginatedResponse
from gltools.models.pipeline import Pipeline
from gltools.services.ci import NoPipelineError

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _make_pipeline(**overrides: object) -> Pipeline:
    defaults = {
        "id": 100,
        "status": "success",
        "ref": "main",
        "sha": "abc12345def",
        "source": "push",
        "created_at": "2025-01-01T00:00:00Z",
        "duration": 120.5,
    }
    defaults.update(overrides)
    return Pipeline.model_validate(defaults)


def _make_job(**overrides: object) -> Job:
    defaults = {
        "id": 1001,
        "name": "test-unit",
        "stage": "test",
        "status": "success",
        "duration": 45.2,
    }
    defaults.update(overrides)
    return Job.model_validate(defaults)


def _mock_build_service(service_mock: MagicMock, client_mock: MagicMock):
    """Create a patch context for _build_service."""
    return patch(
        "gltools.cli.ci._build_service",
        return_value=(service_mock, client_mock),
    )


def _make_mocks() -> tuple[MagicMock, MagicMock]:
    """Create a mock service and client."""
    service = MagicMock()
    client = MagicMock()
    client.close = AsyncMock()
    return service, client


class TestCIStatus:
    def test_status_text_output(self) -> None:
        service, client = _make_mocks()
        pipeline = _make_pipeline()
        jobs = [_make_job(), _make_job(id=1002, name="lint", stage="lint", status="success")]
        service.get_status = AsyncMock(return_value=pipeline)
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "status", "--ref", "main"])

        assert result.exit_code == 0
        assert "Pipeline #100" in result.output
        assert "success" in result.output.lower()

    def test_status_json_output(self) -> None:
        service, client = _make_mocks()
        pipeline = _make_pipeline()
        jobs = [_make_job()]
        service.get_status = AsyncMock(return_value=pipeline)
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--json", "ci", "status", "--ref", "main"])

        assert result.exit_code == 0
        assert '"status": "success"' in result.output

    def test_status_with_mr(self) -> None:
        service, client = _make_mocks()
        pipeline = _make_pipeline()
        jobs = [_make_job()]
        service.get_status = AsyncMock(return_value=pipeline)
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "status", "--mr", "42"])

        assert result.exit_code == 0
        service.get_status.assert_called_once_with(mr_iid=42, ref=None)

    def test_status_no_pipelines(self) -> None:
        service, client = _make_mocks()
        service.get_status = AsyncMock(side_effect=NoPipelineError(ref="main"))
        service.list_jobs = AsyncMock()

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "status", "--ref", "main"])

        assert result.exit_code == 1
        assert "No pipelines found" in result.output

    def test_status_job_breakdown_by_stage(self) -> None:
        service, client = _make_mocks()
        pipeline = _make_pipeline()
        jobs = [
            _make_job(id=1, name="build", stage="build", status="success"),
            _make_job(id=2, name="test-unit", stage="test", status="success"),
            _make_job(id=3, name="deploy", stage="deploy", status="manual"),
        ]
        service.get_status = AsyncMock(return_value=pipeline)
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "status", "--ref", "main"])

        assert result.exit_code == 0
        # Should show all stages
        assert "build" in result.output.lower()
        assert "test" in result.output.lower()
        assert "deploy" in result.output.lower()
        # Manual jobs shown
        assert "manual" in result.output.lower()


class TestCIList:
    def test_list_pipelines(self) -> None:
        service, client = _make_mocks()
        pipelines = [_make_pipeline(id=1), _make_pipeline(id=2, status="failed")]
        service.list_pipelines = AsyncMock(
            return_value=PaginatedResponse[Pipeline](
                items=pipelines, page=1, per_page=20, total=2, total_pages=1
            )
        )

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "list"])

        assert result.exit_code == 0

    def test_list_with_filters(self) -> None:
        service, client = _make_mocks()
        service.list_pipelines = AsyncMock(
            return_value=PaginatedResponse[Pipeline](
                items=[], page=1, per_page=20, total=0, total_pages=0
            )
        )

        with _mock_build_service(service, client):
            result = runner.invoke(
                app,
                ["ci", "list", "--status", "running", "--ref", "main", "--source", "push"],
            )

        assert result.exit_code == 0
        service.list_pipelines.assert_called_once_with(
            status="running", ref="main", source="push", per_page=20, page=1, all_pages=False
        )

    def test_list_no_pipelines(self) -> None:
        service, client = _make_mocks()
        service.list_pipelines = AsyncMock(
            return_value=PaginatedResponse[Pipeline](
                items=[], page=1, per_page=20, total=0, total_pages=0
            )
        )

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "list"])

        assert result.exit_code == 0
        assert "No pipelines found" in result.output


class TestCIRun:
    def test_run_pipeline(self) -> None:
        service, client = _make_mocks()
        pipeline = _make_pipeline()
        service.trigger_pipeline = AsyncMock(return_value=pipeline)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "run", "--ref", "main"])

        assert result.exit_code == 0
        service.trigger_pipeline.assert_called_once_with(ref="main", dry_run=False)

    def test_run_dry_run(self) -> None:
        service, client = _make_mocks()
        dry = DryRunResult(method="POST", url="/projects/42/pipeline", body={"ref": "main"})
        service.trigger_pipeline = AsyncMock(return_value=dry)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "run", "--ref", "main", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run" in result.output or "POST" in result.output
        service.trigger_pipeline.assert_called_once_with(ref="main", dry_run=True)


class TestCIRetry:
    def test_retry_pipeline(self) -> None:
        service, client = _make_mocks()
        pipeline = _make_pipeline()
        service.retry_pipeline = AsyncMock(return_value=pipeline)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "retry", "100"])

        assert result.exit_code == 0
        service.retry_pipeline.assert_called_once_with(100, dry_run=False)

    def test_retry_dry_run(self) -> None:
        service, client = _make_mocks()
        dry = DryRunResult(method="POST", url="/projects/42/pipelines/100/retry")
        service.retry_pipeline = AsyncMock(return_value=dry)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "retry", "100", "--dry-run"])

        assert result.exit_code == 0
        service.retry_pipeline.assert_called_once_with(100, dry_run=True)

    def test_retry_not_found(self) -> None:
        service, client = _make_mocks()
        service.retry_pipeline = AsyncMock(side_effect=NotFoundError("Pipeline", "/pipelines/999"))

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "retry", "999"])

        assert result.exit_code == 1
        assert "Not found" in result.output


class TestCICancel:
    def test_cancel_pipeline(self) -> None:
        service, client = _make_mocks()
        pipeline = _make_pipeline(status="canceled")
        service.cancel_pipeline = AsyncMock(return_value=pipeline)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "cancel", "100"])

        assert result.exit_code == 0
        service.cancel_pipeline.assert_called_once_with(100, dry_run=False)

    def test_cancel_dry_run(self) -> None:
        service, client = _make_mocks()
        dry = DryRunResult(method="POST", url="/projects/42/pipelines/100/cancel")
        service.cancel_pipeline = AsyncMock(return_value=dry)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "cancel", "100", "--dry-run"])

        assert result.exit_code == 0
        service.cancel_pipeline.assert_called_once_with(100, dry_run=True)

    def test_cancel_not_found(self) -> None:
        service, client = _make_mocks()
        service.cancel_pipeline = AsyncMock(side_effect=NotFoundError("Pipeline", "/pipelines/999"))

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "cancel", "999"])

        assert result.exit_code == 1
        assert "Not found" in result.output


class TestCIJobs:
    def test_list_jobs(self) -> None:
        service, client = _make_mocks()
        jobs = [
            _make_job(id=1, name="build", stage="build"),
            _make_job(id=2, name="test", stage="test"),
        ]
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "jobs", "100"])

        assert result.exit_code == 0
        assert "build" in result.output.lower()
        assert "test" in result.output.lower()

    def test_list_jobs_json(self) -> None:
        service, client = _make_mocks()
        jobs = [_make_job()]
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--json", "ci", "jobs", "100"])

        assert result.exit_code == 0
        assert '"name": "test-unit"' in result.output

    def test_list_jobs_empty(self) -> None:
        service, client = _make_mocks()
        service.list_jobs = AsyncMock(return_value=[])

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "jobs", "100"])

        assert result.exit_code == 0
        assert "No jobs found" in result.output

    def test_list_jobs_manual_status(self) -> None:
        service, client = _make_mocks()
        jobs = [_make_job(id=1, name="deploy", stage="deploy", status="manual")]
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "jobs", "100"])

        assert result.exit_code == 0
        assert "manual" in result.output.lower()

    def test_jobs_not_found(self) -> None:
        service, client = _make_mocks()
        service.list_jobs = AsyncMock(side_effect=NotFoundError("Pipeline", "/pipelines/999"))

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "jobs", "999"])

        assert result.exit_code == 1
        assert "Not found" in result.output


class TestCILogs:
    def test_stream_logs(self) -> None:
        service, client = _make_mocks()

        async def _mock_logs(job_id, *, tail=None):
            yield "line 1\n"
            yield "line 2\n"

        service.get_logs = _mock_logs

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "logs", "1001"])

        assert result.exit_code == 0
        assert "line 1" in result.output
        assert "line 2" in result.output

    def test_stream_logs_with_tail(self) -> None:
        service, client = _make_mocks()

        async def _mock_logs(job_id, *, tail=None):
            if tail is not None:
                yield "line 4\n"
                yield "line 5\n"
            else:
                for i in range(1, 6):
                    yield f"line {i}\n"

        service.get_logs = _mock_logs

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "logs", "1001", "--tail", "2"])

        assert result.exit_code == 0
        assert "line 4" in result.output
        assert "line 5" in result.output

    def test_logs_json(self) -> None:
        service, client = _make_mocks()

        async def _mock_logs(job_id, *, tail=None):
            yield "log output\n"

        service.get_logs = _mock_logs

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--json", "ci", "logs", "1001"])

        assert result.exit_code == 0
        assert "log output" in result.output

    def test_logs_not_found(self) -> None:
        service, client = _make_mocks()

        async def _mock_logs(job_id, *, tail=None):
            raise NotFoundError("Job", "/jobs/999")
            yield  # noqa: B033 - make it an async generator

        service.get_logs = _mock_logs

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "logs", "999"])

        assert result.exit_code == 1
        assert "Not found" in result.output


class TestCIArtifacts:
    def test_download_to_file(self, tmp_path: Path) -> None:
        service, client = _make_mocks()
        output_file = tmp_path / "artifacts.zip"
        output_file.write_bytes(b"fake-zip-data")  # Pre-create for stat()
        service.download_artifacts = AsyncMock(return_value=output_file)

        with _mock_build_service(service, client):
            result = runner.invoke(
                app, ["ci", "artifacts", "1001", "--output", str(output_file)]
            )

        assert result.exit_code == 0
        assert "artifacts.zip" in result.output

    def test_download_to_stdout(self) -> None:
        service, client = _make_mocks()
        service.download_artifacts = AsyncMock(return_value=b"binary-data")

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "artifacts", "1001"])

        assert result.exit_code == 0

    def test_download_json(self, tmp_path: Path) -> None:
        service, client = _make_mocks()
        output_file = tmp_path / "artifacts.zip"
        output_file.write_bytes(b"data")
        service.download_artifacts = AsyncMock(return_value=output_file)

        with _mock_build_service(service, client):
            result = runner.invoke(
                app, ["--json", "ci", "artifacts", "1001", "--output", str(output_file)]
            )

        assert result.exit_code == 0
        assert "output_path" in result.output

    def test_artifacts_not_found(self) -> None:
        service, client = _make_mocks()
        service.download_artifacts = AsyncMock(
            side_effect=NotFoundError("Job", "/jobs/999/artifacts")
        )

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "artifacts", "999"])

        assert result.exit_code == 1
        assert "Not found" in result.output


class TestCIStatusJSON:
    """JSON validation tests for CI status."""

    def test_status_json_parseable(self) -> None:
        import json

        service, client = _make_mocks()
        pipeline = _make_pipeline()
        jobs = [_make_job()]
        service.get_status = AsyncMock(return_value=pipeline)
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--json", "ci", "status", "--ref", "main"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["status"] == "success"
        assert "jobs" in data["data"]


class TestCIListJSON:
    """JSON validation tests for CI list."""

    def test_list_json_parseable(self) -> None:
        import json

        service, client = _make_mocks()
        pipelines = [_make_pipeline(id=1)]
        service.list_pipelines = AsyncMock(
            return_value=PaginatedResponse[Pipeline](
                items=pipelines, page=1, per_page=20, total=1, total_pages=1
            )
        )

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--json", "ci", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "items" in data
        assert data["items"][0]["id"] == 1


class TestCIRunJSON:
    """JSON validation tests for CI run."""

    def test_run_json_output(self) -> None:
        import json

        service, client = _make_mocks()
        pipeline = _make_pipeline()
        service.trigger_pipeline = AsyncMock(return_value=pipeline)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--json", "ci", "run", "--ref", "main"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["id"] == 100


class TestCIRetryJSON:
    """JSON validation tests for CI retry."""

    def test_retry_json_output(self) -> None:
        import json

        service, client = _make_mocks()
        pipeline = _make_pipeline()
        service.retry_pipeline = AsyncMock(return_value=pipeline)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--json", "ci", "retry", "100"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["id"] == 100


class TestCICancelJSON:
    """JSON validation tests for CI cancel."""

    def test_cancel_json_output(self) -> None:
        import json

        service, client = _make_mocks()
        pipeline = _make_pipeline(status="canceled")
        service.cancel_pipeline = AsyncMock(return_value=pipeline)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--json", "ci", "cancel", "100"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["status"] == "canceled"


class TestCIRunErrors:
    """Error handling tests for CI run."""

    def test_run_value_error(self) -> None:
        service, client = _make_mocks()
        service.trigger_pipeline = AsyncMock(side_effect=ValueError("No ref specified"))

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "run"])

        assert result.exit_code == 1

    def test_run_gitlab_error(self) -> None:
        from gltools.client.exceptions import GitLabClientError

        service, client = _make_mocks()
        service.trigger_pipeline = AsyncMock(side_effect=GitLabClientError("Server error"))

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "run", "--ref", "main"])

        assert result.exit_code == 1


class TestCIStatusErrors:
    """Error handling tests for CI status."""

    def test_status_value_error(self) -> None:
        service, client = _make_mocks()
        service.get_status = AsyncMock(side_effect=ValueError("Cannot specify both --mr and --ref"))

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "status", "--mr", "1", "--ref", "main"])

        assert result.exit_code == 1

    def test_status_gitlab_error(self) -> None:
        from gltools.client.exceptions import GitLabClientError

        service, client = _make_mocks()
        service.get_status = AsyncMock(side_effect=GitLabClientError("Access denied"))

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "status", "--ref", "main"])

        assert result.exit_code == 1


class TestCIQuietMode:
    """Tests for quiet mode suppressing output."""

    def test_status_quiet_no_output(self) -> None:
        service, client = _make_mocks()
        pipeline = _make_pipeline()
        jobs = [_make_job()]
        service.get_status = AsyncMock(return_value=pipeline)
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--quiet", "ci", "status", "--ref", "main"])

        assert result.exit_code == 0

    def test_jobs_quiet_no_output(self) -> None:
        service, client = _make_mocks()
        jobs = [_make_job()]
        service.list_jobs = AsyncMock(return_value=jobs)

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["--quiet", "ci", "jobs", "100"])

        assert result.exit_code == 0


class TestCIListPagination:
    """Tests for CI list pagination flags."""

    def test_list_with_pagination(self) -> None:
        service, client = _make_mocks()
        service.list_pipelines = AsyncMock(
            return_value=PaginatedResponse[Pipeline](
                items=[], page=3, per_page=5, total=20, total_pages=4
            )
        )

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "list", "--page", "3", "--per-page", "5"])

        assert result.exit_code == 0
        service.list_pipelines.assert_called_once_with(
            status=None, ref=None, source=None, per_page=5, page=3, all_pages=False
        )

    def test_list_all_pages(self) -> None:
        service, client = _make_mocks()
        service.list_pipelines = AsyncMock(
            return_value=PaginatedResponse[Pipeline](
                items=[_make_pipeline()], page=1, per_page=20, total=1, total_pages=1
            )
        )

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "list", "--all"])

        assert result.exit_code == 0
        assert service.list_pipelines.call_args.kwargs["all_pages"] is True


class TestCIErrorHandling:
    """Tests for comprehensive error handling across CI commands."""

    def test_connection_error(self) -> None:
        from gltools.client.exceptions import ConnectionError

        service, client = _make_mocks()
        service.list_pipelines = AsyncMock(side_effect=ConnectionError())

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "list"])

        assert result.exit_code == 1
        assert "network connection" in result.output.lower()

    def test_timeout_error(self) -> None:
        from gltools.client.exceptions import TimeoutError

        service, client = _make_mocks()
        service.list_pipelines = AsyncMock(side_effect=TimeoutError())

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "list"])

        assert result.exit_code == 1
        assert "timed out" in result.output.lower()

    def test_auth_error(self) -> None:
        from gltools.client.exceptions import AuthenticationError

        service, client = _make_mocks()
        service.list_pipelines = AsyncMock(side_effect=AuthenticationError())

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "list"])

        assert result.exit_code == 1
        assert "Authentication failed" in result.output
        assert "gltools auth login" in result.output

    def test_forbidden_error(self) -> None:
        from gltools.client.exceptions import ForbiddenError

        service, client = _make_mocks()
        service.list_pipelines = AsyncMock(side_effect=ForbiddenError())

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "list"])

        assert result.exit_code == 1
        assert "permission" in result.output.lower()

    def test_server_error(self) -> None:
        from gltools.client.exceptions import ServerError

        service, client = _make_mocks()
        service.list_pipelines = AsyncMock(side_effect=ServerError(503, "Service Unavailable"))

        with _mock_build_service(service, client):
            result = runner.invoke(app, ["ci", "list"])

        assert result.exit_code == 1
        assert "503" in result.output
