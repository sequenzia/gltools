"""Configuration management for gltools using Pydantic Settings.

Supports layered configuration with precedence:
1. CLI flags (highest)
2. Environment variables (GLTOOLS_*)
3. Config file (~/.config/gltools/config.toml)
4. Defaults (lowest)
"""

from __future__ import annotations

import os
import stat
import tomllib
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


def get_config_dir() -> Path:
    """Return the XDG-compliant config directory for gltools."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "gltools"
    return Path.home() / ".config" / "gltools"


def get_config_path() -> Path:
    """Return the path to the gltools config file."""
    return get_config_dir() / "config.toml"


class ConfigFileError(Exception):
    """Raised when the config file cannot be parsed."""


class MissingFieldError(Exception):
    """Raised when a required field is missing from configuration."""


class ProfileNotFoundError(Exception):
    """Raised when a requested profile does not exist in the config file."""


def list_profiles(config_path: Path | None = None) -> list[str]:
    """List all available profile names from the config file.

    Args:
        config_path: Path to the TOML config file. Defaults to standard location.

    Returns:
        Sorted list of profile names. Empty list if no config file or no profiles.
    """
    if config_path is None:
        config_path = get_config_path()

    if not config_path.is_file():
        return []

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError:
        return []

    profiles = data.get("profiles", {})
    return sorted(profiles.keys())


def load_profile_from_toml(
    config_path: Path,
    profile_name: str = "default",
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Load configuration values from a TOML config file for a given profile.

    Args:
        config_path: Path to the TOML config file.
        profile_name: Name of the profile to load.
        strict: If True, raise ProfileNotFoundError when the profile doesn't exist
                and other profiles are available.

    Returns:
        Dictionary of configuration values from the profile.

    Raises:
        ConfigFileError: If the TOML file has invalid syntax.
        ProfileNotFoundError: If strict=True and profile is not found.
    """
    if not config_path.is_file():
        return {}

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigFileError(f"Invalid TOML syntax in {config_path}: {e}") from e

    profiles = data.get("profiles", {})
    profile_data = profiles.get(profile_name, {})

    if strict and not profile_data and profiles:
        available = sorted(profiles.keys())
        raise ProfileNotFoundError(
            f"Profile '{profile_name}' not found. Available profiles: {', '.join(available)}"
        )

    # Return only known fields, ignoring unknown ones for forward compatibility
    return {k: v for k, v in profile_data.items() if isinstance(v, str | None)}


class GitLabConfig(BaseSettings):
    """GitLab configuration with layered precedence.

    Precedence (highest to lowest):
    1. Values passed directly (CLI flags)
    2. Environment variables (GLTOOLS_*)
    3. Config file values (loaded via from_config)
    4. Field defaults
    """

    host: str = Field(default="https://gitlab.com", description="GitLab instance URL")
    token: str = Field(default="", description="GitLab Personal Access Token")
    default_project: str | None = Field(default=None, description="Default project path (e.g., group/project)")
    output_format: str = Field(default="text", description="Output format: 'json' or 'text'")
    profile: str = Field(default="default", description="Configuration profile name")

    model_config = {
        "env_prefix": "GLTOOLS_",
        "env_file": None,
        "extra": "ignore",
    }

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate that output_format is either 'json' or 'text'."""
        if v not in ("json", "text"):
            raise ValueError(f"output_format must be 'json' or 'text', got '{v}'")
        return v

    @classmethod
    def from_config(
        cls,
        *,
        profile: str | None = None,
        config_path: Path | None = None,
        cli_overrides: dict[str, Any] | None = None,
    ) -> GitLabConfig:
        """Create a GitLabConfig with full layered precedence.

        Precedence is enforced explicitly:
        1. CLI flags (highest)
        2. Environment variables (GLTOOLS_*)
        3. Config file values
        4. Field defaults (lowest)

        Args:
            profile: Profile name to load from config file. If None, uses
                     GLTOOLS_PROFILE env var or defaults to "default".
            config_path: Path to config file. Defaults to ~/.config/gltools/config.toml.
            cli_overrides: Values from CLI flags (highest precedence).

        Returns:
            Configured GitLabConfig instance.
        """
        if config_path is None:
            config_path = get_config_path()

        # Determine profile: CLI override > env var > default
        effective_profile = (
            (cli_overrides or {}).get("profile")
            or profile
            or os.environ.get("GLTOOLS_PROFILE", "default")
        )

        # Layer 3: Config file values
        # Use strict mode when the profile was explicitly specified (not default)
        explicitly_requested = effective_profile != "default"
        file_values = load_profile_from_toml(
            config_path, effective_profile, strict=explicitly_requested
        )
        file_values["profile"] = effective_profile

        # Layer 2: Environment variables
        env_prefix = "GLTOOLS_"
        env_values: dict[str, Any] = {}
        for field_name in cls.model_fields:
            env_key = f"{env_prefix}{field_name.upper()}"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                env_values[field_name] = env_val

        # Layer 1: CLI overrides (filter out None = unset flags)
        active_cli: dict[str, Any] = {}
        if cli_overrides:
            active_cli = {k: v for k, v in cli_overrides.items() if v is not None}

        # Merge layers: file < env < CLI (later updates win)
        merged = {}
        merged.update(file_values)
        merged.update(env_values)
        merged.update(active_cli)

        # Temporarily clear GLTOOLS_* env vars so BaseSettings.__init__
        # doesn't re-read them (we already handled them above).
        saved_env: dict[str, str] = {}
        for field_name in cls.model_fields:
            env_key = f"{env_prefix}{field_name.upper()}"
            if env_key in os.environ:
                saved_env[env_key] = os.environ.pop(env_key)

        try:
            config = cls(**merged)
        finally:
            # Restore env vars
            os.environ.update(saved_env)

        return config

    @property
    def config_file_exists(self) -> bool:
        """Check if the config file exists."""
        return get_config_path().is_file()


def write_config(config_path: Path, content: str) -> None:
    """Write config content to file with secure permissions (600).

    Args:
        config_path: Path to write the config file.
        content: TOML content to write.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content)
    config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions
