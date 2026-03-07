"""Authentication service coordinating config, keyring, and GitLab API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from gltools.config.keyring import (
    _is_keyring_available,
    delete_token,
    get_token,
    store_refresh_token,
    store_token,
)
from gltools.config.settings import (
    get_config_path,
    load_profile_from_toml,
    write_config,
)

logger = logging.getLogger(__name__)


@dataclass
class AuthStatus:
    """Current authentication state."""

    authenticated: bool
    host: str | None = None
    username: str | None = None
    token_valid: bool = False
    config_file: str | None = None
    token_storage: str | None = None
    profile: str = "default"
    auth_type: str = "pat"


@dataclass
class LoginResult:
    """Result of a login attempt."""

    success: bool
    username: str | None = None
    host: str | None = None
    token_storage: str | None = None
    auth_type: str = "pat"
    error: str | None = None


class AuthService:
    """Coordinates authentication operations between config, keyring, and GitLab API."""

    def __init__(self, *, profile: str = "default") -> None:
        self._profile = profile

    @property
    def profile(self) -> str:
        """Current profile name."""
        return self._profile

    async def validate_token(self, host: str, token: str, *, auth_type: str = "pat") -> dict[str, Any] | None:
        """Validate a token by calling GET /user on the GitLab API.

        Returns:
            User data dict on success, None on failure.
        """
        from gltools.client.exceptions import AuthenticationError as GitLabAuthError
        from gltools.client.exceptions import ConnectionError as GitLabConnError
        from gltools.client.exceptions import GitLabClientError
        from gltools.client.exceptions import TimeoutError as GitLabTimeout
        from gltools.client.http import GitLabHTTPClient, RetryConfig

        client = GitLabHTTPClient(
            host=host,
            token=token,
            auth_type=auth_type,
            retry_config=RetryConfig(max_retries=2, base_delay=0.5),
        )
        try:
            response = await client.get("/user")
            return response.json()
        except GitLabAuthError:
            return None
        except GitLabConnError:
            raise ConnectionError(f"Unable to connect to {host}. Check the URL and your network connection.") from None
        except GitLabTimeout:
            raise ConnectionError(f"Connection to {host} timed out. The server may be unreachable.") from None
        except GitLabClientError:
            return None
        finally:
            await client.close()

    async def login(self, host: str, token: str) -> LoginResult:
        """Validate token, store credentials, and save config.

        Args:
            host: GitLab instance URL.
            token: Personal access token.

        Returns:
            LoginResult with outcome details.
        """
        try:
            user_data = await self.validate_token(host, token)
        except ConnectionError as exc:
            return LoginResult(success=False, error=str(exc))

        if user_data is None:
            return LoginResult(
                success=False,
                error="Authentication failed: token may be expired or invalid.",
            )

        username = user_data.get("username", "unknown")

        store_token(token, profile=self._profile)

        token_storage = "keyring" if _is_keyring_available() else "config file"

        self._save_profile_config(host, auth_type="pat")

        return LoginResult(
            success=True,
            username=username,
            host=host,
            token_storage=token_storage,
            auth_type="pat",
        )

    async def oauth_login(
        self,
        host: str,
        client_id: str,
        *,
        method: str = "web",
    ) -> LoginResult:
        """Perform OAuth2 login flow."""
        from gltools.config.oauth import (
            OAuthConfig,
            OAuthError,
            authorization_code_flow,
            device_authorization_flow,
        )

        config = OAuthConfig(client_id=client_id, host=host)
        try:
            if method == "device":
                result = await device_authorization_flow(config)
            else:
                result = await authorization_code_flow(config)
        except OAuthError as exc:
            return LoginResult(success=False, error=str(exc))

        user_data = await self.validate_token(host, result.access_token, auth_type="oauth")
        if user_data is None:
            return LoginResult(success=False, error="OAuth succeeded but token validation failed.")

        store_token(result.access_token, profile=self._profile)
        if result.refresh_token:
            store_refresh_token(result.refresh_token, profile=self._profile)

        self._save_profile_config(host, auth_type="oauth", client_id=client_id)

        token_storage = "keyring" if _is_keyring_available() else "config file"
        return LoginResult(
            success=True,
            username=user_data.get("username", "unknown"),
            host=host,
            token_storage=token_storage,
            auth_type="oauth",
        )

    def _save_profile_config(self, host: str, *, auth_type: str = "pat", client_id: str | None = None) -> None:
        """Save host, auth_type, and client_id to the TOML config file."""
        config_path = get_config_path()

        existing: dict[str, Any] = {}
        if config_path.is_file():
            import tomllib

            with open(config_path, "rb") as f:
                try:
                    existing = tomllib.load(f)
                except Exception:
                    existing = {}

        profiles = existing.get("profiles", {})
        profile_data = profiles.get(self._profile, {})
        profile_data["host"] = host
        profile_data["auth_type"] = auth_type
        if client_id:
            profile_data["client_id"] = client_id
        elif "client_id" in profile_data:
            del profile_data["client_id"]
        profiles[self._profile] = profile_data
        existing["profiles"] = profiles

        toml_content = _dict_to_toml(existing)
        write_config(config_path, toml_content)

    async def get_status(self) -> AuthStatus:
        """Get the current authentication status.

        Returns:
            AuthStatus with current state.
        """
        config_path = get_config_path()
        config_file_str = str(config_path)

        profile_data = load_profile_from_toml(config_path, self._profile)
        host = profile_data.get("host")
        auth_type = profile_data.get("auth_type", "pat")
        token = get_token(profile=self._profile)

        if not token:
            return AuthStatus(
                authenticated=False,
                host=host,
                config_file=config_file_str,
                profile=self._profile,
                auth_type=auth_type,
            )

        token_storage = "keyring" if _is_keyring_available() else "config file"

        if host:
            try:
                user_data = await self.validate_token(host, token, auth_type=auth_type)
                if user_data:
                    return AuthStatus(
                        authenticated=True,
                        host=host,
                        username=user_data.get("username"),
                        token_valid=True,
                        config_file=config_file_str,
                        token_storage=token_storage,
                        profile=self._profile,
                        auth_type=auth_type,
                    )
                return AuthStatus(
                    authenticated=True,
                    host=host,
                    token_valid=False,
                    config_file=config_file_str,
                    token_storage=token_storage,
                    profile=self._profile,
                    auth_type=auth_type,
                )
            except ConnectionError:
                return AuthStatus(
                    authenticated=True,
                    host=host,
                    token_valid=False,
                    config_file=config_file_str,
                    token_storage=token_storage,
                    profile=self._profile,
                    auth_type=auth_type,
                )

        return AuthStatus(
            authenticated=True,
            host=host,
            token_valid=False,
            config_file=config_file_str,
            token_storage=token_storage,
            profile=self._profile,
            auth_type=auth_type,
        )

    def logout(self) -> bool:
        """Remove stored credentials for the current profile.

        Returns:
            True if credentials were found and removed.
        """
        return delete_token(profile=self._profile)


def _dict_to_toml(data: dict[str, Any]) -> str:
    """Convert a simple dict to TOML string (supports nested tables)."""
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, dict):
                    lines.append(f"[{key}.{sub_key}]")
                    for k, v in sub_value.items():
                        lines.append(f'{k} = "{v}"')
                    lines.append("")
                else:
                    if not any(line.startswith(f"[{key}]") for line in lines):
                        lines.append(f"[{key}]")
                    lines.append(f'{sub_key} = "{sub_value}"')
        else:
            lines.append(f'{key} = "{value}"')
    return "\n".join(lines) + "\n"
