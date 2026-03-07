"""Tests for auth CLI commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from gltools.cli.app import app
from gltools.services.auth import AuthStatus, LoginResult

runner = CliRunner()


class TestAuthLogin:
    """Tests for `gltools auth login`."""

    def test_successful_login(self) -> None:
        login_result = LoginResult(
            success=True,
            username="testuser",
            host="https://gitlab.com",
            token_storage="keyring",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["auth", "login"],
                input="https://gitlab.com\nglpat-test123\n",
            )

        assert result.exit_code == 0
        assert "testuser" in result.output
        assert "keyring" in result.output

    def test_login_invalid_token(self) -> None:
        login_result = LoginResult(
            success=False,
            error="Authentication failed: token may be expired or invalid.",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["auth", "login"],
                input="https://gitlab.com\nglpat-bad\n",
            )

        assert result.exit_code == 1
        assert "Authentication failed" in result.output

    def test_login_network_error(self) -> None:
        login_result = LoginResult(
            success=False,
            error="Unable to connect to https://gitlab.bad.",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["auth", "login"],
                input="https://gitlab.bad\nglpat-test\n",
            )

        assert result.exit_code == 1
        assert "Unable to connect" in result.output

    def test_login_json_output(self) -> None:
        login_result = LoginResult(
            success=True,
            username="testuser",
            host="https://gitlab.com",
            token_storage="keyring",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["--json", "auth", "login"],
                input="https://gitlab.com\nglpat-test123\n",
            )

        assert result.exit_code == 0
        assert '"username"' in result.output
        assert '"testuser"' in result.output

    def test_login_json_error(self) -> None:
        login_result = LoginResult(
            success=False,
            error="Authentication failed: token may be expired or invalid.",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["--json", "auth", "login"],
                input="https://gitlab.com\nglpat-bad\n",
            )

        assert result.exit_code == 1
        assert '"error"' in result.output

    def test_login_overwrites_existing(self) -> None:
        """Login when already authenticated should succeed (overwrite)."""
        login_result = LoginResult(
            success=True,
            username="newuser",
            host="https://gitlab.com",
            token_storage="keyring",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["auth", "login"],
                input="https://gitlab.com\nglpat-new\n",
            )

        assert result.exit_code == 0
        assert "newuser" in result.output

    def test_login_keyring_unavailable_warning(self) -> None:
        login_result = LoginResult(
            success=True,
            username="testuser",
            host="https://gitlab.com",
            token_storage="config file",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["auth", "login"],
                input="https://gitlab.com\nglpat-test\n",
            )

        assert result.exit_code == 0
        assert "config file" in result.output


class TestAuthStatus:
    """Tests for `gltools auth status`."""

    def test_status_authenticated(self) -> None:
        auth_status = AuthStatus(
            authenticated=True,
            host="https://gitlab.com",
            username="testuser",
            token_valid=True,
            config_file="/home/user/.config/gltools/config.toml",
            token_storage="keyring",
            profile="default",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.get_status = AsyncMock(return_value=auth_status)

            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "testuser" in result.output
        assert "gitlab.com" in result.output
        assert "keyring" in result.output

    def test_status_not_authenticated(self) -> None:
        auth_status = AuthStatus(
            authenticated=False,
            config_file="/home/user/.config/gltools/config.toml",
            profile="default",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.get_status = AsyncMock(return_value=auth_status)

            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 1
        assert "Not authenticated" in result.output

    def test_status_json_authenticated(self) -> None:
        auth_status = AuthStatus(
            authenticated=True,
            host="https://gitlab.com",
            username="testuser",
            token_valid=True,
            config_file="/home/user/.config/gltools/config.toml",
            token_storage="keyring",
            profile="default",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.get_status = AsyncMock(return_value=auth_status)

            result = runner.invoke(app, ["--json", "auth", "status"])

        assert result.exit_code == 0
        assert '"authenticated": true' in result.output
        assert '"username": "testuser"' in result.output

    def test_status_json_not_authenticated(self) -> None:
        auth_status = AuthStatus(
            authenticated=False,
            config_file="/home/user/.config/gltools/config.toml",
            profile="default",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.get_status = AsyncMock(return_value=auth_status)

            result = runner.invoke(app, ["--json", "auth", "status"])

        assert result.exit_code == 1
        assert '"authenticated": false' in result.output

    def test_status_with_profile(self) -> None:
        auth_status = AuthStatus(
            authenticated=True,
            host="https://work.gitlab.com",
            username="workuser",
            token_valid=True,
            config_file="/home/user/.config/gltools/config.toml",
            token_storage="keyring",
            profile="work",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.get_status = AsyncMock(return_value=auth_status)

            result = runner.invoke(app, ["--profile", "work", "auth", "status"])

        assert result.exit_code == 0
        assert "work" in result.output


class TestAuthLogout:
    """Tests for `gltools auth logout`."""

    def test_logout_success(self) -> None:
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.logout.return_value = True

            result = runner.invoke(app, ["auth", "logout"])

        assert result.exit_code == 0
        assert "Credentials removed" in result.output

    def test_logout_no_credentials(self) -> None:
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.logout.return_value = False

            result = runner.invoke(app, ["auth", "logout"])

        assert result.exit_code == 0
        assert "No credentials found" in result.output

    def test_logout_json_success(self) -> None:
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.logout.return_value = True

            result = runner.invoke(app, ["--json", "auth", "logout"])

        assert result.exit_code == 0
        assert '"Credentials removed."' in result.output

    def test_logout_json_no_credentials(self) -> None:
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.logout.return_value = False

            result = runner.invoke(app, ["--json", "auth", "logout"])

        assert result.exit_code == 0
        assert '"No credentials found."' in result.output

    def test_logout_with_profile(self) -> None:
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.logout.return_value = True

            result = runner.invoke(app, ["--profile", "work", "auth", "logout"])

        assert result.exit_code == 0
        mock_cls.assert_called_once_with(profile="work")


class TestAuthLoginOAuth:
    """Tests for `gltools auth login --method web/device`."""

    def test_login_oauth_web_success(self) -> None:
        login_result = LoginResult(
            success=True,
            username="oauthuser",
            host="https://gitlab.com",
            token_storage="keyring",
            auth_type="oauth",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.oauth_login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["auth", "login", "--method", "web"],
                input="https://gitlab.com\nclient-id-123\n",
            )

        assert result.exit_code == 0
        assert "oauthuser" in result.output
        mock_service.oauth_login.assert_awaited_once_with("https://gitlab.com", "client-id-123", method="web")

    def test_login_oauth_device_success(self) -> None:
        login_result = LoginResult(
            success=True,
            username="deviceuser",
            host="https://gitlab.com",
            token_storage="keyring",
            auth_type="oauth",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.oauth_login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["auth", "login", "--method", "device"],
                input="https://gitlab.com\nclient-id-123\n",
            )

        assert result.exit_code == 0
        assert "deviceuser" in result.output
        mock_service.oauth_login.assert_awaited_once_with("https://gitlab.com", "client-id-123", method="device")

    def test_login_oauth_failure(self) -> None:
        login_result = LoginResult(
            success=False,
            error="Authentication timed out. Try again.",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.oauth_login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["auth", "login", "--method", "web"],
                input="https://gitlab.com\nclient-id-123\n",
            )

        assert result.exit_code == 1
        assert "timed out" in result.output

    def test_login_oauth_json_output(self) -> None:
        login_result = LoginResult(
            success=True,
            username="oauthuser",
            host="https://gitlab.com",
            token_storage="keyring",
            auth_type="oauth",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.oauth_login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["--json", "auth", "login", "--method", "web"],
                input="https://gitlab.com\nclient-id-123\n",
            )

        assert result.exit_code == 0
        assert '"auth_type"' in result.output
        assert '"oauth"' in result.output

    def test_login_unknown_method(self) -> None:
        result = runner.invoke(
            app,
            ["auth", "login", "--method", "unknown"],
            input="https://gitlab.com\n",
        )
        assert result.exit_code == 1
        assert "Unknown method" in result.output

    def test_login_pat_method_works_like_default(self) -> None:
        login_result = LoginResult(
            success=True,
            username="patuser",
            host="https://gitlab.com",
            token_storage="keyring",
            auth_type="pat",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["auth", "login", "--method", "pat"],
                input="https://gitlab.com\nglpat-test\n",
            )

        assert result.exit_code == 0
        assert "patuser" in result.output
        mock_service.login.assert_awaited_once()


class TestAuthStatusAuthType:
    """Tests for auth_type in status output."""

    def test_status_shows_auth_type_oauth(self) -> None:
        auth_status = AuthStatus(
            authenticated=True,
            host="https://gitlab.com",
            username="oauthuser",
            token_valid=True,
            config_file="/home/user/.config/gltools/config.toml",
            token_storage="keyring",
            profile="default",
            auth_type="oauth",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.get_status = AsyncMock(return_value=auth_status)

            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "oauth" in result.output

    def test_status_json_includes_auth_type(self) -> None:
        import json

        auth_status = AuthStatus(
            authenticated=True,
            host="https://gitlab.com",
            username="oauthuser",
            token_valid=True,
            config_file="/home/user/.config/gltools/config.toml",
            token_storage="keyring",
            profile="default",
            auth_type="oauth",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.get_status = AsyncMock(return_value=auth_status)

            result = runner.invoke(app, ["--json", "auth", "status"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["auth_type"] == "oauth"


class TestAuthLoginEdgeCases:
    """Edge case tests for auth login."""

    def test_login_aborts_on_no_input(self) -> None:
        """When no token is provided, prompt aborts."""
        result = runner.invoke(
            app,
            ["auth", "login"],
            input="https://gitlab.com\n\n",
        )
        # typer.prompt retries on empty input then aborts
        assert result.exit_code == 1


class TestAuthStatusJSON:
    """Additional JSON validation tests for auth status."""

    def test_status_json_has_all_fields(self) -> None:
        import json

        auth_status = AuthStatus(
            authenticated=True,
            host="https://gitlab.com",
            username="testuser",
            token_valid=True,
            config_file="/home/user/.config/gltools/config.toml",
            token_storage="keyring",
            profile="default",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.get_status = AsyncMock(return_value=auth_status)

            result = runner.invoke(app, ["--json", "auth", "status"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["authenticated"] is True
        assert data["data"]["host"] == "https://gitlab.com"
        assert data["data"]["username"] == "testuser"
        assert data["data"]["token_valid"] is True
        assert data["data"]["token_storage"] == "keyring"
        assert data["data"]["profile"] == "default"

    def test_status_token_invalid(self) -> None:
        auth_status = AuthStatus(
            authenticated=True,
            host="https://gitlab.com",
            username="testuser",
            token_valid=False,
            config_file="/home/user/.config/gltools/config.toml",
            token_storage="keyring",
            profile="default",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.get_status = AsyncMock(return_value=auth_status)

            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "invalid" in result.output


class TestAuthLogoutJSON:
    """Additional JSON validation for auth logout."""

    def test_logout_json_has_profile(self) -> None:
        import json

        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.logout.return_value = True

            result = runner.invoke(app, ["--json", "auth", "logout"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["profile"] == "default"

    def test_logout_json_no_credentials_has_profile(self) -> None:
        import json

        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.logout.return_value = False

            result = runner.invoke(app, ["--json", "auth", "logout"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["profile"] == "default"


class TestAuthLoginJSON:
    """Additional JSON validation for auth login."""

    def test_login_json_success_has_all_fields(self) -> None:
        login_result = LoginResult(
            success=True,
            username="testuser",
            host="https://gitlab.com",
            token_storage="keyring",
        )
        with patch("gltools.cli.auth.AuthService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.login = AsyncMock(return_value=login_result)

            result = runner.invoke(
                app,
                ["--json", "auth", "login"],
                input="https://gitlab.com\nglpat-test123\n",
            )

        assert result.exit_code == 0
        # Output includes prompt text + JSON; verify JSON portion is valid
        assert '"username"' in result.output
        assert '"testuser"' in result.output
        assert '"host"' in result.output
        assert '"token_storage"' in result.output
