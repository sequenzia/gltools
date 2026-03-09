"""Milestone reference model for GitLab API responses."""

from gltools.models.base import BaseGitLabModel


class MilestoneRef(BaseGitLabModel):
    """Lightweight milestone reference as returned in nested GitLab API objects."""

    id: int
    iid: int
    title: str
    state: str
    web_url: str
