"""Tests for keyring integration module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gltools.config.keyring import (
    SERVICE_NAME,
    _keyring_key,
    _token_file_path,
    delete_token,
    get_token,
    store_token,
)


class TestKeyringKey:
    """Tests for profile-scoped keyring keys."""

    def test_default_profile(self) -> None:
        assert _keyring_key("default") == "token:default"

    def test_custom_profile(self) -> None:
        assert _keyring_key("work") == "token:work"


class TestTokenFilePath:
    """Tests for file-based token path generation."""

    def test_default_profile_path(self, tmp_path: object) -> None:
        with patch("gltools.config.keyring.get_config_dir", return_value=pytest.importorskip("pathlib").Path("/fake")):
            path = _token_file_path("default")
            assert path.name == ".token-default"

    def test_profile_scoped_path(self) -> None:
        with patch("gltools.config.keyring.get_config_dir", return_value=pytest.importorskip("pathlib").Path("/fake")):
            path = _token_file_path("work")
            assert path.name == ".token-work"


class TestStoreToken:
    """Tests for storing tokens."""

    def test_stores_in_keyring_when_available(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._delete_token_file") as mock_del,
        ):
            store_token("glpat-abc123", profile="default")
            mock_kr.set_password.assert_called_once_with(SERVICE_NAME, "token:default", "glpat-abc123")
            mock_del.assert_called_once_with("default")

    def test_falls_back_to_file_when_keyring_unavailable(self, tmp_path: object) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=False),
            patch("gltools.config.keyring._write_token_file") as mock_write,
        ):
            store_token("glpat-abc123", profile="default")
            mock_write.assert_called_once_with("glpat-abc123", "default")

    def test_falls_back_on_keyring_error(self) -> None:
        from keyring.errors import KeyringError

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._write_token_file") as mock_write,
        ):
            mock_kr.set_password.side_effect = KeyringError("denied")
            store_token("glpat-abc123", profile="default")
            mock_write.assert_called_once_with("glpat-abc123", "default")

    def test_multiple_profiles_store_separately(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._delete_token_file"),
        ):
            store_token("token-work", profile="work")
            store_token("token-personal", profile="personal")
            calls = mock_kr.set_password.call_args_list
            assert calls[0].args == (SERVICE_NAME, "token:work", "token-work")
            assert calls[1].args == (SERVICE_NAME, "token:personal", "token-personal")


class TestGetToken:
    """Tests for retrieving tokens."""

    def test_retrieves_from_keyring(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
        ):
            mock_kr.get_password.return_value = "glpat-abc123"
            result = get_token(profile="default")
            assert result == "glpat-abc123"
            mock_kr.get_password.assert_called_once_with(SERVICE_NAME, "token:default")

    def test_falls_back_to_file_when_keyring_unavailable(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=False),
            patch("gltools.config.keyring._read_token_file", return_value="file-token") as mock_read,
        ):
            result = get_token(profile="default")
            assert result == "file-token"
            mock_read.assert_called_once_with("default")

    def test_falls_back_to_file_on_keyring_error(self) -> None:
        from keyring.errors import KeyringError

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._read_token_file", return_value="file-token"),
        ):
            mock_kr.get_password.side_effect = KeyringError("denied")
            result = get_token(profile="default")
            assert result == "file-token"

    def test_returns_none_when_no_token(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._read_token_file", return_value=None),
        ):
            mock_kr.get_password.return_value = None
            result = get_token(profile="default")
            assert result is None


class TestDeleteToken:
    """Tests for deleting tokens."""

    def test_deletes_from_keyring(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._delete_token_file", return_value=False),
            patch("gltools.config.keyring._delete_file", return_value=False),
        ):
            mock_kr.get_password.side_effect = lambda svc, key: "glpat-abc123" if key == "token:default" else None
            result = delete_token(profile="default")
            assert result is True
            mock_kr.delete_password.assert_any_call(SERVICE_NAME, "token:default")

    def test_deletes_file_fallback(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=False),
            patch("gltools.config.keyring._delete_token_file", return_value=True),
        ):
            result = delete_token(profile="default")
            assert result is True

    def test_returns_false_when_nothing_to_delete(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._delete_token_file", return_value=False),
        ):
            mock_kr.get_password.return_value = None
            result = delete_token(profile="default")
            assert result is False

    def test_handles_keyring_error_on_delete(self) -> None:
        from keyring.errors import KeyringError

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._delete_token_file", return_value=True),
        ):
            mock_kr.get_password.side_effect = KeyringError("denied")
            result = delete_token(profile="default")
            assert result is True  # file fallback was deleted


class TestFileStorage:
    """Integration-style tests for file-based token storage."""

    def test_write_and_read_token_file(self, tmp_path: object) -> None:
        from pathlib import Path

        fake_dir = Path(str(tmp_path)) / "gltools"
        with patch("gltools.config.keyring.get_config_dir", return_value=fake_dir):
            from gltools.config.keyring import _read_token_file, _write_token_file

            _write_token_file("secret-token", "default")
            token_path = fake_dir / ".token-default"
            assert token_path.exists()
            # Check 600 permissions
            mode = token_path.stat().st_mode & 0o777
            assert mode == 0o600

            result = _read_token_file("default")
            assert result == "secret-token"

    def test_delete_token_file(self, tmp_path: object) -> None:
        from pathlib import Path

        fake_dir = Path(str(tmp_path)) / "gltools"
        with patch("gltools.config.keyring.get_config_dir", return_value=fake_dir):
            from gltools.config.keyring import _delete_token_file, _write_token_file

            _write_token_file("secret-token", "default")
            assert _delete_token_file("default") is True
            assert _delete_token_file("default") is False  # already gone

    def test_read_nonexistent_token_file(self, tmp_path: object) -> None:
        from pathlib import Path

        fake_dir = Path(str(tmp_path)) / "gltools"
        with patch("gltools.config.keyring.get_config_dir", return_value=fake_dir):
            from gltools.config.keyring import _read_token_file

            assert _read_token_file("default") is None

    def test_warns_on_wrong_permissions(self, tmp_path: object, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        from pathlib import Path

        fake_dir = Path(str(tmp_path)) / "gltools"
        with patch("gltools.config.keyring.get_config_dir", return_value=fake_dir):
            from gltools.config.keyring import _read_token_file, _write_token_file

            _write_token_file("secret-token", "default")
            token_path = fake_dir / ".token-default"
            token_path.chmod(0o644)  # too open

            with caplog.at_level(logging.WARNING, logger="gltools.config.keyring"):
                result = _read_token_file("default")

            assert result == "secret-token"
            assert "permissions" in caplog.text.lower()


class TestRefreshTokenKeyringKey:
    """Tests for refresh token keyring key generation."""

    def test_default_profile(self) -> None:
        from gltools.config.keyring import _refresh_token_keyring_key

        assert _refresh_token_keyring_key("default") == "refresh_token:default"

    def test_custom_profile(self) -> None:
        from gltools.config.keyring import _refresh_token_keyring_key

        assert _refresh_token_keyring_key("work") == "refresh_token:work"


class TestRefreshTokenFilePath:
    """Tests for refresh token file path generation."""

    def test_default_profile_path(self) -> None:
        from gltools.config.keyring import _refresh_token_file_path

        with patch("gltools.config.keyring.get_config_dir", return_value=pytest.importorskip("pathlib").Path("/fake")):
            path = _refresh_token_file_path("default")
            assert path.name == ".refresh-token-default"


class TestStoreRefreshToken:
    """Tests for storing refresh tokens."""

    def test_stores_in_keyring_when_available(self) -> None:
        from gltools.config.keyring import store_refresh_token

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._delete_file") as mock_del,
        ):
            store_refresh_token("refresh-tok", profile="default")
            mock_kr.set_password.assert_called_once_with(SERVICE_NAME, "refresh_token:default", "refresh-tok")
            mock_del.assert_called_once()

    def test_falls_back_to_file_when_keyring_unavailable(self) -> None:
        from gltools.config.keyring import store_refresh_token

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=False),
            patch("gltools.config.keyring._write_file") as mock_write,
        ):
            store_refresh_token("refresh-tok", profile="default")
            mock_write.assert_called_once()


class TestGetRefreshToken:
    """Tests for retrieving refresh tokens."""

    def test_retrieves_from_keyring(self) -> None:
        from gltools.config.keyring import get_refresh_token

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
        ):
            mock_kr.get_password.return_value = "refresh-tok"
            result = get_refresh_token(profile="default")
            assert result == "refresh-tok"
            mock_kr.get_password.assert_called_once_with(SERVICE_NAME, "refresh_token:default")

    def test_returns_none_when_no_token(self) -> None:
        from gltools.config.keyring import get_refresh_token

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._read_file", return_value=None),
        ):
            mock_kr.get_password.return_value = None
            result = get_refresh_token(profile="default")
            assert result is None


class TestDeleteRefreshToken:
    """Tests for deleting refresh tokens."""

    def test_deletes_from_keyring(self) -> None:
        from gltools.config.keyring import delete_refresh_token

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._delete_file", return_value=False),
        ):
            mock_kr.get_password.return_value = "refresh-tok"
            result = delete_refresh_token(profile="default")
            assert result is True
            mock_kr.delete_password.assert_called_once_with(SERVICE_NAME, "refresh_token:default")

    def test_returns_false_when_nothing_to_delete(self) -> None:
        from gltools.config.keyring import delete_refresh_token

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._delete_file", return_value=False),
        ):
            mock_kr.get_password.return_value = None
            result = delete_refresh_token(profile="default")
            assert result is False


class TestDeleteTokenCleansUpRefresh:
    """Verify that delete_token also removes refresh tokens."""

    def test_delete_token_calls_delete_refresh_token(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=False),
            patch("gltools.config.keyring._delete_token_file", return_value=True),
            patch("gltools.config.keyring.delete_refresh_token") as mock_del_refresh,
        ):
            delete_token(profile="default")
            mock_del_refresh.assert_called_once_with(profile="default")


class TestTokenNeverLogged:
    """Verify tokens are never included in log output."""

    def test_store_does_not_log_token(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with (
            caplog.at_level(logging.DEBUG, logger="gltools.config.keyring"),
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring"),
            patch("gltools.config.keyring._delete_token_file"),
        ):
            store_token("glpat-supersecret", profile="default")

        assert "glpat-supersecret" not in caplog.text

    def test_get_does_not_log_token(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with (
            caplog.at_level(logging.DEBUG, logger="gltools.config.keyring"),
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
        ):
            mock_kr.get_password.return_value = "glpat-supersecret"
            get_token(profile="default")

        assert "glpat-supersecret" not in caplog.text
