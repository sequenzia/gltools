"""Tests for service layer execution trace logging."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gltools.models import DryRunResult, Issue, MergeRequest, PaginatedResponse
from gltools.models.pipeline import Pipeline
from gltools.services.ci import CIService
from gltools.services.issue import IssueService
from gltools.services.merge_request import MergeRequestService, ProjectResolutionError


@pytest.fixture(autouse=True)
def _reset_logger_propagation() -> None:
    """Ensure gltools loggers propagate so caplog can capture them.

    Other tests (e.g., test_logging.py) call setup_logging() which sets
    propagate=False on the gltools root logger. This fixture resets
    propagation before each test in this module.
    """
    root = logging.getLogger("gltools")
    original = root.propagate
    root.propagate = True
    yield  # type: ignore[misc]
    root.propagate = original


def _make_config(default_project: str | None = None) -> MagicMock:
    """Create a mock GitLabConfig."""
    config = MagicMock()
    config.default_project = default_project
    return config


def _make_mr_client() -> MagicMock:
    """Create a mock GitLabClient for MR tests."""
    client = MagicMock()
    client.merge_requests = MagicMock()
    client.merge_requests.list = AsyncMock()
    client.merge_requests.get = AsyncMock()
    client.merge_requests.create = AsyncMock()
    client.merge_requests.update = AsyncMock()
    client.merge_requests.merge = AsyncMock()
    client.merge_requests.approve = AsyncMock()
    client.merge_requests.diff = AsyncMock()
    client.merge_requests.create_note = AsyncMock()
    return client


def _make_issue_client() -> MagicMock:
    """Create a mock GitLabClient for issue tests."""
    client = MagicMock()
    client.issues = MagicMock()
    client.issues.list = AsyncMock()
    client.issues.get = AsyncMock()
    client.issues.create = AsyncMock()
    client.issues.update = AsyncMock()
    client.issues.close = AsyncMock()
    client.issues.reopen = AsyncMock()
    client.issues.create_note = AsyncMock()
    return client


def _make_mr(**overrides: object) -> MergeRequest:
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


def _make_issue(**overrides: object) -> Issue:
    defaults = {
        "id": 1,
        "iid": 5,
        "title": "Test Issue",
        "description": None,
        "state": "opened",
        "author": {"id": 1, "username": "user", "name": "User"},
        "assignee": None,
        "labels": [],
        "milestone": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "closed_at": None,
    }
    defaults.update(overrides)
    return Issue.model_validate(defaults)


def _make_pipeline(**overrides: object) -> Pipeline:
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


def _make_ci_service() -> tuple[CIService, MagicMock, MagicMock, MagicMock]:
    pipeline_mgr = MagicMock()
    pipeline_mgr.list = AsyncMock()
    pipeline_mgr.get = AsyncMock()
    pipeline_mgr.create = AsyncMock()
    pipeline_mgr.retry = AsyncMock()
    pipeline_mgr.cancel = AsyncMock()

    job_mgr = MagicMock()
    job_mgr.list = AsyncMock()

    mr_mgr = MagicMock()
    mr_mgr.get = AsyncMock()

    service = CIService(
        project_id=42,
        pipeline_manager=pipeline_mgr,
        job_manager=job_mgr,
        mr_manager=mr_mgr,
    )
    return service, pipeline_mgr, job_mgr, mr_mgr


class TestMRServiceTraceLogging:
    """Tests for MergeRequest service DEBUG trace logging."""

    async def test_resolve_project_logs_explicit(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_mr_client()
        config = _make_config(default_project="config/proj")
        service = MergeRequestService(client, config, project="explicit/proj")

        with caplog.at_level(logging.DEBUG, logger="gltools.services.merge_request"):
            result = service._resolve_project()

        assert result == "explicit/proj"
        assert "Resolving project..." in caplog.text
        assert "from --project flag" in caplog.text

    async def test_resolve_project_logs_config(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_mr_client()
        config = _make_config(default_project="config/proj")
        service = MergeRequestService(client, config)

        with caplog.at_level(logging.DEBUG, logger="gltools.services.merge_request"):
            result = service._resolve_project()

        assert result == "config/proj"
        assert "from config" in caplog.text

    @patch("gltools.services.merge_request.detect_gitlab_remote")
    async def test_resolve_project_logs_git_remote(
        self, mock_detect: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_detect.return_value = MagicMock(project_path="remote/proj")
        client = _make_mr_client()
        config = _make_config(default_project=None)
        service = MergeRequestService(client, config)

        with caplog.at_level(logging.DEBUG, logger="gltools.services.merge_request"):
            result = service._resolve_project()

        assert result == "remote/proj"
        assert "from git remote" in caplog.text

    @patch("gltools.services.merge_request.detect_gitlab_remote")
    async def test_resolve_project_logs_failure(
        self, mock_detect: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_detect.return_value = None
        client = _make_mr_client()
        config = _make_config(default_project=None)
        service = MergeRequestService(client, config)

        with caplog.at_level(logging.DEBUG, logger="gltools.services.merge_request"), pytest.raises(
            ProjectResolutionError
        ):
            service._resolve_project()

        assert "Project resolution failed" in caplog.text

    async def test_list_mrs_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_mr_client()
        mr = _make_mr()
        client.merge_requests.list.return_value = PaginatedResponse[MergeRequest](
            items=[mr], page=1, per_page=20, total=1, total_pages=1, next_page=None
        )
        service = MergeRequestService(client, _make_config(), project="group/proj")

        with caplog.at_level(logging.DEBUG, logger="gltools.services.merge_request"):
            result = await service.list_mrs()

        assert len(result.items) == 1
        assert "Fetching merge requests..." in caplog.text
        assert "Found 1 merge requests" in caplog.text

    async def test_get_mr_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_mr_client()
        mr = _make_mr(iid=42, title="My Feature")
        client.merge_requests.get.return_value = mr
        service = MergeRequestService(client, _make_config(), project="group/proj")

        with caplog.at_level(logging.DEBUG, logger="gltools.services.merge_request"):
            await service.get_mr(42)

        assert "Fetching merge request !42..." in caplog.text
        assert "Fetched MR !42: My Feature" in caplog.text

    async def test_create_mr_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_mr_client()
        mr = _make_mr(iid=99)
        client.merge_requests.create.return_value = mr
        service = MergeRequestService(client, _make_config(), project="group/proj")

        with caplog.at_level(logging.DEBUG, logger="gltools.services.merge_request"):
            await service.create_mr(
                title="New MR", source_branch="feat", target_branch="main"
            )

        assert "Creating merge request: New MR (feat -> main)..." in caplog.text
        assert "MR created: !99" in caplog.text

    async def test_create_mr_dry_run_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_mr_client()
        service = MergeRequestService(client, _make_config(), project="group/proj")

        with caplog.at_level(logging.DEBUG, logger="gltools.services.merge_request"):
            result = await service.create_mr(
                title="New MR", source_branch="feat", target_branch="main", dry_run=True
            )

        assert isinstance(result, DryRunResult)
        assert "Dry-run: would POST" in caplog.text

    async def test_logging_does_not_interfere_with_exceptions(self) -> None:
        """Verify that logging doesn't swallow service exceptions."""
        client = _make_mr_client()
        client.merge_requests.get.side_effect = Exception("API error")
        service = MergeRequestService(client, _make_config(), project="group/proj")

        with pytest.raises(Exception, match="API error"):
            await service.get_mr(42)


class TestIssueServiceTraceLogging:
    """Tests for Issue service DEBUG trace logging."""

    async def test_resolve_project_logs_source(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_issue_client()
        config = _make_config(default_project="config/proj")
        service = IssueService(client, config, project="explicit/proj")

        with caplog.at_level(logging.DEBUG, logger="gltools.services.issue"):
            result = service._resolve_project()

        assert result == "explicit/proj"
        assert "from --project flag" in caplog.text

    async def test_list_issues_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_issue_client()
        issue = _make_issue()
        client.issues.list.return_value = PaginatedResponse[Issue](
            items=[issue, issue], page=1, per_page=20, total=2, total_pages=1, next_page=None
        )
        service = IssueService(client, _make_config(), project="group/proj")

        with caplog.at_level(logging.DEBUG, logger="gltools.services.issue"):
            result = await service.list_issues()

        assert len(result.items) == 2
        assert "Fetching issues..." in caplog.text
        assert "Found 2 issues" in caplog.text

    async def test_create_issue_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_issue_client()
        issue = _make_issue(iid=7)
        client.issues.create.return_value = issue
        service = IssueService(client, _make_config(), project="group/proj")

        with caplog.at_level(logging.DEBUG, logger="gltools.services.issue"):
            await service.create_issue(title="Bug Report")

        assert "Creating issue: Bug Report..." in caplog.text
        assert "Issue created: #7" in caplog.text

    async def test_logging_does_not_interfere_with_exceptions(self) -> None:
        """Verify that logging doesn't swallow issue service exceptions."""
        client = _make_issue_client()
        client.issues.get.side_effect = Exception("API error")
        service = IssueService(client, _make_config(), project="group/proj")

        with pytest.raises(Exception, match="API error"):
            await service.get_issue(5)


class TestCIServiceTraceLogging:
    """Tests for CI service DEBUG trace logging."""

    async def test_list_pipelines_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        service, pipeline_mgr, _, _ = _make_ci_service()
        pipeline = _make_pipeline()
        pipeline_mgr.list.return_value = PaginatedResponse[Pipeline](
            items=[pipeline], page=1, per_page=20, total=1, total_pages=1, next_page=None
        )

        with caplog.at_level(logging.DEBUG, logger="gltools.services.ci"):
            result = await service.list_pipelines()

        assert len(result.items) == 1
        assert "Fetching pipelines..." in caplog.text
        assert "Found 1 pipelines" in caplog.text

    async def test_get_status_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        service, pipeline_mgr, _, _ = _make_ci_service()
        pipeline = _make_pipeline(id=200)
        pipeline_mgr.list.return_value = PaginatedResponse[Pipeline](
            items=[pipeline], page=1, per_page=1, total=1, total_pages=1, next_page=None
        )
        pipeline_mgr.get.return_value = pipeline

        with caplog.at_level(logging.DEBUG, logger="gltools.services.ci"):
            await service.get_status(ref="main")

        assert "Getting pipeline status..." in caplog.text
        assert "Fetching latest pipeline for ref 'main'..." in caplog.text
        assert "Found pipeline #200" in caplog.text

    async def test_trigger_pipeline_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        service, pipeline_mgr, _, _ = _make_ci_service()
        pipeline = _make_pipeline(id=300)
        pipeline_mgr.create.return_value = pipeline

        with caplog.at_level(logging.DEBUG, logger="gltools.services.ci"):
            await service.trigger_pipeline(ref="develop")

        assert "Triggering pipeline for ref 'develop'..." in caplog.text
        assert "Pipeline #300 triggered" in caplog.text

    async def test_retry_pipeline_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        service, pipeline_mgr, _, _ = _make_ci_service()
        pipeline = _make_pipeline(id=400)
        pipeline_mgr.retry.return_value = pipeline

        with caplog.at_level(logging.DEBUG, logger="gltools.services.ci"):
            await service.retry_pipeline(400)

        assert "Retrying pipeline #400..." in caplog.text
        assert "Pipeline #400 retried" in caplog.text

    async def test_list_jobs_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        from gltools.models.job import Job

        service, _, job_mgr, _ = _make_ci_service()
        job = Job.model_validate({"id": 1001, "name": "test", "stage": "test", "status": "success"})
        job_mgr.list.return_value = [job]

        with caplog.at_level(logging.DEBUG, logger="gltools.services.ci"):
            result = await service.list_jobs(100)

        assert len(result) == 1
        assert "Fetching jobs for pipeline #100..." in caplog.text
        assert "Found 1 jobs" in caplog.text

    async def test_logging_does_not_interfere_with_exceptions(self) -> None:
        """Verify that logging doesn't swallow CI service exceptions."""
        service, pipeline_mgr, _, _ = _make_ci_service()
        pipeline_mgr.retry.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await service.retry_pipeline(999)
