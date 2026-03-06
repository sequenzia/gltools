"""Keyring integration for secure PAT storage.

Stores GitLab Personal Access Tokens in the system keyring (macOS Keychain,
Linux Secret Service) with a config file fallback when the keyring is
unavailable or inaccessible.
"""

from __future__ import annotations

import logging
import stat
from typing import TYPE_CHECKING

import keyring
from keyring.errors import KeyringError, NoKeyringError

if TYPE_CHECKING:
    from pathlib import Path

from gltools.config.settings import get_config_dir

logger = logging.getLogger(__name__)

SERVICE_NAME = "gltools"


def _keyring_key(profile: str) -> str:
    """Return the keyring username key scoped to a profile."""
    return f"token:{profile}"


def _token_file_path(profile: str) -> Path:
    """Return the path for file-based token storage for a profile."""
    return get_config_dir() / f".token-{profile}"


def _is_keyring_available() -> bool:
    """Check whether the system keyring backend is usable."""
    try:
        backend = keyring.get_keyring()
        backend_name = type(backend).__name__
        return "fail" not in backend_name.lower() and "null" not in backend_name.lower()
    except Exception:
        return False


def store_token(token: str, *, profile: str = "default") -> None:
    """Store a token, preferring the system keyring with file fallback.

    Args:
        token: The GitLab PAT to store. Never logged.
        profile: Configuration profile name for scoped storage.
    """
    try:
        if _is_keyring_available():
            keyring.set_password(SERVICE_NAME, _keyring_key(profile), token)
            # Remove any stale file-based token
            _delete_token_file(profile)
            logger.debug("Token stored in system keyring for profile '%s'", profile)
            return
    except (KeyringError, NoKeyringError):
        logger.warning(
            "Cannot access system keyring. Token will be stored in config file."
        )
    except Exception:
        logger.warning(
            "Unexpected keyring error. Token will be stored in config file."
        )

    _write_token_file(token, profile)


def get_token(*, profile: str = "default") -> str | None:
    """Retrieve a stored token, checking keyring first then file fallback.

    Args:
        profile: Configuration profile name.

    Returns:
        The stored token, or None if no token is found.
    """
    try:
        if _is_keyring_available():
            token = keyring.get_password(SERVICE_NAME, _keyring_key(profile))
            if token is not None:
                return token
    except (KeyringError, NoKeyringError):
        logger.warning(
            "Cannot access system keyring. Falling back to config file."
        )
    except Exception:
        logger.warning(
            "Unexpected keyring error. Falling back to config file."
        )

    return _read_token_file(profile)


def delete_token(*, profile: str = "default") -> bool:
    """Delete a stored token from both keyring and file storage.

    Args:
        profile: Configuration profile name.

    Returns:
        True if a token was found and deleted, False otherwise.
    """
    deleted = False

    try:
        if _is_keyring_available():
            existing = keyring.get_password(SERVICE_NAME, _keyring_key(profile))
            if existing is not None:
                keyring.delete_password(SERVICE_NAME, _keyring_key(profile))
                deleted = True
                logger.debug("Token deleted from system keyring for profile '%s'", profile)
    except (KeyringError, NoKeyringError):
        logger.warning(
            "Cannot access system keyring for token deletion."
        )
    except Exception:
        logger.warning(
            "Unexpected keyring error during token deletion."
        )

    if _delete_token_file(profile):
        deleted = True

    return deleted


def _write_token_file(token: str, profile: str) -> None:
    """Write a token to a file with 600 permissions."""
    token_path = _token_file_path(profile)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token, encoding="utf-8")
    token_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    logger.debug("Token stored in config file for profile '%s'", profile)


def _read_token_file(profile: str) -> str | None:
    """Read a token from the file-based fallback storage."""
    token_path = _token_file_path(profile)
    if not token_path.is_file():
        return None

    # Warn if file permissions are too open
    try:
        file_stat = token_path.stat()
        mode = file_stat.st_mode & 0o777
        if mode != 0o600:
            logger.warning(
                "Token file %s has permissions %o, expected 600. "
                "Run: chmod 600 %s",
                token_path,
                mode,
                token_path,
            )
    except OSError:
        pass

    return token_path.read_text(encoding="utf-8").strip()


def _delete_token_file(profile: str) -> bool:
    """Delete the file-based token if it exists.

    Returns:
        True if the file existed and was deleted.
    """
    token_path = _token_file_path(profile)
    if token_path.is_file():
        token_path.unlink()
        return True
    return False
