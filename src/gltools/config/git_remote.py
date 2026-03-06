"""Git remote detection for auto-resolving GitLab instance URL and project path."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class GitRemoteInfo:
    """Parsed git remote information for a GitLab project."""

    host: str
    """GitLab instance URL, e.g. 'https://gitlab.com'."""

    project_path: str
    """Project path, e.g. 'user/project' or 'group/subgroup/project'."""

    @property
    def project_path_encoded(self) -> str:
        """URL-encoded project path for API calls, e.g. 'user%2Fproject'."""
        return quote(self.project_path, safe="")


# Patterns for parsing git remote URLs
_SSH_PATTERN = re.compile(r"^git@([^:]+):(.+?)(?:\.git)?$")
_HTTPS_PATTERN = re.compile(r"^https?://([^/]+)/(.+?)(?:\.git)?$")
_SSH_PROTOCOL_PATTERN = re.compile(r"^ssh://[^@]+@([^/]+)/(.+?)(?:\.git)?$")


def parse_remote_url(url: str) -> GitRemoteInfo | None:
    """Parse a git remote URL and extract host and project path.

    Supports:
    - SSH: git@gitlab.com:user/project.git
    - HTTPS: https://gitlab.com/user/project.git
    - SSH protocol: ssh://git@gitlab.com/user/project.git
    - All formats with or without .git suffix

    Returns None if the URL cannot be parsed.
    """
    url = url.strip()

    for pattern in (_SSH_PATTERN, _SSH_PROTOCOL_PATTERN, _HTTPS_PATTERN):
        match = pattern.match(url)
        if match:
            host = match.group(1)
            project_path = match.group(2).strip("/")
            return GitRemoteInfo(
                host=f"https://{host}",
                project_path=project_path,
            )

    return None


def get_git_remotes() -> dict[str, str]:
    """Get all git remote names and their fetch URLs.

    Returns an empty dict if not in a git repository or git is not installed.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    if result.returncode != 0:
        return {}

    remotes: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and line.endswith("(fetch)"):
            remotes[parts[0]] = parts[1]

    return remotes


def detect_gitlab_remote(preferred_remote: str = "origin") -> GitRemoteInfo | None:
    """Auto-detect GitLab host and project path from git remotes.

    Checks the preferred remote first (default: 'origin'), then falls back
    to other remotes if the preferred one is not found.

    Returns None if:
    - Not in a git repository
    - Git is not installed
    - No parseable remote URLs found
    """
    remotes = get_git_remotes()
    if not remotes:
        return None

    # Try preferred remote first
    if preferred_remote in remotes:
        info = parse_remote_url(remotes[preferred_remote])
        if info:
            return info

    # Fall back to other remotes
    for name, url in remotes.items():
        if name == preferred_remote:
            continue
        info = parse_remote_url(url)
        if info:
            return info

    return None
