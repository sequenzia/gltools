"""Tests verifying multi-instance and profile support for gltools.

Covers:
- Multiple profiles in config.toml
- --profile flag switches between profiles
- Each profile uses correct host and token
- Git remote detection with self-hosted instances
- Keyring stores separate tokens per profile
- Profile not found error with available profiles
- Same project on different instances
- --host and --token flags override profile settings
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from gltools.config.git_remote import parse_remote_url
from gltools.config.keyring import _keyring_key, get_token, store_token
from gltools.config.settings import (
    GitLabConfig,
    ProfileNotFoundError,
    list_profiles,
    load_profile_from_toml,
)


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


MULTI_PROFILE_CONFIG = """\
[profiles.default]
host = "https://gitlab.com"
token = "glpat-default-token"

[profiles.work]
host = "https://gitlab.company.com"
token = "glpat-work-token"
default_project = "team/backend"

[profiles.staging]
host = "https://staging.gitlab.company.com"
token = "glpat-staging-token"
"""


class TestMultipleProfilesInConfig:
    """Verify multiple profiles work in config.toml."""

    def test_load_default_profile_from_multi_config(self, config_file: Path) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)
        config = GitLabConfig.from_config(config_path=config_file)
        assert config.host == "https://gitlab.com"
        assert config.token == "glpat-default-token"
        assert config.profile == "default"

    def test_load_work_profile(self, config_file: Path) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)
        config = GitLabConfig.from_config(config_path=config_file, profile="work")
        assert config.host == "https://gitlab.company.com"
        assert config.token == "glpat-work-token"
        assert config.default_project == "team/backend"
        assert config.profile == "work"

    def test_load_staging_profile(self, config_file: Path) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)
        config = GitLabConfig.from_config(config_path=config_file, profile="staging")
        assert config.host == "https://staging.gitlab.company.com"
        assert config.token == "glpat-staging-token"
        assert config.profile == "staging"

    def test_profiles_are_independent(self, config_file: Path) -> None:
        """Each profile loads its own values without cross-contamination."""
        config_file.write_text(MULTI_PROFILE_CONFIG)
        default = GitLabConfig.from_config(config_path=config_file, profile="default")
        work = GitLabConfig.from_config(config_path=config_file, profile="work")

        assert default.host != work.host
        assert default.token != work.token
        assert default.default_project is None
        assert work.default_project == "team/backend"

    def test_list_profiles_returns_all(self, config_file: Path) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)
        profiles = list_profiles(config_file)
        assert profiles == ["default", "staging", "work"]

    def test_list_profiles_empty_when_no_file(self, config_dir: Path) -> None:
        profiles = list_profiles(config_dir / "nonexistent.toml")
        assert profiles == []


class TestProfileSwitching:
    """Verify --profile flag switches between profiles."""

    def test_cli_profile_override(self, config_file: Path) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)
        config = GitLabConfig.from_config(
            config_path=config_file,
            cli_overrides={"profile": "work"},
        )
        assert config.host == "https://gitlab.company.com"
        assert config.profile == "work"

    def test_env_profile_override(self, config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)
        monkeypatch.setenv("GLTOOLS_PROFILE", "staging")
        config = GitLabConfig.from_config(config_path=config_file)
        assert config.host == "https://staging.gitlab.company.com"
        assert config.profile == "staging"

    def test_cli_profile_overrides_env_profile(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)
        monkeypatch.setenv("GLTOOLS_PROFILE", "staging")
        config = GitLabConfig.from_config(
            config_path=config_file,
            cli_overrides={"profile": "work"},
        )
        assert config.host == "https://gitlab.company.com"
        assert config.profile == "work"


class TestCorrectHostTokenPerProfile:
    """Verify each profile uses the correct host and token."""

    def test_host_and_token_match_profile(self, config_file: Path) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)

        expected = {
            "default": ("https://gitlab.com", "glpat-default-token"),
            "work": ("https://gitlab.company.com", "glpat-work-token"),
            "staging": ("https://staging.gitlab.company.com", "glpat-staging-token"),
        }

        for profile_name, (expected_host, expected_token) in expected.items():
            config = GitLabConfig.from_config(config_path=config_file, profile=profile_name)
            assert config.host == expected_host, f"Profile {profile_name} host mismatch"
            assert config.token == expected_token, f"Profile {profile_name} token mismatch"

    def test_host_override_on_profile(self, config_file: Path) -> None:
        """--host flag overrides the profile's host setting."""
        config_file.write_text(MULTI_PROFILE_CONFIG)
        config = GitLabConfig.from_config(
            config_path=config_file,
            profile="work",
            cli_overrides={"host": "https://override.gitlab.com"},
        )
        assert config.host == "https://override.gitlab.com"
        assert config.token == "glpat-work-token"  # token still from profile

    def test_token_override_on_profile(self, config_file: Path) -> None:
        """--token flag overrides the profile's token setting."""
        config_file.write_text(MULTI_PROFILE_CONFIG)
        config = GitLabConfig.from_config(
            config_path=config_file,
            profile="work",
            cli_overrides={"token": "glpat-override"},
        )
        assert config.host == "https://gitlab.company.com"  # host still from profile
        assert config.token == "glpat-override"

    def test_both_host_and_token_override(self, config_file: Path) -> None:
        """Both --host and --token override profile settings."""
        config_file.write_text(MULTI_PROFILE_CONFIG)
        config = GitLabConfig.from_config(
            config_path=config_file,
            profile="work",
            cli_overrides={"host": "https://custom.com", "token": "glpat-custom"},
        )
        assert config.host == "https://custom.com"
        assert config.token == "glpat-custom"
        assert config.profile == "work"


class TestGitRemoteWithSelfHosted:
    """Verify git remote detection works with self-hosted instances."""

    def test_self_hosted_ssh(self) -> None:
        result = parse_remote_url("git@gitlab.company.com:team/project.git")
        assert result is not None
        assert result.host == "https://gitlab.company.com"
        assert result.project_path == "team/project"

    def test_self_hosted_https(self) -> None:
        result = parse_remote_url("https://gitlab.internal.corp/org/service.git")
        assert result is not None
        assert result.host == "https://gitlab.internal.corp"
        assert result.project_path == "org/service"

    def test_self_hosted_with_port(self) -> None:
        """Port-based self-hosted GitLab URLs parse correctly."""
        result = parse_remote_url("https://git.example.com:8443/team/project.git")
        # The port is part of the host in the HTTPS pattern
        assert result is not None
        assert result.project_path == "team/project"

    def test_different_instances_different_hosts(self) -> None:
        """Same project name on different instances resolves correctly."""
        gitlab_com = parse_remote_url("git@gitlab.com:acme/api.git")
        self_hosted = parse_remote_url("git@gitlab.acme.com:acme/api.git")

        assert gitlab_com is not None
        assert self_hosted is not None
        assert gitlab_com.host == "https://gitlab.com"
        assert self_hosted.host == "https://gitlab.acme.com"
        assert gitlab_com.project_path == self_hosted.project_path  # same path


class TestKeyringPerProfile:
    """Verify keyring stores separate tokens per profile."""

    def test_keyring_key_scoped_per_profile(self) -> None:
        assert _keyring_key("default") == "token:default"
        assert _keyring_key("work") == "token:work"
        assert _keyring_key("personal") == "token:personal"

    def test_store_and_retrieve_different_profiles(self) -> None:
        stored: dict[str, str] = {}

        def mock_set(service: str, key: str, token: str) -> None:
            stored[key] = token

        def mock_get(service: str, key: str) -> str | None:
            return stored.get(key)

        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._delete_token_file"),
        ):
            mock_kr.set_password.side_effect = mock_set
            mock_kr.get_password.side_effect = mock_get

            store_token("token-work", profile="work")
            store_token("token-personal", profile="personal")

            work_token = get_token(profile="work")
            personal_token = get_token(profile="personal")

            assert work_token == "token-work"
            assert personal_token == "token-personal"

    def test_tokens_dont_leak_between_profiles(self) -> None:
        with (
            patch("gltools.config.keyring._is_keyring_available", return_value=True),
            patch("gltools.config.keyring.keyring") as mock_kr,
            patch("gltools.config.keyring._read_token_file", return_value=None),
        ):
            mock_kr.get_password.return_value = None
            result = get_token(profile="nonexistent")
            assert result is None
            mock_kr.get_password.assert_called_once_with("gltools", "token:nonexistent")


class TestProfileNotFoundError:
    """Verify profile not found gives clear error with available profiles."""

    def test_strict_mode_raises_on_missing_profile(self, config_file: Path) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)
        with pytest.raises(ProfileNotFoundError, match="Profile 'nonexistent' not found"):
            load_profile_from_toml(config_file, "nonexistent", strict=True)

    def test_error_lists_available_profiles(self, config_file: Path) -> None:
        config_file.write_text(MULTI_PROFILE_CONFIG)
        with pytest.raises(ProfileNotFoundError, match="default, staging, work"):
            load_profile_from_toml(config_file, "nope", strict=True)

    def test_non_strict_mode_returns_empty(self, config_file: Path) -> None:
        """Default non-strict mode returns empty dict for compatibility."""
        config_file.write_text(MULTI_PROFILE_CONFIG)
        result = load_profile_from_toml(config_file, "nonexistent")
        assert result == {}

    def test_strict_mode_no_error_when_no_profiles_exist(self, config_file: Path) -> None:
        """If there are no profiles at all, don't raise (nothing to suggest)."""
        config_file.write_text("")
        result = load_profile_from_toml(config_file, "anything", strict=True)
        assert result == {}

    def test_from_config_raises_on_explicit_missing_profile(self, config_file: Path) -> None:
        """from_config raises ProfileNotFoundError when explicitly specifying a missing profile."""
        config_file.write_text(MULTI_PROFILE_CONFIG)
        with pytest.raises(ProfileNotFoundError, match="Profile 'bogus' not found"):
            GitLabConfig.from_config(config_path=config_file, profile="bogus")


class TestSameProjectDifferentInstances:
    """Verify same project on different instances resolves correctly."""

    def test_same_project_name_different_hosts(self, config_file: Path) -> None:
        config_file.write_text(
            '[profiles.personal]\nhost = "https://gitlab.com"\ntoken = "personal-token"\n'
            'default_project = "user/myapp"\n\n'
            '[profiles.work]\nhost = "https://gitlab.company.com"\ntoken = "work-token"\n'
            'default_project = "user/myapp"\n'
        )
        personal = GitLabConfig.from_config(config_path=config_file, profile="personal")
        work = GitLabConfig.from_config(config_path=config_file, profile="work")

        # Same project name, different instances
        assert personal.default_project == work.default_project == "user/myapp"
        assert personal.host != work.host
        assert personal.token != work.token

    def test_remote_url_matches_correct_instance(self) -> None:
        """Different remotes point to different GitLab instances."""
        gitlab_info = parse_remote_url("git@gitlab.com:user/myapp.git")
        company_info = parse_remote_url("git@gitlab.company.com:user/myapp.git")

        assert gitlab_info is not None
        assert company_info is not None

        # Same project path but different hosts
        assert gitlab_info.project_path == company_info.project_path
        assert gitlab_info.host != company_info.host
