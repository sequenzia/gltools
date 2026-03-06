"""Tests for git remote detection and URL parsing."""

from __future__ import annotations

from unittest.mock import patch

from gltools.config.git_remote import (
    GitRemoteInfo,
    detect_gitlab_remote,
    get_git_remotes,
    parse_remote_url,
)


class TestParseRemoteUrl:
    """Tests for parse_remote_url."""

    def test_ssh_url(self) -> None:
        result = parse_remote_url("git@gitlab.com:user/project.git")
        assert result is not None
        assert result.host == "https://gitlab.com"
        assert result.project_path == "user/project"

    def test_ssh_url_without_git_suffix(self) -> None:
        result = parse_remote_url("git@gitlab.com:user/project")
        assert result is not None
        assert result.host == "https://gitlab.com"
        assert result.project_path == "user/project"

    def test_https_url(self) -> None:
        result = parse_remote_url("https://gitlab.com/user/project.git")
        assert result is not None
        assert result.host == "https://gitlab.com"
        assert result.project_path == "user/project"

    def test_https_url_without_git_suffix(self) -> None:
        result = parse_remote_url("https://gitlab.com/user/project")
        assert result is not None
        assert result.host == "https://gitlab.com"
        assert result.project_path == "user/project"

    def test_ssh_protocol_url(self) -> None:
        result = parse_remote_url("ssh://git@gitlab.com/user/project.git")
        assert result is not None
        assert result.host == "https://gitlab.com"
        assert result.project_path == "user/project"

    def test_ssh_protocol_url_without_git_suffix(self) -> None:
        result = parse_remote_url("ssh://git@gitlab.com/user/project")
        assert result is not None
        assert result.host == "https://gitlab.com"
        assert result.project_path == "user/project"

    def test_subgroup_project_ssh(self) -> None:
        result = parse_remote_url("git@gitlab.com:group/subgroup/project.git")
        assert result is not None
        assert result.host == "https://gitlab.com"
        assert result.project_path == "group/subgroup/project"

    def test_subgroup_project_https(self) -> None:
        result = parse_remote_url("https://gitlab.com/group/subgroup/project.git")
        assert result is not None
        assert result.host == "https://gitlab.com"
        assert result.project_path == "group/subgroup/project"

    def test_deep_subgroup_project(self) -> None:
        result = parse_remote_url("git@gitlab.com:a/b/c/d/project.git")
        assert result is not None
        assert result.project_path == "a/b/c/d/project"

    def test_self_hosted_instance(self) -> None:
        result = parse_remote_url("git@gitlab.company.com:team/project.git")
        assert result is not None
        assert result.host == "https://gitlab.company.com"
        assert result.project_path == "team/project"

    def test_http_url(self) -> None:
        result = parse_remote_url("http://gitlab.local/user/project.git")
        assert result is not None
        assert result.host == "https://gitlab.local"
        assert result.project_path == "user/project"

    def test_invalid_url_returns_none(self) -> None:
        assert parse_remote_url("not-a-url") is None

    def test_empty_string_returns_none(self) -> None:
        assert parse_remote_url("") is None

    def test_whitespace_handling(self) -> None:
        result = parse_remote_url("  git@gitlab.com:user/project.git  ")
        assert result is not None
        assert result.project_path == "user/project"


class TestGitRemoteInfo:
    """Tests for GitRemoteInfo properties."""

    def test_project_path_encoded(self) -> None:
        info = GitRemoteInfo(host="https://gitlab.com", project_path="user/project")
        assert info.project_path_encoded == "user%2Fproject"

    def test_subgroup_path_encoded(self) -> None:
        info = GitRemoteInfo(host="https://gitlab.com", project_path="group/subgroup/project")
        assert info.project_path_encoded == "group%2Fsubgroup%2Fproject"


class TestGetGitRemotes:
    """Tests for get_git_remotes."""

    @patch("gltools.config.git_remote.subprocess.run")
    def test_parses_git_remote_output(self, mock_run: object) -> None:
        mock_run.return_value.returncode = 0  # type: ignore[union-attr]
        mock_run.return_value.stdout = (  # type: ignore[union-attr]
            "origin\tgit@gitlab.com:user/project.git (fetch)\n"
            "origin\tgit@gitlab.com:user/project.git (push)\n"
            "upstream\tgit@gitlab.com:org/project.git (fetch)\n"
            "upstream\tgit@gitlab.com:org/project.git (push)\n"
        )
        remotes = get_git_remotes()
        assert remotes == {
            "origin": "git@gitlab.com:user/project.git",
            "upstream": "git@gitlab.com:org/project.git",
        }

    @patch("gltools.config.git_remote.subprocess.run", side_effect=FileNotFoundError)
    def test_git_not_installed_returns_empty(self, _mock: object) -> None:
        assert get_git_remotes() == {}

    @patch("gltools.config.git_remote.subprocess.run")
    def test_not_a_git_repo_returns_empty(self, mock_run: object) -> None:
        mock_run.return_value.returncode = 128  # type: ignore[union-attr]
        mock_run.return_value.stdout = ""  # type: ignore[union-attr]
        assert get_git_remotes() == {}


class TestDetectGitlabRemote:
    """Tests for detect_gitlab_remote."""

    @patch("gltools.config.git_remote.get_git_remotes")
    def test_uses_origin_by_default(self, mock_remotes: object) -> None:
        mock_remotes.return_value = {  # type: ignore[union-attr]
            "origin": "git@gitlab.com:user/project.git",
            "upstream": "git@gitlab.com:org/project.git",
        }
        result = detect_gitlab_remote()
        assert result is not None
        assert result.project_path == "user/project"

    @patch("gltools.config.git_remote.get_git_remotes")
    def test_configurable_preferred_remote(self, mock_remotes: object) -> None:
        mock_remotes.return_value = {  # type: ignore[union-attr]
            "origin": "git@gitlab.com:user/project.git",
            "upstream": "git@gitlab.com:org/project.git",
        }
        result = detect_gitlab_remote(preferred_remote="upstream")
        assert result is not None
        assert result.project_path == "org/project"

    @patch("gltools.config.git_remote.get_git_remotes")
    def test_falls_back_to_other_remote(self, mock_remotes: object) -> None:
        mock_remotes.return_value = {  # type: ignore[union-attr]
            "upstream": "git@gitlab.com:org/project.git",
        }
        result = detect_gitlab_remote()
        assert result is not None
        assert result.project_path == "org/project"

    @patch("gltools.config.git_remote.get_git_remotes")
    def test_no_remotes_returns_none(self, mock_remotes: object) -> None:
        mock_remotes.return_value = {}  # type: ignore[union-attr]
        assert detect_gitlab_remote() is None

    @patch("gltools.config.git_remote.get_git_remotes")
    def test_non_git_directory_returns_none(self, mock_remotes: object) -> None:
        mock_remotes.return_value = {}  # type: ignore[union-attr]
        result = detect_gitlab_remote()
        assert result is None
