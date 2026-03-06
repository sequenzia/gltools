"""Tests for gltools configuration system."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from gltools.config.settings import (
    ConfigFileError,
    GitLabConfig,
    get_config_dir,
    get_config_path,
    load_profile_from_toml,
    write_config,
)

# --- Fixtures ---


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory."""
    config_path = tmp_path / "gltools"
    config_path.mkdir()
    return config_path


@pytest.fixture
def config_file(config_dir: Path) -> Path:
    """Return path to config file in temp directory."""
    return config_dir / "config.toml"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove GLTOOLS_* env vars to avoid test pollution."""
    for key in list(os.environ):
        if key.startswith("GLTOOLS_"):
            monkeypatch.delenv(key, raising=False)


# --- Default Values ---


class TestDefaultValues:
    """Test that default values are applied correctly."""

    def test_default_host(self) -> None:
        config = GitLabConfig()
        assert config.host == "https://gitlab.com"

    def test_default_output_format(self) -> None:
        config = GitLabConfig()
        assert config.output_format == "text"

    def test_default_profile(self) -> None:
        config = GitLabConfig()
        assert config.profile == "default"

    def test_default_token_is_empty(self) -> None:
        config = GitLabConfig()
        assert config.token == ""

    def test_default_project_is_none(self) -> None:
        config = GitLabConfig()
        assert config.default_project is None

    def test_output_format_validation_rejects_invalid(self) -> None:
        with pytest.raises(ValueError, match="output_format must be 'json' or 'text'"):
            GitLabConfig(output_format="yaml")

    def test_output_format_accepts_json(self) -> None:
        config = GitLabConfig(output_format="json")
        assert config.output_format == "json"


# --- TOML File Parsing ---


class TestTomlParsing:
    """Test TOML config file loading."""

    def test_load_default_profile(self, config_file: Path) -> None:
        config_file.write_text(
            '[profiles.default]\nhost = "https://gitlab.example.com"\noutput_format = "json"\n'
        )
        result = load_profile_from_toml(config_file, "default")
        assert result["host"] == "https://gitlab.example.com"
        assert result["output_format"] == "json"

    def test_load_named_profile(self, config_file: Path) -> None:
        config_file.write_text(
            '[profiles.work]\nhost = "https://gitlab.company.com"\ntoken = "work-token"\n'
        )
        result = load_profile_from_toml(config_file, "work")
        assert result["host"] == "https://gitlab.company.com"
        assert result["token"] == "work-token"

    def test_missing_config_file_returns_empty(self, config_dir: Path) -> None:
        result = load_profile_from_toml(config_dir / "nonexistent.toml")
        assert result == {}

    def test_missing_profile_returns_empty(self, config_file: Path) -> None:
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        result = load_profile_from_toml(config_file, "nonexistent")
        assert result == {}

    def test_invalid_toml_raises_config_error(self, config_file: Path) -> None:
        config_file.write_text("invalid [[ toml content !!!")
        with pytest.raises(ConfigFileError, match="Invalid TOML syntax"):
            load_profile_from_toml(config_file)

    def test_unknown_fields_ignored(self, config_file: Path) -> None:
        config_file.write_text(
            '[profiles.default]\nhost = "https://gitlab.com"\nfuture_field = "value"\n'
        )
        result = load_profile_from_toml(config_file, "default")
        assert "future_field" in result  # loaded from file
        # But GitLabConfig ignores unknown fields via extra="ignore"
        config = GitLabConfig(**result)
        assert not hasattr(config, "future_field")

    def test_multiple_profiles_coexist(self, config_file: Path) -> None:
        config_file.write_text(
            '[profiles.default]\nhost = "https://gitlab.com"\n\n'
            '[profiles.work]\nhost = "https://gitlab.company.com"\n'
        )
        default = load_profile_from_toml(config_file, "default")
        work = load_profile_from_toml(config_file, "work")
        assert default["host"] == "https://gitlab.com"
        assert work["host"] == "https://gitlab.company.com"

    def test_multiple_profiles_same_host(self, config_file: Path) -> None:
        """Multiple profiles with the same host should not conflict."""
        config_file.write_text(
            '[profiles.personal]\nhost = "https://gitlab.com"\ntoken = "personal-token"\n\n'
            '[profiles.oss]\nhost = "https://gitlab.com"\ntoken = "oss-token"\n'
        )
        personal = load_profile_from_toml(config_file, "personal")
        oss = load_profile_from_toml(config_file, "oss")
        assert personal["host"] == oss["host"]
        assert personal["token"] != oss["token"]


# --- Config Precedence ---


class TestConfigPrecedence:
    """Test layered configuration precedence: file < env < CLI."""

    def test_file_values_override_defaults(self, config_file: Path) -> None:
        config_file.write_text('[profiles.default]\nhost = "https://custom.gitlab.com"\n')
        config = GitLabConfig.from_config(config_path=config_file)
        assert config.host == "https://custom.gitlab.com"

    def test_env_overrides_file(self, config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_file.write_text('[profiles.default]\nhost = "https://file.gitlab.com"\n')
        monkeypatch.setenv("GLTOOLS_HOST", "https://env.gitlab.com")
        config = GitLabConfig.from_config(config_path=config_file)
        assert config.host == "https://env.gitlab.com"

    def test_cli_overrides_env(self, config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GLTOOLS_HOST", "https://env.gitlab.com")
        config = GitLabConfig.from_config(
            config_path=config_file,
            cli_overrides={"host": "https://cli.gitlab.com"},
        )
        assert config.host == "https://cli.gitlab.com"

    def test_cli_overrides_file(self, config_file: Path) -> None:
        config_file.write_text('[profiles.default]\nhost = "https://file.gitlab.com"\n')
        config = GitLabConfig.from_config(
            config_path=config_file,
            cli_overrides={"host": "https://cli.gitlab.com"},
        )
        assert config.host == "https://cli.gitlab.com"

    def test_full_precedence_chain(self, config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI > env > file > default."""
        config_file.write_text(
            '[profiles.default]\nhost = "https://file.gitlab.com"\ntoken = "file-token"\n'
            'output_format = "json"\n'
        )
        monkeypatch.setenv("GLTOOLS_HOST", "https://env.gitlab.com")
        monkeypatch.setenv("GLTOOLS_TOKEN", "env-token")

        config = GitLabConfig.from_config(
            config_path=config_file,
            cli_overrides={"host": "https://cli.gitlab.com"},
        )

        # host: CLI wins
        assert config.host == "https://cli.gitlab.com"
        # token: env wins (no CLI override)
        assert config.token == "env-token"
        # output_format: file wins (no env or CLI override)
        assert config.output_format == "json"
        # profile: default
        assert config.profile == "default"

    def test_none_cli_overrides_ignored(self, config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI overrides with None values should not override env/file values."""
        monkeypatch.setenv("GLTOOLS_HOST", "https://env.gitlab.com")
        config = GitLabConfig.from_config(
            config_path=config_file,
            cli_overrides={"host": None, "token": "cli-token"},
        )
        assert config.host == "https://env.gitlab.com"
        assert config.token == "cli-token"


# --- Profile Loading and Switching ---


class TestProfileLoading:
    """Test profile loading and switching."""

    def test_load_specific_profile(self, config_file: Path) -> None:
        config_file.write_text(
            '[profiles.default]\nhost = "https://gitlab.com"\n\n'
            '[profiles.work]\nhost = "https://gitlab.company.com"\n'
        )
        config = GitLabConfig.from_config(config_path=config_file, profile="work")
        assert config.host == "https://gitlab.company.com"
        assert config.profile == "work"

    def test_profile_from_env(self, config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_file.write_text(
            '[profiles.default]\nhost = "https://gitlab.com"\n\n'
            '[profiles.staging]\nhost = "https://staging.gitlab.com"\n'
        )
        monkeypatch.setenv("GLTOOLS_PROFILE", "staging")
        config = GitLabConfig.from_config(config_path=config_file)
        assert config.host == "https://staging.gitlab.com"
        assert config.profile == "staging"

    def test_profile_cli_override(self, config_file: Path) -> None:
        config_file.write_text(
            '[profiles.default]\nhost = "https://gitlab.com"\n\n'
            '[profiles.work]\nhost = "https://gitlab.work.com"\n'
        )
        config = GitLabConfig.from_config(
            config_path=config_file,
            cli_overrides={"profile": "work"},
        )
        assert config.host == "https://gitlab.work.com"
        assert config.profile == "work"

    def test_nonexistent_profile_raises_error(self, config_file: Path) -> None:
        from gltools.config.settings import ProfileNotFoundError

        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        with pytest.raises(ProfileNotFoundError, match="Profile 'nonexistent' not found"):
            GitLabConfig.from_config(config_path=config_file, profile="nonexistent")

    def test_no_config_file_returns_defaults(self, config_dir: Path) -> None:
        config = GitLabConfig.from_config(config_path=config_dir / "nonexistent.toml")
        assert config.host == "https://gitlab.com"
        assert config.output_format == "text"
        assert config.token == ""


# --- Config File Writing ---


class TestConfigWriting:
    """Test config file writing with secure permissions."""

    def test_write_config_creates_file(self, config_dir: Path) -> None:
        path = config_dir / "config.toml"
        write_config(path, '[profiles.default]\nhost = "https://gitlab.com"\n')
        assert path.exists()
        assert path.read_text() == '[profiles.default]\nhost = "https://gitlab.com"\n'

    def test_write_config_sets_600_permissions(self, config_dir: Path) -> None:
        path = config_dir / "config.toml"
        write_config(path, "content")
        file_stat = path.stat()
        permissions = stat.S_IMODE(file_stat.st_mode)
        assert permissions == 0o600

    def test_write_config_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "config.toml"
        write_config(path, "content")
        assert path.exists()


# --- Helper Functions ---


class TestHelperFunctions:
    """Test config directory and path helpers."""

    def test_get_config_dir_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = get_config_dir()
        assert result == Path.home() / ".config" / "gltools"

    def test_get_config_dir_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        result = get_config_dir()
        assert result == Path("/custom/config/gltools")

    def test_get_config_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = get_config_path()
        assert result == Path.home() / ".config" / "gltools" / "config.toml"


# --- Error Handling ---


class TestErrorHandling:
    """Test error handling for configuration edge cases."""

    def test_invalid_toml_gives_clear_message(self, config_file: Path) -> None:
        config_file.write_text("not valid toml [[[")
        with pytest.raises(ConfigFileError) as exc_info:
            load_profile_from_toml(config_file)
        assert str(config_file) in str(exc_info.value)
        assert "Invalid TOML syntax" in str(exc_info.value)

    def test_missing_required_token_for_api(self) -> None:
        """Token defaults to empty string; callers should validate before API calls."""
        config = GitLabConfig()
        assert config.token == ""
