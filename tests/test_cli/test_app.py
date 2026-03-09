"""Tests for the main Typer CLI application."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

from gltools import __version__
from gltools.cli.app import app
from gltools.logging import LOGGER_NAME

if TYPE_CHECKING:
    from pathlib import Path

import pytest

runner = CliRunner()


class TestHelpOutput:
    """Verify --help shows all command groups."""

    def test_help_shows_all_groups(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "mr" in result.output
        assert "issue" in result.output
        assert "ci" in result.output
        assert "auth" in result.output
        assert "plugin" in result.output
        assert "tui" in result.output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        # no_args_is_help triggers usage error (exit code 0 or 2 depending on Typer version)
        assert result.exit_code in (0, 2)
        assert "mr" in result.output


class TestVersion:
    """Verify --version outputs version string."""

    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output
        assert "gltools" in result.output

    def test_version_short_flag(self) -> None:
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestGlobalOptions:
    """Verify global options are parsed correctly."""

    def test_json_flag_sets_output_format(self) -> None:
        result = runner.invoke(app, ["--json", "auth"])
        assert result.exit_code == 0

    def test_text_flag_sets_output_format(self) -> None:
        result = runner.invoke(app, ["--text", "auth"])
        assert result.exit_code == 0

    def test_host_option(self) -> None:
        result = runner.invoke(app, ["--host", "https://gitlab.example.com", "auth"])
        assert result.exit_code == 0

    def test_token_option(self) -> None:
        result = runner.invoke(app, ["--token", "glpat-test", "auth"])
        assert result.exit_code == 0

    def test_profile_option(self) -> None:
        result = runner.invoke(app, ["--profile", "work", "auth"])
        assert result.exit_code == 0

    def test_quiet_flag(self) -> None:
        result = runner.invoke(app, ["--quiet", "auth"])
        assert result.exit_code == 0

    def test_quiet_short_flag(self) -> None:
        result = runner.invoke(app, ["-q", "auth"])
        assert result.exit_code == 0


class TestSubcommandGroups:
    """Verify subcommand groups are registered."""

    def test_mr_group(self) -> None:
        result = runner.invoke(app, ["mr"])
        assert result.exit_code == 0

    def test_issue_group(self) -> None:
        result = runner.invoke(app, ["issue"])
        assert result.exit_code == 0

    def test_ci_group(self) -> None:
        result = runner.invoke(app, ["ci"])
        assert result.exit_code == 0

    def test_auth_group(self) -> None:
        result = runner.invoke(app, ["auth"])
        assert result.exit_code == 0

    def test_plugin_group(self) -> None:
        result = runner.invoke(app, ["plugin"])
        assert result.exit_code == 0


class TestSubcommandHelp:
    """Verify --help for all subcommand groups and individual commands."""

    def test_mr_help(self) -> None:
        result = runner.invoke(app, ["mr", "--help"])
        assert result.exit_code == 0
        assert "Merge request commands" in result.output

    def test_issue_help(self) -> None:
        result = runner.invoke(app, ["issue", "--help"])
        assert result.exit_code == 0
        assert "Issue commands" in result.output

    def test_ci_help(self) -> None:
        result = runner.invoke(app, ["ci", "--help"])
        assert result.exit_code == 0
        assert "CI/CD" in result.output

    def test_auth_help(self) -> None:
        result = runner.invoke(app, ["auth", "--help"])
        assert result.exit_code == 0
        assert "Authentication" in result.output

    def test_plugin_help(self) -> None:
        result = runner.invoke(app, ["plugin", "--help"])
        assert result.exit_code == 0
        assert "Plugin" in result.output

    def test_mr_list_help(self) -> None:
        result = runner.invoke(app, ["mr", "list", "--help"])
        assert result.exit_code == 0
        assert "--state" in result.output

    def test_mr_create_help(self) -> None:
        result = runner.invoke(app, ["mr", "create", "--help"])
        assert result.exit_code == 0
        assert "--title" in result.output

    def test_mr_view_help(self) -> None:
        result = runner.invoke(app, ["mr", "view", "--help"])
        assert result.exit_code == 0
        assert "MR_IID" in result.output

    def test_mr_merge_help(self) -> None:
        result = runner.invoke(app, ["mr", "merge", "--help"])
        assert result.exit_code == 0
        assert "--squash" in result.output

    def test_mr_approve_help(self) -> None:
        result = runner.invoke(app, ["mr", "approve", "--help"])
        assert result.exit_code == 0
        assert "MR_IID" in result.output

    def test_mr_diff_help(self) -> None:
        result = runner.invoke(app, ["mr", "diff", "--help"])
        assert result.exit_code == 0
        assert "diff" in result.output.lower()

    def test_mr_note_help(self) -> None:
        result = runner.invoke(app, ["mr", "note", "--help"])
        assert result.exit_code == 0
        assert "--body" in result.output

    def test_mr_close_help(self) -> None:
        result = runner.invoke(app, ["mr", "close", "--help"])
        assert result.exit_code == 0
        assert "MR_IID" in result.output

    def test_mr_reopen_help(self) -> None:
        result = runner.invoke(app, ["mr", "reopen", "--help"])
        assert result.exit_code == 0
        assert "MR_IID" in result.output

    def test_mr_update_help(self) -> None:
        result = runner.invoke(app, ["mr", "update", "--help"])
        assert result.exit_code == 0
        assert "--title" in result.output

    def test_issue_create_help(self) -> None:
        result = runner.invoke(app, ["issue", "create", "--help"])
        assert result.exit_code == 0
        assert "--title" in result.output

    def test_issue_list_help(self) -> None:
        result = runner.invoke(app, ["issue", "list", "--help"])
        assert result.exit_code == 0
        assert "--state" in result.output

    def test_issue_view_help(self) -> None:
        result = runner.invoke(app, ["issue", "view", "--help"])
        assert result.exit_code == 0
        assert "ISSUE_IID" in result.output

    def test_issue_update_help(self) -> None:
        result = runner.invoke(app, ["issue", "update", "--help"])
        assert result.exit_code == 0
        assert "--title" in result.output

    def test_issue_close_help(self) -> None:
        result = runner.invoke(app, ["issue", "close", "--help"])
        assert result.exit_code == 0
        assert "ISSUE_IID" in result.output

    def test_issue_reopen_help(self) -> None:
        result = runner.invoke(app, ["issue", "reopen", "--help"])
        assert result.exit_code == 0
        assert "ISSUE_IID" in result.output

    def test_issue_note_help(self) -> None:
        result = runner.invoke(app, ["issue", "note", "--help"])
        assert result.exit_code == 0
        assert "--body" in result.output

    def test_ci_status_help(self) -> None:
        result = runner.invoke(app, ["ci", "status", "--help"])
        assert result.exit_code == 0
        assert "--mr" in result.output

    def test_ci_list_help(self) -> None:
        result = runner.invoke(app, ["ci", "list", "--help"])
        assert result.exit_code == 0
        assert "--status" in result.output

    def test_ci_run_help(self) -> None:
        result = runner.invoke(app, ["ci", "run", "--help"])
        assert result.exit_code == 0
        assert "--ref" in result.output

    def test_ci_retry_help(self) -> None:
        result = runner.invoke(app, ["ci", "retry", "--help"])
        assert result.exit_code == 0
        assert "PIPELINE_ID" in result.output

    def test_ci_cancel_help(self) -> None:
        result = runner.invoke(app, ["ci", "cancel", "--help"])
        assert result.exit_code == 0
        assert "PIPELINE_ID" in result.output

    def test_ci_jobs_help(self) -> None:
        result = runner.invoke(app, ["ci", "jobs", "--help"])
        assert result.exit_code == 0
        assert "PIPELINE_ID" in result.output

    def test_ci_logs_help(self) -> None:
        result = runner.invoke(app, ["ci", "logs", "--help"])
        assert result.exit_code == 0
        assert "JOB_ID" in result.output

    def test_ci_artifacts_help(self) -> None:
        result = runner.invoke(app, ["ci", "artifacts", "--help"])
        assert result.exit_code == 0
        assert "JOB_ID" in result.output

    def test_auth_login_help(self) -> None:
        result = runner.invoke(app, ["auth", "login", "--help"])
        assert result.exit_code == 0
        assert "login" in result.output.lower()

    def test_auth_status_help(self) -> None:
        result = runner.invoke(app, ["auth", "status", "--help"])
        assert result.exit_code == 0
        assert "authentication" in result.output.lower()

    def test_auth_logout_help(self) -> None:
        result = runner.invoke(app, ["auth", "logout", "--help"])
        assert result.exit_code == 0
        assert "credentials" in result.output.lower()

    def test_plugin_list_help(self) -> None:
        result = runner.invoke(app, ["plugin", "list", "--help"])
        assert result.exit_code == 0
        assert "plugin" in result.output.lower()


class TestEdgeCases:
    """Edge case tests."""

    def test_unknown_subcommand_exit_code_2(self) -> None:
        result = runner.invoke(app, ["nonexistent"])
        assert result.exit_code == 2

    def test_mr_unknown_subcommand_exit_code_2(self) -> None:
        result = runner.invoke(app, ["mr", "nonexistent"])
        assert result.exit_code == 2

    def test_issue_unknown_subcommand_exit_code_2(self) -> None:
        result = runner.invoke(app, ["issue", "nonexistent"])
        assert result.exit_code == 2

    def test_ci_unknown_subcommand_exit_code_2(self) -> None:
        result = runner.invoke(app, ["ci", "nonexistent"])
        assert result.exit_code == 2

    def test_auth_unknown_subcommand_exit_code_2(self) -> None:
        result = runner.invoke(app, ["auth", "nonexistent"])
        assert result.exit_code == 2


class TestTuiCommand:
    """Verify tui command launches the TUI."""

    @patch("gltools.tui.launch_tui")
    def test_tui_command_calls_launch(self, mock_launch) -> None:
        result = runner.invoke(app, ["tui"])
        assert result.exit_code == 0
        mock_launch.assert_called_once()

    @patch("gltools.tui.launch_tui")
    def test_tui_with_global_options(self, mock_launch) -> None:
        result = runner.invoke(
            app,
            ["--host", "https://gitlab.example.com", "--token", "tok", "--profile", "work", "tui"],
        )
        assert result.exit_code == 0
        mock_launch.assert_called_once_with(
            profile="work",
            host="https://gitlab.example.com",
            token="tok",
        )


class TestLoggingFlags:
    """Verify --verbose, --debug, and --log-file global flags."""

    @pytest.fixture(autouse=True)
    def _clean_logger(self) -> None:
        """Ensure a clean gltools logger state before and after each test."""
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        logger.setLevel(logging.WARNING)
        yield  # type: ignore[misc]
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        logger.setLevel(logging.WARNING)

    def test_verbose_flag_sets_info_level(self) -> None:
        result = runner.invoke(app, ["--verbose", "auth"])
        assert result.exit_code == 0
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level == logging.INFO

    def test_verbose_short_flag(self) -> None:
        result = runner.invoke(app, ["-v", "auth"])
        assert result.exit_code == 0
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level == logging.INFO

    def test_debug_flag_sets_debug_level(self) -> None:
        result = runner.invoke(app, ["--debug", "auth"])
        assert result.exit_code == 0
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level == logging.DEBUG

    def test_debug_overrides_verbose(self) -> None:
        result = runner.invoke(app, ["--verbose", "--debug", "auth"])
        assert result.exit_code == 0
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level == logging.DEBUG

    def test_debug_overrides_verbose_reverse_order(self) -> None:
        result = runner.invoke(app, ["--debug", "--verbose", "auth"])
        assert result.exit_code == 0
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level == logging.DEBUG

    def test_no_flags_defaults_to_warning(self) -> None:
        result = runner.invoke(app, ["auth"])
        assert result.exit_code == 0
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level == logging.WARNING

    def test_verbose_flag_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.output
        assert "-v" in result.output

    def test_debug_flag_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--debug" in result.output

    def test_log_file_flag_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--log-file" in result.output

    def test_flags_available_on_subcommands(self) -> None:
        """Flags are global and available before any subcommand."""
        result = runner.invoke(app, ["--verbose", "mr"])
        assert result.exit_code == 0
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level == logging.INFO

        result = runner.invoke(app, ["--debug", "issue"])
        assert result.exit_code == 0
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level == logging.DEBUG


class TestLoggingCtxObj:
    """Verify logging state is stored in ctx.obj for downstream access."""

    @pytest.fixture(autouse=True)
    def _clean_logger(self) -> None:
        """Ensure a clean gltools logger state before and after each test."""
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        logger.setLevel(logging.WARNING)
        yield  # type: ignore[misc]
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        logger.setLevel(logging.WARNING)

    def test_verbose_stored_in_ctx(self) -> None:
        captured_ctx: dict = {}

        @app.command("_test_verbose_ctx")
        def _test_cmd(ctx: __import__("typer").Context) -> None:
            captured_ctx.update(ctx.obj)

        result = runner.invoke(app, ["--verbose", "_test_verbose_ctx"])
        assert result.exit_code == 0
        assert captured_ctx["verbose"] is True
        assert captured_ctx["log_level"] == "INFO"
        # Clean up registered command
        app.registered_commands.pop()

    def test_debug_stored_in_ctx(self) -> None:
        captured_ctx: dict = {}

        @app.command("_test_debug_ctx")
        def _test_cmd(ctx: __import__("typer").Context) -> None:
            captured_ctx.update(ctx.obj)

        result = runner.invoke(app, ["--debug", "_test_debug_ctx"])
        assert result.exit_code == 0
        assert captured_ctx["debug"] is True
        assert captured_ctx["log_level"] == "DEBUG"
        app.registered_commands.pop()

    def test_log_file_stored_in_ctx(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        captured_ctx: dict = {}

        @app.command("_test_logfile_ctx")
        def _test_cmd(ctx: __import__("typer").Context) -> None:
            captured_ctx.update(ctx.obj)

        result = runner.invoke(app, ["--log-file", str(log_file), "_test_logfile_ctx"])
        assert result.exit_code == 0
        assert captured_ctx["log_file"] == str(log_file)
        app.registered_commands.pop()

    def test_no_log_file_stores_none(self) -> None:
        captured_ctx: dict = {}

        @app.command("_test_no_logfile_ctx")
        def _test_cmd(ctx: __import__("typer").Context) -> None:
            captured_ctx.update(ctx.obj)

        result = runner.invoke(app, ["_test_no_logfile_ctx"])
        assert result.exit_code == 0
        assert captured_ctx["log_file"] is None
        app.registered_commands.pop()


class TestLogFileFlag:
    """Verify --log-file flag creates a log file with output."""

    @pytest.fixture(autouse=True)
    def _clean_logger(self) -> None:
        """Ensure a clean gltools logger state before and after each test."""
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        logger.setLevel(logging.WARNING)
        yield  # type: ignore[misc]
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        logger.setLevel(logging.WARNING)

    def test_log_file_creates_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "output.log"
        result = runner.invoke(app, ["--log-file", str(log_file), "--debug", "auth"])
        assert result.exit_code == 0
        # File handler should be set up
        logger = logging.getLogger(LOGGER_NAME)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_log_file_with_debug_sets_debug_handler(self, tmp_path: Path) -> None:
        log_file = tmp_path / "debug.log"
        result = runner.invoke(app, ["--log-file", str(log_file), "--debug", "auth"])
        assert result.exit_code == 0

        logger = logging.getLogger(LOGGER_NAME)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        # File handler should use JSON formatter
        from gltools.logging import JSONFormatter

        assert isinstance(file_handlers[0].formatter, JSONFormatter)
        # Logger should be at DEBUG level
        assert logger.level == logging.DEBUG

    def test_log_file_nested_directory(self, tmp_path: Path) -> None:
        log_file = tmp_path / "nested" / "deep" / "output.log"
        result = runner.invoke(app, ["--log-file", str(log_file), "auth"])
        assert result.exit_code == 0
        assert log_file.parent.exists()


class TestLoggingEdgeCases:
    """Edge cases for logging flags."""

    @pytest.fixture(autouse=True)
    def _clean_logger(self) -> None:
        """Ensure a clean gltools logger state before and after each test."""
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        logger.setLevel(logging.WARNING)
        yield  # type: ignore[misc]
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        logger.setLevel(logging.WARNING)

    def test_quiet_and_verbose_together(self) -> None:
        """--quiet suppresses CLI output, but logging still works."""
        result = runner.invoke(app, ["--quiet", "--verbose", "auth"])
        assert result.exit_code == 0
        logger = logging.getLogger(LOGGER_NAME)
        # Logging should still be at INFO despite --quiet
        assert logger.level == logging.INFO

    def test_invalid_log_file_path_exits_with_error(self, tmp_path: Path) -> None:
        """Invalid --log-file path produces a clear error."""
        # Create a read-only directory to prevent file creation
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o444)

        log_file = restricted / "subdir" / "output.log"
        result = runner.invoke(app, ["--log-file", str(log_file), "auth"])
        assert result.exit_code == 1
        assert "Error" in result.output or "Cannot" in result.output

        # Cleanup
        restricted.chmod(0o755)
