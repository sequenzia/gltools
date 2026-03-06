"""Job model for GitLab CI/CD API responses."""

from __future__ import annotations

from gltools.models.base import BaseGitLabModel


class Job(BaseGitLabModel):
    """A GitLab CI/CD job within a pipeline."""

    id: int
    name: str
    stage: str
    status: str
    duration: float | None = None
    failure_reason: str | None = None
    web_url: str | None = None
