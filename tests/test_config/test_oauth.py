"""Tests for OAuth2 protocol module."""

from __future__ import annotations

import hashlib
import time
from base64 import urlsafe_b64encode
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gltools.config.oauth import (
    OAuthConfig,
    OAuthError,
    OAuthTokenResponse,
    _CallbackServer,
    _generate_pkce_pair,
    authorization_code_flow,
    device_authorization_flow,
    refresh_access_token,
)


class TestOAuthDataStructures:
    def test_oauth_error_with_code(self) -> None:
        err = OAuthError("test error", error_code="access_denied")
        assert str(err) == "test error"
        assert err.error_code == "access_denied"

    def test_oauth_error_without_code(self) -> None:
        err = OAuthError("generic error")
        assert err.error_code is None

    def test_oauth_token_response_defaults(self) -> None:
        resp = OAuthTokenResponse(access_token="tok", token_type="bearer")
        assert resp.access_token == "tok"
        assert resp.refresh_token is None
        assert resp.expires_in is None
        assert resp.created_at <= time.time()

    def test_oauth_config_defaults(self) -> None:
        config = OAuthConfig(client_id="abc", host="https://gitlab.com")
        assert config.scopes == "api"


class TestPKCE:
    def test_generate_pkce_pair_format(self) -> None:
        verifier, challenge = _generate_pkce_pair()
        assert len(verifier) > 40
        assert len(challenge) > 20
        # Verify S256: challenge = base64url(sha256(verifier))
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_generate_pkce_pair_unique(self) -> None:
        pair1 = _generate_pkce_pair()
        pair2 = _generate_pkce_pair()
        assert pair1[0] != pair2[0]


class TestCallbackServer:
    def test_start_and_shutdown(self) -> None:
        server = _CallbackServer(timeout=5.0)
        port = server.start()
        assert isinstance(port, int)
        assert port > 0
        server.shutdown()

    def test_timeout_raises_error(self) -> None:
        server = _CallbackServer(timeout=0.1)
        server.start()
        try:
            with pytest.raises(OAuthError, match="timed out"):
                server.wait_for_callback()
        finally:
            server.shutdown()


class TestAuthorizationCodeFlow:
    @pytest.mark.asyncio
    async def test_successful_flow(self) -> None:
        config = OAuthConfig(client_id="test-id", host="https://gitlab.com")

        mock_token_response = httpx.Response(
            200,
            json={
                "access_token": "new-access-token",
                "token_type": "bearer",
                "refresh_token": "new-refresh-token",
                "expires_in": 7200,
                "created_at": 1700000000,
            },
        )

        with (
            patch("gltools.config.oauth._CallbackServer") as mock_server_cls,
            patch("gltools.config.oauth.webbrowser") as mock_wb,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_server = MagicMock()
            mock_server.start.return_value = 12345
            mock_server.wait_for_callback.return_value = ("auth-code", "test-state")
            mock_server_cls.return_value = mock_server

            mock_wb.open.return_value = True

            mock_http = AsyncMock()
            mock_http.post.return_value = mock_token_response
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_http

            # We need to also mock the state to match
            with patch("gltools.config.oauth.secrets") as mock_secrets:
                mock_secrets.token_urlsafe.side_effect = ["verifier123", "test-state"]

                result = await authorization_code_flow(config)

        assert result.access_token == "new-access-token"
        assert result.refresh_token == "new-refresh-token"
        mock_server.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_state_mismatch_raises_error(self) -> None:
        config = OAuthConfig(client_id="test-id", host="https://gitlab.com")

        with (
            patch("gltools.config.oauth._CallbackServer") as mock_server_cls,
            patch("gltools.config.oauth.webbrowser") as mock_wb,
        ):
            mock_server = MagicMock()
            mock_server.start.return_value = 12345
            mock_server.wait_for_callback.return_value = ("auth-code", "wrong-state")
            mock_server_cls.return_value = mock_server
            mock_wb.open.return_value = True

            with pytest.raises(OAuthError, match="State mismatch"):
                await authorization_code_flow(config)

            mock_server.shutdown.assert_called_once()


class TestDeviceAuthorizationFlow:
    @pytest.mark.asyncio
    async def test_unsupported_gitlab_version(self) -> None:
        config = OAuthConfig(client_id="test-id", host="https://gitlab.com")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post.return_value = httpx.Response(404)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_http

            with pytest.raises(OAuthError, match="GitLab 17.2"):
                await device_authorization_flow(config)

    @pytest.mark.asyncio
    async def test_successful_device_flow(self) -> None:
        config = OAuthConfig(client_id="test-id", host="https://gitlab.com")

        device_response = httpx.Response(
            200,
            json={
                "device_code": "dev-code",
                "user_code": "ABCD-1234",
                "verification_uri": "https://gitlab.com/oauth/device",
                "expires_in": 900,
                "interval": 1,
            },
        )

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("gltools.config.oauth.webbrowser"),
            patch("gltools.config.oauth._async_sleep", new_callable=AsyncMock),
        ):
            mock_http = AsyncMock()
            mock_http.post.return_value = device_response
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_http

            # Token exchange uses a separate httpx.AsyncClient context
            # Mock _exchange_token to return success on first poll
            with patch("gltools.config.oauth._exchange_token", new_callable=AsyncMock) as mock_exchange:
                mock_exchange.return_value = OAuthTokenResponse(
                    access_token="device-token",
                    token_type="bearer",
                    refresh_token="device-refresh",
                    expires_in=7200,
                )

                result = await device_authorization_flow(config)

        assert result.access_token == "device-token"
        assert result.refresh_token == "device-refresh"


class TestRefreshAccessToken:
    @pytest.mark.asyncio
    async def test_successful_refresh(self) -> None:
        with patch("gltools.config.oauth._exchange_token", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = OAuthTokenResponse(
                access_token="refreshed-token",
                token_type="bearer",
                refresh_token="new-refresh",
                expires_in=7200,
            )

            result = await refresh_access_token("https://gitlab.com", "client-id", "old-refresh")

        assert result.access_token == "refreshed-token"
        mock_exchange.assert_called_once_with(
            "https://gitlab.com",
            {
                "grant_type": "refresh_token",
                "refresh_token": "old-refresh",
                "client_id": "client-id",
            },
        )

    @pytest.mark.asyncio
    async def test_refresh_failure(self) -> None:
        with patch("gltools.config.oauth._exchange_token", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.side_effect = OAuthError("Refresh token revoked", error_code="invalid_grant")

            with pytest.raises(OAuthError, match="revoked"):
                await refresh_access_token("https://gitlab.com", "client-id", "bad-refresh")


class TestExchangeToken:
    @pytest.mark.asyncio
    async def test_non_200_raises_error(self) -> None:
        from gltools.config.oauth import _exchange_token

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post.return_value = httpx.Response(
                400,
                json={"error": "invalid_grant", "error_description": "Token expired"},
                headers={"content-type": "application/json"},
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_http

            with pytest.raises(OAuthError, match="Token expired"):
                await _exchange_token("https://gitlab.com", {"grant_type": "authorization_code"})
