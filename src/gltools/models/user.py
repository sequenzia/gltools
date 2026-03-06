"""User reference model for GitLab API responses."""

from gltools.models.base import BaseGitLabModel


class UserRef(BaseGitLabModel):
    """Lightweight user reference as returned in nested GitLab API objects."""

    id: int
    username: str
    name: str
