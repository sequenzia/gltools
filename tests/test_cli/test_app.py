"""Tests for the main Typer CLI application."""

from unittest.mock import patch

from typer.testing import CliRunner

from gltools import __version__
from gltools.cli.app import app

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
