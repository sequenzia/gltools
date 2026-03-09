"""Tests for CLI config state logging at command startup."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
import typer


@pytest.fixture(autouse=True)
def _reset_logger_propagation() -> None:
    """Ensure gltools loggers propagate so caplog can capture them."""
    root = logging.getLogger("gltools")
    original = root.propagate
    root.propagate = True
    yield  # type: ignore[misc]
    root.propagate = original


def _make_ctx(**overrides: object) -> typer.Context:
    """Create a minimal Typer context with an object dict."""
    ctx = MagicMock(spec=typer.Context)
    obj: dict[str, object] = {}
    obj.update(overrides)
    ctx.ensure_object.return_value = obj
    ctx.obj = obj
    return ctx


class TestMRConfigLogging:
    """Tests that MR CLI _build_service logs config state at INFO."""

    @patch("gltools.config.settings.GitLabConfig.from_config")
    @patch("gltools.client.gitlab.GitLabClient")
    @patch("gltools.services.merge_request.MergeRequestService")
    async def test_build_service_logs_config(
        self,
        mock_service_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_from_config: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from gltools.cli.mr import _build_service

        mock_config = MagicMock()
        mock_config.host = "https://gitlab.example.com"
        mock_config.auth_type = "pat"
        mock_config.token = "test-token"
        mock_config.profile = "default"
        mock_config.default_project = "mygroup/myproject"
        mock_config.client_id = None
        mock_from_config.return_value = mock_config

        ctx = _make_ctx()

        with caplog.at_level(logging.INFO, logger="gltools.cli.mr"):
            await _build_service(ctx, project="custom/proj")

        assert "https://gitlab.example.com" in caplog.text
        assert "pat" in caplog.text
        assert "custom/proj" in caplog.text
        assert "default" in caplog.text

    @patch("gltools.config.settings.GitLabConfig.from_config")
    @patch("gltools.client.gitlab.GitLabClient")
    @patch("gltools.services.merge_request.MergeRequestService")
    async def test_build_service_logs_auto_detect_when_no_project(
        self,
        mock_service_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_from_config: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from gltools.cli.mr import _build_service

        mock_config = MagicMock()
        mock_config.host = "https://gitlab.com"
        mock_config.auth_type = "oauth"
        mock_config.token = "test-token"
        mock_config.profile = "work"
        mock_config.default_project = None
        mock_config.client_id = None
        mock_from_config.return_value = mock_config

        ctx = _make_ctx()

        with caplog.at_level(logging.INFO, logger="gltools.cli.mr"):
            await _build_service(ctx)

        assert "(auto-detect)" in caplog.text
        assert "oauth" in caplog.text
        assert "work" in caplog.text


class TestIssueConfigLogging:
    """Tests that Issue CLI _build_service logs config state at INFO."""

    @patch("gltools.config.settings.GitLabConfig.from_config")
    @patch("gltools.client.gitlab.GitLabClient")
    @patch("gltools.services.issue.IssueService")
    async def test_build_service_logs_config(
        self,
        mock_service_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_from_config: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from gltools.cli.issue import _build_service

        mock_config = MagicMock()
        mock_config.host = "https://my-gitlab.internal"
        mock_config.auth_type = "pat"
        mock_config.token = "test-token"
        mock_config.profile = "staging"
        mock_config.default_project = "team/repo"
        mock_config.client_id = None
        mock_from_config.return_value = mock_config

        ctx = _make_ctx()

        with caplog.at_level(logging.INFO, logger="gltools.cli.issue"):
            await _build_service(ctx, project="override/proj")

        assert "https://my-gitlab.internal" in caplog.text
        assert "pat" in caplog.text
        assert "override/proj" in caplog.text
        assert "staging" in caplog.text


class TestCIConfigLogging:
    """Tests that CI CLI _build_service logs config state at INFO."""

    @patch("gltools.config.git_remote.detect_gitlab_remote")
    @patch("gltools.config.settings.GitLabConfig.from_config")
    @patch("gltools.client.gitlab.GitLabClient")
    @patch("gltools.services.ci.CIService")
    def test_build_service_logs_config_from_default_project(
        self,
        mock_service_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_from_config: MagicMock,
        mock_detect: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from gltools.cli.ci import _build_service

        mock_config = MagicMock()
        mock_config.host = "https://gitlab.corp.com"
        mock_config.auth_type = "oauth"
        mock_config.token = "test-token"
        mock_config.profile = "production"
        mock_config.default_project = "corp/app"
        mock_config.client_id = None
        mock_from_config.return_value = mock_config

        ctx = _make_ctx()

        with caplog.at_level(logging.INFO, logger="gltools.cli.ci"):
            _build_service(ctx)

        assert "https://gitlab.corp.com" in caplog.text
        assert "oauth" in caplog.text
        assert "corp/app" in caplog.text
        assert "config" in caplog.text
        assert "production" in caplog.text
        mock_detect.assert_not_called()

    @patch("gltools.config.git_remote.detect_gitlab_remote")
    @patch("gltools.config.settings.GitLabConfig.from_config")
    @patch("gltools.client.gitlab.GitLabClient")
    @patch("gltools.services.ci.CIService")
    def test_build_service_logs_git_remote_source(
        self,
        mock_service_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_from_config: MagicMock,
        mock_detect: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from gltools.cli.ci import _build_service

        mock_config = MagicMock()
        mock_config.host = "https://gitlab.com"
        mock_config.auth_type = "pat"
        mock_config.token = "test-token"
        mock_config.profile = "default"
        mock_config.default_project = None
        mock_config.client_id = None
        mock_from_config.return_value = mock_config

        mock_detect.return_value = MagicMock(project_path_encoded="remote%2Fproject")

        ctx = _make_ctx()

        with caplog.at_level(logging.INFO, logger="gltools.cli.ci"):
            _build_service(ctx)

        assert "git remote" in caplog.text
        assert "remote%2Fproject" in caplog.text

    @patch("gltools.config.git_remote.detect_gitlab_remote")
    @patch("gltools.config.settings.GitLabConfig.from_config")
    @patch("gltools.client.gitlab.GitLabClient")
    @patch("gltools.services.ci.CIService")
    def test_build_service_logs_git_remote_detection_failure(
        self,
        mock_service_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_from_config: MagicMock,
        mock_detect: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from gltools.cli.ci import _build_service

        mock_config = MagicMock()
        mock_config.host = "https://gitlab.com"
        mock_config.auth_type = "pat"
        mock_config.token = "test-token"
        mock_config.profile = "default"
        mock_config.default_project = None
        mock_config.client_id = None
        mock_from_config.return_value = mock_config

        mock_detect.return_value = None

        ctx = _make_ctx()

        with caplog.at_level(logging.DEBUG, logger="gltools.cli.ci"), pytest.raises(typer.BadParameter):
            _build_service(ctx)

        assert "Git remote detection did not find a GitLab remote" in caplog.text


class TestConfigWithMissingFields:
    """Tests that config logging handles missing optional fields gracefully."""

    @patch("gltools.config.settings.GitLabConfig.from_config")
    @patch("gltools.client.gitlab.GitLabClient")
    @patch("gltools.services.merge_request.MergeRequestService")
    async def test_missing_optional_fields_logged_without_errors(
        self,
        mock_service_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_from_config: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from gltools.cli.mr import _build_service

        mock_config = MagicMock()
        mock_config.host = "https://gitlab.com"
        mock_config.auth_type = "pat"
        mock_config.token = ""
        mock_config.profile = "default"
        mock_config.default_project = None
        mock_config.client_id = None
        mock_from_config.return_value = mock_config

        ctx = _make_ctx()

        with caplog.at_level(logging.INFO, logger="gltools.cli.mr"):
            await _build_service(ctx)

        assert "(auto-detect)" in caplog.text
        assert "https://gitlab.com" in caplog.text
