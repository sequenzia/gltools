"""Tests for the authentication service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gltools.client.exceptions import (
    AuthenticationError as GitLabAuthError,
)
from gltools.client.exceptions import (
    ConnectionError as GitLabConnError,
)
from gltools.client.exceptions import (
    TimeoutError as GitLabTimeout,
)
from gltools.services.auth import AuthService


class TestValidateToken:
    """Tests for token validation against GitLab API."""

    def _mock_client(self, **kwargs: object) -> MagicMock:
        """Create a mock GitLabHTTPClient with async get/close."""
        client = MagicMock()
        client.get = AsyncMock(**kwargs)
        client.close = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_valid_token_returns_user_data(self) -> None:
        service = AuthService()
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 1, "username": "testuser", "name": "Test User"}

        client = self._mock_client(return_value=mock_response)
        with patch("gltools.client.http.GitLabHTTPClient", return_value=client):
            result = await service.validate_token("https://gitlab.com", "glpat-valid")

        assert result is not None
        assert result["username"] == "testuser"
        client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self) -> None:
        service = AuthService()
        client = self._mock_client(side_effect=GitLabAuthError())
        with patch("gltools.client.http.GitLabHTTPClient", return_value=client):
            result = await service.validate_token("https://gitlab.com", "glpat-bad")

        assert result is None
        client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_error_raises_connection_error(self) -> None:
        service = AuthService()
        client = self._mock_client(side_effect=GitLabConnError())
        with (
            patch("gltools.client.http.GitLabHTTPClient", return_value=client),
            pytest.raises(ConnectionError, match="Unable to connect"),
        ):
            await service.validate_token("https://gitlab.bad", "glpat-test")
        client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_timeout_raises_connection_error(self) -> None:
        service = AuthService()
        client = self._mock_client(side_effect=GitLabTimeout())
        with (
            patch("gltools.client.http.GitLabHTTPClient", return_value=client),
            pytest.raises(ConnectionError, match="timed out"),
        ):
            await service.validate_token("https://gitlab.com", "glpat-test")
        client.close.assert_awaited_once()


class TestLogin:
    """Tests for the login flow."""

    @pytest.mark.asyncio
    async def test_successful_login(self) -> None:
        service = AuthService(profile="default")
        with (
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value={"username": "testuser", "id": 1},
            ),
            patch("gltools.services.auth.store_token") as mock_store,
            patch("gltools.services.auth._is_keyring_available", return_value=True),
            patch.object(service, "_save_profile_config"),
        ):
            result = await service.login("https://gitlab.com", "glpat-valid")

        assert result.success is True
        assert result.username == "testuser"
        assert result.host == "https://gitlab.com"
        assert result.token_storage == "keyring"
        mock_store.assert_called_once_with("glpat-valid", profile="default")

    @pytest.mark.asyncio
    async def test_login_invalid_token(self) -> None:
        service = AuthService()
        with patch.object(
            service,
            "validate_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await service.login("https://gitlab.com", "glpat-bad")

        assert result.success is False
        assert "Authentication failed" in (result.error or "")

    @pytest.mark.asyncio
    async def test_login_network_error(self) -> None:
        service = AuthService()
        with patch.object(
            service,
            "validate_token",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Unable to connect"),
        ):
            result = await service.login("https://gitlab.bad", "glpat-test")

        assert result.success is False
        assert "Unable to connect" in (result.error or "")

    @pytest.mark.asyncio
    async def test_login_keyring_unavailable_falls_back(self) -> None:
        service = AuthService(profile="default")
        with (
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value={"username": "testuser", "id": 1},
            ),
            patch("gltools.services.auth.store_token"),
            patch("gltools.services.auth._is_keyring_available", return_value=False),
            patch.object(service, "_save_profile_config"),
        ):
            result = await service.login("https://gitlab.com", "glpat-valid")

        assert result.success is True
        assert result.token_storage == "config file"

    @pytest.mark.asyncio
    async def test_login_overwrites_existing(self) -> None:
        """Login when already authenticated should overwrite existing credentials."""
        service = AuthService(profile="default")
        with (
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value={"username": "newuser", "id": 2},
            ),
            patch("gltools.services.auth.store_token") as mock_store,
            patch("gltools.services.auth._is_keyring_available", return_value=True),
            patch.object(service, "_save_profile_config"),
        ):
            result = await service.login("https://gitlab.com", "glpat-new")

        assert result.success is True
        assert result.username == "newuser"
        mock_store.assert_called_once_with("glpat-new", profile="default")


class TestGetStatus:
    """Tests for authentication status checks."""

    @pytest.mark.asyncio
    async def test_not_authenticated(self, tmp_path: object) -> None:
        service = AuthService()
        with (
            patch("gltools.services.auth.get_config_path", return_value=tmp_path / "config.toml"),  # type: ignore[operator]
            patch("gltools.services.auth.load_profile_from_toml", return_value={}),
            patch("gltools.services.auth.get_token", return_value=None),
        ):
            status = await service.get_status()

        assert status.authenticated is False
        assert status.profile == "default"

    @pytest.mark.asyncio
    async def test_authenticated_with_valid_token(self) -> None:
        service = AuthService()
        with (
            patch("gltools.services.auth.get_config_path"),
            patch("gltools.services.auth.load_profile_from_toml", return_value={"host": "https://gitlab.com"}),
            patch("gltools.services.auth.get_token", return_value="glpat-valid"),
            patch("gltools.services.auth._is_keyring_available", return_value=True),
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value={"username": "testuser"},
            ),
        ):
            status = await service.get_status()

        assert status.authenticated is True
        assert status.username == "testuser"
        assert status.token_valid is True
        assert status.token_storage == "keyring"

    @pytest.mark.asyncio
    async def test_authenticated_with_invalid_token(self) -> None:
        service = AuthService()
        with (
            patch("gltools.services.auth.get_config_path"),
            patch("gltools.services.auth.load_profile_from_toml", return_value={"host": "https://gitlab.com"}),
            patch("gltools.services.auth.get_token", return_value="glpat-expired"),
            patch("gltools.services.auth._is_keyring_available", return_value=True),
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            status = await service.get_status()

        assert status.authenticated is True
        assert status.token_valid is False


class TestLogout:
    """Tests for credential removal."""

    def test_logout_deletes_token(self) -> None:
        service = AuthService(profile="default")
        with patch("gltools.services.auth.delete_token", return_value=True) as mock_del:
            result = service.logout()

        assert result is True
        mock_del.assert_called_once_with(profile="default")

    def test_logout_no_credentials(self) -> None:
        service = AuthService(profile="default")
        with patch("gltools.services.auth.delete_token", return_value=False):
            result = service.logout()

        assert result is False


class TestOAuthLogin:
    """Tests for the OAuth login flow."""

    @pytest.mark.asyncio
    async def test_successful_oauth_web_login(self) -> None:
        from gltools.config.oauth import OAuthTokenResponse

        service = AuthService(profile="default")
        token_resp = OAuthTokenResponse(
            access_token="oauth-token",
            token_type="bearer",
            refresh_token="oauth-refresh",
            expires_in=7200,
        )

        with (
            patch(
                "gltools.config.oauth.authorization_code_flow",
                new_callable=AsyncMock,
                return_value=token_resp,
            ),
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value={"username": "oauthuser", "id": 1},
            ),
            patch("gltools.services.auth.store_token") as mock_store,
            patch("gltools.services.auth.store_refresh_token") as mock_store_refresh,
            patch("gltools.services.auth._is_keyring_available", return_value=True),
            patch.object(service, "_save_profile_config"),
        ):
            result = await service.oauth_login("https://gitlab.com", "client-id", method="web")

        assert result.success is True
        assert result.username == "oauthuser"
        assert result.auth_type == "oauth"
        mock_store.assert_called_once_with("oauth-token", profile="default")
        mock_store_refresh.assert_called_once_with("oauth-refresh", profile="default")

    @pytest.mark.asyncio
    async def test_oauth_login_token_validation_fails(self) -> None:
        from gltools.config.oauth import OAuthTokenResponse

        service = AuthService(profile="default")
        token_resp = OAuthTokenResponse(
            access_token="oauth-token",
            token_type="bearer",
        )

        with (
            patch(
                "gltools.config.oauth.authorization_code_flow",
                new_callable=AsyncMock,
                return_value=token_resp,
            ),
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await service.oauth_login("https://gitlab.com", "client-id")

        assert result.success is False
        assert "validation failed" in (result.error or "")

    @pytest.mark.asyncio
    async def test_oauth_login_flow_error(self) -> None:
        from gltools.config.oauth import OAuthError

        service = AuthService(profile="default")

        with patch(
            "gltools.config.oauth.authorization_code_flow",
            new_callable=AsyncMock,
            side_effect=OAuthError("Browser auth failed"),
        ):
            result = await service.oauth_login("https://gitlab.com", "client-id")

        assert result.success is False
        assert "Browser auth failed" in (result.error or "")

    @pytest.mark.asyncio
    async def test_oauth_device_flow(self) -> None:
        from gltools.config.oauth import OAuthTokenResponse

        service = AuthService(profile="default")
        token_resp = OAuthTokenResponse(
            access_token="device-token",
            token_type="bearer",
            refresh_token="device-refresh",
            expires_in=7200,
        )

        with (
            patch(
                "gltools.config.oauth.device_authorization_flow",
                new_callable=AsyncMock,
                return_value=token_resp,
            ),
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value={"username": "deviceuser", "id": 2},
            ),
            patch("gltools.services.auth.store_token"),
            patch("gltools.services.auth.store_refresh_token"),
            patch("gltools.services.auth._is_keyring_available", return_value=True),
            patch.object(service, "_save_profile_config"),
        ):
            result = await service.oauth_login("https://gitlab.com", "client-id", method="device")

        assert result.success is True
        assert result.username == "deviceuser"
        assert result.auth_type == "oauth"

    @pytest.mark.asyncio
    async def test_oauth_no_refresh_token(self) -> None:
        from gltools.config.oauth import OAuthTokenResponse

        service = AuthService(profile="default")
        token_resp = OAuthTokenResponse(
            access_token="oauth-token",
            token_type="bearer",
            refresh_token=None,
        )

        with (
            patch(
                "gltools.config.oauth.authorization_code_flow",
                new_callable=AsyncMock,
                return_value=token_resp,
            ),
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value={"username": "user", "id": 1},
            ),
            patch("gltools.services.auth.store_token"),
            patch("gltools.services.auth.store_refresh_token") as mock_store_refresh,
            patch("gltools.services.auth._is_keyring_available", return_value=True),
            patch.object(service, "_save_profile_config"),
        ):
            result = await service.oauth_login("https://gitlab.com", "client-id")

        assert result.success is True
        mock_store_refresh.assert_not_called()


class TestGetStatusAuthType:
    """Tests for auth_type in status output."""

    @pytest.mark.asyncio
    async def test_status_includes_auth_type(self) -> None:
        service = AuthService()
        with (
            patch("gltools.services.auth.get_config_path"),
            patch(
                "gltools.services.auth.load_profile_from_toml",
                return_value={"host": "https://gitlab.com", "auth_type": "oauth"},
            ),
            patch("gltools.services.auth.get_token", return_value="oauth-token"),
            patch("gltools.services.auth._is_keyring_available", return_value=True),
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value={"username": "testuser"},
            ),
        ):
            status = await service.get_status()

        assert status.auth_type == "oauth"

    @pytest.mark.asyncio
    async def test_status_defaults_to_pat(self) -> None:
        service = AuthService()
        with (
            patch("gltools.services.auth.get_config_path"),
            patch("gltools.services.auth.load_profile_from_toml", return_value={"host": "https://gitlab.com"}),
            patch("gltools.services.auth.get_token", return_value="pat-token"),
            patch("gltools.services.auth._is_keyring_available", return_value=True),
            patch.object(
                service,
                "validate_token",
                new_callable=AsyncMock,
                return_value={"username": "testuser"},
            ),
        ):
            status = await service.get_status()

        assert status.auth_type == "pat"


class TestSaveProfileConfig:
    """Tests for config file writing."""

    def test_saves_host_to_new_config(self, tmp_path: object) -> None:
        from pathlib import Path

        config_path = Path(str(tmp_path)) / "config.toml"
        service = AuthService(profile="default")
        with (
            patch("gltools.services.auth.get_config_path", return_value=config_path),
            patch("gltools.services.auth.write_config") as mock_write,
        ):
            service._save_profile_config("https://gitlab.com")

        mock_write.assert_called_once()
        written_content = mock_write.call_args[0][1]
        assert "https://gitlab.com" in written_content
        assert "pat" in written_content

    def test_saves_oauth_config(self, tmp_path: object) -> None:
        from pathlib import Path

        config_path = Path(str(tmp_path)) / "config.toml"
        service = AuthService(profile="default")
        with (
            patch("gltools.services.auth.get_config_path", return_value=config_path),
            patch("gltools.services.auth.write_config") as mock_write,
        ):
            service._save_profile_config("https://gitlab.com", auth_type="oauth", client_id="abc123")

        written_content = mock_write.call_args[0][1]
        assert "oauth" in written_content
        assert "abc123" in written_content

    def test_preserves_existing_profiles(self, tmp_path: object) -> None:
        from pathlib import Path

        config_path = Path(str(tmp_path)) / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('[profiles.work]\nhost = "https://work.gitlab.com"\n')

        service = AuthService(profile="default")
        with patch("gltools.services.auth.get_config_path", return_value=config_path):
            with patch("gltools.services.auth.write_config") as mock_write:
                service._save_profile_config("https://gitlab.com")

            written_content = mock_write.call_args[0][1]
            assert "work" in written_content
